#!/usr/bin/env python3
"""Уборка одной стадии: только собственные синтетические временные деревья."""
import copy
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'research/audit')]
import test_move_execution as fixtures
from kit import init_workspace as init, move_execution as execution, move_finalize as finalizer, move_stage_cleanup as cleanup
from kit.base import move_intent, registry_store as store
from kit.base.registry_policy import StoreError

@unittest.skipUnless(init._supported() and store.fcntl is not None and os.rename in os.supports_dir_fd and os.listdir in os.supports_fd,'POSIX unavailable; not_run')
class StageCleanupTests(unittest.TestCase):
    def fixture(self,src='L1',complete=True):
        helper=fixtures.ExecutionTests();self.addCleanup(helper.doCleanups)
        root,layout,files,before,raw,pin,neighbor=helper.fixture(src)
        if complete:
            s=execution.MoveExecutionSession(layout,intent_bytes=raw,intent_pin=pin);p=s.plan();s.apply(p,confirmed_ticket=p['ticket'])
        return root,layout,files,before,raw,pin,neighbor
    def session(self,layout,raw,pin):return cleanup.MoveStageCleanupSession(layout,intent_bytes=raw,intent_pin=pin)
    def error(self,code,fn,*args,**kw):
        with self.assertRaises(StoreError) as err:fn(*args,**kw)
        self.assertEqual(err.exception.code,code)
    def stage(self,files,raw,pin,area,n=5):
        _,_,after=move_intent._verified(raw,pin);path=files[area].parent/('.move-stage-'+'a'*32)
        path.write_bytes(after[area][:n]);path.chmod(0o600);return path
    def apply(self,s,p):return s.apply(p,confirmed_ticket=p['ticket'])
    def test_cleanup_after_failed_target_then_move_and_finalize_both_directions(self):
        for src in ('L1','L2'):
            with self.subTest(src=src):
                root,layout,files,before,raw,pin,neighbor=self.fixture(src,complete=False);target='L2' if src=='L1' else 'L1'
                s=execution.MoveExecutionSession(layout,intent_bytes=raw,intent_pin=pin);p=s.plan()
                real=os.write
                def partial(fd,data):real(fd,data[:5]);raise OSError('synthetic')
                with patch.object(execution.stage.os,'write',side_effect=partial):self.error('move_execution_unknown',s.apply,p,confirmed_ticket=p['ticket'])
                paths=list(files[target].parent.glob('.move-stage-*'));self.assertEqual(len(paths),1);stage=paths[0]
                marker=root/'.domain-agent-kit/.move-pending';self.assertEqual(stage.stat().st_size,5)
                c=self.session(layout,raw,pin);cp=c.plan(area=target,name=stage.name)
                self.assertEqual(cp['stage_matches'],'after_prefix');self.assertEqual(cp['stage_bytes'],5)
                self.error('confirmation_required',c.apply,cp,confirmed_ticket='wrong');self.assertTrue(stage.exists())
                self.assertEqual(self.apply(c,cp)['outcome'],'selected_stage_removed');self.assertFalse(stage.exists());self.assertEqual(marker.read_bytes(),raw)
                s=execution.MoveExecutionSession(layout,intent_bytes=raw,intent_pin=pin);p=s.plan();s.apply(p,confirmed_ticket=p['ticket'])
                f=finalizer.MoveFinalizationSession(layout,intent_bytes=raw,intent_pin=pin);p=f.plan();f.apply(p,confirmed_ticket=p['ticket'])
                self.assertFalse(marker.exists());self.assertIsInstance(store.status(layout),dict);self.assertEqual(neighbor.read_bytes(),b'keep')
    def test_cleanup_source_stage_after_target_then_resume(self):
        root,layout,files,before,raw,pin,neighbor=self.fixture(complete=False);s=execution.MoveExecutionSession(layout,intent_bytes=raw,intent_pin=pin);p=s.plan()
        real=os.write;calls=[]
        def fail_second(fd,data):
            calls.append(1)
            if len(calls)==2:real(fd,data[:7]);raise OSError('synthetic')
            return real(fd,data)
        with patch.object(execution.stage.os,'write',side_effect=fail_second):self.error('move_execution_unknown',s.apply,p,confirmed_ticket=p['ticket'])
        stage=next(files['L1'].parent.glob('.move-stage-*'));c=self.session(layout,raw,pin);p=c.plan(area='L1',name=stage.name)
        self.assertEqual(p['state'],'target_after_source_before');self.apply(c,p)
        s=execution.MoveExecutionSession(layout,intent_bytes=raw,intent_pin=pin);p=s.plan();s.apply(p,confirmed_ticket=p['ticket'])
        f=finalizer.MoveFinalizationSession(layout,intent_bytes=raw,intent_pin=pin);p=f.plan();f.apply(p,confirmed_ticket=p['ticket'])
        self.assertIsInstance(store.status(layout),dict)
    def test_stages_empty_partial_full_and_final_state(self):
        for n in (0,3,10**6):
            with self.subTest(n=n):
                root,layout,files,before,raw,pin,neighbor=self.fixture();stage=self.stage(files,raw,pin,'L1',n)
                expected={k:p.read_bytes() for k,p in files.items()};c=self.session(layout,raw,pin);p=c.plan(area='L1',name=stage.name)
                self.assertEqual(p['stage_bytes'],stage.stat().st_size);self.assertEqual(p['origin'],'not_verified');self.apply(c,p)
                self.assertFalse(stage.exists());self.assertEqual({k:p.read_bytes() for k,p in files.items()},expected)
    def test_rejects_bad_names_content_symlink_hardlink_mode(self):
        root,layout,files,before,raw,pin,neighbor=self.fixture();c=self.session(layout,raw,pin)
        for name in ('../neighbor','.move-stage-'+'a'*31,'.move-stage-'+'A'*32,'.move-stage-'+'a'*32+'/x'):
            self.error('move_stage_invalid',c.plan,area='L1',name=name)
        self.error('move_stage_invalid',c.plan,area='L0',name='.move-stage-'+'a'*32)
        stage=files['L1'].parent/('.move-stage-'+'a'*32);stage.write_bytes(b'foreign');stage.chmod(0o600)
        self.error('move_stage_unavailable',c.plan,area='L1',name=stage.name);stage.unlink()
        stage.symlink_to(neighbor);self.error('move_stage_unavailable',c.plan,area='L1',name=stage.name);stage.unlink()
        stage=self.stage(files,raw,pin,'L1');stage.chmod(0o644);self.error('move_stage_unavailable',c.plan,area='L1',name=stage.name)
        stage.chmod(0o600);os.link(stage,stage.parent/'link');self.error('move_stage_unavailable',c.plan,area='L1',name=stage.name)
        self.assertEqual(neighbor.read_bytes(),b'keep')
    def test_tampered_plan_stage_state_and_busy_lock(self):
        root,layout,files,before,raw,pin,neighbor=self.fixture();stage=self.stage(files,raw,pin,'L1');marker=root/'.domain-agent-kit/.move-pending'
        c=self.session(layout,raw,pin);p=c.plan(area='L1',name=stage.name);changed=copy.deepcopy(p);changed['name']='different'
        self.error('plan_mismatch',c.apply,changed,confirmed_ticket=p['ticket']);self.error('ticket_unknown',self.apply,c,p);self.assertTrue(stage.exists())
        c=self.session(layout,raw,pin);p=c.plan(area='L1',name=stage.name);stage.write_bytes(b'foreign')
        self.error('move_stage_unavailable',self.apply,c,p);self.assertTrue(stage.exists());stage.write_bytes(move_intent._verified(raw,pin)[2]['L1'][:5])
        c=self.session(layout,raw,pin);p=c.plan(area='L1',name=stage.name);files['L0'].write_bytes(before['L0']+b' ')
        self.error('stale_plan',self.apply,c,p);self.assertTrue(stage.exists());files['L0'].write_bytes(before['L0'])
        c=self.session(layout,raw,pin);p=c.plan(area='L1',name=stage.name);fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
        try:
            store.fcntl.flock(fd,store.fcntl.LOCK_EX|store.fcntl.LOCK_NB);self.error('write_busy',self.apply,c,p)
        finally:os.close(fd)
        self.assertTrue(stage.exists());self.assertTrue(marker.exists())
    def test_replaced_stage_and_wrong_or_changed_marker_rejected(self):
        root,layout,files,before,raw,pin,neighbor=self.fixture();stage=self.stage(files,raw,pin,'L1');marker=root/'.domain-agent-kit/.move-pending'
        c=self.session(layout,raw,pin);p=c.plan(area='L1',name=stage.name);data=stage.read_bytes();stage.rename(stage.parent/'retained');stage.write_bytes(data);stage.chmod(0o600)
        self.error('stale_plan',self.apply,c,p);self.assertTrue(stage.exists());self.assertEqual(marker.read_bytes(),raw)
        c=self.session(layout,raw,'0'*64);self.error('move_intent_pin_mismatch',c.plan,area='L1',name=stage.name)
        c=self.session(layout,raw,pin);p=c.plan(area='L1',name=stage.name);marker.write_bytes(raw+b'foreign')
        self.error('move_intent_pin_mismatch',self.apply,c,p);self.assertTrue(stage.exists())
    def test_refuse_impossible_or_foreign_registry_state(self):
        for kind in ('impossible','foreign'):
            with self.subTest(kind=kind):
                root,layout,files,before,raw,pin,neighbor=self.fixture(complete=False);_,_,after=move_intent._verified(raw,pin)
                stage=self.stage(files,raw,pin,'L1');files['L1'].write_bytes(after['L1'] if kind=='impossible' else b'foreign')
                self.error('move_stage_stale',self.session(layout,raw,pin).plan,area='L1',name=stage.name);self.assertTrue(stage.exists())
    def test_unknown_unlink_and_fsync_never_remove_marker(self):
        for kind in ('unlink','fsync'):
            with self.subTest(kind=kind):
                root,layout,files,before,raw,pin,neighbor=self.fixture();stage=self.stage(files,raw,pin,'L2');marker=root/'.domain-agent-kit/.move-pending'
                current={k:p.read_bytes() for k,p in files.items()};c=self.session(layout,raw,pin);p=c.plan(area='L2',name=stage.name)
                with patch.object(cleanup.os,kind,side_effect=OSError('synthetic')):self.error('move_stage_cleanup_unknown',self.apply,c,p)
                self.assertEqual(stage.exists(),kind=='unlink');self.assertEqual(marker.read_bytes(),raw);self.assertEqual({k:p.read_bytes() for k,p in files.items()},current)
    def test_exit_before_and_after_unlink(self):
        program=r'''import os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1]);from kit import move_stage_cleanup as m
from kit.base.registry_store import Layout
raw=bytes.fromhex(sys.argv[3]);s=m.MoveStageCleanupSession(Layout(Path(sys.argv[2]),'profiles/pilot'),intent_bytes=raw,intent_pin=sys.argv[4]);p=s.plan(area='L1',name=sys.argv[5]);where=sys.argv[6]
real=os.unlink
def stop(*a,**kw):
 if where=='before':os._exit(77)
 real(*a,**kw);os._exit(77)
os.unlink=stop;s.apply(p,confirmed_ticket=p['ticket']);os._exit(3)
'''
        for point in ('before','after'):
            with self.subTest(point=point):
                root,layout,files,before,raw,pin,neighbor=self.fixture();stage=self.stage(files,raw,pin,'L1');marker=root/'.domain-agent-kit/.move-pending'
                current={k:p.read_bytes() for k,p in files.items()}
                p=subprocess.run([sys.executable,'-I','-S','-B','-c',program,str(ROOT),str(root),raw.hex(),pin,stage.name,point],capture_output=True,timeout=20)
                self.assertEqual(p.returncode,77,p.stderr);self.assertEqual(stage.exists(),point=='before');self.assertEqual(marker.read_bytes(),raw)
                self.assertEqual({k:p.read_bytes() for k,p in files.items()},current);self.error('move_pending',store.status,layout)

if __name__=='__main__':unittest.main()
