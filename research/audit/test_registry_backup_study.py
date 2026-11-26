#!/usr/bin/env python3
"""Синтетические реестры и история в памяти; без файлов бэкапа или реальных данных."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'research/audit')]
import registry_backup_study as backup
import test_profile_copy as fixture
import test_atomic_init as atomic
import core_audit as audit
from kit.base import registry_store as store


@unittest.skipUnless(atomic.SUPPORTED and store.fcntl is not None,'POSIX/Linux unavailable; not_run')
class BackupTests(unittest.TestCase):
    def setUp(self):
        self.fx=fixture.ProfileCopyTests();self.fx.setUp();self.addCleanup(self.fx.doCleanups)
    def capture(self):return backup.capture(self.fx.a,system_pin=self.fx.pin)
    def test_roundtrip_exact_bytes_history_and_separate_copy(self):
        before=audit.tree_digest(self.fx.a.workspace);wire,report=self.capture()
        self.assertEqual(report['backup_file'],'not_written');self.assertEqual(report['authenticity'],'not_verified')
        result,data=backup.inspect(wire,system_pin=self.fx.pin)
        self.assertEqual(result['restore'],'not_performed')
        self.assertEqual(audit.tree_digest(self.fx.a.workspace),before)
        for area,path in [('L0',self.fx.a.workspace/'kit/base/registry.json'),('L1',self.fx.a1),('L2',self.fx.ap)]:
            self.assertEqual(data[area],path.read_bytes())
        # Исследовательская копия только на временном workspace, не API восстановления.
        (self.fx.b.workspace/'kit/base/registry.json').write_bytes(data['L0'])
        self.fx.b1.write_bytes(data['L1']);self.fx.bp.write_bytes(data['L2'])
        self.assertEqual(store.registry_history(self.fx.a,target='L1'),store.registry_history(self.fx.b,target='L1'))
        self.assertEqual(store.registry_history(self.fx.a,target='L2'),store.registry_history(self.fx.b,target='L2'))
        self.assertEqual(audit.tree_digest(self.fx.a.workspace),before)
    def test_invalid_hash_pin_duplicate_and_size(self):
        wire,_=self.capture();doc=json.loads(wire)
        with self.assertRaisesRegex(backup.BackupError,'system_pin_mismatch'):backup.inspect(wire,system_pin='0'*64)
        doc['registries']['L1']['sha256']='0'*64
        with self.assertRaisesRegex(backup.BackupError,'snapshot_invalid'):backup.inspect(backup._canonical(doc),system_pin=self.fx.pin)
        malformed=json.loads(wire);malformed['registries']['L1']['base64']='%%%'
        with self.assertRaisesRegex(backup.BackupError,'snapshot_invalid'):backup.inspect(backup._canonical(malformed),system_pin=self.fx.pin)
        with self.assertRaisesRegex(backup.BackupError,'snapshot_invalid'):backup.inspect(b'{"format":1,"format":1}',system_pin=self.fx.pin)
        with self.assertRaisesRegex(backup.BackupError,'snapshot_invalid'):backup.inspect(wire+b' ',system_pin=self.fx.pin)
        with self.assertRaisesRegex(backup.BackupError,'snapshot_invalid'):backup.inspect(b'x'*(backup.MAX_WIRE+1),system_pin=self.fx.pin)
    def test_consistently_rehashed_wrong_root_and_broken_history_refused(self):
        wire,_=self.capture()
        for change in ('root','history'):
            with self.subTest(change=change):
                obj=json.loads(wire);row=obj['registries']['L1'];doc=json.loads(base64.b64decode(row['base64']))
                if change=='root':doc['registry']['roots']=['profiles/other']
                else:doc['journal']['decisions'][0]['after_sha256']='0'*64
                raw=(json.dumps(doc)+'\n').encode();row.update(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),base64=base64.b64encode(raw).decode())
                with self.assertRaises(backup.BackupError):backup.inspect(backup._canonical(obj),system_pin=self.fx.pin)
    def test_self_hash_does_not_prove_source(self):
        wire,_=self.capture();obj=json.loads(wire);row=obj['registries']['L1']
        raw=base64.b64decode(row['base64'])+b' '
        row.update(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),base64=base64.b64encode(raw).decode())
        report,data=backup.inspect(backup._canonical(obj),system_pin=self.fx.pin)
        self.assertEqual(report['authenticity'],'not_verified')
        self.assertEqual(data['L1'],raw)

    def test_pending_move_and_copy_refused(self):
        marker=self.fx.a.workspace/'.domain-agent-kit/.move-pending';marker.write_bytes(b'pending')
        with self.assertRaisesRegex(backup.BackupError,'source_unavailable:move_pending'):self.capture()
        marker.unlink();stage=self.fx.a1.parent/'.profile-copy-stage-test';stage.write_bytes(b'x')
        with self.assertRaisesRegex(backup.BackupError,'source_unavailable:profile_copy_pending'):self.capture()
        self.assertTrue(stage.exists())

if __name__=='__main__':unittest.main()
