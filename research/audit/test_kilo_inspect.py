#!/usr/bin/env python3
"""Разовая сверка только в синтетических временных проектах, не тест Kilo."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'research/audit')]
import core_audit as a
from kit.base.registry_store import StoreError
from kit.kilo_deploy import DeployError, KiloDeploymentSession
from kit.kilo_inspect import InspectionError, MAX_TARGET_BYTES, inspect


class InspectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='kit-inspect-synthetic-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.layout = a.make_workspace(self.root, parent_scope='.')
        self.profile = self.root/'profiles/pilot/registry.json'
        self.project = self.root/'.domain-agent-kit/project/registry.json'
        doc = json.loads(self.profile.read_text(encoding='utf-8'))
        doc['entries'].append(a.entry('R-1','rule','profile_owner','C-1','.',text='Синтетическое правило.'))
        a.write(self.profile, doc)
        self.directory = self.root/'.kilo/rules'
        self.directory.mkdir(parents=True)
        self.target = self.directory/'kit-l1-R-1.md'

    def inspection(self, area='L1', entry_id='R-1'):
        return inspect(self.layout, area=area, entry_id=entry_id)

    def deploy(self, area='L1', entry_id='R-1'):
        session = KiloDeploymentSession(self.layout)
        plan = session.plan(area=area, entry_id=entry_id)
        session.apply(plan, confirmed_ticket=plan['ticket'])
        return plan

    def test_missing_current_and_different_read_only(self):
        before = a.tree_digest(self.root)
        missing = self.inspection()
        self.assertEqual(missing['outcome'], 'missing')
        self.assertFalse(missing['target_present'])
        self.assertIsNone(missing['target_sha256'])
        self.assertEqual(before, a.tree_digest(self.root))
        plan = self.deploy()
        before = a.tree_digest(self.root)
        result = self.inspection()
        self.assertEqual(result['outcome'], 'current')
        self.assertTrue(result['target_present'])
        self.assertEqual(result['expected_sha256'], plan['content_sha256'])
        self.assertEqual(result['target_sha256'], plan['content_sha256'])
        self.assertNotIn('content', result)
        self.assertNotIn('Синтетическое правило.', json.dumps(result, ensure_ascii=False))
        self.assertEqual(before, a.tree_digest(self.root))
        self.target.write_bytes(b'changed')
        before = a.tree_digest(self.root)
        different = self.inspection()
        self.assertEqual(different['outcome'], 'different')
        self.assertEqual(different['target_sha256'], hashlib.sha256(b'changed').hexdigest())
        self.assertEqual(before, a.tree_digest(self.root))

    def test_inactive_source_with_file_and_without_file(self):
        self.deploy()
        doc = json.loads(self.profile.read_text(encoding='utf-8'))
        doc['entries'][1]['state'] = 'draft'; a.write(self.profile, doc)
        before = a.tree_digest(self.root)
        result = self.inspection()
        self.assertEqual(result['outcome'], 'source_unrenderable')
        self.assertTrue(result['target_present'])
        self.assertIsNone(result['expected_sha256'])
        self.assertEqual(before, a.tree_digest(self.root))
        self.target.unlink()  # Только синтетическая фикстура теста.
        result = self.inspection()
        self.assertEqual(result['outcome'], 'source_unrenderable')
        self.assertFalse(result['target_present'])

    def test_deleted_source_and_narrow_scope(self):
        self.deploy()
        doc = json.loads(self.profile.read_text(encoding='utf-8'))
        doc['entries'][1]['scope'] = 'docs'; a.write(self.profile, doc)
        self.assertEqual(self.inspection()['outcome'], 'source_unrenderable')
        doc['entries'].pop(); a.write(self.profile, doc)
        self.assertEqual(self.inspection()['outcome'], 'source_unrenderable')
        self.assertTrue(self.inspection()['target_present'])

    def test_structural_conflict_is_not_current(self):
        self.deploy()
        profile = json.loads(self.profile.read_text(encoding='utf-8'))
        profile['entries'][1].update(key='example', value='a'); a.write(self.profile, profile)
        project = json.loads(self.project.read_text(encoding='utf-8'))
        rule = a.entry('P-R', 'rule', 'project_owner', 'P-1', '.', text='конфликт')
        rule.update(key='example', value='b'); project['entries'].append(rule); a.write(self.project, project)
        result = self.inspection()
        self.assertEqual(result['outcome'], 'source_unrenderable')
        self.assertTrue(result['target_present'])

    def test_changed_source_detected(self):
        self.deploy()
        doc = json.loads(self.profile.read_text(encoding='utf-8'))
        doc['entries'][1]['text'] = 'Новая редакция.'; doc['revision'] += 1; a.write(self.profile, doc)
        self.assertEqual(self.inspection()['outcome'], 'different')

    def test_l2_uses_same_name_as_deployment(self):
        doc = json.loads(self.project.read_text(encoding='utf-8'))
        doc['entries'].append(a.entry('P-R','rule','project_owner','P-1','.',text='Тест L2.'))
        a.write(self.project, doc)
        self.deploy('L2','P-R')
        result = self.inspection('L2','P-R')
        self.assertEqual(result['target'], '.kilo/rules/kit-l2-P-R.md')
        self.assertEqual(result['outcome'], 'current')

    def test_invalid_target_rejected(self):
        for area, ident in [('L0','R-1'), ('L1','../registry'), ('L1','x/y'), ('L1',''), ('L1',None), ([], 'R-1')]:
            with self.subTest(area=area, ident=ident), self.assertRaises(DeployError):
                self.inspection(area, ident)

    def test_bad_registry_is_not_reported_as_current(self):
        self.deploy(); self.profile.write_bytes(b'not json')
        with self.assertRaises(StoreError): self.inspection()

    def test_symlink_refused_without_reading(self):
        other = self.directory/'other'; other.write_bytes(b'foreign')
        try: self.target.symlink_to(other)
        except OSError as exc: self.skipTest(f'нет символических ссылок: {exc}')
        with patch('kit.kilo_inspect.os.open') as opened:
            with self.assertRaises(InspectionError) as exc: self.inspection()
        self.assertEqual(exc.exception.code, 'unsafe_target')
        opened.assert_not_called()
        self.assertEqual(other.read_bytes(), b'foreign')

    def test_symlink_substitution_at_open_is_not_followed_when_supported(self):
        if not hasattr(os, 'O_NOFOLLOW'):
            self.skipTest('O_NOFOLLOW не доступен')
        self.target.write_bytes(b'original')
        other = self.directory/'other'; other.write_bytes(b'foreign')
        original = os.open
        def replace_open(path, flags, *args):
            self.target.unlink()
            self.target.symlink_to(other)
            return original(path, flags, *args)
        with patch('kit.kilo_inspect.os.open', side_effect=replace_open):
            with self.assertRaises(InspectionError) as exc: self.inspection()
        self.assertEqual(exc.exception.code, 'target_unreadable')
        self.assertEqual(other.read_bytes(), b'foreign')

    def test_hardlink_refused(self):
        other = self.directory/'other'; other.write_bytes(b'foreign')
        try: os.link(other, self.target)
        except OSError as exc: self.skipTest(f'нет жестких ссылок: {exc}')
        with self.assertRaises(InspectionError) as exc: self.inspection()
        self.assertEqual(exc.exception.code, 'unsafe_target')

    def test_directory_and_oversized_file_refused(self):
        self.target.mkdir()
        with self.assertRaises(InspectionError) as exc: self.inspection()
        self.assertEqual(exc.exception.code, 'unsafe_target')
        self.target.rmdir()
        self.target.write_bytes(b'x'*(MAX_TARGET_BYTES+1))
        with patch('kit.kilo_inspect.os.open') as opened:
            with self.assertRaises(InspectionError) as exc: self.inspection()
        self.assertEqual(exc.exception.code, 'target_too_large')
        opened.assert_not_called()

    def test_target_changed_while_reading(self):
        self.deploy(); original = os.read; changed = []
        def changed_read(fd, size):
            data = original(fd, size)
            if not changed:
                changed.append(True); self.target.write_bytes(b'external change')
            return data
        with patch('kit.kilo_inspect.os.read', side_effect=changed_read):
            with self.assertRaises(InspectionError) as exc: self.inspection()
        self.assertEqual(exc.exception.code, 'target_changed')
        self.assertEqual(self.target.read_bytes(), b'external change')

    def test_cli_reports_only_hashes(self):
        self.deploy(); before = a.tree_digest(self.root)
        p = subprocess.run([sys.executable, '-B', str(ROOT/'kit/kilo_inspect.py'), '--workspace', str(self.root),
                            '--profile-root', 'profiles/pilot', '--area', 'L1', '--entry-id', 'R-1'],
                           capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.assertEqual(p.returncode, 0, p.stderr)
        result = json.loads(p.stdout)
        self.assertEqual(result['outcome'], 'current')
        self.assertNotIn('Синтетическое правило.', p.stdout)
        self.assertEqual(before, a.tree_digest(self.root))

    def test_cli_missing_is_not_error_or_current(self):
        p = subprocess.run([sys.executable, '-B', str(ROOT/'kit/kilo_inspect.py'), '--workspace', str(self.root),
                            '--profile-root', 'profiles/pilot', '--area', 'L1', '--entry-id', 'R-1'],
                           capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout)['outcome'], 'missing')

    def test_cli_invalid_target_error(self):
        p = subprocess.run([sys.executable, '-B', str(ROOT/'kit/kilo_inspect.py'), '--workspace', str(self.root),
                            '--profile-root', 'profiles/pilot', '--area', 'L1', '--entry-id', '../invalid'],
                           capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.assertEqual(p.returncode, 1)
        self.assertEqual(json.loads(p.stderr)['code'], 'invalid_target')
        self.assertFalse(p.stdout)


if __name__ == '__main__': unittest.main()
