#!/usr/bin/env python3
"""Только синтетический предпросмотр; реальные среды не запускались."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'research/audit')]
import core_audit as audit
import environment_adapter_preview_study as adapter
import test_context_modes as context_fixture
import test_kilo_deploy as kilo_fixture
import test_copilot_deploy as copilot_fixture
from kit import context_export


class AdapterPreviewTests(unittest.TestCase):
    def setup_fixture(self,cls):
        value=cls();value.setUp();self.addCleanup(value.doCleanups);return value
    def test_arena_two_modes_match_context_export_without_writing(self):
        f=self.setup_fixture(context_fixture.ContextTests)
        tmp=tempfile.TemporaryDirectory(prefix='preview-only-');self.addCleanup(tmp.cleanup)
        before=audit.tree_digest(f.root)
        for mode in ('project','kit'):
            result=adapter.arena(f.layout,mode=mode,scope='docs/file',choices=copy.deepcopy(f.choices))
            session=context_export.ContextExportSession(f.layout,Path(tmp.name)/mode,mode=mode,scope='docs/file',choices=f.choices)
            plan=session.plan()
            self.assertEqual(result['content_utf8'],plan['content_utf8'])
            self.assertEqual(result['content_sha256'],plan['content_sha256'])
            self.assertNotIn('EXCLUDED_PROFILE_SECRET',result['content_utf8'])
            self.assertIn('SYS-PROJECT-MODE' if mode=='project' else 'SYS-KIT-MODE',result['content_utf8'])
            self.assertEqual(result['delivery'],'not_performed');self.assertEqual(result['applied'],'not_run')
            self.assertFalse((Path(tmp.name)/mode).exists())
        self.assertEqual(before,audit.tree_digest(f.root))
        with self.assertRaisesRegex(adapter.AdapterError,'context_unavailable:context_choices_incomplete'):
            adapter.arena(f.layout,mode='project',scope='docs/file',choices={'include':[],'exclude':[]})
    def test_kilo_preview_matches_existing_plan_and_rejects_non_global(self):
        f=self.setup_fixture(kilo_fixture.DeployTests);before=audit.tree_digest(f.root)
        result=adapter.instruction(f.layout,environment='kilo',area='L1',entry_id='R-1');plan=f.plan()
        self.assertEqual(result['content_utf8'],plan['content']);self.assertEqual(result['target_hint'],plan['target'])
        self.assertEqual(result['content_sha256'],plan['content_sha256']);self.assertIsNone(result['mode'])
        self.assertFalse((f.root/plan['target']).exists());self.assertEqual(before,audit.tree_digest(f.root))
        with self.assertRaisesRegex(adapter.AdapterError,'rule_invalid'):
            adapter.instruction(f.layout,environment='kilo',area='L1',entry_id='missing')
    def test_copilot_preview_matches_plan_and_refuses_narrow(self):
        f=self.setup_fixture(copilot_fixture.CopilotTests);before=audit.tree_digest(f.root)
        for area in ('L1','L2'):
            result=adapter.instruction(f.layout,environment='copilot',area=area,entry_id='GLOBAL')
            plan=f.session().plan(area=area,entry_id='GLOBAL')
            self.assertEqual(result['content_utf8'],plan['content_utf8']);self.assertEqual(result['target_hint'],plan['target'])
            self.assertEqual(result['content_sha256'],plan['content_sha256']);self.assertEqual(result['read'],'not_run')
            self.assertFalse((f.root/plan['target']).exists())
        with self.assertRaisesRegex(adapter.AdapterError,'rule_invalid'):
            adapter.instruction(f.layout,environment='copilot',area='L1',entry_id='NARROW')
        self.assertEqual(before,audit.tree_digest(f.root))
    def test_unsupported_environment_refused(self):
        with self.assertRaisesRegex(adapter.AdapterError,'environment_invalid'):
            adapter.instruction(None,environment='arena',area='L1',entry_id='R-1')

if __name__=='__main__':unittest.main()
