#!/usr/bin/env python3
"""Публикация нового каталога на синтетической локальной ФС; не тест потери питания."""
import copy
import errno
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'research/audit')]
import core_audit as audit
from kit import atomic_init as atomic
from kit.init_workspace import InitializationError
from kit.verify_candidate import CANDIDATE_VERSION
from kit.base.registry_store import Layout
from kit.guard import guard


try:
    atomic._rename_function();SUPPORTED=True
except InitializationError:
    SUPPORTED=False


@unittest.skipUnless(SUPPORTED,'Linux renameat2/dirfd API unavailable; not_run')
class AtomicInitTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory(prefix='domain-atomic-init-');self.addCleanup(t.cleanup)
        self.root=Path(t.name).resolve();self.dest=self.root/'workspace';self.marker=self.root/'sentinel'
        self.marker.write_bytes(b'preserve')
        self.l0=(json.dumps({'schema_version':2,'area':'L0','roots':['kit'],
                             'release_version':CANDIDATE_VERSION,'entries':[]},sort_keys=True)+'\n').encode()
        self.pin=hashlib.sha256(self.l0).hexdigest();self.session=self.new()
        # Проверить поддержку конкретной ФС до тестов, не трактуя неподдерживаемый режим как успех.
        a=self.root/'probe-a';a.mkdir();fd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY)
        try:
            try:atomic._rename_noreplace(fd,'probe-a','probe-b')
            except OSError as error:
                if error.errno in {errno.ENOSYS,errno.EINVAL,errno.ENOTSUP,errno.EOPNOTSUPP}:
                    self.skipTest('RENAME_NOREPLACE unsupported by filesystem; not_run')
                raise
        finally:os.close(fd)
        (self.root/'probe-b').rmdir()

    def new(self):return atomic.AtomicInitializationSession(self.dest,profile_root='profiles/pilot',
                                                             l0_bytes=self.l0,system_pin=self.pin)
    def stage(self,plan):return Path(plan['staging']['destination'])
    def error(self,code,fn,*args,**kwargs):
        with self.assertRaises(InitializationError) as e:fn(*args,**kwargs)
        self.assertEqual(str(e.exception),code)
    def apply(self,s,p):return s.apply(p,confirmed_ticket=p['ticket'])
    def assert_target_matches(self,plan):
        for row in plan['staging']['files']:
            self.assertEqual((self.dest/row['path']).read_bytes(),row['content_utf8'].encode())
        self.assertEqual(self.marker.read_bytes(),b'preserve')

    def test_plan_separate_confirm_publication_and_guard(self):
        plan=self.session.plan();self.assertFalse(self.dest.exists());self.assertFalse(self.stage(plan).exists())
        self.assertEqual(plan['publication'],'linux_rename_noreplace_after_verified_fsync')
        self.error('confirmation_required',self.session.apply,plan,confirmed_ticket='wrong')
        self.assertFalse(self.dest.exists());self.assertFalse(self.stage(plan).exists())
        self.assertEqual(self.apply(self.session,plan)['outcome'],'published_unverified_origin')
        self.assert_target_matches(plan);self.assertFalse(self.stage(plan).exists())
        manifest=(ROOT/'kit/KIT-VERSION.json').read_bytes()
        self.assertEqual(guard(ROOT,Layout(self.dest,'profiles/pilot'),
                               manifest_pin=hashlib.sha256(manifest).hexdigest(),system_pin=self.pin)['outcome'],'pass')
        self.error('ticket_unknown',self.apply,self.session,plan)
        self.error('destination_occupied',self.session.plan)

    def test_candidate_system_l0_atomic_then_context_modes(self):
        from kit.base import context_modes
        self.l0=(ROOT/'kit/SYSTEM-L0.json').read_bytes();self.pin=hashlib.sha256(self.l0).hexdigest()
        session=self.new();plan=session.plan()
        self.assertEqual(self.apply(session,plan)['outcome'],'published_unverified_origin')
        choices={'include':[],'exclude':[]};layout=Layout(self.dest,'profiles/pilot')
        for mode,expected in (('project','SYS-PROJECT-MODE'),('kit','SYS-KIT-MODE')):
            report=context_modes.prepare(layout,mode=mode,scope='docs/file',choices=choices)
            self.assertEqual(report['outcome'],'review_required')
            self.assertIn(expected,{row['entry']['id'] for row in report['entries']})
        self.assert_target_matches(plan)

    def test_changed_plan_input_and_parent_fail_without_staging(self):
        for change in ('plan','l0','target','parent'):
            with self.subTest(change=change):
                self.dest=self.root/('workspace-'+change);s=self.new();plan=s.plan();changed=copy.deepcopy(plan)
                if change=='plan':changed['staging']['files'][0]['content_utf8']+='x'
                if change=='l0':s.l0_bytes+=b' '
                if change=='target':s.destination=self.root/'elsewhere'
                if change=='parent':
                    # Меняем путь parent с сохранением старого inode на другом имени.
                    parent=self.root/'nested';parent.mkdir();self.dest=parent/'workspace';s=self.new();plan=s.plan();changed=plan
                    parent.rename(self.root/'old-parent');parent.mkdir()
                self.error({'plan':'plan_mismatch','l0':'stale_plan','target':'stale_plan','parent':'stale_parent'}[change],
                           s.apply,changed,confirmed_ticket=plan['ticket'])
                self.assertFalse(self.dest.exists());self.assertFalse(self.stage(plan).exists())
                self.assertEqual(self.marker.read_bytes(),b'preserve')

    def test_existing_and_racing_destination_never_overwritten(self):
        for kind in ('directory','file','symlink'):
            with self.subTest(kind=kind):
                self.dest=self.root/('target-'+kind);s=self.new();plan=s.plan()
                if kind=='directory':self.dest.mkdir();(self.dest/'keep').write_bytes(b'keep')
                elif kind=='file':self.dest.write_bytes(b'keep')
                else:self.dest.symlink_to(self.marker)
                self.error('destination_occupied',self.apply,s,plan)
                self.assertFalse(self.stage(plan).exists())
                self.assertEqual(self.marker.read_bytes(),b'preserve')
        self.dest=self.root/'racing';s=self.new();plan=s.plan();real=atomic._rename_noreplace
        def race(fd,old,new):
            os.mkdir(new,dir_fd=fd)
            return real(fd,old,new)  # Настоящий NOREPLACE на занятом каталоге.
        with patch.object(atomic,'_rename_noreplace',side_effect=race):
            self.error('publication_unknown',self.apply,s,plan)
        self.assertTrue(self.dest.is_dir());self.assertEqual(list(self.dest.iterdir()),[])
        self.assertTrue(self.stage(plan).is_dir());self.assertEqual(self.marker.read_bytes(),b'preserve')

    def test_every_fsync_failure_is_reported_and_never_claims_success(self):
        probe=self.session.plan();count=len(probe['staging']['directories'])+1+len(probe['staging']['files'])+2
        real=os.fsync
        for n in range(count):
            with self.subTest(fsync=n):
                self.dest=self.root/('sync-'+str(n));s=self.new();plan=s.plan();calls=[]
                def fail(fd):
                    calls.append(fd)
                    if len(calls)-1==n:raise OSError(errno.EIO,'synthetic fsync')
                    return real(fd)
                with patch.object(atomic.os,'fsync',side_effect=fail):
                    self.error('publication_unknown' if n==count-1 else 'staging_unverified',self.apply,s,plan)
                if n==count-1:
                    self.assert_target_matches(plan);self.assertFalse(self.stage(plan).exists())
                else:
                    self.assertFalse(self.dest.exists());self.assertTrue(self.stage(plan).exists())
                self.assertEqual(self.marker.read_bytes(),b'preserve')

    def test_extra_file_and_changed_staging_content_refuse_publication(self):
        real=atomic._sync_verified_tree
        for variant in ('extra','contents'):
            with self.subTest(variant=variant):
                self.dest=self.root/('stage-'+variant);s=self.new();plan=s.plan()
                def modify(root,files,uid,gid):
                    if variant=='extra':
                        f=os.open('unknown',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600,dir_fd=root);os.close(f)
                    else:
                        target=self.stage(plan)/'profiles/pilot/registry.json';target.write_bytes(b'changed')
                    return real(root,files,uid,gid)
                with patch.object(atomic,'_sync_verified_tree',side_effect=modify):
                    self.error('staging_unverified',self.apply,s,plan)
                self.assertFalse(self.dest.exists());self.assertTrue(self.stage(plan).exists())
                self.assertEqual(self.marker.read_bytes(),b'preserve')

    def test_platform_refusal_and_staging_failure(self):
        with patch.object(atomic,'_rename_function',side_effect=InitializationError('atomic_platform_unsupported')):
            self.error('atomic_platform_unsupported',self.session.plan)
        plan=self.session.plan()
        with patch.object(atomic.init,'_build',side_effect=OSError('synthetic')):
            self.error('staging_partial_or_unverified',self.apply,self.session,plan)
        self.assertFalse(self.dest.exists());self.assertTrue(self.stage(plan).exists())
        self.assertEqual(self.marker.read_bytes(),b'preserve')

    def test_two_concurrent_sessions_publish_at_most_once(self):
        s1,s2=self.new(),self.new();p1,p2=s1.plan(),s2.plan();barrier=threading.Barrier(2);results=[]
        def run(s,p):
            barrier.wait()
            try:results.append(self.apply(s,p)['outcome'])
            except InitializationError as error:results.append(str(error))
        threads=[threading.Thread(target=run,args=x) for x in ((s1,p1),(s2,p2))]
        for t in threads:t.start()
        for t in threads:t.join(timeout=15);self.assertFalse(t.is_alive())
        self.assertEqual(results.count('published_unverified_origin'),1)
        self.assertTrue(any(x in ('destination_occupied','publication_unknown') for x in results))
        self.assert_target_matches(p1)

    def test_abrupt_exit_at_each_staging_fsync_and_write(self):
        probe=self.session.plan();sync_count=len(probe['staging']['directories'])+1+len(probe['staging']['files'])+2
        program=r'''import hashlib,json,os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1]);from kit import atomic_init as a
raw=bytes.fromhex(sys.argv[3]);s=a.AtomicInitializationSession(Path(sys.argv[2]),profile_root='profiles/pilot',l0_bytes=raw,system_pin=hashlib.sha256(raw).hexdigest())
p=s.plan();print(json.dumps(p),flush=True)
kind=sys.argv[4];point=int(sys.argv[5]);real=getattr(os,kind);count=[0]
def stop(*args,**kw):
 i=count[0];count[0]+=1
 if i==point:
  if kind=='write':real(args[0],args[1][:len(args[1])//2])
  os._exit(77)
 return real(*args,**kw)
a.init._supported=lambda:True
setattr(os,kind,stop)
s.apply(p,confirmed_ticket=p['ticket']);os._exit(3)
'''
        for kind,count in (('mkdir',1+len(probe['staging']['directories'])),
                           ('write',len(probe['staging']['files'])),('fsync',sync_count)):
            for n in range(count):
                with self.subTest(kind=kind,point=n):
                    self.dest=self.root/f'kill-{kind}-{n}'
                    proc=subprocess.run([sys.executable,'-I','-S','-B','-c',program,str(ROOT),str(self.dest),
                                         self.l0.hex(),kind,str(n)],capture_output=True,text=True,timeout=15)
                    self.assertEqual(proc.returncode,77,proc.stderr);plan=json.loads(proc.stdout)
                    if kind=='fsync' and n==sync_count-1:
                        self.assert_target_matches(plan);self.assertFalse(self.stage(plan).exists())
                    else:
                        self.assertFalse(self.dest.exists())
                        self.assertEqual(self.stage(plan).exists(),not (kind=='mkdir' and n==0))
                    self.assertEqual(self.marker.read_bytes(),b'preserve')

    def test_process_exit_before_and_after_rename(self):
        program=r'''import hashlib,json,os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from kit import atomic_init as a
raw=bytes.fromhex(sys.argv[3]);s=a.AtomicInitializationSession(Path(sys.argv[2]),profile_root='profiles/pilot',l0_bytes=raw,system_pin=hashlib.sha256(raw).hexdigest())
p=s.plan();print(json.dumps(p),flush=True)
real=a._rename_noreplace
if sys.argv[4]=='before':a._rename_noreplace=lambda *args:os._exit(77)
else:
 def stop(*args):real(*args);os._exit(77)
 a._rename_noreplace=stop
s.apply(p,confirmed_ticket=p['ticket']);os._exit(3)
'''
        for phase in ('before','after'):
            with self.subTest(phase=phase):
                self.dest=self.root/('abrupt-'+phase)
                proc=subprocess.run([sys.executable,'-I','-S','-B','-c',program,str(ROOT),str(self.dest),self.l0.hex(),phase],
                                    capture_output=True,text=True,timeout=15)
                self.assertEqual(proc.returncode,77,proc.stderr);plan=json.loads(proc.stdout)
                if phase=='before':self.assertFalse(self.dest.exists());self.assertTrue(self.stage(plan).exists())
                else:self.assert_target_matches(plan);self.assertFalse(self.stage(plan).exists())
                self.assertEqual(self.marker.read_bytes(),b'preserve')


if __name__=='__main__':unittest.main()
