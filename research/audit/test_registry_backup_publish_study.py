#!/usr/bin/env python3
"""Публикация ограниченного снимка только в синтетическом временном дереве."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'research/audit')]
import core_audit as audit
import registry_backup_study as backup
import registry_backup_publish_study as publish
import test_profile_copy as fixture
import test_atomic_init as atomic
from kit.base import registry_store as store


@unittest.skipUnless(atomic.SUPPORTED and store.fcntl is not None,'POSIX/Linux unavailable; not_run')
class BackupPublishTests(unittest.TestCase):
    def setUp(self):
        self.fx=fixture.ProfileCopyTests();self.fx.setUp();self.addCleanup(self.fx.doCleanups)
        self.parent=self.fx.root/'backups';self.parent.mkdir();self.dest=self.parent/'one'
        self.s=publish.BackupSession(self.fx.a,self.dest,system_pin=self.fx.pin)
    def test_plan_confirm_publish_and_verify(self):
        before=audit.tree_digest(self.fx.a.workspace);p=self.s.plan()
        self.assertFalse(self.dest.exists());self.assertEqual(p['confidentiality'],'not_provided_sensitive_data')
        with self.assertRaisesRegex(publish.PublishError,'confirmation_required'):self.s.apply(p,confirmed_ticket='нет')
        result=self.s.apply(p,confirmed_ticket=p['ticket']);self.assertEqual(result['outcome'],'study_snapshot_published')
        report,data=backup.inspect((self.dest/'backup.json').read_bytes(),system_pin=self.fx.pin)
        self.assertEqual(report['authenticity'],'not_verified');self.assertEqual(data['L1'],self.fx.a1.read_bytes())
        self.assertEqual(before,audit.tree_digest(self.fx.a.workspace))
        with self.assertRaisesRegex(publish.PublishError,'ticket_unknown'):self.s.apply(p,confirmed_ticket=p['ticket'])
    def test_cancel_changed_plan_and_source_drift(self):
        p=self.s.plan();bad=copy.deepcopy(p);bad['snapshot_sha256']='0'*64
        with self.assertRaisesRegex(publish.PublishError,'plan_mismatch'):self.s.apply(bad,confirmed_ticket=p['ticket'])
        p=self.s.plan();self.s.cancel()
        with self.assertRaisesRegex(publish.PublishError,'ticket_unknown'):self.s.apply(p,confirmed_ticket=p['ticket'])
        p=self.s.plan();self.fx.a1.write_bytes(self.fx.a1.read_bytes()+b' ')
        with self.assertRaisesRegex(publish.PublishError,'stale_plan'):self.s.apply(p,confirmed_ticket=p['ticket'])
        self.assertFalse(self.dest.exists())
    def test_occupied_and_inside_source_refused(self):
        self.dest.mkdir();(self.dest/'keep').write_bytes(b'keep')
        with self.assertRaisesRegex(publish.PublishError,'destination_occupied'):self.s.plan()
        self.assertEqual((self.dest/'keep').read_bytes(),b'keep')
        nested=publish.BackupSession(self.fx.a,self.fx.a.workspace/'backup',system_pin=self.fx.pin)
        with self.assertRaisesRegex(publish.PublishError,'destination_invalid'):nested.plan()
    def test_rename_failure_leaves_stage_and_blocks_retry(self):
        p=self.s.plan()
        with mock.patch.object(publish.atomic,'_rename_noreplace',side_effect=OSError('fault')):
            with self.assertRaisesRegex(publish.PublishError,'publication_unknown'):self.s.apply(p,confirmed_ticket=p['ticket'])
        stage=self.parent/p['stage_name'];self.assertTrue((stage/'backup.json').is_file());self.assertFalse(self.dest.exists())
        with self.assertRaisesRegex(publish.PublishError,'ticket_unknown'):self.s.apply(p,confirmed_ticket=p['ticket'])
        with self.assertRaisesRegex(publish.PublishError,'stage_pending'):self.s.plan()
    def test_file_fsync_failure_leaves_partial_stage(self):
        p=self.s.plan()
        with mock.patch.object(publish.os,'fsync',side_effect=OSError('fault')):
            with self.assertRaisesRegex(publish.PublishError,'stage_partial_or_unverified'):self.s.apply(p,confirmed_ticket=p['ticket'])
        self.assertTrue((self.parent/p['stage_name']).is_dir());self.assertFalse(self.dest.exists())

if __name__=='__main__':unittest.main()
