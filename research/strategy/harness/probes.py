#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Пробы закреплённого выпуска 0.1.36, перенесённые из И-101.

Инвентарь фиксирует дерево до импорта contract.py; присутствие поверхности
проверяется по операциям/командам (P13). Чистый сценарий не калибрует агента.
Пробам передаётся только ZIP, хеш которого проверен вызывающим харнессом.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile

EXPECTED_SURFACES = ('promote', 'simulate', 'bundle', 'bundle_verify', 'guard', 'prompt')
EXPECTED_ADAPTERS = ('kilo', 'copilot', 'arena')
PIN_OF = 'releases/0.1.36'


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def zip_facts(path):
    with zipfile.ZipFile(path) as z:
        names = sorted(n for n in z.namelist() if not n.endswith('/'))
        sizes = {n: z.getinfo(n).file_size for n in names}
    raw = Path(path).read_bytes()
    return {
        'file': os.path.basename(path),
        'bytes': len(raw),
        'sha256': sha256_bytes(raw),
        'members': len(names),
        'uncompressed_bytes': sum(sizes.values()),
    }


def tree_facts(root):
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d != '__pycache__')
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace(os.sep, '/')
            files.append((rel, os.path.getsize(full)))
    files.sort()
    h = hashlib.sha256()
    for rel, size in files:
        with open(os.path.join(root, rel), 'rb') as fh:
            h.update(rel.encode() + b'\0' + str(size).encode() + b'\0')
            h.update(sha256_bytes(fh.read()).encode() + b'\n')
    return {'files': len(files), 'tree_digest': h.hexdigest()}


def load_contract(root):
    path = os.path.join(root, 'kit', 'tools', 'contract.py')
    spec = importlib.util.spec_from_file_location('contract_baseline', path)
    mod = importlib.util.module_from_spec(spec)
    # dataclass() в 0.1.36 ищет модуль в sys.modules — регистрируем до исполнения.
    sys.modules[spec.name] = mod
    try:
        spec.loader.exec_module(mod)
    finally:
        del sys.modules[spec.name]
    return mod, Path(path).read_text(encoding='utf-8')


def ops_of(source):
    ops = set(re.findall(r"op == '([a-z_]+)'", source))
    for group in re.findall(r"op in \(([^)]*)\)", source):
        ops.update(re.findall(r"'([a-z_]+)'", group))
    return sorted(ops)


def commands_of(source):
    m = re.search(r"choices=\(([^)]*)\)", source)
    return sorted(re.findall(r"'([a-z_]+)'", m.group(1))) if m else []


def adapters_of(mod):
    out = {}
    for name, card in sorted(getattr(mod, 'ADAPTERS', {}).items()):
        out[name] = {
            'title': card.get('title'),
            'status': card.get('status'),
            'entry': card.get('entry'),
            'rank': (card.get('priority') or {}).get('rank'),
            'of': (card.get('priority') or {}).get('of'),
        }
    return out


def surfaces_of(source, ops, commands):
    """Совпадение токена — справочная отметка, не условие наличия поверхности."""
    found = {}
    for surface in EXPECTED_SURFACES:
        token = surface.replace('_bundle', '').replace('bundle_', '')
        found[surface] = {
            'command_present': surface in commands,
            'op_present': surface in ops,
            'token_in_source_advisory': token in source,  # совпадение имени — не доказательство поверхности
            'present': surface in ops or surface in commands,
        }
    return found


def inventory(zip_path):
    with tempfile.TemporaryDirectory(prefix='ack-inventory-') as temp:
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(temp)
        tree = os.path.join(temp, 'AgentContractLab')
        tree_data = tree_facts(tree)   # до импорта: импорт создаёт __pycache__
        mod, source = load_contract(tree)
        ops = ops_of(source)
        commands = commands_of(source)
        adapters = adapters_of(mod)
        data = {
            'format': 1,
            'release': getattr(mod, 'VERSION', None),
            'zip': zip_facts(zip_path),
            'tree': tree_data,
            'schema': {
                'targets': sorted(getattr(mod, 'TARGETS', [])),
                'types': list(getattr(mod, 'TYPES', [])),
                'transitions': {k: list(v) for k, v in sorted(getattr(mod, 'TRANSITIONS', {}).items())},
                'env_keys': list(getattr(mod, 'ENV_KEYS', '')),
            },
            'commands': commands,
            'ops': ops,
            'adapters': adapters,
            'surfaces': surfaces_of(source, ops, commands),
            'absent_adapters': [n for n in EXPECTED_ADAPTERS if n not in adapters],
            'stub_adapters': [n for n in adapters if adapters[n]['status'] != 'documented'],
            'not_run': [
                {'what': 'поведение моделей в трёх средах', 'why': 'требует отдельной сессии и N повторов; И-125'},
                {'what': 'чтение AGENTS.md в Arena', 'why': 'публичной спецификации нет; И-124/И-125'},
            ],
        }
        blob = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
        data['digest'] = sha256_bytes(blob)
        return data


def run(lab, project, command, payload=None):
    cmd = [sys.executable, '-I', '-B', '-X', 'utf8', os.path.join(lab, 'kit', 'tools', 'contract.py'),
           '--lab', lab, '--project', project, command]
    data = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else b''
    p = subprocess.run(cmd, input=data, capture_output=True, cwd=lab, timeout=30)
    try:
        out = json.loads(p.stdout.decode() or '{}')
    except ValueError:
        out = {'unparsed': p.stdout.decode(errors='replace')[:400]}
    return p.returncode, out


def plan_apply(lab, project, request):
    rc, view = run(lab, project, 'plan', request)
    if rc != 0:
        return rc, view
    rc2, res = run(lab, project, 'apply', {'request': request, 'ticket': view['ticket']})
    return rc2, res


def manifest_pin(lab):
    with open(os.path.join(lab, PIN_OF, 'manifest.json'), 'rb') as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def clean_room(zip_path):
    with tempfile.TemporaryDirectory(prefix='ack-cleanroom-') as temp:
        return run_clean_room(zip_path, temp)


def run_clean_room(zip_path, temp):
    lab = os.path.join(temp, 'lab')
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(temp)
    os.rename(os.path.join(temp, 'AgentContractLab'), lab)
    os.makedirs(os.path.join(lab, 'A'))
    steps = []

    rc, out = run(lab, 'A', 'status')
    steps.append({'step': '1-status-before', 'rc': rc, 'health': out.get('health')})

    rc, out = plan_apply(lab, 'A', {'op': 'install', 'package': PIN_OF, 'pin': manifest_pin(lab)})
    steps.append({'step': '2-install', 'rc': rc, 'error': out.get('error')})

    rc, out = run(lab, 'A', 'status')
    steps.append({'step': '3-status-after-install', 'rc': rc, 'health': out.get('health'),
                  'entry_mode': out.get('entry_mode')})

    rc, out = plan_apply(lab, 'A', {'op': 'connect'})
    steps.append({'step': '4-connect', 'rc': rc, 'error': out.get('error')})

    # Находка И-101: запись вида rule обязана принадлежать контракту (parent).
    # Поэтому минимальный create — два шага: контракт, затем правило внутри него.
    rc, out = plan_apply(lab, 'A', {
        'op': 'create', 'kind': 'contract', 'title': 'Канарейка И-101', 'scope': '.',
        'text': 'Контракт чистого прогона.', 'basis': 'И-101 чистая копия',
        'criterion': 'list показывает контракт с действующим правилом',
        'reason': 'инициализация чистой копии', 'state': 'active'})
    steps.append({'step': '5a-create-contract', 'rc': rc, 'error': out.get('error')})

    rc, out = plan_apply(lab, 'A', {
        'op': 'create', 'kind': 'rule', 'contract': 'P-1', 'title': 'Правило канарейки',
        'scope': '.', 'text': 'Проверка чистого прогона: правило существует один раз.',
        'basis': 'И-101 чистая копия', 'criterion': 'list показывает ровно одно правило P-2',
        'reason': 'инициализация чистой копии', 'state': 'active'})
    steps.append({'step': '5b-create-rule', 'rc': rc, 'error': out.get('error')})

    rc, out = run(lab, 'A', 'list')
    entries = (out.get('active') or []) + (out.get('contracts') or [])
    steps.append({'step': '6-list', 'rc': rc, 'count': len(entries),
                  'active': len(out.get('active') or []),
                  'contracts': len(out.get('contracts') or []),
                  'ids': [e.get('id') for e in entries]})

    rc, out = run(lab, 'A', 'adapter', {'name': 'arena'})
    steps.append({'step': '7-adapter-arena', 'rc': rc, 'error': out.get('error')})

    rc, out = run(lab, 'A', 'status')
    steps.append({'step': '8-status-final', 'rc': rc, 'health': out.get('health'),
                  'revision': out.get('revision')})

    stable = [{k: v for k, v in s.items() if k not in ('at',)} for s in steps]
    digest = hashlib.sha256(json.dumps(stable, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return {'format': 1, 'zip': os.path.basename(zip_path), 'steps': steps,
            'checkpoints_digest': digest,
            'expected': {'2-install': 'rc=0', '5a-create-contract': 'rc=0', '5b-create-rule': 'rc=0', '6-list': 'count=2 (1 contract + 1 active)',
                         '7-adapter-arena': 'error=adapter_unknown'}}



def release_suite(zip_path):
    """Повтор kit/tests, отдельно от сценария «установить, подключить, создать»."""
    with tempfile.TemporaryDirectory(prefix='ack-release-tests-') as temp:
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(temp)
        lab = Path(temp) / 'AgentContractLab'
        run_id = 'iteration-release-tests'
        command = ['kit/tests/test_contract.py', '--run-id', run_id]
        proc = subprocess.run([sys.executable, '-I', '-B', '-X', 'utf8', *command],
                              cwd=lab, capture_output=True, timeout=180)
        result = lab / 'runs' / run_id / 'CHECKS.json'
        if not result.is_file():
            raise ValueError(f'kit/tests не записал CHECKS.json (rc={proc.returncode}): '
                             + proc.stderr.decode('utf-8', errors='replace')[-1000:])
        report = json.loads(result.read_text(encoding='utf-8'))
        return {
            'rc': proc.returncode,
            'version': report['version'],
            'totals': report['totals'],
            'not_run': [{'case': row['case'], 'test': row['test'], 'reason': row['actual']}
                        for row in report['cases'] if row['status'] == 'not run'],
            'failures': [{'case': row['case'], 'test': row['test']}
                         for row in report['cases'] if row['status'] == 'fail'],
        }
