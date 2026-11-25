#!/usr/bin/env python3
"""Предупреждение полного плана: только новые синтетические временные раскладки."""
import copy
import json
import queue
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'research/audit')]
import core_audit as audit
from kit.base.operation_card import compile_prompt
from kit.base.operation_plan import PlanSession
from kit.base.registry_policy import StoreError

EXPECTED = ('При замене файла реестра могут измениться права доступа, владелец, ACL и другие '
            'метаданные. Их сохранность не проверяется; на POSIX перед записью сравниваются '
            'только биты mode входных файлов.')


class NoticeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='domain-notice-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.layout = audit.make_workspace(self.root,parent_scope='.')
        self.session = PlanSession(self.layout,profile_id='Pilot')
        self.procs = []
        self.addCleanup(self.stop_processes)

    def stop_processes(self):
        for proc in self.procs:
            if proc.poll() is None: proc.kill()
            proc.communicate(timeout=15)

    def phrase(self, target, ident='X-9'):
        where = 'в профиле Pilot' if target == 'L1' else 'в проекте'
        return (f'Создай черновик контракта {ident} {where}, постоянное, '
                'область «docs», название «Пример», основание «Проба», '
                'критерий «Запись существует»: Синтетический текст.')

    def plan(self, target='L1'):
        result = self.session.plan(compile_prompt(self.phrase(target)))
        self.assertEqual((result['plan_format'],result['outcome']),(3,'planned'))
        self.assertEqual(result['replacement_notice'],EXPECTED)
        return result

    def error(self, code, fn):
        with self.assertRaises(StoreError) as failure: fn()
        self.assertEqual(failure.exception.code,code)

    def test_both_layers_show_same_notice_before_any_write(self):
        before = audit.tree_digest(self.root)
        for target in ('L1','L2'):
            with self.subTest(target=target):
                plan = self.plan(target)
                self.assertEqual(plan['card']['params']['target'],target)
                self.assertTrue(plan['dry_run'])
                self.assertEqual(audit.tree_digest(self.root),before)

    def test_notice_tampering_and_old_format_fail_without_write(self):
        plan = self.plan(); before = audit.tree_digest(self.root)
        variants = []
        removed = copy.deepcopy(plan); del removed['replacement_notice']; variants.append(removed)
        edited = copy.deepcopy(plan); edited['replacement_notice'] = 'Без изменений прав'; variants.append(edited)
        wrong_type = copy.deepcopy(plan); wrong_type['replacement_notice'] = True; variants.append(wrong_type)
        old = copy.deepcopy(plan); old['plan_format'] = 1; del old['replacement_notice']; variants.append(old)
        version_only = copy.deepcopy(plan); version_only['plan_format'] = 1; variants.append(version_only)
        old2 = copy.deepcopy(plan); old2['plan_format'] = 2; del old2['input_mode_bits']; variants.append(old2)
        for changed in variants:
            with self.subTest(plan=changed.get('replacement_notice')):
                self.error('plan_mismatch',lambda: self.session.apply(changed,confirmed_ticket=plan['ticket']))
                self.assertEqual(audit.tree_digest(self.root),before)
        # Сопоставление не является удостоверением личности/факта показа. Успех только на фикстуре.
        self.assertEqual(self.session.apply(plan,confirmed_ticket=plan['ticket'])['outcome'],'applied')
        self.error('ticket_unknown',lambda: self.session.apply(plan,confirmed_ticket=plan['ticket']))

    def test_confirmation_still_required_and_exactly_one_application(self):
        before = audit.tree_digest(self.root); plan = self.plan('L2')
        self.error('confirmation_required',lambda: self.session.apply(plan))
        self.assertEqual(audit.tree_digest(self.root),before)
        result = self.session.apply(plan,confirmed_ticket=plan['ticket'])
        self.assertEqual(result['outcome'],'applied')
        after = audit.tree_digest(self.root)
        self.assertNotEqual(before,after)
        self.error('ticket_unknown',lambda: self.session.apply(plan,confirmed_ticket=plan['ticket']))
        self.assertEqual(audit.tree_digest(self.root),after)

    def test_non_mutating_outcomes_do_not_claim_replacement(self):
        before = audit.tree_digest(self.root)
        for phrase in ('Покажи правила в профиле Pilot.', 'Создай правило в профиле Pilot.',
                       'Временное указание: Синтетическое указание.'):
            with self.subTest(phrase=phrase):
                result = self.session.plan(compile_prompt(phrase))
                self.assertEqual(result['plan_format'],3)
                self.assertIn(result['outcome'],('listed','missing_params','non_registry'))
                self.assertNotIn('replacement_notice',result)
                self.assertNotIn('ticket',result)
                self.assertEqual(audit.tree_digest(self.root),before)

    def test_no_change_has_no_ticket_or_replacement_notice(self):
        card = compile_prompt(self.phrase('L1'))
        plan = self.session.plan(card)
        self.session.apply(plan,confirmed_ticket=plan['ticket'])
        before = audit.tree_digest(self.root)
        repeated = self.session.plan(card)
        self.assertEqual((repeated['plan_format'],repeated['outcome']),(3,'no_change'))
        self.assertNotIn('replacement_notice',repeated)
        self.assertNotIn('ticket',repeated)
        self.assertEqual(audit.tree_digest(self.root),before)

    def test_revoke_and_delete_also_warn_and_delete_needs_extra_consent(self):
        created = self.plan('L1')
        self.session.apply(created,confirmed_ticket=created['ticket'])
        revoked = self.session.plan(compile_prompt('Отмени контракт X-9 в профиле Pilot.'))
        self.assertEqual((revoked['outcome'],revoked['replacement_notice']),('planned',EXPECTED))
        self.session.apply(revoked,confirmed_ticket=revoked['ticket'])
        request = compile_prompt('Удали контракт X-9 в профиле Pilot.')
        deletion = self.session.plan(request)
        self.assertEqual((deletion['outcome'],deletion['replacement_notice']),('planned',EXPECTED))
        before = audit.tree_digest(self.root)
        self.error('delete_confirmation_required',lambda: self.session.apply(deletion,confirmed_ticket=deletion['ticket']))
        self.assertEqual(audit.tree_digest(self.root),before)
        deletion = self.session.plan(request)
        self.assertEqual(deletion['replacement_notice'],EXPECTED)
        self.assertEqual(self.session.apply(deletion,confirmed_ticket=deletion['ticket'],allow_delete=True)['outcome'],
                         'applied')

    def test_plan_still_rechecks_content_drift(self):
        plan = self.plan()
        project = self.root/'.domain-agent-kit/project/registry.json'
        project.write_bytes(project.read_bytes()+b'\n')
        before = audit.tree_digest(self.root)
        self.error('stale_plan',lambda: self.session.apply(plan,confirmed_ticket=plan['ticket']))
        self.assertEqual(audit.tree_digest(self.root),before)
        self.error('ticket_unknown',lambda: self.session.apply(plan,confirmed_ticket=plan['ticket']))

    def test_json_line_cli_returns_and_checks_full_notice(self):
        proc = subprocess.Popen([sys.executable,'-I','-S','-B',str(ROOT/'kit/session_cli.py'),
            '--workspace',str(self.root),'--profile-root','profiles/pilot','--profile-id','Pilot'],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',bufsize=1)
        self.procs.append(proc)
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
        before = audit.tree_digest(self.root)
        plan = send({'type':'plan','request':self.phrase('L1')})
        self.assertEqual((plan['plan_format'],plan['replacement_notice']),(3,EXPECTED))
        forged = copy.deepcopy(plan); del forged['replacement_notice']
        response = send({'type':'apply','plan':forged,'confirmed_ticket':plan['ticket']})
        self.assertEqual(response['diagnostic']['code'],'plan_mismatch')
        self.assertEqual(audit.tree_digest(self.root),before)
        self.assertEqual(send({'type':'apply','plan':plan,'confirmed_ticket':plan['ticket']})['outcome'],'applied')


if __name__ == '__main__': unittest.main()
