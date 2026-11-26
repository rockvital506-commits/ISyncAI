#!/usr/bin/env python3
"""Копирование L1: только синтетические workspace; не проверка живого агента."""
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

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'research/audit')]
import core_audit as audit
import test_atomic_init as atomic_tests
from kit import atomic_init, profile_copy
from kit.base import operation_card, operation_plan, registry_store as store
from kit.base.registry_policy import StoreError


@unittest.skipUnless(atomic_tests.SUPPORTED and store.fcntl is not None,'POSIX/Linux unavailable; not_run')
class ProfileCopyTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='profile-copy-');self.addCleanup(temp.cleanup)
        self.root=Path(temp.name).resolve();self.l0=(ROOT/'kit/SYSTEM-L0.json').read_bytes()
        self.pin=hashlib.sha256(self.l0).hexdigest();self.layouts=[]
        for name in ('A','B'):
            path=self.root/name;s=atomic_init.AtomicInitializationSession(path,profile_root='profiles/pilot',l0_bytes=self.l0,system_pin=self.pin)
            p=s.plan();s.apply(p,confirmed_ticket=p['ticket']);self.layouts.append(store.Layout(path,'profiles/pilot'))
        self.a,self.b=self.layouts;self.a1=self.a.workspace/'profiles/pilot/registry.json';self.b1=self.b.workspace/'profiles/pilot/registry.json'
        self.ap=self.a.workspace/'.domain-agent-kit/project/registry.json';self.bp=self.b.workspace/'.domain-agent-kit/project/registry.json'
        session=operation_plan.PlanSession(self.a,profile_id='Pilot')
        req='Создай черновик контракта C-9 в профиле Pilot, постоянное, область «docs», название «Пример», основание «Проба», критерий «Запись существует»: Согласуем порядок чтения.'
        plan=session.plan(operation_card.compile_prompt(req));self.assertEqual(plan['outcome'],'planned')
        self.assertEqual(session.apply(plan,confirmed_ticket=plan['ticket'])['outcome'],'applied')

    def session(self):return profile_copy.ProfileCopySession(self.a,self.b,system_pin=self.pin)
    def error(self,code,fn,*args,**kw):
        with self.assertRaises(StoreError) as error:fn(*args,**kw)
        self.assertEqual(error.exception.code,code)
    def test_copy_preserves_history_and_projects_and_requires_confirmation(self):
        before_a=audit.tree_digest(self.a.workspace);before_b_l0=(self.b.workspace/'kit/base/registry.json').read_bytes()
        before_ap=self.ap.read_bytes();before_bp=self.bp.read_bytes();source=self.a1.read_bytes();s=self.session();p=s.plan()
        self.assertEqual(p['outcome'],'planned');self.assertIn('C-9',p['target_after_utf8'])
        self.assertNotEqual(source,self.b1.read_bytes());self.error('confirmation_required',s.apply,p,confirmed_ticket='wrong')
        self.assertNotEqual(source,self.b1.read_bytes());self.assertEqual(s.apply(p,confirmed_ticket=p['ticket'])['outcome'],'profile_copied')
        self.assertEqual(source,self.b1.read_bytes());self.assertEqual(before_a,audit.tree_digest(self.a.workspace))
        self.assertEqual(before_b_l0,(self.b.workspace/'kit/base/registry.json').read_bytes())
        self.assertEqual(before_ap,self.ap.read_bytes());self.assertEqual(before_bp,self.bp.read_bytes())
        self.assertEqual(store.registry_history(self.a,target='L1'),store.registry_history(self.b,target='L1'))
        self.error('ticket_unknown',s.apply,p,confirmed_ticket=p['ticket'])
        self.assertEqual(self.session().plan()['outcome'],'no_change')

    def test_nonpristine_target_refused_even_when_empty_different_bytes(self):
        before=self.b1.read_bytes();self.b1.write_bytes(before+b' ');s=self.session()
        self.error('profile_copy_target_not_pristine',s.plan)
        self.assertEqual(self.b1.read_bytes(),before+b' ')

    def test_edited_plan_and_drift_never_overwrite(self):
        s=self.session();p=s.plan();changed=copy.deepcopy(p);changed['target_after_utf8']+=' '
        self.error('plan_mismatch',s.apply,changed,confirmed_ticket=p['ticket'])
        self.error('ticket_unknown',s.apply,p,confirmed_ticket=p['ticket'])
        self.assertNotEqual(self.a1.read_bytes(),self.b1.read_bytes())
        s=self.session();p=s.plan();source=self.a1.read_bytes();self.a1.write_bytes(source+b' ')
        self.error('stale_plan',s.apply,p,confirmed_ticket=p['ticket'])
        self.assertNotEqual(self.a1.read_bytes(),self.b1.read_bytes())
        self.error('ticket_unknown',s.apply,p,confirmed_ticket=p['ticket'])

    def test_root_pin_lock_marker_and_unsafe_paths(self):
        self.error('profile_copy_overlap',profile_copy.ProfileCopySession(self.a,self.a,system_pin=self.pin).plan)
        self.error('profile_copy_system_mismatch',profile_copy.ProfileCopySession(self.a,self.b,system_pin='0'*64).plan)
        fd=os.open(self.a.workspace,os.O_RDONLY|os.O_DIRECTORY)
        try:
            store.fcntl.flock(fd,store.fcntl.LOCK_EX|store.fcntl.LOCK_NB)
            self.error('profile_copy_busy',self.session().plan)
        finally:os.close(fd)
        marker=self.b.workspace/'.domain-agent-kit/.move-pending';marker.write_bytes(b'pending')
        self.error('move_pending',self.session().plan);marker.unlink()
        self.b1.unlink();self.b1.symlink_to(self.a1)
        self.error('unsafe_path',self.session().plan)
        self.assertTrue(self.b1.is_symlink())

    def test_conflict_with_target_project_refuses_before_writing(self):
        a=json.loads(self.a1.read_bytes())['registry']
        a['entries']=[audit.entry('C-1','contract','profile_owner',None,'docs',state='active'),
                      dict(audit.entry('R-1','rule','profile_owner','C-1','docs',state='active'),key='style.requirement',value='one')]
        audit.write(self.a1,a)
        b=json.loads(self.bp.read_bytes())
        b['entries']=[audit.entry('P-1','contract','project_owner',None,'docs',state='active'),
                      dict(audit.entry('R-2','rule','project_owner','P-1','docs',state='active'),key='style.requirement',value='two')]
        audit.write(self.bp,b)
        before=audit.tree_digest(self.root)
        self.error('profile_copy_conflict',self.session().plan)
        self.assertEqual(before,audit.tree_digest(self.root))

    def test_different_populated_target_is_never_overwritten(self):
        doc=json.loads(self.a1.read_bytes());doc['registry']['entries'][0]['title']='Different synthetic entry'
        # История изменённого документа некорректна; используем голый валидный target, чтобы
        # проверить отказ и для синтаксически допустимой независимой истории.
        audit.write(self.b1,doc['registry']);before=self.b1.read_bytes()
        self.error('profile_copy_target_not_pristine',self.session().plan)
        self.assertEqual(before,self.b1.read_bytes())

    def test_file_sync_failure_returns_unknown_and_preserves_stage(self):
        source=self.a1.read_bytes();before=self.b1.read_bytes();s=self.session();p=s.plan()
        with patch.object(profile_copy.os,'fsync',side_effect=OSError('synthetic fsync')):
            self.error('profile_copy_unknown',s.apply,p,confirmed_ticket=p['ticket'])
        self.assertEqual(source,self.a1.read_bytes());self.assertEqual(before,self.b1.read_bytes())
        stage=self.b1.parent/p['stage_name'];self.assertTrue(stage.exists())
        self.error('ticket_unknown',s.apply,p,confirmed_ticket=p['ticket'])
        self.error('profile_copy_pending',self.session().plan)

    def test_parent_fsync_failure_reports_unknown_even_after_replacement(self):
        source=self.a1.read_bytes();s=self.session();p=s.plan();real=os.fsync
        def fail_directory(fd):
            import stat
            if stat.S_ISDIR(os.fstat(fd).st_mode):raise OSError('synthetic parent fsync')
            return real(fd)
        with patch.object(profile_copy.os,'fsync',side_effect=fail_directory):
            self.error('profile_copy_unknown',s.apply,p,confirmed_ticket=p['ticket'])
        self.assertEqual(source,self.a1.read_bytes());self.assertEqual(source,self.b1.read_bytes())
        self.assertFalse((self.b1.parent/p['stage_name']).exists())
        self.error('ticket_unknown',s.apply,p,confirmed_ticket=p['ticket'])

    def test_cli_explicit_plan_apply_and_repeat(self):
        command=[sys.executable,'-I','-S','-B',str(ROOT/'kit/profile_copy.py'),
                 '--source-workspace',str(self.a.workspace),'--target-workspace',str(self.b.workspace),
                 '--profile-root','profiles/pilot','--system-pin',self.pin]
        p=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8')
        self.addCleanup(lambda: p.poll() is None and p.kill())
        def send(obj):
            p.stdin.write(json.dumps(obj,ensure_ascii=False)+'\n');p.stdin.flush();return json.loads(p.stdout.readline())
        try:
            plan=send({'type':'plan'});self.assertEqual(plan['outcome'],'planned')
            bad=send({'type':'apply','plan':plan,'confirmed_ticket':'wrong'});self.assertEqual(bad['diagnostic']['code'],'confirmation_required')
            ok=send({'type':'apply','plan':plan,'confirmed_ticket':plan['ticket']});self.assertEqual(ok['outcome'],'profile_copied')
            self.assertEqual(send({'type':'plan'})['outcome'],'no_change');p.stdin.close();self.assertEqual(p.wait(timeout=15),0)
        finally:
            if not p.stdin.closed:p.stdin.close()
            p.stdout.close();p.stderr.close()

if __name__=='__main__':unittest.main()
