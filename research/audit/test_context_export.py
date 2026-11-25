#!/usr/bin/env python3
"""Явная выдача файла контекста только на синтетических данных, не живому агенту."""
import copy
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
import test_context_modes as fixtures
from kit import context_export, init_workspace as init
from kit.base import registry_store as store
from kit.base.registry_policy import StoreError

@unittest.skipUnless(init._supported() and store.fcntl is not None,'POSIX unavailable; not_run')
class ContextExportTests(unittest.TestCase):
    def setUp(self):
        self.ctx=fixtures.ContextTests();self.ctx.setUp();self.addCleanup(self.ctx.doCleanups)
        temp=tempfile.TemporaryDirectory(prefix='context-export-external-');self.addCleanup(temp.cleanup)
        self.out=Path(temp.name).resolve();self.neighbor=self.out/'neighbor';self.neighbor.write_bytes(b'keep')
    def session(self,mode='project',destination=None):
        return context_export.ContextExportSession(self.ctx.layout,destination or self.out/'context.json',mode=mode,scope='docs/file',choices=copy.deepcopy(self.ctx.choices))
    def error(self,code,fn,*args,**kwargs):
        with self.assertRaises(StoreError) as err:fn(*args,**kwargs)
        self.assertEqual(err.exception.code,code)
    def apply(self,s,p):return s.apply(p,confirmed_ticket=p['ticket'])
    def test_both_modes_include_selected_and_exclude_unselected(self):
        for mode in ('project','kit'):
            with self.subTest(mode=mode):
                path=self.out/(mode+'.json');s=self.session(mode,path);p=s.plan();self.assertFalse(path.exists())
                self.assertEqual(p['agent_delivery'],'not_checked');self.assertEqual(p['agent_application'],'not_checked')
                self.assertNotIn('EXCLUDED_PROFILE_SECRET',p['content_utf8']);self.assertNotIn('EXCLUDED_PROJECT_SECRET',p['content_utf8'])
                self.error('confirmation_required',s.apply,p,confirmed_ticket='wrong');self.assertFalse(path.exists())
                result=self.apply(s,p);self.assertEqual(result['outcome'],'context_file_created');self.assertEqual(path.read_text(),p['content_utf8'])
                doc=json.loads(path.read_bytes());self.assertEqual(doc['outcome'],'review_required');self.assertEqual(doc['context']['mode'],mode)
                ids={r['entry']['id'] for r in doc['context']['entries']};self.assertIn('IN',ids);self.assertIn('SAFETY',ids)
                self.assertIn('SYS-PROJECT-MODE' if mode=='project' else 'SYS-KIT-MODE',ids)
                self.assertNotIn('SYS-KIT-MODE' if mode=='project' else 'SYS-PROJECT-MODE',ids)
                self.assertEqual(path.stat().st_mode&0o777,0o600);self.assertEqual(self.neighbor.read_bytes(),b'keep')
    def test_stale_plan_and_mutated_fields_refuse(self):
        for field in ('plan','choices','mode','registry','destination'):
            with self.subTest(field=field):
                path=self.out/(field+'.json');s=self.session(destination=path);p=s.plan();bad=copy.deepcopy(p)
                if field=='plan':bad['content_utf8']+=' ';code='plan_mismatch'
                elif field=='choices':s.choices['exclude'].reverse();code='stale_plan'
                elif field=='mode':s.mode='kit';code='stale_plan'
                elif field=='destination':s.destination=self.out/'other.json';code='stale_plan'
                else:
                    original=self.ctx.paths['L1'].read_bytes();self.ctx.paths['L1'].write_bytes(original+b' ');code='stale_plan'
                self.error(code,s.apply,bad,confirmed_ticket=p['ticket']);self.assertFalse(path.exists())
                if field=='registry':self.ctx.paths['L1'].write_bytes(original)
    def test_occupied_link_or_workspace_destination_refuse(self):
        s=self.session(destination=self.ctx.root/'context.json');self.error('context_export_destination_invalid',s.plan)
        for kind in ('file','directory','symlink','dangling'):
            with self.subTest(kind=kind):
                path=self.out/('occupied-'+kind);s=self.session(destination=path);p=s.plan()
                if kind=='file':path.write_bytes(b'foreign')
                elif kind=='directory':path.mkdir()
                elif kind=='symlink':path.symlink_to(self.neighbor)
                else:path.symlink_to(self.out/'missing')
                self.error('context_export_destination_occupied',self.apply,s,p)
                self.assertEqual(self.neighbor.read_bytes(),b'keep')
    def test_pending_marker_and_conflicts_refuse_without_output(self):
        marker=self.ctx.root/'.domain-agent-kit/.move-pending';marker.write_bytes(b'unknown')
        s=self.session();self.error('move_pending',s.plan);self.assertFalse(s.destination.exists())
        marker.unlink();s=self.session();p=s.plan();marker.write_bytes(b'unknown')
        self.error('move_pending',self.apply,s,p);self.assertFalse(s.destination.exists())
    def test_busy_and_parent_replacement_refuse(self):
        s=self.session();p=s.plan();fd=os.open(self.ctx.root,os.O_RDONLY|os.O_DIRECTORY)
        try:
            store.fcntl.flock(fd,store.fcntl.LOCK_EX|store.fcntl.LOCK_NB);self.error('context_export_busy',self.apply,s,p)
        finally:os.close(fd)
        self.assertFalse(s.destination.exists())
        parent=self.out/'selected';parent.mkdir();s=self.session(destination=parent/'context');p=s.plan()
        parent.rename(self.out/'prior');parent.mkdir();self.error('stale_plan',self.apply,s,p);self.assertFalse(s.destination.exists())
    def test_replaced_workspace_with_same_bytes_refuses(self):
        s=self.session();p=s.plan();root=self.ctx.root;old=root.parent/(root.name+'-prior')
        self.addCleanup(shutil.rmtree,old,True);root.rename(old);shutil.copytree(old,root)
        self.error('stale_plan',self.apply,s,p);self.assertFalse(s.destination.exists())
    def test_uncooperative_input_change_after_creation_is_unknown(self):
        s=self.session();p=s.plan();real=os.write;original=self.ctx.paths['L1'].read_bytes()
        def change(fd,data):
            result=real(fd,data);self.ctx.paths['L1'].write_bytes(original+b' ');return result
        with patch.object(context_export.os,'write',side_effect=change):self.error('context_export_unknown',self.apply,s,p)
        self.assertTrue(s.destination.exists());self.assertEqual(self.neighbor.read_bytes(),b'keep')
    def test_write_fsync_and_xattr_failures_leave_unverified_file(self):
        for kind in ('write','file_sync','parent_sync','xattr'):
            with self.subTest(kind=kind):
                s=self.session(destination=self.out/(kind+'.json'));p=s.plan();real=os.fsync;calls=[]
                if kind=='write':mock=patch.object(context_export.os,'write',side_effect=OSError('synthetic'))
                elif kind=='xattr':mock=patch.object(init.os,'listxattr',return_value=['user.synthetic'])
                else:
                    def sync(fd):
                        calls.append(fd)
                        if len(calls)==(1 if kind=='file_sync' else 2):raise OSError('synthetic')
                        return real(fd)
                    mock=patch.object(context_export.os,'fsync',side_effect=sync)
                with mock:self.error('context_export_unknown',self.apply,s,p)
                self.assertTrue(s.destination.exists());self.assertEqual(self.neighbor.read_bytes(),b'keep')
    def test_process_exit_after_create_or_sync(self):
        program=r'''import json,os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1]);from kit import context_export as m
from kit.base.registry_store import Layout
s=m.ContextExportSession(Layout(Path(sys.argv[2]),'profiles/pilot'),Path(sys.argv[3]),mode='project',scope='docs/file',choices=json.loads(sys.argv[4]));p=s.plan();where=sys.argv[5]
if where=='write':
 real=os.write
 def stop(fd,data):real(fd,data[:8]);os._exit(77)
 os.write=stop
else:
 real=os.fsync;calls=[0]
 def stop(fd):
  real(fd);calls[0]+=1
  if calls[0]==int(where):os._exit(77)
 os.fsync=stop
s.apply(p,confirmed_ticket=p['ticket']);os._exit(3)
'''
        for kind in ('write','1','2'):
            with self.subTest(kind=kind):
                path=self.out/('exit-'+kind);proc=subprocess.run([sys.executable,'-I','-S','-B','-c',program,str(ROOT),str(self.ctx.root),str(path),json.dumps(self.ctx.choices),kind],capture_output=True,timeout=20)
                self.assertEqual(proc.returncode,77,proc.stderr);self.assertTrue(path.exists());self.assertEqual(self.neighbor.read_bytes(),b'keep')
                if kind=='write':self.assertEqual(len(path.read_bytes()),8)
                else:self.assertEqual(json.loads(path.read_bytes())['outcome'],'review_required')

if __name__=='__main__':unittest.main()
