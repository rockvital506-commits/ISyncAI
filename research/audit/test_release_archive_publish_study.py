#!/usr/bin/env python3
"""Публикация в синтетические временные каталоги, не выпуск или установка."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
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
import test_source_release_trust as signing
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
    def test_missing_lock_support_is_fail_closed(self):
        s=self.session()
        with patch.object(publish,'fcntl',None):self.error('publication_lock_unavailable',s.plan)
        p=s.plan()
        with patch.object(publish,'fcntl',None):self.error('publication_lock_unavailable',s.apply,p,confirmed_ticket=p['ticket'])
        self.assertFalse(self.dest.exists());self.assertFalse((self.root/p['stage_name']).exists())
        self.error('ticket_unknown',s.apply,p,confirmed_ticket=p['ticket'])
    def test_other_process_holds_parent_lock_refuses_before_write(self):
        s=self.session();p=s.plan()
        code=('import os,fcntl,sys; '
              'fd=os.open(sys.argv[1],os.O_RDONLY|os.O_DIRECTORY); '
              'fcntl.flock(fd,fcntl.LOCK_EX); print("locked",flush=True); '
              'sys.stdin.readline(); os.close(fd)')
        proc=subprocess.Popen([sys.executable,'-I','-S','-B','-c',code,str(self.root)],
                              stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            self.assertEqual(proc.stdout.readline().strip(),'locked')
            self.error('publication_busy',s.apply,p,confirmed_ticket=p['ticket'])
            self.assertFalse(self.dest.exists());self.assertFalse((self.root/p['stage_name']).exists())
            self.error('ticket_unknown',s.apply,p,confirmed_ticket=p['ticket'])
        finally:
            proc.stdin.write('\n');proc.stdin.flush();proc.communicate(timeout=10)
        s=self.session();p=s.plan();self.assertEqual(s.apply(p,confirmed_ticket=p['ticket'])['outcome'],'snapshot_published_unverified_origin')
    def test_process_exit_around_rename_leaves_observable_state(self):
        # os._exit is a process crash simulation, not a power-loss test.
        wire=copy.deepcopy(self.f.policy);wire['keys']={k:v.hex() for k,v in wire['keys'].items()}
        archive_path=self.root/'release.zip';archive_path.write_bytes(self.bytes)
        statement_path=self.root/'statement';statement_path.write_bytes(self.statement)
        policy_path=self.root/'policy';policy_path.write_text(json.dumps(wire))
        provider_pin=hashlib.sha256(signing.OPENSSL.read_bytes()).hexdigest()
        code=r'''import json,os,sys
from pathlib import Path
sys.path[:0]=[sys.argv[1],str(Path(sys.argv[1])/'research/audit')]
import release_archive_publish_study as p, release_ed25519_study as crypto
from kit import atomic_init
root=Path(sys.argv[2]);pol=json.loads((root/'policy').read_text());pol['keys']={k:bytes.fromhex(v) for k,v in pol['keys'].items()}
def verify(key,msg,sig):return crypto.verify(key,msg,sig,executable=Path(sys.argv[5]),executable_pin=sys.argv[6])
s=p.PublishSession(root/sys.argv[3]/'destination',archive_bytes=(root/'release.zip').read_bytes(),statement=(root/'statement').read_bytes(),signature=bytes.fromhex(sys.argv[4]),policy=pol,verify_signature=verify)
plan=s.plan();real=atomic_init._rename_noreplace
def stop(*a,**kw):
 if sys.argv[7]=='before':os._exit(77)
 real(*a,**kw);os._exit(77)
atomic_init._rename_noreplace=stop;s.apply(plan,confirmed_ticket=plan['ticket']);os._exit(9)
'''
        for point in ('before','after'):
            with self.subTest(point=point):
                folder=self.root/point;folder.mkdir()
                proc=subprocess.run([sys.executable,'-I','-S','-B','-c',code,str(ROOT),str(self.root),point,
                                     self.sig.hex(),str(signing.OPENSSL),provider_pin,point],capture_output=True,text=True,timeout=20)
                self.assertEqual(proc.returncode,77,proc.stderr)
                stages=list(folder.glob('.domain-release-stage-*'));dest=folder/'destination'
                self.assertEqual(len(stages),1 if point=='before' else 0)
                self.assertEqual(dest.exists(),point=='after')
                if dest.exists():self.assertEqual((dest/'kit/KIT-VERSION.json').read_bytes(),self.f.manifest)
    def test_post_rename_directory_substitution_or_file_mutation_is_unknown(self):
        real=atomic_init._rename_noreplace
        for kind in ('replace_directory','alter_file'):
            with self.subTest(kind=kind):
                dest=self.root/kind;s=self.session();s.destination=dest;p=s.plan()
                def tamper(*args,**kwargs):
                    real(*args,**kwargs)
                    if kind=='replace_directory':
                        dest.rename(self.root/'retained');dest.mkdir()
                    else:
                        target=dest/'kit/IDENTITY.md';target.write_bytes(target.read_bytes()+b'changed')
                with patch.object(publish.atomic,'_rename_noreplace',side_effect=tamper):
                    self.error('publication_unknown',s.apply,p,confirmed_ticket=p['ticket'])
                self.assertTrue(dest.exists())
                self.assertFalse((self.root/p['stage_name']).exists())
                if kind=='replace_directory':self.assertTrue((self.root/'retained/kit/KIT-VERSION.json').is_file())
                else:self.assertTrue((dest/'kit/IDENTITY.md').read_bytes().endswith(b'changed'))
    def test_unverified_callback_and_staging_collision_no_overwrite(self):
        s=self.session();p=s.plan()
        with patch.object(archive,'capture',side_effect=archive.ArchiveError('synthetic')):
            self.error('archive_unverified',s.apply,p,confirmed_ticket=p['ticket'])
        self.assertFalse(self.dest.exists())
        s=self.session();p=s.plan();stage=self.root/p['stage_name'];stage.write_bytes(b'foreign')
        self.error('stage_pending',s.apply,p,confirmed_ticket=p['ticket'])
        self.assertEqual(stage.read_bytes(),b'foreign');self.assertFalse(self.dest.exists())

if __name__=='__main__':unittest.main()
