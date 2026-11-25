#!/usr/bin/env python3
"""Наблюдения одного user.* xattr на синтетических файлах; не тест ACL/политики."""
import errno
import hashlib
import json
import os
import queue
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'research/audit')]
import core_audit as audit
from kit.base.operation_card import compile_prompt
from kit.base.operation_plan import PlanSession
from kit.base.registry_policy import StoreError

NAME = 'user.domainagentkit_synthetic_probe'
INITIAL = b'synthetic-before'
CHANGED = b'synthetic-after'
ABSENT = {getattr(errno, name) for name in ('ENODATA', 'ENOATTR') if hasattr(errno, name)}
UNSUPPORTED = {getattr(errno, name) for name in ('ENOTSUP', 'EOPNOTSUPP', 'ENOSYS', 'EPERM', 'EACCES') if hasattr(errno, name)}
HAS_XATTR = os.name == 'posix' and all(hasattr(os, n) for n in ('setxattr', 'getxattr')) and bool(ABSENT)


def attribute(path):
    try:
        return os.getxattr(path, NAME)
    except OSError as error:
        if error.errno in ABSENT:
            return None
        raise


@unittest.skipUnless(HAS_XATTR, 'POSIX user xattr API недоступен; not_run')
class XattrDiagnosis(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='domain-xattr-study-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.workspace = self.root / 'workspace'; self.workspace.mkdir()
        self.layout = audit.make_workspace(self.workspace, parent_scope='.')
        self.files = {'L0': self.workspace/'kit/base/registry.json',
                      'L1': self.workspace/'profiles/pilot/registry.json',
                      'L2': self.workspace/'.domain-agent-kit/project/registry.json'}
        # Проба только созданных в этом тесте файлов. Не читаем список атрибутов.
        try:
            for path in self.files.values():
                os.setxattr(path, NAME, INITIAL)
                if attribute(path) != INITIAL:
                    self.skipTest('ФС не возвращает пробный xattr; not_run')
                with tempfile.NamedTemporaryFile(dir=path.parent) as sibling:
                    info, candidate = path.stat(), os.fstat(sibling.fileno())
                    if (stat.S_IMODE(info.st_mode), info.st_uid, info.st_gid) != (
                            stat.S_IMODE(candidate.st_mode), candidate.st_uid, candidate.st_gid):
                        self.skipTest('метаданные пробного temp не совпадают; not_run')
                    if attribute(sibling.name) is not None:
                        self.skipTest('temp наследует пробный атрибут; not_run')
        except OSError as error:
            if error.errno in UNSUPPORTED:
                self.skipTest('user xattr недоступен для ФС/процесса; not_run')
            raise
        self.session = PlanSession(self.layout, profile_id='Pilot')

    def observed(self):
        result = {}
        for area, path in self.files.items():
            info = path.stat()
            result[area] = (path.read_bytes(), stat.S_IMODE(info.st_mode), info.st_uid, info.st_gid, attribute(path))
        return result

    def request(self, target='L1'):
        where = 'в профиле Pilot' if target == 'L1' else 'в проекте'
        return (f'Создай черновик контракта X-9 {where}, постоянное, область «docs», '
                'название «Пример», основание «Проба», критерий «Запись существует»: Синтетический текст.')

    def plan(self, target='L1'):
        plan = self.session.plan(compile_prompt(self.request(target)))
        self.assertEqual((plan['plan_format'], plan['outcome']), (4, 'planned'))
        return plan

    def apply(self, plan):
        return self.session.apply(plan, confirmed_ticket=plan['ticket'])

    def assert_replaced(self, before, after, target):
        self.assertNotEqual(before[target][0], after[target][0])
        self.assertEqual(before[target][1:4], after[target][1:4])
        self.assertEqual(before[target][4], INITIAL)
        self.assertIsNone(after[target][4])
        for other in set(self.files) - {target}: self.assertEqual(before[other], after[other])

    def test_confirmed_replacements_lose_probe_xattr_on_this_filesystem(self):
        for target in ('L1', 'L2'):
            with self.subTest(target=target):
                before = self.observed(); plan = self.plan(target)
                self.assertEqual(self.observed(), before)
                with self.assertRaises(StoreError) as denied:
                    self.session.apply(plan)
                self.assertEqual(denied.exception.code, 'confirmation_required')
                self.assertEqual(self.observed(), before)
                self.assertEqual(self.apply(plan)['outcome'], 'applied')
                self.assert_replaced(before, self.observed(), target)
                with self.assertRaises(StoreError) as again: self.apply(plan)
                self.assertEqual(again.exception.code, 'ticket_unknown')

    def test_target_xattr_drift_is_not_a_plan_input(self):
        before = self.observed(); plan = self.plan()
        os.setxattr(self.files['L1'], NAME, CHANGED)
        drift = self.observed()
        self.assertEqual(before['L1'][:4], drift['L1'][:4])
        self.assertEqual(plan['inputs_sha256']['L1'], hashlib.sha256(drift['L1'][0]).hexdigest())
        self.assertEqual(self.apply(plan)['outcome'], 'applied')
        after = self.observed()
        self.assertIsNone(after['L1'][4]); self.assertEqual(after['L1'][1:4], drift['L1'][1:4])
        self.assertNotEqual(after['L1'][0], drift['L1'][0])
        for other in ('L0', 'L2'): self.assertEqual(drift[other], after[other])

    def test_non_target_xattr_drift_is_not_checked(self):
        plan = self.plan(); before = self.observed()
        os.setxattr(self.files['L2'], NAME, CHANGED)
        drift = self.observed(); self.assertEqual(before['L2'][:4], drift['L2'][:4])
        self.assertEqual(self.apply(plan)['outcome'], 'applied')
        after = self.observed(); self.assertEqual(after['L2'], drift['L2'])
        self.assert_replaced(drift, after, 'L1')

    def test_replace_failure_preserves_probe_and_consumes_ticket(self):
        before = self.observed(); plan = self.plan()
        with patch('kit.base.registry_store.os.replace', side_effect=OSError('synthetic')):
            with self.assertRaises(StoreError) as failure: self.apply(plan)
        self.assertEqual(failure.exception.code, 'write_failed'); self.assertEqual(self.observed(), before)
        self.assertFalse(list(self.files['L1'].parent.glob('.registry-*.tmp')))
        with self.assertRaises(StoreError) as again: self.apply(plan)
        self.assertEqual(again.exception.code, 'ticket_unknown')

    def run_lines(self, args, before):
        proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
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
        def send(value):
            proc.stdin.write(json.dumps(value, ensure_ascii=False)+'\n'); proc.stdin.flush()
            try: line = lines.get(timeout=15)
            except queue.Empty: raise AssertionError('нет ответа сессии') from None
            self.assertIsNotNone(line, 'сессия завершилась без ответа')
            return json.loads(line)
        plan = send({'type':'plan', 'request':self.request()})
        self.assertEqual(plan['outcome'], 'planned'); self.assertEqual(self.observed(), before)
        denied = send({'type':'apply', 'plan':plan, 'confirmed_ticket':''})
        self.assertEqual(denied['diagnostic']['code'], 'confirmation_required')
        self.assertEqual(self.observed(), before)
        result = send({'type':'apply', 'plan':plan, 'confirmed_ticket':plan['ticket']})
        self.assertEqual(result['outcome'], 'applied')
        self.assert_replaced(before, self.observed(), 'L1')
        again = send({'type':'apply', 'plan':plan, 'confirmed_ticket':plan['ticket']})
        self.assertEqual(again['diagnostic']['code'], 'ticket_unknown')

    def test_cli_observes_same_xattr_loss(self):
        args = [sys.executable, '-I', '-S', '-B', str(ROOT/'kit/session_cli.py'),
                '--workspace', str(self.workspace), '--profile-root', 'profiles/pilot', '--profile-id', 'Pilot']
        self.run_lines(args, self.observed())

    def test_isolated_snapshot_observes_same_xattr_loss(self):
        raw = (ROOT/'kit/KIT-VERSION.json').read_bytes(); manifest = json.loads(raw)
        source = self.root/'source'; source.mkdir(); trusted = self.root/'trusted'; trusted.mkdir()
        for rel in ('kit/KIT-VERSION.json', *manifest['files']):
            destination = source/rel; destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT/rel, destination)
        for name in ('snapshot_session.py', 'verify_candidate.py'):
            shutil.copyfile(ROOT/'kit'/name, trusted/name)
        l0 = json.loads(self.files['L0'].read_bytes()); l0['release_version'] = manifest['version']
        audit.write(self.files['L0'], l0)
        self.assertEqual(attribute(self.files['L0']), INITIAL)
        args = [sys.executable, '-I', '-S', '-B', str(trusted/'snapshot_session.py'),
                '--candidate-root', str(source), '--workspace', str(self.workspace),
                '--profile-root', 'profiles/pilot', '--profile-id', 'Pilot',
                '--manifest-pin', hashlib.sha256(raw).hexdigest(),
                '--system-pin', hashlib.sha256(self.files['L0'].read_bytes()).hexdigest()]
        self.run_lines(args, self.observed())


@unittest.skipUnless(HAS_XATTR, 'POSIX user xattr API недоступен; not_run')
class CapabilityReporting(unittest.TestCase):
    def test_denied_capability_is_reported_as_not_run(self):
        case = XattrDiagnosis('test_target_xattr_drift_is_not_a_plan_input')
        try:
            with patch.object(os, 'setxattr', side_effect=OSError(errno.EOPNOTSUPP, 'synthetic')):
                with self.assertRaises(unittest.SkipTest) as skipped: case.setUp()
            self.assertIn('not_run', str(skipped.exception))
        finally:
            case.doCleanups()

    def test_unexpected_io_error_is_not_misreported_as_skip(self):
        case = XattrDiagnosis('test_target_xattr_drift_is_not_a_plan_input')
        try:
            with patch.object(os, 'setxattr', side_effect=OSError(errno.EIO, 'synthetic')):
                with self.assertRaises(OSError) as failure: case.setUp()
            self.assertEqual(failure.exception.errno, errno.EIO)
        finally:
            case.doCleanups()


if __name__ == '__main__': unittest.main()
