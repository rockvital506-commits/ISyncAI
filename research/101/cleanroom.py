#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""И-101: прогон в ЧИСТОЙ КОПИИ (протокол П4).

Ничего из рабочего дерева не используется: архив распаковывается заново во временный
каталог, проект `A` создаётся пустым. Проверяется только то, что спецификация
называет тестом: инициализация (install / connect) и create.

Стабильные точки замера (volatile: ticket, at, журнальные записи) — их не сравниваем.
Один и тот же архив обязан давать один и тот же `checkpoints_digest`.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

PIN_OF = 'releases/0.1.36'


def run(lab, project, command, payload=None):
    cmd = [sys.executable, '-I', '-B', os.path.join(lab, 'kit', 'tools', 'contract.py'),
           '--lab', lab, '--project', project, command]
    data = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else b''
    p = subprocess.run(cmd, input=data, capture_output=True, cwd=lab)
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
    temp = tempfile.mkdtemp(prefix='clean101-')
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

    shutil.rmtree(temp, ignore_errors=True)
    stable = [{k: v for k, v in s.items() if k not in ('at',)} for s in steps]
    digest = hashlib.sha256(json.dumps(stable, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return {'format': 1, 'zip': os.path.basename(zip_path), 'steps': steps,
            'checkpoints_digest': digest,
            'expected': {'2-install': 'rc=0', '5a-create-contract': 'rc=0', '5b-create-rule': 'rc=0', '6-list': 'count=2 (1 contract + 1 active)',
                         '7-adapter-arena': 'error=adapter_unknown'}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--zip', required=True)
    ap.add_argument('--out', default=None)
    args = ap.parse_args()
    data = clean_room(args.zip)
    text = json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2)
    if args.out:
        with open(args.out, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(text + '\n')
    print(text)


if __name__ == '__main__':
    main()
