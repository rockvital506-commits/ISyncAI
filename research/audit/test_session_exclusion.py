#!/usr/bin/env python3
"""Одновременные методы одного PlanSession на синтетических временных данных."""
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
from kit.base import operation_plan, registry_store as store
from kit.base.operation_plan import PlanSession
from kit.base.registry_policy import StoreError


@unittest.skipUnless(os.name == 'posix', 'POSIX synthetic mode not_run')
class SessionExclusion(ModePlanBase):
    def error(self, code, fn):
        with self.assertRaises(StoreError) as error: fn()
        self.assertEqual(error.exception.code, code)

    def threaded(self, apply):
        result = []
        def run():
            try: result.append(('ok', apply()))
            except BaseException as error: result.append(('error', error))
        thread = threading.Thread(target=run, daemon=True); thread.start()
        return thread, result

    def finish(self, release, thread, result):
        release.set(); thread.join(timeout=15); self.assertFalse(thread.is_alive())
        self.assertEqual(len(result), 1)
        if result[0][0] == 'error': raise result[0][1]
        return result[0][1]

    def test_plan_and_apply_busy_during_existing_apply(self):
        card_a, card_b = audit.card(ident='Q-9'), audit.card(ident='Q-8')
        old = self.session.plan(card_a); before = self.observed()
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        real_same = operation_plan._same_json
        def pause(got, expected):
            if type(got) is dict and got.get('ticket') == old['ticket']:
                entered.set()
                if not release.wait(10): raise RuntimeError('synthetic timeout')
            return real_same(got, expected)
        with patch.object(operation_plan, '_same_json', side_effect=pause):
            thread, result = self.threaded(lambda: self.session.apply(old, confirmed_ticket=old['ticket']))
            try:
                self.assertTrue(entered.wait(10))
                self.error('session_busy', lambda: self.session.plan(card_b))
                self.error('session_busy', lambda: self.session.apply(old, confirmed_ticket=old['ticket']))
                self.assertEqual(self.observed(), before)
            finally: release.set(); thread.join(timeout=15)
            self.assertEqual(self.finish(release, thread, result)['outcome'], 'applied')
        self.error('ticket_unknown', lambda: self.session.apply(old, confirmed_ticket=old['ticket']))
        new = self.session.plan(card_b)
        self.assertEqual(self.session.apply(new, confirmed_ticket=new['ticket'])['outcome'], 'applied')

    def test_busy_during_plan_does_not_modify_new_ticket(self):
        old = self.session.plan(audit.card(ident='Q-9')); before = self.observed()
        entered, release = threading.Event(), threading.Event(); self.addCleanup(release.set)
        real_preview = store._preview_action
        def pause(*args, **kwargs):
            entered.set()
            if not release.wait(10): raise RuntimeError('synthetic timeout')
            return real_preview(*args, **kwargs)
        with patch.object(store, '_preview_action', side_effect=pause):
            thread, result = self.threaded(lambda: self.session.plan(audit.card(ident='Q-8')))
            try:
                self.assertTrue(entered.wait(10))
                self.error('session_busy', lambda: self.session.apply(old, confirmed_ticket=old['ticket']))
                self.error('session_busy', lambda: self.session.plan(audit.card(ident='Q-7')))
                self.assertEqual(self.observed(), before)
            finally: release.set(); thread.join(timeout=15)
            new = self.finish(release, thread, result)
        self.assertEqual(new['outcome'], 'planned')
        self.error('ticket_unknown', lambda: self.session.apply(old, confirmed_ticket=old['ticket']))
        self.assertEqual(self.session.apply(new, confirmed_ticket=new['ticket'])['outcome'], 'applied')

    def test_reentrant_plan_refused_without_losing_applying_ticket(self):
        plan = self.session.plan(audit.card(ident='Q-9')); real_same = operation_plan._same_json; calls = []
        def nested(got, expected):
            if type(got) is dict and got.get('ticket') == plan['ticket'] and not calls:
                calls.append(True)
                self.error('session_busy', lambda: self.session.plan(audit.card(ident='Q-8')))
            return real_same(got, expected)
        with patch.object(operation_plan, '_same_json', side_effect=nested):
            self.assertEqual(self.session.apply(plan, confirmed_ticket=plan['ticket'])['outcome'], 'applied')
        self.assertEqual(calls, [True]); self.error('ticket_unknown', lambda: self.session.apply(plan, confirmed_ticket=plan['ticket']))

    def test_exceptions_release_session_guard_and_existing_rules_hold(self):
        old = self.session.plan(audit.card(ident='Q-9'))
        self.error('card_mismatch', lambda: self.session.plan({}))
        self.error('ticket_unknown', lambda: self.session.apply(old, confirmed_ticket=old['ticket']))
        plan = self.session.plan(audit.card(ident='Q-8'))
        self.error('confirmation_required', lambda: self.session.apply(plan))
        modified = dict(plan); modified['replacement_notice'] = 'изменено'
        self.error('plan_mismatch', lambda: self.session.apply(modified, confirmed_ticket=plan['ticket']))
        self.assertEqual(self.session.apply(plan, confirmed_ticket=plan['ticket'])['outcome'], 'applied')

    def test_unexpected_exception_releases_guard(self):
        with patch.object(operation_plan, '_checked_card', side_effect=RuntimeError('synthetic')):
            with self.assertRaises(RuntimeError): self.session.plan(audit.card(ident='Q-9'))
        plan = self.session.plan(audit.card(ident='Q-9'))
        self.assertEqual(self.session.apply(plan, confirmed_ticket=plan['ticket'])['outcome'], 'applied')

    def test_store_busy_consumes_confirmed_ticket_but_session_lock_releases(self):
        plan = self.session.plan(audit.card(ident='Q-9')); before = self.observed()
        self.assertTrue(store._WRITE_LOCK.acquire(blocking=False))
        try: self.error('write_busy', lambda: self.session.apply(plan, confirmed_ticket=plan['ticket']))
        finally: store._WRITE_LOCK.release()
        self.assertEqual(self.observed(), before)
        self.error('ticket_unknown', lambda: self.session.apply(plan, confirmed_ticket=plan['ticket']))
        new = self.session.plan(audit.card(ident='Q-9'))
        self.assertEqual(self.session.apply(new, confirmed_ticket=new['ticket'])['outcome'], 'applied')

    def test_other_session_can_plan_while_first_session_is_busy(self):
        other = PlanSession(self.layout, profile_id='Pilot')
        entered, release = threading.Event(), threading.Event(); self.addCleanup(release.set)
        real_checked = operation_plan._checked_card
        def pause(card):
            if card['request'] == audit.card(ident='Q-9')['request']:
                entered.set()
                if not release.wait(10): raise RuntimeError('synthetic timeout')
            return real_checked(card)
        with patch.object(operation_plan, '_checked_card', side_effect=pause):
            thread, result = self.threaded(lambda: self.session.plan(audit.card(ident='Q-9')))
            try:
                self.assertTrue(entered.wait(10))
                second = other.plan(audit.card(ident='Q-8'))
                self.assertEqual(second['outcome'], 'planned')
            finally: release.set(); thread.join(timeout=15)
            first = self.finish(release, thread, result)
        self.assertEqual(first['outcome'], 'planned')
        self.assertEqual(other.apply(second, confirmed_ticket=second['ticket'])['outcome'], 'applied')
        self.error('stale_revision', lambda: self.session.apply(first, confirmed_ticket=first['ticket']))


if __name__ == '__main__': unittest.main()
