#!/usr/bin/env python3
"""Синтетический L2→L1 через закреплённую сессию, не приёмка продукта."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'research/audit')]
import core_audit as audit
import test_snapshot_move_session as fixture
import test_move_execution as execution_fixture
from kit import init_workspace as init, move_execution as execution, move_recovery_inspect as probe
from kit.base import registry_store as store


@unittest.skipUnless(init._supported() and store.fcntl is not None,'POSIX unavailable; not_run')
class SnapshotMoveReverseStudy(unittest.TestCase):
    def setUp(self):
        self.fx=fixture.SnapshotMoveTests();self.fx.setUp();self.addCleanup(self.fx.doCleanups)
        doc=json.loads(self.fx.project.read_bytes())
        doc['entries'].append(audit.entry('PROJECT-RULE','rule','project_owner','P-1','docs',state='active'))
        audit.write(self.fx.project,doc);self.fx.project.chmod(0o600)
        self.context={'project_names':[],'machine_names':[],'project_paths':[]}
        self.candidate=audit.entry('PROFILE-RULE','rule','profile_owner','C-1','docs',state='draft')
    def build(self,proc,lines,context):
        return self.fx.send(proc,lines,{'type':'build','source':'L2','target':'L1','entry_id':'PROJECT-RULE',
                                      'candidate':self.candidate,'portability_context':context})
    def configure(self,proc,lines,built):
        return self.fx.send(proc,lines,{'type':'configure','intent_utf8':built['intent_utf8'],
                                        'intent_pin':built['intent_sha256']})
    def test_reverse_move_restarted_after_reservation(self):
        before_l0=self.fx.l0.read_bytes();before=audit.tree_digest(self.fx.root)
        proc,lines=self.fx.launch()
        self.assertEqual(self.build(proc,lines,None)['outcome'],'error')
        self.assertEqual(before,audit.tree_digest(self.fx.root))
        built=self.build(proc,lines,self.context);self.assertEqual(built['outcome'],'intent_draft_only',built)
        self.assertEqual(self.configure(proc,lines,built)['outcome'],'configured')
        p=self.fx.plan(proc,lines,'reserve')
        reject=self.fx.send(proc,lines,{'type':'apply','plan':p,'confirmed_ticket':'wrong'})
        self.assertEqual(reject['outcome'],'error');self.assertFalse(self.fx.marker.exists())
        self.assertEqual(self.fx.apply(proc,lines,p)['outcome'],'reserved_not_moved')
        self.assertTrue(self.fx.marker.exists());proc.stdin.close();self.assertEqual(proc.wait(timeout=20),0)
        proc,lines=self.fx.launch();self.assertEqual(self.configure(proc,lines,built)['outcome'],'configured')
        self.assertEqual(self.fx.send(proc,lines,{'type':'inspect'})['state'],'before_both')
        p=self.fx.plan(proc,lines,'execute')
        self.assertEqual(self.fx.apply(proc,lines,p)['outcome'],'registries_updated_marker_retained')
        self.assertEqual(self.fx.send(proc,lines,{'type':'inspect'})['state'],'after_both')
        p=self.fx.plan(proc,lines,'finalize');self.assertEqual(self.fx.apply(proc,lines,p)['outcome'],'marker_removed_after_both')
        self.assertFalse(self.fx.marker.exists());self.assertEqual(self.fx.l0.read_bytes(),before_l0)
        l1=json.loads(self.fx.profile.read_bytes());l2=json.loads(self.fx.project.read_bytes())
        self.assertIn('PROFILE-RULE',{e['id'] for e in l1['registry']['entries']})
        self.assertNotIn('PROJECT-RULE',{e['id'] for e in l2['registry']['entries']})
        self.assertEqual(l1['journal']['decisions'][-1]['operation'],'create')
        self.assertEqual(l2['journal']['decisions'][-1]['operation'],'delete')

    def test_reverse_source_write_failure_preserves_target_and_source(self):
        f=execution_fixture.ExecutionTests();root,layout,files,before,raw,pin,neighbor=f.fixture('L2')
        self.addCleanup(f.doCleanups)
        session=f.session(layout,raw,pin);p=session.plan();real=execution.stage._replace_for_move;calls=[]
        def fail_source(*args,**kw):
            calls.append(1)
            if len(calls)==2:raise OSError('synthetic')
            return real(*args,**kw)
        with patch.object(execution.stage,'_replace_for_move',side_effect=fail_source):
            f.error('move_execution_unknown',session.apply,p,confirmed_ticket=p['ticket'])
        self.assertEqual(files['L2'].read_bytes(),before['L2'])
        self.assertNotEqual(files['L1'].read_bytes(),before['L1'])
        self.assertEqual(probe.inspect(layout,intent_pin=pin)['state'],'target_after_source_before')
        session=f.session(layout,raw,pin);p=session.plan()
        self.assertEqual(p['state'],'target_after_source_before')
        self.assertEqual(session.apply(p,confirmed_ticket=p['ticket'])['outcome'],'registries_updated_marker_retained')
        self.assertEqual(probe.inspect(layout,intent_pin=pin)['state'],'after_both')
        self.assertEqual(files['L0'].read_bytes(),before['L0'])

if __name__=='__main__':unittest.main()
