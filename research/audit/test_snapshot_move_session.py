#!/usr/bin/env python3
"""Закреплённая move-сессия: только временные синтетические каталоги и процессы."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'research/audit')]
import core_audit as audit
import test_snapshot_session as snapshot_fixtures
from kit import init_workspace as init
from kit.base import registry_store as store

RUNNER=ROOT/'kit/snapshot_move_session.py'

@unittest.skipUnless(init._supported() and store.fcntl is not None and os.rename in os.supports_dir_fd and os.listdir in os.supports_fd,'POSIX unavailable; not_run')
class SnapshotMoveTests(unittest.TestCase):
    def setUp(self):
        self.ctx=snapshot_fixtures.SnapshotTests();self.ctx.setUp();self.addCleanup(self.ctx.doCleanups)
        self.root=self.ctx.workspace;self.profile=self.ctx.profile;self.l0=self.ctx.l0
        doc=json.loads(self.profile.read_bytes());doc['entries'].append(audit.entry('SOURCE','rule','profile_owner','C-1','docs',state='active'));audit.write(self.profile,doc)
        self.project=self.root/'.domain-agent-kit/project/registry.json'
        for path in (self.l0,self.profile,self.project):path.chmod(0o600)
        self.marker=self.root/'.domain-agent-kit/.move-pending'
        self.ctx.args=self.args
    def args(self,*,manifest_pin=None,system_pin=None,flags=('-I','-S','-B'),candidate=None,workspace=None):
        return [sys.executable,*flags,str(RUNNER),'--candidate-root',str(candidate or self.ctx.candidate),
                '--workspace',str(workspace or self.root),'--profile-root','profiles/pilot',
                '--manifest-pin',self.ctx.manifest_pin if manifest_pin is None else manifest_pin,
                '--system-pin',self.ctx.system_pin if system_pin is None else system_pin]
    def launch(self):
        box=[]
        def close_streams():
            for proc in box:
                for stream in (proc.stdin,proc.stdout,proc.stderr):
                    if stream is not None and not stream.closed:stream.close()
        self.ctx.addCleanup(close_streams)
        proc,lines=self.ctx.launch();box.append(proc);return proc,lines
    def send(self,proc,lines,data):return self.ctx.send(proc,lines,data)
    def configure(self,proc,lines):
        candidate=audit.entry('TARGET','rule','project_owner','P-1','docs',state='draft')
        built=self.send(proc,lines,{'type':'build','source':'L1','target':'L2','entry_id':'SOURCE','candidate':candidate,'portability_context':None})
        self.assertEqual(built['outcome'],'intent_draft_only',built)
        response=self.send(proc,lines,{'type':'configure','intent_utf8':built['intent_utf8'],'intent_pin':built['intent_sha256']})
        self.assertEqual(response['outcome'],'configured');return built
    def plan(self,proc,lines,action):
        res=self.send(proc,lines,{'type':'plan','action':action});self.assertEqual(res['outcome'],'planned',res);return res['plan']
    def apply(self,proc,lines,p):return self.send(proc,lines,{'type':'apply','plan':p,'confirmed_ticket':p['ticket']})
    def refuse(self,args):
        result=subprocess.run(args,input='',capture_output=True,text=True,timeout=25)
        self.assertEqual(result.returncode,1,result.stderr);self.assertEqual(result.stdout,'')
        return json.loads(result.stderr)
    def test_complete_through_marker_with_pinned_code_and_l0(self):
        hostile=self.root/'kit/base/move_intent.py';hostile.write_text('from pathlib import Path\nPath('+repr(str(self.ctx.marker))+').touch()\n')
        proc,lines=self.launch();self.configure(proc,lines)
        p=self.plan(proc,lines,'reserve');self.assertEqual(self.apply(proc,lines,p)['outcome'],'reserved_not_moved');self.assertTrue(self.marker.exists())
        self.assertEqual(self.send(proc,lines,{'type':'inspect'})['state'],'before_both')
        p=self.plan(proc,lines,'execute');self.assertEqual(self.apply(proc,lines,p)['outcome'],'registries_updated_marker_retained')
        p=self.plan(proc,lines,'finalize');self.assertEqual(self.apply(proc,lines,p)['outcome'],'marker_removed_after_both')
        self.assertFalse(self.marker.exists());self.assertFalse(self.ctx.marker.exists());self.assertIsInstance(store.status(self.ctx.layout),dict)
    def test_preflight_changed_candidate_revokes_plan_and_intent(self):
        proc,lines=self.launch();self.configure(proc,lines);p=self.plan(proc,lines,'reserve')
        path=self.ctx.candidate/'kit/base/schema_v2.py';original=path.read_bytes();path.write_bytes(original+b'\n# changed\n')
        self.assertEqual(self.apply(proc,lines,p),{'outcome':'error','code':'runtime_preflight_failed'});self.assertFalse(self.marker.exists())
        path.write_bytes(original)
        self.assertEqual(self.apply(proc,lines,p)['diagnostic']['code'],'ticket_unknown')
        self.assertEqual(self.send(proc,lines,{'type':'inspect'})['diagnostic']['code'],'move_intent_required')
    def test_l0_drift_and_busy_lock_revoke_plan(self):
        proc,lines=self.launch();self.configure(proc,lines);p=self.plan(proc,lines,'reserve');original=self.l0.read_bytes();self.l0.write_bytes(original+b' ')
        self.assertEqual(self.apply(proc,lines,p),{'outcome':'error','code':'runtime_preflight_failed'});self.assertFalse(self.marker.exists());self.l0.write_bytes(original)
        self.assertEqual(self.apply(proc,lines,p)['diagnostic']['code'],'ticket_unknown')
        self.configure(proc,lines);p=self.plan(proc,lines,'reserve');fd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY)
        try:
            store.fcntl.flock(fd,store.fcntl.LOCK_EX|store.fcntl.LOCK_NB)
            self.assertEqual(self.apply(proc,lines,p),{'outcome':'error','code':'runtime_preflight_failed'})
        finally:os.close(fd)
        self.assertEqual(self.apply(proc,lines,p)['diagnostic']['code'],'ticket_unknown');self.assertFalse(self.marker.exists())
    def test_start_with_existing_marker_and_restored_external_intent(self):
        proc,lines=self.launch();built=self.configure(proc,lines);p=self.plan(proc,lines,'reserve');self.apply(proc,lines,p)
        proc.stdin.close();self.assertEqual(proc.wait(timeout=20),0)
        next_proc,next_lines=self.launch()
        response=self.send(next_proc,next_lines,{'type':'configure','intent_utf8':built['intent_utf8'],'intent_pin':built['intent_sha256']})
        self.assertEqual(response['outcome'],'configured');self.assertEqual(self.send(next_proc,next_lines,{'type':'inspect'})['state'],'before_both')
        p=self.plan(next_proc,next_lines,'cancel_reservation');self.assertEqual(self.apply(next_proc,next_lines,p)['outcome'],'reservation_cancelled')
    def test_partial_marker_can_be_cancelled_after_new_preflight(self):
        proc,lines=self.launch();built=self.configure(proc,lines);p=self.plan(proc,lines,'reserve');self.apply(proc,lines,p)
        self.marker.write_bytes(built['intent_utf8'].encode()[:7]);self.assertTrue(self.marker.exists())
        p=self.plan(proc,lines,'cancel_partial');self.assertEqual(p['marker_bytes'],7)
        self.assertEqual(self.apply(proc,lines,p)['outcome'],'partial_marker_removed');self.assertFalse(self.marker.exists())
        self.assertIsInstance(store.status(self.ctx.layout),dict)
    def test_bad_pins_isolation_tamper_and_overlap_refuse(self):
        for args,reason in ((self.args(manifest_pin='bad'),'pin_required'),(self.args(system_pin='0'*64),'runtime_unverified'),
                            (self.args(flags=('-B',)),'isolated_python_required'),(self.args(candidate=self.root),'roots_invalid_or_overlap')):
            with self.subTest(reason=reason):self.assertEqual(self.refuse(args)['reason'],reason)
        path=self.ctx.candidate/'kit/move_execution.py';path.write_bytes(path.read_bytes()+b'\n# modified\n')
        self.assertEqual(self.refuse(self.args())['reason'],'candidate_unverified')
    def test_l0_symlink_and_wrong_version_refused(self):
        raw=self.l0.read_bytes();doc=json.loads(raw);doc['release_version']='0.2.0-other';audit.write(self.l0,doc)
        self.ctx.system_pin=hashlib.sha256(self.l0.read_bytes()).hexdigest();self.assertEqual(self.refuse(self.args())['reason'],'runtime_unverified')
        self.l0.unlink();self.l0.symlink_to(self.ctx.candidate/'kit/SYSTEM-L0.json')
        self.ctx.system_pin=hashlib.sha256((self.ctx.candidate/'kit/SYSTEM-L0.json').read_bytes()).hexdigest()
        self.assertEqual(self.refuse(self.args())['reason'],'runtime_unverified')

if __name__=='__main__':unittest.main()
