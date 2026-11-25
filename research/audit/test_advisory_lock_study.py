#!/usr/bin/env python3
"""Наблюдение flock между отдельными процессами; не код блокировки Kit."""
import errno
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import unittest

try:
    import fcntl
except ImportError:
    fcntl = None

SUPPORTED = os.name == 'posix' and fcntl is not None and hasattr(fcntl, 'flock')
UNSUPPORTED = {getattr(errno, n) for n in ('ENOTSUP', 'EOPNOTSUPP', 'ENOSYS') if hasattr(errno, n)}
BUSY = {errno.EACCES, errno.EAGAIN}
SCRIPT = str(Path(__file__).resolve())
OLD = b'synthetic-original\n'
NEW = b'synthetic-uncooperative\n'


def child(mode, path):
    path = Path(path)
    if mode == 'lock':
        with path.open('rb') as file:
            try:
                fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                if error.errno not in BUSY: raise
                print('busy', flush=True); return
            print('acquired', flush=True)
    elif mode == 'hold':
        with path.open('rb') as file:
            fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            print('acquired', flush=True)
            sys.stdin.readline()
    elif mode == 'write':
        path.write_bytes(NEW); print('written', flush=True)
    elif mode == 'replace':
        staged = path.parent/'stage'; staged.write_bytes(NEW)
        os.replace(staged, path); print('replaced', flush=True)
    else:
        raise ValueError('unsupported child mode')


@unittest.skipUnless(SUPPORTED, 'POSIX flock недоступен; not_run')
class AdvisoryLockStudy(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='isync-flock-study-')
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.target = self.root/'registry'; self.target.write_bytes(OLD)
        self.lock = self.root/'lock'; self.lock.write_bytes(b'')
        self.probe = self.root/'probe'; self.probe.write_bytes(b'')
        with self.probe.open('rb') as f:
            try: fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                if error.errno in UNSUPPORTED: self.skipTest('ФС не поддерживает flock; not_run')
                raise
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def command(self, mode, path):
        return [sys.executable, '-I', '-S', '-B', SCRIPT, '--child', mode, str(path)]

    def run_child(self, mode, path):
        result = subprocess.run(self.command(mode, path), capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def locked(self, path):
        file = path.open('rb'); self.addCleanup(file.close)
        fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return file

    def test_cooperating_process_busy_then_acquires_after_unlock(self):
        file = self.locked(self.lock)
        self.assertEqual(self.run_child('lock', self.lock), 'busy')
        self.assertEqual(self.target.read_bytes(), OLD)
        fcntl.flock(file.fileno(), fcntl.LOCK_UN)
        self.assertEqual(self.run_child('lock', self.lock), 'acquired')
        self.assertEqual(self.target.read_bytes(), OLD)

    def test_uncooperative_process_writes_locked_target(self):
        self.locked(self.target)
        self.assertEqual(self.run_child('lock', self.target), 'busy')
        self.assertEqual(self.run_child('write', self.target), 'written')
        self.assertEqual(self.target.read_bytes(), NEW)
        self.assertEqual(self.run_child('lock', self.target), 'busy')

    def test_uncooperative_process_replaces_locked_target(self):
        old = self.locked(self.target); old_id = os.fstat(old.fileno()).st_ino
        self.assertEqual(self.run_child('replace', self.target), 'replaced')
        self.assertEqual(old.read(), OLD); self.assertEqual(self.target.read_bytes(), NEW)
        self.assertNotEqual(old_id, self.target.stat().st_ino)
        self.assertEqual(self.run_child('lock', self.target), 'acquired')

    def test_separate_lock_does_not_stop_uncooperative_replace(self):
        self.locked(self.lock)
        self.assertEqual(self.run_child('replace', self.target), 'replaced')
        self.assertEqual(self.target.read_bytes(), NEW)
        self.assertEqual(self.run_child('lock', self.lock), 'busy')

    def test_separate_lock_does_not_stop_uncooperative_stage_write(self):
        staged = self.root/'prepared'; staged.write_bytes(OLD)
        self.locked(self.lock)
        self.assertEqual(self.run_child('write', staged), 'written')
        self.assertEqual(staged.read_bytes(), NEW)
        self.assertEqual(self.target.read_bytes(), OLD)
        self.assertEqual(self.run_child('lock', self.lock), 'busy')

    def test_replacing_lock_path_splits_cooperating_locks(self):
        old = self.locked(self.lock)
        moved = self.root/'old-lock'; self.lock.rename(moved)
        self.lock.write_bytes(b'')
        self.assertNotEqual(os.fstat(old.fileno()).st_ino, self.lock.stat().st_ino)
        self.assertEqual(self.run_child('lock', moved), 'busy')
        self.assertEqual(self.run_child('lock', self.lock), 'acquired')
        self.assertEqual(self.target.read_bytes(), OLD)

    def test_terminated_process_releases_lock(self):
        proc = subprocess.Popen(self.command('hold', self.lock), stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
        def cleanup():
            if proc.poll() is None: proc.kill()
            proc.communicate(timeout=10)
        self.addCleanup(cleanup)
        lines = queue.Queue()
        threading.Thread(target=lambda: lines.put(proc.stdout.readline()), daemon=True).start()
        try: first = lines.get(timeout=10)
        except queue.Empty: self.fail('child lock readiness timeout')
        self.assertEqual(first.strip(), 'acquired')
        self.assertEqual(self.run_child('lock', self.lock), 'busy')
        proc.kill(); proc.wait(timeout=10)
        self.assertEqual(self.run_child('lock', self.lock), 'acquired')
        self.assertEqual(self.target.read_bytes(), OLD)


if __name__ == '__main__':
    if len(sys.argv) == 4 and sys.argv[1] == '--child': child(sys.argv[2], sys.argv[3])
    else: unittest.main()
