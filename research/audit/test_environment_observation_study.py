#!/usr/bin/env python3
"""Арифметические пробы не являются наблюдениями живых сред."""
from pathlib import Path
import json
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'research/audit')]
import environment_observation_study as study


class ObservationTests(unittest.TestCase):
    def test_empty_cards_distinguish_states(self):
        for name in study.ENVIRONMENTS:
            card=study.card(name)
            self.assertEqual(card['status'],dict.fromkeys(study.STATES,'not_run'))
            self.assertEqual(card['run_count'],0);self.assertIsNone(card['recorded_action'])
            self.assertEqual(card['budget'],'not_measured')
        with self.assertRaises(study.ObservationError):study.card('unknown')
    def test_checked_in_cards_match_unobserved_templates(self):
        saved=json.loads((ROOT/'research/kilo/ENVIRONMENT-OBSERVATION-CARDS.json').read_text(encoding='utf-8'))
        self.assertEqual(saved,{'format':1,'cards':[study.card(name) for name in study.ENVIRONMENTS]})

    def test_actual_window_arithmetic_exact_boundaries(self):
        for n,expected in ((250,'at_or_below_25_percent'),(251,'above_25_at_or_below_30_percent'),
                           (300,'above_25_at_or_below_30_percent'),(301,'above_30_percent')):
            out=study.context_budget(window_tokens=1000,injected_tokens=n,measurement_source='reported by test')
            self.assertEqual(out['budget_class'],expected);self.assertEqual(out['measurement_accuracy'],'not_verified')
        out=study.context_budget(window_tokens=7,injected_tokens=2,measurement_source='test')
        self.assertEqual(out['budget_class'],'above_25_at_or_below_30_percent')
        self.assertEqual((out['target_25_percent_tokens_floor'],out['maximum_30_percent_tokens_floor']),(1,2))
    def test_invalid_measurements_fail_closed(self):
        for window,tokens,source in ((True,0,'x'),(100,True,'x'),(0,0,'x'),(100,-1,'x'),
                                     (100,101,'x'),(100,1,''),(100,1,None),(2**63,1,'x')):
            with self.subTest(window=window,tokens=tokens,source=source):
                with self.assertRaises(study.ObservationError):
                    study.context_budget(window_tokens=window,injected_tokens=tokens,measurement_source=source)

if __name__=='__main__':unittest.main()
