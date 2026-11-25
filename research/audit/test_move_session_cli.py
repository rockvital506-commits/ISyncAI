#!/usr/bin/env python3
"""Опытная JSON-сессия: весь ввод и данные только из временной синтетической фикстуры."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'research/audit')]
import core_audit as audit
import test_move_execution as fixtures
from kit import init_workspace as init, move_reservation as reservation
from kit.base import registry_store as store

@unittest.skipUnless(init._supported() and store.fcntl is not None and os.rename in os.supports_dir_fd and os.listdir in os.supports_fd,'POSIX unavailable; not_run')
class MoveConsoleTests(unittest.TestCase):
    def setUp(self):
        helper=fixtures.ExecutionTests();self.addCleanup(helper.doCleanups)
        self.root,self.layout,self.files,self.before,self.raw,self.pin,self.neighbor=helper.fixture()
        r=reservation.ReservationSession(self.layout,intent_bytes=self.raw,intent_pin=self.pin)
        p=r.plan(action='cancel');r.apply(p,confirmed_ticket=p['ticket'])
        self.marker=self.root/'.domain-agent-kit/.move-pending'
        self.process=subprocess.Popen([sys.executable,'-I','-S','-B',str(ROOT/'kit/move_session_cli.py'),
             '--workspace',str(self.root),'--profile-root','profiles/pilot'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        self.addCleanup(self.stop)
    def stop(self):
        if self.process.poll() is None:self.process.kill()
        self.process.communicate(timeout=10)
    def send(self,data):
        self.process.stdin.write(json.dumps(data,ensure_ascii=False)+'\n');self.process.stdin.flush()
        line=self.process.stdout.readline();self.assertTrue(line);return json.loads(line)
    def build(self):
        candidate=audit.entry('TARGET','rule','project_owner','P-1','docs',state='draft')
        return self.send({'type':'build','source':'L1','target':'L2','entry_id':'SOURCE','candidate':candidate,'portability_context':None})
    def configure(self):
        built=self.build();self.assertEqual(built['outcome'],'intent_draft_only');self.assertFalse(built['configured'])
        response=self.send({'type':'configure','intent_utf8':built['intent_utf8'],'intent_pin':built['intent_sha256']})
        self.assertEqual(response['outcome'],'configured');return built
    def plan(self,action,**kw):
        response=self.send({'type':'plan','action':action,**kw});self.assertEqual(response['outcome'],'planned',response);return response['plan']
    def apply(self,plan):return self.send({'type':'apply','plan':plan,'confirmed_ticket':plan['ticket']})
    def test_build_export_reserve_execute_finalize_with_separate_tickets(self):
        built=self.configure()
        with tempfile.TemporaryDirectory(prefix='external-intent-') as d:
            destination=str(Path(d)/'copy.json');p=self.plan('export',destination=destination)
            self.assertEqual(self.apply(p)['outcome'],'exported_unverified_origin');self.assertEqual(Path(destination).read_bytes(),built['intent_utf8'].encode())
        p=self.plan('reserve');bad=self.send({'type':'apply','plan':p,'confirmed_ticket':'wrong'})
        self.assertEqual(bad['diagnostic']['code'],'confirmation_required');self.assertFalse(self.marker.exists())
        self.assertEqual(self.apply(p)['outcome'],'reserved_not_moved');self.assertEqual(self.send({'type':'inspect'})['state'],'before_both')
        p=self.plan('execute');self.assertEqual(self.apply(p)['outcome'],'registries_updated_marker_retained');self.assertTrue(self.marker.exists())
        self.assertEqual(self.send({'type':'inspect'})['state'],'after_both')
        p=self.plan('finalize');self.assertEqual(self.apply(p)['outcome'],'marker_removed_after_both');self.assertFalse(self.marker.exists())
        self.assertEqual(self.files['L0'].read_bytes(),self.before['L0']);self.assertEqual(self.neighbor.read_bytes(),b'keep')
        self.assertIsInstance(store.status(self.layout),dict)
    def test_other_commands_and_invalid_input_revoke_pending(self):
        self.configure();p=self.plan('reserve');self.assertEqual(self.send({'type':'cancel'})['outcome'],'plan_cancelled')
        self.assertEqual(self.apply(p)['diagnostic']['code'],'ticket_unknown');self.assertFalse(self.marker.exists())
        p=self.plan('reserve');self.assertEqual(self.send({'type':'unknown'})['code'],'invalid_request')
        self.assertEqual(self.apply(p)['diagnostic']['code'],'ticket_unknown');self.assertFalse(self.marker.exists())
        p=self.plan('reserve');bad=copy.deepcopy(p);bad['effect']='different'
        self.assertEqual(self.send({'type':'apply','plan':bad,'confirmed_ticket':p['ticket']})['diagnostic']['code'],'plan_mismatch')
        self.assertEqual(self.apply(p)['diagnostic']['code'],'ticket_unknown');self.assertFalse(self.marker.exists())
    def test_configuration_and_intent_pin_are_required(self):
        self.assertEqual(self.send({'type':'plan','action':'reserve'})['diagnostic']['code'],'move_intent_required')
        built=self.build();bad=self.send({'type':'configure','intent_utf8':built['intent_utf8'],'intent_pin':'0'*64})
        self.assertEqual(bad['diagnostic']['code'],'move_intent_pin_mismatch')
        self.assertEqual(self.send({'type':'plan','action':'reserve'})['diagnostic']['code'],'move_intent_required')
    def test_duplicate_json_invalidates_plan(self):
        self.configure();p=self.plan('reserve')
        self.process.stdin.write('{"type":"cancel","type":"cancel"}\n');self.process.stdin.flush()
        self.assertEqual(json.loads(self.process.stdout.readline())['code'],'invalid_request')
        self.assertEqual(self.apply(p)['diagnostic']['code'],'ticket_unknown');self.assertFalse(self.marker.exists())
    def test_restart_with_separately_saved_intent_and_pin(self):
        built=self.configure();p=self.plan('reserve');self.apply(p);self.assertTrue(self.marker.exists())
        self.process.stdin.close();self.assertEqual(self.process.wait(timeout=10),0);self.process.stdout.close();self.process.stderr.close()
        self.process=subprocess.Popen([sys.executable,'-I','-S','-B',str(ROOT/'kit/move_session_cli.py'),
             '--workspace',str(self.root),'--profile-root','profiles/pilot'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        self.assertEqual(self.send({'type':'configure','intent_utf8':built['intent_utf8'],'intent_pin':built['intent_sha256']})['outcome'],'configured')
        self.assertEqual(self.send({'type':'inspect'})['state'],'before_both');p=self.plan('execute');self.apply(p)
        p=self.plan('finalize');self.assertEqual(self.apply(p)['outcome'],'marker_removed_after_both');self.assertFalse(self.marker.exists())
    def test_cancel_partial_and_cleanup_stage_routes(self):
        built=self.configure();p=self.plan('reserve');self.assertEqual(self.apply(p)['outcome'],'reserved_not_moved')
        self.marker.write_bytes(built['intent_utf8'].encode()[:5]);p=self.plan('cancel_partial')
        self.assertEqual(self.apply(p)['outcome'],'partial_marker_removed');self.assertFalse(self.marker.exists())
        p=self.plan('reserve');self.apply(p);p=self.plan('execute');self.apply(p)
        from kit.base import move_intent
        _,_,after=move_intent._verified(built['intent_utf8'].encode(),built['intent_sha256'])
        stage=self.files['L1'].parent/('.move-stage-'+'a'*32);stage.write_bytes(after['L1'][:7]);stage.chmod(0o600)
        self.assertEqual(self.send({'type':'plan','action':'finalize'})['diagnostic']['code'],'move_stages_present')
        p=self.plan('cleanup_stage',area='L1',name=stage.name);self.assertEqual(self.apply(p)['outcome'],'selected_stage_removed')
        p=self.plan('finalize');self.assertEqual(self.apply(p)['outcome'],'marker_removed_after_both')
    def test_oversized_request_stops_without_fragment_commands(self):
        program='import sys;sys.path.insert(0,sys.argv[1]);from kit import move_session_cli as m;m.MAX_LINE=64;sys.argv=["session","--workspace",sys.argv[2],"--profile-root","profiles/pilot"];raise SystemExit(m.main())'
        proc=subprocess.run([sys.executable,'-I','-S','-B','-c',program,str(ROOT),str(self.root)],input='x'*65+'\\n'+json.dumps({'type':'cancel'})+'\\n',text=True,capture_output=True,timeout=15)
        self.assertEqual(proc.returncode,1);self.assertEqual([json.loads(line) for line in proc.stdout.splitlines()],[{'outcome':'error','code':'input_too_large'}])
        self.assertFalse(self.marker.exists())
    def test_explicit_reservation_cancel_route(self):
        self.configure();p=self.plan('reserve');self.apply(p);p=self.plan('cancel_reservation')
        self.assertEqual(self.apply(p)['outcome'],'reservation_cancelled');self.assertFalse(self.marker.exists())
        self.assertEqual({k:f.read_bytes() for k,f in self.files.items()},self.before)

if __name__=='__main__':unittest.main()
