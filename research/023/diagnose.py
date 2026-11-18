#!/usr/bin/env python3
"""И-023: почему настоящий повтор не склеился. Диагностика, не приёмка: продукт не меняется.

Для каждой пары-повтора из журналов берутся собственные сравнения продукта (`same_observation`,
`word_deviation`, `fact_bits`) и три контрфактических варианта в отдельных проектах:
  как есть → выровнена улика → выровнена улика и длительность.
Контрфактические варианты помечены как `counterfactual`: они существуют только чтобы назвать причину.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import re
import shutil
import sys
import tempfile

HERE = pathlib.Path(__file__).absolute().parent
ap = argparse.ArgumentParser()
ap.add_argument('--tree', default=str(HERE.parent / 'release-0.1.4/base/AgentContractLab'))
ARGS = ap.parse_args()
TREE = pathlib.Path(ARGS.tree).absolute()
spec = importlib.util.spec_from_file_location('kit_contract', TREE / 'kit/tools/contract.py')
c = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = c
spec.loader.exec_module(c)

VERSION = c.parse((TREE / 'kit/base/manifest.json').read_bytes())['base_version']
PIN = c.digest((TREE / 'kit/base/manifest.json').read_bytes())
OBS = {o['id']: o for o in json.loads((HERE / 'observations.json').read_text(encoding='utf-8'))['rows']}
ENV = {k: 'synthetic' for k in c.ENV_KEYS.split()}
FIELDS = 'case level conditions expected actual status evidence limits environment'.split()
DURATION = re.compile(r' in \d+\.\d+s(?: \(\d+:\d+:\d+\))?')

PAIRS = [
    ('repeat-form', 'pytest-run1#L386', 'pytest-run2#L385'),
    ('repeat-form', 'pip-build#L75', 'pip-build#L92'),
    ('repeat-volatile', None, None),   # заполняется ниже из pairs-023-base.json
]


def payload(observation_id, **overrides):
    source = OBS[observation_id]
    record = {k: source[k] for k in FIELDS if k in source}
    record['status'] = 'pass'
    record.update(overrides)
    record['environment'] = dict(ENV)
    return record


def compare(a, b):
    same = {k: a[k] == b[k] for k in c._TEXT_FIELDS}
    return dict(same=same,
                words={k: c.word_deviation(a[k], b[k])[0] for k in c._TEXT_FIELDS},
                worst={k: round(c.word_deviation(a[k], b[k])[1], 4) for k in c._TEXT_FIELDS},
                critical={k: a[k] == b[k] for k in c._CRITICAL},
                facts_left=sorted(c.fact_bits(a) - c.fact_bits(b)),
                facts_right=sorted(c.fact_bits(b) - c.fact_bits(a)),
                same_observation=c.same_observation(a, b))


def main():
    report = json.loads((HERE / 'pairs-023-base.json').read_text(encoding='utf-8'))
    volatile = [r['pair'] for r in report['rows'] if r['pair']['klass'] == 'repeat-volatile'][0]
    PAIRS[2] = ('repeat-volatile', volatile['left'], volatile['right'])

    lab = pathlib.Path(tempfile.mkdtemp(prefix='i023d-'))
    shutil.copytree(TREE / 'releases', lab / 'releases')

    def call(command, project, body):
        return c.dispatch(lab, project, command, body)

    def approved(project, request):
        view = call('plan', project, request)
        return call('apply', project, {'request': request, 'ticket': view['ticket']})

    results = []
    for number, (klass, left_id, right_id) in enumerate(PAIRS, 1):
        left, right = payload(left_id), payload(right_id)
        evidence_right = dict(right, evidence=left['evidence'])
        variants = [('как есть', left, right), ('улика выровнена', left, evidence_right)]
        if klass == 'repeat-volatile':
            variants.append(('улика выровнена и длительность снята у обоих',
                             dict(left, actual=DURATION.sub('', left['actual'])),
                             dict(evidence_right, actual=DURATION.sub('', evidence_right['actual']))))
        outcomes = []
        for name, first, second in variants:
            project = f'D{number}_{len(outcomes)}'
            (lab / project).mkdir()
            approved(project, dict(op='install', package=f'releases/{VERSION}', pin=PIN))
            approved(project, dict(op='connect'))
            approved(project, dict(op='record_check', observation=first))
            got = approved(project, dict(op='record_check', observation=second))
            outcomes.append(dict(variant=name, outcome=got['outcome']))
        results.append(dict(klass=klass, left=left_id, right=right_id, comparison=compare(left, right),
                            counterfactual=outcomes))
    shutil.rmtree(lab, ignore_errors=True)

    out = dict(iteration='И-023', kind='diagnosis', note='продукт не менялся; контрфактические варианты '
               'помечены и в приёмку не входят', text_fields=list(c._TEXT_FIELDS),
               critical_fields=list(c._CRITICAL), pairs=results)
    (HERE / 'DIAGNOSIS.json').write_text(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True)
                                         + '\n', encoding='utf-8')
    for row in results:
        cmp = row['comparison']
        print(f"{row['klass']:16} {row['left']} / {row['right']}")
        print(f"  слова: {cmp['words']}  худшее сходство: {cmp['worst']}  same: {cmp['same_observation']}")
        print(f"  факты только слева: {cmp['facts_left']}")
        print(f"  факты только справа: {cmp['facts_right']}")
        print(f"  варианты: {[(v['variant'], v['outcome']) for v in row['counterfactual']]}")


if __name__ == '__main__':
    main()
