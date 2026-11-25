#!/usr/bin/env python3
"""Согласование штатного трёхреестрового чтения и записи; синтетические процессы."""
import errno
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'research/audit')]
import core_audit as audit
from kit.base import registry_store as store, applicability
from kit.base.registry_policy import StoreError

SUPPORTED=(os.name=='posix' and store.fcntl is not None and hasattr(os,'O_DIRECTORY') and hasattr(os,'O_NOFOLLOW'))

SCRIPT=r'''import json,sys
from pathlib import Path
sys.path[:0]=[sys.argv[1],str(Path(sys.argv[1])/'research/audit')]
from kit.base import registry_store as store
from kit.base.registry_policy import StoreError
from unittest.mock import patch
layout=store.Layout(Path(sys.argv[2]),'profiles/pilot');real=store._load_unlocked
def pause(*args):
 print(json.dumps({'event':'locked'}),flush=True)
 if sys.stdin.readline().strip()!='resume':raise ValueError('resume')
 return real(*args)
try:
 with patch.object(store,'_load_unlocked',side_effect=pause):result=store.status(layout)
 print(json.dumps({'result':'read','revision':result['profile_revision']}),flush=True)
except StoreError as e:print(json.dumps({'error':e.code}),flush=True)
'''

@unittest.skipUnless(SUPPORTED,'POSIX directory flock API unavailable; not_run')
class ReadLockTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(prefix='read-lock-');self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name).resolve();audit.make_workspace(self.root,parent_scope='.')
        self.layout=store.Layout(self.root,'profiles/pilot');self.children=[];self.addCleanup(self.cleanup)
        try:
            fd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY)
            try:store.fcntl.flock(fd,store.fcntl.LOCK_SH|store.fcntl.LOCK_NB)
            finally:os.close(fd)
        except OSError as error:
            if error.errno in (errno.ENOSYS,errno.ENOTSUP,errno.EOPNOTSUPP):self.skipTest('filesystem flock unsupported; not_run')
            raise
    def cleanup(self):
        for p,_ in self.children:
            if p.poll() is None:p.kill()
            p.communicate(timeout=10)
    def child(self):
        p=subprocess.Popen([sys.executable,'-I','-S','-B','-c',SCRIPT,str(ROOT),str(self.root)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
        lines=queue.Queue()
        def read():
            for line in p.stdout:lines.put(line)
            lines.put(None)
        threading.Thread(target=read,daemon=True).start();self.children.append((p,lines));return p,lines
    def receive(self,peer):
        line=peer[1].get(timeout=10)
        if line is None:self.fail('process exited: '+peer[0].stderr.read())
        return json.loads(line)
    def release(self,peer):
        peer[0].stdin.write('resume\n');peer[0].stdin.flush();self.assertEqual(self.receive(peer)['result'],'read')
    def error(self,code,fn,*args,**kw):
        with self.assertRaises(StoreError) as e:fn(*args,**kw)
        self.assertEqual(e.exception.code,code)
    def test_readers_share_and_exclude_actual_writer(self):
        entry=audit.entry('N-1','rule','profile_owner','C-1','docs',state='draft')
        plan=store.plan_create(self.layout,entry)
        a,b=self.child(),self.child()
        self.assertEqual(self.receive(a),{'event':'locked'});self.assertEqual(self.receive(b),{'event':'locked'})
        self.error('write_busy',store.apply_create,self.layout,plan,confirmed_ticket=plan['ticket'])
        self.release(a)
        self.error('write_busy',store.apply_create,self.layout,plan,confirmed_ticket=plan['ticket'])
        self.release(b)
        result=store.apply_create(self.layout,plan,confirmed_ticket=plan['ticket'])
        self.assertEqual(result['profile_revision'],1)
        self.assertEqual(store.status(self.layout)['profile_revision'],1)
    def test_actual_paused_writer_excludes_other_process_readers(self):
        script=r'''import json,sys
from pathlib import Path
sys.path[:0]=[sys.argv[1],str(Path(sys.argv[1])/'research/audit')]
import core_audit as audit
from kit.base import registry_store as store
from unittest.mock import patch
layout=store.Layout(Path(sys.argv[2]),'profiles/pilot')
entry=audit.entry('N-2','rule','profile_owner','C-1','docs',state='draft');plan=store.plan_create(layout,entry)
real=store._replace
def pause(*args,**kwargs):
 print(json.dumps({'event':'writing'}),flush=True)
 if sys.stdin.readline().strip()!='resume':raise ValueError('resume')
 return real(*args,**kwargs)
with patch.object(store,'_replace',side_effect=pause):store.apply_create(layout,plan,confirmed_ticket=plan['ticket'])
print(json.dumps({'event':'done'}),flush=True)
'''
        p=subprocess.Popen([sys.executable,'-I','-S','-B','-c',script,str(ROOT),str(self.root)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
        lines=queue.Queue()
        def read():
            for line in p.stdout:lines.put(line)
            lines.put(None)
        threading.Thread(target=read,daemon=True).start();peer=(p,lines);self.children.append(peer)
        self.assertEqual(self.receive(peer),{'event':'writing'})
        self.error('read_busy',store.status,self.layout)
        self.error('read_busy',applicability.applicable,self.layout,scope='docs')
        p.stdin.write('resume\n');p.stdin.flush();self.assertEqual(self.receive(peer),{'event':'done'})
        self.assertEqual(store.status(self.layout)['profile_revision'],1)

    def test_writer_lock_refuses_all_load_based_readers_then_recovers(self):
        fd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY)
        try:
            store.fcntl.flock(fd,store.fcntl.LOCK_EX|store.fcntl.LOCK_NB)
            for call in (lambda:store.status(self.layout),lambda:store.read_registry(self.layout,target='L1'),
                         lambda:store.report_conflicts(self.layout),lambda:applicability.applicable(self.layout,scope='docs')):
                self.error('read_busy',call)
        finally:os.close(fd)
        self.assertEqual(store.status(self.layout)['profile_revision'],0)
    def test_exception_releases_lock_and_unsupported_fails_closed(self):
        with patch.object(store,'_load_unlocked',side_effect=StoreError('synthetic','workspace')):
            self.error('synthetic',store.status,self.layout)
        fd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY)
        try:store.fcntl.flock(fd,store.fcntl.LOCK_EX|store.fcntl.LOCK_NB)
        finally:os.close(fd)
        with patch.object(store,'fcntl',None):self.error('read_lock_unavailable',store.status,self.layout)
    def test_changed_inode_after_load_and_close_failure_do_not_return_snapshot(self):
        real_stat=store.os.stat; calls=[]
        def altered(*args,**kwargs):
            value=real_stat(*args,**kwargs)
            if kwargs.get('follow_symlinks') is False and Path(args[0]) == self.root:
                calls.append(True)
                if len(calls)==2:
                    data=list(value);data[1]+=1;return os.stat_result(data)
            return value
        with patch.object(store.os,'stat',side_effect=altered):
            self.error('read_lock_unavailable',store.status,self.layout)
        self.assertEqual(len(calls),2)
        real_close=store.os.close
        def close_fail(fd):
            real_close(fd)
            raise OSError('synthetic close error')
        with patch.object(store.os,'close',side_effect=close_fail):
            self.error('read_lock_release_failed',store.status,self.layout)
        self.assertEqual(store.status(self.layout)['profile_revision'],0)

    def test_readers_refuse_lock_error_and_changed_inode(self):
        with patch.object(store.fcntl,'flock',side_effect=OSError(errno.EIO,'synthetic')):
            self.error('read_lock_unavailable',store.status,self.layout)
        real=store.os.stat
        def altered(*args,**kwargs):
            value=real(*args,**kwargs)
            if kwargs.get('follow_symlinks') is False:
                data=list(value);data[1]+=1;return os.stat_result(data)
            return value
        with patch.object(store.os,'stat',side_effect=altered):
            self.error('read_lock_unavailable',store.status,self.layout)

if __name__=='__main__':unittest.main()
