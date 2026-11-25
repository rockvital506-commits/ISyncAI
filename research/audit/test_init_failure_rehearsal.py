#!/usr/bin/env python3
"""Тестовая репетиция сбоев в собственных temp-каталогах; не установщик Kit."""
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'research/audit')]
import init_model
from kit.guard import guard, GuardViolation
from kit.base.registry_store import Layout

# Эта последовательность — только искусственный сценарий теста, не код инициализации Kit.
DIRS = ('kit', 'kit/base', 'profiles', 'profiles/pilot',
        '.domain-agent-kit', '.domain-agent-kit/project')
FILES = ('kit/base/registry.json', 'profiles/pilot/registry.json',
         '.domain-agent-kit/project/registry.json')
TOTAL_STEPS = 1 + len(DIRS) + len(FILES)


class InjectedFailure(Exception):
    pass


def rehearsal(workspace, files, hook):
    """Вспомогательный код пробы: вызывается только на новых каталогах теста."""
    operations = [('dir', workspace)] + [('dir', workspace/p) for p in DIRS]
    operations += [('file', workspace/p) for p in FILES]
    for index, (kind, path) in enumerate(operations):
        hook('before', index)
        if kind == 'dir':
            path.mkdir(mode=0o700)  # Без exist_ok: занятый корень запрещён.
        else:
            data = files[path.relative_to(workspace).as_posix()]
            with path.open('xb') as out:
                middle = len(data)//2
                out.write(data[:middle])
                hook('mid', index)
                out.write(data[middle:])
        hook('after', index)
    return 'synthetic_complete'


class InitFailureRehearsalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='domain-init-failure-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.manifest = (ROOT/'kit/KIT-VERSION.json').read_bytes()
        self.version = json.loads(self.manifest)['version']
        l0 = {'schema_version':2, 'area':'L0', 'roots':['kit'],
              'release_version':self.version, 'entries':[]}
        self.raw = (json.dumps(l0, sort_keys=True)+'\n').encode()
        self.pin = hashlib.sha256(self.raw).hexdigest()
        self.plan, self.files = init_model.model(self.raw, system_pin=self.pin,
            candidate_version=self.version, profile_root='profiles/pilot')
        self.assertEqual(self.plan['outcome'], 'study_only')

    def case(self, name):
        parent = self.root/name; parent.mkdir()
        sentinel = parent/'untouched-sentinel'; sentinel.write_bytes(b'synthetic sentinel')
        return parent, parent/'workspace', sentinel

    def verify_guard(self, workspace):
        return guard(ROOT, Layout(workspace, 'profiles/pilot'),
            manifest_pin=hashlib.sha256(self.manifest).hexdigest(), system_pin=self.pin)

    def assert_retry_refused(self, workspace):
        before = self.snapshot(workspace)
        with self.assertRaises(FileExistsError):
            rehearsal(workspace, self.files, lambda *_: None)
        self.assertEqual(self.snapshot(workspace), before)

    def snapshot(self, root):
        result = {}
        for p in root.rglob('*'):
            name = p.relative_to(root).as_posix()
            result[name] = ('dir',) if p.is_dir() else ('file', p.read_bytes())
        return result

    def assert_known_partial(self, workspace):
        snapshot = self.snapshot(workspace)
        self.assertLessEqual(set(snapshot), set(DIRS) | set(FILES))
        for name, state in snapshot.items():
            if name in DIRS:
                self.assertEqual(state, ('dir',))
            else:
                self.assertEqual(state[0], 'file')
                self.assertTrue(self.files[name].startswith(state[1]))

    def test_success_and_existing_root_never_overwritten(self):
        parent, workspace, sentinel = self.case('success')
        self.assertEqual(rehearsal(workspace, self.files, lambda *_: None), 'synthetic_complete')
        self.assertEqual({p.relative_to(workspace).as_posix() for p in workspace.rglob('*') if p.is_file()},
                         set(FILES))
        for rel in FILES:
            self.assertEqual((workspace/rel).read_bytes(), self.files[rel])
        self.assertEqual(self.verify_guard(workspace)['outcome'], 'pass')
        self.assert_retry_refused(workspace)
        self.assertEqual(sentinel.read_bytes(), b'synthetic sentinel')
        other_parent, occupied, other_sentinel = self.case('occupied')
        occupied.mkdir(); (occupied/'existing').write_bytes(b'preserve')
        self.assert_retry_refused(occupied)
        self.assertEqual((occupied/'existing').read_bytes(), b'preserve')
        self.assertEqual(other_sentinel.read_bytes(), b'synthetic sentinel')

    def test_injected_failure_before_and_after_every_step(self):
        for phase in ('before', 'after'):
            for step in range(TOTAL_STEPS):
                with self.subTest(phase=phase, step=step):
                    parent, workspace, sentinel = self.case(phase+str(step))
                    def fail(where, current):
                        if (where, current) == (phase, step): raise InjectedFailure()
                    with self.assertRaises(InjectedFailure):
                        rehearsal(workspace, self.files, fail)
                    self.assertEqual(sentinel.read_bytes(), b'synthetic sentinel')
                    self.assertEqual({p.name for p in parent.iterdir()},
                                     {'untouched-sentinel', 'workspace'} if workspace.exists()
                                     else {'untouched-sentinel'})
                    if not workspace.exists():
                        self.assertEqual((phase, step), ('before', 0))
                        self.assertEqual(rehearsal(workspace, self.files, lambda *_: None), 'synthetic_complete')
                    else:
                        self.assert_known_partial(workspace)
                        self.assert_retry_refused(workspace)
                        if (phase, step) == ('after', TOTAL_STEPS-1):
                            # Без записи о завершении guard видит полный состав, а не историю сбоя.
                            self.assertEqual(self.verify_guard(workspace)['outcome'], 'pass')
                        else:
                            with self.assertRaises(GuardViolation): self.verify_guard(workspace)

    def test_partial_write_at_each_file_is_not_success(self):
        for offset, rel in enumerate(FILES):
            with self.subTest(file=rel):
                parent, workspace, sentinel = self.case('partial'+str(offset))
                step = 1 + len(DIRS) + offset
                def fail(where, current):
                    if (where, current) == ('mid', step): raise InjectedFailure()
                with self.assertRaises(InjectedFailure):
                    rehearsal(workspace, self.files, fail)
                self.assertEqual((workspace/rel).read_bytes(), self.files[rel][:len(self.files[rel])//2])
                self.assertEqual(sentinel.read_bytes(), b'synthetic sentinel')
                self.assert_known_partial(workspace)
                self.assert_retry_refused(workspace)
                with self.assertRaises(GuardViolation): self.verify_guard(workspace)

    def test_process_exit_after_each_step_and_mid_file_never_reports_success(self):
        # Сценарий загружается в дочерний процесс; все пути — собственные temp-каталоги теста.
        child = r'''import importlib.util,json,os,sys
from pathlib import Path
spec=importlib.util.spec_from_file_location('init_failure_rehearsal',sys.argv[1])
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
workspace=Path(sys.argv[2]); target=sys.argv[3]; step=int(sys.argv[4]); files={k:bytes.fromhex(v) for k,v in json.loads(sys.argv[5]).items()}
def hook(phase,index):
 if phase==target and index==step: os._exit(77)
m.rehearsal(workspace,files,hook)
print('unexpected success')
'''
        packed = json.dumps({k:v.hex() for k,v in self.files.items()})
        scenarios = [('after', step) for step in range(TOTAL_STEPS)]
        scenarios += [('mid', 1+len(DIRS)+i) for i in range(len(FILES))]
        for phase, step in scenarios:
            with self.subTest(phase=phase, step=step):
                parent, workspace, sentinel = self.case('abrupt'+phase+str(step))
                result = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', child, str(Path(__file__).resolve()),
                                         str(workspace), phase, str(step), packed], capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 77, result.stderr)
                self.assertEqual(result.stdout, '')
                self.assertTrue(workspace.is_dir())
                self.assertEqual(sentinel.read_bytes(), b'synthetic sentinel')
                self.assert_known_partial(workspace)
                self.assert_retry_refused(workspace)
                if phase == 'mid':
                    rel = FILES[step-1-len(DIRS)]
                    partial = (workspace/rel).read_bytes()
                    self.assertTrue(self.files[rel].startswith(partial))
                    self.assertLess(len(partial), len(self.files[rel]))
                if (phase, step) == ('after', TOTAL_STEPS-1):
                    self.assertEqual(self.verify_guard(workspace)['outcome'], 'pass')
                else:
                    with self.assertRaises(GuardViolation): self.verify_guard(workspace)


if __name__ == '__main__':
    unittest.main()
