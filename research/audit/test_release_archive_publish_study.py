#!/usr/bin/env python3
"""Публикация в синтетические временные каталоги, не выпуск или установка."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'research/audit')]
import release_archive_publish_study as publish
import release_archive_study as archive
import release_policy_study as policy
import test_release_policy_study as fixtures
import test_atomic_init as atomic_test
from kit import atomic_init


@unittest.skipUnless(atomic_test.SUPPORTED,'Linux atomic prerequisites unavailable; not_run')
class PublishTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.ReleasePolicyStudyTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.tmp=tempfile.TemporaryDirectory(prefix='archive-publish-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.dest=self.root/'snapshot'
        self.bytes=archive.build(self.f.manifest,self.f.files);self.statement=policy.canonical(self.f.doc);self.sig=self.f.sign()
    def session(self):return publish.PublishSession(self.dest,archive_bytes=self.bytes,statement=self.statement,
                        signature=self.sig,policy=self.f.policy,verify_signature=self.f.fx.verify)
    def error(self,code,fn,*args,**kw):
        with self.assertRaises(publish.PublishError) as e:fn(*args,**kw)
        self.assertEqual(str(e.exception),code)
    def test_verified_capture_and_publication(self):
        report,rows=archive.capture(self.bytes,self.statement,self.sig,policy=self.f.policy,verify_signature=self.f.fx.verify)
        self.assertEqual(report['outcome'],'study_policy_consistent');self.assertIsInstance(rows,tuple)
        s=self.session();p=s.plan();self.assertFalse(self.dest.exists());self.assertEqual(len(p['files']),len(self.f.files)+1)
        self.error('confirmation_required',s.apply,p,confirmed_ticket='wrong');self.assertFalse(self.dest.exists())
        result=s.apply(p,confirmed_ticket=p['ticket']);self.assertEqual(result['outcome'],'snapshot_published_unverified_origin')
        self.assertEqual({p.relative_to(self.dest).as_posix():p.read_bytes() for p in self.dest.rglob('*') if p.is_file()},dict(rows))
        self.assertFalse((self.root/p['stage_name']).exists());self.error('ticket_unknown',s.apply,p,confirmed_ticket=p['ticket'])
    def test_wrong_signature_plan_tampering_and_input_drift(self):
        s=self.session();s.signature=bytes(64);self.error('archive_unverified',s.plan);self.assertFalse(self.dest.exists())
        s=self.session();p=s.plan();bad=copy.deepcopy(p);bad['files'][0]['sha256']='0'*64
        self.error('plan_mismatch',s.apply,bad,confirmed_ticket=p['ticket']);self.error('ticket_unknown',s.apply,p,confirmed_ticket=p['ticket'])
        s=self.session();p=s.plan();s.policy['revoked']=[self.f.key_id]
        self.error('stale_plan',s.apply,p,confirmed_ticket=p['ticket']);self.assertFalse(self.dest.exists())
        s=self.session();p=s.plan();s.archive_bytes+=b'changed'
        self.error('stale_plan',s.apply,p,confirmed_ticket=p['ticket']);self.assertFalse(self.dest.exists())
    def test_occupied_destination_and_parent_replaced(self):
        self.dest.mkdir();self.error('destination_occupied',self.session().plan);self.dest.rmdir()
        s=self.session();p=s.plan();self.dest.mkdir()
        self.error('destination_occupied',s.apply,p,confirmed_ticket=p['ticket']);self.assertEqual(list(self.dest.iterdir()),[])
        self.dest.rmdir();parent=self.root/'parent';parent.mkdir();s=self.session();s.destination=parent/'snapshot';p=s.plan()
        parent.rename(self.root/'old-parent');parent.mkdir()
        self.error('stale_parent',s.apply,p,confirmed_ticket=p['ticket']);self.assertFalse((parent/'snapshot').exists())
    def test_no_cleanup_after_failure_and_no_blind_replay(self):
        s=self.session();p=s.plan()
        with patch.object(publish.init,'_build',side_effect=OSError('synthetic')):
            self.error('stage_partial_or_unverified',s.apply,p,confirmed_ticket=p['ticket'])
        self.assertTrue((self.root/p['stage_name']).is_dir());self.assertFalse(self.dest.exists())
        self.error('ticket_unknown',s.apply,p,confirmed_ticket=p['ticket'])
        self.error('stage_pending',self.session().plan)
    def test_failure_after_rename_is_unknown_without_deleting_result(self):
        s=self.session();p=s.plan();real=atomic_init._rename_noreplace
        def rename_then_fail(*a,**kw):real(*a,**kw);raise OSError('synthetic after rename')
        with patch.object(publish.atomic,'_rename_noreplace',side_effect=rename_then_fail):
            self.error('publication_unknown',s.apply,p,confirmed_ticket=p['ticket'])
        self.assertTrue(self.dest.is_dir());self.assertFalse((self.root/p['stage_name']).exists())
        self.error('ticket_unknown',s.apply,p,confirmed_ticket=p['ticket'])
    def test_fsync_failures_before_and_after_rename(self):
        s=self.session();p=s.plan();stage=self.root/p['stage_name']
        with patch.object(publish.atomic,'_sync_verified_tree',side_effect=OSError('synthetic fsync')):
            self.error('stage_partial_or_unverified',s.apply,p,confirmed_ticket=p['ticket'])
        self.assertTrue(stage.is_dir());self.assertFalse(self.dest.exists())
        # Only this test's private temporary fixture is discarded before the next subcase.
        import shutil
        shutil.rmtree(stage)
        s=self.session();p=s.plan();realrename=atomic_init._rename_noreplace;realsync=publish.os.fsync;renamed=[]
        def rename(*args,**kwargs):realrename(*args,**kwargs);renamed.append(True)
        def sync(fd):
            if renamed:raise OSError('synthetic parent fsync')
            return realsync(fd)
        with patch.object(publish.atomic,'_rename_noreplace',side_effect=rename), patch.object(publish.os,'fsync',side_effect=sync):
            self.error('publication_unknown',s.apply,p,confirmed_ticket=p['ticket'])
        self.assertTrue(self.dest.is_dir());self.assertFalse((self.root/p['stage_name']).exists())
    def test_unverified_callback_and_staging_collision_no_overwrite(self):
        s=self.session();p=s.plan()
        with patch.object(archive,'capture',side_effect=archive.ArchiveError('synthetic')):
            self.error('archive_unverified',s.apply,p,confirmed_ticket=p['ticket'])
        self.assertFalse(self.dest.exists())
        s=self.session();p=s.plan();stage=self.root/p['stage_name'];stage.write_bytes(b'foreign')
        self.error('stage_pending',s.apply,p,confirmed_ticket=p['ticket'])
        self.assertEqual(stage.read_bytes(),b'foreign');self.assertFalse(self.dest.exists())

if __name__=='__main__':unittest.main()
