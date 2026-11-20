#!/usr/bin/env python3
"""Приёмка И-022: восстановленный выпуск 0.1.4 собран, проверен, запечатан и повторяем.

Запуск: python3 acceptance.py <корень research/022> <путь к запечатанному архиву> <каталог повтора>
Пишет ACCEPTANCE.json в stdout.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys
import zipfile
from collections import Counter

ROOT = pathlib.Path(sys.argv[1]).absolute()
SEAL = pathlib.Path(sys.argv[2]).absolute()
REPLAY = pathlib.Path(sys.argv[3]).absolute()
ORIGINAL = ROOT.parents[1] / 'dist/AgentContractKit-0.1.0.zip'
LINES = ('base', 'edition')
rows = []


def sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def add(case, expected, actual, ok, evidence, limits=''):
    rows.append(dict(case=case, expected=expected, actual=actual, status='pass' if ok else 'fail',
                     evidence=evidence, limits=limits))


def tree(line):
    return ROOT.parent / 'release-0.1.4' / line / 'AgentContractLab'


# 1. Испытания обеих линий
for line in LINES:
    totals = json.loads((tree(line) / 'reports/CHECKS.json').read_bytes())['totals']
    cases = {c['case']: c['status'] for c in json.loads((tree(line) / 'reports/CHECKS.json').read_bytes())['cases']}
    add(f'испытания комплекта, {line}', '35 pass / 0 fail / 3 not run',
        dict(totals=totals, X17=cases.get('X17'), X18=cases.get('X18'), X19=cases.get('X19')),
        totals == {'pass': 35, 'fail': 0, 'not run': 3, 'inconclusive': 0}
        and (cases.get('X17'), cases.get('X18'), cases.get('X19')) == ('pass', 'pass', 'pass'),
        f'release-0.1.4/{line}/AgentContractLab/reports/CHECKS.json')

# 2. Сквозная имитация
for line in LINES:
    pipe = json.loads((tree(line) / 'reports/PIPELINE.json').read_bytes())
    steps = pipe['steps']
    add(f'сквозная имитация, {line}', 'pass: повтор и пересказ не пишут, изменение смысла пишет, переход сохраняет записи',
        dict(outcome=pipe['outcome'], steps=steps, plans=pipe['plans']),
        pipe['outcome'] == 'pass' and steps['exact_repeat_inert'] and steps['reworded_repeat_inert']
        and steps['meaning_change_writes'] == 2 and steps['transition_preserved_records']
        and steps['repeat_after_update_inert'],
        f'release-0.1.4/{line}/AgentContractLab/reports/PIPELINE.json')

# 3. Ведомость отпечатков и метаданные
for line in LINES:
    base = tree(line)
    sums = {}
    for entry in (base / 'SHA256SUMS').read_text().splitlines():
        h, n = entry.split('  ', 1)
        sums[n] = h
    files = {p.relative_to(base).as_posix() for p in base.rglob('*') if p.is_file()} - {'SHA256SUMS'}
    bad = [n for n in files if sums.get(n) != sha(base / n)]
    man = (base / 'kit/base/manifest.json').read_bytes()
    rel = (base / 'releases/0.1.4/manifest.json').read_bytes()
    add(f'ведомость и метаданные, {line}', '23 отпечатка сходятся, манифест базы равен манифесту выпуска',
        dict(count=len(sums), files=len(files), bad=bad, manifest_equal=man == rel,
             base_version=json.loads(man)['base_version'], origin=json.loads(man)['origin']),
        len(sums) == len(files) == 23 and not bad and man == rel and json.loads(man)['base_version'] == '0.1.4',
        f'release-0.1.4/{line}/AgentContractLab/SHA256SUMS')

# 4. Предок не переписан
with zipfile.ZipFile(ORIGINAL) as z:
    original = {n.split('/', 1)[1]: z.read(n) for n in z.namelist() if n.startswith('AgentContractLab/releases/0.1.0/')}
diff = []
for line in LINES:
    for name, data in original.items():
        rel = name.replace('releases/0.1.0/', 'releases/0.1.0/', 1)
        if (tree(line) / rel).read_bytes() != data:
            diff.append(f'{line}:{rel}')
add('предок 0.1.0 не переписан', 'шесть файлов совпадают с исходным архивом байт в байт',
    dict(files=len(original), differences=diff), not diff, 'dist/AgentContractKit-0.1.0.zip')

# 5. Печать
with zipfile.ZipFile(SEAL) as z:
    names = [n for n in z.namelist() if not n.endswith('/')]
    broken = z.testzip()
    sums = {}
    for entry in z.read('Iteration-022/SHA256SUMS').decode().splitlines():
        h, n = entry.split('  ', 1)
        sums[n] = h
    bad = [n for n in names if not n.endswith('SHA256SUMS')
           and hashlib.sha256(z.read(n)).hexdigest() != sums.get(n.replace('Iteration-022/', ''))]
add('печать', 'архив цел, все отпечатки членов сходятся', dict(members=len(names), sums=len(sums), broken=broken, bad=bad),
    broken is None and not bad and len(sums) == len(names) - 1, SEAL.name)

# 6. Повтор из печати
replay_checks = json.loads((REPLAY / 'CHECKS.json').read_bytes())
replay_pipe = json.loads((REPLAY / 'PIPELINE.json').read_bytes())
add('повтор из печати', 'испытания и имитация распакованного архива дают те же итоги, что и сборка',
    dict(totals=replay_checks['totals'], outcome=replay_pipe['outcome'], version=replay_pipe['version']),
    replay_checks['totals'] == {'pass': 35, 'fail': 0, 'not run': 3, 'inconclusive': 0}
    and replay_pipe['outcome'] == 'pass', str(REPLAY))

# 7. Вне площадки
add('настоящие журналы', 'Вне площадки: принимаются в И-023.', None, False, '—',
    'Правило проверено на синтетических наблюдениях; реальные журналы не подавались.')
rows[-1]['status'] = 'not run'
add('полный корпус 112 пар', 'Вне площадки: корпус утрачен, восстанавливается и измеряется в И-024.', None, False, '—',
    'Здесь правило подтверждено только регрессиями X17–X19 и шагом имитации.')
rows[-1]['status'] = 'not run'
add('Windows, права и живые расширения', 'Вне площадки: как и в прежних выпусках.', None, False, '—',
    'Linux, синтетические проекты, без моделей.')
rows[-1]['status'] = 'not run'

print(json.dumps(dict(counts=dict(Counter(r['status'] for r in rows)), rows=rows), ensure_ascii=False, indent=2, sort_keys=True))
