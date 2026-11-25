#!/usr/bin/env python3
"""Резервирование без перемещения, только новые синтетические деревья."""
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
from kit import move_reservation as reservation, move_recovery_inspect as probe, init_workspace as init
from kit.base import move_intent, registry_store as store
from kit.base.registry_policy import StoreError

@unittest.skipUnless(init._supported() and store.fcntl is not None,'POSIX lock/dirfd/xattr unsupported; not_run')
class ReservationTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(prefix='move-reservation-');self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name).resolve();self.layout=audit.make_workspace(self.root,parent_scope='.')
        self.files={'L0':self.root/'kit/base/registry.json','L1':self.root/'profiles/pilot/registry.json',
                    'L2':self.root/'.domain-agent-kit/project/registry.json'}
        for area,parent,auth in (('L1','C-1','profile_owner'),('L2','P-1','project_owner')):
            doc=json.loads(self.files[area].read_bytes());doc['entries'].append(audit.entry('SRC-'+area,'rule',auth,parent,'docs',state='active'));audit.write(self.files[area],doc)
        self.before={k:v.read_bytes() for k,v in self.files.items()};self.neighbor=self.root/'neighbor';self.neighbor.write_bytes(b'keep')
        self.marker=self.root/'.domain-agent-kit/.move-pending'
    def new(self,src='L1'):
        dst='L2' if src=='L1' else 'L1';auth='project_owner' if dst=='L2' else 'profile_owner';parent='P-1' if dst=='L2' else 'C-1'
        candidate=audit.entry('DST-'+src,'rule',auth,parent,'docs',state='draft',text='SYNTHETIC_SECRET')
        report,raw=move_intent.build(self.before,source=src,target=dst,entry_id='SRC-'+src,candidate=candidate,
                   portability_context=None if src=='L1' else {'project_names':[],'machine_names':[],'project_paths':[]})
        return reservation.ReservationSession(self.layout,intent_bytes=raw,intent_pin=report['intent_sha256']),raw,report['intent_sha256']
    def error(self,code,fn,*args,**kw):
        with self.assertRaises(StoreError) as e:fn(*args,**kw)
        self.assertEqual(e.exception.code,code)
    def apply(self,s,p):return s.apply(p,confirmed_ticket=p['ticket'])
    def original(self):
        self.assertEqual({k:v.read_bytes() for k,v in self.files.items()},self.before);self.assertEqual(self.neighbor.read_bytes(),b'keep')
    def test_reserve_and_separately_cancel_in_both_directions(self):
        for src in ('L1','L2'):
            with self.subTest(src=src):
                s,raw,pin=self.new(src);plan=s.plan(action='reserve');self.assertFalse(self.marker.exists())
                self.assertEqual(plan['intent_utf8'].encode(),raw);self.assertEqual(plan['move'],'not_implemented')
                self.error('confirmation_required',s.apply,plan,confirmed_ticket='wrong');self.assertFalse(self.marker.exists())
                self.assertEqual(self.apply(s,plan)['outcome'],'reserved_not_moved');self.original()
                self.assertEqual(self.marker.read_bytes(),raw);self.error('move_pending',store.status,self.layout)
                self.assertEqual(probe.inspect(self.layout,intent_pin=pin)['state'],'before_both')
                other=reservation.ReservationSession(self.layout,intent_bytes=raw,intent_pin=pin);cancel=other.plan(action='cancel')
                self.error('confirmation_required',other.apply,cancel,confirmed_ticket='bad');self.assertEqual(self.marker.read_bytes(),raw)
                self.assertEqual(self.apply(other,cancel)['outcome'],'reservation_cancelled')
                self.assertFalse(self.marker.exists());self.assertEqual(store.status(self.layout)['profile_revision'],0);self.original()
    def test_tampered_plan_ticket_inputs_and_marker_refuse(self):
        s,raw,pin=self.new();plan=s.plan(action='reserve');changed=copy.deepcopy(plan);changed['intent_utf8']+='x'
        self.error('plan_mismatch',s.apply,changed,confirmed_ticket=plan['ticket']);self.assertFalse(self.marker.exists())
        s,raw,pin=self.new();plan=s.plan(action='reserve');self.files['L0'].write_bytes(self.before['L0']+b' ')
        self.error('stale_plan',self.apply,s,plan);self.assertFalse(self.marker.exists());self.files['L0'].write_bytes(self.before['L0'])
        s,raw,pin=self.new();plan=s.plan(action='reserve');self.marker.symlink_to(self.neighbor)
        self.error('move_pending',self.apply,s,plan);self.assertEqual(self.neighbor.read_bytes(),b'keep');self.marker.unlink()
        s,raw,pin=self.new();plan=s.plan(action='reserve');s.intent_pin='0'*64
        self.error('stale_plan',self.apply,s,plan);self.assertFalse(self.marker.exists());self.original()
    def test_same_bytes_under_replaced_project_root_are_stale(self):
        s,raw,pin=self.new();plan=s.plan(action='reserve')
        project=self.root/'.domain-agent-kit';prior=self.root/'old-project';project.rename(prior)
        shutil.copytree(prior,project)
        self.error('stale_plan',self.apply,s,plan)
        self.assertFalse(self.marker.exists());self.original()

    def test_cancel_refuses_other_state_changed_data_wrong_pin_and_modified_marker(self):
        for changed in ('L0','L1','L2','marker'):
            with self.subTest(changed=changed):
                s,raw,pin=self.new();self.assertEqual(self.apply(s,s.plan(action='reserve'))['outcome'],'reserved_not_moved')
                cancel=reservation.ReservationSession(self.layout,intent_bytes=raw,intent_pin=pin);plan=cancel.plan(action='cancel')
                path=self.marker if changed=='marker' else self.files[changed];prior=path.read_bytes();path.write_bytes(prior+b'changed')
                self.error('move_intent_pin_mismatch' if changed=='marker' else 'move_reservation_stale',self.apply,cancel,plan)
                self.assertTrue(self.marker.exists());self.assertEqual(path.read_bytes(),prior+b'changed')
                path.write_bytes(prior)
                retry=reservation.ReservationSession(self.layout,intent_bytes=raw,intent_pin=pin)
                self.assertEqual(self.apply(retry,retry.plan(action='cancel'))['outcome'],'reservation_cancelled');self.original()
        s,raw,pin=self.new();self.apply(s,s.plan(action='reserve'))
        wrong=reservation.ReservationSession(self.layout,intent_bytes=raw,intent_pin='0'*64)
        self.error('move_intent_pin_mismatch',wrong.plan,action='cancel');self.assertEqual(self.marker.read_bytes(),raw)
    def test_partial_write_and_fsync_errors_leave_barrier(self):
        for kind in ('write','fsync_file','fsync_dir','xattr'):
            with self.subTest(kind=kind):
                s,raw,pin=self.new();p=s.plan(action='reserve');real=os.fsync;calls=[]
                if kind=='write':mock=patch.object(reservation.os,'write',side_effect=OSError('synthetic'))
                elif kind=='xattr':mock=patch.object(init.os,'listxattr',return_value=['user.synthetic'])
                else:
                    def fail(fd):
                        calls.append(fd)
                        if len(calls)==(1 if kind=='fsync_file' else 2):raise OSError('synthetic')
                        return real(fd)
                    mock=patch.object(reservation.os,'fsync',side_effect=fail)
                with mock:self.error('move_reservation_unknown',self.apply,s,p)
                self.assertTrue(self.marker.exists());self.error('move_pending',store.status,self.layout);self.original()
                # Уборка только собственного временного синтетического объекта между пробами.
                self.marker.unlink()
    def test_cancel_refuses_intermediate_or_final_move_and_marker_metadata(self):
        s,raw,pin=self.new();self.apply(s,s.plan(action='reserve'))
        _,_,after=move_intent._verified(raw,pin)
        for area in ('L2','L1'):
            self.files[area].write_bytes(after[area])
            other=reservation.ReservationSession(self.layout,intent_bytes=raw,intent_pin=pin)
            self.error('move_reservation_stale',other.plan,action='cancel')
            self.assertEqual(self.marker.read_bytes(),raw)
        for area in ('L1','L2'):self.files[area].write_bytes(self.before[area])
        other=reservation.ReservationSession(self.layout,intent_bytes=raw,intent_pin=pin);plan=other.plan(action='cancel')
        with patch.object(init.os,'listxattr',return_value=['user.synthetic']):
            self.error('move_cancel_unavailable',self.apply,other,plan)
        self.assertEqual(self.marker.read_bytes(),raw);self.original()
        self.marker.chmod(0o644);other=reservation.ReservationSession(self.layout,intent_bytes=raw,intent_pin=pin)
        plan=other.plan(action='cancel');self.error('move_cancel_unavailable',self.apply,other,plan)
        self.assertEqual(self.marker.read_bytes(),raw);self.original()

    def test_cancel_unlink_failure_keeps_marker_and_reports_unknown(self):
        s,raw,pin=self.new();self.apply(s,s.plan(action='reserve'))
        other=reservation.ReservationSession(self.layout,intent_bytes=raw,intent_pin=pin);plan=other.plan(action='cancel')
        with patch.object(reservation.os,'unlink',side_effect=OSError('synthetic')):
            self.error('move_cancel_unknown',self.apply,other,plan)
        self.assertEqual(self.marker.read_bytes(),raw);self.original();self.error('move_pending',store.status,self.layout)

    def test_cancel_fsync_error_is_unknown_and_never_changes_registries(self):
        s,raw,pin=self.new();self.apply(s,s.plan(action='reserve'))
        other=reservation.ReservationSession(self.layout,intent_bytes=raw,intent_pin=pin);plan=other.plan(action='cancel')
        with patch.object(reservation.os,'fsync',side_effect=OSError('synthetic')):
            self.error('move_cancel_unknown',self.apply,other,plan)
        self.assertFalse(self.marker.exists());self.original()
    def test_competing_writer_prevents_both_reserve_and_cancel(self):
        s,raw,pin=self.new();p=s.plan(action='reserve');fd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY)
        try:
            store.fcntl.flock(fd,store.fcntl.LOCK_EX|store.fcntl.LOCK_NB)
            self.error('write_busy',self.apply,s,p);self.assertFalse(self.marker.exists())
        finally:os.close(fd)
        s,raw,pin=self.new();self.apply(s,s.plan(action='reserve'))
        other=reservation.ReservationSession(self.layout,intent_bytes=raw,intent_pin=pin);p=other.plan(action='cancel')
        fd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY)
        try:
            store.fcntl.flock(fd,store.fcntl.LOCK_EX|store.fcntl.LOCK_NB)
            self.error('write_busy',self.apply,other,p);self.assertEqual(self.marker.read_bytes(),raw)
        finally:os.close(fd)
        self.original()

    def test_abrupt_exit_after_marker_and_cancel_fsync(self):
        program=r'''import json,os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1]);from kit import move_reservation as m
from kit.base.registry_store import Layout
raw=bytes.fromhex(sys.argv[3]);s=m.ReservationSession(Layout(Path(sys.argv[2]),'profiles/pilot'),intent_bytes=raw,intent_pin=sys.argv[4]);action=sys.argv[5];p=s.plan(action=action);print(json.dumps({'planned':True}),flush=True)
real=os.fsync;count=[0]
def die(fd):
 real(fd);count[0]+=1
 if count[0]==int(sys.argv[6]):os._exit(77)
os.fsync=die;s.apply(p,confirmed_ticket=p['ticket']);os._exit(3)
'''
        for action,number in (('reserve',1),('reserve',2),('cancel',1)):
            with self.subTest(action=action,sync=number):
                s,raw,pin=self.new()
                if action=='cancel':self.apply(s,s.plan(action='reserve'))
                proc=subprocess.run([sys.executable,'-I','-S','-B','-c',program,str(ROOT),str(self.root),raw.hex(),pin,action,str(number)],capture_output=True,text=True,timeout=15)
                self.assertEqual(proc.returncode,77,proc.stderr);self.assertEqual(json.loads(proc.stdout),{'planned':True});self.original()
                if action=='reserve':
                    self.assertEqual(self.marker.read_bytes(),raw);self.error('move_pending',store.status,self.layout)
                    other=reservation.ReservationSession(self.layout,intent_bytes=raw,intent_pin=pin)
                    self.assertEqual(self.apply(other,other.plan(action='cancel'))['outcome'],'reservation_cancelled')
                else:self.assertFalse(self.marker.exists())

    def test_actual_exit_during_reservation_preserves_barrier(self):
        program=r'''import json,os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1]);from kit import move_reservation as m
from kit.base.registry_store import Layout
raw=bytes.fromhex(sys.argv[3]);s=m.ReservationSession(Layout(Path(sys.argv[2]),'profiles/pilot'),intent_bytes=raw,intent_pin=sys.argv[4]);p=s.plan(action='reserve');print(json.dumps({'planned':True}),flush=True)
real=os.write
def die(fd,data):real(fd,data[:len(data)//2]);os._exit(77)
os.write=die;s.apply(p,confirmed_ticket=p['ticket']);os._exit(3)
'''
        s,raw,pin=self.new();proc=subprocess.run([sys.executable,'-I','-S','-B','-c',program,str(ROOT),str(self.root),raw.hex(),pin],capture_output=True,text=True,timeout=15)
        self.assertEqual(proc.returncode,77,proc.stderr);self.assertEqual(json.loads(proc.stdout),{'planned':True})
        self.assertEqual(self.marker.read_bytes(),raw[:len(raw)//2]);self.original();self.error('move_pending',store.status,self.layout)
        self.error('move_intent_pin_mismatch',s.plan,action='cancel');self.assertTrue(self.marker.exists())

if __name__=='__main__':unittest.main()
