#!/usr/bin/env python3
"""Синтетический preflight: никакое обновление или N−1 не выполняются."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'research/audit')]
import core_audit as audit
import release_archive_study as archive
import release_policy_study as policy
import release_update_preflight_study as preflight
import test_release_policy_study as policy_fixture
import test_profile_copy as workspace_fixture
import test_atomic_init as atomic
import test_source_release_trust as signing
from kit.base import registry_store as store


@unittest.skipUnless(atomic.SUPPORTED and signing.SUPPORTED and store.fcntl is not None,'Linux/OpenSSL unavailable; not_run')
class UpdatePreflightTests(unittest.TestCase):
    def setUp(self):
        self.w=workspace_fixture.ProfileCopyTests();self.w.setUp();self.addCleanup(self.w.doCleanups)
        self.f=policy_fixture.ReleasePolicyStudyTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
    def assess(self,data=None,*,pin=None,signature=None,wire=None):
        if data is None:data={'doc':self.f.doc,'manifest':self.f.manifest,'files':self.f.files}
        statement=policy.canonical(data['doc'])
        if signature is None:signature=self.f.fx.sign(statement,domain=policy.DOMAIN)
        if wire is None:wire=archive.build(data['manifest'],data['files'])
        return preflight.assess(self.w.a,old_system_pin=self.w.pin if pin is None else pin,
              archive_bytes=wire,statement=statement,signature=signature,policy=self.f.policy,
              verify_signature=self.f.fx.verify)
    def test_preflight_is_read_only_and_preserves_histories(self):
        before=audit.tree_digest(self.w.a.workspace);result=self.assess()
        self.assertEqual(result['outcome'],'structural_preflight_only');self.assertFalse(result['system_changed'])
        self.assertEqual(result['update'],'not_performed');self.assertEqual(result['code_compatibility'],'not_checked')
        self.assertEqual(result['l1_sha256'],hashlib.sha256(self.w.a1.read_bytes()).hexdigest())
        self.assertEqual(audit.tree_digest(self.w.a.workspace),before)
    def test_resigned_modified_l0_structural_only(self):
        system=json.loads(self.f.files['kit/SYSTEM-L0.json']);system['entries'][0]['text']+=' synthetic extra'
        data=self.f.system_fixture(system);before=audit.tree_digest(self.w.a.workspace)
        result=self.assess(data);self.assertTrue(result['system_changed'])
        self.assertEqual(result['semantics'],'not_checked');self.assertEqual(result['rollback'],'not_performed')
        self.assertEqual(audit.tree_digest(self.w.a.workspace),before)
    def test_unsupported_version_is_not_called_n_plus_one(self):
        system=json.loads(self.f.files['kit/SYSTEM-L0.json']);system['release_version']='0.2.0-mvp.73'
        data=self.f.system_fixture(system);manifest=json.loads(data['manifest']);manifest['version']=system['release_version']
        data['manifest']=(json.dumps(manifest)+'\n').encode();data['doc']['version']=system['release_version']
        data['doc']['manifest_sha256']=policy.sha(data['manifest'])
        with self.assertRaisesRegex(preflight.UpdateError,'candidate_version_unsupported'):self.assess(data)
    def test_invalid_signature_old_pin_and_pending_state_refuse(self):
        with self.assertRaisesRegex(preflight.UpdateError,'archive_unverified'):self.assess(signature=bytes(64))
        with self.assertRaisesRegex(preflight.UpdateError,'workspace_or_catalog_invalid'):self.assess(pin='0'*64)
        marker=self.w.a.workspace/'.domain-agent-kit/.move-pending';marker.write_bytes(b'pending')
        with self.assertRaisesRegex(preflight.UpdateError,'workspace_or_catalog_invalid'):self.assess()
        self.assertTrue(marker.exists())

if __name__=='__main__':unittest.main()
