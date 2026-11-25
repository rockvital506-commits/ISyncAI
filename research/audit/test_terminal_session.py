#!/usr/bin/env python3
"""PTY-интеграция только на временном синтетическом workspace."""
import importlib.util
import json
import os
import pty
import select
import subprocess
import sys
import termios
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'research/audit')]
import core_audit as audit
import test_snapshot_session as fixtures

spec = importlib.util.spec_from_file_location('terminal_test', ROOT/'kit/terminal_session.py')
terminal = importlib.util.module_from_spec(spec); spec.loader.exec_module(terminal)


@unittest.skipUnless(os.name == 'posix' and hasattr(os, 'openpty'), 'PTY unavailable; not_run')
class TerminalTests(unittest.TestCase):
    def setUp(self):
        self.ctx = fixtures.SnapshotTests(); self.ctx.setUp(); self.addCleanup(self.ctx.doCleanups)
        self.procs = []; self.addCleanup(self.cleanup)

    def cleanup(self):
        for proc, master in self.procs:
            if proc.poll() is None: proc.kill()
            proc.wait(timeout=15)
            os.close(master)

    def command(self):
        return [sys.executable, '-I', '-S', '-B', str(ROOT/'kit/terminal_session.py'),
                '--candidate-root', str(self.ctx.candidate), '--workspace', str(self.ctx.workspace),
                '--profile-root', 'profiles/pilot', '--profile-id', 'Pilot',
                '--manifest-pin', self.ctx.manifest_pin, '--system-pin', self.ctx.system_pin]

    def start(self):
        master, slave = pty.openpty()
        attrs = termios.tcgetattr(slave); attrs[3] &= ~termios.ECHO; termios.tcsetattr(slave, termios.TCSANOW, attrs)
        try:
            proc = subprocess.Popen(self.command(), stdin=slave, stdout=slave, stderr=slave, close_fds=True)
        finally:
            os.close(slave)
        self.procs.append((proc, master)); self.until(master, 'Запрос> ')
        return proc, master

    def until(self, fd, token):
        data = bytearray(); deadline = time.monotonic()+25; target = token.encode('utf-8')
        while target not in data:
            ready, _, _ = select.select([fd], [], [], max(0, deadline-time.monotonic()))
            self.assertTrue(ready, 'истекло время ожидания: '+repr(bytes(data[-1000:])))
            try: chunk = os.read(fd, 65536)
            except OSError: chunk = b''
            self.assertTrue(chunk, 'терминал завершился: '+repr(bytes(data[-1000:])))
            data.extend(chunk)
            self.assertLess(len(data), 20*1024*1024)
        return data.decode('utf-8')

    def send(self, fd, text):
        os.write(fd, (text+'\n').encode('utf-8'))

    def test_plan_cancel_then_confirm_and_no_replay(self):
        proc, fd = self.start(); before = audit.tree_digest(self.ctx.workspace)
        phrase = self.ctx.request()['request']
        self.send(fd, phrase); shown = self.until(fd, 'иной ответ отменяет: ')
        self.assertIn('"replacement_notice"', shown); self.assertIn('"unified"', shown)
        self.assertEqual(before, audit.tree_digest(self.ctx.workspace))
        self.send(fd, 'нет'); self.until(fd, 'Запрос> ')
        self.assertEqual(before, audit.tree_digest(self.ctx.workspace))
        self.send(fd, phrase); self.until(fd, 'иной ответ отменяет: ')
        self.send(fd, 'ПОДТВЕРЖДАЮ'); out = self.until(fd, 'Запрос> ')
        self.assertIn('"outcome": "applied"', out)
        registry = json.loads(self.ctx.profile.read_bytes())['registry']['entries']
        self.assertEqual(len([e for e in registry if e['id']=='C-9']), 1)
        self.send(fd, '/выход'); self.assertEqual(proc.wait(timeout=15), 0)

    def test_delete_requires_second_confirmation(self):
        path = self.ctx.profile; doc = json.loads(path.read_bytes())
        doc['entries'].append(audit.entry('Q-1','rule','profile_owner','C-1','docs',state='revoked'))
        audit.write(path, doc)
        proc, fd = self.start(); before = audit.tree_digest(self.ctx.workspace)
        phrase = 'Удали правило Q-1 в профиле Pilot.'
        self.send(fd, phrase); self.until(fd, 'иной ответ отменяет: ')
        self.send(fd, 'ПОДТВЕРЖДАЮ'); self.until(fd, 'иной ответ отменяет: ')
        self.send(fd, 'нет'); self.until(fd, 'Запрос> ')
        self.assertEqual(before, audit.tree_digest(self.ctx.workspace))
        self.send(fd, phrase); self.until(fd, 'иной ответ отменяет: ')
        self.send(fd, 'ПОДТВЕРЖДАЮ'); self.until(fd, 'иной ответ отменяет: ')
        self.send(fd, 'УДАЛИТЬ'); output = self.until(fd, 'Запрос> ')
        self.assertIn('"outcome": "applied"', output)
        doc = json.loads(path.read_bytes()); self.assertNotIn('Q-1', {e['id'] for e in doc['registry']['entries']})
        self.send(fd, '/выход'); self.assertEqual(proc.wait(timeout=15), 0)

    def test_eof_at_confirmation_does_not_apply(self):
        proc, fd = self.start(); before = audit.tree_digest(self.ctx.workspace)
        self.send(fd, self.ctx.request()['request']); self.until(fd, 'иной ответ отменяет: ')
        os.write(fd, b'\x04')
        self.assertEqual(proc.wait(timeout=15), 0)
        self.assertEqual(before, audit.tree_digest(self.ctx.workspace))

    def use_candidate_system(self):
        import hashlib
        raw = (ROOT/'kit/SYSTEM-L0.json').read_bytes()
        self.ctx.l0.write_bytes(raw)
        self.ctx.system_pin = hashlib.sha256(raw).hexdigest()

    def test_context_modes_explicit_choices_and_cancel(self):
        self.use_candidate_system()
        proc, fd = self.start(); before = audit.tree_digest(self.ctx.workspace)
        for mode, present, absent in (('project','SYS-PROJECT-MODE','SYS-KIT-MODE'),
                                      ('kit','SYS-KIT-MODE','SYS-PROJECT-MODE')):
            self.send(fd, '/контекст '+mode+' docs/a')
            self.until(fd, 'иной ответ отменяет обзор: ')
            self.send(fd, 'включить'); self.until(fd, 'иной ответ отменяет обзор: ')
            self.send(fd, 'исключить'); output = self.until(fd, 'Запрос> ')
            self.assertIn('"outcome": "review_required"', output)
            self.assertIn(present, output); self.assertNotIn(absent, output)
            self.assertIn('"delivery": "not_implemented"', output)
        self.send(fd, '/контекст project docs/a')
        self.until(fd, 'иной ответ отменяет обзор: ')
        self.send(fd, 'отмена'); output = self.until(fd, 'Запрос> ')
        self.assertIn('context_cancelled', output)
        self.assertEqual(before, audit.tree_digest(self.ctx.workspace))
        self.send(fd, '/выход'); self.assertEqual(proc.wait(timeout=15),0)

    def test_context_detects_drift_before_display(self):
        self.use_candidate_system()
        proc, fd = self.start()
        self.send(fd, '/контекст project docs/a')
        self.until(fd, 'иной ответ отменяет обзор: ')
        doc = json.loads(self.ctx.profile.read_bytes())
        doc['entries'][0]['text'] = 'Синтетическое изменение после показа'
        audit.write(self.ctx.profile, doc)
        changed = audit.tree_digest(self.ctx.workspace)
        self.send(fd, 'включить'); self.until(fd, 'иной ответ отменяет обзор: ')
        self.send(fd, 'включить'); output = self.until(fd, 'Запрос> ')
        self.assertIn('context_inputs_changed', output)
        self.assertNotIn('"outcome": "review_required"', output)
        self.assertEqual(changed, audit.tree_digest(self.ctx.workspace))
        self.send(fd, '/выход'); self.assertEqual(proc.wait(timeout=15),0)

    def test_context_cannot_exclude_mandatory_constraint(self):
        self.use_candidate_system()
        doc = json.loads(self.ctx.profile.read_bytes())
        doc['entries'].append(audit.entry('X-1','constraint','profile_owner','C-1','docs',state='active'))
        audit.write(self.ctx.profile, doc)
        proc, fd = self.start(); before = audit.tree_digest(self.ctx.workspace)
        self.send(fd, '/контекст project docs/a')
        for _ in range(3):
            prompt = self.until(fd, 'иной ответ отменяет обзор: ')
            current_row = prompt.rsplit('\r\n{', 1)[-1]
            decision = 'исключить' if '"id": "X-1"' in current_row else 'включить'
            self.send(fd, decision)
        result = self.until(fd, 'Запрос> ')
        self.assertIn('context_mandatory_excluded', result)
        self.assertEqual(before, audit.tree_digest(self.ctx.workspace))
        self.send(fd, '/выход'); self.assertEqual(proc.wait(timeout=15),0)

    def test_context_export_both_modes_with_separate_confirmation(self):
        self.use_candidate_system()
        proc, fd = self.start(); before = audit.tree_digest(self.ctx.workspace)
        for mode in ('project','kit'):
            destination = self.ctx.root/('export '+mode+'.json')
            self.send(fd, '/экспорт '+mode+' docs/a')
            self.until(fd, 'иной ответ отменяет обзор: '); self.send(fd, 'включить')
            self.until(fd, 'иной ответ отменяет обзор: '); self.send(fd, 'исключить')
            output = self.until(fd, 'пустая строка отменяет): ')
            self.assertIn('"outcome": "review_required"', output)
            self.send(fd, str(destination)); plan = self.until(fd, 'иной ответ отменяет: ')
            self.assertIn('"content_utf8"', plan); self.assertIn('"failure": "leave_partial_or_unverified"', plan)
            self.assertFalse(destination.exists())
            self.send(fd, 'ПОДТВЕРЖДАЮ'); output = self.until(fd, 'Запрос> ')
            self.assertIn('"outcome": "context_file_created"', output)
            result = json.loads(destination.read_bytes()); self.assertEqual(result['context']['mode'], mode)
            self.assertEqual(result['agent_delivery'], 'not_checked')
            self.assertNotIn('P-1', {r['entry']['id'] for r in result['context']['entries']})
            self.assertEqual(before, audit.tree_digest(self.ctx.workspace))
        self.send(fd, '/выход'); self.assertEqual(proc.wait(timeout=15),0)

    def test_context_export_cancel_occupied_and_input_drift(self):
        self.use_candidate_system()
        proc, fd = self.start(); before = audit.tree_digest(self.ctx.workspace)
        dest = self.ctx.root/'out.json'
        def review():
            self.send(fd, '/экспорт project docs/a')
            self.until(fd, 'иной ответ отменяет обзор: '); self.send(fd, 'включить')
            self.until(fd, 'иной ответ отменяет обзор: '); self.send(fd, 'включить')
            self.until(fd, 'пустая строка отменяет): ')
        review(); self.send(fd, str(dest)); self.until(fd, 'иной ответ отменяет: ')
        self.assertFalse(dest.exists()); self.send(fd, 'нет')
        self.until(fd, 'Запрос> '); self.assertFalse(dest.exists())
        dest.write_bytes(b'unchanged')
        review(); self.send(fd, str(dest)); out = self.until(fd, 'Запрос> ')
        self.assertIn('context_export_destination_occupied', out); self.assertEqual(dest.read_bytes(), b'unchanged')
        for protected in (self.ctx.workspace/'protected.json', self.ctx.candidate/'protected.json'):
            review(); self.send(fd, str(protected)); out = self.until(fd, 'Запрос> ')
            self.assertIn('context_export_destination_invalid', out); self.assertFalse(protected.exists())
        review()
        doc = json.loads(self.ctx.profile.read_bytes()); doc['entries'][0]['text'] = 'drift after review'
        audit.write(self.ctx.profile, doc); changed = audit.tree_digest(self.ctx.workspace)
        other = self.ctx.root/'drift.json'; self.send(fd, str(other)); out = self.until(fd, 'Запрос> ')
        self.assertIn('context_inputs_changed', out); self.assertFalse(other.exists())
        self.assertNotEqual(before,changed); self.assertEqual(changed,audit.tree_digest(self.ctx.workspace))
        self.send(fd, '/выход'); self.assertEqual(proc.wait(timeout=15),0)

    def test_export_input_change_after_plan_never_creates_file(self):
        self.use_candidate_system()
        proc, fd = self.start(); destination = self.ctx.root/'stale.json'
        self.send(fd, '/экспорт project docs/a')
        self.until(fd, 'иной ответ отменяет обзор: '); self.send(fd, 'включить')
        self.until(fd, 'иной ответ отменяет обзор: '); self.send(fd, 'включить')
        self.until(fd, 'пустая строка отменяет): '); self.send(fd, str(destination))
        self.until(fd, 'иной ответ отменяет: ')
        doc = json.loads(self.ctx.profile.read_bytes()); doc['entries'][0]['text'] = 'drift after plan'
        audit.write(self.ctx.profile, doc); changed = audit.tree_digest(self.ctx.workspace)
        self.send(fd, 'ПОДТВЕРЖДАЮ'); result = self.until(fd, 'Запрос> ')
        self.assertIn('"outcome": "error"', result)
        self.assertFalse(destination.exists()); self.assertEqual(changed, audit.tree_digest(self.ctx.workspace))
        self.send(fd, '/выход'); self.assertEqual(proc.wait(timeout=15),0)

    def test_export_eof_before_confirmation_never_creates_file(self):
        self.use_candidate_system()
        proc, fd = self.start(); before = audit.tree_digest(self.ctx.workspace)
        destination = self.ctx.root/'eof.json'
        self.send(fd, '/экспорт kit docs/a')
        self.until(fd, 'иной ответ отменяет обзор: '); self.send(fd, 'включить')
        self.until(fd, 'иной ответ отменяет обзор: '); self.send(fd, 'включить')
        self.until(fd, 'пустая строка отменяет): '); self.send(fd, str(destination))
        self.until(fd, 'иной ответ отменяет: '); os.write(fd, b'\x04')
        self.assertEqual(proc.wait(timeout=15), 0)
        self.assertFalse(destination.exists()); self.assertEqual(before, audit.tree_digest(self.ctx.workspace))

    def test_export_failure_after_send_is_unknown_and_not_retried(self):
        from io import StringIO
        from unittest.mock import patch
        calls = []; inputs = {'L0':'a','L1':'b','L2':'c'}
        class BrokenBackend:
            def __init__(self, args): pass
            def request(self, request):
                calls.append(request['type'])
                if request['type'] == 'bootstrap': return {'outcome':'bootstrap'}
                if request['type'] == 'context_export_plan':
                    return {'outcome':'planned','ticket':'t','inputs_sha256':inputs}
                raise terminal.TerminalError('backend_response_unavailable')
            def close(self): pass
        stderr = StringIO()
        with patch.object(sys, 'argv', self.command()[4:]), \
             patch.object(sys.stdin, 'isatty', return_value=True), \
             patch.object(sys.stdout, 'isatty', return_value=True), \
             patch.object(sys, 'stderr', stderr), \
             patch.object(terminal, 'Backend', BrokenBackend), \
             patch.object(terminal, 'context_review', return_value=({'include':[],'exclude':[]},inputs)), \
             patch.object(terminal, 'ask', side_effect=['/экспорт project docs/a','/tmp/file','ПОДТВЕРЖДАЮ']), \
             patch.object(terminal, 'display'):
            self.assertEqual(terminal.main(), 1)
        self.assertEqual(calls, ['bootstrap','context_export_plan','context_export_apply'])
        self.assertIn('Исход применения неизвестен', stderr.getvalue())

    def test_non_tty_and_nonisolated_are_refused(self):
        before = audit.tree_digest(self.ctx.workspace)
        result = subprocess.run(self.command(), input='', text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 2); self.assertIn('терминал', result.stderr)
        cmd = self.command(); cmd.remove('-I')
        result = subprocess.run(cmd, input='', text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 2); self.assertIn('-I -S -B', result.stderr)
        self.assertEqual(before, audit.tree_digest(self.ctx.workspace))

    def test_failure_after_apply_is_reported_unknown_and_not_retried(self):
        from io import StringIO
        from unittest.mock import patch
        calls = []
        class BrokenBackend:
            def __init__(self, args): pass
            def request(self, request):
                calls.append(request['type'])
                if request['type'] == 'bootstrap': return {'outcome':'bootstrap'}
                if request['type'] == 'plan':
                    return {'outcome':'planned','ticket':'t','card':{'operation':'create'}}
                raise terminal.TerminalError('backend_response_unavailable')
            def close(self): pass
        stderr = StringIO()
        with patch.object(sys, 'argv', self.command()[4:]), \
             patch.object(sys.stdin, 'isatty', return_value=True), \
             patch.object(sys.stdout, 'isatty', return_value=True), \
             patch.object(sys, 'stderr', stderr), \
             patch.object(terminal, 'Backend', BrokenBackend), \
             patch.object(terminal, 'ask', side_effect=['фраза','ПОДТВЕРЖДАЮ']), \
             patch.object(terminal, 'display'):
            self.assertEqual(terminal.main(), 1)
        self.assertEqual(calls, ['bootstrap','plan','apply'])
        self.assertIn('Исход применения неизвестен', stderr.getvalue())

    def test_terminal_escape_and_formatting_are_escaped(self):
        from io import StringIO
        from unittest.mock import patch
        out = StringIO()
        with patch.object(sys, 'stdout', out):
            terminal.display({'value':'a\x1b[31m\u202eопасно\u2066b'})
        self.assertNotIn('\x1b',out.getvalue()); self.assertNotIn('\u202e',out.getvalue())
        self.assertIn('\\u001b',out.getvalue()); self.assertIn('\\u202e',out.getvalue())
        self.assertIn('\\u2066',out.getvalue())

if __name__ == '__main__':
    unittest.main()
