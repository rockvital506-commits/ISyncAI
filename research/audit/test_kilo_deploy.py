#!/usr/bin/env python3
"""Доставка только в синтетические временные деревья, без реального Kilo."""
import copy
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
from kit.base.registry_store import Layout, StoreError
from kit.kilo_deploy import KiloDeploymentSession, DeployError
from kit.render_rule import RenderError


class DeployTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='kit-kilo-synthetic-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.layout = a.make_workspace(self.root, parent_scope='.')
        self.profile = self.root/'profiles/pilot/registry.json'
        doc = json.loads(self.profile.read_text(encoding='utf-8'))
        doc['entries'].append(a.entry('R-1','rule','profile_owner','C-1','.',text='Синтетическое правило.'))
        a.write(self.profile, doc)
        self.dir = self.root/'.kilo/rules'; self.dir.mkdir(parents=True)
        self.session = KiloDeploymentSession(self.layout)

    def plan(self): return self.session.plan(area='L1', entry_id='R-1')
    def apply(self, plan): return self.session.apply(copy.deepcopy(plan), confirmed_ticket=plan['ticket'])
    def denied(self, action, code):
        before = a.tree_digest(self.root)
        with self.assertRaises(DeployError) as exc: action()
        self.assertEqual(exc.exception.code, code)
        self.assertEqual(before, a.tree_digest(self.root))

    def test_plan_confirmation_exact_create_and_no_overwrite(self):
        before = a.tree_digest(self.root); plan = self.plan()
        self.assertEqual(before, a.tree_digest(self.root))
        self.denied(lambda: self.session.apply(plan), 'confirmation_required')
        self.denied(lambda: self.session.apply(plan, confirmed_ticket='wrong'), 'confirmation_required')
        result = self.apply(plan)
        self.assertEqual(result['outcome'], 'created')
        target = self.root/result['target']
        self.assertEqual(target.read_text(encoding='utf-8'), plan['content'])
        self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), plan['content_sha256'])
        self.denied(lambda: self.apply(plan), 'ticket_unknown')
        self.denied(lambda: self.plan(), 'target_exists')

    def test_l2_and_cancel(self):
        project = self.root/'.agent-contract/project/registry.json'
        doc = json.loads(project.read_text(encoding='utf-8'))
        doc['entries'].append(a.entry('R-2', 'rule', 'project_owner', 'P-1', '.', text='Проектное правило.'))
        a.write(project, doc)
        plan = self.session.plan(area='L2', entry_id='R-2')
        self.session.cancel()
        self.denied(lambda: self.apply(plan), 'ticket_unknown')
        plan = self.session.plan(area='L2', entry_id='R-2')
        self.assertEqual(self.apply(plan)['target'], '.kilo/rules/kit-l2-R-2.md')

    def test_edited_plan_and_foreign_session(self):
        before = a.tree_digest(self.root); plan = self.plan()
        forged = copy.deepcopy(plan); forged['target'] = 'kit/base/registry.json'
        self.denied(lambda: self.session.apply(forged, confirmed_ticket=plan['ticket']), 'plan_mismatch')
        other = KiloDeploymentSession(self.layout)
        self.denied(lambda: other.apply(plan, confirmed_ticket=plan['ticket']), 'ticket_unknown')
        self.assertEqual(before, a.tree_digest(self.root))

    def test_changed_source_denied_and_ticket_consumed(self):
        plan = self.plan()
        project = self.root/'.agent-contract/project/registry.json'
        project.write_bytes(project.read_bytes()+b'\n')
        self.denied(lambda: self.apply(plan), 'stale_plan')
        self.denied(lambda: self.apply(plan), 'ticket_unknown')

    def test_replaced_directory_denied(self):
        plan = self.plan(); self.dir.rename(self.root/'.kilo/old-rules'); self.dir.mkdir()
        self.denied(lambda: self.apply(plan), 'stale_plan')

    def test_existing_file_is_not_overwritten(self):
        plan = self.plan(); target = self.root/plan['target']; target.write_text('владелец', encoding='utf-8')
        self.denied(lambda: self.apply(plan), 'target_exists')
        self.assertEqual(target.read_text(encoding='utf-8'), 'владелец')

    def test_symlink_directory_rejected(self):
        self.dir.rename(self.root/'.kilo/real-rules')
        try: self.dir.symlink_to(self.root/'.kilo/real-rules', target_is_directory=True)
        except OSError as exc: self.skipTest(f'нет символических ссылок: {exc}')
        before = a.tree_digest(self.root)
        with self.assertRaises(StoreError): self.plan()
        self.assertEqual(before, a.tree_digest(self.root))

    def test_profile_root_overlap_rejected(self):
        doc = json.loads(self.profile.read_text(encoding='utf-8')); doc['roots'] = ['.kilo']
        a.write(self.root/'.kilo/registry.json', doc)
        session = KiloDeploymentSession(Layout(self.root, '.kilo'))
        self.denied(lambda: session.plan(area='L1', entry_id='R-1'), 'root_overlap')

    def test_failed_write_removes_created_file_only(self):
        plan = self.plan(); before = a.tree_digest(self.root)
        with patch('kit.kilo_deploy.os.write', side_effect=OSError('synthetic')):
            with self.assertRaises(DeployError) as exc: self.apply(plan)
        self.assertEqual(exc.exception.code, 'write_failed')
        self.assertEqual(before, a.tree_digest(self.root))

    def test_partial_write_is_cleaned_up(self):
        plan = self.plan(); before = a.tree_digest(self.root); original = os.write; calls = []
        def fail_after_partial(fd, data):
            if not calls:
                calls.append(1)
                return original(fd, data[:3])
            raise OSError('synthetic partial write')
        with patch('kit.kilo_deploy.os.write', side_effect=fail_after_partial):
            with self.assertRaises(DeployError) as exc: self.apply(plan)
        self.assertEqual(exc.exception.code, 'write_failed')
        self.assertEqual(before, a.tree_digest(self.root))

    def test_file_exists_error_after_open_also_cleans_up(self):
        plan = self.plan(); before = a.tree_digest(self.root)
        with patch('kit.kilo_deploy.os.write', side_effect=FileExistsError('synthetic')):
            with self.assertRaises(DeployError) as exc: self.apply(plan)
        self.assertEqual(exc.exception.code, 'write_failed')
        self.assertEqual(before, a.tree_digest(self.root))

    def test_unknown_created_identity_is_reported(self):
        plan = self.plan()
        with patch('kit.kilo_deploy.os.fstat', side_effect=OSError('synthetic')):
            with self.assertRaises(DeployError) as exc: self.apply(plan)
        self.assertEqual(exc.exception.code, 'cleanup_unsafe')
        self.assertTrue((self.root/plan['target']).exists())

    def test_draft_and_narrow_scope_rejected(self):
        doc = json.loads(self.profile.read_text(encoding='utf-8')); doc['entries'][1]['state'] = 'draft'; a.write(self.profile, doc)
        with self.assertRaises(RenderError): self.plan()
        doc['entries'][1]['state'] = 'active'; doc['entries'][1]['scope'] = 'docs'; a.write(self.profile, doc)
        with self.assertRaises(RenderError): self.plan()

    def test_cli_separate_confirmation(self):
        p = subprocess.Popen([sys.executable, '-B', str(ROOT/'kit/kilo_deploy.py'), '--workspace', str(self.root),
                              '--profile-root', 'profiles/pilot'], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, encoding='utf-8', bufsize=1)
        try:
            p.stdin.write(json.dumps({'type':'plan','area':'L1','entry_id':'R-1'})+'\n'); p.stdin.flush()
            plan = json.loads(p.stdout.readline()); self.assertEqual(plan['outcome'], 'planned')
            self.assertFalse((self.root/plan['target']).exists())
            p.stdin.write(json.dumps({'type':'apply','plan':plan,'confirmed_ticket':plan['ticket']},ensure_ascii=False)+'\n'); p.stdin.flush()
            result = json.loads(p.stdout.readline()); self.assertEqual(result['outcome'], 'created')
            self.assertEqual(hashlib.sha256((self.root/result['target']).read_bytes()).hexdigest(), plan['content_sha256'])
        finally:
            p.stdin.close(); p.wait(timeout=10); p.stdout.close(); p.stderr.close()

    def test_oversized_input_is_rejected(self):
        before = a.tree_digest(self.root)
        p = subprocess.run([sys.executable,'-B',str(ROOT/'kit/kilo_deploy.py'),'--workspace',str(self.root),
                            '--profile-root','profiles/pilot'],input='x'*1_048_577+'\n',text=True,capture_output=True,timeout=30)
        self.assertNotEqual(p.returncode,0)
        self.assertEqual(json.loads(p.stdout)['code'],'input_too_large')
        self.assertEqual(before,a.tree_digest(self.root))


if __name__ == '__main__': unittest.main()
