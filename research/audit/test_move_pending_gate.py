#!/usr/bin/env python3
"""Зарезервированное имя: только синтетические деревья и отсутствие автоматической очистки."""
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
from kit.base import applicability, registry_store as store
from kit.base.operation_plan import PlanSession
from kit.base.registry_policy import StoreError

class GateTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(prefix='move-gate-');self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name).resolve();self.layout=audit.make_workspace(self.root,parent_scope='.')
        self.marker=self.root/'.domain-agent-kit/.move-pending'
        self.sibling=self.root/'sibling';self.sibling.write_bytes(b'synthetic preserved')
        self.paths=[self.root/'kit/base/registry.json',self.root/'profiles/pilot/registry.json',
                    self.root/'.domain-agent-kit/project/registry.json']
    def error(self,code,fn,*args,**kw):
        with self.assertRaises(StoreError) as e:fn(*args,**kw)
        self.assertEqual(e.exception.code,code)
    def setup_plan(self):
        s=PlanSession(self.layout,profile_id='Pilot');p=s.plan(audit.card(ident='Q-77'))
        n=store.plan_create(self.layout,audit.entry('R-77','rule','profile_owner','C-1','docs',state='draft'))
        return s,p,n
    def blocked(self,s,p,n):
        before=[p.read_bytes() for p in self.paths];sibling=self.sibling.read_bytes()
        for call in (lambda:store.status(self.layout),lambda:store.read_registry(self.layout,target='L1'),
                     lambda:store.registry_history(self.layout,target='L2'),lambda:store.report_conflicts(self.layout),
                     lambda:applicability.applicable(self.layout,scope='docs'),
                     lambda:store.plan_create(self.layout,audit.entry('R-78','rule','profile_owner','C-1','docs',state='draft'))):
            self.error('move_pending',call)
        self.error('move_pending',s.apply,p,confirmed_ticket=p['ticket'])
        self.error('ticket_unknown',s.apply,p,confirmed_ticket=p['ticket'])
        self.error('move_pending',store.apply_create,self.layout,n,confirmed_ticket=n['ticket'])
        self.assertEqual(before,[p.read_bytes() for p in self.paths]);self.assertEqual(self.sibling.read_bytes(),sibling)
        self.assertTrue(self.marker.is_symlink() or self.marker.exists())
    def test_each_existing_type_blocks_read_and_old_confirmed_plans(self):
        for kind in ('file','directory','symlink','dangling'):
            with self.subTest(kind=kind):
                s,p,n=self.setup_plan()
                if kind=='file':self.marker.write_bytes(b'not inspected')
                elif kind=='directory':self.marker.mkdir()
                elif kind=='symlink':self.marker.symlink_to(self.sibling)
                else:self.marker.symlink_to(self.root/'does-not-exist')
                self.blocked(s,p,n)
                # Только тестовый собственный объект временного каталога очищается фикстурой.
                if kind=='directory':self.marker.rmdir()
                else:self.marker.unlink()
                self.assertEqual(store.status(self.layout)['profile_revision'],0)
    def test_lstat_error_and_parent_unavailable_refuse(self):
        original=Path.lstat
        def failure(path):
            if path==self.marker:raise PermissionError('synthetic')
            return original(path)
        with patch.object(Path,'lstat',failure):self.error('move_state_unavailable',store.status,self.layout)
        original_existing=store._existing;calls=[]
        def fail_second(workspace,rel,**kwargs):
            if rel=='.domain-agent-kit':
                calls.append(True)
                if len(calls)==2:raise StoreError('missing_path',rel)
            return original_existing(workspace,rel,**kwargs)
        with patch.object(store,'_existing',fail_second):self.error('move_state_unavailable',store.status,self.layout)
        calls.clear()
        def changed_parent(workspace,rel,**kwargs):
            path,info=original_existing(workspace,rel,**kwargs)
            if rel=='.domain-agent-kit':
                calls.append(True)
                if len(calls)==2:
                    values=list(info);values[1]+=1;info=os.stat_result(values)
            return path,info
        with patch.object(store,'_existing',changed_parent):self.error('move_state_unavailable',store.status,self.layout)
        self.assertFalse(self.marker.exists());self.assertEqual(self.sibling.read_bytes(),b'synthetic preserved')
    def test_abrupt_external_process_leaves_marker_and_blocks(self):
        s,p,n=self.setup_plan()
        code='from pathlib import Path;import os,sys;Path(sys.argv[1]).write_bytes(b"interrupted");os._exit(77)'
        proc=subprocess.run([sys.executable,'-I','-S','-B','-c',code,str(self.marker)],capture_output=True,timeout=10)
        self.assertEqual(proc.returncode,77);self.blocked(s,p,n);self.assertEqual(self.marker.read_bytes(),b'interrupted')
    def test_marker_absence_is_not_proof_of_consistency(self):
        # Два активных варианта могут существовать без маркера: барьер не проверяет историю транзакции.
        for path,ident,authority,parent in ((self.paths[1],'SRC','profile_owner','C-1'),
                                            (self.paths[2],'DST','project_owner','P-1')):
            doc=json.loads(path.read_bytes())
            doc['entries'].append(audit.entry(ident,'rule',authority,parent,'docs',state='active',text='same synthetic rule'))
            audit.write(path,doc)
        report=applicability.applicable(self.layout,scope='docs')
        self.assertFalse(self.marker.exists())
        self.assertEqual(report['outcome'],'applicable')
        self.assertTrue({'SRC','DST'} <= {row['entry']['id'] for row in report['entries']})

if __name__=='__main__':unittest.main()
