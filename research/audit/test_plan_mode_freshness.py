#!/usr/bin/env python3
"""Проверки mode только на синтетических временных деревьях, не политика ACL."""
import copy
import json
import os
import queue
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
from kit.base import registry_store as store
from kit.base.operation_card import compile_prompt
from kit.base.operation_plan import PlanSession
from kit.base.registry_policy import StoreError


class ModePlanBase(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='domain-mode-plan-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.layout = audit.make_workspace(self.root,parent_scope='.')
        self.files = {'L0':self.root/'kit/base/registry.json',
                      'L1':self.root/'profiles/pilot/registry.json',
                      'L2':self.root/'.domain-agent-kit/project/registry.json'}
        self.session = PlanSession(self.layout,profile_id='Pilot')

    def make_plan(self,target='L1'):
        where = 'в профиле Pilot' if target == 'L1' else 'в проекте'
        text = (f'Создай черновик контракта X-9 {where}, постоянное, '
                'область «docs», название «Пример», основание «Проба», '
                'критерий «Запись существует»: Синтетический текст.')
        plan = self.session.plan(compile_prompt(text))
        self.assertEqual((plan['plan_format'],plan['outcome']),(4,'planned'))
        return plan

    def reject(self,code,plan):
        with self.assertRaises(StoreError) as error:
            self.session.apply(plan,confirmed_ticket=plan['ticket'])
        self.assertEqual(error.exception.code,code)

    def observed(self):
        return {area:(path.read_bytes(),stat.S_IMODE(path.stat().st_mode)) for area,path in self.files.items()}


@unittest.skipUnless(os.name == 'posix','POSIX mode недоступен; not_run')
class PosixModePlanTests(ModePlanBase):
    def setUp(self):
        super().setUp()
        for path in self.files.values():
            path.chmod(0o640)
            if stat.S_IMODE(path.stat().st_mode) != 0o640:
                self.skipTest('ФС не отражает chmod; not_run')

    def test_full_plan_contains_each_observed_mode_without_writing(self):
        before = self.observed(); plan = self.make_plan()
        self.assertEqual(plan['input_mode_bits'],{'status':'captured_posix_mode_bits',
                                                 'inputs':{'L0':'0640','L1':'0640','L2':'0640'}})
        self.assertEqual(self.observed(),before)

    def test_each_input_mode_drift_rejects_both_mutation_targets(self):
        for target in ('L1','L2'):
            for area in ('L0','L1','L2'):
                with self.subTest(target=target,area=area):
                    plan = self.make_plan(target)
                    self.files[area].chmod(0o600)
                    before = self.observed()
                    self.reject('stale_metadata',plan)
                    self.assertEqual(self.observed(),before)
                    self.assertFalse(list(self.files[target].parent.glob('.registry-*.tmp')))
                    self.files[area].chmod(0o640)
                    self.reject('ticket_unknown',plan)

    def test_mode_fields_are_bound_to_exact_plan(self):
        plan = self.make_plan(); before = self.observed()
        variants = []
        dropped = copy.deepcopy(plan); del dropped['input_mode_bits']; variants.append(dropped)
        edited = copy.deepcopy(plan); edited['input_mode_bits']['inputs']['L1']='0600'; variants.append(edited)
        status = copy.deepcopy(plan); status['input_mode_bits']['status']='not_checked'; variants.append(status)
        wrong_type = copy.deepcopy(plan); wrong_type['input_mode_bits']['inputs']['L1']=640; variants.append(wrong_type)
        old = copy.deepcopy(plan); old['plan_format']=2; del old['input_mode_bits']; variants.append(old)
        for changed in variants:
            with self.subTest(changed=changed.get('input_mode_bits')):
                self.reject('plan_mismatch',changed)
                self.assertEqual(self.observed(),before)
        self.reject('replacement_metadata_mismatch',plan)
        self.assertEqual(self.observed(),before)

    def test_unchanged_mode_that_cannot_be_retained_is_refused(self):
        plan = self.make_plan(); initial = self.observed()
        self.reject('replacement_metadata_mismatch',plan)
        self.assertEqual(self.observed(),initial)
        self.assertFalse(list(self.files['L1'].parent.glob('.registry-*.tmp')))
        self.reject('ticket_unknown',plan)

    def test_restored_mode_is_not_detected_as_history(self):
        self.files['L1'].chmod(0o600)
        plan = self.make_plan()
        self.files['L1'].chmod(0o640)
        self.files['L1'].chmod(0o600)
        self.assertEqual(self.session.apply(plan,confirmed_ticket=plan['ticket'])['outcome'],'applied')

    def test_change_after_last_check_still_races(self):
        self.files['L1'].chmod(0o600)
        plan = self.make_plan(); real_replace = store._replace; events = []
        def after_check(path, raw, rel, *, expected_metadata):
            self.files['L1'].chmod(0o640)
            events.append(stat.S_IMODE(self.files['L1'].stat().st_mode))
            return real_replace(path,raw,rel,expected_metadata=expected_metadata)
        with patch.object(store,'_replace',side_effect=after_check):
            result = self.session.apply(plan,confirmed_ticket=plan['ticket'])
        self.assertEqual(events,[0o640])
        self.assertEqual(result['outcome'],'applied')  # Не защита от конкурентной гонки.

    def test_special_mode_bits_are_compared_when_supported_by_fs(self):
        plan = self.make_plan()
        self.files['L1'].chmod(0o2640)
        if stat.S_IMODE(self.files['L1'].stat().st_mode) != 0o2640:
            self.skipTest('ФС не сохраняет синтетический setgid бит; not_run')
        before = self.observed(); self.reject('stale_metadata',plan)
        self.assertEqual(self.observed(),before)
        new = self.make_plan()
        self.assertEqual(new['input_mode_bits']['inputs']['L1'],'2640')

    def test_cli_rejects_mode_drift_without_write(self):
        proc = subprocess.Popen([sys.executable,'-I','-S','-B',str(ROOT/'kit/session_cli.py'),
            '--workspace',str(self.root),'--profile-root','profiles/pilot','--profile-id','Pilot'],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',bufsize=1)
        def cleanup():
            if proc.poll() is None: proc.kill()
            proc.communicate(timeout=15)
        self.addCleanup(cleanup)
        lines = queue.Queue()
        def reader():
            for line in proc.stdout: lines.put(line)
            lines.put(None)
        threading.Thread(target=reader,daemon=True).start()
        def send(obj):
            proc.stdin.write(json.dumps(obj,ensure_ascii=False)+'\n'); proc.stdin.flush()
            try: line = lines.get(timeout=15)
            except queue.Empty: raise AssertionError('нет ответа CLI') from None
            self.assertIsNotNone(line,'CLI завершился без ответа')
            return json.loads(line)
        plan = send({'type':'plan','request':audit.card(ident='Q-9')['request']})
        self.assertEqual(plan['input_mode_bits']['inputs']['L1'],'0640')
        self.files['L1'].chmod(0o600)
        before = self.observed()
        command = {'type':'apply','plan':plan,'confirmed_ticket':plan['ticket']}
        self.assertEqual(send(command)['diagnostic']['code'],'stale_metadata')
        self.assertEqual(self.observed(),before)
        self.assertEqual(send(command)['diagnostic']['code'],'ticket_unknown')
        self.files['L1'].chmod(0o640)
        plan = send({'type':'plan','request':audit.card(ident='Q-9')['request']})
        before = self.observed()
        command = {'type':'apply','plan':plan,'confirmed_ticket':plan['ticket']}
        self.assertEqual(send(command)['diagnostic']['code'],'replacement_metadata_mismatch')
        self.assertEqual(self.observed(),before)
        self.assertEqual(send(command)['diagnostic']['code'],'ticket_unknown')

    def test_native_plan_does_not_capture_mode_but_replacement_checks_current_mode(self):
        entry = audit.entry('Q-9','rule','profile_owner','C-1','docs',state='draft')
        self.files['L1'].chmod(0o600)
        plan = store.plan_create(self.layout,entry)
        self.files['L1'].chmod(0o640)
        before = self.observed()
        with self.assertRaises(StoreError) as error:
            store.apply_create(self.layout,plan,confirmed_ticket=plan['ticket'])
        self.assertEqual(error.exception.code,'replacement_metadata_mismatch')
        self.assertEqual(self.observed(),before)
        # В нативном плане нет mode: повтор после исправления режима может быть успешен.
        self.files['L1'].chmod(0o600)
        store.apply_create(self.layout,plan,confirmed_ticket=plan['ticket'])
        self.assertNotEqual(self.files['L1'].read_bytes(),before['L1'][0])
        self.assertEqual(stat.S_IMODE(self.files['L1'].stat().st_mode),0o600)


class SimulatedUnsupportedTests(ModePlanBase):
    def test_unsupported_explicitly_not_checked_not_an_emulated_windows_test(self):
        with patch.object(store,'_mode_check_supported',return_value=False):
            plan = self.make_plan()
            self.assertEqual(plan['input_mode_bits'],{'status':'not_checked','inputs':None})
            self.assertEqual(self.session.apply(plan,confirmed_ticket=plan['ticket'])['outcome'],'applied')

    def test_support_status_change_invalidates_plan_without_write(self):
        with patch.object(store,'_mode_check_supported',return_value=False):
            plan = self.make_plan()
        before = self.observed()
        with patch.object(store,'_mode_check_supported',return_value=True):
            self.reject('stale_metadata',plan)
        self.assertEqual(self.observed(),before)
        self.reject('ticket_unknown',plan)


if __name__ == '__main__': unittest.main()
