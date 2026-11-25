#!/usr/bin/env python3
"""Терминальная инициализация только на синтетической временной ФС."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pty
import subprocess
import sys
import tempfile
import termios
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'research/audit')]
import test_terminal_session as helpers
import test_atomic_init as atomic_tests
import core_audit as audit
from kit.atomic_init import AtomicInitializationSession
from kit.guard import guard
from kit.base.registry_store import Layout

spec=importlib.util.spec_from_file_location('terminal_init_test',ROOT/'kit/terminal_init.py')
terminal=importlib.util.module_from_spec(spec);spec.loader.exec_module(terminal)


@unittest.skipUnless(os.name=='posix' and hasattr(os,'openpty') and atomic_tests.SUPPORTED,'Linux/PTY unavailable; not_run')
class TerminalInitTests(unittest.TestCase):
    until=helpers.TerminalTests.until
    send=helpers.TerminalTests.send

    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='terminal-init-');self.addCleanup(temp.cleanup)
        self.root=Path(temp.name).resolve();self.dest=self.root/'new workspace'
        self.l0=self.root/'external-l0.json';self.l0.write_bytes((ROOT/'kit/SYSTEM-L0.json').read_bytes())
        self.pin=hashlib.sha256(self.l0.read_bytes()).hexdigest();self.procs=[];self.addCleanup(self.cleanup)

    def cleanup(self):
        for proc,master in self.procs:
            if proc.poll() is None:proc.kill()
            proc.wait(timeout=15);os.close(master)

    def command(self):return [sys.executable,'-I','-S','-B',str(ROOT/'kit/terminal_init.py')]

    def start(self,path=None,pin=None,*,inspect=False,staging=None):
        master,slave=pty.openpty();attrs=termios.tcgetattr(slave);attrs[3]&=~termios.ECHO;termios.tcsetattr(slave,termios.TCSANOW,attrs)
        command=self.command()+(['--inspect'] if inspect else [])
        try:proc=subprocess.Popen(command,stdin=slave,stdout=slave,stderr=slave,close_fds=True)
        finally:os.close(slave)
        self.procs.append((proc,master));self.until(master,'Абсолютный путь нового workspace: ')
        self.send(master,str(self.dest))
        if inspect:
            self.until(master,'Сохранённый из плана абсолютный путь staging: ')
            self.send(master,str(staging or self.root/('.domain-init-'+'a'*32)))
        self.until(master,'Относительный корень нового профиля: ')
        self.send(master,'profiles/pilot');self.until(master,'Абсолютный путь доверенного файла L0: ')
        self.send(master,str(path or self.l0));self.until(master,'Отдельно удостоверенный SHA-256 L0: ')
        self.send(master,self.pin if pin is None else pin);return proc,master

    def test_plan_cancel_then_confirm_create_and_guard(self):
        p,fd=self.start();out=self.until(fd,'иной ответ отменяет: ')
        self.assertIn('"content_utf8"',out);self.assertIn('"publication"',out)
        self.assertFalse(self.dest.exists());self.send(fd,'нет');self.assertEqual(p.wait(timeout=20),0)
        self.assertFalse(self.dest.exists());self.assertEqual(sorted(p.name for p in self.root.iterdir()),['external-l0.json'])
        p,fd=self.start();self.until(fd,'иной ответ отменяет: ');self.assertFalse(self.dest.exists())
        self.send(fd,'ПОДТВЕРЖДАЮ');out=self.until(fd,'применение агентом не подтверждены.')
        self.assertIn('"outcome": "published_unverified_origin"',out);self.assertEqual(p.wait(timeout=20),0)
        manifest_pin=hashlib.sha256((ROOT/'kit/KIT-VERSION.json').read_bytes()).hexdigest()
        self.assertEqual(guard(ROOT,Layout(self.dest,'profiles/pilot'),manifest_pin=manifest_pin,system_pin=self.pin)['outcome'],'pass')
        self.assertEqual((self.dest/'kit/base/registry.json').read_bytes(),self.l0.read_bytes())

    def test_bad_pin_and_symlink_or_hardlink_refused(self):
        p,fd=self.start(pin='0'*64);self.until(fd,'l0_pin_mismatch');self.assertEqual(p.wait(timeout=20),1)
        link=self.root/'link';link.symlink_to(self.l0)
        p,fd=self.start(path=link);self.until(fd,'l0_unavailable');self.assertEqual(p.wait(timeout=20),1)
        hard=self.root/'hard';os.link(self.l0,hard)
        p,fd=self.start();self.until(fd,'l0_unavailable');self.assertEqual(p.wait(timeout=20),1)
        self.assertFalse(self.dest.exists())

    def test_existing_destination_untouched_and_eof_cancels(self):
        self.dest.mkdir();sentinel=self.dest/'keep';sentinel.write_bytes(b'preserve')
        p,fd=self.start();self.until(fd,'destination_occupied');self.assertEqual(p.wait(timeout=20),1)
        self.assertEqual(sentinel.read_bytes(),b'preserve')
        sentinel.unlink();self.dest.rmdir()
        p,fd=self.start();self.until(fd,'иной ответ отменяет: ');os.write(fd,b'\x04')
        self.assertEqual(p.wait(timeout=20),0);self.assertFalse(self.dest.exists())

    def test_inspect_absent_partial_and_published_without_mutation(self):
        stage=self.root/('.domain-init-'+'a'*32)
        before=audit.tree_digest(self.root)
        p,fd=self.start(inspect=True,staging=stage);out=self.until(fd,'ничего не повторяйте и не удаляйте автоматически.')
        self.assertIn('"destination_state": "absent"',out);self.assertIn('"staging_state": "absent"',out)
        self.assertEqual(p.wait(timeout=20),0);self.assertEqual(before,audit.tree_digest(self.root))
        stage.mkdir(mode=0o700);(stage/'incomplete').write_bytes(b'keep')
        before=audit.tree_digest(self.root)
        p,fd=self.start(inspect=True,staging=stage);out=self.until(fd,'ничего не повторяйте и не удаляйте автоматически.')
        self.assertIn('"staging_state": "different"',out);self.assertEqual(p.wait(timeout=20),0)
        self.assertEqual(before,audit.tree_digest(self.root))
        session=AtomicInitializationSession(self.dest,profile_root='profiles/pilot',l0_bytes=self.l0.read_bytes(),system_pin=self.pin)
        plan=session.plan();session.apply(plan,confirmed_ticket=plan['ticket'])
        before=audit.tree_digest(self.root)
        p,fd=self.start(inspect=True,staging=stage);out=self.until(fd,'ничего не повторяйте и не удаляйте автоматически.')
        self.assertIn('"destination_state": "matches_observation"',out);self.assertIn('"staging_state": "different"',out)
        self.assertEqual(p.wait(timeout=20),0);self.assertEqual(before,audit.tree_digest(self.root))

    def test_inspect_invalid_staging_and_wrong_pin_do_not_write(self):
        before=audit.tree_digest(self.root)
        p,fd=self.start(inspect=True,staging=self.root/'bad-stage');out=self.until(fd,'inspection_paths_invalid')
        self.assertIn('inspection_paths_invalid',out);self.assertEqual(p.wait(timeout=20),1)
        p,fd=self.start(inspect=True,pin='0'*64);self.until(fd,'l0_pin_mismatch')
        self.assertEqual(p.wait(timeout=20),1);self.assertEqual(before,audit.tree_digest(self.root))

    def test_non_tty_and_apply_failure_unknown_without_retry(self):
        result=subprocess.run(self.command(),input='',capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,2);self.assertIn('терминал',result.stderr)
        from io import StringIO
        from unittest.mock import patch
        calls=[]
        class BrokenBackend:
            def __init__(self):pass
            def request(self,obj):
                calls.append(obj['type'])
                if obj['type']=='plan_atomic':return {'outcome':'planned','ticket':'t'}
                raise terminal.ui.TerminalError('backend_response_unavailable')
            def close(self):pass
        stderr=StringIO()
        with patch.object(sys,'argv',[str(ROOT/'kit/terminal_init.py')]), \
             patch.object(sys.stdin,'isatty',return_value=True),patch.object(sys.stdout,'isatty',return_value=True), \
             patch.object(sys,'stderr',stderr),patch.object(terminal,'_read_l0',return_value='{}'), \
             patch.object(terminal,'InitBackend',BrokenBackend),patch.object(terminal.ui,'display'), \
             patch.object(terminal.ui,'ask',side_effect=['/new','profiles/pilot','/safe','a'*64,'ПОДТВЕРЖДАЮ']):
            self.assertEqual(terminal.main(),1)
        self.assertEqual(calls,['plan_atomic','apply']);self.assertIn('Исход отправленной публикации неизвестен',stderr.getvalue())
        self.assertFalse(self.dest.exists())

if __name__=='__main__':unittest.main()
