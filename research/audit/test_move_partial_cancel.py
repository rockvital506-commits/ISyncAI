#!/usr/bin/env python3
"""Отмена неполного маркера только в новых синтетических деревьях."""
import copy
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'research/audit')]
import test_move_execution as fixtures
import test_move_reservation as reserve_fixtures
from kit import init_workspace as init, move_partial_cancel as partial, move_reservation as reservation
from kit.base import move_intent, registry_store as store
from kit.base.registry_policy import StoreError

@unittest.skipUnless(init._supported() and store.fcntl is not None and os.listdir in os.supports_fd,'POSIX unavailable; not_run')
class PartialCancelTests(unittest.TestCase):
    def fixture(self,src='L1',length=5):
        helper=fixtures.ExecutionTests();self.addCleanup(helper.doCleanups)
        root,layout,files,before,raw,pin,neighbor=helper.fixture(src)
        marker=root/'.domain-agent-kit/.move-pending';marker.write_bytes(raw[:length]);marker.chmod(0o600)
        return root,layout,files,before,raw,pin,neighbor,marker
    def session(self,layout,raw,pin):return partial.PartialReservationCancelSession(layout,intent_bytes=raw,intent_pin=pin)
    def error(self,code,fn,*args,**kwargs):
        with self.assertRaises(StoreError) as err:fn(*args,**kwargs)
        self.assertEqual(err.exception.code,code)
    def apply(self,s,p):return s.apply(p,confirmed_ticket=p['ticket'])
    def test_actual_partial_write_both_directions_then_cancel(self):
        for src in ('L1','L2'):
            with self.subTest(src=src):
                h=reserve_fixtures.ReservationTests();h.setUp();self.addCleanup(h.doCleanups)
                s,raw,pin=h.new(src);plan=s.plan(action='reserve');real=os.write
                def fail(fd,data):real(fd,data[:9]);raise OSError('synthetic')
                with patch.object(reservation.os,'write',side_effect=fail):self.error('move_reservation_unknown',s.apply,plan,confirmed_ticket=plan['ticket'])
                self.assertEqual(h.marker.read_bytes(),raw[:9]);self.error('move_pending',store.status,h.layout)
                c=self.session(h.layout,raw,pin);p=c.plan();self.assertEqual(p['marker_bytes'],9);self.assertEqual(p['origin'],'not_verified')
                self.error('confirmation_required',c.apply,p,confirmed_ticket='wrong');self.assertTrue(h.marker.exists())
                self.assertEqual(self.apply(c,p)['outcome'],'partial_marker_removed');self.assertFalse(h.marker.exists());h.original()
                self.assertIsInstance(store.status(h.layout),dict)
    def test_empty_near_complete_and_full_refusal(self):
        for length in (0,1,100000000):
            with self.subTest(length=length):
                root,layout,files,before,raw,pin,neighbor,marker=self.fixture(length=length);s=self.session(layout,raw,pin)
                if length>=len(raw):self.error('move_partial_unavailable',s.plan);self.assertEqual(marker.read_bytes(),raw)
                else:
                    p=s.plan();self.assertEqual(p['marker_bytes'],length);self.apply(s,p);self.assertFalse(marker.exists())
                    self.assertEqual({k:f.read_bytes() for k,f in files.items()},before);self.assertEqual(neighbor.read_bytes(),b'keep')
    def test_nonprefix_wrong_pin_symlink_hardlink_metadata_and_stages(self):
        root,layout,files,before,raw,pin,neighbor,marker=self.fixture();s=self.session(layout,raw,pin)
        marker.write_bytes(b'foreign');self.error('move_partial_unavailable',s.plan);marker.write_bytes(raw[:5])
        self.error('move_intent_pin_mismatch',self.session(layout,raw,'0'*64).plan)
        marker.chmod(0o644);self.error('move_partial_unavailable',s.plan);marker.chmod(0o600)
        os.link(marker,root/'link');self.error('move_partial_unavailable',s.plan);(root/'link').unlink()
        marker.unlink();marker.symlink_to(neighbor);self.error('move_partial_unavailable',s.plan);marker.unlink();marker.write_bytes(raw[:5]);marker.chmod(0o600)
        stage=files['L1'].parent/'.move-stage-unknown';stage.write_bytes(b'secret');self.error('move_stages_present',s.plan)
        self.assertEqual(stage.read_bytes(),b'secret');self.assertEqual(neighbor.read_bytes(),b'keep');self.assertEqual(marker.read_bytes(),raw[:5])
    def test_changed_any_registry_refused(self):
        for area in ('L0','L1','L2'):
            with self.subTest(area=area):
                root,layout,files,before,raw,pin,neighbor,marker=self.fixture();files[area].write_bytes(before[area]+b' ')
                self.error('move_partial_stale',self.session(layout,raw,pin).plan);self.assertTrue(marker.exists())
    def test_plan_tamper_and_changes_after_plan_refused(self):
        root,layout,files,before,raw,pin,neighbor,marker=self.fixture();s=self.session(layout,raw,pin);p=s.plan();bad=copy.deepcopy(p);bad['marker_bytes']=100
        self.error('plan_mismatch',s.apply,bad,confirmed_ticket=p['ticket']);self.error('ticket_unknown',self.apply,s,p);self.assertTrue(marker.exists())
        s=self.session(layout,raw,pin);p=s.plan();marker.write_bytes(raw[:6]);self.error('stale_plan',self.apply,s,p);self.assertTrue(marker.exists())
        s=self.session(layout,raw,pin);p=s.plan();files['L2'].write_bytes(before['L2']+b' ');self.error('move_partial_stale',self.apply,s,p);self.assertTrue(marker.exists())
    def test_same_registry_bytes_at_wrong_profile_root_refused(self):
        root,layout,files,before,raw,pin,neighbor,marker=self.fixture()
        shutil.copytree(root/'profiles/pilot',root/'profiles/other')
        wrong=store.Layout(root,'profiles/other')
        self.error('move_probe_root_mismatch',self.session(wrong,raw,pin).plan)
        self.assertEqual(marker.read_bytes(),raw[:5]);self.assertEqual((root/'profiles/other/registry.json').read_bytes(),before['L1'])
    def test_competing_lock_blocks_planning_and_application(self):
        root,layout,files,before,raw,pin,neighbor,marker=self.fixture();s=self.session(layout,raw,pin);p=s.plan();fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
        try:
            store.fcntl.flock(fd,store.fcntl.LOCK_EX|store.fcntl.LOCK_NB);self.error('move_partial_busy',self.session(layout,raw,pin).plan)
            self.error('write_busy',self.apply,s,p)
        finally:os.close(fd)
        self.assertEqual(marker.read_bytes(),raw[:5])
    def test_unknown_unlink_and_fsync(self):
        for kind in ('unlink','fsync'):
            with self.subTest(kind=kind):
                root,layout,files,before,raw,pin,neighbor,marker=self.fixture();s=self.session(layout,raw,pin);p=s.plan()
                with patch.object(partial.os,kind,side_effect=OSError('synthetic')):self.error('move_partial_cancel_unknown',self.apply,s,p)
                self.assertEqual(marker.exists(),kind=='unlink');self.assertEqual({k:f.read_bytes() for k,f in files.items()},before)
    def test_process_exit_before_and_after_unlink(self):
        program=r'''import os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1]);from kit import move_partial_cancel as m
from kit.base.registry_store import Layout
raw=bytes.fromhex(sys.argv[3]);s=m.PartialReservationCancelSession(Layout(Path(sys.argv[2]),'profiles/pilot'),intent_bytes=raw,intent_pin=sys.argv[4]);p=s.plan();where=sys.argv[5]
real=os.unlink
def stop(*a,**kw):
 if where=='before':os._exit(77)
 real(*a,**kw);os._exit(77)
os.unlink=stop;s.apply(p,confirmed_ticket=p['ticket']);os._exit(3)
'''
        for where in ('before','after'):
            with self.subTest(where=where):
                root,layout,files,before,raw,pin,neighbor,marker=self.fixture()
                proc=subprocess.run([sys.executable,'-I','-S','-B','-c',program,str(ROOT),str(root),raw.hex(),pin,where],capture_output=True,timeout=20)
                self.assertEqual(proc.returncode,77,proc.stderr);self.assertEqual(marker.exists(),where=='before')
                self.assertEqual({k:f.read_bytes() for k,f in files.items()},before);self.assertEqual(neighbor.read_bytes(),b'keep')

if __name__=='__main__':unittest.main()
