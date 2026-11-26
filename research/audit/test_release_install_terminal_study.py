#!/usr/bin/env python3
"""Только синтетическая временная установка в PTY, не независимая приёмка."""
import importlib.util
import os
from pathlib import Path
import pty
import subprocess
import sys
import termios
import unittest
from io import StringIO
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'research/audit')]
import test_release_archive_publish_cli_study as fixture
import test_terminal_session as helpers
import test_atomic_init as atomic
import test_source_release_trust as signing

spec=importlib.util.spec_from_file_location('install_terminal',ROOT/'research/audit/release_install_terminal_study.py')
terminal=importlib.util.module_from_spec(spec);spec.loader.exec_module(terminal)


@unittest.skipUnless(os.name=='posix' and hasattr(os,'openpty') and signing.SUPPORTED and atomic.SUPPORTED,
                     'PTY/OpenSSL/Linux unavailable; not_run')
class InstallTerminalTests(unittest.TestCase):
    until=helpers.TerminalTests.until
    send=helpers.TerminalTests.send
    def setUp(self):
        self.fx=fixture.PublishCliTests();self.fx.setUp();self.addCleanup(self.fx.doCleanups)
        self.procs=[];self.addCleanup(self.cleanup)
        self.cmd=self.fx.args();self.cmd[4]=str(ROOT/'research/audit/release_install_terminal_study.py')
        self.cmd+=['--profile-root','profiles/pilot']
    def cleanup(self):
        for proc,master in self.procs:
            if proc.poll() is None:proc.kill()
            proc.wait(timeout=15);os.close(master)
    def start(self):
        master,slave=pty.openpty();attrs=termios.tcgetattr(slave);attrs[3]&=~termios.ECHO
        termios.tcsetattr(slave,termios.TCSANOW,attrs)
        try:proc=subprocess.Popen(self.cmd,stdin=slave,stdout=slave,stderr=slave,close_fds=True)
        finally:os.close(slave)
        self.procs.append((proc,master));return proc,master
    def test_cancel_then_confirm_full_plan(self):
        proc,fd=self.start();out=self.until(fd,'иной ответ отменяет: ')
        self.assertIn('"policy_sha256"',out);self.assertIn('"stage_name"',out)
        self.assertIn('snapshot/kit/SYSTEM-L0.json',out);self.assertIn('workspace/profiles/pilot/registry.json',out)
        self.assertFalse(self.fx.dest.exists());self.send(fd,'нет')
        self.until(fd,'"outcome": "cancelled"');self.assertEqual(proc.wait(timeout=20),0)
        self.assertFalse(self.fx.dest.exists())
        proc,fd=self.start();self.until(fd,'иной ответ отменяет: ');self.send(fd,'ПОДТВЕРЖДАЮ')
        out=self.until(fd,'Контейнер создан в исследовательской пробе')
        self.assertIn('study_container_published_unverified_origin',out)
        self.assertEqual(proc.wait(timeout=20),0)
        self.assertTrue((self.fx.dest/'snapshot/kit/KIT-VERSION.json').is_file())
        self.assertTrue((self.fx.dest/'workspace/profiles/pilot/registry.json').is_file())
    def test_non_tty_refuses(self):
        p=subprocess.run(self.cmd,input='',capture_output=True,text=True,timeout=20)
        self.assertEqual(p.returncode,2);self.assertIn('терминал',p.stderr);self.assertFalse(self.fx.dest.exists())
    def test_lost_response_after_apply_is_unknown(self):
        calls=[]
        class BrokenBackend:
            def __init__(self,args):pass
            def request(self,obj):
                calls.append(obj['type'])
                if obj['type']=='plan':return {'outcome':'planned','ticket':'a'*64}
                raise terminal.ui.TerminalError('backend_response_unavailable')
            def close(self):pass
        stderr=StringIO()
        with patch.object(sys,'argv',self.cmd[4:]),patch.object(sys.stdin,'isatty',return_value=True), \
             patch.object(sys.stdout,'isatty',return_value=True),patch.object(sys,'stderr',stderr), \
             patch.object(terminal,'Backend',BrokenBackend),patch.object(terminal.ui,'display'), \
             patch.object(terminal.ui,'ask',return_value='ПОДТВЕРЖДАЮ'):
            self.assertEqual(terminal.main(),1)
        self.assertEqual(calls,['plan','apply']);self.assertIn('Исход отправленной публикации неизвестен',stderr.getvalue())
        self.assertFalse(self.fx.dest.exists())

if __name__=='__main__':unittest.main()
