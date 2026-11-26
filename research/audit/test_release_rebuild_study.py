#!/usr/bin/env python3
"""Новая пустая реплика, только синтетический архив и временная директория."""
import copy
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'research/audit')]
import core_audit as audit
import release_install_study as install
import release_policy_study as policy
import release_rebuild_study as rebuild
import test_release_install_study as fixture
import test_atomic_init as atomic
import test_source_release_trust as signing


@unittest.skipUnless(signing.SUPPORTED and atomic.SUPPORTED,'OpenSSL/Linux unavailable; not_run')
class RebuildTests(unittest.TestCase):
    def setUp(self):
        self.fx=fixture.InstallTests();self.fx.setUp();self.addCleanup(self.fx.doCleanups)
        plan=self.fx.s.plan()
        with mock.patch.object(install.publish.atomic,'_rename_noreplace',side_effect=OSError('injected')):
            with self.assertRaisesRegex(install.InstallError,'publication_unknown'):
                self.fx.s.apply(plan,confirmed_ticket=plan['ticket'])
        self.stage=plan['publication_plan']['stage_name']
        self.new_parent=self.fx.root/'separate';self.new_parent.mkdir()
        self.new=self.new_parent/'new';self.s=self.make(self.new)
    def make(self,dest):
        return rebuild.RebuildSession(self.fx.dest,self.stage,dest,profile_root='profiles/pilot',
                 archive_bytes=self.fx.raw,statement=policy.canonical(self.fx.f.doc),
                 signature=self.fx.f.sign(),policy=self.fx.f.policy,verify_signature=self.fx.f.fx.verify)
    def test_rebuild_separate_new_container_does_not_change_old(self):
        before=audit.tree_digest(self.fx.root/self.stage)
        p=self.s.plan();self.assertEqual(p['old_observation']['outcome'],'observation_only')
        self.assertEqual(p['old_observation']['destination_state'],'absent')
        self.assertEqual(p['old_observation']['stage_state'],'matches_observation')
        self.assertEqual(p['user_l1_l2_history'],'not_copied_or_recovered')
        self.assertFalse(self.new.exists());self.assertEqual(before,audit.tree_digest(self.fx.root/self.stage))
        with self.assertRaisesRegex(rebuild.RebuildError,'confirmation_required'):
            self.s.apply(p,confirmed_ticket='bad')
        result=self.s.apply(p,confirmed_ticket=p['ticket'])
        self.assertEqual(result['outcome'],'study_new_empty_container_published')
        self.assertEqual(before,audit.tree_digest(self.fx.root/self.stage));self.assertFalse(self.fx.dest.exists())
        self.assertTrue((self.new/'snapshot/kit/KIT-VERSION.json').exists())
        with self.assertRaisesRegex(rebuild.RebuildError,'ticket_unknown'):self.s.apply(p,confirmed_ticket=p['ticket'])
    def test_changed_old_observation_refuses_without_new_write(self):
        p=self.s.plan();(self.fx.root/self.stage/'extra').write_bytes(b'changed')
        with self.assertRaisesRegex(rebuild.RebuildError,'stale_observation'):
            self.s.apply(p,confirmed_ticket=p['ticket'])
        self.assertFalse(self.new.exists());self.assertTrue((self.fx.root/self.stage/'extra').exists())
    def test_bad_plan_cancel_and_same_parent(self):
        p=self.s.plan();bad=copy.deepcopy(p);bad['old_completion']='proved'
        with self.assertRaisesRegex(rebuild.RebuildError,'plan_mismatch'):self.s.apply(bad,confirmed_ticket=p['ticket'])
        p=self.s.plan();self.s.cancel()
        with self.assertRaisesRegex(rebuild.RebuildError,'ticket_unknown'):self.s.apply(p,confirmed_ticket=p['ticket'])
        for destination in (self.fx.dest,self.fx.root/'same-parent',self.fx.dest/'nested'):
            with self.subTest(destination=destination):
                with self.assertRaisesRegex(rebuild.RebuildError,'destinations_overlap'):self.make(destination).plan()
        self.assertFalse(self.new.exists())
    def test_new_rename_failure_preserves_both_stages_and_refuses_replay(self):
        before=audit.tree_digest(self.fx.root/self.stage);p=self.s.plan()
        newstage=p['new_install_plan']['publication_plan']['stage_name']
        with mock.patch.object(install.publish.atomic,'_rename_noreplace',side_effect=OSError('injected')):
            with self.assertRaisesRegex(rebuild.RebuildError,'publication_unknown'):
                self.s.apply(p,confirmed_ticket=p['ticket'])
        self.assertEqual(before,audit.tree_digest(self.fx.root/self.stage))
        self.assertTrue((self.new_parent/newstage).is_dir());self.assertFalse(self.new.exists())
        with self.assertRaisesRegex(rebuild.RebuildError,'ticket_unknown'):self.s.apply(p,confirmed_ticket=p['ticket'])

    def test_new_parent_occupied_and_old_not_deleted(self):
        self.new.mkdir();(self.new/'keep').write_bytes(b'keep')
        with self.assertRaisesRegex(rebuild.RebuildError,'destination_occupied'):self.s.plan()
        self.assertEqual((self.new/'keep').read_bytes(),b'keep');self.assertTrue((self.fx.root/self.stage).is_dir())

if __name__=='__main__':unittest.main()
