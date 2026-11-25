#!/usr/bin/env python3
"""Диагностика L1/L2 в синтетических деревьях; не живой полигон и не синхронизация."""
import hashlib
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

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'research/audit')]
import core_audit as audit
from kit.base import registry_journal, registry_store, schema_v2


def digest(data):
    return hashlib.sha256(data).hexdigest()


class ProfilePortabilityTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='domain-portability-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.source = self.root/'source'; self.source.mkdir()
        self.trusted = self.root/'trusted'; self.trusted.mkdir()
        self.manifest_raw = (ROOT/'kit/KIT-VERSION.json').read_bytes()
        self.manifest = json.loads(self.manifest_raw)
        self.manifest_pin = digest(self.manifest_raw)
        for rel in ('kit/KIT-VERSION.json', *self.manifest['files']):
            path = self.source/rel; path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT/rel, path)
        for name in ('snapshot_session.py', 'verify_candidate.py'):
            shutil.copyfile(ROOT/'kit'/name, self.trusted/name)
        self.ws = {}
        for label in ('A', 'B'):
            workspace = self.root/label; workspace.mkdir()
            audit.make_workspace(workspace, parent_scope='.')
            system = workspace/'kit/base/registry.json'
            doc = json.loads(system.read_bytes()); doc['entries'] = []
            doc['release_version'] = self.manifest['version']; audit.write(system, doc)
            project = workspace/'.domain-agent-kit/project/registry.json'
            project_doc = json.loads(project.read_bytes())
            project_doc['entries'][0]['title'] = 'Synthetic project ' + label
            audit.write(project, project_doc)
            self.ws[label] = workspace
        self.system_pin = digest((self.ws['A']/'kit/base/registry.json').read_bytes())
        self.assertEqual(self.system_pin, digest((self.ws['B']/'kit/base/registry.json').read_bytes()))
        self.procs = []
        self.addCleanup(self.stop_processes)

    def stop_processes(self):
        for proc in self.procs:
            if proc.poll() is None: proc.kill()
            proc.communicate(timeout=15)

    def args(self, label, profile='profiles/pilot'):
        return [sys.executable, '-I', '-S', '-B', str(self.trusted/'snapshot_session.py'),
                '--candidate-root', str(self.source), '--workspace', str(self.ws[label]),
                '--profile-root', profile, '--profile-id', 'Pilot',
                '--manifest-pin', self.manifest_pin, '--system-pin', self.system_pin]

    def launch(self, label):
        proc = subprocess.Popen(self.args(label), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, encoding='utf-8', bufsize=1,
                                env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
        self.procs.append(proc)
        lines = queue.Queue()
        def reader():
            for line in proc.stdout: lines.put(line)
            lines.put(None)
        threading.Thread(target=reader, daemon=True).start()
        return proc, lines

    def send(self, session, data):
        proc, lines = session
        proc.stdin.write(json.dumps(data, ensure_ascii=False)+'\n'); proc.stdin.flush()
        try: line = lines.get(timeout=15)
        except queue.Empty: raise AssertionError('нет ответа сессии') from None
        self.assertIsNotNone(line, 'сессия завершилась без ответа')
        return json.loads(line)

    def add_contract(self, session, ident):
        request = (f'Создай черновик контракта {ident} в профиле Pilot, постоянное, '
                   'область «docs», название «Пример», основание «Проба», '
                   'критерий «Запись существует»: Согласуем порядок чтения.')
        plan = self.send(session, {'type':'plan', 'request':request})
        self.assertEqual(plan['outcome'], 'planned', plan)
        refused = self.send(session, {'type':'apply', 'plan':plan, 'confirmed_ticket':''})
        self.assertEqual(refused['diagnostic']['code'], 'confirmation_required')
        result = self.send(session, {'type':'apply', 'plan':plan, 'confirmed_ticket':plan['ticket']})
        self.assertEqual(result['outcome'], 'applied', result)

    def profile(self, label):
        return self.ws[label]/'profiles/pilot/registry.json'

    def project(self, label):
        return self.ws[label]/'.domain-agent-kit/project/registry.json'

    def read_profile(self, label):
        doc = schema_v2.parse_json(self.profile(label).read_bytes())
        return registry_journal.unpack_registry(doc, area='L1')

    def startup_refused(self, label, profile='profiles/pilot'):
        result = subprocess.run(self.args(label, profile), input='{"type":"bootstrap"}\n',
                                capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stdout, '')
        self.assertEqual(json.loads(result.stderr)['reason'], 'runtime_unverified')

    def test_independent_copies_diverge_even_at_same_revision(self):
        self.assertEqual(self.profile('A').read_bytes(), self.profile('B').read_bytes())
        l0s = {key:(ws/'kit/base/registry.json').read_bytes() for key,ws in self.ws.items()}
        projects = {key:self.project(key).read_bytes() for key in self.ws}
        self.assertNotEqual(projects['A'], projects['B'])
        a, b = self.launch('A'), self.launch('B')
        self.assertEqual(self.send(a, {'type':'bootstrap'})['outcome'], 'bootstrap')
        self.assertEqual(self.send(b, {'type':'bootstrap'})['outcome'], 'bootstrap')
        before_b = self.profile('B').read_bytes()
        self.add_contract(a, 'C-9')
        self.assertEqual(self.profile('B').read_bytes(), before_b)
        self.add_contract(b, 'C-10')
        ar, ah = self.read_profile('A'); br, bh = self.read_profile('B')
        self.assertEqual((ar['revision'], br['revision']), (1, 1))
        self.assertNotEqual(self.profile('A').read_bytes(), self.profile('B').read_bytes())
        self.assertEqual(ah['decisions'][-1]['entry_id'], 'C-9')
        self.assertEqual(bh['decisions'][-1]['entry_id'], 'C-10')
        for key, workspace in self.ws.items():
            self.assertEqual((workspace/'kit/base/registry.json').read_bytes(), l0s[key])
            self.assertEqual(self.project(key).read_bytes(), projects[key])
        # Две успешные локальные проверки не выявляют расхождения копий одного профиля.
        self.assertEqual(self.send(a, {'type':'bootstrap'})['outcome'], 'bootstrap')
        self.assertEqual(self.send(b, {'type':'bootstrap'})['outcome'], 'bootstrap')

    def test_project_change_stays_in_selected_project(self):
        a, b = self.launch('A'), self.launch('B')
        before = {key:audit.tree_digest(ws) for key,ws in self.ws.items()}
        request = ('Создай черновик контракта P-9 в проекте, постоянное, '
                   'область «docs», название «Пример», основание «Проба», '
                   'критерий «Запись существует»: Согласуем порядок чтения.')
        plan = self.send(a, {'type':'plan', 'request':request})
        self.assertEqual(plan['outcome'], 'planned', plan)
        self.assertEqual({key:audit.tree_digest(ws) for key,ws in self.ws.items()}, before)
        self.assertEqual(self.send(a, {'type':'apply', 'plan':plan, 'confirmed_ticket':''})
                         ['diagnostic']['code'], 'confirmation_required')
        applied = self.send(a, {'type':'apply', 'plan':plan, 'confirmed_ticket':plan['ticket']})
        self.assertEqual(applied['outcome'], 'applied')
        after = {key:audit.tree_digest(ws) for key,ws in self.ws.items()}
        self.assertEqual({name for name in before['A'] if before['A'][name] != after['A'][name]},
                         {'.domain-agent-kit/project/registry.json'})
        self.assertEqual(after['B'], before['B'])
        document = schema_v2.parse_json(self.project('A').read_bytes())
        registry, journal = registry_journal.unpack_registry(document, area='L2')
        self.assertEqual(registry['revision'], 1)
        self.assertEqual(journal['decisions'][-1]['entry_id'], 'P-9')
        self.assertEqual(self.send(b, {'type':'bootstrap'})['outcome'], 'bootstrap')

    def test_manual_copy_preserves_past_history_but_not_future_synchronization(self):
        a = self.launch('A'); self.add_contract(a, 'C-9')
        # Только синтетические фикстуры: прямое копирование намеренно не описывается как API Kit.
        self.profile('B').write_bytes(self.profile('A').read_bytes())
        self.assertEqual(self.profile('A').read_bytes(), self.profile('B').read_bytes())
        _, initial = self.read_profile('B')
        self.assertEqual(initial['decisions'][-1]['entry_id'], 'C-9')
        b = self.launch('B')
        self.add_contract(a, 'C-10'); self.add_contract(b, 'C-11')
        ar, ah = self.read_profile('A'); br, bh = self.read_profile('B')
        self.assertEqual((ar['revision'], br['revision']), (2, 2))
        self.assertEqual([d['entry_id'] for d in ah['decisions']], ['C-9', 'C-10'])
        self.assertEqual([d['entry_id'] for d in bh['decisions']], ['C-9', 'C-11'])
        self.assertNotEqual(self.profile('A').read_bytes(), self.profile('B').read_bytes())

    def test_absolute_and_parent_escape_profile_paths_refused(self):
        before = {key:audit.tree_digest(ws) for key,ws in self.ws.items()}
        for profile in (str(self.ws['A']/'profiles/pilot'), '../A/profiles/pilot', '../../A/profiles/pilot'):
            with self.subTest(profile=profile): self.startup_refused('B', profile)
        self.assertEqual(before, {key:audit.tree_digest(ws) for key,ws in self.ws.items()})

    def test_profile_directory_symlink_to_other_workspace_is_refused(self):
        target = self.ws['B']/'profiles/pilot'
        backup = self.ws['B']/'profiles/saved-pilot'
        target.rename(backup)  # Только новый тестовый каталог.
        try:
            target.symlink_to(self.ws['A']/'profiles/pilot', target_is_directory=True)
        except OSError as exc:
            self.skipTest('символические ссылки недоступны: '+str(exc))
        before_a = audit.tree_digest(self.ws['A']); saved = (backup/'registry.json').read_bytes()
        project_b = self.project('B').read_bytes()
        self.startup_refused('B')
        self.assertEqual(audit.tree_digest(self.ws['A']), before_a)
        self.assertEqual((backup/'registry.json').read_bytes(), saved)
        self.assertEqual(self.project('B').read_bytes(), project_b)

    def test_hardlinked_profile_file_refused_in_both_workspaces(self):
        b = self.profile('B'); backup = b.with_name('saved-registry.json')
        b.rename(backup)
        try: os.link(self.profile('A'), b)
        except OSError as exc: self.skipTest('жёсткие ссылки недоступны: '+str(exc))
        original = self.profile('A').read_bytes(); saved = backup.read_bytes()
        self.startup_refused('A'); self.startup_refused('B')
        self.assertEqual(self.profile('A').read_bytes(), original)
        self.assertEqual(b.read_bytes(), original)
        self.assertEqual(backup.read_bytes(), saved)

    def test_l2_is_fixed_by_each_workspace_in_current_layout(self):
        layouts = {key:registry_store.Layout(ws, 'profiles/pilot') for key,ws in self.ws.items()}
        a = registry_store._load(layouts['A']); b = registry_store._load(layouts['B'])
        self.assertEqual(a.files['L2'], self.project('A'))
        self.assertEqual(b.files['L2'], self.project('B'))
        self.assertNotEqual(a.files['L2'], b.files['L2'])
        help_result = subprocess.run([sys.executable, '-I', '-S', '-B',
              str(self.trusted/'snapshot_session.py'), '--help'], capture_output=True, text=True, timeout=30)
        self.assertEqual(help_result.returncode, 0)
        self.assertNotIn('--project-root', help_result.stdout)


if __name__ == '__main__':
    unittest.main()
