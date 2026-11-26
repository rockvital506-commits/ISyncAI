#!/usr/bin/env python3
"""Только правила интерпретации результатов CI; не средовая приёмка."""
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'research/audit')]
import ci_gate_study as gate


class GateTests(unittest.TestCase):
    def test_positive_suite(self):
        self.assertEqual(gate._test_status('','----------------------------------------------------------------------\nRan 6 tests in 0.001s\n\nOK\n'),6)
        self.assertEqual(gate._test_status('Ran 1 test in 0.1s\nOK',''),1)
    def test_annotation_escapes_workflow_commands(self):
        self.assertEqual(gate._annotation('bad%\r\n::warning::fake'),
                         '::error::bad%25%0D%0A::warning::fake')

    def test_skips_zero_or_missing_fail_closed(self):
        for text in ('Ran 0 tests in 0.1s\nOK','Ran 2 tests in 0.1s\nOK (skipped=1)',
                     'OK','Ran 1 test in 0.1s\nRan 1 test in 0.2s\nOK'):
            with self.subTest(text=text):
                with self.assertRaises(gate.GateError):gate._test_status('',text)

if __name__=='__main__':unittest.main()
