#!/usr/bin/env python3
"""Модельные тесты; намеренно НЕ проверяют файловую систему или кандидат."""
import itertools
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from concurrent_plan_study import Cell, Plan, State, compare_and_write, matches, write_unconditionally


def original():
    return State((Cell(b'L0', 0), Cell(b'L1', 0), Cell(b'L2', 0)))


class ConcurrentPlanStudy(unittest.TestCase):
    def setUp(self):
        self.start = original()
        self.a = Plan(self.start, 'L1', b'L1+A')
        self.b = Plan(self.start, 'L1', b'L1+B')

    def test_six_split_check_write_schedules_have_four_lost_updates(self):
        schedules = [order for order in itertools.permutations(('ac', 'aw', 'bc', 'bw'))
                     if order.index('ac') < order.index('aw') and order.index('bc') < order.index('bw')]
        self.assertEqual(len(schedules), 6)
        lost = 0; stale = 0
        for order in schedules:
            state = self.start; decisions = {}; successful = []
            for step in order:
                label, action = step
                plan = self.a if label == 'a' else self.b
                if action == 'c': decisions[label] = matches(state, plan, epochs=True)
                elif decisions[label]:
                    state = write_unconditionally(state, plan.target, plan.after); successful.append(label)
            if len(successful) == 2:
                lost += 1
                self.assertIn(state.get('L1').content, (self.a.after, self.b.after))
                self.assertEqual(state.get('L1').epoch, 2)
            else:
                stale += 1; self.assertEqual(len(successful), 1)
        self.assertEqual((lost, stale), (4, 2))

    def test_ideal_atomic_comparison_allows_exactly_one_same_base_writer(self):
        for first, second in ((self.a, self.b), (self.b, self.a)):
            state, result1 = compare_and_write(self.start, first, epochs=True)
            state2, result2 = compare_and_write(state, second, epochs=True)
            self.assertEqual((result1, result2), ('applied', 'stale'))
            self.assertEqual(state2, state); self.assertEqual(state.get('L1').content, first.after)

    def test_different_target_still_invalidates_three_input_snapshot(self):
        b = Plan(self.start, 'L2', b'L2+B')
        for first, second in ((self.a, b), (b, self.a)):
            state, first_result = compare_and_write(self.start, first, epochs=True)
            unchanged, second_result = compare_and_write(state, second, epochs=True)
            self.assertEqual((first_result, second_result), ('applied', 'stale'))
            self.assertEqual(unchanged, state)

    def test_split_check_misses_non_target_change(self):
        self.assertTrue(matches(self.start, self.a, epochs=True))
        drift = write_unconditionally(self.start, 'L2', b'other')
        result = write_unconditionally(drift, 'L1', self.a.after)
        self.assertEqual(result.get('L1').content, self.a.after)
        self.assertEqual(result.get('L2').content, b'other')
        self.assertFalse(matches(drift, self.a, epochs=True))
        self.assertEqual(compare_and_write(drift, self.a, epochs=True), (drift, 'stale'))

    def test_aba_byte_only_matches_but_assumed_monotonic_epoch_detects_it(self):
        changed = write_unconditionally(self.start, 'L2', b'intermediate')
        aba = write_unconditionally(changed, 'L2', b'L2')
        self.assertTrue(matches(aba, self.a, epochs=False))
        self.assertFalse(matches(aba, self.a, epochs=True))
        _, byte_result = compare_and_write(aba, self.a, epochs=False)
        same, epoch_result = compare_and_write(aba, self.a, epochs=True)
        self.assertEqual((byte_result, epoch_result), ('applied', 'stale'))
        self.assertEqual(same, aba)

    def test_rollback_of_epoch_and_bytes_is_indistinguishable(self):
        changed = write_unconditionally(self.start, 'L2', b'intermediate')
        aba = write_unconditionally(changed, 'L2', b'L2')
        # Вне write_unconditionally: злоумышленник/сбой откатил всё состояние модели.
        rolled_back = State(tuple(self.start.cells))
        self.assertNotEqual(aba, rolled_back); self.assertEqual(rolled_back, self.start)
        self.assertTrue(matches(rolled_back, self.a, epochs=True))
        self.assertEqual(compare_and_write(rolled_back, self.a, epochs=True)[1], 'applied')

    def test_plan_and_state_validation_reject_wrong_types(self):
        with self.assertRaises(ValueError): Cell(b'x', True)
        with self.assertRaises(ValueError): State([Cell(b'x', 0)] * 3)
        with self.assertRaises(ValueError): Plan(self.start, 'L0', b'x')
        with self.assertRaises(ValueError): compare_and_write(self.start, self.a, epochs=1)
        with self.assertRaises(ValueError): write_unconditionally(self.start, 'L2', 'not bytes')


if __name__ == '__main__': unittest.main()
