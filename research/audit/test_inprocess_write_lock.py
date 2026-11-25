#!/usr/bin/env python3
"""Границы mutex одного экземпляра модуля; только синтетические файлы."""
import os
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'research/audit')]
import core_audit as audit
from test_plan_mode_freshness import ModePlanBase
from kit.base import registry_store as store
from kit.base.operation_plan import PlanSession
from kit.base.registry_policy import StoreError


@unittest.skipUnless(os.name == 'posix', 'synthetic POSIX mode not_run')
class InProcessWriteLock(ModePlanBase):
    def native(self):
        entry = audit.entry('Q-9', 'rule', 'profile_owner', 'C-1', 'docs', state='draft')
        return store.plan_create(self.layout, entry)

    def hold_apply(self, apply):
        ready, resume = threading.Event(), threading.Event(); result = []
        real_replace = store._replace
        def hold(path, raw, rel, **kwargs):
            ready.set()
            if not resume.wait(10): raise RuntimeError('test_resume_timeout')
            return real_replace(path, raw, rel, **kwargs)
        def execute():
            try: result.append(('ok', apply()))
            except BaseException as error: result.append(('error', error))
        patcher = patch.object(store, '_replace', side_effect=hold); patcher.start()
        thread = threading.Thread(target=execute, daemon=True); thread.start()
        def cleanup():
            resume.set(); thread.join(timeout=15); patcher.stop()
        self.addCleanup(cleanup)
        self.assertTrue(ready.wait(10), 'thread did not reach _replace')
        return resume, thread, result

    def finish(self, resume, thread, result):
        resume.set(); thread.join(timeout=15); self.assertFalse(thread.is_alive())
        self.assertEqual(len(result), 1)
        if result[0][0] == 'error': raise result[0][1]
        return result[0][1]

    def error(self, code, call):
        with self.assertRaises(StoreError) as raised: call()
        self.assertEqual(raised.exception.code, code)

    def test_threaded_same_target_busy_consumes_ticket_and_replan_succeeds(self):
        a = self.make_plan('L1'); b = PlanSession(self.layout, profile_id='Pilot')
        # Другая карточка, иначе повтор стал бы no_change.
        from kit.base.operation_card import compile_prompt
        request = ('Создай черновик контракта B-9 в профиле Pilot, постоянное, '
                   'область «docs», название «Пример», основание «Проба», '
                   'критерий «Запись существует»: Синтетический текст.')
        card = compile_prompt(request); pb = b.plan(card); before = self.observed()
        resume, thread, result = self.hold_apply(lambda: self.session.apply(a, confirmed_ticket=a['ticket']))
        self.error('confirmation_required', lambda: b.apply(pb))
        self.error('write_busy', lambda: b.apply(pb, confirmed_ticket=pb['ticket']))
        self.assertEqual(self.observed(), before)
        self.error('ticket_unknown', lambda: b.apply(pb, confirmed_ticket=pb['ticket']))
        self.assertEqual(self.finish(resume, thread, result)['outcome'], 'applied')
        new = b.plan(card); self.assertEqual(new['outcome'], 'planned')
        self.assertEqual(b.apply(new, confirmed_ticket=new['ticket'])['outcome'], 'applied')
        import json
        doc = json.loads(self.files['L1'].read_bytes())
        self.assertEqual([d['entry_id'] for d in doc['journal']['decisions']], ['X-9', 'B-9'])

    def test_native_busy_while_session_holds_lock(self):
        native = self.native(); session = self.make_plan('L2'); before = self.observed()
        resume, thread, result = self.hold_apply(lambda: self.session.apply(session, confirmed_ticket=session['ticket']))
        self.error('write_busy', lambda: store.apply_create(self.layout, native, confirmed_ticket=native['ticket']))
        self.assertEqual(self.observed(), before)
        self.assertEqual(self.finish(resume, thread, result)['outcome'], 'applied')
        # Нативный план не имеет сессионного одноразового билета и не сверяет L2 без preview.
        store.apply_create(self.layout, native, confirmed_ticket=native['ticket'])

    def test_session_busy_while_native_holds_lock(self):
        native = self.native(); plan = self.make_plan('L2'); before = self.observed()
        resume, thread, result = self.hold_apply(lambda: store.apply_create(self.layout, native, confirmed_ticket=native['ticket']))
        self.error('write_busy', lambda: self.session.apply(plan, confirmed_ticket=plan['ticket']))
        self.assertEqual(self.observed(), before)
        self.error('ticket_unknown', lambda: self.session.apply(plan, confirmed_ticket=plan['ticket']))
        self.finish(resume, thread, result)
        self.assertNotEqual(self.observed()['L1'], before['L1'])
        self.assertEqual(self.observed()['L2'], before['L2'])

    def test_unrelated_workspace_is_also_busy(self):
        other = self.root/'other-workspace'; other.mkdir(); layout = audit.make_workspace(other, parent_scope='.')
        b = PlanSession(layout, profile_id='Pilot')
        from kit.base.operation_card import compile_prompt
        card = compile_prompt('Создай черновик контракта B-9 в профиле Pilot, постоянное, '
                              'область «docs», название «Пример», основание «Проба», '
                              'критерий «Запись существует»: Синтетический текст.')
        pb = b.plan(card); plan = self.make_plan(); before = audit.tree_digest(other)
        resume, thread, result = self.hold_apply(lambda: self.session.apply(plan, confirmed_ticket=plan['ticket']))
        self.error('write_busy', lambda: b.apply(pb, confirmed_ticket=pb['ticket']))
        self.assertEqual(audit.tree_digest(other), before)
        self.finish(resume, thread, result)
        new = b.plan(card); self.assertEqual(b.apply(new, confirmed_ticket=new['ticket'])['outcome'], 'applied')

    def test_lock_released_after_write_failure_and_unexpected_exception(self):
        before = self.observed(); plan = self.make_plan()
        with patch.object(store.os, 'replace', side_effect=OSError('synthetic')):
            self.error('write_failed', lambda: self.session.apply(plan, confirmed_ticket=plan['ticket']))
        self.assertEqual(self.observed(), before)
        plan = self.make_plan()
        with patch.object(store, '_replace', side_effect=RuntimeError('synthetic')):
            with self.assertRaises(RuntimeError): self.session.apply(plan, confirmed_ticket=plan['ticket'])
        self.assertEqual(self.observed(), before)
        new = self.make_plan(); self.assertEqual(self.session.apply(new, confirmed_ticket=new['ticket'])['outcome'], 'applied')

    def test_lock_released_after_native_validation_error(self):
        self.error('plan_mismatch', lambda: store.apply_create(self.layout, None, confirmed_ticket='x'))
        plan = self.make_plan()
        self.assertEqual(self.session.apply(plan, confirmed_ticket=plan['ticket'])['outcome'], 'applied')


if __name__ == '__main__': unittest.main()
