#!/usr/bin/env python3
"""PTY-тест терминального переноса на временных синтетических реестрах."""
import importlib.util
import json
import os
import pty
import subprocess
import sys
import termios
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT),str(ROOT/'research/audit')]
import core_audit as audit
import test_snapshot_session as fixtures
import test_terminal_session as terminal_fixtures

spec = importlib.util.spec_from_file_location('terminal_move_test',ROOT/'kit/terminal_move.py')
move = importlib.util.module_from_spec(spec); spec.loader.exec_module(move)


@unittest.skipUnless(os.name=='posix' and hasattr(os,'openpty'),'PTY unavailable; not_run')
class MoveTerminalTests(unittest.TestCase):
    until = terminal_fixtures.TerminalTests.until
    send = terminal_fixtures.TerminalTests.send

    def setUp(self):
        self.ctx = fixtures.SnapshotTests(); self.ctx.setUp(); self.addCleanup(self.ctx.doCleanups)
        profile = json.loads(self.ctx.profile.read_bytes())
        profile['entries'].append(audit.entry('SOURCE','rule','profile_owner','C-1','docs',state='active'))
        audit.write(self.ctx.profile,profile)
        self.project = self.ctx.workspace/'.domain-agent-kit/project/registry.json'
        project = json.loads(self.project.read_bytes())
        project['entries'].append(audit.entry('SOURCE2','rule','project_owner','P-1','docs',state='active'))
        audit.write(self.project,project)
        self.marker = self.ctx.workspace/'.domain-agent-kit/.move-pending'
        self.procs = []; self.addCleanup(self.cleanup)

    def cleanup(self):
        for proc, master in self.procs:
            if proc.poll() is None: proc.kill()
            proc.wait(timeout=15); os.close(master)

    def command(self):
        return [sys.executable,'-I','-S','-B',str(ROOT/'kit/terminal_move.py'),
                '--candidate-root',str(self.ctx.candidate),'--workspace',str(self.ctx.workspace),
                '--profile-root','profiles/pilot','--manifest-pin',self.ctx.manifest_pin,'--system-pin',self.ctx.system_pin]

    def start(self,source='L1'):
        master,slave = pty.openpty()
        attrs=termios.tcgetattr(slave); attrs[3]&=~termios.ECHO; termios.tcsetattr(slave,termios.TCSANOW,attrs)
        try: proc=subprocess.Popen(self.command(),stdin=slave,stdout=slave,stderr=slave,close_fds=True)
        finally: os.close(slave)
        self.procs.append((proc,master)); self.until(master,'Источник L1 или L2: ')
        self.send(master,source); self.until(master,'ID исходной записи: ')
        self.send(master,'SOURCE' if source=='L1' else 'SOURCE2')
        self.until(master,'Полная целевая запись, один JSON-объект: ')
        candidate = audit.entry('TARGET','rule','project_owner' if source=='L1' else 'profile_owner',
                                'P-1' if source=='L1' else 'C-1','docs',state='draft')
        self.send(master,json.dumps(candidate,ensure_ascii=False))
        if source=='L2':
            self.until(master,'project_names/machine_names/project_paths: ')
            self.send(master,json.dumps({'project_names':[],'machine_names':[],'project_paths':[]}))
        out=self.until(master,'пустая строка отменяет): ')
        self.assertIn('"outcome": "intent_draft_only"',out)
        self.assertIn('"intent_sha256"',out)
        return proc,master

    def export(self,fd,destination):
        self.send(fd,str(destination)); output=self.until(fd,'иной ответ останавливает: ')
        self.assertIn('"action": "export"',output); self.assertFalse(destination.exists())
        self.send(fd,'ПОДТВЕРЖДАЮ'); out=self.until(fd,'иной ответ останавливает: ')
        self.assertIn('"outcome": "exported_unverified_origin"',out)
        self.assertTrue(destination.is_file())
        self.send(fd,'PIN СОХРАНЁН')

    def step(self,fd,action):
        out=self.until(fd,'иной ответ останавливает: ')
        self.assertIn('"action": "'+action+'"',out)
        self.send(fd,'ПОДТВЕРЖДАЮ')

    def test_complete_both_directions_remove_source(self):
        for source in ('L1','L2'):
            with self.subTest(source=source):
                proc,fd=self.start(source); dest=self.ctx.root/('intent '+source+'.json')
                self.export(fd,dest); self.step(fd,'reserve'); self.step(fd,'execute'); self.step(fd,'finalize')
                self.assertEqual(proc.wait(timeout=30),0)
                self.assertFalse(self.marker.exists())
                profile=json.loads(self.ctx.profile.read_bytes()); project=json.loads(self.project.read_bytes())
                profile=profile.get('registry',profile); project=project.get('registry',project)
                src=profile if source=='L1' else project; dst=project if source=='L1' else profile
                ident='SOURCE' if source=='L1' else 'SOURCE2'
                self.assertNotIn(ident,{e['id'] for e in src['entries']})
                self.assertIn('TARGET',{e['id'] for e in dst['entries']})
                # Вторая подзадача работает в другой цели, поэтому повтор id допустим.

    def test_refuse_before_reserve_keeps_registries_unchanged(self):
        before=audit.tree_digest(self.ctx.workspace); proc,fd=self.start()
        dest=self.ctx.root/'intent.json'; self.export(fd,dest)
        self.until(fd,'иной ответ останавливает: '); self.send(fd,'нет')
        self.assertEqual(proc.wait(timeout=20),1)
        self.assertFalse(self.marker.exists()); self.assertEqual(before,audit.tree_digest(self.ctx.workspace))

    def test_stop_after_reserve_keeps_marker_and_warns(self):
        proc,fd=self.start(); dest=self.ctx.root/'intent.json'; self.export(fd,dest)
        self.step(fd,'reserve'); out=self.until(fd,'иной ответ останавливает: ')
        self.assertIn('"action": "execute"',out); self.assertTrue(self.marker.exists())
        self.send(fd,'нет'); warning=self.until(fd,'отдельную диагностику восстановления.')
        self.assertIn('Marker может существовать',warning)
        self.assertEqual(proc.wait(timeout=20),1); self.assertTrue(self.marker.exists()); self.assertTrue(dest.exists())

    def test_stop_after_execute_leaves_marker_with_source_removed(self):
        proc,fd=self.start(); dest=self.ctx.root/'intent.json'; self.export(fd,dest)
        self.step(fd,'reserve'); self.step(fd,'execute')
        out=self.until(fd,'иной ответ останавливает: ')
        self.assertIn('"action": "finalize"',out); self.assertTrue(self.marker.exists())
        self.send(fd,'нет'); warning=self.until(fd,'отдельную диагностику восстановления.')
        self.assertIn('Marker может существовать',warning); self.assertEqual(proc.wait(timeout=20),1)
        profile=json.loads(self.ctx.profile.read_bytes())['registry']
        project=json.loads(self.project.read_bytes())['registry']
        self.assertNotIn('SOURCE',{e['id'] for e in profile['entries']})
        self.assertIn('TARGET',{e['id'] for e in project['entries']}); self.assertTrue(self.marker.exists())

    def test_unknown_reserve_outcome_never_retries_and_warns(self):
        from io import StringIO
        from unittest.mock import patch
        calls=[]
        class FakeBackend:
            def __init__(self,args):pass
            def request(self,obj):
                calls.append((obj['type'],obj.get('action')))
                if obj['type']=='build':return {'outcome':'intent_draft_only','intent_utf8':'{}','intent_sha256':'x'}
                if obj['type']=='configure':return {'outcome':'configured'}
                if obj['type']=='plan':return {'outcome':'planned','plan':{'ticket':'t','action':obj['action']}}
                if obj['type']=='apply' and obj['plan']['action']=='export':return {'outcome':'exported_unverified_origin'}
                raise move.ui.TerminalError('backend_response_unavailable')
            def close(self):pass
        stderr=StringIO()
        with patch.object(sys,'argv',self.command()[4:]), \
             patch.object(sys.stdin,'isatty',return_value=True), patch.object(sys.stdout,'isatty',return_value=True), \
             patch.object(sys,'stderr',stderr), patch.object(move,'MoveBackend',FakeBackend), \
             patch.object(move,'_external_destination',return_value=Path('/safe/intent')), \
             patch.object(move.ui,'display'), \
             patch.object(move.ui,'ask',side_effect=['L1','SOURCE','{}','/safe/intent','ПОДТВЕРЖДАЮ',
                                                    'PIN СОХРАНЁН','ПОДТВЕРЖДАЮ']):
            self.assertEqual(move.main(),1)
        self.assertEqual(calls,[('build',None),('configure',None),('plan','export'),('apply',None),
                                ('plan','reserve'),('apply',None)])
        self.assertIn('Исход отправленного этапа неизвестен',stderr.getvalue())
        self.assertIn('Marker может существовать',stderr.getvalue())

    def test_protected_and_occupied_destinations_refused(self):
        before=audit.tree_digest(self.ctx.workspace)
        for protected in (self.ctx.workspace/'not-created',self.ctx.candidate/'not-created'):
            proc,fd=self.start(); self.send(fd,str(protected)); out=self.until(fd,'intent_destination_invalid')
            self.assertIn('intent_destination_invalid',out); self.assertEqual(proc.wait(timeout=20),1)
            self.assertFalse(protected.exists()); self.assertEqual(before,audit.tree_digest(self.ctx.workspace))
        dest=self.ctx.root/'occupied'; dest.write_bytes(b'preserve')
        proc,fd=self.start(); self.send(fd,str(dest)); out=self.until(fd,'destination_occupied')
        self.assertIn('destination_occupied',out); self.assertEqual(proc.wait(timeout=20),1)
        self.assertEqual(dest.read_bytes(),b'preserve'); self.assertFalse(self.marker.exists())

    def test_non_tty_and_invalid_json_no_changes(self):
        before=audit.tree_digest(self.ctx.workspace)
        p=subprocess.run(self.command(),input='',text=True,capture_output=True,timeout=20)
        self.assertEqual(p.returncode,2); self.assertIn('терминал',p.stderr)
        master,slave=pty.openpty()
        attrs=termios.tcgetattr(slave);attrs[3]&=~termios.ECHO;termios.tcsetattr(slave,termios.TCSANOW,attrs)
        try: proc=subprocess.Popen(self.command(),stdin=slave,stdout=slave,stderr=slave,close_fds=True)
        finally:os.close(slave)
        self.procs.append((proc,master));self.until(master,'Источник L1 или L2: ');self.send(master,'L1')
        self.until(master,'ID исходной записи: ');self.send(master,'SOURCE')
        self.until(master,'Полная целевая запись, один JSON-объект: ');self.send(master,'{"id": 1, "id": 2}')
        out=self.until(master,'duplicate key');self.assertIn('duplicate key',out)
        self.assertEqual(proc.wait(timeout=20),1);self.assertEqual(before,audit.tree_digest(self.ctx.workspace))

if __name__=='__main__':unittest.main()
