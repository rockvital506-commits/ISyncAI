#!/usr/bin/env python3
"""Подготовка снимка только во временных синтетических каталогах."""
import copy
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

spec = importlib.util.spec_from_file_location('snapshot_export_test', ROOT/'kit/snapshot_export.py')
export = importlib.util.module_from_spec(spec); spec.loader.exec_module(export)


class ExportTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='domain-export-synthetic-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.source = self.root/'source'; self.source.mkdir()
        shutil.copytree(ROOT/'kit', self.source/'kit', ignore=shutil.ignore_patterns('__pycache__'))
        (self.source/'unrelated.txt').write_text('не читать как часть снимка', encoding='utf-8')
        (self.source/'kit/unlisted.py').write_text('raise AssertionError("untrusted code")\n', encoding='utf-8')
        self.parent = self.root/'output'; self.parent.mkdir()
        self.dest = self.parent/'snapshot'
        self.pin = hashlib.sha256((self.source/'kit/KIT-VERSION.json').read_bytes()).hexdigest()
        self.loader = export._trusted_loader(); self.verifier = self.loader._trusted_verifier()
        self.session = export.ExportSession(self.source, self.dest, self.pin, self.loader, self.verifier)

    def error(self, expected, operation, *args):
        with self.assertRaises(export.ExportError) as caught:
            operation(*args)
        self.assertEqual(str(caught.exception), expected)

    def test_plan_confirm_and_exact_snapshot(self):
        source_before = audit.tree_digest(self.source)
        plan = self.session.plan()
        self.assertEqual(plan['outcome'], 'planned')
        self.assertEqual(plan['publication'], {'existing_destination':'refuse', 'failure':'leave_unverified',
            'directory_mode':'0700_before_umask', 'file_mode':'0600_before_umask'})
        self.assertFalse(self.dest.exists())
        doc = json.loads((self.source/'kit/KIT-VERSION.json').read_bytes())
        self.assertEqual({r['path'] for r in plan['files']}, set(doc['files']) | {'kit/KIT-VERSION.json'})
        self.assertEqual(len(plan['files']), len(doc['files'])+1)
        self.error('confirmation_required', self.session.apply, plan, '')
        self.error('confirmation_required', self.session.apply, plan, 'ошибка')
        self.assertFalse(self.dest.exists())
        result = self.session.apply(plan, plan['ticket'])
        self.assertEqual(result['outcome'], 'created')
        self.assertEqual(result['files'], len(doc['files'])+1)
        self.assertEqual(audit.tree_digest(self.source), source_before)
        self.assertEqual({p.relative_to(self.dest).as_posix() for p in self.dest.rglob('*') if p.is_file()},
                         {r['path'] for r in plan['files']})
        self.assertFalse((self.dest/'kit/unlisted.py').exists())
        self.assertFalse((self.dest/'kit/examples').exists())
        self.loader._strict_source(self.dest, self.pin, self.verifier)
        self.error('ticket_unknown', self.session.apply, plan, plan['ticket'])
        self.error('destination_occupied', self.session.plan)

    def test_changed_plan_and_source_refuse_without_destination(self):
        plan = self.session.plan()
        changed = copy.deepcopy(plan); changed['files'][0]['sha256'] = '0'*64
        self.error('plan_mismatch', self.session.apply, changed, plan['ticket'])
        self.error('ticket_unknown', self.session.apply, plan, plan['ticket'])
        self.assertFalse(self.dest.exists())
        plan = self.session.plan()
        f = self.source/'kit/base/operation_plan.py'; f.write_bytes(f.read_bytes()+b'\n# test\n')
        self.error('source_unverified', self.session.apply, plan, plan['ticket'])
        self.assertFalse(self.dest.exists())
        self.error('ticket_unknown', self.session.apply, plan, plan['ticket'])

    def test_wrong_pin_limit_overlap_and_existing_target(self):
        self.session.pin = '0'*64
        self.error('source_unverified', self.session.plan)
        self.session.pin = 'bad'
        self.error('pin_required', self.session.plan)
        self.session.pin = self.pin
        with patch.object(export, 'MAX_TOTAL', 10):
            self.error('source_unverified', self.session.plan)
        self.session.destination = self.source/'inside'
        self.error('path_overlap', self.session.plan)
        self.session.destination = self.dest
        self.dest.mkdir(); sentinel = self.dest/'sentinel'; sentinel.write_bytes(b'preserve')
        self.error('destination_occupied', self.session.plan)
        self.assertEqual(sentinel.read_bytes(), b'preserve')

    def test_overlaps_with_trusted_directory_are_refused_before_plan(self):
        for pair in ('source', 'destination'):
            for relation in ('same', 'inside_trusted', 'contains_trusted'):
                with self.subTest(pair=pair, relation=relation):
                    case = self.root/(pair+'-'+relation); case.mkdir()
                    source = case/'source'; source.mkdir()
                    parent = case/'out'; parent.mkdir()
                    dest = parent/'snapshot'
                    trusted = case/'trusted'; trusted.mkdir()
                    if pair == 'source':
                        if relation == 'same': source = trusted
                        elif relation == 'inside_trusted': source = trusted/'source'; source.mkdir()
                        else: trusted = source/'trusted'; trusted.mkdir()
                    else:
                        if relation == 'same': dest = trusted
                        elif relation == 'inside_trusted': dest = trusted/'snapshot'
                        else: dest = case/'container'; dest.mkdir(); trusted = dest/'trusted'; trusted.mkdir()
                    tool = trusted/'snapshot_export.py'; tool.write_text('# synthetic\n')
                    before = audit.tree_digest(case)
                    session = export.ExportSession(source, dest, self.pin, self.loader, self.verifier)
                    with patch.object(export, '__file__', str(tool)):
                        self.error('path_overlap', session.plan)
                    self.assertEqual(audit.tree_digest(case), before)
                    self.assertIsNone(session.pending)

    def test_replaced_source_same_bytes_revokes_plan_without_destination(self):
        plan = self.session.plan()
        replacement = self.root/'replacement-source'; shutil.copytree(self.source, replacement)
        saved = self.root/'saved-source'
        self.assertEqual(audit.tree_digest(self.source), audit.tree_digest(replacement))
        self.assertNotEqual(self.source.stat().st_ino, replacement.stat().st_ino)
        self.source.rename(saved); replacement.rename(self.source)
        self.error('stale_plan', self.session.apply, plan, plan['ticket'])
        self.assertFalse(self.dest.exists())
        self.assertEqual(audit.tree_digest(self.source), audit.tree_digest(saved))
        self.source.rename(replacement); saved.rename(self.source)
        self.error('ticket_unknown', self.session.apply, plan, plan['ticket'])
        self.assertFalse(self.dest.exists())

    def test_replaced_trusted_root_same_bytes_revokes_plan_without_destination(self):
        trusted = self.root/'trusted'; trusted.mkdir()
        for name in ('snapshot_export.py', 'snapshot_session.py', 'verify_candidate.py'):
            shutil.copyfile(ROOT/'kit'/name, trusted/name)
        replacement = self.root/'replacement-trusted'; shutil.copytree(trusted, replacement)
        saved = self.root/'saved-trusted'
        self.assertEqual(audit.tree_digest(trusted), audit.tree_digest(replacement))
        self.assertNotEqual(trusted.stat().st_ino, replacement.stat().st_ino)
        with patch.object(export, '__file__', str(trusted/'snapshot_export.py')):
            plan = self.session.plan()
            trusted.rename(saved); replacement.rename(trusted)
            self.error('stale_plan', self.session.apply, plan, plan['ticket'])
            self.assertFalse(self.dest.exists())
            self.assertEqual(audit.tree_digest(trusted), audit.tree_digest(saved))
            trusted.rename(replacement); saved.rename(trusted)
            self.error('ticket_unknown', self.session.apply, plan, plan['ticket'])
            self.assertFalse(self.dest.exists())

    def test_same_trusted_root_does_not_attest_its_files(self):
        trusted = self.root/'trusted'; trusted.mkdir()
        for name in ('snapshot_export.py', 'snapshot_session.py', 'verify_candidate.py'):
            shutil.copyfile(ROOT/'kit'/name, trusted/name)
        with patch.object(export, '__file__', str(trusted/'snapshot_export.py')):
            plan = self.session.plan()
            old = (trusted.stat().st_dev, trusted.stat().st_ino)
            (trusted/'verify_candidate.py').write_text('synthetic replacement\n', encoding='utf-8')
            self.assertEqual((trusted.stat().st_dev, trusted.stat().st_ino), old)
            # Используется уже загруженный проверяющий; файл тройки заново не удостоверяется.
            self.assertEqual(self.session.apply(plan, plan['ticket'])['outcome'], 'created')

    def test_zero_inode_and_identical_root_ids_are_refused(self):
        original_lstat = Path.lstat
        source_info = original_lstat(self.source)
        for kind in ('zero', 'same'):
            def simulated(path, *args, **kwargs):
                info = original_lstat(path, *args, **kwargs)
                if path == self.parent:
                    return SimpleNamespace(st_mode=info.st_mode, st_dev=source_info.st_dev,
                                           st_ino=0 if kind == 'zero' else source_info.st_ino)
                return info
            with self.subTest(kind=kind), patch.object(Path, 'lstat', simulated):
                self.error('path_invalid' if kind == 'zero' else 'path_overlap', self.session.plan)
                self.assertFalse(self.dest.exists())

    def test_source_replaced_during_plan_refuses_and_no_ticket(self):
        replacement = self.root/'replacement-source'; shutil.copytree(self.source, replacement)
        saved = self.root/'saved-source'; real_source = export._source
        def replaced(*args):
            data = real_source(*args)
            self.source.rename(saved); replacement.rename(self.source)
            return data
        with patch.object(export, '_source', side_effect=replaced):
            self.error('paths_changed', self.session.plan)
        self.assertIsNone(self.session.pending)
        self.assertFalse(self.dest.exists())
        self.assertEqual(audit.tree_digest(self.source), audit.tree_digest(saved))

    def test_parent_symlink_and_occupied_race(self):
        link = self.root/'symlink-parent'
        try:
            link.symlink_to(self.parent, target_is_directory=True)
        except OSError as exc:
            self.skipTest('ссылки недоступны: '+str(exc))
        self.session.destination = link/'other'
        self.error('path_invalid', self.session.plan)
        self.session.destination = self.dest
        plan = self.session.plan()
        self.dest.mkdir(); sentinel = self.dest/'sentinel'; sentinel.write_bytes(b'unchanged')
        self.error('destination_occupied', self.session.apply, plan, plan['ticket'])
        self.assertEqual(sentinel.read_bytes(), b'unchanged')
        self.error('ticket_unknown', self.session.apply, plan, plan['ticket'])

    def test_new_plan_and_reservation_failure_never_write(self):
        old = self.session.plan(); current = self.session.plan()
        self.assertNotEqual(old['ticket'], current['ticket'])
        self.error('confirmation_required', self.session.apply, old, old['ticket'])
        self.assertFalse(self.dest.exists())
        with patch.object(export.os, 'mkdir', side_effect=PermissionError('synthetic denied')):
            self.error('destination_unavailable', self.session.apply, current, current['ticket'])
        self.assertFalse(self.dest.exists())
        self.error('ticket_unknown', self.session.apply, current, current['ticket'])

    def test_replaced_parent_revokes_plan_without_writing(self):
        plan = self.session.plan()
        old = self.root/'previous-parent'
        self.parent.rename(old)  # Только новый временный синтетический каталог.
        self.parent.mkdir()
        self.error('stale_plan', self.session.apply, plan, plan['ticket'])
        self.assertEqual(list(self.parent.iterdir()), [])
        self.assertEqual(list(old.iterdir()), [])
        self.error('ticket_unknown', self.session.apply, plan, plan['ticket'])

    def test_failed_write_leaves_partial_never_overwrites_or_deletes(self):
        plan = self.session.plan(); source_before = audit.tree_digest(self.source)
        original = export._write_exclusive; calls = []
        def fail_after_first(path, data):
            calls.append(path)
            if len(calls) == 2:
                raise OSError('synthetic failure')
            original(path, data)
        with patch.object(export, '_write_exclusive', side_effect=fail_after_first):
            self.error('destination_partial_or_unverified', self.session.apply, plan, plan['ticket'])
        self.assertTrue(self.dest.is_dir())
        self.assertEqual(len([p for p in self.dest.rglob('*') if p.is_file()]), 1)
        self.assertEqual(audit.tree_digest(self.source), source_before)
        self.error('ticket_unknown', self.session.apply, plan, plan['ticket'])
        self.error('destination_occupied', self.session.plan)
        with self.assertRaises(Exception):
            self.loader._strict_source(self.dest, self.pin, self.verifier)

    def test_failures_at_creation_and_final_verification_leave_untrusted_target(self):
        for stage in ('mkdir_kit', 'last_file', 'verify'):
            with self.subTest(stage=stage):
                self.dest = self.parent/stage
                self.session = export.ExportSession(self.source, self.dest, self.pin, self.loader, self.verifier)
                plan = self.session.plan()
                original_mkdir = os.mkdir
                original_write = export._write_exclusive
                calls = []
                def mkdir(path, *args, **kwargs):
                    if stage == 'mkdir_kit' and Path(path) == self.dest/'kit':
                        raise OSError('synthetic mkdir failure')
                    return original_mkdir(path, *args, **kwargs)
                def write(path, data):
                    calls.append(path)
                    if stage == 'last_file' and len(calls) == len(plan['files']):
                        raise OSError('synthetic late write failure')
                    original_write(path, data)
                def strict(root, pin, verifier):
                    if stage == 'verify':
                        raise OSError('synthetic verify failure')
                    return real_strict(root, pin, verifier)
                real_strict = self.loader._strict_source
                with patch.object(export.os, 'mkdir', side_effect=mkdir), \
                     patch.object(export, '_write_exclusive', side_effect=write), \
                     patch.object(self.loader, '_strict_source', side_effect=strict):
                    self.error('destination_partial_or_unverified', self.session.apply, plan, plan['ticket'])
                self.assertTrue(self.dest.is_dir())
                self.error('destination_occupied', self.session.plan)

    def test_failure_at_each_file_leaves_only_partial_destination(self):
        count = len(self.session.plan()['files'])
        original = export._write_exclusive
        for fail_at in range(1, count + 1):
            self.dest = self.parent/('file-failure-' + str(fail_at))
            self.session = export.ExportSession(self.source, self.dest, self.pin, self.loader, self.verifier)
            plan = self.session.plan(); calls = []
            def write(path, data):
                calls.append(path)
                if len(calls) == fail_at:
                    raise OSError('synthetic file failure')
                original(path, data)
            with patch.object(export, '_write_exclusive', side_effect=write):
                self.error('destination_partial_or_unverified', self.session.apply, plan, plan['ticket'])
            self.assertTrue(self.dest.is_dir())
            self.assertEqual(len([p for p in self.dest.rglob('*') if p.is_file()]), fail_at - 1)
            self.error('destination_occupied', self.session.plan)

    def test_abrupt_exit_after_writes_never_marks_success_or_allows_overwrite(self):
        total = len(self.session.plan()['files'])
        payload = r'''import importlib.util, os, sys
from pathlib import Path
runner, src, dst, pin, fail_at = sys.argv[1:]
spec=importlib.util.spec_from_file_location('trusted_export',runner)
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
l=m._trusted_loader(); v=l._trusted_verifier()
s=m.ExportSession(Path(src),Path(dst),pin,l,v); p=s.plan()
original=m._write_exclusive; count=0
def write(path, data):
 global count
 original(path,data); count+=1
 if count==int(fail_at): os._exit(77)
m._write_exclusive=write
s.apply(p,p['ticket'])
raise AssertionError('exit not reached')
'''
        before = audit.tree_digest(self.source)
        for fail_at in (1, total):
            with self.subTest(fail_at=fail_at):
                dest = self.parent/('crash-' + str(fail_at))
                p = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', payload,
                    str(ROOT/'kit/snapshot_export.py'), str(self.source), str(dest), self.pin, str(fail_at)],
                    capture_output=True, text=True, timeout=30)
                self.assertEqual(p.returncode, 77, p.stderr)
                self.assertEqual(p.stdout, '')
                self.assertTrue(dest.is_dir())
                self.assertEqual(len([f for f in dest.rglob('*') if f.is_file()]), fail_at)
                retry = export.ExportSession(self.source, dest, self.pin, self.loader, self.verifier)
                self.error('destination_occupied', retry.plan)
        self.assertEqual(audit.tree_digest(self.source), before)

    def test_source_symlink_and_extra_base_rejected(self):
        p = self.source/'kit/base/SCHEMA-V2.md'; p.unlink()
        try:
            p.symlink_to(ROOT/'kit/base/SCHEMA-V2.md')
        except OSError as exc:
            self.skipTest('ссылки недоступны: '+str(exc))
        self.error('source_unverified', self.session.plan)
        self.assertFalse(self.dest.exists())
        p.unlink(); shutil.copyfile(ROOT/'kit/base/SCHEMA-V2.md', p)
        (self.source/'kit/base/extra').write_text('x')
        self.error('source_unverified', self.session.plan)
        self.assertFalse(self.dest.exists())

    def test_process_export_then_verified_session(self):
        # Исполняется только независимая доверенная тестовая тройка, а не код источника.
        trusted = self.root/'trusted'; trusted.mkdir()
        for name in ('snapshot_export.py', 'snapshot_session.py', 'verify_candidate.py'):
            shutil.copyfile(ROOT/'kit'/name, trusted/name)
        proc = subprocess.Popen([sys.executable,'-I','-S','-B',str(trusted/'snapshot_export.py'),
              '--source',str(self.source),'--destination',str(self.dest),'--manifest-pin',self.pin],
              stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', bufsize=1)
        def cleanup():
            if proc.poll() is None: proc.kill()
            proc.communicate(timeout=15)
        self.addCleanup(cleanup)
        lines = queue.Queue()
        def reader():
            for line in proc.stdout: lines.put(line)
            lines.put(None)
        threading.Thread(target=reader,daemon=True).start()
        def send(message):
            proc.stdin.write(json.dumps(message,ensure_ascii=False)+'\n'); proc.stdin.flush()
            try: line = lines.get(timeout=15)
            except queue.Empty: raise AssertionError('нет ответа') from None
            self.assertIsNotNone(line, 'процесс вышел без ответа')
            return json.loads(line)
        plan = send({'type':'plan'}); self.assertEqual(plan['outcome'],'planned')
        self.assertFalse(self.dest.exists())
        denied = send({'type':'apply','plan':plan,'confirmed_ticket':''})
        self.assertEqual(denied['code'],'confirmation_required'); self.assertFalse(self.dest.exists())
        applied = send({'type':'apply','plan':plan,'confirmed_ticket':plan['ticket']})
        self.assertEqual(applied['outcome'],'created')
        workspace = self.root/'workspace'; workspace.mkdir(); audit.make_workspace(workspace, parent_scope='.')
        l0 = workspace/'kit/base/registry.json'
        system = json.loads(l0.read_bytes())
        system['release_version'] = json.loads((self.source/'kit/KIT-VERSION.json').read_bytes())['version']
        audit.write(l0, system)  # Версия синтетической раскладки, не рабочая установка.
        system_pin = hashlib.sha256(l0.read_bytes()).hexdigest()
        p = subprocess.run([sys.executable,'-I','-S','-B',str(trusted/'snapshot_session.py'),
            '--candidate-root',str(self.dest),'--workspace',str(workspace),'--profile-root','profiles/pilot',
            '--profile-id','Pilot','--manifest-pin',self.pin,'--system-pin',system_pin],
            input='{"type":"bootstrap"}\n',capture_output=True,text=True,encoding='utf-8',timeout=30)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout)['outcome'], 'bootstrap')

    def test_process_replaced_trusted_root_refuses_and_revokes_ticket(self):
        trusted = self.root/'trusted-process'; trusted.mkdir()
        for name in ('snapshot_export.py', 'snapshot_session.py', 'verify_candidate.py'):
            shutil.copyfile(ROOT/'kit'/name, trusted/name)
        replacement = self.root/'trusted-copy'; shutil.copytree(trusted, replacement)
        saved = self.root/'trusted-saved'
        proc = subprocess.Popen([sys.executable, '-I', '-S', '-B', str(trusted/'snapshot_export.py'),
            '--source', str(self.source), '--destination', str(self.dest), '--manifest-pin', self.pin],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding='utf-8', bufsize=1)
        def cleanup():
            if proc.poll() is None: proc.kill()
            proc.communicate(timeout=15)
        self.addCleanup(cleanup)
        lines = queue.Queue()
        def reader():
            for line in proc.stdout: lines.put(line)
            lines.put(None)
        threading.Thread(target=reader, daemon=True).start()
        def send(message):
            proc.stdin.write(json.dumps(message)+'\n'); proc.stdin.flush()
            try: line = lines.get(timeout=15)
            except queue.Empty: raise AssertionError('нет ответа экспортёра') from None
            self.assertIsNotNone(line, 'экспортёр завершился без ответа')
            return json.loads(line)
        plan = send({'type':'plan'}); self.assertEqual(plan['outcome'], 'planned')
        trusted.rename(saved); replacement.rename(trusted)
        denied = send({'type':'apply', 'plan':plan, 'confirmed_ticket':plan['ticket']})
        self.assertEqual(denied, {'outcome':'error', 'code':'stale_plan'})
        self.assertFalse(self.dest.exists())
        trusted.rename(replacement); saved.rename(trusted)
        stale = send({'type':'apply', 'plan':plan, 'confirmed_ticket':plan['ticket']})
        self.assertEqual(stale, {'outcome':'error', 'code':'ticket_unknown'})
        self.assertFalse(self.dest.exists())

    def test_requires_isolated_python(self):
        p = subprocess.run([sys.executable,'-B',str(ROOT/'kit/snapshot_export.py'),
            '--source',str(self.source),'--destination',str(self.dest),'--manifest-pin',self.pin],
            input='{"type":"plan"}\n',capture_output=True,text=True,timeout=30)
        self.assertEqual(p.returncode, 2)
        self.assertIn('isolated_python_required', p.stderr)
        self.assertFalse(self.dest.exists())


if __name__ == '__main__':
    unittest.main()
