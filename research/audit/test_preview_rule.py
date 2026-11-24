#!/usr/bin/env python3
"""Локальные физические фикстуры для read-only preview."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'research/audit')]
import core_audit as a
from kit.base.registry_store import StoreError
from kit.base.operation_card import compile_prompt
from kit.base.operation_plan import PlanSession
from kit.preview_rule import preview
from kit.render_rule import RenderError


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='kit-preview-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.layout = a.make_workspace(self.root, parent_scope='.')
        path = self.root / 'profiles/pilot/registry.json'
        doc = json.loads(path.read_text(encoding='utf-8'))
        doc['entries'].append(a.entry('R-1', 'rule', 'profile_owner', 'C-1', '.', text='Проверочный текст.'))
        a.write(path, doc)

    def test_preview_read_only_and_exact_hashes(self):
        before = a.tree_digest(self.root)
        result = preview(self.layout, area='L1', entry_id='R-1')
        self.assertEqual(before, a.tree_digest(self.root))
        self.assertEqual(result['outcome'], 'preview')
        self.assertEqual(result['content_sha256'], hashlib.sha256(result['content'].encode()).hexdigest())
        self.assertEqual(result['inputs_sha256']['L1'], hashlib.sha256((self.root/'profiles/pilot/registry.json').read_bytes()).hexdigest())
        self.assertIn('Проверочный текст.', result['content'])
        self.assertEqual(result, preview(self.layout, area='L1', entry_id='R-1'))

    def test_draft_and_missing_rejected(self):
        path = self.root / 'profiles/pilot/registry.json'
        doc = json.loads(path.read_text(encoding='utf-8')); doc['entries'][1]['state'] = 'draft'; a.write(path, doc)
        before = a.tree_digest(self.root)
        with self.assertRaises(RenderError): preview(self.layout, area='L1', entry_id='R-1')
        with self.assertRaises(RenderError): preview(self.layout, area='L1', entry_id='missing')
        self.assertEqual(before, a.tree_digest(self.root))

    def test_valid_journal_after_create_and_activate(self):
        session = PlanSession(self.layout, profile_id='Pilot')
        create = session.plan(a.card(ident='Q-1', scope='.'))
        session.apply(create, confirmed_ticket=create['ticket'])
        active = session.plan(compile_prompt('Активируй протокол Q-1 в профиле Pilot.'))
        session.apply(active, confirmed_ticket=active['ticket'])
        result = preview(self.layout, area='L1', entry_id='Q-1')
        self.assertIn('Сверяй свидетельства.', result['content'])

    def test_bad_journal_rejected(self):
        path = self.root / 'profiles/pilot/registry.json'
        doc = json.loads(path.read_text(encoding='utf-8'))
        a.write(path, {'registry_format': 2, 'registry': doc, 'journal': {'corrupt': True}})
        with self.assertRaises(StoreError) as exc: preview(self.layout, area='L1', entry_id='R-1')
        self.assertEqual(exc.exception.code, 'invalid_history')

    def test_conflict_rejected(self):
        profile = self.root / 'profiles/pilot/registry.json'; doc = json.loads(profile.read_text(encoding='utf-8'))
        doc['entries'][1].update(key='x', value='a'); a.write(profile, doc)
        project = self.root / '.agent-contract/project/registry.json'; other = json.loads(project.read_text(encoding='utf-8'))
        child = a.entry('Q-1', 'rule', 'project_owner', 'P-1', '.'); child.update(key='x', value='b')
        other['entries'].append(child); a.write(project, other)
        with self.assertRaises(RenderError): preview(self.layout, area='L1', entry_id='R-1')

    def test_missing_layer_rejected(self):
        (self.root/'.agent-contract/project/registry.json').unlink()
        with self.assertRaises(StoreError): preview(self.layout, area='L1', entry_id='R-1')

    def test_symlink_rejected(self):
        file = self.root/'profiles/pilot/registry.json'; saved = self.root/'profiles/pilot/synthetic.json'
        file.rename(saved)
        try: file.symlink_to(saved.name)
        except OSError as exc: self.skipTest(f'символическая ссылка недоступна: {exc}')
        with self.assertRaises(StoreError): preview(self.layout, area='L1', entry_id='R-1')

    def test_cli_and_relative_workspace(self):
        cmd = [sys.executable,'-B',str(ROOT/'kit/preview_rule.py'),'--workspace',str(self.root),
               '--profile-root','profiles/pilot','--area','L1','--entry-id','R-1']
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout)['outcome'], 'preview')
        cmd[cmd.index('--workspace')+1] = '.'
        result = subprocess.run(cmd, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '')


if __name__ == '__main__': unittest.main()
