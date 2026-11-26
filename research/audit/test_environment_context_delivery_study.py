#!/usr/bin/env python3
"""Тест ручного экспорта в синтетическую директорию, не наблюдение живого агента."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'research/audit')]
import core_audit as audit
import environment_context_delivery_study as delivery
import test_context_modes as fixture


class ManualContextTests(unittest.TestCase):
    def setUp(self):
        self.fx=fixture.ContextTests();self.fx.setUp();self.addCleanup(self.fx.doCleanups)
        self.temp=tempfile.TemporaryDirectory(prefix='manual-context-');self.addCleanup(self.temp.cleanup)
        self.dest=Path(self.temp.name).resolve()
    def session(self,env='arena',mode='project',name='context'):
        return delivery.ManualContextSession(self.fx.layout,self.dest/name,environment=env,mode=mode,
                                              scope='docs/file',choices=copy.deepcopy(self.fx.choices))
    def test_six_explicit_manual_files_two_modes_without_agent_claim(self):
        before=audit.tree_digest(self.fx.root)
        for env in delivery.ENVIRONMENTS:
            for mode in ('project','kit'):
                with self.subTest(env=env,mode=mode):
                    target=env+'-'+mode;s=self.session(env,mode,target);p=s.plan()
                    self.assertFalse((self.dest/target).exists());self.assertEqual(p['delivery'],'not_performed')
                    with self.assertRaisesRegex(delivery.DeliveryError,'confirmation_required'):
                        s.apply(p,confirmed_ticket='wrong')
                    result=s.apply(p,confirmed_ticket=p['ticket'])
                    self.assertEqual(result['outcome'],'manual_context_file_created')
                    self.assertEqual((result['detected'],result['read'],result['applied']),('not_run',)*3)
                    raw=(self.dest/target).read_bytes();doc=json.loads(raw)
                    self.assertEqual(hashlib.sha256(raw).hexdigest(),p['export_plan']['content_sha256'])
                    self.assertEqual(doc['context']['mode'],mode)
                    self.assertNotIn(b'EXCLUDED_PROFILE_SECRET',raw);self.assertNotIn(b'EXCLUDED_PROJECT_SECRET',raw)
                    self.assertIn(('SYS-PROJECT-MODE' if mode=='project' else 'SYS-KIT-MODE').encode(),raw)
        self.assertEqual(audit.tree_digest(self.fx.root),before)
    def test_cancel_tamper_drift_and_occupied_refuse(self):
        s=self.session();p=s.plan();altered=copy.deepcopy(p);altered['environment']='copilot'
        with self.assertRaisesRegex(delivery.DeliveryError,'plan_mismatch'):s.apply(altered,confirmed_ticket=p['ticket'])
        with self.assertRaisesRegex(delivery.DeliveryError,'ticket_unknown'):s.apply(p,confirmed_ticket=p['ticket'])
        p=s.plan();s.cancel()
        with self.assertRaisesRegex(delivery.DeliveryError,'ticket_unknown'):s.apply(p,confirmed_ticket=p['ticket'])
        p=s.plan();self.fx.paths['L1'].write_bytes(self.fx.paths['L1'].read_bytes()+b' ')
        with self.assertRaisesRegex(delivery.DeliveryError,'stale_plan'):s.apply(p,confirmed_ticket=p['ticket'])
        self.assertFalse((self.dest/'context').exists())
        (self.dest/'context').write_bytes(b'foreign')
        with self.assertRaisesRegex(delivery.DeliveryError,'context_export_destination_occupied'):s.plan()
        self.assertEqual((self.dest/'context').read_bytes(),b'foreign')
    def test_invalid_environment_and_repository_destination_refuse(self):
        with self.assertRaisesRegex(delivery.DeliveryError,'environment_invalid'):self.session('unknown')
        s=delivery.ManualContextSession(self.fx.layout,ROOT/'not-allowed.json',environment='arena',
                                         mode='project',scope='docs/file',choices=self.fx.choices)
        with self.assertRaisesRegex(delivery.DeliveryError,'destination_invalid'):s.plan()

if __name__=='__main__':unittest.main()
