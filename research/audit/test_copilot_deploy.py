#!/usr/bin/env python3
"""Публикация только в синтетические деревья; реальный Copilot не запускался."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'research/audit')]
import core_audit as audit
from kit import copilot_deploy as deploy, init_workspace as init
from kit.base import registry_store as store
from kit.base.registry_policy import StoreError

@unittest.skipUnless(init._supported() and store.fcntl is not None and os.link in os.supports_dir_fd and os.link in os.supports_follow_symlinks,'POSIX unavailable; not_run')
class CopilotTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='copilot-deploy-');self.addCleanup(temp.cleanup)
        self.root=Path(temp.name).resolve();self.layout=audit.make_workspace(self.root,parent_scope='.')
        self.files={'L0':self.root/'kit/base/registry.json','L1':self.root/'profiles/pilot/registry.json',
                    'L2':self.root/'.domain-agent-kit/project/registry.json'}
        for area,parent,auth in (('L1','C-1','profile_owner'),('L2','P-1','project_owner')):
            doc=json.loads(self.files[area].read_bytes())
            doc['entries'] += [audit.entry('GLOBAL','rule',auth,parent,'.',text='SYNTHETIC_GLOBAL'),
                               audit.entry('NARROW','rule',auth,parent,'docs',text='SYNTHETIC_NARROW')]
            audit.write(self.files[area],doc)
        self.before={a:p.read_bytes() for a,p in self.files.items()};self.dest=self.root/'.github/instructions';self.dest.mkdir(parents=True)
        self.neighbor=self.dest/'owner.instructions.md';self.neighbor.write_bytes(b'owner unchanged')
    def session(self):return deploy.CopilotDeploymentSession(self.layout)
    def plan(self,s,area='L1',entry_id='GLOBAL'):return s.plan(area=area,entry_id=entry_id)
    def apply(self,s,p):return s.apply(p,confirmed_ticket=p['ticket'])
    def error(self,code,fn,*args,**kwargs):
        with self.assertRaises(StoreError) as e:fn(*args,**kwargs)
        self.assertEqual(e.exception.code,code)
    def unchanged(self):
        self.assertEqual({a:p.read_bytes() for a,p in self.files.items()},self.before);self.assertEqual(self.neighbor.read_bytes(),b'owner unchanged')
    def test_both_areas_exact_bytes_confirmation_and_no_overwrite(self):
        for area in ('L1','L2'):
            with self.subTest(area=area):
                s=self.session();p=self.plan(s,area);target=self.root/p['target'];stage=self.root/p['staging_target']
                self.assertFalse(target.exists());self.assertFalse(stage.exists());self.assertTrue(p['content_utf8'].startswith('---\napplyTo: "**"\n---\n'))
                self.assertIn('SYNTHETIC_GLOBAL',p['content_utf8']);self.assertNotIn('SYNTHETIC_NARROW',p['content_utf8'])
                self.error('confirmation_required',s.apply,p,confirmed_ticket='wrong');self.assertFalse(target.exists())
                result=self.apply(s,p);self.assertEqual(result['outcome'],'instruction_file_created')
                self.assertEqual(target.read_text(),p['content_utf8']);self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(),p['content_sha256'])
                self.assertEqual(target.stat().st_mode&0o777,0o600);self.assertFalse(stage.exists());self.assertEqual(result['copilot_read'],'not_run');self.assertEqual(result['copilot_applied'],'not_run')
                self.error('copilot_target_occupied',self.plan,self.session(),area);self.unchanged()
    def test_inspection_missing_matched_different_unsafe_and_changed_source(self):
        self.assertEqual(deploy.inspect(self.layout,area='L1',entry_id='GLOBAL')['outcome'],'missing')
        s=self.session();p=self.plan(s);self.apply(s,p);target=self.root/p['target']
        result=deploy.inspect(self.layout,area='L1',entry_id='GLOBAL');self.assertEqual(result['outcome'],'matched')
        self.assertEqual(result['copilot_read'],'not_run');self.assertEqual(result['copilot_applied'],'not_run')
        target.write_bytes(b'changed');self.assertEqual(deploy.inspect(self.layout,area='L1',entry_id='GLOBAL')['outcome'],'different')
        target.unlink();target.symlink_to(self.neighbor);self.error('copilot_inspection_unavailable',deploy.inspect,self.layout,area='L1',entry_id='GLOBAL')
        target.unlink();target.write_text(p['content_utf8']);doc=json.loads(self.files['L1'].read_bytes());doc['entries'][-2]['text']='changed';audit.write(self.files['L1'],doc)
        self.assertEqual(deploy.inspect(self.layout,area='L1',entry_id='GLOBAL')['outcome'],'different');self.assertEqual(self.neighbor.read_bytes(),b'owner unchanged')
    def test_narrow_draft_absent_and_invalid_area_refuse(self):
        s=self.session();self.error('copilot_render_failed',self.plan,s,'L1','NARROW')
        self.error('copilot_render_failed',self.plan,s,'L1','MISSING');self.error('copilot_target_invalid',self.plan,s,'L0','GLOBAL')
        self.error('copilot_target_invalid',self.plan,s,'L1','../evil');self.unchanged()
        doc=json.loads(self.files['L1'].read_bytes());doc['entries'][-2]['state']='draft';audit.write(self.files['L1'],doc)
        self.error('copilot_render_failed',self.plan,s,'L1','GLOBAL')
        self.assertEqual(self.neighbor.read_bytes(),b'owner unchanged')
    def test_stale_plan_replaced_directory_and_target_race(self):
        s=self.session();p=self.plan(s);bad=copy.deepcopy(p);bad['content_utf8']+='bad'
        self.error('plan_mismatch',s.apply,bad,confirmed_ticket=p['ticket']);self.error('ticket_unknown',self.apply,s,p)
        s=self.session();p=self.plan(s);self.files['L0'].write_bytes(self.before['L0']+b' ')
        self.error('stale_plan',self.apply,s,p);self.files['L0'].write_bytes(self.before['L0'])
        s=self.session();p=self.plan(s);target=self.root/p['target'];target.write_bytes(b'owner')
        self.error('copilot_target_occupied',self.apply,s,p);self.assertEqual(target.read_bytes(),b'owner');target.unlink()
        s=self.session();p=self.plan(s);self.dest.rename(self.root/'.github/old');self.dest.mkdir()
        self.error('stale_plan',self.apply,s,p);self.assertFalse((self.root/p['target']).exists())
    def test_link_and_directory_symlinks_refused(self):
        s=self.session();p=self.plan(s);target=self.root/p['target'];target.symlink_to(self.neighbor)
        self.error('copilot_target_occupied',self.apply,s,p);self.assertEqual(self.neighbor.read_bytes(),b'owner unchanged');target.unlink()
        self.dest.rename(self.root/'.github/original');self.dest.symlink_to(self.root/'.github/original',target_is_directory=True)
        self.error('copilot_directory_unavailable',self.plan,self.session())
    def test_root_overlap_pending_and_competing_lock(self):
        s=self.session();p=self.plan(s);marker=self.root/'.domain-agent-kit/.move-pending';marker.write_bytes(b'unknown')
        self.error('move_pending',self.apply,s,p);self.assertFalse((self.root/p['target']).exists());marker.unlink()
        s=self.session();p=self.plan(s);fd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY)
        try:
            store.fcntl.flock(fd,store.fcntl.LOCK_EX|store.fcntl.LOCK_NB);self.error('copilot_busy',self.apply,s,p)
        finally:os.close(fd)
        self.assertFalse((self.root/p['target']).exists())
        doc=json.loads(self.files['L1'].read_bytes());doc['roots']=['.github']
        audit.write(self.root/'.github/registry.json',doc);overlap=deploy.CopilotDeploymentSession(store.Layout(self.root,'.github'))
        self.error('copilot_root_overlap',self.plan,overlap)
    def test_uncooperative_source_change_and_target_race_never_overwrite(self):
        for kind in ('source','target'):
            with self.subTest(kind=kind):
                s=self.session();p=self.plan(s);target=self.root/p['target'];stage=self.root/p['staging_target'];real=os.write
                def race(fd,data):
                    n=real(fd,data)
                    if kind=='source':self.files['L0'].write_bytes(self.before['L0']+b' ')
                    else:target.write_bytes(b'owner-race')
                    return n
                with patch.object(deploy.os,'write',side_effect=race):self.error('copilot_publication_unknown',self.apply,s,p)
                self.assertTrue(stage.exists())
                if kind=='source':self.assertFalse(target.exists());self.files['L0'].write_bytes(self.before['L0'])
                else:self.assertEqual(target.read_bytes(),b'owner-race');target.unlink()
                stage.unlink();self.unchanged()
    def test_write_link_unlink_and_fsync_failures_leave_unknown(self):
        for kind in ('write','link','unlink','file_sync','dir_sync','xattr'):
            with self.subTest(kind=kind):
                s=self.session();p=self.plan(s);target=self.root/p['target'];stage=self.root/p['staging_target'];real=os.fsync;calls=[]
                if kind in ('write','link','unlink'):mock=patch.object(deploy.os,kind,side_effect=OSError('synthetic'))
                elif kind=='xattr':mock=patch.object(init.os,'listxattr',return_value=['user.synthetic'])
                else:
                    def sync(fd):
                        calls.append(fd)
                        if len(calls)==(1 if kind=='file_sync' else 2):raise OSError('synthetic')
                        return real(fd)
                    mock=patch.object(deploy.os,'fsync',side_effect=sync)
                with mock as patched:
                    if kind in ('link','unlink'):os.supports_dir_fd.add(patched)
                    if kind=='link':os.supports_follow_symlinks.add(patched)
                    try:self.error('copilot_publication_unknown',self.apply,s,p)
                    finally:
                        if kind in ('link','unlink'):os.supports_dir_fd.discard(patched)
                        if kind=='link':os.supports_follow_symlinks.discard(patched)
                self.assertTrue(stage.exists() or target.exists());self.unchanged()
                # Удаляем исключительно объекты своей синтетической фикстуры между вариантами.
                if stage.exists():stage.unlink()
                if target.exists():target.unlink()
    def test_os_exit_after_stage_fsync_link_and_unlink(self):
        program=r'''import os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1]);from kit import copilot_deploy as m
from kit.base.registry_store import Layout
s=m.CopilotDeploymentSession(Layout(Path(sys.argv[2]),'profiles/pilot'));p=s.plan(area='L1',entry_id='GLOBAL');print(p['target']+' '+p['staging_target'],flush=True)
kind=sys.argv[3]
if kind=='sync':
 real=os.fsync
 def stop(fd):real(fd);os._exit(77)
 os.fsync=stop
elif kind=='link':
 real=os.link
 def stop(*a,**kw):real(*a,**kw);os._exit(77)
 os.link=stop;os.supports_dir_fd.add(stop);os.supports_follow_symlinks.add(stop)
else:
 real=os.unlink
 def stop(*a,**kw):real(*a,**kw);os._exit(77)
 os.unlink=stop;os.supports_dir_fd.add(stop)
s.apply(p,confirmed_ticket=p['ticket']);os._exit(3)
'''
        for kind in ('sync','link','unlink'):
            with self.subTest(kind=kind):
                proc=subprocess.run([sys.executable,'-I','-S','-B','-c',program,str(ROOT),str(self.root),kind],capture_output=True,text=True,timeout=15)
                self.assertEqual(proc.returncode,77,proc.stderr);target_name,stage_name=proc.stdout.strip().split();target=self.root/target_name;stage=self.root/stage_name
                self.assertEqual(target.exists(),kind in ('link','unlink'));self.assertEqual(stage.exists(),kind in ('sync','link'))
                if target.exists():self.assertIn('SYNTHETIC_GLOBAL',target.read_text())
                self.unchanged()
                if stage.exists():stage.unlink()
                if target.exists():target.unlink()
    def test_json_session_plan_and_apply(self):
        proc=subprocess.Popen([sys.executable,'-I','-S','-B',str(ROOT/'kit/copilot_deploy.py'),'--workspace',str(self.root),'--profile-root','profiles/pilot'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            def send(obj):proc.stdin.write(json.dumps(obj)+'\n');proc.stdin.flush();return json.loads(proc.stdout.readline())
            p=send({'type':'plan','area':'L1','entry_id':'GLOBAL'});self.assertEqual(p['outcome'],'planned')
            self.assertEqual(send({'type':'inspect','area':'L1','entry_id':'GLOBAL'})['outcome'],'missing')
            self.assertEqual(send({'type':'apply','plan':p,'confirmed_ticket':p['ticket']})['diagnostic']['code'],'ticket_unknown')
            p=send({'type':'plan','area':'L1','entry_id':'GLOBAL'})
            self.assertEqual(send({'type':'apply','plan':p,'confirmed_ticket':p['ticket']})['outcome'],'instruction_file_created')
            self.assertEqual(send({'type':'inspect','area':'L1','entry_id':'GLOBAL'})['outcome'],'matched')
        finally:
            proc.stdin.close();proc.wait(timeout=15);proc.stdout.close();proc.stderr.close()

if __name__=='__main__':unittest.main()
