#!/usr/bin/env python3
"""Отдельное завершение только в изолированных синтетических workspace."""
import copy
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'research/audit')]
import test_move_execution as fixtures
from kit import init_workspace as init, move_execution as execution, move_finalize as finalizer, move_recovery_inspect as probe
from kit.base import move_intent, registry_store as store
from kit.base.registry_policy import StoreError

@unittest.skipUnless(init._supported() and store.fcntl is not None and os.rename in os.supports_dir_fd and os.listdir in os.supports_fd,'POSIX unavailable; not_run')
class FinalizationTests(unittest.TestCase):
    def fixture(self,src='L1',*,complete=True):
        helper=fixtures.ExecutionTests();self.addCleanup(helper.doCleanups)
        root,layout,files,before,raw,pin,neighbor=helper.fixture(src)
        if complete:
            s=execution.MoveExecutionSession(layout,intent_bytes=raw,intent_pin=pin);p=s.plan();s.apply(p,confirmed_ticket=p['ticket'])
        return root,layout,files,before,raw,pin,neighbor
    def session(self,layout,raw,pin):return finalizer.MoveFinalizationSession(layout,intent_bytes=raw,intent_pin=pin)
    def apply(self,s,p):return s.apply(p,confirmed_ticket=p['ticket'])
    def error(self,code,fn,*args,**kwargs):
        with self.assertRaises(StoreError) as e:fn(*args,**kwargs)
        self.assertEqual(e.exception.code,code)
    def test_complete_both_directions_and_separate_confirmation(self):
        for src in ('L1','L2'):
            with self.subTest(src=src):
                root,layout,files,before,raw,pin,neighbor=self.fixture(src);marker=root/'.domain-agent-kit/.move-pending'
                doc,_,after=move_intent._verified(raw,pin);observed={k:p.read_bytes() for k,p in files.items()}
                s=self.session(layout,raw,pin);p=s.plan();self.assertEqual(p['state'],'after_both');self.assertEqual(p['effect'],'remove_marker_after_checks_and_sync')
                self.error('confirmation_required',s.apply,p,confirmed_ticket='wrong');self.assertTrue(marker.exists())
                self.assertEqual(self.apply(s,p)['outcome'],'marker_removed_after_both');self.assertFalse(marker.exists())
                self.assertEqual({k:p.read_bytes() for k,p in files.items()},observed);self.assertEqual(files[src].read_bytes(),after[src])
                self.assertEqual(files[doc['target']].read_bytes(),after[doc['target']]);self.assertEqual(files['L0'].read_bytes(),before['L0'])
                self.assertEqual(neighbor.read_bytes(),b'keep');self.assertIsInstance(store.status(layout),dict)
    def test_incomplete_foreign_and_impossible_are_refused(self):
        for state in ('before','intermediate','impossible','foreign'):
            with self.subTest(state=state):
                root,layout,files,before,raw,pin,neighbor=self.fixture(complete=False);_,_,after=move_intent._verified(raw,pin)
                if state=='intermediate':files['L2'].write_bytes(after['L2'])
                if state=='impossible':files['L1'].write_bytes(after['L1'])
                if state=='foreign':files['L0'].write_bytes(b'foreign')
                marker=root/'.domain-agent-kit/.move-pending';self.error('move_finalize_stale',self.session(layout,raw,pin).plan)
                self.assertEqual(marker.read_bytes(),raw)
    def test_tampered_plan_stale_inputs_or_marker_never_remove(self):
        root,layout,files,before,raw,pin,neighbor=self.fixture();marker=root/'.domain-agent-kit/.move-pending'
        s=self.session(layout,raw,pin);p=s.plan();changed=copy.deepcopy(p);changed['effect']='another'
        self.error('plan_mismatch',s.apply,changed,confirmed_ticket=p['ticket']);self.assertTrue(marker.exists());self.error('ticket_unknown',self.apply,s,p)
        s=self.session(layout,raw,pin);p=s.plan();files['L0'].write_bytes(before['L0']+b' ')
        self.error('stale_plan',self.apply,s,p);self.assertTrue(marker.exists());files['L0'].write_bytes(before['L0'])
        s=self.session(layout,raw,pin);p=s.plan();marker.write_bytes(raw+b'changed')
        self.error('move_intent_pin_mismatch',self.apply,s,p);self.assertEqual(marker.read_bytes(),raw+b'changed')
    def test_stages_of_any_type_refuse_without_cleanup(self):
        for area in ('L1','L2'):
            for kind in ('file','directory','symlink'):
                with self.subTest(area=area,kind=kind):
                    root,layout,files,before,raw,pin,neighbor=self.fixture();marker=root/'.domain-agent-kit/.move-pending'
                    stage=files[area].parent/'.move-stage-unrecognized'
                    if kind=='file':stage.write_bytes(b'secret')
                    elif kind=='directory':stage.mkdir()
                    else:stage.symlink_to(neighbor)
                    s=self.session(layout,raw,pin);self.error('move_stages_present',s.plan)
                    self.assertTrue(os.path.lexists(stage));self.assertTrue(marker.exists());self.assertEqual(neighbor.read_bytes(),b'keep')
    def test_stage_appearing_after_plan_and_busy_lock_refuse(self):
        root,layout,files,before,raw,pin,neighbor=self.fixture();marker=root/'.domain-agent-kit/.move-pending'
        s=self.session(layout,raw,pin);p=s.plan();stage=files['L1'].parent/'.move-stage-new';stage.write_bytes(b'synthetic')
        self.error('move_stages_present',self.apply,s,p);self.assertTrue(marker.exists());self.assertTrue(stage.exists());stage.unlink()
        s=self.session(layout,raw,pin);p=s.plan();fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
        try:
            store.fcntl.flock(fd,store.fcntl.LOCK_EX|store.fcntl.LOCK_NB);self.error('write_busy',self.apply,s,p)
        finally:os.close(fd)
        self.assertTrue(marker.exists())
    def test_marker_metadata_and_changed_state_during_barriers_refuse(self):
        root,layout,files,before,raw,pin,neighbor=self.fixture();marker=root/'.domain-agent-kit/.move-pending'
        marker.chmod(0o644);s=self.session(layout,raw,pin);p=s.plan();self.error('move_finalize_unavailable',self.apply,s,p)
        self.assertTrue(marker.exists());marker.chmod(0o600)
        s=self.session(layout,raw,pin);p=s.plan();real=finalizer.execution._sync_file;calls=[]
        def change(*a,**kw):
            real(*a,**kw);calls.append(1)
            if len(calls)==3:files['L0'].write_bytes(before['L0']+b' ')
        with patch.object(finalizer.execution,'_sync_file',side_effect=change):self.error('stale_plan',self.apply,s,p)
        self.assertTrue(marker.exists());self.assertEqual(marker.read_bytes(),raw)
    def test_stage_appearing_during_barriers_refuses(self):
        root,layout,files,before,raw,pin,neighbor=self.fixture();marker=root/'.domain-agent-kit/.move-pending'
        s=self.session(layout,raw,pin);p=s.plan();real=finalizer.execution._sync_file;calls=[];stage=files['L2'].parent/'.move-stage-late'
        def create(*a,**kw):
            real(*a,**kw);calls.append(1)
            if len(calls)==3:stage.write_bytes(b'secret')
        with patch.object(finalizer.execution,'_sync_file',side_effect=create):self.error('move_stages_present',self.apply,s,p)
        self.assertTrue(marker.exists());self.assertEqual(stage.read_bytes(),b'secret')
    def test_fsync_failures_and_unlink_error_are_conservative(self):
        for point in range(1,8):
            with self.subTest(point=point):
                root,layout,files,before,raw,pin,neighbor=self.fixture();marker=root/'.domain-agent-kit/.move-pending'
                expected={k:p.read_bytes() for k,p in files.items()};s=self.session(layout,raw,pin);p=s.plan();real=os.fsync;calls=[]
                def fail(fd):
                    calls.append(fd)
                    if len(calls)==point:raise OSError('synthetic')
                    return real(fd)
                with patch.object(finalizer.os,'fsync',side_effect=fail):self.error('move_finalize_unknown' if point==7 else 'move_finalize_unavailable',self.apply,s,p)
                self.assertEqual(marker.exists(),point!=7);self.assertEqual({k:p.read_bytes() for k,p in files.items()},expected)
        root,layout,files,before,raw,pin,neighbor=self.fixture();marker=root/'.domain-agent-kit/.move-pending';s=self.session(layout,raw,pin);p=s.plan()
        with patch.object(finalizer.os,'unlink',side_effect=OSError('synthetic')):self.error('move_finalize_unknown',self.apply,s,p)
        self.assertEqual(marker.read_bytes(),raw)
    def test_process_exit_at_unlink_and_after_sync(self):
        program=r'''import os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1]);from kit import move_finalize as m
from kit.base.registry_store import Layout
raw=bytes.fromhex(sys.argv[3]);s=m.MoveFinalizationSession(Layout(Path(sys.argv[2]),'profiles/pilot'),intent_bytes=raw,intent_pin=sys.argv[4]);p=s.plan();where=sys.argv[5]
if where in ('before','after'):
 real=os.unlink
 def stop(*a,**kw):
  if where=='before':os._exit(77)
  real(*a,**kw);os._exit(77)
 os.unlink=stop
else:
 real=os.fsync;count=[0]
 def stop(fd):
  real(fd);count[0]+=1
  if count[0]==7:os._exit(77)
 os.fsync=stop
s.apply(p,confirmed_ticket=p['ticket']);os._exit(3)
'''
        for point in ('before','after','sync'):
            with self.subTest(point=point):
                root,layout,files,before,raw,pin,neighbor=self.fixture();marker=root/'.domain-agent-kit/.move-pending';expected={k:p.read_bytes() for k,p in files.items()}
                proc=subprocess.run([sys.executable,'-I','-S','-B','-c',program,str(ROOT),str(root),raw.hex(),pin,point],capture_output=True,timeout=20)
                self.assertEqual(proc.returncode,77,proc.stderr);self.assertEqual(marker.exists(),point=='before')
                self.assertEqual({k:p.read_bytes() for k,p in files.items()},expected);self.assertEqual(neighbor.read_bytes(),b'keep')
                if point=='before':self.assertEqual(probe.inspect(layout,intent_pin=pin)['state'],'after_both');self.error('move_pending',store.status,layout)
                else:self.assertIsInstance(store.status(layout),dict)

if __name__=='__main__':unittest.main()
