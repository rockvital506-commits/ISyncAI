#!/usr/bin/env python3
"""Синтетическая поставка только по манифесту и отдельно доверенная пара; не установка."""
import hashlib
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'research/audit')]
import core_audit as audit

MANIFEST = 'kit/KIT-VERSION.json'
PAIR = ('snapshot_session.py', 'verify_candidate.py')


def sha(data):
    return hashlib.sha256(data).hexdigest()


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='domain-delivery-synthetic-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.source = self.root/'source'; self.source.mkdir()
        self.trusted = self.root/'trusted'/'kit'; self.trusted.mkdir(parents=True)
        self.workspace = self.root/'workspace'; self.workspace.mkdir()
        raw = (ROOT/MANIFEST).read_bytes()
        self.manifest_pin = sha(raw)  # Только испытательная согласованность, не происхождение.
        self.manifest = json.loads(raw)
        for rel, digest in self.manifest['files'].items():
            p = Path(rel)
            self.assertTrue(not p.is_absolute() and '..' not in p.parts and p.parts[0] == 'kit')
            data = (ROOT/p).read_bytes()
            self.assertEqual(sha(data), digest)
            target = self.source/p; target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        (self.source/MANIFEST).write_bytes(raw)
        # Имитируем доверенную доставку тех же файлов отдельно; реальный канал не проверяется.
        for name in PAIR:
            (self.trusted/name).write_bytes((ROOT/'kit'/name).read_bytes())
        audit.make_workspace(self.workspace, parent_scope='.')
        self.l0 = self.workspace/'kit/base/registry.json'
        doc = json.loads(self.l0.read_bytes()); doc['entries'] = []
        audit.write(self.l0, doc)  # Пустой L0 — лишь тест схемы, не содержимое Kit.
        self.system_pin = sha(self.l0.read_bytes())
        self.profile = self.workspace/'profiles/pilot/registry.json'
        self.marker = self.root/'unexpected-execution'
        self.procs = []
        self.addCleanup(self.stop_processes)

    def stop_processes(self):
        for process in self.procs:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=15)

    def args(self, manifest_pin=None, system_pin=None):
        return [sys.executable, '-I', '-S', '-B', str(self.trusted/'snapshot_session.py'),
                '--candidate-root', str(self.source), '--workspace', str(self.workspace),
                '--profile-root', 'profiles/pilot', '--profile-id', 'Pilot',
                '--manifest-pin', self.manifest_pin if manifest_pin is None else manifest_pin,
                '--system-pin', self.system_pin if system_pin is None else system_pin]

    def launch(self):
        env = dict(os.environ, PYTHONPATH=str(self.workspace), PYTHONDONTWRITEBYTECODE='1')
        p = subprocess.Popen(self.args(), cwd=self.workspace, env=env, stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', bufsize=1)
        self.procs.append(p)
        lines = queue.Queue()
        def reader():
            for line in p.stdout:
                lines.put(line)
            lines.put(None)
        threading.Thread(target=reader, daemon=True).start()
        return p, lines

    def send(self, p, lines, message):
        p.stdin.write(json.dumps(message, ensure_ascii=False)+'\n'); p.stdin.flush()
        try:
            line = lines.get(timeout=15)
        except queue.Empty:
            raise AssertionError('нет ответа из автономной сессии') from None
        if line is None:
            raise AssertionError('автономная сессия завершилась без ответа')
        return json.loads(line)

    def refusal(self, args=None, reason=None):
        before = audit.tree_digest(self.workspace)
        result = subprocess.run(args or self.args(), cwd=self.workspace, input='', capture_output=True,
                                text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stdout, '')
        if reason is not None:
            self.assertEqual(json.loads(result.stderr)['reason'], reason)
        self.assertEqual(before, audit.tree_digest(self.workspace))
        self.assertFalse(self.marker.exists())

    def test_manifest_only_standalone_session(self):
        listed = {p.relative_to(self.source).as_posix() for p in self.source.rglob('*') if p.is_file()}
        self.assertEqual(listed, set(self.manifest['files']) | {MANIFEST})
        self.assertEqual({p.name for p in self.trusted.iterdir()}, set(PAIR))
        self.assertFalse((self.source/'research').exists())
        self.assertFalse((self.source/'kit/examples').exists())
        self.assertFalse((self.source/'kit/base/registry.json').exists())
        source_before = audit.tree_digest(self.source); trusted_before = audit.tree_digest(self.trusted)
        before = audit.tree_digest(self.workspace)
        p, lines = self.launch()
        start = self.send(p, lines, {'type':'bootstrap'})
        self.assertEqual(start['outcome'], 'bootstrap')
        self.assertEqual(start['manifest_sha256'], self.manifest_pin)
        request = ('Создай черновик контракта C-9 в профиле Pilot, постоянное, '
                   'область «docs», название «Пример», основание «Проба», '
                   'критерий «Запись существует»: Согласуем порядок чтения.')
        plan = self.send(p, lines, {'type':'plan', 'request':request})
        self.assertEqual(plan['outcome'], 'planned')
        self.assertEqual(before, audit.tree_digest(self.workspace))
        denied = self.send(p, lines, {'type':'apply', 'plan':plan, 'confirmed_ticket':''})
        self.assertEqual(denied['diagnostic']['code'], 'confirmation_required')
        self.assertEqual(before, audit.tree_digest(self.workspace))
        applied = self.send(p, lines, {'type':'apply', 'plan':plan, 'confirmed_ticket':plan['ticket']})
        self.assertEqual(applied['outcome'], 'applied')
        after = audit.tree_digest(self.workspace)
        self.assertEqual({x for x in before if before[x] != after[x]}, {'profiles/pilot/registry.json'})
        self.assertEqual(set(after), set(before))
        self.assertEqual(audit.tree_digest(self.source), source_before)
        self.assertEqual(audit.tree_digest(self.trusted), trusted_before)
        self.assertEqual(json.loads(self.profile.read_bytes())['registry']['entries'][-1]['id'], 'C-9')
        l0 = json.loads(self.l0.read_bytes())
        self.assertEqual(l0['entries'], [])
        # Pin фиксирует байты, но guard пока не связывает версию реестра с версией кандидата.
        self.assertNotEqual(l0['release_version'], self.manifest['version'])

    def test_refusal_bad_pin_and_altered_candidates(self):
        self.refusal(self.args(manifest_pin='0'*64), 'candidate_unverified')
        self.refusal(self.args(system_pin='0'*64), 'runtime_unverified')
        source = self.source/'kit/base/operation_plan.py'; original = source.read_bytes()
        source.write_bytes(original + b'\n# synthetic tamper\n')
        self.refusal(reason='candidate_unverified')
        source.write_bytes(original)
        extra = self.source/'kit/base/unlisted.py'; extra.write_text('not executed', encoding='utf-8')
        self.refusal(reason='candidate_unverified')

    def test_missing_workspace_is_not_initialized(self):
        # Удаляется только синтетический реестр в новом временном каталоге.
        self.l0.unlink()
        self.refusal(reason='runtime_unverified')
        self.assertFalse(self.l0.exists())

    def test_extra_top_level_is_not_verified_or_imported(self):
        extra = self.source/'kit/unlisted.py'
        extra.write_text('from pathlib import Path\nPath('+repr(str(self.marker))+').touch()\n', encoding='utf-8')
        # Проверяем отдельно известную границу verify_candidate: лишний kit/* вне списка игнорируется.
        check = subprocess.run([sys.executable, '-I', '-S', '-B', str(self.trusted/'verify_candidate.py'),
                                '--root', str(self.source), '--pin', self.manifest_pin],
                               capture_output=True, text=True, timeout=30)
        self.assertEqual(check.returncode, 0, check.stderr)
        self.assertEqual(json.loads(check.stdout)['status'], 'pass')
        # Опытная сессия теперь дополнительно отклоняет лишний объект до исполнения.
        self.refusal(reason='candidate_unverified')
        self.assertFalse(self.marker.exists())

    def test_recomputed_pin_only_proves_consistency(self):
        start = self.source/'kit/base/START.md'
        changed = start.read_bytes().replace(b'## 0. ', b'## 0. SYNTHETIC_UNTRUSTED ')
        self.assertNotEqual(start.read_bytes(), changed)
        start.write_bytes(changed)
        self.refusal(reason='candidate_unverified')
        # Имитируем подмену и манифеста, и pin одним источником: это НЕ доверенный канал.
        self.manifest['files']['kit/base/START.md'] = sha(changed)
        raw = (json.dumps(self.manifest, sort_keys=True, indent=2)+'\n').encode()
        (self.source/MANIFEST).write_bytes(raw)
        self.manifest_pin = sha(raw)
        p, lines = self.launch()
        reply = self.send(p, lines, {'type':'bootstrap'})
        self.assertIn('SYNTHETIC_UNTRUSTED', reply['section0'])
        self.assertEqual(reply['manifest_sha256'], self.manifest_pin)


if __name__ == '__main__':
    unittest.main()
