#!/usr/bin/env python3
"""Негативная проверка шлюза приёмки; не подменяет целевой прогон."""
import copy
import io
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from accept import case_problems


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.expected_error = {'ok': False, 'stage': 'links', 'code': 'parent_missing', 'path': '/parent'}
        self.cases = [{'id': 'V', 'expected': {'ok': True}}, {'id': 'N', 'expected': self.expected_error}]
        self.result = {'rows': [
            {'id': 'V', 'status': 'pass', 'observed': {'ok': True}, 'unchanged': True},
            {'id': 'N', 'status': 'pass', 'observed': copy.deepcopy(self.expected_error), 'unchanged': True},
        ]}

    def test_exact_evidence_accepted(self):
        self.assertEqual(case_problems(self.cases, self.result), [])

    def test_missing_duplicate_and_foreign(self):
        positive, negative = self.result['rows']
        self.result['rows'] = [positive, positive, dict(negative, id='other')]
        self.assertEqual(case_problems(self.cases, self.result), ['missing:N', 'unexpected:other', 'duplicate:V'])

    def test_not_run_cannot_close_required_case(self):
        self.result['rows'][0]['status'] = 'not run'
        self.assertEqual(case_problems(self.cases, self.result), ['bad_result:V'])

    def test_wrong_rejection_and_no_type_coercion(self):
        self.result['rows'][0]['observed']['ok'] = 1
        self.result['rows'][1]['observed']['code'] = 'other'
        self.assertEqual(case_problems(self.cases, self.result), ['bad_result:V', 'bad_result:N'])

    def test_mutation_and_bad_row(self):
        self.result['rows'][0]['unchanged'] = False
        self.assertEqual(case_problems(self.cases, self.result), ['bad_result:V'])
        self.result['rows'][0] = None
        self.assertEqual(case_problems(self.cases, self.result), ['malformed_row'])


if __name__ == '__main__':
    log = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(AcceptanceTests)
    result = unittest.TextTestRunner(stream=log).run(suite)
    print(json.dumps({'run': result.testsRun, 'fail': len(result.failures), 'errors': len(result.errors),
                      'skipped': len(result.skipped)}, sort_keys=True))
    if not result.wasSuccessful():
        print(log.getvalue(), file=sys.stderr)
    raise SystemExit(0 if result.wasSuccessful() else 1)
