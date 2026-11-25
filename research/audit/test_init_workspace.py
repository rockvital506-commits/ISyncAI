#!/usr/bin/env python3
"""Только новые синтетические деревья: опытный D04 API не подтверждает источник."""
import copy
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'research/audit')]
import core_audit as audit
from kit import init_workspace as init
from kit.base import registry_store
from kit.base.operation_card import compile_prompt
from kit.base.operation_plan import PlanSession
from kit.guard import guard
from kit.verify_candidate import CANDIDATE_VERSION


@unittest.skipUnless(init._supported(), 'POSIX descriptor API unavailable; not_run')
class InitializationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='domain-init-api-'); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve(); self.parent = self.root/'parent'; self.parent.mkdir(mode=0o700)
        self.dest = self.parent/'workspace'; self.marker=self.parent/'sentinel';self.marker.write_bytes(b'untouched')
        self.l0 = (json.dumps({'schema_version':2,'area':'L0','roots':['kit'],
                              'release_version':CANDIDATE_VERSION,'entries':[]},sort_keys=True)+'\n').encode()
        self.pin = hashlib.sha256(self.l0).hexdigest()
        self.session=self.make_session()

    def make_session(self):
        return init.InitializationSession(self.dest,profile_root='profiles/pilot',l0_bytes=self.l0,system_pin=self.pin)

    def error(self, code, function, *args, **kwargs):
        with self.assertRaises(init.InitializationError) as error:function(*args,**kwargs)
        self.assertEqual(str(error.exception),code)

    def test_plan_confirmation_and_registry_session(self):
        plan=self.session.plan();self.assertFalse(self.dest.exists())
        self.assertEqual(plan['publication'],'non_atomic_partial_on_failure')
        self.assertEqual((plan['origin'],plan['l0_semantics']),('not_verified','not_checked'))
        self.assertEqual((plan['directory_mode'],plan['file_mode']),('0700','0600'))
        for row in plan['files']:
            raw=row['content_utf8'].encode();self.assertEqual(len(raw),row['bytes'])
            self.assertEqual(hashlib.sha256(raw).hexdigest(),row['sha256'])
        for wrong in ('','ошибка', '0'*64):self.error('confirmation_required',self.session.apply,plan,confirmed_ticket=wrong)
        self.assertFalse(self.dest.exists())
        self.assertEqual(self.session.apply(plan,confirmed_ticket=plan['ticket'])['outcome'],'created_unverified_origin')
        self.assertEqual(self.marker.read_bytes(),b'untouched')
        for row in plan['files']:
            p=self.dest/row['path'];self.assertEqual(p.read_bytes(),row['content_utf8'].encode())
            self.assertEqual(stat.S_IMODE(p.stat().st_mode),0o600)
            self.assertEqual((p.stat().st_uid,p.stat().st_gid),(plan['uid'],plan['gid']))
        for d in (self.dest,*[self.dest/p for p in plan['directories']]):
            self.assertEqual(stat.S_IMODE(d.stat().st_mode),0o700)
        manifest=(ROOT/'kit/KIT-VERSION.json').read_bytes()
        self.assertEqual(guard(ROOT,registry_store.Layout(self.dest,'profiles/pilot'),
                         manifest_pin=hashlib.sha256(manifest).hexdigest(),system_pin=self.pin)['outcome'],'pass')
        self.error('ticket_unknown',self.session.apply,plan,confirmed_ticket=plan['ticket'])
        self.error('destination_occupied',self.session.plan)
        before={row['path']:(self.dest/row['path']).read_bytes() for row in plan['files']}
        action=PlanSession(registry_store.Layout(self.dest,'profiles/pilot'),profile_id='Pilot')
        prompt=('Создай черновик контракта X-9 в профиле Pilot, постоянное, область «docs», '
                'название «Пример», основание «Проба», критерий «Запись существует»: Синтетический текст.')
        change=action.plan(compile_prompt(prompt))
        self.assertEqual(action.apply(change,confirmed_ticket=change['ticket'])['outcome'],'applied')
        for path,raw in before.items():
            if path!='profiles/pilot/registry.json':self.assertEqual((self.dest/path).read_bytes(),raw)

    def test_plan_edit_and_input_drift_revoke(self):
        for drift in ('plan','raw','pin','profile','destination'):
            with self.subTest(drift=drift):
                s=self.make_session();plan=s.plan();changed=copy.deepcopy(plan)
                if drift=='plan':changed['files'][0]['content_utf8']+='x'
                if drift=='raw':s.l0_bytes+=b' '
                if drift=='pin':s.system_pin='0'*64
                if drift=='profile':s.profile_root='profiles/other'
                if drift=='destination':s.destination=self.parent/'another'
                self.error('plan_mismatch' if drift=='plan' else 'stale_plan',s.apply,changed,confirmed_ticket=plan['ticket'])
                self.error('ticket_unknown',s.apply,plan,confirmed_ticket=plan['ticket'])
                self.assertFalse(self.dest.exists());self.assertEqual(self.marker.read_bytes(),b'untouched')

    def test_invalid_inputs_and_symlink_or_occupied_parent(self):
        for profile in ('kit', '.domain-agent-kit/project','../profile', 'profiles/CON',None):
            with self.subTest(profile=profile):
                s=self.make_session();s.profile_root=profile;self.error('catalog_invalid',s.plan)
        s=self.make_session();s.system_pin='0'*64;self.error('system_pin_mismatch',s.plan)
        s=self.make_session();s.l0_bytes=b'not json';s.system_pin=hashlib.sha256(s.l0_bytes).hexdigest()
        self.error('catalog_invalid',s.plan)
        self.dest.symlink_to(self.marker);self.error('destination_occupied',self.session.plan)
        self.dest.unlink();link=self.root/'alias';link.symlink_to(self.parent,target_is_directory=True)
        self.session.destination=link/'workspace';self.error('parent_unavailable',self.session.plan)
        self.assertEqual(self.marker.read_bytes(),b'untouched')

    def test_parent_identity_drift_refuses_before_reservation(self):
        plan=self.session.plan();old=self.root/'old';self.parent.rename(old);self.parent.mkdir()
        self.error('stale_parent',self.session.apply,plan,confirmed_ticket=plan['ticket'])
        self.assertFalse(self.dest.exists());self.assertEqual((old/'sentinel').read_bytes(),b'untouched')

    def test_two_sessions_same_destination_do_not_overwrite(self):
        other=self.make_session();a,b=self.session.plan(),other.plan()
        self.session.apply(a,confirmed_ticket=a['ticket']);before=audit.tree_digest(self.dest)
        self.error('destination_occupied',other.apply,b,confirmed_ticket=b['ticket'])
        self.assertEqual(audit.tree_digest(self.dest),before)

    def test_faults_each_mkdir_and_each_write_leave_partial_without_cleanup(self):
        baseline=self.session.plan();count=1+len(baseline['directories']);real_mkdir=os.mkdir;real_write=os.write
        for kind, positions in (('mkdir',range(count)),('write',range(len(baseline['files'])))):
            for position in positions:
                with self.subTest(kind=kind,position=position):
                    self.dest=self.parent/f'{kind}-{position}';s=self.make_session();plan=s.plan();calls=[]
                    def fail_mkdir(*args,**kwargs):
                        calls.append(args)
                        if len(calls)-1==position:raise OSError('synthetic mkdir failure')
                        return real_mkdir(*args,**kwargs)
                    def fail_write(*args,**kwargs):
                        calls.append(args)
                        if len(calls)-1==position:raise OSError('synthetic write failure')
                        return real_write(*args,**kwargs)
                    mock=patch.object(init.os,kind,side_effect=fail_mkdir if kind=='mkdir' else fail_write)
                    with patch.object(init,'_supported',return_value=True), mock:
                        self.error('destination_unavailable' if kind=='mkdir' and position==0 else
                                   'destination_partial_or_unverified',s.apply,plan,confirmed_ticket=plan['ticket'])
                    self.assertEqual(self.marker.read_bytes(),b'untouched')
                    if kind=='mkdir' and position==0:self.assertFalse(self.dest.exists())
                    else:
                        self.assertTrue(self.dest.exists());before=audit.tree_digest(self.dest)
                        self.error('destination_occupied',s.plan);self.assertEqual(audit.tree_digest(self.dest),before)

    def test_abrupt_process_exit_each_directory_and_file(self):
        template=self.session.plan()
        program=r'''import hashlib,json,os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from kit import init_workspace as m
raw=bytes.fromhex(sys.argv[3]);s=m.InitializationSession(Path(sys.argv[2]),profile_root='profiles/pilot',l0_bytes=raw,system_pin=hashlib.sha256(raw).hexdigest())
p=s.plan();kind=sys.argv[4];point=int(sys.argv[5]);calls=[0]
real_mkdir=os.mkdir;real_write=os.write
m._supported=lambda:True
def mkdir(*a,**kw):
 result=real_mkdir(*a,**kw);i=calls[0];calls[0]+=1
 if kind=='mkdir' and i==point:os._exit(77)
 return result
def write(fd,data):
 i=calls[0];calls[0]+=1
 if kind=='write' and i==point:
  real_write(fd,data[:len(data)//2]);os._exit(77)
 return real_write(fd,data)
if kind=='mkdir':os.mkdir=mkdir
else:os.write=write
s.apply(p,confirmed_ticket=p['ticket'])
os._exit(3)
'''
        for kind, n in (('mkdir',1+len(template['directories'])),('write',len(template['files']))):
            for position in range(n):
                with self.subTest(kind=kind,position=position):
                    target=self.parent/f'abrupt-{kind}-{position}'
                    proc=subprocess.run([sys.executable,'-I','-S','-B','-c',program,str(ROOT),str(target),
                                         self.l0.hex(),kind,str(position)],capture_output=True,text=True,timeout=15)
                    self.assertEqual(proc.returncode,77,proc.stderr);self.assertTrue(target.exists())
                    before=audit.tree_digest(target)
                    s=init.InitializationSession(target,profile_root='profiles/pilot',l0_bytes=self.l0,system_pin=self.pin)
                    self.error('destination_occupied',s.plan);self.assertEqual(audit.tree_digest(target),before)
                    self.assertEqual(self.marker.read_bytes(),b'untouched')

    def test_two_threads_compete_for_same_name(self):
        a=self.make_session();b=self.make_session();plans=(a.plan(),b.plan());barrier=threading.Barrier(2);results=[]
        def run(session,plan):
            barrier.wait()
            try:results.append(session.apply(plan,confirmed_ticket=plan['ticket'])['outcome'])
            except init.InitializationError as error:results.append(str(error))
        threads=[threading.Thread(target=run,args=(s,p)) for s,p in zip((a,b),plans)]
        for thread in threads:thread.start()
        for thread in threads:thread.join(timeout=10);self.assertFalse(thread.is_alive())
        self.assertCountEqual(results,['created_unverified_origin','destination_occupied'])
        self.assertEqual(self.marker.read_bytes(),b'untouched')

    def test_platform_unavailable_prevents_any_reservation(self):
        with patch.object(init,'_supported',return_value=False):
            self.error('platform_unsupported',self.session.plan)
        self.assertFalse(self.dest.exists());self.assertEqual(self.marker.read_bytes(),b'untouched')

    def test_permissions_and_xattrs_fail_closed(self):
        for kind in ('mode','xattrs','xattrs_unavailable'):
            with self.subTest(kind=kind):
                self.dest=self.parent/f'failure-{kind}';session=self.make_session();plan=session.plan()
                if kind=='mode':
                    old_mask=os.umask(0o777)
                    try:self.error('destination_partial_or_unverified',session.apply,plan,confirmed_ticket=plan['ticket'])
                    finally:os.umask(old_mask)
                else:
                    value=['user.synthetic'] if kind=='xattrs' else OSError('synthetic')
                    kwargs=({'return_value':value} if kind=='xattrs' else {'side_effect':value})
                    with patch.object(init.os,'listxattr',**kwargs):
                        self.error('destination_partial_or_unverified',session.apply,plan,confirmed_ticket=plan['ticket'])
                self.assertTrue(self.dest.is_dir())
                if kind!='mode':self.assertEqual(list(self.dest.iterdir()),[])
                else:self.dest.chmod(0o700)  # Только для очистки нашего тестового дерева.
                self.assertEqual(self.marker.read_bytes(),b'untouched')

    def test_busy_does_not_mutate_pending(self):
        plan=self.session.plan();self.session._lock.acquire()
        try:
            self.error('session_busy',self.session.plan)
            self.error('session_busy',self.session.apply,plan,confirmed_ticket=plan['ticket'])
        finally:self.session._lock.release()
        self.assertEqual(self.session.apply(plan,confirmed_ticket=plan['ticket'])['outcome'],'created_unverified_origin')


if __name__=='__main__':unittest.main()
