#!/usr/bin/env python3
"""Только синтетическая модель D04 и временное ручное размещение, не установщик."""
import hashlib
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'research/audit')]
import core_audit as audit
import init_model
from kit.base import registry_journal, schema_v2


def sha(data):
    return hashlib.sha256(data).hexdigest()


def wire(doc):
    return (json.dumps(doc, ensure_ascii=False, sort_keys=True) + '\n').encode('utf-8')


class InitModelTests(unittest.TestCase):
    def setUp(self):
        self.version = json.loads((ROOT/'kit/KIT-VERSION.json').read_bytes())['version']
        self.l0 = {'schema_version': 2, 'area': 'L0', 'roots': ['kit'],
                   'release_version': self.version, 'entries': []}
        self.raw = wire(self.l0)
        self.pin = sha(self.raw)  # Вычислен из фикстуры, не является независимым доверием.

    def model(self, raw=None, **kwargs):
        opts = {'system_pin': self.pin, 'candidate_version': self.version, 'profile_root': 'profiles/pilot'}
        opts.update(kwargs)
        return init_model.model(self.raw if raw is None else raw, **opts)

    def assert_refused(self, code, raw=None, **kwargs):
        with self.assertRaises(init_model.ModelError) as result:
            self.model(raw, **kwargs)
        self.assertEqual(str(result.exception), code)

    def test_pure_deterministic_model_without_file_access(self):
        with patch('builtins.open', side_effect=AssertionError('filesystem access')), \
             patch.object(Path, 'open', side_effect=AssertionError('filesystem access')), \
             patch('os.open', side_effect=AssertionError('filesystem access')), \
             patch('os.stat', side_effect=AssertionError('filesystem access')):
            plan, files = self.model()
            self.assertEqual((plan, files), self.model())
        self.assertEqual(plan['outcome'], 'study_only')
        self.assertEqual(plan['origin'], 'not_verified')
        self.assertEqual(plan['l0_semantics'], 'not_checked')
        self.assertEqual(plan['destination'], 'not_selected')
        self.assertEqual(plan['apply'], 'not_implemented')
        self.assertEqual(set(files), {'kit/base/registry.json', 'profiles/pilot/registry.json',
                                     '.domain-agent-kit/project/registry.json'})
        self.assertEqual(files['kit/base/registry.json'], self.raw)
        for row in plan['files']:
            self.assertEqual(row['bytes'], len(files[row['path']]))
            self.assertEqual(row['sha256'], sha(files[row['path']]))
        for area, path, root in (('L1', 'profiles/pilot/registry.json', 'profiles/pilot'),
                                 ('L2', '.domain-agent-kit/project/registry.json', '.domain-agent-kit')):
            doc = schema_v2.parse_json(files[path])
            reg, journal = registry_journal.unpack_registry(doc, area=area)
            self.assertEqual((reg['revision'], reg['entries'], reg['roots']), (0, [], [root]))
            self.assertEqual(journal['decisions'], [])

    def test_pin_and_input_size_refuse(self):
        self.assert_refused('pin_invalid', system_pin='BAD')
        self.assert_refused('pin_mismatch', system_pin='0'*64)
        self.assert_refused('l0_invalid', raw='not bytes')
        self.assert_refused('l0_invalid', raw=b'x'*(init_model.MAX_L0+1))
        changed = self.raw + b' '
        self.assert_refused('pin_mismatch', raw=changed)
        plan, files = self.model(raw=changed, system_pin=sha(changed))
        self.assertEqual(files['kit/base/registry.json'], changed)
        self.assertEqual(plan['origin'], 'not_verified')

    def test_version_exact_and_l0_identity(self):
        for version in ('0.0.0', self.version+'+build', None):
            with self.subTest(version=version):
                self.assert_refused('version_mismatch', candidate_version=version)
        changed = dict(self.l0, roots=['other'])
        self.assert_refused('l0_root_mismatch', raw=wire(changed), system_pin=sha(wire(changed)))
        changed = dict(self.l0, area='L1', revision=0); changed.pop('release_version')
        self.assert_refused('catalog_invalid', raw=wire(changed), system_pin=sha(wire(changed)))

    def test_bad_profile_roots_rejected(self):
        for root in ('kit', 'KIT/base', 'kit/inner', '.domain-agent-kit/project',
                     '.domain-agent-kit', '.', '../profile', '/absolute', 'profiles//pilot',
                     'profiles/../pilot', 'profiles/CON', '', None):
            with self.subTest(root=root):
                self.assert_refused('catalog_invalid', profile_root=root)
        plan, files = self.model(profile_root='kit-like/pilot')
        self.assertIn('kit-like/pilot/registry.json', files)
        self.assertEqual(plan['outcome'], 'study_only')

    def test_invalid_json_and_schema_rejected_even_with_matching_pin(self):
        invalid = [b'{"area":"L0","area":"L0"}', b'{"x":NaN}', b'\xff', b'{', wire(dict(self.l0, extra=True))]
        for raw in invalid:
            with self.subTest(raw=raw):
                self.assert_refused('catalog_invalid', raw=raw, system_pin=sha(raw))

    def test_supplied_version_is_not_candidate_verification(self):
        invented = '9.9.9-synthetic'
        raw = wire(dict(self.l0, release_version=invented))
        plan, files = self.model(raw=raw, system_pin=sha(raw), candidate_version=invented)
        self.assertNotEqual(invented, self.version)
        self.assertEqual(plan['origin'], 'not_verified')
        self.assertEqual(files['kit/base/registry.json'], raw)

    def test_valid_l0_does_not_prove_semantics_or_origin(self):
        # Содержимое не оценивается: две противоположные формулировки синтетически проходят.
        for text in ('разрешено', 'запрещено'):
            item = audit.entry('S-1', 'contract', 'system_release', None, '.', text=text)
            raw = wire(dict(self.l0, entries=[item]))
            plan, files = self.model(raw=raw, system_pin=sha(raw))
            self.assertEqual(plan['l0_semantics'], 'not_checked')
            self.assertEqual(plan['origin'], 'not_verified')
            self.assertEqual(files['kit/base/registry.json'], raw)

    def test_manual_synthetic_placement_then_verified_first_action(self):
        # Ручное тестовое размещение в новом temp: не реализация применения модели.
        plan, files = self.model()
        with tempfile.TemporaryDirectory(prefix='domain-init-study-') as td:
            root = Path(td).resolve(); workspace = root/'workspace'; workspace.mkdir()
            source = root/'source'; source.mkdir(); trusted = root/'trusted'; trusted.mkdir()
            for rel, data in files.items():
                path = workspace/rel; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
                if os.name == 'posix': path.chmod(0o600)  # Только новые синтетические файлы.
            manifest_raw = (ROOT/'kit/KIT-VERSION.json').read_bytes()
            manifest = json.loads(manifest_raw)
            for rel in ['kit/KIT-VERSION.json', *manifest['files']]:
                dest = source/rel; dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT/rel, dest)
            for name in ('snapshot_session.py', 'verify_candidate.py'):
                shutil.copyfile(ROOT/'kit'/name, trusted/name)
            before = audit.tree_digest(workspace)
            proc = subprocess.Popen([sys.executable, '-I', '-S', '-B', str(trusted/'snapshot_session.py'),
                '--candidate-root', str(source), '--workspace', str(workspace), '--profile-root', 'profiles/pilot',
                '--profile-id', 'Pilot', '--manifest-pin', sha(manifest_raw), '--system-pin', self.pin],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding='utf-8', bufsize=1, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
            lines = queue.Queue()
            def reader():
                for line in proc.stdout: lines.put(line)
                lines.put(None)
            threading.Thread(target=reader, daemon=True).start()
            def send(payload):
                proc.stdin.write(json.dumps(payload, ensure_ascii=False)+'\n'); proc.stdin.flush()
                try: line = lines.get(timeout=15)
                except queue.Empty: raise AssertionError('нет ответа сессии') from None
                self.assertIsNotNone(line, 'сессия завершилась без ответа')
                return json.loads(line)
            try:
                self.assertEqual(send({'type':'bootstrap'})['outcome'], 'bootstrap')
                request = ('Создай черновик контракта C-9 в профиле Pilot, постоянное, '
                           'область «docs», название «Пример», основание «Проба», '
                           'критерий «Запись существует»: Согласуем порядок чтения.')
                operation = send({'type':'plan', 'request':request})
                self.assertEqual(operation['outcome'], 'planned')
                self.assertEqual(audit.tree_digest(workspace), before)
                denied = send({'type':'apply', 'plan':operation, 'confirmed_ticket':''})
                self.assertEqual(denied['diagnostic']['code'], 'confirmation_required')
                self.assertEqual(audit.tree_digest(workspace), before)
                applied = send({'type':'apply', 'plan':operation, 'confirmed_ticket':operation['ticket']})
                self.assertEqual(applied['outcome'], 'applied')
                after = audit.tree_digest(workspace)
                self.assertEqual({name for name in before if before[name] != after[name]},
                                 {'profiles/pilot/registry.json'})
                self.assertEqual(set(before), set(after))
                self.assertEqual((workspace/'kit/base/registry.json').read_bytes(), self.raw)
                l1 = schema_v2.parse_json((workspace/'profiles/pilot/registry.json').read_bytes())
                reg, history = registry_journal.unpack_registry(l1, area='L1')
                self.assertEqual((reg['revision'], reg['entries'][0]['id'], reg['entries'][0]['state']),
                                 (1, 'C-9', 'draft'))
                self.assertEqual(len(history['decisions']), 1)
            finally:
                if proc.poll() is None: proc.kill()
                proc.communicate(timeout=15)
        self.assertEqual(plan['origin'], 'not_verified')


if __name__ == '__main__':
    unittest.main()
