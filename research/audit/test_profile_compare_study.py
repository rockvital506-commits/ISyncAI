#!/usr/bin/env python3
"""Синтетические пробы сравнения L1; не перенос, не слияние и не доверенная история."""
import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'research/audit')]
import core_audit as audit
import profile_compare_study as study
from kit.base import profile_journal, registry_journal, schema_v2
from kit.base.operation_card import compile_prompt
from kit.base.operation_plan import PlanSession


def raw(doc, **kwargs):
    return (json.dumps(doc, ensure_ascii=False, **kwargs)+'\n').encode('utf-8')


def base(*, root='profiles/pilot', title='initial', two=False):
    row = audit.entry('C-1', 'contract', 'profile_owner', None, '.', text='synthetic secret')
    row['title'] = title
    entries = [row]
    if two: entries.append(audit.entry('C-2', 'contract', 'profile_owner', None, '.'))
    return {'schema_version': 2, 'area':'L1', 'roots':[root], 'revision':0, 'entries':entries}


def add(doc, ident):
    previous, history = registry_journal.unpack_registry(copy.deepcopy(doc), area='L1')
    updated = copy.deepcopy(previous); updated['revision'] += 1
    entry = audit.entry(ident, 'contract', 'profile_owner', None, '.', state='draft')
    updated['entries'].append(entry)
    result = registry_journal.with_change(updated, previous, history,
                                          operation='create', before=None, after=entry)
    registry_journal.unpack_registry(result, area='L1')
    return result


class ProfileCompareStudyTests(unittest.TestCase):
    def setUp(self):
        self.base = base()
        self.first = add(self.base, 'C-9')
        self.second = add(self.first, 'C-10')
        self.fork = add(self.base, 'C-11')

    def compare(self, left, right):
        return study.compare(raw(left, sort_keys=True), raw(right, sort_keys=True))

    def test_same_bytes_and_same_document_different_encoding(self):
        canonical = raw(self.first, sort_keys=True)
        self.assertEqual(study.compare(canonical, canonical)['relation'], 'same_bytes')
        other = raw(self.first, indent=2, sort_keys=False)
        result = study.compare(canonical, other)
        self.assertEqual(result['relation'], 'same_document_different_bytes')
        self.assertNotEqual(result['left_sha256'], result['right_sha256'])
        self.assertEqual(result['profile_identity'], 'not_verified')
        self.assertEqual(result['history_authenticity'], 'not_verified')

    def test_recorded_prefix_only_not_proven_ancestor(self):
        result = self.compare(self.first, self.second)
        self.assertEqual(result['relation'], 'recorded_prefix_compatible')
        self.assertEqual(result['common_prefix_decisions'], 1)
        self.assertEqual(result['shorter_record'], 'left')
        reverse = self.compare(self.second, self.first)
        self.assertEqual(reverse['relation'], 'recorded_prefix_compatible')
        self.assertEqual(reverse['shorter_record'], 'right')
        self.assertEqual(result['history_authenticity'], 'not_verified')
        self.assertEqual(result['merge'], 'not_implemented')

    def test_same_revision_different_decisions_not_selected(self):
        result = self.compare(self.first, self.fork)
        self.assertEqual((result['left_revision'], result['right_revision']), (1, 1))
        self.assertEqual(result['relation'], 'different_recorded_decisions')
        self.assertEqual(result['common_prefix_decisions'], 0)
        self.assertIsNone(result['shorter_record'])
        self.assertNotIn('winner', result)

    def test_fork_after_common_step_is_not_prefix(self):
        other = add(self.first, 'C-11')
        result = self.compare(self.second, other)
        self.assertEqual(result['relation'], 'different_recorded_decisions')
        self.assertEqual(result['common_prefix_decisions'], 1)
        self.assertIsNone(result['shorter_record'])

    def test_delete_can_return_entries_to_base_without_erasing_history(self):
        previous, journal = registry_journal.unpack_registry(copy.deepcopy(self.first), area='L1')
        deleted = previous['entries'][-1]
        updated = copy.deepcopy(previous); updated['revision'] += 1; updated['entries'].pop()
        restored_entries = registry_journal.with_change(updated, previous, journal,
                                                        operation='delete', before=deleted, after=None)
        registry_journal.unpack_registry(restored_entries, area='L1')
        self.assertEqual(restored_entries['registry']['entries'], self.base['entries'])
        result = self.compare(self.first, restored_entries)
        self.assertEqual(result['relation'], 'recorded_prefix_compatible')
        self.assertEqual(result['common_prefix_decisions'], 1)
        self.assertEqual(result['history_authenticity'], 'not_verified')

    def test_baselines_and_roots_are_not_guessed(self):
        other_base = add(base(title='different baseline'), 'C-9')
        self.assertEqual(self.compare(self.first, other_base)['relation'], 'different_recorded_baselines')
        other_root = add(base(root='profiles/other'), 'C-9')
        result = self.compare(self.first, other_root)
        self.assertEqual(result['relation'], 'different_roots')
        self.assertFalse(result['roots_equal'])
        self.assertIsNone(result['common_prefix_decisions'])

    def test_same_history_does_not_imply_same_document(self):
        original = add(base(two=True), 'C-9')
        reordered = copy.deepcopy(original); reordered['registry']['entries'].reverse()
        registry_journal.unpack_registry(reordered, area='L1')
        result = self.compare(original, reordered)
        self.assertEqual(result['relation'], 'same_recorded_history_different_document')
        self.assertEqual(result['common_prefix_decisions'], 1)

    def test_bare_and_format_one_history_remain_incomparable(self):
        self.assertEqual(self.compare(self.base, self.first)['relation'], 'incomparable_history_formats')
        previous = base(); updated = copy.deepcopy(previous); updated['revision'] = 1
        row = audit.entry('R-1', 'rule', 'profile_owner', 'C-1', '.', state='draft')
        updated['entries'].append(row)
        old = profile_journal.with_creation(updated, {'base_revision':0, 'decisions':[]})
        new = registry_journal.with_change(updated, previous, {'base_revision':0, 'decisions':[]},
                                           operation='create', before=None, after=row)
        result = self.compare(old, new)
        self.assertEqual((result['left_format'], result['right_format']), ('profile_format_1', 'registry_format_2'))
        self.assertEqual(result['relation'], 'incomparable_history_formats')
        self.assertIsNone(result['common_prefix_decisions'])
        self.assertEqual(self.compare(old, old)['relation'], 'same_bytes')

    def test_invalid_documents_are_refused_before_comparing(self):
        broken = copy.deepcopy(self.first); broken['journal']['decisions'][0]['after_sha256'] = '0'*64
        truncated = copy.deepcopy(self.first); truncated['journal']['decisions'] = []
        candidates = (raw(broken), raw(truncated), b'{"x":1,"x":2}', b'{"x":NaN}', b'\xff',
                      b'x'*(study.MAX_INPUT+1), 'not bytes')
        for value in candidates:
            with self.subTest(kind=type(value).__name__, size=len(value)):
                with self.assertRaises(study.ComparisonError) as left:
                    study.compare(value, raw(self.first))
                self.assertEqual(str(left.exception), 'left_invalid')
                with self.assertRaises(study.ComparisonError) as right:
                    study.compare(raw(self.first), value)
                self.assertEqual(str(right.exception), 'right_invalid')

    def test_complete_forged_chain_can_pass_without_authority(self):
        # Две независимо сконструированные фикстуры имеют структурно совместимый журнал.
        fabricated1 = add(base(title='not independently authenticated'), 'C-9')
        fabricated2 = add(copy.deepcopy(fabricated1), 'C-10')
        result = self.compare(fabricated1, fabricated2)
        self.assertEqual(result['relation'], 'recorded_prefix_compatible')
        self.assertEqual(result['history_authenticity'], 'not_verified')
        self.assertEqual(result['profile_identity'], 'not_verified')
        self.assertEqual(result['semantic_conflicts'], 'not_checked')

    def test_comparison_is_memory_only_and_does_not_return_entry_text(self):
        left, right = raw(self.first), raw(self.fork)
        with patch('builtins.open', side_effect=AssertionError('filesystem access')), \
             patch.object(Path, 'open', side_effect=AssertionError('filesystem access')), \
             patch('os.open', side_effect=AssertionError('filesystem access')), \
             patch('os.stat', side_effect=AssertionError('filesystem access')):
            result = study.compare(left, right)
        self.assertNotIn('synthetic secret', json.dumps(result))
        self.assertEqual(result['outcome'], 'study_only')
        self.assertEqual(result['merge'], 'not_implemented')

    def test_real_recorded_synthetic_operations_compare_without_writing(self):
        with tempfile.TemporaryDirectory(prefix='domain-compare-study-') as td:
            root = Path(td).resolve(); paths = []
            for name, ident in (('A','C-9'), ('B','C-10')):
                ws = root/name; ws.mkdir(); layout = audit.make_workspace(ws, parent_scope='.')
                session = PlanSession(layout, profile_id='Pilot')
                phrase = (f'Создай черновик контракта {ident} в профиле Pilot, постоянное, '
                          'область «docs», название «Пример», основание «Проба», '
                          'критерий «Запись существует»: Согласуем порядок чтения.')
                plan = session.plan(compile_prompt(phrase))
                self.assertEqual(plan['outcome'], 'planned')
                self.assertEqual(session.apply(plan, confirmed_ticket=plan['ticket'])['outcome'], 'applied')
                paths.append(ws/'profiles/pilot/registry.json')
            before = audit.tree_digest(root)
            result = study.compare(paths[0].read_bytes(), paths[1].read_bytes())
            self.assertEqual(result['relation'], 'different_recorded_decisions')
            self.assertEqual((result['left_revision'], result['right_revision']), (1, 1))
            self.assertEqual(audit.tree_digest(root), before)


if __name__ == '__main__':
    unittest.main()
