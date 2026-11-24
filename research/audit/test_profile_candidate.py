#!/usr/bin/env python3
"""Только проверка предложенного профиля в памяти, не запись в пользовательский профиль."""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from kit.base.schema_v2 import SchemaError, validate_json, validate_registry


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.doc = validate_json((ROOT / 'kit/examples/profile-candidate.json').read_bytes(), expected_area='L1')

    def test_exact_kinds_parents_and_drafts(self):
        self.assertEqual(self.doc['revision'], 0)
        entries = {r['id']: r for r in self.doc['entries']}
        self.assertEqual(set(entries), {'C-MVP', 'P-PHASED', 'R-ROADMAP'})
        self.assertEqual(entries['C-MVP']['kind'], 'contract')
        self.assertEqual(entries['P-PHASED']['kind'], 'protocol')
        self.assertEqual(entries['R-ROADMAP']['kind'], 'rule')
        self.assertTrue(all(r['state'] == 'draft' for r in entries.values()))
        self.assertTrue(all(entries[x]['parent'] == 'C-MVP' for x in ('P-PHASED', 'R-ROADMAP')))

    def test_wrong_parent_rejected(self):
        doc = copy.deepcopy(self.doc)
        doc['entries'][1]['parent'] = 'MISSING'
        with self.assertRaises(SchemaError):
            validate_registry(doc, expected_area='L1')

    def test_wrong_area_and_scope_rejected(self):
        with self.assertRaises(SchemaError):
            validate_registry(self.doc, expected_area='L2')
        doc = copy.deepcopy(self.doc)
        doc['entries'][0]['scope'] = 'docs'
        doc['entries'][1]['scope'] = 'docs2'
        with self.assertRaises(SchemaError):
            validate_registry(doc, expected_area='L1')

    def test_invalid_state_rejected(self):
        doc = copy.deepcopy(self.doc)
        doc['entries'][1]['state'] = 'unknown'
        with self.assertRaises(SchemaError):
            validate_registry(doc, expected_area='L1')

    def test_duplicate_id_rejected(self):
        doc = copy.deepcopy(self.doc)
        doc['entries'].append(copy.deepcopy(doc['entries'][1]))
        with self.assertRaises(SchemaError):
            validate_registry(doc, expected_area='L1')


if __name__ == '__main__':
    unittest.main()
