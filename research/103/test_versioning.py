#!/usr/bin/env python3
"""П2: независимые ожидания для классификатора и десяти мутаций стенда."""
from pathlib import Path
import copy
import json
import tempfile
import unittest

from version_probe import add_rule, candidate_route, init_profile, read, rule

MATRIX = Path(__file__).resolve().parents[1] / 'strategy/COMPATIBILITY.json'


class CompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.matrix = json.loads(MATRIX.read_text(encoding='utf-8'))

    def test_routes_match_explicit_sources_and_schemas(self):
        shipped = {'0.1.0', '0.1.35', '0.1.36'}
        cases = (
            ('0.1.36', 1, '0.1.36', 'use_baseline', 'baseline_observed'),
            ('0.1.36', 1, '0.2.0', 'migration_required', 'not run'),
            ('0.1.35', 1, '0.2.0', 'review_upgrade_path', 'not run'),
            ('0.1.0', 1, '0.2.0', 'review_upgrade_path', 'not run'),
            ('absent', None, '0.2.0', 'clean_install', 'not run'),
            ('0.2.0', 2, '0.1.36', 'restore_snapshot_only', 'not run'),
            ('0.2.0', 2, '0.1.35', 'restore_snapshot_only', 'not run'),
        )
        for source, schema, target, decision, status in cases:
            with self.subTest(source=source, schema=schema, target=target):
                self.assertEqual(candidate_route(self.matrix, shipped, source, schema, target),
                                 {'decision': decision, 'evidence': status})

    def test_unknown_or_mismatched_inputs_never_authorize_writes(self):
        cases = (
            ('0.1.1', 1, '0.2.0'), ('0.1.37', 1, '0.2.0'), ('0.1.036', 1, '0.2.0'),
            ('0.1.36+custom', 1, '0.2.0'), ('0.1.36', 2, '0.2.0'), ('0.1.36', True, '0.2.0'),
            ('0.1.36', '1', '0.2.0'), ('0.1.36', None, '0.2.0'), ('absent', 1, '0.2.0'),
            ('0.1.36', 1, '1.0.0'), ('0.2.0', 2, '0.1.1'), ('*', 1, '0.2.0'),
            ({'unexpected': 'object'}, 1, '0.2.0'), ('0.1.36', 1, ['0.2.0']),
        )
        for source, schema, target in cases:
            with self.subTest(source=source, schema=schema, target=target):
                self.assertEqual(candidate_route(self.matrix, {'0.1.0', '0.1.35', '0.1.36'}, source,
                                                 schema, target),
                                 {'decision': 'unknown_version', 'evidence': 'policy_only'})


class ProfileFixtureTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.profile = Path(tmp.name) / 'profiles/test'
        init_profile(self.profile)

    def bytes(self):
        return {p.name: p.read_bytes() for p in self.profile.iterdir()}

    def test_mutations_persist_revision_and_keep_the_contract(self):
        old = self.bytes()
        for n in range(1, 11):
            self.assertEqual(add_rule(self.profile, n - 1, rule(n)), 'committed')
            payload = read(self.profile / 'profile.json')
            self.assertEqual(payload, {'revision': n})
            entries = read(self.profile / 'rules.json')['entries']
            self.assertEqual(entries[0], {'id': 'R-1', 'kind': 'contract', 'scope': '.'})
            self.assertEqual([entry['id'] for entry in entries], [f'R-{i}' for i in range(1, n + 2)])
            self.assertTrue(all(entry['contract'] == 'R-1' and entry['scope'] == '.' for entry in entries[1:]))
            current = self.bytes()
            self.assertNotEqual(old['rules.json'], current['rules.json'])
            self.assertNotEqual(old['profile.json'], current['profile.json'])
            old = current

    def test_refusals_are_no_write(self):
        self.assertEqual(add_rule(self.profile, 0, rule(1)), 'committed')
        exact = self.bytes()
        wrong_parent = {**rule(2), 'contract': 'R-99'}
        conflicting = {**copy.deepcopy(rule(1)), 'text': 'Другое содержание'}
        for revision, entry, expected in ((1, rule(1), 'no_change'), (0, rule(2), 'stale_revision'),
                                          (True, rule(2), 'stale_revision'), (1, wrong_parent, 'parent'),
                                          (1, conflicting, 'fixture_conflict')):
            with self.subTest(expected=expected):
                self.assertEqual(add_rule(self.profile, revision, entry), expected)
                self.assertEqual(exact, self.bytes())


if __name__ == '__main__':
    unittest.main()
