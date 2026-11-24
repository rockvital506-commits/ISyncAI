#!/usr/bin/env python3
"""Проверка честных статусов кандидата, не проба указанных сред."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class EnvironmentStatuses(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT/'kit/ENVIRONMENTS.json').read_text(encoding='utf-8'))

    def test_closed_shape(self):
        self.assertEqual(set(self.data), {'format','scope','environments'})
        self.assertEqual(self.data['format'], 1)
        self.assertEqual(self.data['scope'], 'mvp-candidate')
        self.assertEqual(set(self.data['environments']), {'arena','kilo','copilot'})

    def test_each_status_is_honest(self):
        for name, value in self.data['environments'].items():
            with self.subTest(environment=name):
                self.assertEqual(set(value), {'status','mvp_reading','mvp_application','basis','limit'})
                self.assertEqual(value['mvp_reading'], 'not_run')
                self.assertEqual(value['mvp_application'], 'not_run')
                self.assertTrue((ROOT/value['basis']).is_file())
                self.assertTrue(value['limit'])
        self.assertEqual(self.data['environments']['copilot']['status'], 'stub')
        self.assertEqual(self.data['environments']['kilo']['status'], 'candidate')
        self.assertEqual(self.data['environments']['arena']['status'], 'candidate')


if __name__ == '__main__': unittest.main()
