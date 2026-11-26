#!/usr/bin/env python3
"""Синтетические пробы экспериментальной установки в новый контейнер."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'research/audit')]
import release_archive_study as archive
import release_policy_study as policy
import release_install_study as install
import test_release_policy_study as fixture
import test_atomic_init as platform
import test_source_release_trust as signing


@unittest.skipUnless(signing.SUPPORTED and platform.SUPPORTED, 'OpenSSL/Linux unavailable; not_run')
class InstallTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.ReleasePolicyStudyTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.tmp=tempfile.TemporaryDirectory(prefix='install-study-'); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve(); self.dest=self.root/'container'
        self.raw=archive.build(self.f.manifest,self.f.files)
        self.s=install.InstallSession(self.dest,profile_root='profiles/pilot',archive_bytes=self.raw,
                  statement=policy.canonical(self.f.doc),signature=self.f.sign(),policy=self.f.policy,
                  verify_signature=self.f.fx.verify)
    def test_plan_confirm_publish_and_bootstrap(self):
        p=self.s.plan(); self.assertFalse(self.dest.exists())
        self.assertEqual(p['effect'],'publish_new_snapshot_and_workspace')
        with self.assertRaisesRegex(install.InstallError,'confirmation_required'):
            self.s.apply(p,confirmed_ticket='wrong')
        with self.assertRaisesRegex(install.InstallError,'confirmation_required'):
            self.s.apply(p,confirmed_ticket='я'*64)
        self.assertFalse(self.dest.exists())
        result=self.s.apply(p,confirmed_ticket=p['ticket'])
        self.assertEqual(result['outcome'],'study_container_published_unverified_origin')
        snapshot=self.dest/'snapshot'; workspace=self.dest/'workspace'
        self.assertEqual((workspace/'kit/base/registry.json').read_bytes(),self.f.files['kit/SYSTEM-L0.json'])
        args=[sys.executable,'-I','-S','-B',str(ROOT/'kit/snapshot_session.py'),
              '--candidate-root',str(snapshot),'--workspace',str(workspace),
              '--profile-root','profiles/pilot','--profile-id','Pilot',
              '--manifest-pin',hashlib.sha256(self.f.manifest).hexdigest(),
              '--system-pin',hashlib.sha256(self.f.files['kit/SYSTEM-L0.json']).hexdigest()]
        commands=[{'type':'bootstrap'}]+[{'type':'context','mode':mode,'scope':'docs/a',
                    'choices':{'include':[],'exclude':[]}} for mode in ('project','kit')]
        proc=subprocess.run(args,input=''.join(json.dumps(c)+'\n' for c in commands),capture_output=True,text=True,timeout=25)
        self.assertEqual(proc.returncode,0,proc.stderr)
        replies=[json.loads(line) for line in proc.stdout.splitlines()]
        self.assertEqual(replies[0]['outcome'],'bootstrap')
        for reply,expected in zip(replies[1:],('SYS-PROJECT-MODE','SYS-KIT-MODE')):
            self.assertEqual(reply['outcome'],'review_required')
            self.assertIn(expected,{row['entry']['id'] for row in reply['entries'] if row['area']=='L0'})
        self.assertEqual(len(replies),3)
        with self.assertRaisesRegex(install.InstallError,'ticket_unknown'):
            self.s.apply(p,confirmed_ticket=p['ticket'])
    def test_tamper_cancel_and_occupied(self):
        p=self.s.plan(); altered=copy.deepcopy(p);altered['workspace_root']+='bad'
        with self.assertRaisesRegex(install.InstallError,'plan_mismatch'):
            self.s.apply(altered,confirmed_ticket=p['ticket'])
        with self.assertRaisesRegex(install.InstallError,'ticket_unknown'):
            self.s.apply(p,confirmed_ticket=p['ticket'])
        p=self.s.plan();self.s.cancel()
        with self.assertRaisesRegex(install.InstallError,'ticket_unknown'):
            self.s.apply(p,confirmed_ticket=p['ticket'])
        self.dest.mkdir()
        with self.assertRaisesRegex(install.InstallError,'destination_occupied'):self.s.plan()
        self.assertEqual(list(self.dest.iterdir()),[])
    def test_bad_profile_signature_and_changed_profile_refused(self):
        self.s._inner.profile_root='../escape'
        with self.assertRaisesRegex(install.InstallError,'workspace_incompatible'):self.s.plan()
        self.s._inner.profile_root='profiles/pilot';p=self.s.plan()
        self.s._inner.profile_root='profiles/other'
        with self.assertRaisesRegex(install.InstallError,'stale_plan'):self.s.apply(p,confirmed_ticket=p['ticket'])
        self.assertFalse(self.dest.exists())
        self.s._inner.signature=bytes(64)
        with self.assertRaisesRegex(install.InstallError,'archive_unverified'):self.s.plan()
    def test_rename_failure_is_unknown_and_no_cleanup(self):
        p=self.s.plan()
        with mock.patch.object(install.publish.atomic,'_rename_noreplace',side_effect=OSError('injected')):
            with self.assertRaisesRegex(install.InstallError,'publication_unknown'):
                self.s.apply(p,confirmed_ticket=p['ticket'])
        stage=self.root/p['publication_plan']['stage_name']
        self.assertTrue(stage.is_dir());self.assertFalse(self.dest.exists())
        with self.assertRaisesRegex(install.InstallError,'ticket_unknown'):
            self.s.apply(p,confirmed_ticket=p['ticket'])

if __name__=='__main__':unittest.main()
