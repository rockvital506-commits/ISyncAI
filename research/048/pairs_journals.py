#!/usr/bin/env python3
"""И-025: пары наблюдений из настоящих журналов (И-023) через продукт 0.1.5.

Классы пар (правила из DESIGN.md, не пересматриваются после прогона):
  repeat-form      — одинаковый текст наблюдения из двух разных строк/журналов; ожидание: склейка
  repeat-volatile  — повторы, у которых отличается только длительность; ожидание: отказ (находка)
  hard-negative    — 20 самых похожих пар с разным текстом; ожидание: отказ
  random-negative  — 20 пар, выбранных отпечатком ключа; ожидание: отказ
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import importlib.util
import json
import pathlib
import re
import shutil
import sys
import tempfile

HERE = pathlib.Path(__file__).absolute().parent

ap = argparse.ArgumentParser()
ap.add_argument('--tree', required=True)
ap.add_argument('--line', default='base')
args = ap.parse_args()
tree = pathlib.Path(args.tree).absolute()
spec = importlib.util.spec_from_file_location('kit_contract', tree / 'kit/tools/contract.py')
c = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = c
spec.loader.exec_module(c)

VERSION = c.parse((tree / 'kit/base/manifest.json').read_bytes())['base_version']
PIN = c.digest((tree / 'kit/base/manifest.json').read_bytes())
OBS_PATH = HERE / 'observations.json' if (HERE / 'observations.json').exists() else HERE.parent / '023/observations.json'
OBS = json.loads(OBS_PATH.read_text(encoding='utf-8'))['rows']
BY_ID = {o['id']: o for o in OBS}
ENV_OK = {k: 'synthetic' for k in c.ENV_KEYS.split()}
FIELDS = 'case level conditions expected actual status evidence limits environment'.split()


def payload(observation_id):
    source = BY_ID[observation_id]
    record = {k: source[k] for k in FIELDS if k in source}
    record['status'] = 'pass'
    record['environment'] = dict(ENV_OK)
    return record


def build_pairs():
    pairs, used = [], set()

    def add(a, b, klass, note=''):
        key = tuple(sorted((a, b)))
        if key in used:
            return
        used.add(key)
        pairs.append(dict(left=a, right=b, klass=klass, note=note,
                          similarity=round(difflib.SequenceMatcher(None, BY_ID[a]['actual'],
                                                                   BY_ID[b]['actual']).ratio(), 4)))

    groups = {}
    for o in OBS:
        groups.setdefault(o['actual'], []).append(o)
    for text, members in groups.items():
        if len(members) >= 2:
            add(members[0]['id'], members[1]['id'], 'repeat-form', 'одинаковый текст наблюдения')

    durations = re.compile(r' in \d+\.\d+s(?: \(\d+:\d+:\d+\))?')
    summaries = [o for o in OBS if o['case'] == 'pytest-summary']
    for i in range(len(summaries)):
        for j in range(i + 1, len(summaries)):
            a, b = summaries[i], summaries[j]
            if a['facts'] != b['facts'] and durations.sub('', a['facts']) == durations.sub('', b['facts']):
                add(a['id'], b['id'], 'repeat-volatile', 'счётчики те же, длительность разная')

    candidates = []
    for i in range(len(OBS)):
        for j in range(i + 1, len(OBS)):
            a, b = OBS[i], OBS[j]
            key = tuple(sorted((a['id'], b['id'])))
            if a['actual'] == b['actual'] or key in used:
                continue
            ratio = difflib.SequenceMatcher(None, a['actual'], b['actual']).ratio()
            candidates.append((ratio, key))
    candidates.sort(key=lambda item: (-item[0], item[1]))
    for ratio, key in candidates[:20]:
        add(key[0], key[1], 'hard-negative', 'самые похожие пары с разным текстом')

    rest = [key for _, key in candidates]
    rest = [k for k in rest if k not in used]
    rest.sort(key=lambda k: hashlib.sha256(('И-023' + '|'.join(k)).encode()).hexdigest())
    for key in rest[:20]:
        add(key[0], key[1], 'random-negative', 'выбор по отпечатку ключа')
    return pairs


def main():
    pairs = build_pairs()
    lab = pathlib.Path(tempfile.mkdtemp(prefix='i023-'))
    shutil.copytree(tree / 'releases', lab / 'releases')

    def call(command, project, payload):
        return c.dispatch(lab, project, command, payload)

    def approved(project, request):
        view = call('plan', project, request)
        assert view['writes'] is False, view
        return call('apply', project, {'request': request, 'ticket': view['ticket']})

    rows = []
    for index, pair in enumerate(pairs, 1):
        project = f'R{index:03d}'
        (lab / project).mkdir()
        approved(project, dict(op='install', package=f'releases/{VERSION}', pin=PIN))
        approved(project, dict(op='connect'))
        first = approved(project, dict(op='record_check', observation=payload(pair['left'])))
        assert first['outcome'] == 'committed', (pair['left'], first)
        before = (lab / project / c.CHECKS).read_bytes()
        second = approved(project, dict(op='record_check', observation=payload(pair['right'])))
        after = (lab / project / c.CHECKS).read_bytes()
        old_checks = c.parse(before)['checks']
        new_checks = c.parse(after)['checks']
        row = dict(pair=pair, expected='no_change' if pair['klass'] == 'repeat-form' else 'committed',
                   actual=second['outcome'], files=second['files'],
                   kept=(before == after) if second['outcome'] == 'no_change' else None,
                   preserved=all(item in new_checks for item in old_checks),
                   observations=len(new_checks))
        rows.append(row)
    shutil.rmtree(lab, ignore_errors=True)

    def tally(klass):
        subset = [r for r in rows if r['pair']['klass'] == klass]
        return dict(pairs=len(subset), merged=sum(1 for r in subset if r['actual'] == 'no_change'),
                    refused=sum(1 for r in subset if r['actual'] == 'committed'),
                    mismatches=[r['pair'] for r in subset if r['expected'] != r['actual']])

    classes = {k: tally(k) for k in ('repeat-form', 'repeat-volatile', 'hard-negative', 'random-negative')}
    report = dict(line=args.line, version=VERSION, release_pin=PIN, journals=8,
                  observations=len(OBS), pairs=len(rows), classes=classes,
                  false_merges=[r['pair'] for r in rows
                                if r['pair']['klass'] in ('hard-negative', 'random-negative')
                                and r['actual'] == 'no_change'],
                  missed_repeats=[r['pair'] for r in rows
                                  if r['pair']['klass'] == 'repeat-form' and r['actual'] != 'no_change'],
                  merges_kept=all(r['kept'] for r in rows if r['kept'] is not None),
                  preserved=all(r['preserved'] for r in rows), rows=rows)
    (HERE / f'pairs-048-journals-{args.line}.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('line', 'pairs', 'classes', 'merges_kept', 'preserved')},
                     ensure_ascii=False, indent=1))
    print('ложных склеек:', len(report['false_merges']), 'не склеено повторов:', len(report['missed_repeats']))


if __name__ == '__main__':
    main()
