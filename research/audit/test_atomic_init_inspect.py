#!/usr/bin/env python3
"""Синтетическое наблюдение без очистки и без доверия к результату."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from kit import atomic_init, atomic_init_inspect as observer
from kit.init_workspace import InitializationError
from kit.verify_candidate import CANDIDATE_VERSION

try:atomic_init._rename_function();SUPPORTED=True
except InitializationError:SUPPORTED=False

@unittest.skipUnless(SUPPORTED,'Linux renameat2 unavailable; not_run')
class ObservationTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(prefix='atomic-inspect-');self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name).resolve();self.dest=self.root/'destination';self.marker=self.root/'neighbor';self.marker.write_bytes(b'private')
        self.raw=(json.dumps({'schema_version':2,'area':'L0','roots':['kit'],'release_version':CANDIDATE_VERSION,'entries':[]})+'\n').encode()
        self.pin=hashlib.sha256(self.raw).hexdigest()
        self.session=atomic_init.AtomicInitializationSession(self.dest,profile_root='profiles/x',l0_bytes=self.raw,system_pin=self.pin)
        self.plan=self.session.plan();self.stage=Path(self.plan['staging']['destination'])
    def inspect(self,**kw):
        args={'profile_root':'profiles/x','l0_bytes':self.raw,'system_pin':self.pin};args.update(kw)
        return observer.inspect(self.dest,self.stage,**args)
    def states(self):
        result=self.inspect();self.assertEqual(result['outcome'],'observation_only');self.assertEqual(result['recovery'],'not_performed')
        self.assertNotIn('private',repr(result));return result['destination_state'],result['staging_state']
    def apply(self):return self.session.apply(self.plan,confirmed_ticket=self.plan['ticket'])
    def test_before_and_after_publication(self):
        self.assertEqual(self.states(),('absent','absent'));self.apply()
        self.assertEqual(self.states(),('matches_observation','absent'))
        self.assertEqual(self.marker.read_bytes(),b'private')
    def test_interrupted_rename_leaves_observable_staging(self):
        with patch.object(atomic_init,'_rename_noreplace',side_effect=OSError('injected')):
            with self.assertRaisesRegex(InitializationError,'publication_unknown'):self.apply()
        self.assertEqual(self.states(),('absent','matches_observation'))
        self.dest.mkdir(mode=0o700);self.assertEqual(self.states(),('different','matches_observation'))
        self.assertEqual(self.marker.read_bytes(),b'private')
    def test_corruption_extra_missing_metadata_and_symlink(self):
        self.apply();self.assertEqual(self.states()[0],'matches_observation')
        f=self.dest/'profiles/x/registry.json';old=f.read_bytes();f.write_bytes(b'bad')
        self.assertEqual(self.states()[0],'different');f.write_bytes(old)
        f.chmod(0o644);self.assertEqual(self.states()[0],'different');f.chmod(0o600)
        extra=self.dest/'extra';extra.write_text('not read');self.assertEqual(self.states()[0],'different');extra.unlink()
        f.unlink();self.assertEqual(self.states()[0],'different')
        f.symlink_to(self.marker);self.assertIn(self.states()[0],('unavailable','different'))
        self.assertEqual(self.marker.read_bytes(),b'private')
    def test_fifo_does_not_block_or_read(self):
        self.apply();f=self.dest/'profiles/x/registry.json';f.unlink();os.mkfifo(f,0o600)
        self.assertEqual(self.states()[0],'different')
    def test_bad_paths_and_wrong_inputs_fail_closed(self):
        for stage in (self.root/'another',self.root/'../escape'/self.stage.name,self.dest,self.root.parent/self.stage.name):
            with self.subTest(stage=stage):
                with self.assertRaisesRegex(InitializationError,'inspection_paths_invalid'):
                    observer.inspect(self.dest,stage,profile_root='profiles/x',l0_bytes=self.raw,system_pin=self.pin)
        with self.assertRaisesRegex(InitializationError,'system_pin_mismatch'):self.inspect(system_pin='0'*64)
        self.assertEqual(self.states(),('absent','absent'))
    def test_unreadable_or_changing_parent_is_not_absent(self):
        self.apply()
        with patch.object(observer.os,'listdir',side_effect=PermissionError('injected')) as mocked:
            with patch.object(observer.os,'supports_fd',observer.os.supports_fd | {mocked}):
                self.assertEqual(self.states()[0],'unavailable')
        original=observer.init._open_parent;count=[0]
        def changed(path):
            fd,identity=original(path);count[0]+=1
            return fd, (identity[0],identity[1]+1) if count[0]==2 else identity
        with patch.object(observer.init,'_open_parent',side_effect=changed):
            with self.assertRaisesRegex(InitializationError,'inspection_parent_changed'):self.inspect()
    def test_observe_after_real_process_exit_before_and_after_rename(self):
        program=r'''import hashlib,json,os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1]);from kit import atomic_init as a
raw=bytes.fromhex(sys.argv[3]);s=a.AtomicInitializationSession(Path(sys.argv[2]),profile_root='profiles/x',l0_bytes=raw,system_pin=hashlib.sha256(raw).hexdigest())
p=s.plan();print(json.dumps(p),flush=True);real=a._rename_noreplace
def stop(*args):
 if sys.argv[4]=='after':real(*args)
 os._exit(77)
a._rename_noreplace=stop;s.apply(p,confirmed_ticket=p['ticket'])
'''
        for phase in ('before','after'):
            with self.subTest(phase=phase):
                self.dest=self.root/phase
                run=subprocess.run([sys.executable,'-I','-S','-B','-c',program,str(ROOT),str(self.dest),self.raw.hex(),phase],capture_output=True,text=True,timeout=15)
                self.assertEqual(run.returncode,77,run.stderr);self.stage=Path(json.loads(run.stdout)['staging']['destination'])
                self.assertEqual(self.states(),('absent','matches_observation') if phase=='before' else ('matches_observation','absent'))
                self.assertEqual(self.marker.read_bytes(),b'private')

    def test_cli_inspection_revokes_plan(self):
        cmd=[sys.executable,'-I','-S','-B',str(ROOT/'kit/init_workspace_cli.py')]
        with subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) as proc:
            def send(obj):
                proc.stdin.write(json.dumps(obj)+'\n');proc.stdin.flush();return json.loads(proc.stdout.readline())
            plan=send({'type':'plan_atomic','destination':str(self.dest),'profile_root':'profiles/x','l0_utf8':self.raw.decode(),'system_pin':self.pin})
            result=send({'type':'inspect_atomic','destination':str(self.dest),'staging':plan['staging']['destination'],
                         'profile_root':'profiles/x','l0_utf8':self.raw.decode(),'system_pin':self.pin})
            self.assertEqual(result['destination_state'],'absent');self.assertEqual(result['staging_state'],'absent')
            self.assertEqual(send({'type':'apply','plan':plan,'confirmed_ticket':plan['ticket']})['code'],'ticket_unknown')
        self.assertFalse(self.dest.exists());self.assertEqual(self.marker.read_bytes(),b'private')

if __name__=='__main__':unittest.main()
