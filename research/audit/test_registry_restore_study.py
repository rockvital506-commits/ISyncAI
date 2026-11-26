#!/usr/bin/env python3
"""Только синтетическое восстановление трёх реестров в новый временный каталог."""
import copy
import hashlib
import os
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'research/audit')]
import core_audit as audit
import registry_backup_study as backup
import registry_backup_publish_study as publish
import release_archive_cli_study as reader
import registry_restore_study as restore
import test_profile_copy as fixture
import test_atomic_init as atomic
from kit.base import registry_store as store


@unittest.skipUnless(atomic.SUPPORTED and store.fcntl is not None,'POSIX/Linux unavailable; not_run')
class RestoreTests(unittest.TestCase):
    def setUp(self):
        self.fx=fixture.ProfileCopyTests();self.fx.setUp();self.addCleanup(self.fx.doCleanups)
        self.wire,_=backup.capture(self.fx.a,system_pin=self.fx.pin)
        self.pin=hashlib.sha256(self.wire).hexdigest();self.dest=self.fx.root/'restored'
        self.s=restore.RestoreSession(self.dest,wire=self.wire,snapshot_pin=self.pin,system_pin=self.fx.pin)
    def test_restore_exact_bytes_and_histories_in_new_workspace(self):
        before=audit.tree_digest(self.fx.a.workspace);p=self.s.plan()
        self.assertFalse(self.dest.exists());self.assertEqual(p['scope'],'not_kit_or_project_files')
        with self.assertRaisesRegex(restore.RestoreError,'confirmation_required'):self.s.apply(p,confirmed_ticket='no')
        result=self.s.apply(p,confirmed_ticket=p['ticket'])
        self.assertEqual(result['outcome'],'study_registries_restored_unverified_origin')
        self.assertEqual(audit.tree_digest(self.fx.a.workspace),before)
        target=store.Layout(self.dest,'profiles/pilot')
        for area in ('L1','L2'):
            self.assertEqual(store.registry_history(self.fx.a,target=area),store.registry_history(target,target=area))
        _,data=backup.inspect(self.wire,system_pin=self.fx.pin)
        self.assertEqual((self.dest/'kit/base/registry.json').read_bytes(),data['L0'])
        self.assertEqual((self.dest/'profiles/pilot/registry.json').read_bytes(),data['L1'])
        self.assertEqual((self.dest/'.domain-agent-kit/project/registry.json').read_bytes(),data['L2'])
        with self.assertRaisesRegex(restore.RestoreError,'ticket_unknown'):self.s.apply(p,confirmed_ticket=p['ticket'])
    def test_published_backup_to_new_workspace_end_to_end(self):
        parent=self.fx.root/'backup-parent';parent.mkdir()
        publisher=publish.BackupSession(self.fx.a,parent/'backup',system_pin=self.fx.pin)
        plan=publisher.plan();out=publisher.apply(plan,confirmed_ticket=plan['ticket'])
        wire=reader.read_regular(parent/'backup'/'backup.json',backup.MAX_WIRE)
        self.assertEqual(hashlib.sha256(wire).hexdigest(),out['sha256'])
        session=restore.RestoreSession(self.dest,wire=wire,snapshot_pin=out['sha256'],system_pin=self.fx.pin)
        restored=session.plan();session.apply(restored,confirmed_ticket=restored['ticket'])
        target=store.Layout(self.dest,'profiles/pilot')
        self.assertEqual(store.registry_history(self.fx.a,target='L1'),store.registry_history(target,target='L1'))
        self.assertEqual(store.registry_history(self.fx.a,target='L2'),store.registry_history(target,target='L2'))
        self.assertEqual((self.dest/'profiles/pilot/registry.json').read_bytes(),self.fx.a1.read_bytes())

    def test_wrong_pins_and_changed_plan_do_not_write(self):
        with self.assertRaisesRegex(restore.RestoreError,'snapshot_pin_mismatch'):
            restore.RestoreSession(self.dest,wire=self.wire,snapshot_pin='0'*64,system_pin=self.fx.pin).plan()
        with self.assertRaisesRegex(restore.RestoreError,'snapshot_unusable'):
            restore.RestoreSession(self.dest,wire=self.wire,snapshot_pin=self.pin,system_pin='0'*64).plan()
        p=self.s.plan();bad=copy.deepcopy(p);bad['files'][0]['sha256']='0'*64
        with self.assertRaisesRegex(restore.RestoreError,'plan_mismatch'):self.s.apply(bad,confirmed_ticket=p['ticket'])
        p=self.s.plan();self.s.wire+=b' '
        with self.assertRaisesRegex(restore.RestoreError,'stale_plan'):self.s.apply(p,confirmed_ticket=p['ticket'])
        self.assertFalse(self.dest.exists())
    def test_cancel_occupied_and_parent_lock(self):
        p=self.s.plan();self.s.cancel()
        with self.assertRaisesRegex(restore.RestoreError,'ticket_unknown'):self.s.apply(p,confirmed_ticket=p['ticket'])
        p=self.s.plan();fd=os.open(self.dest.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:
            store.fcntl.flock(fd,store.fcntl.LOCK_EX|store.fcntl.LOCK_NB)
            with self.assertRaisesRegex(restore.RestoreError,'publication_busy'):self.s.apply(p,confirmed_ticket=p['ticket'])
        finally:os.close(fd)
        self.dest.mkdir();(self.dest/'keep').write_bytes(b'keep')
        with self.assertRaisesRegex(restore.RestoreError,'destination_occupied'):self.s.plan()
        self.assertEqual((self.dest/'keep').read_bytes(),b'keep')
    def test_failed_rename_retains_stage_and_blocks_repeat(self):
        p=self.s.plan()
        with mock.patch.object(restore.atomic,'_rename_noreplace',side_effect=OSError('fault')):
            with self.assertRaisesRegex(restore.RestoreError,'publication_unknown'):self.s.apply(p,confirmed_ticket=p['ticket'])
        self.assertTrue((self.dest.parent/p['stage_name']).is_dir());self.assertFalse(self.dest.exists())
        with self.assertRaisesRegex(restore.RestoreError,'ticket_unknown'):self.s.apply(p,confirmed_ticket=p['ticket'])
        with self.assertRaisesRegex(restore.RestoreError,'stage_pending'):self.s.plan()

if __name__=='__main__':unittest.main()
