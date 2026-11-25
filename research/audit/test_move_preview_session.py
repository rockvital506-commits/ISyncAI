#!/usr/bin/env python3
"""Двухсторонний preview в обычной и закреплённой JSON-сессиях; синтетические файлы."""
import hashlib
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'research/audit')]
import core_audit as audit
from kit.base import registry_journal, schema_v2, registry_store as store


def digest(data):return hashlib.sha256(data).hexdigest()

class PreviewSessionTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(prefix='move-preview-cli-');self.addCleanup(tmp.cleanup)
        self.base=Path(tmp.name).resolve();self.workspace=self.base/'workspace';self.workspace.mkdir()
        audit.make_workspace(self.workspace,parent_scope='.')
        self.paths={'L0':self.workspace/'kit/base/registry.json','L1':self.workspace/'profiles/pilot/registry.json',
                    'L2':self.workspace/'.domain-agent-kit/project/registry.json'}
        manifest=json.loads((ROOT/'kit/KIT-VERSION.json').read_bytes())
        l0=json.loads(self.paths['L0'].read_bytes());l0['release_version']=manifest['version'];audit.write(self.paths['L0'],l0)
        for area,parent,auth in (('L1','C-1','profile_owner'),('L2','P-1','project_owner')):
            doc=json.loads(self.paths[area].read_bytes());doc['entries'].append(audit.entry('SRC-'+area,'rule',auth,parent,'docs',state='active'))
            audit.write(self.paths[area],doc)
        self.candidate=self.base/'candidate';self.candidate.mkdir()
        for rel in ('kit/KIT-VERSION.json',*manifest['files']):
            to=self.candidate/rel;to.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/rel,to)
        self.sentinel=self.base/'workspace-code-ran'
        for name in ('move_preview.py','project_specificity.py'):
            (self.workspace/'kit/base'/name).write_text('from pathlib import Path\nPath('+repr(str(self.sentinel))+').touch()\n')
        self.procs=[];self.addCleanup(self.cleanup)
    def cleanup(self):
        for p,_ in self.procs:
            if p.poll() is None:p.kill()
            p.communicate(timeout=10)
    def process(self,snapshot):
        if snapshot:
            args=[str(ROOT/'kit/snapshot_session.py'),'--candidate-root',str(self.candidate),
                  '--manifest-pin',digest((self.candidate/'kit/KIT-VERSION.json').read_bytes()),
                  '--system-pin',digest(self.paths['L0'].read_bytes())]
        else:args=[str(ROOT/'kit/session_cli.py')]
        args+=['--workspace',str(self.workspace),'--profile-root','profiles/pilot','--profile-id','Pilot']
        p=subprocess.Popen([sys.executable,'-I','-S','-B',*args],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',bufsize=1)
        q=queue.Queue()
        def read():
            for line in p.stdout:q.put(line)
            q.put(None)
        threading.Thread(target=read,daemon=True).start();self.procs.append((p,q));return p,q
    def send(self,peer,obj):
        p,q=peer;p.stdin.write(json.dumps(obj,ensure_ascii=False)+'\n');p.stdin.flush();line=q.get(timeout=15)
        if line is None:self.fail('session exited: '+p.stderr.read())
        return json.loads(line)
    def request(self,src):
        dst='L2' if src=='L1' else 'L1';auth='project_owner' if dst=='L2' else 'profile_owner';parent='P-1' if dst=='L2' else 'C-1'
        return {'type':'move_preview','source':src,'target':dst,'entry_id':'SRC-'+src,
                'candidate':audit.entry('DST-'+src,'rule',auth,parent,'docs',state='draft',text='synthetic revision'),
                'portability_context':None if src=='L1' else {'project_names':[],'machine_names':[],'project_paths':[]}}
    def plan(self,peer):
        result=self.send(peer,{'type':'plan','request':audit.card(ident='Q-91')['request']})
        self.assertEqual(result['outcome'],'planned');return result
    def assert_unknown(self,peer,plan):
        result=self.send(peer,{'type':'apply','plan':plan,'confirmed_ticket':plan['ticket']})
        self.assertEqual(result['diagnostic']['code'],'ticket_unknown')
    def test_both_directions_and_revoked_plan_in_both_sessions(self):
        for snapshot in (False,True):
            with self.subTest(snapshot=snapshot):
                peer=self.process(snapshot);old=self.plan(peer);before=audit.tree_digest(self.workspace)
                for src in ('L1','L2'):
                    request=self.request(src);result=self.send(peer,request)
                    self.assertEqual(result['outcome'],'hypothetical_only')
                    for key in ('confirmation','apply','recovery','transaction_history'):self.assertEqual(result[key],'not_implemented')
                    self.assertNotIn('ticket',result);self.assertTrue(result['source_removed_in_hypothesis'])
                    self.assertEqual(result['inputs_sha256'],{area:digest(path.read_bytes()) for area,path in self.paths.items()})
                    for row in result['diffs']:
                        area=row['area'];raw=row['after_utf8'].encode()
                        self.assertEqual(digest(raw),row['after_sha256'])
                        doc,journal=registry_journal.unpack_registry(schema_v2.parse_json(raw),area=area)
                        ids={entry['id'] for entry in doc['entries']}
                        self.assertEqual(('SRC-'+src) in ids,False)
                        self.assertEqual(('DST-'+src) in ids,area==request['target'])
                        self.assertEqual(journal['decisions'][-1]['operation'],'delete' if area==src else 'create')
                self.assert_unknown(peer,old);self.assertEqual(before,audit.tree_digest(self.workspace));self.assertFalse(self.sentinel.exists())
    def test_invalid_input_and_project_specificity_revoke(self):
        peer=self.process(False)
        for alteration,code in (('direction','move_direction_invalid'),('context','invalid_context'),
                                ('missing','entry_not_found'),('children','source_has_children'),('specific','project_specific')):
            with self.subTest(alteration=alteration):
                plan=self.plan(peer);request=self.request('L2' if alteration=='specific' else 'L1')
                if alteration=='direction':request['target']='L0'
                if alteration=='context':request['portability_context']={}
                if alteration=='missing':request['entry_id']='ABSENT'
                if alteration=='children':request['entry_id']='C-1'
                if alteration=='specific':request['candidate']['text']='Use /home/synthetic/private'
                self.assertEqual(self.send(peer,request)['diagnostic']['code'],code);self.assert_unknown(peer,plan)
        plan=self.plan(peer);request=self.request('L1');del request['candidate']
        self.assertEqual(self.send(peer,request)['code'],'invalid_request');self.assert_unknown(peer,plan)
        self.assertFalse(self.sentinel.exists())
    def test_existing_structural_conflict_refused_without_writes(self):
        for area,value in (('L1','A'),('L2','B')):
            doc=json.loads(self.paths[area].read_bytes())
            doc['entries'][-1].update(key='build.policy',value=value)
            audit.write(self.paths[area],doc)
        peer=self.process(False);before=audit.tree_digest(self.workspace)
        self.assertEqual(self.send(peer,self.request('L1'))['diagnostic']['code'],'rule_conflict')
        self.assertEqual(before,audit.tree_digest(self.workspace));self.assertFalse(self.sentinel.exists())

    @unittest.skipUnless(os.name=='posix' and store.fcntl is not None,'POSIX flock unavailable; not_run')
    def test_pending_and_busy_refuse_without_modification(self):
        peer=self.process(False);request=self.request('L1');before=audit.tree_digest(self.workspace)
        fd=os.open(self.workspace,os.O_RDONLY|os.O_DIRECTORY)
        try:
            store.fcntl.flock(fd,store.fcntl.LOCK_EX|store.fcntl.LOCK_NB)
            self.assertEqual(self.send(peer,request)['diagnostic']['code'],'read_busy')
        finally:os.close(fd)
        self.assertEqual(before,audit.tree_digest(self.workspace))
        marker=self.workspace/'.domain-agent-kit/.move-pending';marker.write_bytes(b'unknown synthetic')
        before=audit.tree_digest(self.workspace)
        self.assertEqual(self.send(peer,request)['diagnostic']['code'],'move_pending')
        self.assertEqual(before,audit.tree_digest(self.workspace));self.assertEqual(marker.read_bytes(),b'unknown synthetic')

if __name__=='__main__':unittest.main()
