#!/usr/bin/env python3
"""Диагностика текущих метаданных только на новых синтетических POSIX-деревьях."""
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
sys.path[:0] = [str(ROOT), str(ROOT/'research/audit')]
import core_audit as audit
from kit.base.operation_card import compile_prompt
from kit.base.operation_plan import PlanSession
from kit.base.registry_policy import StoreError


@unittest.skipUnless(os.name == 'posix', 'POSIX mode не поддерживается; диагностика not_run')
class MetadataDiagnosisTests(unittest.TestCase):
    def setUp(self):
        old_umask = os.umask(0o022)
        self.addCleanup(os.umask, old_umask)
        temp = tempfile.TemporaryDirectory(prefix='domain-registry-metadata-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.workspace = self.root/'workspace'; self.workspace.mkdir()
        self.layout = audit.make_workspace(self.workspace, parent_scope='.')
        self.l0 = self.workspace/'kit/base/registry.json'
        self.l1 = self.workspace/'profiles/pilot/registry.json'
        self.l2 = self.workspace/'.domain-agent-kit/project/registry.json'
        for path in (self.l0, self.l1, self.l2):
            path.chmod(0o640)
            if stat.S_IMODE(path.stat().st_mode) != 0o640:
                self.skipTest('ФС не отражает POSIX chmod; диагностика not_run')
        self.session = PlanSession(self.layout, profile_id='Pilot')

    def snapshot(self):
        return {str(p.relative_to(self.workspace)): (p.read_bytes(), stat.S_IMODE(p.stat().st_mode))
                for p in (self.l0, self.l1, self.l2)}

    def plan(self, target):
        where = 'в профиле Pilot' if target == 'L1' else 'в проекте'
        request = (f'Создай черновик контракта X-9 {where}, постоянное, '
                   'область «docs», название «Пример», основание «Проба», '
                   'критерий «Запись существует»: Синтетический текст.')
        result = self.session.plan(compile_prompt(request))
        self.assertEqual(result['outcome'], 'planned')
        self.assertEqual(set(result['diff']), {'file','revision','before_sha256','after_sha256','unified'})
        return result

    def apply(self, plan):
        return self.session.apply(plan, confirmed_ticket=plan['ticket'])

    def assert_only_target_changed(self, before, target):
        after = self.snapshot()
        for path in (self.l0, self.l1, self.l2):
            rel = str(path.relative_to(self.workspace))
            if path == target:
                self.assertNotEqual(after[rel][0], before[rel][0])
                self.assertEqual(after[rel][1], 0o600)
            else:
                self.assertEqual(after[rel], before[rel])

    def test_l1_confirmed_replacement_changes_mode(self):
        before = self.snapshot(); old_inode = (self.l1.stat().st_dev,self.l1.stat().st_ino)
        plan = self.plan('L1')
        self.assertEqual(self.snapshot(), before)
        with self.assertRaises(StoreError) as denied:
            self.session.apply(plan, confirmed_ticket='')
        self.assertEqual(denied.exception.code, 'confirmation_required')
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.apply(plan)['outcome'], 'applied')
        self.assert_only_target_changed(before,self.l1)
        self.assertNotEqual(old_inode,(self.l1.stat().st_dev,self.l1.stat().st_ino))

    def test_l2_confirmed_replacement_changes_mode(self):
        self.l2.chmod(0o644)
        before = self.snapshot(); plan = self.plan('L2')
        self.assertEqual(self.snapshot(),before)
        self.assertEqual(self.apply(plan)['outcome'], 'applied')
        self.assert_only_target_changed(before,self.l2)

    def test_mode_drift_after_plan_is_rejected(self):
        self.l1.chmod(0o600)
        plan = self.plan('L1')
        self.assertEqual(plan['inputs_sha256']['L1'],hashlib.sha256(self.l1.read_bytes()).hexdigest())
        self.l1.chmod(0o640)  # Только синтетический файл; содержимое не меняется.
        before = self.snapshot()
        self.assertEqual(plan['inputs_sha256']['L1'],hashlib.sha256(self.l1.read_bytes()).hexdigest())
        self.assertEqual(before[str(self.l1.relative_to(self.workspace))][1],0o640)
        with self.assertRaises(StoreError) as error: self.apply(plan)
        self.assertEqual(error.exception.code,'stale_metadata')
        self.assertEqual(self.snapshot(),before)
        with self.assertRaises(StoreError) as retry: self.apply(plan)
        self.assertEqual(retry.exception.code,'ticket_unknown')

    def test_non_target_mode_drift_is_not_in_hashes_but_is_rejected(self):
        self.l2.chmod(0o600)
        plan = self.plan('L1')
        content_hash = hashlib.sha256(self.l2.read_bytes()).hexdigest()
        self.assertEqual(plan['inputs_sha256']['L2'],content_hash)
        self.l2.chmod(0o640)
        before = self.snapshot()
        self.assertEqual(hashlib.sha256(self.l2.read_bytes()).hexdigest(),content_hash)
        with self.assertRaises(StoreError) as error: self.apply(plan)
        self.assertEqual(error.exception.code,'stale_metadata')
        self.assertEqual(self.snapshot(),before)
        self.assertEqual(stat.S_IMODE(self.l2.stat().st_mode),0o640)

    def test_original_private_mode_stays_private(self):
        self.l1.chmod(0o600)
        before = self.snapshot(); plan = self.plan('L1')
        self.assertEqual(self.apply(plan)['outcome'], 'applied')
        self.assert_only_target_changed(before,self.l1)

    def test_replace_failure_preserves_observed_bytes_and_mode(self):
        before = self.snapshot(); plan = self.plan('L1')
        with patch('kit.base.registry_store.os.replace',side_effect=OSError('synthetic')):
            with self.assertRaises(StoreError) as error:
                self.apply(plan)
        self.assertEqual(error.exception.code,'write_failed')
        self.assertEqual(self.snapshot(),before)
        self.assertEqual(list(self.l1.parent.glob('.registry-*.tmp')),[])
        with self.assertRaises(StoreError) as retry:
            self.apply(plan)
        self.assertEqual(retry.exception.code,'ticket_unknown')
        self.assertEqual(self.snapshot(),before)

    def test_isolated_snapshot_session_rejects_mode_drift(self):
        manifest_raw = (ROOT/'kit/KIT-VERSION.json').read_bytes()
        manifest = json.loads(manifest_raw)
        source = self.root/'source'; source.mkdir()
        trusted = self.root/'trusted'; trusted.mkdir()
        for rel in ('kit/KIT-VERSION.json', *manifest['files']):
            path = source/rel; path.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/rel,path)
        for name in ('snapshot_session.py','verify_candidate.py'):
            shutil.copyfile(ROOT/'kit'/name,trusted/name)
        l0 = json.loads(self.l0.read_bytes()); l0['release_version'] = manifest['version']
        audit.write(self.l0,l0)
        self.l1.chmod(0o600)
        args = [sys.executable,'-I','-S','-B',str(trusted/'snapshot_session.py'),
                '--candidate-root',str(source),'--workspace',str(self.workspace),
                '--profile-root','profiles/pilot','--profile-id','Pilot',
                '--manifest-pin',hashlib.sha256(manifest_raw).hexdigest(),
                '--system-pin',hashlib.sha256(self.l0.read_bytes()).hexdigest()]
        proc = subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                text=True,encoding='utf-8',bufsize=1)
        def cleanup():
            if proc.poll() is None: proc.kill()
            proc.communicate(timeout=15)
        self.addCleanup(cleanup)
        lines = queue.Queue()
        def reader():
            for line in proc.stdout: lines.put(line)
            lines.put(None)
        threading.Thread(target=reader,daemon=True).start()
        def send(data):
            proc.stdin.write(json.dumps(data,ensure_ascii=False)+'\n'); proc.stdin.flush()
            try: line = lines.get(timeout=15)
            except queue.Empty: raise AssertionError('нет ответа сессии') from None
            self.assertIsNotNone(line, 'сессия завершилась без ответа')
            return json.loads(line)
        request = audit.card(ident='Q-9')['request']
        before_plan = self.snapshot()
        plan = send({'type':'plan','request':request})
        self.assertEqual(plan['outcome'],'planned')
        self.assertEqual(plan['plan_format'],3)
        self.assertEqual(plan['replacement_notice'],
            'При замене файла реестра могут измениться права доступа, владелец, ACL и другие '
            'метаданные. Их сохранность не проверяется; на POSIX перед записью сравниваются '
            'только биты mode входных файлов.')
        self.assertEqual(self.snapshot(),before_plan)
        altered = dict(plan); del altered['replacement_notice']
        denied = send({'type':'apply','plan':altered,'confirmed_ticket':plan['ticket']})
        self.assertEqual(denied['diagnostic']['code'],'plan_mismatch')
        self.assertEqual(self.snapshot(),before_plan)
        self.l1.chmod(0o640)
        before_apply = self.snapshot()
        result = send({'type':'apply','plan':plan,'confirmed_ticket':plan['ticket']})
        self.assertEqual(result['diagnostic']['code'],'stale_metadata')
        self.assertEqual(self.snapshot(),before_apply)
        self.assertEqual(send({'type':'apply','plan':plan,'confirmed_ticket':plan['ticket']})['diagnostic']['code'],
                         'ticket_unknown')


if __name__ == '__main__':
    unittest.main()
