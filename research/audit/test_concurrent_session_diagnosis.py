#!/usr/bin/env python3
"""Два PlanSession в одном модуле, вложенный apply, не защита между процессами."""
import hashlib
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'research/audit')]
from test_plan_mode_freshness import ModePlanBase
from kit.base import registry_store as store, registry_journal
from kit.base.operation_card import compile_prompt
from kit.base.operation_plan import PlanSession
from kit.base.registry_policy import StoreError


def digest(data): return hashlib.sha256(data).hexdigest()


@unittest.skipUnless(os.name == 'posix', 'POSIX synthetic metadata not_run')
class ConcurrentSessions(ModePlanBase):
    def plans(self, target_a, target_b):
        b = PlanSession(self.layout, profile_id='Pilot')
        def plan(session, target, ident):
            where = 'в профиле Pilot' if target == 'L1' else 'в проекте'
            text = (f'Создай черновик контракта {ident} {where}, постоянное, '
                    'область «docs», название «Пример», основание «Проба», '
                    'критерий «Запись существует»: Синтетический текст.')
            value = session.plan(compile_prompt(text))
            self.assertEqual((value['plan_format'], value['outcome']), (4, 'planned'))
            return value
        before = self.observed()
        a_plan, b_plan = plan(self.session, target_a, 'A-9'), plan(b, target_b, 'B-9')
        self.assertEqual(before, self.observed())
        self.assertEqual(a_plan['inputs_sha256'], b_plan['inputs_sha256'])
        for session, p in ((self.session, a_plan), (b, b_plan)):
            with self.assertRaises(StoreError) as error: session.apply(p)
            self.assertEqual(error.exception.code, 'confirmation_required')
            self.assertEqual(before, self.observed())
        return before, b, a_plan, b_plan

    def history(self, target):
        return registry_journal.unpack_registry(json.loads(self.files[target].read_bytes()), area=target)

    def consumed(self, session, plan):
        with self.assertRaises(StoreError) as error:
            session.apply(plan, confirmed_ticket=plan['ticket'])
        self.assertEqual(error.exception.code, 'ticket_unknown')

    def serial(self, target_a, target_b):
        before, b, pa, pb = self.plans(target_a, target_b)
        self.assertEqual(self.session.apply(pa, confirmed_ticket=pa['ticket'])['outcome'], 'applied')
        after = self.observed()
        self.assertEqual(digest(after[target_a][0]), pa['diff']['after_sha256'])
        with self.assertRaises(StoreError) as error: b.apply(pb, confirmed_ticket=pb['ticket'])
        self.assertEqual(error.exception.code, 'stale_revision' if target_a == target_b else 'stale_plan')
        self.assertEqual(self.observed(), after)
        self.assertEqual(after['L0'], before['L0'])
        self.consumed(self.session, pa); self.consumed(b, pb)

    def interleaved(self, target_a, target_b):
        before, b, pa, pb = self.plans(target_a, target_b)
        real_replace = store._replace
        events = []
        def intersect(path, raw, rel, *, expected_metadata):
            # A уже держит общую блокировку и проверила входы.
            self.assertEqual(digest(raw), pa['diff']['after_sha256'])
            self.assertEqual(self.observed(), before)
            with self.assertRaises(StoreError) as error:
                b.apply(pb, confirmed_ticket=pb['ticket'])
            self.assertEqual(error.exception.code, 'write_busy')
            self.assertEqual(self.observed(), before)
            events.append('B-busy')
            return real_replace(path, raw, rel, expected_metadata=expected_metadata)
        with patch.object(store, '_replace', side_effect=intersect):
            result_a = self.session.apply(pa, confirmed_ticket=pa['ticket'])
        self.assertEqual(events, ['B-busy'])
        self.assertEqual(result_a['outcome'], 'applied')
        after = self.observed(); self.assertEqual(after['L0'], before['L0'])
        self.assertEqual(digest(after[target_a][0]), pa['diff']['after_sha256'])
        registry, journal = self.history(target_a)
        self.assertEqual([d['entry_id'] for d in journal['decisions']], ['A-9'])
        self.assertIn('A-9', [e['id'] for e in registry['entries']])
        self.assertNotIn('B-9', [e['id'] for e in registry['entries']])
        other = 'L2' if target_a == 'L1' else 'L1'
        self.assertEqual(after[other], before[other])
        for target in ('L1', 'L2'):
            self.assertEqual(list(self.files[target].parent.glob('.registry-*.tmp')), [])
        self.consumed(self.session, pa); self.consumed(b, pb)

    def test_serial_l1_same_target(self): self.serial('L1', 'L1')
    def test_serial_l2_same_target(self): self.serial('L2', 'L2')
    def test_serial_l1_then_l2(self): self.serial('L1', 'L2')
    def test_serial_l2_then_l1(self): self.serial('L2', 'L1')
    def test_interleaved_l1_same_target(self): self.interleaved('L1', 'L1')
    def test_interleaved_l2_same_target(self): self.interleaved('L2', 'L2')
    def test_interleaved_l1_then_l2(self): self.interleaved('L1', 'L2')
    def test_interleaved_l2_then_l1(self): self.interleaved('L2', 'L1')


if __name__ == '__main__': unittest.main()
