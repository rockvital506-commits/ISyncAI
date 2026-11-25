#!/usr/bin/env python3
"""Изолированный исполнитель: только синтетические деревья и процессы."""
import hashlib
import importlib.util
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'research/audit')]
import core_audit as audit

RUNNER = ROOT/'kit/snapshot_session.py'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='domain-snapshot-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.candidate = self.root/'candidate'; self.candidate.mkdir()
        manifest = json.loads((ROOT/'kit/KIT-VERSION.json').read_bytes())
        for rel in ('kit/KIT-VERSION.json', *manifest['files']):
            target = self.candidate/rel; target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT/rel, target)
        self.workspace = self.root/'workspace'; self.workspace.mkdir()
        self.layout = audit.make_workspace(self.workspace, parent_scope='.')
        self.manifest_pin = digest(self.candidate/'kit/KIT-VERSION.json')
        self.l0 = self.workspace/'kit/base/registry.json'
        system = json.loads(self.l0.read_bytes()); system['release_version'] = manifest['version']
        audit.write(self.l0, system)  # Синтетический L0, не продуктовый системный реестр.
        self.system_pin = digest(self.l0)
        self.profile = self.workspace/'profiles/pilot/registry.json'
        self.marker = self.root/'untrusted-code-executed'

    def args(self, *, manifest_pin=None, system_pin=None, flags=('-I','-S','-B'), runner=RUNNER):
        return [sys.executable, *flags, str(runner), '--candidate-root', str(self.candidate),
                '--workspace', str(self.workspace), '--profile-root', 'profiles/pilot', '--profile-id', 'Pilot',
                '--manifest-pin', self.manifest_pin if manifest_pin is None else manifest_pin,
                '--system-pin', self.system_pin if system_pin is None else system_pin]

    def launch(self, **kwargs):
        env = dict(os.environ, PYTHONPATH=str(self.root/'untrusted'), PYTHONDONTWRITEBYTECODE='1')
        proc = subprocess.Popen(self.args(**kwargs), cwd=self.workspace, env=env, stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', bufsize=1)
        def cleanup():
            if proc.poll() is None:
                proc.kill()
            proc.communicate(timeout=15)
        self.addCleanup(cleanup)
        lines = queue.Queue()
        def reader():
            for line in proc.stdout:
                lines.put(line)
            lines.put(None)
        thread = threading.Thread(target=reader, daemon=True)
        thread.start()
        return proc, lines

    def send(self, proc, lines, data):
        proc.stdin.write(json.dumps(data, ensure_ascii=False) + '\n'); proc.stdin.flush()
        try:
            line = lines.get(timeout=15)
        except queue.Empty:
            raise AssertionError('нет ответа проверенной сессии') from None
        if line is None:
            raise AssertionError('проверенная сессия завершилась без ответа')
        return json.loads(line)

    def request(self):
        return {'type':'plan', 'request':('Создай черновик контракта C-9 в профиле Pilot, постоянное, '
                'область «docs», название «Пример», основание «Проба», '
                'критерий «Запись существует»: Согласуем порядок чтения.')}

    def check_refusal(self, args=None):
        before = audit.tree_digest(self.workspace)
        result = subprocess.run(args or self.args(), cwd=self.workspace, input='', capture_output=True,
                                text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stdout, '')
        self.assertEqual(before, audit.tree_digest(self.workspace))
        self.assertFalse(self.marker.exists())
        return json.loads(result.stderr)['reason']

    def repin_document(self, rel, data):
        (self.candidate/rel).write_bytes(data)
        manifest = self.candidate/'kit/KIT-VERSION.json'
        doc = json.loads(manifest.read_text(encoding='utf-8'))
        doc['files'][rel] = hashlib.sha256(data).hexdigest()
        manifest.write_text(json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        self.manifest_pin = digest(manifest)

    def test_applicable_uses_pinned_module_and_revokes_pending(self):
        before=audit.tree_digest(self.workspace);proc,lines=self.launch()
        plan=self.send(proc,lines,self.request());self.assertEqual(plan['outcome'],'planned')
        report=self.send(proc,lines,{'type':'applicable','scope':'docs/readme.md'})
        self.assertEqual(report['outcome'],'applicable')
        self.assertEqual({row['area'] for row in report['entries']},{'L0','L1','L2'})
        self.assertEqual(report['inputs_sha256']['L0'],self.system_pin)
        again=self.send(proc,lines,{'type':'apply','plan':plan,'confirmed_ticket':plan['ticket']})
        self.assertEqual(again['diagnostic']['code'],'ticket_unknown')
        self.assertEqual(before,audit.tree_digest(self.workspace))

    def test_start_is_pinned_minimal_and_not_workspace_input(self):
        entry = self.candidate/'kit/base/entry.txt'
        start = self.candidate/'kit/base/START.md'
        for name in ('entry.txt', 'START.md'):
            (self.workspace/'kit/base'/name).write_text('UNTRUSTED-WORKSPACE-INPUT', encoding='utf-8')
        before = audit.tree_digest(self.workspace)
        proc, lines = self.launch()
        result = self.send(proc, lines, {'type':'bootstrap'})
        self.assertEqual(result['outcome'], 'bootstrap')
        self.assertEqual(result['manifest_sha256'], self.manifest_pin)
        self.assertEqual(result['start_file_sha256'], digest(start))
        section = result['section0'].encode('utf-8')
        self.assertTrue(start.read_bytes().startswith(section))
        self.assertTrue(section.endswith(b'<!-- /bootstrap-0 -->\n'))
        self.assertNotIn('## 1.', result['section0'])
        self.assertNotIn('UNTRUSTED-WORKSPACE-INPUT', result['section0'])
        self.assertEqual(result['inputs'], [
            {'file':'kit/base/entry.txt', 'bytes':len(entry.read_bytes()), 'sha256':digest(entry)},
            {'file':'kit/base/START.md', 'bytes':len(section), 'sha256':hashlib.sha256(section).hexdigest()}])
        self.assertEqual(audit.tree_digest(self.workspace), before)
        self.assertEqual(self.send(proc, lines, {'type':'bootstrap', 'extra':True})['code'], 'invalid_request')
        direct = subprocess.run([sys.executable, '-I', '-S', '-B', str(ROOT/'kit/session_cli.py'),
            '--workspace', str(self.workspace), '--profile-root', 'profiles/pilot', '--profile-id', 'Pilot'],
            input='{"type":"bootstrap"}\n', capture_output=True, text=True, timeout=30)
        self.assertEqual(direct.returncode, 0, direct.stderr)
        self.assertEqual(json.loads(direct.stdout)['code'], 'invalid_request')

    def test_start_missing_and_link_rejected(self):
        path = self.candidate/'kit/base/entry.txt'; original = path.read_bytes()
        path.unlink()
        self.assertEqual(self.check_refusal(), 'candidate_unverified')
        try:
            path.symlink_to(ROOT/'kit/base/entry.txt')
        except OSError as exc:
            self.skipTest('символические ссылки недоступны: '+str(exc))
        self.assertEqual(self.check_refusal(), 'source_file_invalid')
        path.unlink(); path.write_bytes(original)

    def test_changed_start_revokes_plan_and_refuses_bootstrap(self):
        proc, lines = self.launch()
        source = self.candidate/'kit/base/START.md'; original = source.read_bytes()
        plan = self.send(proc, lines, self.request())
        self.assertEqual(plan['outcome'], 'planned')
        source.write_bytes(original + b'\nmutation\n')
        self.assertEqual(self.send(proc, lines, {'type':'bootstrap'}),
                         {'outcome':'error','code':'runtime_preflight_failed'})
        source.write_bytes(original)
        result = self.send(proc, lines, {'type':'apply','plan':plan,'confirmed_ticket':plan['ticket']})
        self.assertEqual(result['diagnostic']['code'], 'ticket_unknown')

    def test_start_invalid_or_unpinned_refuses(self):
        for rel in ('kit/base/entry.txt', 'kit/base/START.md'):
            path = self.candidate/rel; old = path.read_bytes()
            path.write_bytes(old + b'mutation')
            self.assertEqual(self.check_refusal(), 'candidate_unverified')
            path.write_bytes(old)
        self.repin_document('kit/base/entry.txt', b'wrong\n')
        self.assertEqual(self.check_refusal(), 'bootstrap_unverified')
        self.repin_document('kit/base/entry.txt', b'kit/base/START.md#0\n')
        for data in (b'## 0. Title\n\n<!-- /bootstrap-0 -->\n',
                     b'## 0. Title\nbody\n## 1. Next\n<!-- /bootstrap-0 -->\n',
                     b'## 0. Title\n'+b'x'*4100+b'\n<!-- /bootstrap-0 -->\n',
                     b'## 0. Title\n\xff\n<!-- /bootstrap-0 -->\n'):
            self.repin_document('kit/base/START.md', data)
            self.assertEqual(self.check_refusal(), 'bootstrap_unverified')
        self.repin_document('kit/base/START.md', b'x' * (2_097_152 + 1))
        self.assertEqual(self.check_refusal(), 'source_file_invalid')

    def test_crlf_start_and_pointer(self):
        self.repin_document('kit/base/entry.txt', b'kit/base/START.md#0\r\n')
        data = b'## 0. Title\r\nbody\r\n<!-- /bootstrap-0 -->\r\n## 1. hidden\r\n'
        self.repin_document('kit/base/START.md', data)
        proc, lines = self.launch()
        result = self.send(proc, lines, {'type':'bootstrap'})
        self.assertEqual(result['section0'], '## 0. Title\r\nbody\r\n<!-- /bootstrap-0 -->\r\n')
        self.assertEqual(result['start_file_sha256'], hashlib.sha256(data).hexdigest())

    def test_verified_plan_and_explicit_apply(self):
        proc, lines = self.launch()
        before = self.profile.read_bytes()
        plan = self.send(proc, lines, self.request())
        self.assertEqual(plan['outcome'], 'planned')
        self.assertEqual(plan['replacement_notice'], audit.PLAN4_NOTICE)
        self.assertEqual(self.profile.read_bytes(), before)
        forged = dict(plan); forged['replacement_notice'] = 'без предупреждения о гонке'
        altered = self.send(proc, lines, {'type':'apply', 'plan':forged, 'confirmed_ticket':plan['ticket']})
        self.assertEqual(altered['diagnostic']['code'], 'plan_mismatch')
        self.assertEqual(self.profile.read_bytes(), before)
        refusal = self.send(proc, lines, {'type':'apply', 'plan':plan, 'confirmed_ticket':''})
        self.assertEqual(refusal['diagnostic']['code'], 'confirmation_required')
        self.assertEqual(self.profile.read_bytes(), before)
        result = self.send(proc, lines, {'type':'apply', 'plan':plan, 'confirmed_ticket':plan['ticket']})
        self.assertEqual(result['outcome'], 'applied')
        doc = json.loads(self.profile.read_text(encoding='utf-8'))
        self.assertEqual(doc['registry']['entries'][-1]['id'], 'C-9')
        self.assertEqual(doc['registry']['entries'][-1]['state'], 'draft')

    def test_cancel_revokes_ticket_in_snapshot_session(self):
        proc, lines = self.launch(); before = audit.tree_digest(self.workspace)
        plan = self.send(proc, lines, self.request())
        self.assertEqual(plan['outcome'], 'planned')
        self.assertEqual(self.send(proc, lines, {'type':'cancel'}), {'outcome':'cancelled'})
        self.assertEqual(self.send(proc, lines, {'type':'cancel'}), {'outcome':'cancelled'})
        denied = self.send(proc, lines, {'type':'apply', 'plan':plan, 'confirmed_ticket':plan['ticket']})
        self.assertEqual(denied['diagnostic']['code'], 'ticket_unknown')
        self.assertEqual(audit.tree_digest(self.workspace), before)

    def test_workspace_code_and_pythonpath_are_not_imported(self):
        for folder in (self.workspace/'kit/base', self.root/'untrusted/kit/base'):
            folder.mkdir(parents=True, exist_ok=True)
            (folder/'registry_store.py').write_text('from pathlib import Path\nPath('+repr(str(self.marker))+').touch()\n', encoding='utf-8')
        proc, lines = self.launch()
        got = self.send(proc, lines, self.request())
        self.assertEqual(got['outcome'], 'planned')
        self.assertFalse(self.marker.exists())

    def test_bad_pins_and_missing_isolation_fail_before_session(self):
        self.assertEqual(self.check_refusal(self.args(manifest_pin='0'*64)), 'candidate_unverified')
        self.assertEqual(self.check_refusal(self.args(manifest_pin='bad')), 'pin_required')
        self.assertEqual(self.check_refusal(self.args(system_pin='0'*64)), 'runtime_unverified')
        self.assertEqual(self.check_refusal(self.args(system_pin='bad')), 'pin_required')
        self.assertEqual(self.check_refusal(self.args(flags=('-B',))), 'isolated_python_required')

    def test_version_mismatch_with_matching_system_pin_refuses_before_commands(self):
        before = audit.tree_digest(self.workspace)
        system = json.loads(self.l0.read_bytes()); system['release_version'] = '0.2.0-mvp.20'
        audit.write(self.l0, system)
        self.system_pin = digest(self.l0)  # Совпадение хеша не подтверждает совместимость.
        changed = audit.tree_digest(self.workspace)
        self.assertNotEqual(before, changed)
        self.assertEqual(self.check_refusal(), 'runtime_unverified')
        self.assertEqual(audit.tree_digest(self.workspace), changed)

    def test_missing_registry_or_workspace_mismatch_fail_closed(self):
        project = self.workspace/'.domain-agent-kit/project/registry.json'
        project.unlink()  # только синтетическая временная копия
        self.assertEqual(self.check_refusal(), 'runtime_unverified')
        args = self.args()
        index = args.index('--workspace') + 1
        args[index] = 'relative-workspace'
        self.assertEqual(self.check_refusal(args), 'workspace_invalid')
        args = self.args()
        index = args.index('--candidate-root') + 1
        args[index] = 'relative-candidate'
        self.assertEqual(self.check_refusal(args), 'candidate_root_invalid')

    def test_overlapping_source_workspace_and_trusted_directories_refused(self):
        # До загрузки кандидата: совпадение и вложенность в обоих направлениях для каждой пары.
        pairs = ((0, 1), (0, 2), (1, 2))
        for pair in pairs:
            for relation in ('equal', 'first_inside', 'second_inside'):
                with self.subTest(pair=pair, relation=relation):
                    sandbox = self.root/('case-%s-%s-%s' % (*pair, relation)); sandbox.mkdir()
                    paths = [sandbox/'source', sandbox/'work', sandbox/'trusted']
                    a, b = pair
                    if relation == 'equal':
                        paths[b] = paths[a]
                    elif relation == 'first_inside':
                        paths[a] = paths[b]/'nested'
                    else:
                        paths[b] = paths[a]/'nested'
                    for path in paths:
                        path.mkdir(parents=True, exist_ok=True)
                    for name in ('snapshot_session.py', 'verify_candidate.py'):
                        shutil.copyfile(ROOT/'kit'/name, paths[2]/name)
                    before = audit.tree_digest(sandbox)
                    cmd = [sys.executable, '-I', '-S', '-B', str(paths[2]/'snapshot_session.py'),
                           '--candidate-root', str(paths[0]), '--workspace', str(paths[1]),
                           '--profile-root', 'profiles/pilot', '--profile-id', 'Pilot',
                           '--manifest-pin', self.manifest_pin, '--system-pin', self.system_pin]
                    result = subprocess.run(cmd, input='{"type":"bootstrap"}\n', capture_output=True,
                                            text=True, timeout=30)
                    self.assertEqual(result.returncode, 1, result.stderr)
                    self.assertEqual(result.stdout, '')
                    self.assertEqual(json.loads(result.stderr)['reason'], 'roots_overlap')
                    self.assertEqual(audit.tree_digest(sandbox), before)

    def test_aliases_are_resolved_for_overlap_and_disjoint_paths(self):
        alias = self.root/'alias'
        try:
            alias.symlink_to(self.candidate, target_is_directory=True)
        except OSError as exc:
            self.skipTest('символические ссылки недоступны: '+str(exc))
        args = self.args()
        args[args.index('--workspace') + 1] = str(alias)
        self.assertEqual(self.check_refusal(args), 'roots_overlap')
        alias.unlink(); alias.symlink_to(self.candidate/'kit', target_is_directory=True)
        self.assertEqual(self.check_refusal(args), 'roots_overlap')
        alias.unlink(); alias.symlink_to(self.candidate, target_is_directory=True)
        self.candidate = alias
        proc, lines = self.launch()
        self.assertEqual(self.send(proc, lines, {'type':'bootstrap'})['outcome'], 'bootstrap')

    def test_similar_path_prefixes_are_not_nested(self):
        sibling = self.root/'candidate-other'
        shutil.copytree(self.workspace, sibling)
        self.workspace = sibling
        proc, lines = self.launch()
        self.assertEqual(self.send(proc, lines, {'type':'bootstrap'})['outcome'], 'bootstrap')

    def test_root_alias_drift_revokes_pending_plan(self):
        for which in ('candidate', 'workspace'):
            with self.subTest(root=which):
                original = getattr(self, which)
                alias = self.root/(which+'-link')
                try:
                    alias.symlink_to(original, target_is_directory=True)
                except OSError as exc:
                    self.skipTest('символические ссылки недоступны: '+str(exc))
                setattr(self, which, alias)
                proc, lines = self.launch()
                plan = self.send(proc, lines, self.request())
                self.assertEqual(plan['outcome'], 'planned')
                before = audit.tree_digest(self.root/'workspace')
                other = self.root/(which+'-other'); other.mkdir()
                alias.unlink(); alias.symlink_to(other, target_is_directory=True)
                denied = self.send(proc, lines, {'type':'apply', 'plan':plan, 'confirmed_ticket':plan['ticket']})
                self.assertEqual(denied, {'outcome':'error', 'code':'runtime_preflight_failed'})
                self.assertEqual(audit.tree_digest(self.root/'workspace'), before)
                alias.unlink(); alias.symlink_to(original, target_is_directory=True)
                stale = self.send(proc, lines, {'type':'apply', 'plan':plan, 'confirmed_ticket':plan['ticket']})
                self.assertEqual(stale['diagnostic']['code'], 'ticket_unknown')
                self.assertEqual(audit.tree_digest(self.root/'workspace'), before)
                setattr(self, which, original)
                proc.kill(); proc.wait(timeout=15)

    def test_trusted_path_alias_drift_revokes_pending_plan(self):
        for directory in (self.root/'trusted-a', self.root/'trusted-b'):
            directory.mkdir()
            for name in ('snapshot_session.py', 'verify_candidate.py'):
                shutil.copyfile(ROOT/'kit'/name, directory/name)
        alias = self.root/'trusted-link'
        try:
            alias.symlink_to(self.root/'trusted-a', target_is_directory=True)
        except OSError as exc:
            self.skipTest('символические ссылки недоступны: '+str(exc))
        proc, lines = self.launch(runner=alias/'snapshot_session.py')
        plan = self.send(proc, lines, self.request())
        self.assertEqual(plan['outcome'], 'planned')
        before = audit.tree_digest(self.workspace)
        alias.unlink(); alias.symlink_to(self.root/'trusted-b', target_is_directory=True)
        denied = self.send(proc, lines, {'type':'apply', 'plan':plan, 'confirmed_ticket':plan['ticket']})
        self.assertEqual(denied, {'outcome':'error', 'code':'runtime_preflight_failed'})
        self.assertEqual(audit.tree_digest(self.workspace), before)
        alias.unlink(); alias.symlink_to(self.root/'trusted-a', target_is_directory=True)
        stale = self.send(proc, lines, {'type':'apply', 'plan':plan, 'confirmed_ticket':plan['ticket']})
        self.assertEqual(stale['diagnostic']['code'], 'ticket_unknown')
        self.assertEqual(audit.tree_digest(self.workspace), before)

    def test_replaced_same_path_roots_revoke_plan_even_with_identical_files(self):
        trusted = self.root/'trusted'; trusted.mkdir()
        for name in ('snapshot_session.py', 'verify_candidate.py'):
            shutil.copyfile(ROOT/'kit'/name, trusted/name)
        for name, directory in (('candidate', self.candidate), ('workspace', self.workspace), ('trusted', trusted)):
            with self.subTest(root=name):
                replacement = self.root/(name+'-replacement')
                saved = self.root/(name+'-saved')
                shutil.copytree(directory, replacement)
                self.assertEqual(audit.tree_digest(directory), audit.tree_digest(replacement))
                self.assertNotEqual((directory.stat().st_dev, directory.stat().st_ino),
                                    (replacement.stat().st_dev, replacement.stat().st_ino))
                proc, lines = self.launch(runner=trusted/'snapshot_session.py')
                plan = self.send(proc, lines, self.request())
                self.assertEqual(plan['outcome'], 'planned')
                before = audit.tree_digest(self.workspace)
                directory.rename(saved); replacement.rename(directory)
                self.assertEqual(audit.tree_digest(directory), audit.tree_digest(saved))
                denied = self.send(proc, lines, {'type':'apply', 'plan':plan, 'confirmed_ticket':plan['ticket']})
                self.assertEqual(denied, {'outcome':'error', 'code':'runtime_preflight_failed'})
                self.assertEqual(audit.tree_digest(self.workspace), before)
                if name == 'workspace':
                    self.assertEqual(audit.tree_digest(saved), before)
                directory.rename(replacement); saved.rename(directory)
                stale = self.send(proc, lines, {'type':'apply', 'plan':plan, 'confirmed_ticket':plan['ticket']})
                self.assertEqual(stale['diagnostic']['code'], 'ticket_unknown')
                self.assertEqual(audit.tree_digest(self.workspace), before)
                proc.kill(); proc.wait(timeout=15)

    def test_identical_or_unavailable_root_identity_is_refused(self):
        # Имитируем файловую систему с одинаковыми/недоступными номерами, без bind mount.
        spec = importlib.util.spec_from_file_location('snapshot_identity_test', RUNNER)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        original_stat = Path.stat
        source_info = original_stat(self.candidate)
        for mode in ('same', 'zero'):
            def simulated(path, *args, **kwargs):
                info = original_stat(path, *args, **kwargs)
                if path == self.workspace:
                    return SimpleNamespace(st_mode=info.st_mode, st_dev=source_info.st_dev,
                                           st_ino=source_info.st_ino if mode == 'same' else 0)
                return info
            with self.subTest(mode=mode), patch.object(Path, 'stat', simulated):
                with self.assertRaises(module.SnapshotError) as raised:
                    module._roots(self.candidate, self.workspace)
                self.assertEqual(str(raised.exception), 'roots_overlap' if mode == 'same' else 'roots_invalid')

    def test_same_root_does_not_attest_trusted_file_contents(self):
        trusted = self.root/'trusted'; trusted.mkdir()
        for name in ('snapshot_session.py', 'verify_candidate.py'):
            shutil.copyfile(ROOT/'kit'/name, trusted/name)
        proc, lines = self.launch(runner=trusted/'snapshot_session.py')
        self.assertEqual(self.send(proc, lines, {'type':'bootstrap'})['outcome'], 'bootstrap')
        identity = (trusted.stat().st_dev, trusted.stat().st_ino)
        (trusted/'verify_candidate.py').write_text('untrusted replacement\n', encoding='utf-8')
        self.assertEqual((trusted.stat().st_dev, trusted.stat().st_ino), identity)
        before = audit.tree_digest(self.workspace)
        # Сосед загружен при старте; содержимое файла доверенного инструмента не сверяется.
        self.assertEqual(self.send(proc, lines, {'type':'bootstrap'})['outcome'], 'bootstrap')
        self.assertEqual(audit.tree_digest(self.workspace), before)

    def test_missing_or_non_directory_roots_refused(self):
        for root in ('candidate', 'workspace'):
            for path in (self.root/'missing', self.l0):
                with self.subTest(root=root, path=path):
                    args = self.args(); flag = '--candidate-root' if root == 'candidate' else '--workspace'
                    args[args.index(flag) + 1] = str(path)
                    self.assertEqual(self.check_refusal(args), 'roots_invalid')

    def test_modified_source_rejected_without_executing_it(self):
        file = self.candidate/'kit/base/registry_store.py'
        file.write_text('from pathlib import Path\nPath('+repr(str(self.marker))+').touch()\n', encoding='utf-8')
        self.assertEqual(self.check_refusal(), 'candidate_unverified')

    def test_replaced_l0_refuses_and_revokes_pending_plan(self):
        proc, lines = self.launch()
        original_l0 = self.l0.read_bytes()
        before_profile = self.profile.read_bytes()
        plan = self.send(proc, lines, self.request())
        self.assertEqual(plan['outcome'], 'planned')
        self.l0.write_bytes(original_l0 + b' ')
        result = self.send(proc, lines, {'type':'apply', 'plan':plan, 'confirmed_ticket':plan['ticket']})
        self.assertEqual(result, {'outcome':'error', 'code':'runtime_preflight_failed'})
        self.assertEqual(self.profile.read_bytes(), before_profile)
        self.l0.write_bytes(original_l0)
        stale = self.send(proc, lines, {'type':'apply', 'plan':plan, 'confirmed_ticket':plan['ticket']})
        self.assertEqual(stale['diagnostic']['code'], 'ticket_unknown')
        self.assertEqual(self.profile.read_bytes(), before_profile)

    def test_new_formal_conflict_refuses_command_without_selecting_winner(self):
        proc, lines = self.launch()
        plan = self.send(proc, lines, self.request())
        self.assertEqual(plan['outcome'], 'planned')
        project = self.workspace/'.domain-agent-kit/project/registry.json'
        profile = json.loads(self.profile.read_text(encoding='utf-8'))
        row = audit.entry('R-profile', 'rule', 'profile_owner', 'C-1', '.', text='профиль')
        row.update(key='policy', value='first'); profile['entries'].append(row); audit.write(self.profile, profile)
        project_doc = json.loads(project.read_text(encoding='utf-8'))
        row = audit.entry('R-project', 'rule', 'project_owner', 'P-1', '.', text='проект')
        row.update(key='policy', value='second'); project_doc['entries'].append(row); audit.write(project, project_doc)
        before = audit.tree_digest(self.workspace)
        result = self.send(proc, lines, {'type':'apply', 'plan':plan, 'confirmed_ticket':plan['ticket']})
        self.assertEqual(result, {'outcome':'error', 'code':'runtime_preflight_failed'})
        self.assertEqual(audit.tree_digest(self.workspace), before)

    def test_changed_source_after_plan_refuses_and_revokes_ticket(self):
        proc, lines = self.launch()
        source = self.candidate/'kit/base/operation_plan.py'
        original = source.read_bytes()
        before_profile = self.profile.read_bytes()
        plan = self.send(proc, lines, self.request())
        source.write_bytes(original + b'\n# synthetic mutation\n')
        result = self.send(proc, lines, {'type':'apply', 'plan':plan, 'confirmed_ticket':plan['ticket']})
        self.assertEqual(result, {'outcome':'error', 'code':'runtime_preflight_failed'})
        self.assertEqual(self.profile.read_bytes(), before_profile)
        source.write_bytes(original)
        stale = self.send(proc, lines, {'type':'apply', 'plan':plan, 'confirmed_ticket':plan['ticket']})
        self.assertEqual(stale['diagnostic']['code'], 'ticket_unknown')
        self.assertEqual(self.profile.read_bytes(), before_profile)

    def test_source_symlink_and_hardlink_rejected(self):
        source = self.candidate/'kit/base/operation_card.py'
        original = source.read_bytes(); source.unlink()
        try:
            source.symlink_to(ROOT/'kit/base/operation_card.py')
        except OSError as exc:
            self.skipTest('символические ссылки недоступны: '+str(exc))
        self.assertEqual(self.check_refusal(), 'source_file_invalid')
        source.unlink(); source.write_bytes(original)
        alias = self.root/'alias.py'
        try:
            os.link(source, alias)
        except OSError as exc:
            self.skipTest('жёсткие ссылки недоступны: '+str(exc))
        self.assertEqual(self.check_refusal(), 'source_file_invalid')

    def test_closed_source_rejects_unlisted_objects_without_writing(self):
        for rel, is_dir in (('extra.txt', False), ('kit/extra.py', False),
                            ('kit/examples', True), ('kit/base/__pycache__', True),
                            ('kit/base/nested', True)):
            with self.subTest(path=rel):
                p = self.candidate/rel
                if is_dir:
                    p.mkdir()
                else:
                    p.write_text('synthetic extra', encoding='utf-8')
                self.assertEqual(self.check_refusal(), 'candidate_unverified')
                if is_dir:
                    p.rmdir()  # Только созданный в этой пробе пустой каталог.
                else:
                    p.unlink()

    def test_unlisted_file_after_plan_revokes_ticket(self):
        proc, lines = self.launch()
        plan = self.send(proc, lines, self.request())
        self.assertEqual(plan['outcome'], 'planned')
        before = audit.tree_digest(self.workspace)
        extra = self.candidate/'kit/unlisted.py'; extra.write_text('unused', encoding='utf-8')
        denied = self.send(proc, lines, {'type':'apply', 'plan':plan, 'confirmed_ticket':plan['ticket']})
        self.assertEqual(denied, {'outcome':'error','code':'runtime_preflight_failed'})
        self.assertEqual(audit.tree_digest(self.workspace), before)
        extra.unlink()  # Только тестовый объект.
        stale = self.send(proc, lines, {'type':'apply', 'plan':plan, 'confirmed_ticket':plan['ticket']})
        self.assertEqual(stale['diagnostic']['code'], 'ticket_unknown')
        self.assertEqual(audit.tree_digest(self.workspace), before)

    def test_nonexecuted_member_size_and_hardlink_are_checked(self):
        path = self.candidate/'kit/base/SCHEMA-V2.md'; original = path.read_bytes()
        self.repin_document('kit/base/SCHEMA-V2.md', b'x' * (2_097_152 + 1))
        self.assertEqual(self.check_refusal(), 'source_file_invalid')
        self.repin_document('kit/base/SCHEMA-V2.md', original)
        alias = self.root/'outside-alias'
        try:
            os.link(path, alias)
        except OSError as exc:
            self.skipTest('жёсткие ссылки недоступны: '+str(exc))
        self.assertEqual(self.check_refusal(), 'source_file_invalid')

    def test_excessive_member_count_with_local_pin_rejected(self):
        manifest = self.candidate/'kit/KIT-VERSION.json'
        doc = json.loads(manifest.read_bytes())
        for i in range(1025):
            doc['files'][f'kit/base/synthetic-{i}.txt'] = '0'*64
        manifest.write_text(json.dumps(doc, sort_keys=True)+'\n', encoding='utf-8')
        self.manifest_pin = digest(manifest)  # Тестовый pin не устанавливает подлинность.
        self.assertEqual(self.check_refusal(), 'candidate_unverified')

    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'FIFO недоступен')
    def test_nonregular_member_refused_without_blocking(self):
        target = self.candidate/'kit/base/SCHEMA-V2.md'
        target.unlink()  # Только синтетический файл во временной копии.
        os.mkfifo(target)
        self.assertEqual(self.check_refusal(), 'source_file_invalid')

    def test_snapshotted_bytes_and_unknown_kit_module(self):
        # Отдельный -I-процесс доказывает загрузку уже закреплённых байтов после изменения
        # на диске; это не обещание работы с конкурирующим процессом в production.
        payload = r'''import importlib, importlib.util, sys
from pathlib import Path
runner, root, pin, marker = sys.argv[1:]
spec=importlib.util.spec_from_file_location('trusted_loader',runner)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
root,sources,start=m.capture(Path(root),pin,m._trusted_verifier())
path=root/'kit/base/registry_policy.py'
path.write_bytes(path.read_bytes()+b'\nfrom pathlib import Path\nPath('+repr(marker).encode()+b').touch()\n')
(root/'kit/unexpected.py').write_text('raise AssertionError("unexpected fallback")\n')
sys.meta_path.insert(0,m.SnapshotFinder(sources))
loaded=importlib.import_module('kit.base.registry_policy')
assert callable(loaded.operation_matrix) and not Path(marker).exists()
try: importlib.import_module('kit.unexpected')
except ModuleNotFoundError: pass
else: raise AssertionError('unlisted kit module loaded')
print('snapshot-ok')
'''
        result = subprocess.run([sys.executable,'-I','-S','-B','-c',payload,str(RUNNER),str(self.candidate),
                                 self.manifest_pin,str(self.marker)], capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'snapshot-ok')
        self.assertFalse(self.marker.exists())


if __name__ == '__main__':
    unittest.main()
