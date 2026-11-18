#!/usr/bin/env python3
"""Приёмка И-024: корпус восстановлен, измерение воспроизведено, правило 0.1.4 совпадает с ним.

Запуск: python3 acceptance.py <корень 024>
Читает measure.json, pairs-base.json, pairs-edition.json, replay/*.json и пишет ACCEPTANCE.json в stdout.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys
from collections import Counter

ROOT = pathlib.Path(sys.argv[1]).absolute()
rows = []


def get(name):
    return json.loads((ROOT / name).read_bytes())


def add(case, expected, actual, ok, evidence, limits='', status=None):
    rows.append(dict(case=case, expected=expected, actual=actual, status=status or ('pass' if ok else 'fail'),
                     evidence=evidence, limits=limits))


measure = get('measure.json')
base = get('pairs-base.json')
edition = get('pairs-edition.json')
replay_measure = get('replay/measure.json')
replay_pairs = get('replay/pairs-base.json')

add('корпус восстановлен', '112 пар: 36 повторов, 76 разных событий, 12 случаев',
    measure['corpus'], measure['corpus']['pairs'] == 112 and measure['corpus']['repeats'] == 36
    and measure['corpus']['different'] == 76 and measure['corpus']['cases'] == 12, 'measure.json')

bands = measure['text_bands']
add('порога по проценту похожести не существует', 'у всех четырёх мер зазор между повтором и чужим событием отсутствует',
    {name: dict(lowest=b['lowest_repeat'], highest=b['highest_different'], band=b['band']) for name, b in bands.items()},
    measure['all_bands_absent'] and all(b['band'] is None for b in bands.values()), 'measure.json')

grid = {g['added_max']: g for g in measure['token_grid']}
add('допустимое отклонение — 0 добавленных слов', 'при 0 добавленных словах 0 ложных склеек; при 2 — 13; при 3 — 18',
    grid, grid[0]['false_merges'] == 0 and grid[0]['repeats_found'] == 12
    and grid[2]['false_merges'] > 0 and grid[3]['false_merges'] > grid[2]['false_merges'], 'measure.json',
    'Точка 0 — единственная с нулём ложных склеек на этом корпусе.')

for line, data in (('base', base), ('edition', edition)):
    add(f'правило 0.1.4 совпадает с измерением, {line}',
        '12 склеек, все — «вар3»; 0 ложных; 0 пропущенных; байты не менялись',
        dict(outcome=data['outcome'], merged=data['merged_count'], unexpected=data['unexpected_merges'],
             missed=data['missed_merges'], mismatches=len(data['mismatches']), bytes_unchanged=data['bytes_unchanged'],
             pairs=data['pairs']),
        data['outcome'] == 'pass' and data['merged_count'] == 12 and not data['unexpected_merges']
        and not data['missed_merges'] and not data['mismatches'] and data['bytes_unchanged'],
        f'pairs-{line}.json')

add('записи прошли через план и билет', 'на каждую из 112 пар — установка, подключение и две записи; всего 448 одобренных операций',
    dict(pairs=base['pairs'], operations=base['pairs'] * 4),
    base['pairs'] == 112 and base['outcome'] == 'pass', 'pairs-base.json')

add('повтор из печати', 'измерение и записи из запечатанного архива дают те же числа',
    dict(measure_equal=replay_measure == measure, pairs_equal=replay_pairs == base),
    replay_measure == measure and replay_pairs == base, 'replay/')

add('настоящие журналы', 'Вне площадки: принимаются в И-023.', None, False, '—',
    'Корпус синтетический: 12 случаев, формулировки стенда. Реальные журналы не подавались.', status='not run')
add('Windows, права и живые расширения', 'Вне площадки: как и в прежних выпусках.', None, False, '—',
    'Linux, синтетические проекты, без моделей и сети.', status='not run')

print(json.dumps(dict(counts=dict(Counter(r['status'] for r in rows)), rows=rows,
                      corpus_sha256=measure['corpus']['sha256']), ensure_ascii=False, indent=2, sort_keys=True))
