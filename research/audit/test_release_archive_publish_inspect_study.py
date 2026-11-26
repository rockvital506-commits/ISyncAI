#!/usr/bin/env python3
"""Осмотр после неопределённой публикации, только синтетические деревья."""
import copy
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'research/audit')]
import core_audit as audit
import release_archive_publish_study as publish
import release_archive_study as archive
import release_policy_study as policy
import test_atomic_init as atomic_test
import test_release_policy_study as fixture
import test_source_release_trust as signing


@unittest.skipUnless(signing.SUPPORTED and atomic_test.SUPPORTED,'OpenSSL/Linux unavailable; not_run')
class PublishInspectTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.ReleasePolicyStudyTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.tmp=tempfile.TemporaryDirectory(prefix='publish-inspect-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.dest=self.root/'snapshot'
        self.raw=archive.build(self.f.manifest,self.f.files);self.statement=policy.canonical(self.f.doc);self.sig=self.f.sign()
    def session(self):return publish.PublishSession(self.dest,archive_bytes=self.raw,statement=self.statement,
                         signature=self.sig,policy=self.f.policy,verify_signature=self.f.fx.verify)
    def error(self,code,fn,*args,**kwargs):
        with self.assertRaises(publish.PublishError) as error:fn(*args,**kwargs)
        self.assertEqual(str(error.exception),code)
    def observe(self,s,name):
        before=audit.tree_digest(self.root);result=s.inspect(stage_name=name)
        self.assertEqual(before,audit.tree_digest(self.root));self.assertEqual(result['completion'],'not_verified')
        self.assertEqual(result['recovery'],'not_performed');return result
    def test_absent_partial_full_target_and_full_stage(self):
        s=self.session();p=s.plan();name=p['stage_name'];r=self.observe(s,name)
        self.assertEqual((r['destination_state'],r['stage_state']),('absent','absent'))
        self.error('ticket_unknown',s.apply,p,confirmed_ticket=p['ticket'])
        stage=self.root/name;stage.mkdir(mode=0o700);(stage/'foreign').write_bytes(b'test')
        r=self.observe(self.session(),name);self.assertEqual(r['stage_state'],'different')
        shutil.rmtree(stage)  # Только синтетическая фикстура этого теста.
        s=self.session();p=s.plan();s.apply(p,confirmed_ticket=p['ticket'])
        r=self.observe(self.session(),p['stage_name'])
        self.assertEqual((r['destination_state'],r['stage_state']),('matches_observation','absent'))
        stage=self.root/p['stage_name'];shutil.copytree(self.dest,stage)
        r=self.observe(self.session(),stage.name)
        self.assertEqual((r['destination_state'],r['stage_state']),('matches_observation','matches_observation'))
    def test_invalid_name_symlink_and_bad_signature(self):
        s=self.session();p=s.plan()
        for bad in ('../snapshot','.domain-release-stage-X'*3,'.domain-release-stage-'+'a'*31):
            self.error('inspection_invalid',s.inspect,stage_name=bad)
        stage=self.root/p['stage_name'];stage.symlink_to(self.root/'missing',target_is_directory=True)
        result=self.observe(self.session(),stage.name);self.assertEqual(result['stage_state'],'different')
        stage.unlink();s=self.session();s.signature=bytes(64)
        self.error('archive_unverified',s.inspect,stage_name=p['stage_name'])
        self.assertFalse(self.dest.exists())
    def test_changed_file_reported_different_without_repair(self):
        s=self.session();p=s.plan();s.apply(p,confirmed_ticket=p['ticket'])
        target=self.dest/'kit/IDENTITY.md';target.write_bytes(target.read_bytes()+b'tamper')
        r=self.observe(self.session(),p['stage_name']);self.assertEqual(r['destination_state'],'different')
        self.assertTrue(target.read_bytes().endswith(b'tamper'))

if __name__=='__main__':unittest.main()
