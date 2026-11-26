#!/usr/bin/env python3
"""Два синтетических контейнера, явная копия L1; не живой агент и не синхронизация."""
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'research/audit')]
import core_audit as audit
import release_install_study as install
import release_policy_study as policy
import test_release_install_study as fixture
import test_atomic_init as atomic
import test_source_release_trust as signing
from kit import profile_copy
from kit.base import operation_card, operation_plan, registry_store as store
from kit.base.registry_policy import StoreError


@unittest.skipUnless(atomic.SUPPORTED and signing.SUPPORTED and store.fcntl is not None,'Linux/OpenSSL unavailable; not_run')
class InstalledPortabilityTests(unittest.TestCase):
    def setUp(self):
        self.fx=fixture.InstallTests();self.fx.setUp();self.addCleanup(self.fx.doCleanups)
        self.containers=[];self.layouts=[]
        for name in ('project-a','project-b'):
            dest=self.fx.root/name
            session=install.InstallSession(dest,profile_root='profiles/pilot',archive_bytes=self.fx.raw,
                     statement=policy.canonical(self.fx.f.doc),signature=self.fx.f.sign(),policy=self.fx.f.policy,
                     verify_signature=self.fx.f.fx.verify)
            p=session.plan();self.assertEqual(session.apply(p,confirmed_ticket=p['ticket'])['outcome'],
                                                'study_container_published_unverified_origin')
            self.containers.append(dest);self.layouts.append(store.Layout(dest/'workspace','profiles/pilot'))
        self.a,self.b=self.layouts
        for i,layout in enumerate(self.layouts):
            path=layout.workspace/'.domain-agent-kit/project/registry.json'
            doc=json.loads(path.read_bytes());doc['entries']=[audit.entry('P-'+str(i),'contract','project_owner',None,'docs',state='draft')]
            audit.write(path,doc);path.chmod(0o600)
        session=operation_plan.PlanSession(self.a,profile_id='Pilot')
        request='Создай черновик контракта C-9 в профиле Pilot, постоянное, область «docs», название «Пример», основание «Проба», критерий «Запись существует»: Согласуем порядок чтения.'
        p=session.plan(operation_card.compile_prompt(request));self.assertEqual(p['outcome'],'planned')
        self.assertEqual(session.apply(p,confirmed_ticket=p['ticket'])['outcome'],'applied')
        self.pin=hashlib.sha256(self.fx.f.files['kit/SYSTEM-L0.json']).hexdigest()
    def session(self):return profile_copy.ProfileCopySession(self.a,self.b,system_pin=self.pin)
    def test_copy_history_and_two_project_l2_remain_distinct(self):
        project_paths=[x.workspace/'.domain-agent-kit/project/registry.json' for x in self.layouts]
        before_l2=[p.read_bytes() for p in project_paths];self.assertNotEqual(*before_l2)
        before_source=audit.tree_digest(self.a.workspace);s=self.session();p=s.plan()
        with self.assertRaises(StoreError) as err:s.apply(p,confirmed_ticket='wrong')
        self.assertEqual(err.exception.code,'confirmation_required')
        self.assertEqual(s.apply(p,confirmed_ticket=p['ticket'])['outcome'],'profile_copied')
        self.assertEqual(audit.tree_digest(self.a.workspace),before_source)
        self.assertEqual([p.read_bytes() for p in project_paths],before_l2)
        self.assertEqual(store.registry_history(self.a,target='L1'),store.registry_history(self.b,target='L1'))
        self.assertEqual((self.a.workspace/'profiles/pilot/registry.json').read_bytes(),
                         (self.b.workspace/'profiles/pilot/registry.json').read_bytes())
        self.assertEqual(self.session().plan()['outcome'],'no_change')
    def test_conflicting_target_and_source_drift_refuse_without_copy(self):
        s=self.session();p=s.plan();source=self.a.workspace/'profiles/pilot/registry.json'
        source.write_bytes(source.read_bytes()+b' ')
        with self.assertRaises(StoreError) as err:s.apply(p,confirmed_ticket=p['ticket'])
        self.assertEqual(err.exception.code,'stale_plan')
        target=self.b.workspace/'profiles/pilot/registry.json';target.write_bytes(target.read_bytes()+b' ')
        with self.assertRaises(StoreError) as err:self.session().plan()
        self.assertEqual(err.exception.code,'profile_copy_target_not_pristine')

if __name__=='__main__':unittest.main()
