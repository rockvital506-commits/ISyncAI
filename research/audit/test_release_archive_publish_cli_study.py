#!/usr/bin/env python3
"""Сквозная репетиция синтетического архива; не доверенная установка и не приёмка."""
import copy
import hashlib
import json
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'research/audit')]
import release_archive_study as archive
import release_policy_study as policy
import test_release_policy_study as fixture
import test_source_release_trust as signing
import test_atomic_init as atomic_test
import core_audit as audit
from kit import atomic_init


@unittest.skipUnless(signing.SUPPORTED and atomic_test.SUPPORTED,'OpenSSL/Linux unavailable; not_run')
class PublishCliTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.ReleasePolicyStudyTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.tmp=tempfile.TemporaryDirectory(prefix='signed-publish-cli-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.dest=self.root/'published';self.workspace=self.root/'workspace'
        self.archive=self.root/'release.zip';self.archive.write_bytes(archive.build(self.f.manifest,self.f.files))
        self.statement=self.root/'statement.json';self.statement.write_bytes(policy.canonical(self.f.doc))
        wire=copy.deepcopy(self.f.policy);wire['keys']={k:v.hex() for k,v in wire['keys'].items()}
        self.policy=self.root/'policy.json';self.policy.write_bytes(policy.canonical(wire))
        self.pin=hashlib.sha256(self.policy.read_bytes()).hexdigest();self.signature=self.f.sign().hex()
        self.openssl_pin=hashlib.sha256(signing.OPENSSL.read_bytes()).hexdigest();self.processes=[]
        self.addCleanup(self.close_processes)
    def close_processes(self):
        for p in self.processes:
            if p.stdin and not p.stdin.closed:p.stdin.close()
            try:p.wait(timeout=15)
            except subprocess.TimeoutExpired:p.kill();p.wait(timeout=15)
            p.stdout.close();p.stderr.close()
    def args(self):
        return [sys.executable,'-I','-S','-B',str(ROOT/'research/audit/release_archive_publish_cli_study.py'),
                '--archive',str(self.archive),'--statement',str(self.statement),'--policy',str(self.policy),
                '--policy-pin',self.pin,'--signature-hex',self.signature,'--openssl',str(signing.OPENSSL),
                '--openssl-pin',self.openssl_pin,'--destination',str(self.dest)]
    def start(self,cmd):
        p=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                           text=True,encoding='utf-8',bufsize=1);self.processes.append(p);return p
    def send(self,p,req):
        p.stdin.write(json.dumps(req,ensure_ascii=False)+'\n');p.stdin.flush()
        ready,_,_=select.select([p.stdout],[],[],25);self.assertTrue(ready,'no reply')
        line=p.stdout.readline();self.assertTrue(line);return json.loads(line)
    def test_signed_archive_to_snapshot_session_and_confirmed_operation(self):
        process=self.start(self.args());plan=self.send(process,{'type':'plan'})
        self.assertEqual(plan['outcome'],'planned',plan);self.assertEqual(plan['policy_sha256'],self.pin)
        self.assertEqual(plan['input_observation'],'captured_once_at_start');self.assertFalse(self.dest.exists())
        rejected=self.send(process,{'type':'apply','plan':plan,'confirmed_ticket':'wrong'})
        self.assertEqual(rejected['code'],'confirmation_required');self.assertFalse(self.dest.exists())
        result=self.send(process,{'type':'apply','plan':plan,'confirmed_ticket':plan['ticket']})
        self.assertEqual(result['outcome'],'snapshot_published_unverified_origin',result)
        self.assertEqual(self.send(process,{'type':'apply','plan':plan,'confirmed_ticket':plan['ticket']})['code'],'ticket_unknown')
        l0=(ROOT/'kit/SYSTEM-L0.json').read_bytes();system_pin=hashlib.sha256(l0).hexdigest()
        init=atomic_init.AtomicInitializationSession(self.workspace,profile_root='profiles/pilot',l0_bytes=l0,system_pin=system_pin)
        p=init.plan();init.apply(p,confirmed_ticket=p['ticket'])
        session=self.start([sys.executable,'-I','-S','-B',str(ROOT/'kit/snapshot_session.py'),
                            '--candidate-root',str(self.dest),'--workspace',str(self.workspace),
                            '--profile-root','profiles/pilot','--profile-id','Pilot',
                            '--manifest-pin',hashlib.sha256(self.f.manifest).hexdigest(),'--system-pin',system_pin])
        self.assertEqual(self.send(session,{'type':'bootstrap'})['outcome'],'bootstrap')
        for mode,expected in (('project','SYS-PROJECT-MODE'),('kit','SYS-KIT-MODE')):
            context=self.send(session,{'type':'context','mode':mode,'scope':'docs/a','choices':{'include':[],'exclude':[]}})
            self.assertEqual(context['outcome'],'review_required',context)
            self.assertIn(expected,{row['entry']['id'] for row in context['entries'] if row['area']=='L0'})
        request={'type':'plan','request':'Создай черновик контракта C-9 в профиле Pilot, постоянное, область «docs», название «Пример», основание «Проба», критерий «Запись существует»: Согласуем порядок чтения.'}
        before=audit.tree_digest(self.workspace);p=self.send(session,request);self.assertEqual(p['outcome'],'planned',p)
        self.assertEqual(before,audit.tree_digest(self.workspace))
        self.assertEqual(self.send(session,{'type':'apply','plan':p,'confirmed_ticket':p['ticket']})['outcome'],'applied')
        self.assertNotEqual(before,audit.tree_digest(self.workspace))
        move=self.start([sys.executable,'-I','-S','-B',str(ROOT/'kit/snapshot_move_session.py'),
                         '--candidate-root',str(self.dest),'--workspace',str(self.workspace),
                         '--profile-root','profiles/pilot','--manifest-pin',hashlib.sha256(self.f.manifest).hexdigest(),
                         '--system-pin',system_pin])
        candidate=audit.entry('P-9','contract','project_owner',None,'docs',state='draft')
        built=self.send(move,{'type':'build','source':'L1','target':'L2','entry_id':'C-9',
                              'candidate':candidate,'portability_context':None})
        self.assertEqual(built['outcome'],'intent_draft_only',built)
        self.assertEqual(self.send(move,{'type':'configure','intent_utf8':built['intent_utf8'],
                                        'intent_pin':built['intent_sha256']})['outcome'],'configured')
        for action,expected in (('reserve','reserved_not_moved'),('execute','registries_updated_marker_retained'),
                                ('finalize','marker_removed_after_both')):
            planned=self.send(move,{'type':'plan','action':action});self.assertEqual(planned['outcome'],'planned',planned)
            p=planned['plan'];result=self.send(move,{'type':'apply','plan':p,'confirmed_ticket':p['ticket']})
            self.assertEqual(result['outcome'],expected,result)
        profile=json.loads((self.workspace/'profiles/pilot/registry.json').read_bytes())
        project=json.loads((self.workspace/'.domain-agent-kit/project/registry.json').read_bytes())
        self.assertNotIn('C-9',{entry['id'] for entry in profile['registry']['entries']})
        self.assertIn('P-9',{entry['id'] for entry in project['registry']['entries']})
        self.assertFalse((self.workspace/'.domain-agent-kit/.move-pending').exists())
    def test_changed_plan_revoke_cancel_and_invalid_request(self):
        proc=self.start(self.args());p=self.send(proc,{'type':'plan'});bad=copy.deepcopy(p);bad['policy_sha256']='0'*64
        self.assertEqual(self.send(proc,{'type':'apply','plan':bad,'confirmed_ticket':p['ticket']})['code'],'plan_mismatch')
        self.assertEqual(self.send(proc,{'type':'apply','plan':p,'confirmed_ticket':p['ticket']})['code'],'ticket_unknown')
        p=self.send(proc,{'type':'plan'});self.assertEqual(self.send(proc,{'type':'cancel'})['outcome'],'cancelled')
        self.assertEqual(self.send(proc,{'type':'apply','plan':p,'confirmed_ticket':p['ticket']})['code'],'ticket_unknown')
        p=self.send(proc,{'type':'plan'});self.assertEqual(self.send(proc,{'type':'unexpected'})['code'],'invalid_request')
        self.assertEqual(self.send(proc,{'type':'apply','plan':p,'confirmed_ticket':p['ticket']})['code'],'ticket_unknown')
        self.assertFalse(self.dest.exists())
    def test_wrong_pin_or_tampered_archive_fail_without_publication(self):
        cmd=self.args();cmd[cmd.index('--policy-pin')+1]='0'*64
        result=subprocess.run(cmd,input='',capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,1);self.assertEqual(json.loads(result.stderr)['reason'],'policy_pin_mismatch')
        self.archive.write_bytes(self.archive.read_bytes()+b'extra')
        proc=self.start(self.args());response=self.send(proc,{'type':'plan'})
        self.assertEqual(response['code'],'archive_unverified');self.assertFalse(self.dest.exists())
    def test_captured_once_inputs_do_not_silently_change_plan(self):
        proc=self.start(self.args());p=self.send(proc,{'type':'plan'})
        self.archive.write_bytes(b'changed after input capture')
        self.policy.write_bytes(b'changed after input capture')
        result=self.send(proc,{'type':'apply','plan':p,'confirmed_ticket':p['ticket']})
        self.assertEqual(result['outcome'],'snapshot_published_unverified_origin')
        self.assertEqual((self.dest/'kit/KIT-VERSION.json').read_bytes(),self.f.manifest)

if __name__=='__main__':unittest.main()
