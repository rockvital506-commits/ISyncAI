#!/usr/bin/env python3
"""Терминальная диагностика и ручные операции только во временном стенде."""
import hashlib
import importlib.util
import json
import os
import pty
import subprocess
import sys
import termios
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'research/audit')]
import core_audit as audit
import test_snapshot_session as fixtures
import test_terminal_session as helpers
from kit.base import move_intent, registry_store
from kit.move_reservation import ReservationSession

spec=importlib.util.spec_from_file_location('terminal_recovery_test',ROOT/'kit/terminal_recovery.py')
recovery=importlib.util.module_from_spec(spec);spec.loader.exec_module(recovery)


@unittest.skipUnless(os.name=='posix' and hasattr(os,'openpty'),'PTY unavailable; not_run')
class RecoveryTerminalTests(unittest.TestCase):
    until=helpers.TerminalTests.until
    send=helpers.TerminalTests.send

    def setUp(self):
        self.ctx=fixtures.SnapshotTests();self.ctx.setUp();self.addCleanup(self.ctx.doCleanups)
        doc=json.loads(self.ctx.profile.read_bytes())
        doc['entries'].append(audit.entry('SOURCE','rule','profile_owner','C-1','docs',state='active'))
        audit.write(self.ctx.profile,doc)
        self.project=self.ctx.workspace/'.domain-agent-kit/project/registry.json'
        inputs=registry_store._load(self.ctx.layout).raw
        candidate=audit.entry('TARGET','rule','project_owner','P-1','docs',state='draft')
        report,self.raw=move_intent.build(inputs,source='L1',target='L2',entry_id='SOURCE',
                                         candidate=candidate,portability_context=None)
        self.pin=report['intent_sha256'];self.assertEqual(hashlib.sha256(self.raw).hexdigest(),self.pin)
        self.external=self.ctx.root/'intent.json';self.external.write_bytes(self.raw);self.external.chmod(0o600)
        self.marker=self.ctx.workspace/'.domain-agent-kit/.move-pending'
        session=ReservationSession(layout=self.ctx.layout,intent_bytes=self.raw,intent_pin=self.pin)
        plan=session.plan(action='reserve');self.assertEqual(session.apply(plan,confirmed_ticket=plan['ticket'])['outcome'],'reserved_not_moved')
        self.procs=[];self.addCleanup(self.cleanup)

    def cleanup(self):
        for proc,master in self.procs:
            if proc.poll() is None:proc.kill()
            proc.wait(timeout=15);os.close(master)

    def command(self):
        return [sys.executable,'-I','-S','-B',str(ROOT/'kit/terminal_recovery.py'),
                '--candidate-root',str(self.ctx.candidate),'--workspace',str(self.ctx.workspace),
                '--profile-root','profiles/pilot','--manifest-pin',self.ctx.manifest_pin,'--system-pin',self.ctx.system_pin]

    def start(self,path=None,pin=None):
        master,slave=pty.openpty();attrs=termios.tcgetattr(slave);attrs[3]&=~termios.ECHO;termios.tcsetattr(slave,termios.TCSANOW,attrs)
        try:proc=subprocess.Popen(self.command(),stdin=slave,stdout=slave,stderr=slave,close_fds=True)
        finally:os.close(slave)
        self.procs.append((proc,master));self.until(master,'Абсолютный путь внешней доверенной копии intent: ')
        self.send(master,str(path or self.external));self.until(master,'Отдельно удостоверенный SHA-256 intent: ')
        self.send(master,self.pin if pin is None else pin)
        return proc,master

    def menu(self,fd):return self.until(fd,'cleanup_stage или /выход: ')
    def plan(self,fd,action):
        self.send(fd,action)
        output=self.until(fd,'иной ответ отменяет: ')
        self.assertIn('"action": "'+action+'"',output)
        return output

    def test_manual_execute_and_separate_finalize_after_inspection(self):
        proc,fd=self.start();before=audit.tree_digest(self.ctx.workspace)
        out=self.menu(fd);self.assertIn('"state": "before_both"',out)
        self.assertEqual(before,audit.tree_digest(self.ctx.workspace))
        self.plan(fd,'execute');self.assertTrue(self.marker.exists());self.send(fd,'ПОДТВЕРЖДАЮ')
        out=self.menu(fd);self.assertIn('"outcome": "registries_updated_marker_retained"',out)
        self.assertTrue(self.marker.exists())
        self.send(fd,'inspect');out=self.menu(fd);self.assertIn('"state": "after_both"',out)
        self.plan(fd,'finalize');self.assertTrue(self.marker.exists())
        self.send(fd,'ПРОВЕРЕНО');self.until(fd,'иной ответ отменяет: ')
        self.assertTrue(self.marker.exists());self.send(fd,'ПОДТВЕРЖДАЮ')
        out=self.menu(fd);self.assertIn('"outcome": "marker_removed_after_both"',out)
        self.send(fd,'/выход');self.assertEqual(proc.wait(timeout=20),0);self.assertFalse(self.marker.exists())
        l1=json.loads(self.ctx.profile.read_bytes())['registry'];l2=json.loads(self.project.read_bytes())['registry']
        self.assertNotIn('SOURCE',{e['id'] for e in l1['entries']});self.assertIn('TARGET',{e['id'] for e in l2['entries']})

    def test_cancel_reservation_requires_two_decisions(self):
        before=audit.tree_digest(self.ctx.workspace);proc,fd=self.start();self.menu(fd)
        self.plan(fd,'cancel_reservation');self.send(fd,'нет')
        self.assertEqual(proc.wait(timeout=20),0);self.assertTrue(self.marker.exists())
        self.assertEqual(before,audit.tree_digest(self.ctx.workspace))
        proc,fd=self.start();self.menu(fd);self.plan(fd,'cancel_reservation')
        self.send(fd,'ПРОВЕРЕНО');self.until(fd,'иной ответ отменяет: ');self.send(fd,'ПОДТВЕРЖДАЮ')
        out=self.menu(fd);self.assertIn('"outcome": "reservation_cancelled"',out)
        self.send(fd,'/выход');self.assertEqual(proc.wait(timeout=20),0);self.assertFalse(self.marker.exists())

    def test_partial_marker_is_not_auto_deleted_and_requires_independent_decision(self):
        self.marker.write_bytes(self.raw[:9]);partial=self.marker.read_bytes()
        proc,fd=self.start();out=self.menu(fd)
        self.assertIn('"outcome": "error"',out);self.assertEqual(partial,self.marker.read_bytes())
        self.plan(fd,'cancel_partial');self.assertEqual(partial,self.marker.read_bytes())
        self.send(fd,'ПРОВЕРЕНО');self.until(fd,'иной ответ отменяет: ');self.send(fd,'ПОДТВЕРЖДАЮ')
        out=self.menu(fd);self.assertIn('"outcome": "partial_marker_removed"',out)
        self.send(fd,'/выход');self.assertEqual(proc.wait(timeout=20),0);self.assertFalse(self.marker.exists())

    def test_selected_stage_requires_explicit_name_and_two_decisions(self):
        _,_,after=move_intent._verified(self.raw,self.pin)
        stage=self.ctx.profile.parent/('.move-stage-'+'a'*32)
        stage.write_bytes(after['L1'][:8]);stage.chmod(0o600)
        proc,fd=self.start();self.menu(fd)
        self.send(fd,'cleanup_stage');self.until(fd,'Область L1 или L2: ');self.send(fd,'L1')
        self.until(fd,'Точное имя стадии: ');self.send(fd,stage.name)
        out=self.until(fd,'иной ответ отменяет: ')
        self.assertIn('"stage_matches": "after_prefix"',out);self.assertTrue(stage.exists())
        self.send(fd,'ПРОВЕРЕНО');self.until(fd,'иной ответ отменяет: ')
        self.assertTrue(stage.exists());self.send(fd,'ПОДТВЕРЖДАЮ')
        out=self.menu(fd);self.assertIn('"outcome": "selected_stage_removed"',out)
        self.send(fd,'/выход');self.assertEqual(proc.wait(timeout=20),0)
        self.assertFalse(stage.exists());self.assertTrue(self.marker.exists())

    def test_unknown_apply_warns_and_does_not_retry(self):
        from io import StringIO
        from unittest.mock import patch
        calls=[]
        class FakeBackend:
            def __init__(self,args):pass
            def request(self,obj):
                calls.append(obj['type'])
                if obj['type']=='configure':return {'outcome':'configured'}
                if obj['type']=='inspect':return {'outcome':'observation_only','state':'before_both'}
                if obj['type']=='plan':return {'outcome':'planned','plan':{'ticket':'t'}}
                raise recovery.ui.TerminalError('backend_response_unavailable')
            def close(self):pass
        stderr=StringIO()
        with patch.object(sys,'argv',self.command()[4:]), \
             patch.object(sys.stdin,'isatty',return_value=True),patch.object(sys.stdout,'isatty',return_value=True), \
             patch.object(sys,'stderr',stderr),patch.object(recovery,'_read_external',return_value='{}'), \
             patch.object(recovery.move,'MoveBackend',FakeBackend),patch.object(recovery.ui,'display'), \
             patch.object(recovery.ui,'ask',side_effect=['/safe/intent','a'*64,'execute','ПОДТВЕРЖДАЮ']):
            self.assertEqual(recovery.main(),1)
        self.assertEqual(calls,['configure','inspect','plan','apply'])
        self.assertIn('Исход отправленного этапа неизвестен',stderr.getvalue())
        self.assertTrue(self.marker.exists())

    def test_bad_pin_symlink_and_hardlink_refused_without_mutation(self):
        before=audit.tree_digest(self.ctx.workspace)
        proc,fd=self.start(pin='0'*64);out=self.until(fd,'intent_pin_mismatch')
        self.assertIn('intent_pin_mismatch',out);self.assertEqual(proc.wait(timeout=20),1)
        link=self.ctx.root/'link';link.symlink_to(self.external)
        proc,fd=self.start(path=link);self.until(fd,'intent_unavailable');self.assertEqual(proc.wait(timeout=20),1)
        hard=self.ctx.root/'hard';os.link(self.external,hard)
        proc,fd=self.start();self.until(fd,'intent_unavailable');self.assertEqual(proc.wait(timeout=20),1)
        self.assertEqual(before,audit.tree_digest(self.ctx.workspace));self.assertTrue(self.marker.exists())

    def test_non_tty_and_eof_before_confirmation(self):
        before=audit.tree_digest(self.ctx.workspace)
        p=subprocess.run(self.command(),input='',capture_output=True,text=True,timeout=20)
        self.assertEqual(p.returncode,2);self.assertIn('терминал',p.stderr)
        proc,fd=self.start();self.menu(fd);self.plan(fd,'execute');os.write(fd,b'\x04')
        self.assertEqual(proc.wait(timeout=20),0);self.assertEqual(before,audit.tree_digest(self.ctx.workspace))
        self.assertTrue(self.marker.exists())

if __name__=='__main__':unittest.main()
