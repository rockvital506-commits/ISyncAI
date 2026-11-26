#!/usr/bin/env python3
"""Синтетическая изолированная сессия установки; не реальная доставка."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'research/audit')]
import test_release_archive_publish_cli_study as fixture
import test_atomic_init as atomic
import test_source_release_trust as signing


@unittest.skipUnless(signing.SUPPORTED and atomic.SUPPORTED,'OpenSSL/Linux unavailable; not_run')
class InstallCliTests(unittest.TestCase):
    def setUp(self):
        self.fx=fixture.PublishCliTests();self.fx.setUp();self.addCleanup(self.fx.doCleanups)
        cmd=self.fx.args();cmd[4]=str(ROOT/'research/audit/release_install_cli_study.py')
        self.cmd=cmd+['--profile-root','profiles/pilot']
    def start(self):return self.fx.start(self.cmd)
    def send(self,proc,req):return self.fx.send(proc,req)
    def test_signed_install_to_first_confirmed_operation(self):
        proc=self.start();p=self.send(proc,{'type':'plan'});self.assertEqual(p['outcome'],'planned',p)
        self.assertFalse(self.fx.dest.exists())
        self.assertEqual(self.send(proc,{'type':'apply','plan':p,'confirmed_ticket':'bad'})['code'],'confirmation_required')
        r=self.send(proc,{'type':'apply','plan':p,'confirmed_ticket':p['ticket']})
        self.assertEqual(r['outcome'],'study_container_published_unverified_origin',r)
        snapshot=self.fx.dest/'snapshot';workspace=self.fx.dest/'workspace'
        system_pin=hashlib.sha256(self.fx.f.files['kit/SYSTEM-L0.json']).hexdigest()
        session=self.fx.start([sys.executable,'-I','-S','-B',str(ROOT/'kit/snapshot_session.py'),
                    '--candidate-root',str(snapshot),'--workspace',str(workspace),'--profile-root','profiles/pilot',
                    '--profile-id','Pilot','--manifest-pin',hashlib.sha256(self.fx.f.manifest).hexdigest(),
                    '--system-pin',system_pin])
        self.assertEqual(self.send(session,{'type':'bootstrap'})['outcome'],'bootstrap')
        req={'type':'plan','request':'Создай черновик контракта C-9 в профиле Pilot, постоянное, область «docs», название «Пример», основание «Проба», критерий «Запись существует»: Согласуем порядок чтения.'}
        planned=self.send(session,req);self.assertEqual(planned['outcome'],'planned',planned)
        applied=self.send(session,{'type':'apply','plan':planned,'confirmed_ticket':planned['ticket']})
        self.assertEqual(applied['outcome'],'applied',applied)
        doc=json.loads((workspace/'profiles/pilot/registry.json').read_bytes())
        self.assertIn('C-9',{entry['id'] for entry in doc['registry']['entries']})
        self.assertEqual(self.send(proc,{'type':'apply','plan':p,'confirmed_ticket':p['ticket']})['code'],'ticket_unknown')
    def test_tamper_cancel_and_bad_input(self):
        proc=self.start();p=self.send(proc,{'type':'plan'})
        changed=copy.deepcopy(p);changed['provider_sha256']='0'*64
        self.assertEqual(self.send(proc,{'type':'apply','plan':changed,'confirmed_ticket':p['ticket']})['code'],'plan_mismatch')
        self.assertEqual(self.send(proc,{'type':'apply','plan':p,'confirmed_ticket':p['ticket']})['code'],'ticket_unknown')
        p=self.send(proc,{'type':'plan'});self.assertEqual(self.send(proc,{'type':'cancel'})['outcome'],'cancelled')
        self.assertEqual(self.send(proc,{'type':'apply','plan':p,'confirmed_ticket':p['ticket']})['code'],'ticket_unknown')
        p=self.send(proc,{'type':'plan'});self.assertEqual(self.send(proc,{'type':'nonsense'})['code'],'invalid_request')
        self.assertEqual(self.send(proc,{'type':'apply','plan':p,'confirmed_ticket':p['ticket']})['code'],'ticket_unknown')
        self.assertFalse(self.fx.dest.exists())
    def test_bad_pin_and_tampered_archive(self):
        cmd=self.cmd.copy();cmd[cmd.index('--policy-pin')+1]='0'*64
        res=subprocess.run(cmd,input='',capture_output=True,text=True,timeout=20)
        self.assertEqual(res.returncode,1);self.assertEqual(json.loads(res.stderr)['reason'],'policy_pin_mismatch')
        self.fx.archive.write_bytes(self.fx.archive.read_bytes()+b'tamper')
        p=self.start();self.assertEqual(self.send(p,{'type':'plan'})['code'],'archive_unverified')
        self.assertFalse(self.fx.dest.exists())
    def test_observation_revokes_plan_and_makes_no_claim_of_completion(self):
        proc=self.start();p=self.send(proc,{'type':'plan'})
        stage=p['install_plan']['publication_plan']['stage_name']
        result=self.send(proc,{'type':'inspect','stage_name':stage})
        self.assertEqual(result['outcome'],'observation_only',result)
        self.assertEqual((result['stage_state'],result['destination_state']),('absent','absent'))
        self.assertEqual(result['installation'],'not_proved');self.assertEqual(result['recovery'],'not_performed')
        self.assertEqual(self.send(proc,{'type':'apply','plan':p,'confirmed_ticket':p['ticket']})['code'],'ticket_unknown')
        self.assertFalse(self.fx.dest.exists())
        self.assertEqual(self.send(proc,{'type':'inspect','stage_name':'../invalid'})['code'],'inspection_invalid')

    def test_read_once_explicitly_not_continuous(self):
        p=self.start();plan=self.send(p,{'type':'plan'})
        self.fx.archive.write_bytes(b'changed after capture')
        self.assertEqual(plan['input_observation'],'captured_once_at_start')
        r=self.send(p,{'type':'apply','plan':plan,'confirmed_ticket':plan['ticket']})
        self.assertEqual(r['outcome'],'study_container_published_unverified_origin',r)

if __name__=='__main__':unittest.main()
