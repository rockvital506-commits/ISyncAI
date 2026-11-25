#!/usr/bin/env python3
"""Guard на синтетических снимках; не тест hook, GitHub Action или реального проекта."""
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'research/audit')]
import core_audit as a
from kit.guard import GuardViolation, guard


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='kit-guard-synthetic-')
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.snapshot = root/'candidate'; self.snapshot.mkdir()
        shutil.copytree(ROOT/'kit', self.snapshot/'kit', ignore=shutil.ignore_patterns('__pycache__'))
        self.workspace = root/'workspace'; self.workspace.mkdir()
        self.layout = a.make_workspace(self.workspace, parent_scope='.')
        self.manifest = self.snapshot/'kit/KIT-VERSION.json'
        self.l0 = self.workspace/'kit/base/registry.json'
        system = json.loads(self.l0.read_bytes())
        system['release_version'] = json.loads(self.manifest.read_bytes())['version']
        a.write(self.l0, system)  # Только синтетическая раскладка; не поставка системного L0.
        self.profile = self.workspace/'profiles/pilot/registry.json'
        self.project = self.workspace/'.domain-agent-kit/project/registry.json'
        self.manifest_pin = sha(self.manifest)
        self.system_pin = sha(self.l0)

    def check(self, **kw):
        return guard(self.snapshot, self.layout, manifest_pin=kw.get('manifest_pin', self.manifest_pin),
                     system_pin=kw.get('system_pin', self.system_pin))

    def violation(self, reason, **kw):
        before = a.tree_digest(self.workspace), a.tree_digest(self.snapshot)
        with self.assertRaises(GuardViolation) as error: self.check(**kw)
        self.assertEqual(error.exception.reason, reason)
        self.assertEqual(before, (a.tree_digest(self.workspace), a.tree_digest(self.snapshot)))

    def add_pair(self, *, second_state='active', second_value='b'):
        profile = json.loads(self.profile.read_text(encoding='utf-8'))
        p = a.entry('R-1', 'rule', 'profile_owner', 'C-1', '.', text='профиль не для вывода')
        p.update(key='test', value='a'); profile['entries'].append(p); a.write(self.profile, profile)
        project = json.loads(self.project.read_text(encoding='utf-8'))
        r = a.entry('R-2', 'rule', 'project_owner', 'P-1', '.', state=second_state, text='проект не для вывода')
        r.update(key='test', value=second_value); project['entries'].append(r); a.write(self.project, project)

    def test_clean_guard_no_write(self):
        before = a.tree_digest(self.workspace), a.tree_digest(self.snapshot)
        report = self.check()
        self.assertEqual(report['outcome'], 'pass')
        self.assertEqual(report['inputs_sha256']['L0'], self.system_pin)
        self.assertEqual(report['manifest_sha256'], self.manifest_pin)
        self.assertEqual(report['conflicts_checked'], 'structured_key_value')
        self.assertEqual(report['text_conflicts'], 'not_checked')
        self.assertEqual(report['unstructured_active_entries'], 0)
        self.assertEqual(before, (a.tree_digest(self.workspace), a.tree_digest(self.snapshot)))

    def test_pins_are_mandatory_and_checked_first(self):
        for name, value in [('manifest_pin',None), ('system_pin',None), ('manifest_pin','A'*64),
                            ('system_pin','bad'), ('system_pin',42)]:
            with self.subTest(name=name, value=value), patch('kit.guard.verify') as verifier:
                self.violation('pins_required', **{name:value})
                verifier.assert_not_called()
        self.violation('candidate_unverified', manifest_pin='0'*64)
        self.violation('system_digest_mismatch', system_pin='0'*64)

    def test_modified_l0_candidate_file_rejected(self):
        path = self.snapshot/'kit/base/SCHEMA-V2.md'; path.write_bytes(path.read_bytes()+b'changed')
        self.violation('candidate_unverified')

    def test_rewriting_manifest_does_not_defeat_pin(self):
        path = self.snapshot/'kit/base/SCHEMA-V2.md'; path.write_bytes(path.read_bytes()+b'changed')
        doc = json.loads(self.manifest.read_text(encoding='utf-8'))
        doc['files']['kit/base/SCHEMA-V2.md'] = sha(path)
        self.manifest.write_text(json.dumps(doc, sort_keys=True), encoding='utf-8')
        self.violation('candidate_unverified')

    def test_system_registry_changed_with_valid_schema_rejected(self):
        doc = json.loads(self.l0.read_text(encoding='utf-8'))
        doc['entries'][0]['text'] = 'другой системный текст'; a.write(self.l0, doc)
        self.violation('system_digest_mismatch')

    def test_system_version_is_exact_and_pin_checked_first(self):
        original = json.loads(self.l0.read_bytes())
        expected = json.loads(self.manifest.read_bytes())['version']
        for version in ('0.2.0-mvp.20', '0.2.0', expected+'+build.1', '0.2.0-audit'):
            with self.subTest(version=version):
                doc = dict(original, release_version=version); a.write(self.l0, doc)
                self.violation('system_digest_mismatch')  # Прежний pin отказывает первым.
                self.system_pin = sha(self.l0)  # Только локальный синтетический pin.
                self.violation('system_version_mismatch')
                result = self.cli()
                self.assertEqual(result.returncode, 1)
                self.assertEqual(json.loads(result.stdout)['reason'], 'system_version_mismatch')
        a.write(self.l0, original); self.system_pin = sha(self.l0)
        self.assertEqual(self.check()['outcome'], 'pass')
        doc = dict(original, release_version='not-semver'); a.write(self.l0, doc)
        self.system_pin = sha(self.l0)
        self.violation('workspace_unverified')

    def test_matching_version_does_not_certify_nonempty_l0(self):
        doc = json.loads(self.l0.read_bytes()); doc['entries'] = []; a.write(self.l0, doc)
        self.system_pin = sha(self.l0)
        self.assertEqual(self.check()['outcome'], 'pass')  # Только схема, pin и версия.

    def test_version_compares_decoded_string_not_json_spelling(self):
        doc = json.loads(self.l0.read_bytes()); version = doc['release_version']
        self.assertTrue(version.startswith('0'))
        raw = json.dumps(doc, ensure_ascii=False).replace('"release_version": "'+version+'"',
              '"release_version": "\\u0030'+version[1:]+'"', 1).encode('utf-8')
        self.assertIn(b'\\u0030', raw)
        self.l0.write_bytes(raw); self.system_pin = sha(self.l0)
        self.assertEqual(self.check()['outcome'], 'pass')

    def test_corrupt_registry_and_missing_file_rejected(self):
        self.profile.write_bytes(b'not a registry')
        self.violation('workspace_unverified')

    def test_conflict_stops_without_choosing_winner(self):
        self.add_pair()
        self.violation('structural_conflict')
        p = self.cli()
        self.assertEqual(p.returncode, 1)
        self.assertEqual(json.loads(p.stdout)['reason'], 'structural_conflict')
        self.assertNotIn('не для вывода', p.stdout + p.stderr)

    def test_system_vs_profile_conflict_rejected(self):
        system = json.loads(self.l0.read_text(encoding='utf-8'))
        rule = a.entry('S-R', 'constraint', 'system_release', 'S-1', '.', text='ограничение')
        rule.update(key='policy', value='a'); system['entries'].append(rule); a.write(self.l0, system)
        self.system_pin = sha(self.l0)  # Тестовый доверенный L0, не рабочая печать.
        profile = json.loads(self.profile.read_text(encoding='utf-8'))
        row = a.entry('R-1', 'rule', 'profile_owner', 'C-1', '.', text='конфликт')
        row.update(key='policy', value='b'); profile['entries'].append(row); a.write(self.profile, profile)
        self.violation('structural_conflict')

    def test_same_value_or_draft_not_conflict(self):
        self.add_pair(second_value='a')
        self.assertEqual(self.check()['outcome'], 'pass')
        doc = json.loads(self.project.read_text(encoding='utf-8'))
        doc['entries'][1]['value'] = 'b'; doc['entries'][1]['state'] = 'draft'; a.write(self.project, doc)
        self.assertEqual(self.check()['outcome'], 'pass')

    def test_unstructured_texts_reported_not_checked(self):
        for path, area, parent in ((self.profile,'profile_owner','C-1'),(self.project,'project_owner','P-1')):
            doc = json.loads(path.read_text(encoding='utf-8'))
            doc['entries'].append(a.entry('R-X', 'rule', area, parent, '.', text='обычный текст'))
            a.write(path, doc)
        result = self.check()
        self.assertEqual(result['outcome'], 'pass')
        self.assertEqual(result['unstructured_active_entries'], 2)
        self.assertEqual(result['text_conflicts'], 'not_checked')

    def test_symlinked_profile_rejected(self):
        target = self.workspace/'profiles/pilot/fake-registry.json'
        target.write_bytes(self.profile.read_bytes())
        self.profile.unlink()
        try: self.profile.symlink_to(target)
        except OSError as exc: self.skipTest(f'нет символических ссылок: {exc}')
        with self.assertRaises(GuardViolation) as exc: self.check()
        self.assertEqual(exc.exception.reason, 'workspace_unverified')

    def test_symlinked_candidate_rejected(self):
        path = self.snapshot/'kit/base/SCHEMA-V2.md'; path.unlink()
        try: path.symlink_to(ROOT/'kit/base/SCHEMA-V2.md')
        except OSError as exc: self.skipTest(f'нет символических ссылок: {exc}')
        with self.assertRaises(GuardViolation) as exc: self.check()
        self.assertEqual(exc.exception.reason, 'candidate_unverified')

    def cli(self, *extra, with_pins=True):
        args = [sys.executable,'-I','-S','-B',str(ROOT/'kit/guard.py'),
                '--candidate-root',str(self.snapshot),'--workspace',str(self.workspace),
                '--profile-root','profiles/pilot']
        if with_pins: args += ['--manifest-pin',self.manifest_pin,'--system-pin',self.system_pin]
        return subprocess.run(args+list(extra),cwd=self.snapshot,capture_output=True,text=True,encoding='utf-8',timeout=30)

    def test_cli_pass_and_missing_pins_violation(self):
        before = a.tree_digest(self.workspace), a.tree_digest(self.snapshot)
        passed = self.cli(); self.assertEqual(passed.returncode, 0, passed.stderr)
        self.assertEqual(json.loads(passed.stdout)['outcome'], 'pass')
        missing = self.cli(with_pins=False); self.assertEqual(missing.returncode, 1)
        self.assertEqual(json.loads(missing.stdout)['reason'], 'pins_required')
        self.assertEqual(before, (a.tree_digest(self.workspace), a.tree_digest(self.snapshot)))

    def test_untrusted_candidate_guard_is_never_executed(self):
        target = self.snapshot/'kit/guard.py'
        target.write_text('raise SystemExit(0)\n', encoding='utf-8')
        p = self.cli()
        self.assertEqual(p.returncode, 1)
        self.assertEqual(json.loads(p.stdout)['reason'], 'candidate_unverified')


if __name__ == '__main__': unittest.main()
