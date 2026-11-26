#!/usr/bin/env python3
"""PTY-путь только с синтетическим ключом/данными; не независимая приёмка."""
import hashlib
import json
import os
from pathlib import Path
import pty
import subprocess
import sys
import termios
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'research/audit')]
import test_release_install_terminal_study as install_fixture
import test_terminal_session as terminal_fixture
import test_atomic_init as atomic
import test_source_release_trust as signing


@unittest.skipUnless(os.name=='posix' and hasattr(os,'openpty') and signing.SUPPORTED and atomic.SUPPORTED,
                     'PTY/OpenSSL/Linux unavailable; not_run')
class InstallToSessionTests(unittest.TestCase):
    until=terminal_fixture.TerminalTests.until
    send=terminal_fixture.TerminalTests.send
    def setUp(self):
        self.fx=install_fixture.InstallTerminalTests();self.fx.setUp();self.addCleanup(self.fx.doCleanups)
        self.sessions=[];self.addCleanup(self.cleanup)
    def cleanup(self):
        for proc,fd in self.sessions:
            if proc.poll() is None:proc.kill()
            proc.wait(timeout=15);os.close(fd)
    def test_confirmed_install_cancel_and_confirm_first_operation(self):
        proc,fd=self.fx.start();shown=self.until(fd,'иной ответ отменяет: ')
        self.assertIn('"archive_sha256"',shown)
        self.assertFalse(self.fx.fx.dest.exists());self.send(fd,'ПОДТВЕРЖДАЮ')
        self.until(fd,'Контейнер создан в исследовательской пробе');self.assertEqual(proc.wait(timeout=20),0)
        container=self.fx.fx.dest;snapshot=container/'snapshot';workspace=container/'workspace'
        l0=workspace/'kit/base/registry.json';before=l0.read_bytes()
        cmd=[sys.executable,'-I','-S','-B',str(ROOT/'kit/terminal_session.py'),
             '--candidate-root',str(snapshot),'--workspace',str(workspace),'--profile-root','profiles/pilot',
             '--profile-id','Pilot','--manifest-pin',hashlib.sha256(self.fx.fx.f.manifest).hexdigest(),
             '--system-pin',hashlib.sha256(before).hexdigest()]
        master,slave=pty.openpty();attrs=termios.tcgetattr(slave);attrs[3]&=~termios.ECHO
        termios.tcsetattr(slave,termios.TCSANOW,attrs)
        try:proc2=subprocess.Popen(cmd,stdin=slave,stdout=slave,stderr=slave,close_fds=True)
        finally:os.close(slave)
        self.sessions.append((proc2,master));self.until(master,'Запрос> ')
        request='Создай черновик контракта C-9 в профиле Pilot, постоянное, область «docs», название «Пример», основание «Проба», критерий «Запись существует»: Согласуем порядок чтения.'
        profile=workspace/'profiles/pilot/registry.json';before_profile=profile.read_bytes()
        self.send(master,request);self.until(master,'иной ответ отменяет: ');self.send(master,'нет')
        self.until(master,'Запрос> ');self.assertEqual(profile.read_bytes(),before_profile)
        self.send(master,request);self.until(master,'иной ответ отменяет: ');self.send(master,'ПОДТВЕРЖДАЮ')
        shown=self.until(master,'Запрос> ');self.assertIn('"outcome": "applied"',shown)
        self.assertIn('C-9',{e['id'] for e in json.loads(profile.read_bytes())['registry']['entries']})
        self.assertEqual(l0.read_bytes(),before);self.send(master,'/выход');self.assertEqual(proc2.wait(timeout=20),0)

if __name__=='__main__':unittest.main()
