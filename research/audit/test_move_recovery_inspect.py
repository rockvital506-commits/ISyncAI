#!/usr/bin/env python3
"""Осмотр маркера только в новых синтетических деревьях; никогда не восстанавливает."""
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
from kit import move_recovery_inspect as probe
from kit.base import move_intent, registry_store as store
from kit.base.registry_policy import StoreError

SUPPORTED=(os.name=='posix' and store.fcntl is not None and hasattr(os,'O_NOFOLLOW') and hasattr(os,'O_DIRECTORY'))

@unittest.skipUnless(SUPPORTED,'POSIX descriptor/flock unavailable; not_run')
class RecoveryInspectTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(prefix='move-probe-');self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name).resolve();self.layout=audit.make_workspace(self.root,parent_scope='.')
        self.paths={'L0':self.root/'kit/base/registry.json','L1':self.root/'profiles/pilot/registry.json',
                    'L2':self.root/'.domain-agent-kit/project/registry.json'}
        l1=json.loads(self.paths['L1'].read_bytes());l1['entries'].append(audit.entry('SOURCE','rule','profile_owner','C-1','docs',state='active'))
        audit.write(self.paths['L1'],l1)
        self.before={k:p.read_bytes() for k,p in self.paths.items()}
        candidate=audit.entry('TARGET','rule','project_owner','P-1','docs',state='draft',text='SECRET_SYNTHETIC_TEXT')
        self.report,self.record=move_intent.build(self.before,source='L1',target='L2',entry_id='SOURCE',candidate=candidate,portability_context=None)
        self.pin=self.report['intent_sha256'];self.marker=self.root/'.domain-agent-kit/.move-pending';self.marker.write_bytes(self.record)
        self.after={r['area']:r['after_utf8'].encode() for r in self.report['preview']['diffs']}
        self.sibling=self.root/'neighbor';self.sibling.write_bytes(b'keep')
    def inspect(self,pin=None):return probe.inspect(self.layout,intent_pin=self.pin if pin is None else pin)
    def error(self,code,fn,*args,**kwargs):
        with self.assertRaises(StoreError) as e:fn(*args,**kwargs)
        self.assertEqual(e.exception.code,code)
    def verify_gate(self):
        self.error('move_pending',store.status,self.layout)
        self.assertTrue(self.marker.exists() or self.marker.is_symlink());self.assertEqual(self.sibling.read_bytes(),b'keep')
    def test_all_states_diagnosed_without_unblocking_or_mutation(self):
        states=(({},'before_both'),({'L2':self.after['L2']},'target_after_source_before'),
                (self.after,'after_both'),({'L1':self.after['L1']},'impossible_order'))
        for changes,expected in states:
            with self.subTest(expected=expected):
                for area,path in self.paths.items():path.write_bytes(changes.get(area,self.before[area]))
                baseline=audit.tree_digest(self.root);result=self.inspect()
                self.assertEqual(result['state'],expected);self.assertEqual(result['marker'],'present_and_pin_matched')
                self.assertEqual(result['snapshot'],'cooperative_lock_only');self.assertEqual(result['recovery'],'not_implemented')
                self.assertNotIn('SECRET_SYNTHETIC_TEXT',repr(result));self.assertEqual(baseline,audit.tree_digest(self.root));self.verify_gate()
    def test_changed_inputs_and_pin_and_corrupt_record_fail_closed(self):
        for area in ('L0','L1','L2'):
            with self.subTest(area=area):
                self.paths[area].write_bytes(self.before[area]+b' changed')
                self.assertEqual(self.inspect()['state'],'foreign_or_changed');self.paths[area].write_bytes(self.before[area])
        real=probe._read;accessed=[]
        def track(parent,name,limit):accessed.append(name);return real(parent,name,limit)
        with patch.object(probe,'_read',side_effect=track):self.error('move_intent_pin_mismatch',self.inspect,'0'*64)
        self.assertEqual(accessed,['.move-pending'])  # При недостоверном marker реестры не открываются.
        self.marker.write_bytes(self.record[:20]);self.error('move_intent_pin_mismatch',self.inspect)
        self.error('move_intent_invalid',self.inspect,hashlib.sha256(self.marker.read_bytes()).hexdigest());self.verify_gate()
    def test_unsafe_marker_types_and_links_are_not_opened(self):
        self.marker.unlink()
        for kind in ('directory','symlink','dangling','fifo','hardlink','oversized'):
            with self.subTest(kind=kind):
                if kind=='directory':self.marker.mkdir()
                elif kind=='symlink':self.marker.symlink_to(self.sibling)
                elif kind=='dangling':self.marker.symlink_to(self.root/'absent')
                elif kind=='fifo':os.mkfifo(self.marker,0o600)
                elif kind=='hardlink':os.link(self.sibling,self.marker)
                else:self.marker.write_bytes(b'x'*(move_intent.MAX_INTENT+1))
                self.error('move_probe_unavailable',self.inspect);self.assertEqual(self.sibling.read_bytes(),b'keep');self.verify_gate()
                if kind=='directory':self.marker.rmdir()
                else:self.marker.unlink()
    def test_unsafe_registry_and_path_refuse(self):
        path=self.paths['L1'];path.unlink();path.symlink_to(self.sibling)
        self.error('move_probe_unavailable',self.inspect);self.assertEqual(self.sibling.read_bytes(),b'keep');self.verify_gate()
        path.unlink();path.write_bytes(self.before['L1'])
        # Результат не может использовать профиль с пересечением корней.
        self.error('profile_root_conflict',probe.inspect,store.Layout(self.root,'.domain-agent-kit/project'),intent_pin=self.pin)
    def test_real_writer_lock_blocks_separate_cli_and_releases(self):
        command=[sys.executable,'-I','-S','-B',str(ROOT/'kit/move_recovery_inspect.py'),
                 '--workspace',str(self.root),'--profile-root','profiles/pilot','--intent-pin',self.pin]
        fd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY)
        try:
            store.fcntl.flock(fd,store.fcntl.LOCK_EX|store.fcntl.LOCK_NB)
            proc=subprocess.run(command,capture_output=True,text=True,timeout=10)
            self.assertEqual(proc.returncode,1,proc.stderr);self.assertEqual(json.loads(proc.stdout)['diagnostic']['code'],'move_probe_busy')
        finally:os.close(fd)
        before=audit.tree_digest(self.root);proc=subprocess.run(command,capture_output=True,text=True,timeout=10)
        self.assertEqual(proc.returncode,0,proc.stderr);self.assertEqual(json.loads(proc.stdout)['state'],'before_both')
        self.assertNotIn('SECRET_SYNTHETIC_TEXT',proc.stdout+proc.stderr);self.assertEqual(before,audit.tree_digest(self.root));self.verify_gate()
    def test_content_change_during_read_is_rejected(self):
        original=os.read;calls=[]
        def mutate(fd,size):
            data=original(fd,size)
            if not calls:
                calls.append(True);self.marker.write_bytes(self.record+b'x')
            return data
        with patch.object(probe.os,'read',side_effect=mutate):self.error('move_probe_unavailable',self.inspect)
        self.assertTrue(calls);self.assertEqual(self.sibling.read_bytes(),b'keep');self.verify_gate()

    def test_exclusive_process_is_blocked_while_probe_reads(self):
        real=probe._read;tested=[]
        def competing(parent,name,limit):
            if not tested:
                tested.append(True)
                code='import fcntl,os,sys;f=os.open(sys.argv[1],os.O_RDONLY|os.O_DIRECTORY);fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)'
                proc=subprocess.run([sys.executable,'-I','-S','-B','-c',code,str(self.root)],capture_output=True,timeout=10)
                self.assertNotEqual(proc.returncode,0);self.assertIn(b'BlockingIOError',proc.stderr)
            return real(parent,name,limit)
        with patch.object(probe,'_read',side_effect=competing):self.assertEqual(self.inspect()['state'],'before_both')
        self.assertTrue(tested);self.verify_gate()

    def test_directory_moved_while_reading_is_detected(self):
        real=probe._read;calls=[];root=self.root
        def move_dir(parent,name,limit):
            result=real(parent,name,limit);calls.append(name)
            if name=='registry.json' and calls.count(name)==1:
                (root/'profiles/pilot').rename(root/'profiles/old');(root/'profiles/pilot').mkdir()
            return result
        with patch.object(probe,'_read',side_effect=move_dir):self.error('move_probe_unavailable',self.inspect)
        self.assertEqual(self.sibling.read_bytes(),b'keep');self.assertTrue(self.marker.exists())
    def test_rejects_missing_marker_and_invalid_platform(self):
        self.marker.unlink();self.error('move_probe_unavailable',self.inspect)
        with patch.object(probe.registry_store,'fcntl',None):self.error('move_probe_unavailable',self.inspect)
        self.assertEqual(self.sibling.read_bytes(),b'keep')

if __name__=='__main__':unittest.main()
