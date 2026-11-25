#!/usr/bin/env python3
"""Проба исходного состава в синтетическом временном дереве, не установка Kit."""
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = 'kit/KIT-VERSION.json'
LEGACY = ('kit/compare_old.py', 'kit/COMPARE-OLD.md',
          'kit/legacy_capsule.py', 'kit/LEGACY-CAPSULE.md',
          'kit/legacy_projection.py', 'kit/LEGACY-PROJECTION.md')

# Исполняется отдельным интерпретатором -I -S в корне ТОЛЬКО временной копии.
RUNNER = r'''
import json, os, sys
from pathlib import Path
root = Path(sys.argv[1]); scenario = sys.argv[2]
sys.path.insert(0, str(root))
from kit.verify_candidate import VerificationError, verify
from kit.base import registry_store
from kit.base.bootstrap import BootstrapSession
from kit.base.registry_store import Layout, StoreError

assert Path(registry_store.__file__).resolve().is_relative_to(root)
layout = Layout(root, 'profiles/pilot')

def verify_status():
    try:
        return verify(root)['status']
    except VerificationError as exc:
        return str(exc)

if scenario == 'missing':
    before = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    try:
        BootstrapSession(layout, profile_id='Pilot').plan(
            'Создай черновик контракта C-1 в профиле Pilot, постоянное, '
            'область «docs», название «Пример», основание «Тест», '
            'критерий «Запись существует»: Согласуем порядок чтения.')
    except StoreError as exc:
        code = exc.code
    else:
        raise AssertionError('missing registries accepted')
    after = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    print(json.dumps({'verification': verify_status(), 'failure': code, 'unchanged': before == after}))
else:
    initial_verification = verify_status()
    # Эти файлы создаёт только тест, а не автономный установщик Kit.
    def write(path, value):
        p = root / path; p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(value, ensure_ascii=False) + '\n', encoding='utf-8')
        if os.name == 'posix': p.chmod(0o600)  # Только синтетическая проба.
    def empty(area, roots):
        result = {'schema_version': 2, 'area': area, 'roots': [roots], 'entries': []}
        result.update({'release_version': '0.2.0-mvp.59'} if area == 'L0' else {'revision': 0})
        return result
    write('kit/base/registry.json', empty('L0', 'kit'))
    write('profiles/pilot/registry.json', empty('L1', 'profiles/pilot'))
    write('.domain-agent-kit/project/registry.json', empty('L2', '.domain-agent-kit'))
    session = BootstrapSession(layout, profile_id='Pilot')
    phrase = ('Создай черновик контракта C-1 в профиле Pilot, постоянное, '
              'область «docs», название «Пример», основание «Тест», '
              'критерий «Запись существует»: Согласуем порядок чтения.')
    plan = session.plan(phrase)
    assert plan['outcome'] == 'planned', plan
    target = root / 'profiles/pilot/registry.json'
    before = target.read_bytes()
    try:
        session.apply(plan)
    except StoreError as exc:
        refusal = exc.code
    else:
        raise AssertionError('write without confirmation')
    unchanged = target.read_bytes() == before
    result = session.apply(plan, confirmed_ticket=plan['ticket'])
    entry = registry_store.read_registry(layout, target='L1')['entries'][0]
    unexpected = [x for x in sys.modules if x in ('kit.compare_old', 'kit.legacy_capsule', 'kit.legacy_projection') or x.startswith('research')]
    print(json.dumps({'initial_verification': initial_verification, 'verification': verify_status(), 'refusal': refusal, 'unchanged': unchanged,
                      'outcome': result['outcome'], 'id': entry['id'], 'state': entry['state'],
                      'legacy_or_research_imports': unexpected}, ensure_ascii=False))
'''


GUARD_RUNNER = r'''
import hashlib, json, shutil, sys
from pathlib import Path
source = Path(sys.argv[1]); workspace = source / 'synthetic-workspace'
workspace.mkdir()
shutil.copytree(source / 'kit', workspace / 'kit')
sys.path.insert(0, str(source))
from kit.guard import guard, GuardViolation
from kit.base.registry_store import Layout

def write(path, doc):
    p = workspace / path; p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc) + '\n', encoding='utf-8')
for area, root, path in (('L0', 'kit', 'kit/base/registry.json'),
                         ('L1', 'profiles/pilot', 'profiles/pilot/registry.json'),
                         ('L2', '.domain-agent-kit', '.domain-agent-kit/project/registry.json')):
    doc = {'schema_version': 2, 'area': area, 'roots': [root], 'entries': []}
    doc.update({'release_version': '0.2.0-mvp.59'} if area == 'L0' else {'revision': 0})
    write(path, doc)
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
manifest_pin = sha(source / 'kit/KIT-VERSION.json')
system_pin = sha(workspace / 'kit/base/registry.json')
layout = Layout(workspace, 'profiles/pilot')
first = guard(source, layout, manifest_pin=manifest_pin, system_pin=system_pin)['outcome']
# Меняется только тестовая рабочая копия; guard запускается из исходной.
changed = workspace / 'kit/base/bootstrap.py'
changed.write_bytes(changed.read_bytes() + b'\n# synthetic divergence\n')
second = guard(source, layout, manifest_pin=manifest_pin, system_pin=system_pin)['outcome']
code_differs = sha(changed) != sha(source / 'kit/base/bootstrap.py')
try:
    guard(source, layout, manifest_pin=manifest_pin, system_pin='0' * 64)
except GuardViolation as exc:
    wrong_pin = exc.reason
else:
    raise AssertionError('wrong system pin accepted')
l0 = workspace / 'kit/base/registry.json'
l0.write_bytes(l0.read_bytes() + b' ')
try:
    guard(source, layout, manifest_pin=manifest_pin, system_pin=system_pin)
except GuardViolation as exc:
    changed_l0 = exc.reason
else:
    raise AssertionError('changed system registry accepted')
(source / 'kit/base/bootstrap.py').write_bytes((source / 'kit/base/bootstrap.py').read_bytes() + b'\n# source divergence\n')
try:
    guard(source, layout, manifest_pin=manifest_pin, system_pin=system_pin)
except GuardViolation as exc:
    changed_source = exc.reason
else:
    raise AssertionError('changed source accepted')
print(json.dumps({'before': first, 'after_workspace_code_change': second,
                  'code_differs': code_differs, 'wrong_pin': wrong_pin, 'changed_l0': changed_l0,
                  'changed_source': changed_source}))
'''


class IsolatedCandidateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='isync-isolated-candidate-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        raw = (ROOT / MANIFEST).read_bytes()
        manifest = json.loads(raw)
        for rel, digest in manifest['files'].items():
            self.assertTrue(rel.startswith('kit/') and '..' not in Path(rel).parts)
            source = ROOT / rel
            content = source.read_bytes()
            self.assertEqual(hashlib.sha256(content).hexdigest(), digest, rel)
            target = self.root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        (self.root / MANIFEST).write_bytes(raw)

    def run_scenario(self, scenario):
        result = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', RUNNER, str(self.root), scenario],
                                cwd=self.root, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_clean_source_verifies_but_does_not_initialize_itself(self):
        result = self.run_scenario('missing')
        self.assertEqual(result, {'verification': 'pass', 'failure': 'missing_path', 'unchanged': True})

    def test_manually_prepared_synthetic_layout_and_source_check_conflict(self):
        result = self.run_scenario('prepared')
        self.assertEqual(result['refusal'], 'confirmation_required')
        self.assertTrue(result['unchanged'])
        self.assertEqual((result['outcome'], result['id'], result['state']), ('applied', 'C-1', 'draft'))
        self.assertEqual(result['legacy_or_research_imports'], [])
        self.assertIn('состав отличается', result['verification'])
        self.assertIn('kit/base/registry.json', result['verification'])

    def test_old_project_root_is_not_implicitly_selected(self):
        result = self.run_scenario('prepared')
        self.assertEqual(result['outcome'], 'applied')
        new_root = self.root/'.domain-agent-kit'
        old_root = self.root/'.agent-contract'
        new_root.rename(old_root)  # только временная синтетическая фикстура
        before = (old_root/'project/registry.json').read_bytes()
        probe = r'''import sys
from pathlib import Path
root=Path(sys.argv[1]); sys.path.insert(0,str(root))
from kit.base.registry_store import Layout, StoreError, status
try: status(Layout(root,'profiles/pilot'))
except StoreError as e: print(e.code)
else: raise AssertionError('old root unexpectedly accepted')
'''
        p = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', probe, str(self.root)],
                           cwd=self.root, capture_output=True, text=True, timeout=30)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout.strip(), 'missing_path')
        self.assertEqual((old_root/'project/registry.json').read_bytes(), before)

    def test_guard_separate_source_does_not_check_workspace_code(self):
        result = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', GUARD_RUNNER, str(self.root)],
                                cwd=self.root, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout), {'before': 'pass', 'after_workspace_code_change': 'pass',
                                                     'code_differs': True,
                                                     'wrong_pin': 'system_digest_mismatch',
                                                     'changed_l0': 'system_digest_mismatch',
                                                     'changed_source': 'candidate_unverified'})

    def test_without_donor_experiments_specific_core_flow_works_but_manifest_fails(self):
        for rel in LEGACY:
            (self.root / rel).unlink()
        result = self.run_scenario('prepared')
        self.assertEqual((result['outcome'], result['id'], result['state']), ('applied', 'C-1', 'draft'))
        self.assertTrue(result['unchanged'])
        self.assertEqual(result['refusal'], 'confirmation_required')
        self.assertEqual(result['legacy_or_research_imports'], [])
        self.assertIn('файл недоступен:', result['initial_verification'])
        self.assertIn(result['initial_verification'].split(': ')[-1], {Path(x).name for x in LEGACY})


if __name__ == '__main__':
    unittest.main()
