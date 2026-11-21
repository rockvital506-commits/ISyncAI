#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""И-101: машинный инвентарь установленного выпуска AgentContractKit.

Назначение — снять baseline (BASELINE.json) из АРТЕФАКТА, а не из памяти агента.
Скрипт не пишет в проверяемое дерево, не запускает операций записи и не требует
внешних модулей. Только чтение: zip + распакованное дерево + импорт contract.py.

Детерминизм: ни времени, ни путей машины, ни порядка обхода в выход не попадают.
Один и тот же вход обязан давать один и тот же digest.

Использование:
  python3 inventory.py --zip <путь к AgentContractKit-X.Y.Z.zip> [--tree <распакованный каталог>]

Если --tree не указан, архив распаковывается во временный каталог и удаляется.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
import shutil
import tempfile
import zipfile

# Поверхности, которые стратегия объявляет существующими (И-101..И-140).
EXPECTED_SURFACES = ('promote', 'simulate', 'bundle', 'bundle_verify', 'guard', 'prompt')
EXPECTED_ADAPTERS = ('kilo', 'copilot', 'arena')
STUB_ADAPTERS = ('claude', 'cursor', 'antigravity')


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def zip_facts(path):
    with zipfile.ZipFile(path) as z:
        names = sorted(n for n in z.namelist() if not n.endswith('/'))
        sizes = {n: z.getinfo(n).file_size for n in names}
        raw = open(path, 'rb').read()
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
    spec.loader.exec_module(mod)
    return mod, open(path, encoding='utf-8').read()


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
    """Сигнал существования поверхности — токен в исходнике и операция, а не
    совпадение имён команд: команда `verify` в 0.1.36 проверяет не пакет."""
    found = {}
    for surface in EXPECTED_SURFACES:
        token = surface.replace('_bundle', '').replace('bundle_', '')
        found[surface] = {
            'command_present': surface in commands,
            'op_present': surface in ops,
            'token_in_source_advisory': token in source,  # совпадение имени — не доказательство поверхности
            'present': bool(surface in ops or (token in source and surface in commands)),
        }
    return found


def inventory(zip_path, tree=None):
    temp = None
    try:
        if tree is None:
            temp = tempfile.mkdtemp(prefix='inv101-')
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
    finally:
        if temp:
            shutil.rmtree(temp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--zip', required=True)
    ap.add_argument('--tree', default=None)
    ap.add_argument('--out', default=None)
    args = ap.parse_args()
    data = inventory(args.zip, args.tree)
    text = json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2)
    if args.out:
        with open(args.out, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(text + '\n')
    print(text)


if __name__ == '__main__':
    main()
