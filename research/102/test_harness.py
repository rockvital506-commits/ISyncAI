#!/usr/bin/env python3
"""Фикстуры П2: отказы и соответствие печати финальным файлам."""
import contextlib
import copy
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'research/strategy/harness'))
import run_iteration as harness


class HarnessTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.patch(harness, 'REPO', self.root)
        self.room = self.root / 'research/102'
        self.source = 'research/102/ITERATION.json'
        self.spec = json.loads((ROOT / self.source).read_text(encoding='utf-8'))
        generated = {f'research/102/{name}' for name in harness.SEALED_OUTPUTS}
        inputs = (set(self.spec['seal_members']) - generated) | {self.spec['artifact_zip']}
        for name in inputs:
            src, dest = ROOT / name, self.root / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
        self.fresh_base = json.loads((ROOT / 'research/strategy/BASELINE.json').read_text(encoding='utf-8'))
        self.fresh_room = json.loads((ROOT / 'research/101/CLEANROOM.json').read_text(encoding='utf-8'))
        self.suite = {'rc': 0, 'version': '0.1.36', 'totals': {'pass': 105, 'fail': 0, 'not run': 3, 'inconclusive': 0},
                      'not_run': [], 'failures': []}

    def patch(self, owner, name, value):
        mock = patch.object(owner, name, value)
        self.addCleanup(mock.stop)
        mock.start()

    def enter(self, *args):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            rc = harness.main(['--spec', self.source, *args])
        return rc, json.loads(stream.getvalue())

    def save_spec(self):
        (self.root / self.source).write_text(json.dumps(self.spec, ensure_ascii=False), encoding='utf-8')

    def run_with_fixtures(self):
        self.save_spec()
        with (patch.object(harness.probes, 'inventory', return_value=self.fresh_base),
              patch.object(harness.probes, 'clean_room', return_value=self.fresh_room),
              patch.object(harness.probes, 'release_suite', return_value=self.suite)):
            return self.enter()

    def artifacts(self):
        return {p.name: p.read_bytes() for p in self.room.iterdir() if p.is_file()}

    def test_invalid_specs_are_refused_without_writes(self):
        cases = {
            'too_few_checks': lambda s: s.update(checks=s['checks'][:1]),
            'not_an_object': lambda s: s['checks'].__setitem__(0, None),
            'unknown_check': lambda s: s['checks'][0].update(type='unknown'),
            'duplicate_names': lambda s: s['checks'][1].update(name=s['checks'][0]['name']),
            'no_comparison': lambda s: s.update(checks=[c for c in s['checks'] if c['type'] != 'json_equal']),
            'missing_criterion': lambda s: s['checks'][0].pop('criterion'),
            'tautology': lambda s: s['checks'][0].update(reference='research/102/BASELINE.json'),
            'cyclic_seal': lambda s: s['seal_members'].append('research/102/SEAL.json'),
            'missing_final_report': lambda s: s['seal_members'].remove('research/102/REPORT.md'),
            'unsafe_id': lambda s: s.update(id='../101'),
        }
        original = copy.deepcopy(self.spec)
        for case, mutate in cases.items():
            with self.subTest(case=case):
                self.spec = copy.deepcopy(original)
                mutate(self.spec)
                self.save_spec()
                before = self.artifacts()
                rc, result = self.enter('--dry-run')
                self.assertEqual((rc, result['error']), (2, 'spec_invalid'))
                self.assertEqual(before, self.artifacts())

    def test_dry_run_only_validates(self):
        before = self.artifacts()
        rc, result = self.enter('--dry-run')
        self.assertEqual(rc, 0)
        self.assertEqual(result['plan'], ['П3', 'П4', 'П5', 'П6', 'П7', 'П8'])
        self.assertEqual(before, self.artifacts())

    def test_wrong_artifact_digest_stops_before_import(self):
        (self.root / self.spec['artifact_zip']).write_bytes(b'wrong archive')
        with patch.object(harness.probes, 'inventory') as inventory:
            rc, result = self.enter()
            self.assertEqual((rc, result['error']), (1, 'artifact_digest_mismatch'))
            inventory.assert_not_called()

    def test_rejected_expectation_is_not_a_pass(self):
        check = next(c for c in self.spec['checks'] if c['name'] == 'arena_absent')
        check['value'] = ['kilo']
        rc, result = self.run_with_fixtures()
        self.assertEqual((rc, result['outcome']), (1, 'rejected'))
        evidence = json.loads((self.room / 'ACCEPTANCE.json').read_text(encoding='utf-8'))
        self.assertEqual(evidence['counts']['fail'], 1)
        self.assertEqual(evidence['counts']['not run'], len(self.spec['not_run']))
        self.assertEqual(evidence['counts']['pass'], len(self.spec['checks']) - 1)

    def test_missing_step_does_not_match_expected_null(self):
        checked = {'type': 'steps', 'expect': [{'step': 'not-there', 'error': None}]}
        self.assertFalse(harness.evaluate(checked, {'cleanroom': self.fresh_room})[0])

    def test_final_report_sealed_and_repeat_is_read_only(self):
        rc, result = self.run_with_fixtures()
        self.assertEqual((rc, result['outcome']), (0, 'accepted'))
        archive = self.room / 'AgentContractKit-Iteration-102.zip'
        with zipfile.ZipFile(archive) as z:
            self.assertEqual(set(z.namelist()), set(self.spec['seal_members']))
            for name in z.namelist():
                self.assertEqual(z.read(name), (self.root / name).read_bytes(), name)
        original = self.artifacts()
        self.assertEqual(self.run_with_fixtures()[0], 0)
        self.assertEqual(original, self.artifacts())
        self.assertEqual(self.enter('--verify-seal')[0], 0)
        self.assertEqual(original, self.artifacts())

    def test_repeat_detects_changed_inputs_or_archive(self):
        self.assertEqual(self.run_with_fixtures()[0], 0)
        for name in ('REPORT.md', 'AgentContractKit-Iteration-102.zip', 'SEAL.json'):
            with self.subTest(name=name):
                path = self.room / name
                original = path.read_bytes()
                path.write_bytes(b'[]' if name == 'SEAL.json' else original + b'changed')
                modified = self.artifacts()
                rc, result = self.enter('--verify-seal')
                self.assertEqual((rc, result['outcome']), (1, 'mismatch'))
                self.assertEqual(modified, self.artifacts())
                path.write_bytes(original)


if __name__ == '__main__':
    unittest.main()
