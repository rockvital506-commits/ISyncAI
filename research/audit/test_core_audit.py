#!/usr/bin/env python3
"""Проверки A-002. Только синтетические случаи и временные каталоги."""
import copy
import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import core_audit as audit


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.matrix_text = (audit.ROOT / 'kit/base/OPERATION-MATRIX.md').read_text(encoding='utf-8')
        self.matrix = audit.store.operation_matrix()

    def test_matrix_full_and_codes(self):
        self.assertEqual(audit.compare_matrix(self.matrix_text, self.matrix), [])
        self.assertEqual(audit.check_matrix()['cases'], 27)
        changed = copy.deepcopy(self.matrix)
        changed['create']['L0']['code'] = 'other'
        self.assertTrue(audit.compare_matrix(self.matrix_text, changed))

    def test_document_matrix_changed_or_truncated(self):
        changed = self.matrix_text.replace('| `list` · пользовательский просмотр | `planned`',
                                           '| `list` · пользовательский просмотр | `available`')
        self.assertNotEqual(changed, self.matrix_text)
        self.assertTrue(audit.compare_matrix(changed, self.matrix))
        with self.assertRaises(ValueError):
            audit.parse_matrix(self.matrix_text.replace('| Операция | L0 | L1 | L2 |', '| broken |'))

    def test_known_exception_exact(self):
        self.assertTrue(audit.known_exception('N17-list', KeyError('diff')))
        self.assertFalse(audit.known_exception('N17-list', KeyError('other')))
        self.assertFalse(audit.known_exception('N17-list', ValueError('diff')))
        self.assertFalse(audit.known_exception('other', KeyError('diff')))

    def test_known_id_wrong_observation_or_digest_fails(self):
        spec = importlib.util.spec_from_file_location('audit105test', audit.ROOT / 'research/105/test_layout.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        all_cases = json.loads((audit.ROOT / 'research/105/CASES.json').read_text(encoding='utf-8'))['cases']
        cases = [c for c in audit.current_cases(105, all_cases) if c['id'] == 'N12-no-parent']
        case = cases[0]
        digest = {k: 'a' * 64 for k in ('L0', 'L1', 'L2', 'L0_manifest')}
        row = {'id': case['id'], 'observed': copy.deepcopy(case['expected']),
               'digest': {'before': copy.deepcopy(digest), 'after': copy.deepcopy(digest)}}
        evidence = {'rows': [row]}
        self.assertEqual(audit.compare_evidence(module, cases, evidence), [])
        row['observed']['error']['code'] = 'wrong'
        self.assertTrue(audit.compare_evidence(module, cases, evidence))
        row['observed'] = copy.deepcopy(case['expected'])
        row['digest']['after']['L0'] = 'b' * 64
        self.assertTrue(audit.compare_evidence(module, cases, evidence))
        self.assertTrue(audit.compare_evidence(module, cases, {'rows': []}))

    def test_108_known_case_still_checks_io_and_complete_card(self):
        spec = importlib.util.spec_from_file_location('audit108test', audit.ROOT / 'research/108/test_cards.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cases = json.loads((audit.ROOT / 'research/108/CASES.json').read_text(encoding='utf-8'))['cases']
        expected = audit.current_cases(108, cases)
        evidence = audit.subprocess_evidence(audit.ROOT / 'research/108/test_cards.py')
        self.assertEqual(audit.compare_evidence(module, expected, evidence), [])
        modified = copy.deepcopy(evidence)
        row = next(row for row in modified['rows'] if row['id'] == 'NL02')
        row['observed']['empty']['card']['params']['text'] = 'другая ошибка'
        self.assertTrue(audit.compare_evidence(module, expected, modified))
        modified = copy.deepcopy(evidence)
        row = next(row for row in modified['rows'] if row['id'] == 'N19')
        row['observed']['seeded']['io_events'] = ['write']
        self.assertTrue(audit.compare_evidence(module, expected, modified))

    def test_unexpected_or_missing_case(self):
        spec = importlib.util.spec_from_file_location('audit105extra', audit.ROOT / 'research/105/test_layout.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cases = [{'id': 'fixture', 'expected': {}}]
        self.assertTrue(audit.compare_evidence(module, cases, {'rows': []}))
        self.assertTrue(audit.compare_evidence(module, cases, {'rows': [{'id': 'extra'}]}))

    def test_subprocess_failure_and_invalid_json(self):
        for result in (subprocess.CompletedProcess([], 2, '', 'crash'),
                       subprocess.CompletedProcess([], 1, 'not json', ''),
                       subprocess.CompletedProcess([], 1, '{"rows": []}', 'unexpected error')):
            with self.subTest(result=result), patch('subprocess.run', return_value=result):
                with self.assertRaises(ValueError):
                    audit.subprocess_evidence(Path('synthetic.py'))
        with patch('subprocess.run', return_value=subprocess.CompletedProcess([], 1, '{"rows": []}', '')):
            self.assertEqual(audit.subprocess_evidence(Path('synthetic.py')), {'rows': []})

    def test_historical_input_is_not_modified(self):
        cases = json.loads((audit.ROOT / 'research/108/CASES.json').read_text(encoding='utf-8'))['cases']
        before = copy.deepcopy(cases)
        adjusted = audit.current_cases(108, cases)
        self.assertEqual(cases, before)
        self.assertNotEqual(adjusted, cases)

    def test_known_expectation_not_arbitrary_failure(self):
        cases = json.loads((audit.ROOT / 'research/109/CASES.json').read_text(encoding='utf-8'))['cases']
        adjusted = {c['id']: c['expected'] for c in audit.current_cases(109, cases)}
        self.assertEqual(adjusted['N16-project']['outcome'], 'planned')
        self.assertEqual(adjusted['N28-kind']['revision'], {'from': 4, 'to': 5})
        self.assertTrue(adjusted['N16-project']['l0_l2_unchanged'])

    def test_legacy_paths_are_translated_only_in_memory(self):
        source = {'paths': ['.agent-contract/project/registry.json', 'unrelated'], 'n': 1}
        before = copy.deepcopy(source)
        adapted = audit.translated_paths(source)
        self.assertEqual(source, before)
        self.assertEqual(adapted, {'paths': ['.domain-agent-kit/project/registry.json', 'unrelated'], 'n': 1})
        path = audit.ROOT/'research/105/test_layout.py'
        original = path.read_bytes()
        module = audit.load_path_adapted_test(105, path)
        self.assertEqual(module.L2, '.domain-agent-kit')
        self.assertEqual(path.read_bytes(), original)

    def test_109_preview_oracle_adapts_only_expected_and_fails_on_wrong_notice(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory(prefix='oracle-mode-') as tmp:
            root = Path(tmp)
            for name in ('l0', 'l1', 'l2'): (root/name).write_bytes(b'test')
            files = {'L0':'l0','L1':'l1','L2':'l2'}
            module = SimpleNamespace(FILES=files,
                expected_preview=lambda work,outcome: {'plan_format':4, 'outcome':outcome})
            audit.adapt_109_preview(module)
            planned = module.expected_preview(root,'planned')
            self.assertEqual(planned['replacement_notice'], audit.PLAN4_NOTICE)
            modes = ({'status':'captured_posix_mode_bits','inputs':
                      {area:format(stat.S_IMODE((root/name).lstat().st_mode),'04o') for area,name in files.items()}}
                     if os.name == 'posix' else {'status':'not_checked','inputs':None})
            self.assertEqual(planned['input_mode_bits'],modes)
            self.assertNotIn('replacement_notice', module.expected_preview(root,'no_change'))
            self.assertNotIn('input_mode_bits', module.expected_preview(root,'no_change'))
            with self.assertRaises(ValueError): module.expected_preview(root,'other')
            original = (audit.ROOT/'research/109/test_plan.py').read_bytes()
            historical = audit.load_path_adapted_test(109, audit.ROOT/'research/109/test_plan.py')
            self.assertEqual((audit.ROOT/'research/109/test_plan.py').read_bytes(),original)
            expected = planned
            actual = {**expected, 'ticket':'a'*64}
            self.assertTrue(historical.exact_preview(actual, expected))
            actual['replacement_notice'] = 'wrong'
            self.assertFalse(historical.exact_preview(actual, expected))
            actual['replacement_notice'] = audit.PLAN4_NOTICE
            actual['input_mode_bits'] = {'status':'not_checked','inputs':None} if os.name == 'posix' else {}
            self.assertFalse(historical.exact_preview(actual, expected))

    def test_audit_integration(self):
        self.assertEqual(audit.check_known_drift()['mismatches'], [])


if __name__ == '__main__':
    unittest.main()
