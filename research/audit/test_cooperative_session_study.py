#!/usr/bin/env python3
"""Стендовая оболочка для двух кооперативных процессов; НЕ интерфейс Kit."""
import errno
import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

try:
    import fcntl
except ImportError:
    fcntl = None

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'research/audit')]
import core_audit as audit
from kit.base import registry_store as store, registry_journal
from kit.base.operation_card import compile_prompt
from kit.base.operation_plan import PlanSession
from kit.base.registry_policy import StoreError

SUPPORTED = os.name == 'posix' and fcntl is not None and hasattr(fcntl, 'flock') and hasattr(os, 'O_NOFOLLOW')
UNSUPPORTED = {getattr(errno, n) for n in ('ENOSYS', 'ENOTSUP', 'EOPNOTSUPP') if hasattr(errno, n)}
BUSY = {errno.EACCES, errno.EAGAIN}
SCRIPT = str(Path(__file__).resolve())


def emit(value): print(json.dumps(value, ensure_ascii=False), flush=True)


def worker(root):
    root = Path(root)
    session = PlanSession(store.Layout(root, 'profiles/pilot'), profile_id='Pilot')
    plan = None
    for line in sys.stdin:
        msg = json.loads(line)
        if msg['cmd'] == 'plan':
            plan = session.plan(compile_prompt(msg['request']))
            emit(plan)
        elif msg['cmd'] == 'bypass':
            # Прямой вход в кандидат не знает об исследовательской оболочке.
            try: emit(session.apply(plan, confirmed_ticket=msg.get('ticket')))
            except StoreError as error: emit({'outcome': 'error', 'code': error.code})
        elif msg['cmd'] == 'apply':
            # Никакого создания lock-файла; тест предполагает один стабильный объект.
            fd = os.open(root/'study.lock', os.O_RDONLY | os.O_NOFOLLOW)
            try:
                try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as error:
                    if error.errno not in BUSY: raise
                    emit({'outcome': 'study_busy'}); continue
                real_replace = store._replace
                def pause(path, raw, rel, *, expected_metadata):
                    emit({'outcome': 'study_paused_before_replace'})
                    if json.loads(sys.stdin.readline()) != {'cmd': 'resume'}:
                        raise RuntimeError('study_resume_invalid')
                    return real_replace(path, raw, rel, expected_metadata=expected_metadata)
                try:
                    if msg.get('pause'):
                        with patch.object(store, '_replace', side_effect=pause):
                            result = session.apply(plan, confirmed_ticket=msg.get('ticket'))
                    else:
                        result = session.apply(plan, confirmed_ticket=msg.get('ticket'))
                    response = result
                except StoreError as error:
                    response = {'outcome': 'error', 'code': error.code}
            finally:
                os.close(fd)
            # Ответ после освобождения lock: следующий запрос не гоняется с закрытием fd.
            emit(response)
        else:
            raise ValueError('invalid study command')


@unittest.skipUnless(SUPPORTED, 'POSIX flock/O_NOFOLLOW недоступен; not_run')
class CooperativeSessionStudy(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='isync-cooperative-study-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        audit.make_workspace(self.root, parent_scope='.')
        self.paths = {'L0': self.root/'kit/base/registry.json',
                      'L1': self.root/'profiles/pilot/registry.json',
                      'L2': self.root/'.domain-agent-kit/project/registry.json'}
        self.lock = self.root/'study.lock'; self.lock.write_bytes(b'')
        with self.lock.open('rb') as handle:
            try: fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                if error.errno in UNSUPPORTED: self.skipTest('ФС не поддерживает flock; not_run')
                raise
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        self.procs = []
        self.addCleanup(self.cleanup_procs)

    def cleanup_procs(self):
        for proc, _ in self.procs:
            if proc.poll() is None: proc.kill()
            proc.communicate(timeout=10)

    def process(self):
        proc = subprocess.Popen([sys.executable, '-I', '-S', '-B', SCRIPT, '--worker', str(self.root)],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, encoding='utf-8', bufsize=1)
        lines = queue.Queue()
        def reader():
            for line in proc.stdout: lines.put(line)
            lines.put(None)
        threading.Thread(target=reader, daemon=True).start()
        self.procs.append((proc, lines))
        return proc, lines

    def send(self, peer, msg):
        proc, _ = peer
        proc.stdin.write(json.dumps(msg, ensure_ascii=False)+'\n'); proc.stdin.flush()

    def receive(self, peer):
        proc, lines = peer
        try: line = lines.get(timeout=10)
        except queue.Empty: self.fail('worker response timeout')
        if line is None:
            proc.wait(timeout=10)
            self.fail('worker exited: ' + proc.stderr.read())
        return json.loads(line)

    def request(self, peer, msg):
        self.send(peer, msg); return self.receive(peer)

    def plan(self, peer, ident, target):
        where = 'в профиле Pilot' if target == 'L1' else 'в проекте'
        text = (f'Создай черновик контракта {ident} {where}, постоянное, '
                'область «docs», название «Пример», основание «Проба», '
                'критерий «Запись существует»: Синтетический текст.')
        result = self.request(peer, {'cmd': 'plan', 'request': text})
        self.assertEqual(result['outcome'], 'planned')
        return result

    def setup_peers(self, area_a, area_b):
        a, b = self.process(), self.process()
        before = {area: path.read_bytes() for area, path in self.paths.items()}
        pa, pb = self.plan(a, 'A-9', area_a), self.plan(b, 'B-9', area_b)
        self.assertEqual(pa['inputs_sha256'], pb['inputs_sha256'])
        self.assertEqual(before, {area: path.read_bytes() for area, path in self.paths.items()})
        self.send(a, {'cmd': 'apply', 'ticket': pa['ticket'], 'pause': True})
        self.assertEqual(self.receive(a)['outcome'], 'study_paused_before_replace')
        return a, b, pa, pb, before

    def resume(self, peer):
        self.send(peer, {'cmd': 'resume'})
        return self.receive(peer)

    def history(self, area):
        registry, journal = registry_journal.unpack_registry(json.loads(self.paths[area].read_bytes()), area=area)
        return registry, [d['entry_id'] for d in journal['decisions']]

    def case(self, area_a, area_b):
        a, b, pa, pb, before = self.setup_peers(area_a, area_b)
        attempt = {'cmd': 'apply', 'ticket': pb['ticket']}
        self.assertEqual(self.request(b, attempt)['outcome'], 'study_busy')
        self.assertEqual(before, {area: path.read_bytes() for area, path in self.paths.items()})
        self.assertEqual(self.resume(a)['outcome'], 'applied')
        after = {area: path.read_bytes() for area, path in self.paths.items()}
        self.assertEqual(hashlib.sha256(after[area_a]).hexdigest(), pa['diff']['after_sha256'])
        error = self.request(b, attempt)
        self.assertEqual(error, {'outcome': 'error', 'code': 'stale_revision' if area_a == area_b else 'stale_plan'})
        self.assertEqual(after, {area: path.read_bytes() for area, path in self.paths.items()})
        self.assertEqual(self.history(area_a)[1], ['A-9'])
        self.assertEqual(after['L0'], before['L0'])
        self.assertEqual(self.request(b, attempt)['code'], 'ticket_unknown')

    def test_cooperative_same_l1(self): self.case('L1', 'L1')
    def test_cooperative_same_l2(self): self.case('L2', 'L2')
    def test_cooperative_l1_l2(self): self.case('L1', 'L2')
    def test_cooperative_l2_l1(self): self.case('L2', 'L1')

    def test_confirmation_remains_required_and_no_ticket_consumed(self):
        a = self.process(); before = self.paths['L1'].read_bytes(); plan = self.plan(a, 'A-9', 'L1')
        self.assertEqual(self.request(a, {'cmd': 'apply', 'ticket': ''}),
                         {'outcome': 'error', 'code': 'confirmation_required'})
        self.assertEqual(self.paths['L1'].read_bytes(), before)
        self.assertEqual(self.request(a, {'cmd': 'apply', 'ticket': plan['ticket']})['outcome'], 'applied')
        self.assertEqual(self.history('L1')[1], ['A-9'])

    def test_bypassing_wrapper_allows_loss(self):
        a, b, pa, pb, _ = self.setup_peers('L1', 'L1')
        self.assertEqual(self.request(b, {'cmd': 'bypass', 'ticket': pb['ticket']})['outcome'], 'applied')
        self.assertEqual(self.history('L1')[1], ['B-9'])
        self.assertEqual(self.resume(a)['outcome'], 'applied')
        self.assertEqual(self.history('L1')[1], ['A-9'])
        self.assertEqual(hashlib.sha256(self.paths['L1'].read_bytes()).hexdigest(), pa['diff']['after_sha256'])

    def test_process_killed_before_temp_allows_second_to_apply(self):
        a, b, _, pb, before = self.setup_peers('L1', 'L1')
        attempt = {'cmd': 'apply', 'ticket': pb['ticket']}
        self.assertEqual(self.request(b, attempt)['outcome'], 'study_busy')
        a[0].kill(); a[0].wait(timeout=10)
        self.assertEqual(before, {area: path.read_bytes() for area, path in self.paths.items()})
        self.assertEqual(self.request(b, attempt)['outcome'], 'applied')
        self.assertEqual(hashlib.sha256(self.paths['L1'].read_bytes()).hexdigest(), pb['diff']['after_sha256'])
        self.assertEqual(self.history('L1')[1], ['B-9'])

    def test_replaced_lock_file_allows_loss_despite_cooperation(self):
        a, b, pa, pb, _ = self.setup_peers('L1', 'L1')
        old = self.root/'old-study.lock'; self.lock.rename(old); self.lock.write_bytes(b'')
        self.assertNotEqual(old.stat().st_ino, self.lock.stat().st_ino)
        self.assertEqual(self.request(b, {'cmd': 'apply', 'ticket': pb['ticket']})['outcome'], 'applied')
        self.assertEqual(self.history('L1')[1], ['B-9'])
        self.assertEqual(hashlib.sha256(self.paths['L1'].read_bytes()).hexdigest(), pb['diff']['after_sha256'])
        self.assertEqual(self.resume(a)['outcome'], 'applied')
        self.assertEqual(self.history('L1')[1], ['A-9'])
        self.assertEqual(hashlib.sha256(self.paths['L1'].read_bytes()).hexdigest(), pa['diff']['after_sha256'])


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--worker': worker(sys.argv[2])
    else: unittest.main()
