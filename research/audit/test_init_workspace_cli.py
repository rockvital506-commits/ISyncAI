#!/usr/bin/env python3
"""Внешний JSON-lines процесс: только новые синтетические директории."""
import copy
import hashlib
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'research/audit')]
from kit import init_workspace as init
from kit.init_workspace_cli import MAX_LINE
from kit.verify_candidate import CANDIDATE_VERSION


@unittest.skipUnless(init._supported(),'POSIX descriptor API unavailable; not_run')
class CliInitializationTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='domain-init-cli-');self.addCleanup(temp.cleanup)
        self.root=Path(temp.name).resolve();self.dest=self.root/'workspace'
        self.marker=self.root/'sentinel';self.marker.write_bytes(b'synthetic')
        self.raw=(json.dumps({'schema_version':2,'area':'L0','roots':['kit'],
                              'release_version':CANDIDATE_VERSION,'entries':[]},sort_keys=True)+'\n').encode()
        self.pin=hashlib.sha256(self.raw).hexdigest();self.peers=[];self.addCleanup(self.cleanup)
        self.peer=self.spawn([sys.executable,'-I','-S','-B',str(ROOT/'kit/init_workspace_cli.py')])

    def spawn(self,args):
        p=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                           encoding='utf-8',text=True,bufsize=1)
        lines=queue.Queue()
        def reader():
            for line in p.stdout:lines.put(line)
            lines.put(None)
        threading.Thread(target=reader,daemon=True).start();self.peers.append((p,lines));return p,lines

    def cleanup(self):
        for p,_ in self.peers:
            if p.poll() is None:p.kill()
            p.communicate(timeout=10)

    def raw_request(self,text,peer=None):
        p,lines=peer or self.peer;p.stdin.write(text+'\n');p.stdin.flush()
        try:result=lines.get(timeout=15)
        except queue.Empty:self.fail('process response timeout')
        if result is None:
            p.wait(timeout=10);self.fail('process ended: '+p.stderr.read())
        return json.loads(result)

    def request(self,obj,peer=None):return self.raw_request(json.dumps(obj,ensure_ascii=False),peer)
    def command(self):return {'type':'plan','destination':str(self.dest),'profile_root':'profiles/pilot',
                               'l0_utf8':self.raw.decode(),'system_pin':self.pin}
    def apply(self,plan,ticket=None,peer=None):
        return self.request({'type':'apply','plan':plan,'confirmed_ticket':plan['ticket'] if ticket is None else ticket},peer)

    def full_synthetic_path_from_cli_to_isolated_snapshot_session(self, expected_system_ids=None):
        plan=self.request(self.command());self.assertEqual(plan['outcome'],'planned');self.assertFalse(self.dest.exists())
        self.assertEqual(self.apply(plan,'')['code'],'confirmation_required');self.assertFalse(self.dest.exists())
        self.assertEqual(self.apply(plan)['outcome'],'created_unverified_origin')
        for row in plan['files']:
            raw=(self.dest/row['path']).read_bytes();self.assertEqual(raw,row['content_utf8'].encode())
            self.assertEqual(hashlib.sha256(raw).hexdigest(),row['sha256'])
        self.assertEqual(self.apply(plan)['code'],'ticket_unknown')
        self.assertEqual(self.marker.read_bytes(),b'synthetic')
        raw=(ROOT/'kit/KIT-VERSION.json').read_bytes();manifest=json.loads(raw)
        source=self.root/'source';trusted=self.root/'trusted';source.mkdir();trusted.mkdir()
        for rel in ('kit/KIT-VERSION.json',*manifest['files']):
            p=source/rel;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/rel,p)
        for name in ('snapshot_session.py','verify_candidate.py'):shutil.copyfile(ROOT/'kit'/name,trusted/name)
        snapshot=self.spawn([sys.executable,'-I','-S','-B',str(trusted/'snapshot_session.py'),
            '--candidate-root',str(source),'--workspace',str(self.dest),'--profile-root','profiles/pilot',
            '--profile-id','Pilot','--manifest-pin',hashlib.sha256(raw).hexdigest(),'--system-pin',self.pin])
        self.assertEqual(self.request({'type':'bootstrap'},snapshot)['outcome'],'bootstrap')
        if expected_system_ids is not None:
            report=self.request({'type':'applicable','scope':'docs/file'},snapshot)
            self.assertEqual(report['outcome'],'applicable')
            self.assertEqual({r['entry']['id'] for r in report['entries'] if r['area']=='L0'},expected_system_ids)
            self.assertEqual(report['text_conflicts'],'not_checked')
        prompt=('Создай черновик контракта X-9 в профиле Pilot, постоянное, область «docs», '
                'название «Пример», основание «Проба», критерий «Запись существует»: Синтетический текст.')
        change=self.request({'type':'plan','request':prompt},snapshot)
        self.assertEqual(change['outcome'],'planned')
        cmd={'type':'apply','plan':change,'confirmed_ticket':''}
        self.assertEqual(self.request(cmd,snapshot)['diagnostic']['code'],'confirmation_required')
        before={p:(self.dest/p).read_bytes() for p in ('kit/base/registry.json',
                'profiles/pilot/registry.json','.domain-agent-kit/project/registry.json')}
        cmd['confirmed_ticket']=change['ticket']
        self.assertEqual(self.request(cmd,snapshot)['outcome'],'applied')
        self.assertEqual((self.dest/'kit/base/registry.json').read_bytes(),before['kit/base/registry.json'])
        self.assertEqual((self.dest/'.domain-agent-kit/project/registry.json').read_bytes(),
                         before['.domain-agent-kit/project/registry.json'])
        self.assertNotEqual((self.dest/'profiles/pilot/registry.json').read_bytes(),before['profiles/pilot/registry.json'])

    def test_full_synthetic_path_empty_l0(self):
        self.full_synthetic_path_from_cli_to_isolated_snapshot_session()

    def test_full_synthetic_path_candidate_system_l0(self):
        self.raw=(ROOT/'kit/SYSTEM-L0.json').read_bytes();self.pin=hashlib.sha256(self.raw).hexdigest()
        system=json.loads(self.raw)
        self.assertEqual(len(system['entries']),10)
        self.full_synthetic_path_from_cli_to_isolated_snapshot_session({e['id'] for e in system['entries']})

    def test_cancel_malformed_and_new_plan_revoke(self):
        plan=self.request(self.command());self.assertEqual(self.request({'type':'cancel'})['outcome'],'cancelled')
        self.assertEqual(self.apply(plan)['code'],'ticket_unknown')
        plan=self.request(self.command());self.assertEqual(self.raw_request('{"type":"cancel","type":"cancel"}')['code'],'invalid_request')
        self.assertEqual(self.apply(plan)['code'],'ticket_unknown')
        plan=self.request(self.command());bad=dict(self.command(),system_pin='0'*64)
        self.assertEqual(self.request(bad)['code'],'system_pin_mismatch')
        self.assertEqual(self.apply(plan)['code'],'ticket_unknown');self.assertFalse(self.dest.exists())

    def test_plan_tampering_and_existing_destination(self):
        plan=self.request(self.command());tampered=copy.deepcopy(plan);tampered['files'][0]['content_utf8']+='x'
        self.assertEqual(self.apply(tampered)['code'],'plan_mismatch')
        self.assertEqual(self.apply(plan)['code'],'ticket_unknown');self.assertFalse(self.dest.exists())
        self.dest.mkdir();sentinel=self.dest/'do-not-touch';sentinel.write_bytes(b'preserve')
        self.assertEqual(self.request(self.command())['code'],'destination_occupied')
        self.assertEqual(sentinel.read_bytes(),b'preserve')

    def test_two_processes_cannot_both_reserve_same_destination(self):
        peer2=self.spawn([sys.executable,'-I','-S','-B',str(ROOT/'kit/init_workspace_cli.py')])
        a=self.request(self.command());b=self.request(self.command(),peer2)
        barrier=threading.Barrier(2);results=[];errors=[]
        def apply(peer,plan):
            try:
                barrier.wait(timeout=10)
                results.append(self.apply(plan,peer=peer))
            except BaseException as error:errors.append(error)
        threads=[threading.Thread(target=apply,args=pair) for pair in ((self.peer,a),(peer2,b))]
        for thread in threads:thread.start()
        for thread in threads:thread.join(timeout=15);self.assertFalse(thread.is_alive())
        self.assertEqual(errors,[])
        self.assertCountEqual([r.get('code',r['outcome']) for r in results],
                              ['destination_occupied','created_unverified_origin'])
        self.assertEqual(self.marker.read_bytes(),b'synthetic')
        for row in a['files']:self.assertEqual((self.dest/row['path']).read_bytes(),row['content_utf8'].encode())

    def test_eof_does_not_apply_pending_plan(self):
        plan=self.request(self.command());self.peer[0].stdin.close();self.peer[0].stdin=None
        self.peer[0].wait(timeout=10);self.assertEqual(self.peer[0].returncode,0)
        self.assertFalse(self.dest.exists());self.assertEqual(self.marker.read_bytes(),b'synthetic')

    def test_oversized_line_terminates_without_command_splitting(self):
        plan=self.request(self.command())
        p,lines=self.peer
        p.stdin.write(' '+('x'*MAX_LINE)+'\n');p.stdin.flush()
        result=lines.get(timeout=15);self.assertEqual(json.loads(result)['code'],'input_too_large')
        p.wait(timeout=10);self.assertEqual(p.returncode,1)
        self.assertFalse(self.dest.exists());self.assertEqual(self.marker.read_bytes(),b'synthetic')

    def test_plan_request_type_and_invalid_json(self):
        for obj in ({'type':'plan'}, dict(self.command(),l0_utf8=1), dict(self.command(),unexpected=True),
                    dict(self.command(),profile_root='p'*4097), dict(self.command(),destination='d'*4097),
                    {'type':'cancel','extra':1}, {'type':'apply','plan':{},'confirmed_ticket':True}):
            self.assertEqual(self.request(obj)['code'],'invalid_request')
        self.assertEqual(self.raw_request('not json')['code'],'invalid_request');self.assertFalse(self.dest.exists())


if __name__=='__main__':unittest.main()
