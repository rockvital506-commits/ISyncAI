#!/usr/bin/env python3
"""Опытная последовательность в изолированных синтетических каталогах."""
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
from kit import init_workspace as init, move_execution as execution, move_reservation as reservation, move_recovery_inspect as probe
from kit.base import move_intent, registry_store as store
from kit.base.registry_policy import StoreError

@unittest.skipUnless(init._supported() and store.fcntl is not None and os.rename in os.supports_dir_fd,'POSIX unavailable; not_run')
class ExecutionTests(unittest.TestCase):
    def fixture(self,src='L1'):
        t=tempfile.TemporaryDirectory(prefix='move-execution-');self.addCleanup(t.cleanup);root=Path(t.name).resolve()
        layout=audit.make_workspace(root,parent_scope='.')
        files={'L0':root/'kit/base/registry.json','L1':root/'profiles/pilot/registry.json','L2':root/'.domain-agent-kit/project/registry.json'}
        auth='profile_owner' if src=='L1' else 'project_owner'; parent='C-1' if src=='L1' else 'P-1'
        doc=json.loads(files[src].read_bytes());doc['entries'].append(audit.entry('SOURCE','rule',auth,parent,'docs',state='active'));audit.write(files[src],doc)
        for f in files.values():f.chmod(0o600)
        before={k:p.read_bytes() for k,p in files.items()};dst='L2' if src=='L1' else 'L1'
        candidate=audit.entry('TARGET','rule','project_owner' if dst=='L2' else 'profile_owner','P-1' if dst=='L2' else 'C-1','docs',state='draft')
        report,raw=move_intent.build(before,source=src,target=dst,entry_id='SOURCE',candidate=candidate,
                    portability_context=None if src=='L1' else {'project_names':[],'machine_names':[],'project_paths':[]})
        pin=report['intent_sha256'];reserve=reservation.ReservationSession(layout,intent_bytes=raw,intent_pin=pin)
        plan=reserve.plan(action='reserve');reserve.apply(plan,confirmed_ticket=plan['ticket'])
        neighbor=root/'neighbor';neighbor.write_bytes(b'keep')
        return root,layout,files,before,raw,pin,neighbor
    def error(self,code,fn,*args,**kwargs):
        with self.assertRaises(StoreError) as e:fn(*args,**kwargs)
        self.assertEqual(e.exception.code,code)
    def session(self,layout,raw,pin):return execution.MoveExecutionSession(layout,intent_bytes=raw,intent_pin=pin)
    def apply(self,s,p):return s.apply(p,confirmed_ticket=p['ticket'])
    def test_both_directions_and_reinspection(self):
        for src in ('L1','L2'):
            with self.subTest(src=src):
                root,layout,files,before,raw,pin,neighbor=self.fixture(src);doc,_,after=move_intent._verified(raw,pin)
                s=self.session(layout,raw,pin);p=s.plan();self.assertEqual(p['state'],'before_both')
                self.error('confirmation_required',s.apply,p,confirmed_ticket='bad');self.assertEqual({k:v.read_bytes() for k,v in files.items()},before)
                result=self.apply(s,p);self.assertEqual(result['outcome'],'registries_updated_marker_retained')
                self.assertEqual(files['L0'].read_bytes(),before['L0']);self.assertEqual(files[src].read_bytes(),after[src])
                self.assertEqual(files[doc['target']].read_bytes(),after[doc['target']]);self.assertEqual(neighbor.read_bytes(),b'keep')
                self.assertEqual((root/'.domain-agent-kit/.move-pending').read_bytes(),raw)
                self.error('move_pending',store.status,layout);self.assertEqual(probe.inspect(layout,intent_pin=pin)['state'],'after_both')
                s=self.session(layout,raw,pin);p=s.plan();self.assertEqual(p['state'],'after_both');self.apply(s,p)
                self.assertEqual(files[src].read_bytes(),after[src])
    def test_stale_plan_changed_bytes_and_wrong_ticket(self):
        root,layout,files,before,raw,pin,neighbor=self.fixture();s=self.session(layout,raw,pin);p=s.plan()
        altered=copy.deepcopy(p);altered['state']='after_both';self.error('plan_mismatch',s.apply,altered,confirmed_ticket=p['ticket'])
        self.error('ticket_unknown',self.apply,s,p)
        s=self.session(layout,raw,pin);p=s.plan();files['L0'].write_bytes(before['L0']+b' ')
        self.error('stale_plan',self.apply,s,p);self.assertEqual(files['L1'].read_bytes(),before['L1']);self.assertEqual(files['L2'].read_bytes(),before['L2'])
    def test_foreign_or_impossible_states_are_refused(self):
        for kind in ('foreign','impossible'):
            with self.subTest(kind=kind):
                root,layout,files,before,raw,pin,neighbor=self.fixture();doc,_,after=move_intent._verified(raw,pin)
                files['L1'].write_bytes(b'foreign' if kind=='foreign' else after['L1'])
                s=self.session(layout,raw,pin);self.error('move_execution_stale',s.plan)
                self.assertEqual(files['L2'].read_bytes(),before['L2']);self.assertTrue((root/'.domain-agent-kit/.move-pending').exists())
    def test_busy_and_bad_registry_metadata(self):
        root,layout,files,before,raw,pin,neighbor=self.fixture();s=self.session(layout,raw,pin);p=s.plan()
        fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
        try:
            store.fcntl.flock(fd,store.fcntl.LOCK_EX|store.fcntl.LOCK_NB);self.error('write_busy',self.apply,s,p)
        finally:os.close(fd)
        self.assertEqual({k:v.read_bytes() for k,v in files.items()},before)
        files['L2'].chmod(0o644);s=self.session(layout,raw,pin);p=s.plan();self.error('move_execution_unknown',self.apply,s,p)
        self.assertEqual({k:v.read_bytes() for k,v in files.items()},before);self.assertTrue((root/'.domain-agent-kit/.move-pending').exists())
        files['L2'].chmod(0o600);files['L1'].chmod(0o644);s=self.session(layout,raw,pin);p=s.plan();self.error('move_execution_unknown',self.apply,s,p)
        self.assertEqual({k:v.read_bytes() for k,v in files.items()},before)
    def test_target_failure_never_replaces_source_and_resume(self):
        root,layout,files,before,raw,pin,neighbor=self.fixture();s=self.session(layout,raw,pin);p=s.plan()
        with patch.object(execution.stage,'_replace_for_move',side_effect=OSError('synthetic')):self.error('move_execution_unknown',self.apply,s,p)
        self.assertEqual({k:v.read_bytes() for k,v in files.items()},before)
        s=self.session(layout,raw,pin);self.apply(s,s.plan());self.assertEqual(probe.inspect(layout,intent_pin=pin)['state'],'after_both')
    def test_source_failure_leaves_target_and_retry(self):
        root,layout,files,before,raw,pin,neighbor=self.fixture();s=self.session(layout,raw,pin);p=s.plan();real=execution.stage._replace_for_move;calls=[]
        def fail_second(*a,**kw):
            calls.append(1)
            if len(calls)==2:raise OSError('synthetic')
            return real(*a,**kw)
        with patch.object(execution.stage,'_replace_for_move',side_effect=fail_second):self.error('move_execution_unknown',self.apply,s,p)
        self.assertEqual(files['L1'].read_bytes(),before['L1']);self.assertEqual(probe.inspect(layout,intent_pin=pin)['state'],'target_after_source_before')
        s=self.session(layout,raw,pin);p=s.plan();self.assertEqual(p['state'],'target_after_source_before');self.apply(s,p)
        self.assertEqual(probe.inspect(layout,intent_pin=pin)['state'],'after_both')
    def test_barrier_failure_keeps_source_and_marker(self):
        for fail_name in ('.move-pending','registry.json'):
            with self.subTest(fail_name=fail_name):
                root,layout,files,before,raw,pin,neighbor=self.fixture();s=self.session(layout,raw,pin);p=s.plan();real=execution._sync_file
                def fail(parent,name,expected,limit):
                    if name==fail_name:raise OSError('synthetic barrier failure')
                    return real(parent,name,expected,limit)
                with patch.object(execution,'_sync_file',side_effect=fail):self.error('move_execution_unknown',self.apply,s,p)
                self.assertEqual(files['L1'].read_bytes(),before['L1']);self.assertEqual(files['L0'].read_bytes(),before['L0'])
                self.assertEqual(probe.inspect(layout,intent_pin=pin)['state'],'before_both' if fail_name=='.move-pending' else 'target_after_source_before')
                self.assertEqual((root/'.domain-agent-kit/.move-pending').read_bytes(),raw)
    def test_directory_replacement_and_marker_change_invalidate_plan(self):
        root,layout,files,before,raw,pin,neighbor=self.fixture();s=self.session(layout,raw,pin);p=s.plan()
        project=root/'.domain-agent-kit/project';old=root/'saved-project';project.rename(old);shutil.copytree(old,project)
        self.error('stale_plan',self.apply,s,p);self.assertEqual(files['L1'].read_bytes(),before['L1']);self.assertEqual(files['L2'].read_bytes(),before['L2'])
        s=self.session(layout,raw,pin);p=s.plan();marker=root/'.domain-agent-kit/.move-pending';marker.write_bytes(raw+b'foreign')
        self.error('move_intent_pin_mismatch',self.apply,s,p);self.assertEqual(files['L1'].read_bytes(),before['L1']);self.assertEqual(files['L2'].read_bytes(),before['L2'])
    def test_fsync_failures_preserve_order_and_permit_new_synthetic_attempt(self):
        for src in ('L1','L2'):
            for nth in range(1,11):
                with self.subTest(src=src,nth=nth):
                    root,layout,files,before,raw,pin,neighbor=self.fixture(src);doc,_,after=move_intent._verified(raw,pin)
                    s=self.session(layout,raw,pin);p=s.plan();real=os.fsync;calls=[]
                    def fail(fd):
                        calls.append(fd)
                        if len(calls)==nth:raise OSError('synthetic fsync failure')
                        return real(fd)
                    with patch.object(execution.os,'fsync',side_effect=fail):self.error('move_execution_unknown',self.apply,s,p)
                    self.assertEqual(files['L0'].read_bytes(),before['L0'])
                    if files[src].read_bytes()==after[src]:self.assertEqual(files[doc['target']].read_bytes(),after[doc['target']])
                    self.assertIn(probe.inspect(layout,intent_pin=pin)['state'],('before_both','target_after_source_before','after_both'))
                    self.assertEqual((root/'.domain-agent-kit/.move-pending').read_bytes(),raw);self.error('move_pending',store.status,layout)
                    s=self.session(layout,raw,pin);self.apply(s,s.plan());self.assertEqual(probe.inspect(layout,intent_pin=pin)['state'],'after_both')
    def test_abrupt_exit_inside_rename_and_retry(self):
        program=r'''import os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1]);from kit import move_execution as m
from kit.base.registry_store import Layout
raw=bytes.fromhex(sys.argv[3]);s=m.MoveExecutionSession(Layout(Path(sys.argv[2]),'profiles/pilot'),intent_bytes=raw,intent_pin=sys.argv[4]);p=s.plan()
real=os.replace;count=[0]
def stop(*a,**kw):
 result=real(*a,**kw);count[0]+=1
 if count[0]==int(sys.argv[5]):os._exit(77)
 return result
os.replace=stop;s.apply(p,confirmed_ticket=p['ticket']);os._exit(3)
'''
        for src in ('L1','L2'):
            for n in (1,2):
                with self.subTest(src=src,n=n):
                    root,layout,files,before,raw,pin,neighbor=self.fixture(src)
                    proc=subprocess.run([sys.executable,'-I','-S','-B','-c',program,str(ROOT),str(root),raw.hex(),pin,str(n)],capture_output=True,timeout=20)
                    self.assertEqual(proc.returncode,77,proc.stderr)
                    expected='target_after_source_before' if n==1 else 'after_both'
                    self.assertEqual(probe.inspect(layout,intent_pin=pin)['state'],expected)
                    s=self.session(layout,raw,pin);p=s.plan();self.assertEqual(p['state'],expected);self.apply(s,p)
                    self.assertEqual(probe.inspect(layout,intent_pin=pin)['state'],'after_both');self.assertEqual(neighbor.read_bytes(),b'keep')
    def test_abrupt_exit_after_each_replacement_and_retry(self):
        program=r'''import os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1]);from kit import move_execution as m
from kit.base.registry_store import Layout
raw=bytes.fromhex(sys.argv[3]);s=m.MoveExecutionSession(Layout(Path(sys.argv[2]),'profiles/pilot'),intent_bytes=raw,intent_pin=sys.argv[4]);p=s.plan()
real=m.stage._replace_for_move;count=[0]
def stop(*a,**kw):
 result=real(*a,**kw);count[0]+=1
 if count[0]==int(sys.argv[5]):os._exit(77)
 return result
m.stage._replace_for_move=stop;s.apply(p,confirmed_ticket=p['ticket']);os._exit(3)
'''
        for src in ('L1','L2'):
            for n in (1,2):
                with self.subTest(src=src,n=n):
                    root,layout,files,before,raw,pin,neighbor=self.fixture(src)
                    proc=subprocess.run([sys.executable,'-I','-S','-B','-c',program,str(ROOT),str(root),raw.hex(),pin,str(n)],capture_output=True,timeout=20)
                    self.assertEqual(proc.returncode,77,proc.stderr)
                    expected='target_after_source_before' if n==1 else 'after_both'
                    self.assertEqual(probe.inspect(layout,intent_pin=pin)['state'],expected);self.error('move_pending',store.status,layout)
                    s=self.session(layout,raw,pin);p=s.plan();self.assertEqual(p['state'],expected);self.apply(s,p)
                    self.assertEqual(probe.inspect(layout,intent_pin=pin)['state'],'after_both');self.assertEqual(files['L0'].read_bytes(),before['L0']);self.assertEqual(neighbor.read_bytes(),b'keep')

if __name__=='__main__':unittest.main()
