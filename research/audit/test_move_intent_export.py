#!/usr/bin/env python3
"""Экспорт только в новые синтетические файлы; не перенос и не доставка доверия."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'research/audit')]
import core_audit as audit
from kit import init_workspace as init, move_intent_export as export
from kit.base import move_intent


def wire(doc):return (json.dumps(doc,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()

@unittest.skipUnless(init._supported(),'POSIX dirfd/xattr unsupported; not_run')
class IntentExportTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(prefix='move-intent-export-');self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name).resolve();self.destination=self.root/'intent.json';self.neighbor=self.root/'neighbor';self.neighbor.write_bytes(b'unchanged')
        l0={'schema_version':2,'area':'L0','roots':['kit'],'release_version':'0.2.0-synthetic','entries':[]}
        l1={'schema_version':2,'area':'L1','roots':['profiles/pilot'],'revision':0,'entries':[audit.entry('C-1','contract','profile_owner',None,'.'),audit.entry('SOURCE','rule','profile_owner','C-1','docs',state='active')]}
        l2={'schema_version':2,'area':'L2','roots':['.domain-agent-kit'],'revision':0,'entries':[audit.entry('P-1','contract','project_owner',None,'.')]}
        before={'L0':wire(l0),'L1':wire(l1),'L2':wire(l2)}
        report,self.raw=move_intent.build(before,source='L1',target='L2',entry_id='SOURCE',
                       candidate=audit.entry('TARGET','rule','project_owner','P-1','docs',state='draft',text='SYNTHETIC_SECRET'),portability_context=None)
        self.pin=report['intent_sha256'];self.session=self.new()
    def new(self):return export.IntentExportSession(self.destination,intent_bytes=self.raw,intent_pin=self.pin)
    def error(self,code,fn,*args,**kw):
        with self.assertRaises(export.IntentExportError) as e:fn(*args,**kw)
        self.assertEqual(str(e.exception),code)
    def apply(self,s,p):return s.apply(p,confirmed_ticket=p['ticket'])
    def test_plan_and_separate_confirmation_exact_bytes(self):
        p=self.session.plan();self.assertFalse(self.destination.exists());self.assertEqual(p['intent_utf8'].encode(),self.raw)
        self.assertEqual(p['intent_sha256'],hashlib.sha256(self.raw).hexdigest());self.assertEqual(p['preview']['outcome'],'hypothetical_only')
        self.error('confirmation_required',self.session.apply,p,confirmed_ticket='wrong');self.assertFalse(self.destination.exists())
        result=self.apply(self.session,p);self.assertEqual(result['outcome'],'exported_unverified_origin')
        self.assertEqual(self.destination.read_bytes(),self.raw);self.assertEqual(self.destination.stat().st_mode&0o777,0o600)
        self.assertEqual(self.neighbor.read_bytes(),b'unchanged');self.error('ticket_unknown',self.apply,self.session,p)
        self.error('destination_occupied',self.session.plan)
    def test_exported_intent_supports_separate_synthetic_probe(self):
        from kit import move_recovery_inspect
        from kit.base import registry_store
        plan=self.session.plan();self.apply(self.session,plan)
        workspace=self.root/'synthetic-workspace';workspace.mkdir();layout=audit.make_workspace(workspace,parent_scope='.')
        _,before,_=move_intent._verified(self.destination.read_bytes(),self.pin)
        paths={'L0':workspace/'kit/base/registry.json','L1':workspace/'profiles/pilot/registry.json',
               'L2':workspace/'.domain-agent-kit/project/registry.json'}
        for area,path in paths.items():path.write_bytes(before[area])
        # Тест сам создаёт marker: штатный Kit по-прежнему этого не делает.
        marker=workspace/'.domain-agent-kit/.move-pending';marker.write_bytes(self.destination.read_bytes())
        result=move_recovery_inspect.inspect(layout,intent_pin=self.pin)
        self.assertEqual(result['state'],'before_both');self.assertEqual(result['recovery'],'not_implemented')
        with self.assertRaises(registry_store.StoreError) as error:registry_store.status(layout)
        self.assertEqual(error.exception.code,'move_pending')
        self.assertEqual(marker.read_bytes(),self.raw);self.assertEqual(self.destination.read_bytes(),self.raw)
        self.assertNotIn('SYNTHETIC_SECRET',repr(result))

    def test_changed_plan_input_cancel_and_parent_refuse(self):
        for kind in ('plan','data','pin','destination','cancel','parent'):
            with self.subTest(kind=kind):
                parent=self.root/kind;parent.mkdir();self.destination=parent/'intent';s=self.new();p=s.plan();changed=copy.deepcopy(p)
                if kind=='plan':changed['intent_utf8']+=' '
                elif kind=='data':s.intent_bytes+=b'x'
                elif kind=='pin':s.intent_pin='0'*64
                elif kind=='destination':s.destination=parent/'other'
                elif kind=='cancel':s.cancel()
                else:parent.rename(self.root/(kind+'-old'));parent.mkdir()
                expected={'plan':'plan_mismatch','data':'stale_plan','pin':'stale_plan','destination':'stale_plan',
                          'cancel':'ticket_unknown','parent':'stale_parent'}[kind]
                self.error(expected,s.apply,changed,confirmed_ticket=p['ticket'])
                self.assertFalse(self.destination.exists());self.assertEqual(self.neighbor.read_bytes(),b'unchanged')
    def test_existing_file_directory_symlink_and_race_refuse(self):
        for kind in ('file','directory','symlink','dangling'):
            with self.subTest(kind=kind):
                self.destination=self.root/('target-'+kind);s=self.new();p=s.plan()
                if kind=='file':self.destination.write_bytes(b'other')
                elif kind=='directory':self.destination.mkdir()
                elif kind=='symlink':self.destination.symlink_to(self.neighbor)
                else:self.destination.symlink_to(self.root/'missing')
                self.error('destination_occupied',self.apply,s,p);self.error('destination_occupied',s.plan)
                self.assertEqual(self.neighbor.read_bytes(),b'unchanged')
        self.destination=self.root/'.move-pending';self.error('destination_invalid',self.new().plan)
    def test_same_session_busy_does_not_consume_plan(self):
        plan=self.session.plan();self.assertTrue(self.session._lock.acquire(blocking=False))
        try:
            self.error('session_busy',self.session.plan)
            self.error('session_busy',self.session.cancel)
            self.error('session_busy',self.apply,self.session,plan)
        finally:self.session._lock.release()
        self.assertEqual(self.apply(self.session,plan)['outcome'],'exported_unverified_origin')
        self.assertEqual(self.destination.read_bytes(),self.raw)

    def test_invalid_intent_is_not_exported(self):
        self.error('move_intent_pin_mismatch',export.IntentExportSession(self.destination,intent_bytes=self.raw,intent_pin='0'*64).plan)
        malformed=b'{}';self.error('move_intent_invalid',export.IntentExportSession(self.destination,intent_bytes=malformed,intent_pin=hashlib.sha256(malformed).hexdigest()).plan)
        self.assertFalse(self.destination.exists())
    def test_write_or_sync_failure_keeps_target_and_consumes_ticket(self):
        for kind in ('write','file_fsync','parent_fsync','metadata'):
            with self.subTest(kind=kind):
                self.destination=self.root/('fail-'+kind);s=self.new();p=s.plan()
                if kind=='write':mock=patch.object(export.os,'write',side_effect=OSError('injected'))
                elif kind=='metadata':mock=patch.object(export.init,'_check_new_fd',side_effect=init.InitializationError('injected'))
                else:
                    original=os.fsync;calls=[]
                    def fail(fd):
                        calls.append(fd)
                        if len(calls)==(1 if kind=='file_fsync' else 2):raise OSError('injected')
                        return original(fd)
                    mock=patch.object(export.os,'fsync',side_effect=fail)
                with mock:self.error('destination_partial_or_unverified',self.apply,s,p)
                self.assertTrue(self.destination.is_file());self.error('ticket_unknown',self.apply,s,p)
                self.assertEqual(self.neighbor.read_bytes(),b'unchanged')
    def test_visible_or_unreadable_xattrs_fail_before_writing(self):
        for mode in ('present','unavailable'):
            with self.subTest(mode=mode):
                self.destination=self.root/('xattr-'+mode);s=self.new();p=s.plan()
                if mode=='present':mock=patch.object(init.os,'listxattr',return_value=['user.synthetic'])
                else:mock=patch.object(init.os,'listxattr',side_effect=OSError('synthetic'))
                with mock:self.error('destination_partial_or_unverified',self.apply,s,p)
                self.assertEqual(self.destination.read_bytes(),b'');self.assertEqual(self.neighbor.read_bytes(),b'unchanged')

    def test_actual_process_interrupted_during_write_and_sync(self):
        program=r'''import os,sys,json
from pathlib import Path
sys.path.insert(0,sys.argv[1]);from kit import move_intent_export as e
raw=bytes.fromhex(sys.argv[3]);s=e.IntentExportSession(Path(sys.argv[2]),intent_bytes=raw,intent_pin=sys.argv[4]);p=s.plan()
print(json.dumps({'planned':True}),flush=True);realwrite=os.write;realsync=os.fsync;kind=sys.argv[5]
if kind=='write':
 def partial(fd,data):realwrite(fd,data[:len(data)//2]);os._exit(77)
 os.write=partial
else:
 count=[0]
 def sync(fd):
  realsync(fd);count[0]+=1
  if count[0]==(1 if kind=='file' else 2):os._exit(77)
 os.fsync=sync
s.apply(p,confirmed_ticket=p['ticket']);os._exit(3)
'''
        for phase in ('write','file','parent'):
            with self.subTest(phase=phase):
                dest=self.root/('abrupt-'+phase)
                proc=subprocess.run([sys.executable,'-I','-S','-B','-c',program,str(ROOT),str(dest),self.raw.hex(),self.pin,phase],capture_output=True,text=True,timeout=15)
                self.assertEqual(proc.returncode,77,proc.stderr);self.assertEqual(json.loads(proc.stdout),{'planned':True})
                self.assertTrue(dest.is_file());content=dest.read_bytes()
                self.assertEqual(content,self.raw[:len(self.raw)//2] if phase=='write' else self.raw)
                self.error('destination_occupied',export.IntentExportSession(dest,intent_bytes=self.raw,intent_pin=self.pin).plan)
                self.assertEqual(self.neighbor.read_bytes(),b'unchanged')

if __name__=='__main__':unittest.main()
