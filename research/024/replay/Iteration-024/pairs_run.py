#!/usr/bin/env python3
"""Все 112 пар восстановленного корпуса через настоящий продукт 0.1.4 (И-024).

Каждая пара — отдельный установленный проект, установка и обе записи проходят через план и билет.
Ожидание: второй член пары даёт `no_change` только для «вар3» (регистр, пунктуация, словоформа,
порядок слов) и `committed` для всех остальных; при склейке `checks.json` не меняется байт в байт.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import pathlib
import shutil
import sys
import tempfile

HERE = pathlib.Path(__file__).absolute().parent
sys.path.insert(0, str(HERE))
CORPUS = HERE / 'corpus.py' if (HERE / 'corpus.py').exists() else HERE.parent / '020' / 'corpus.py'
CORPUS_DIR = CORPUS.parent
sys.path.insert(0, str(CORPUS_DIR))
import corpus  # noqa: E402

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
PAIRS = corpus.pairs()
MERGE = frozenset(name for _, name, _, _ in PAIRS if name.endswith('вар3'))
ENV_OK = {k: 'synthetic' for k in c.ENV_KEYS.split()}


def full(o):
    out = dict(o)
    out['environment'] = dict(out['environment'])
    out.setdefault('status', 'pass')
    return out


def main():
    lab = pathlib.Path(tempfile.mkdtemp(prefix='i024-'))
    shutil.copytree(tree / 'releases', lab / 'releases')
    rows = []

    def call(command, project, payload):
        return c.dispatch(lab, project, command, payload)

    def approved(project, request):
        view = call('plan', project, request)
        assert view['writes'] is False, view
        return call('apply', project, {'request': request, 'ticket': view['ticket']})

    for index, (label, name, left, right) in enumerate(PAIRS, 1):
        project = f'P{index:03d}'
        (lab / project).mkdir()
        approved(project, dict(op='install', package=f'releases/{VERSION}', pin=PIN))
        approved(project, dict(op='connect'))
        first = approved(project, dict(op='record_check', observation=full(left)))
        assert first['outcome'] == 'committed', (name, first)
        before = (lab / project / c.CHECKS).read_bytes()
        want = 'no_change' if name in MERGE else 'committed'
        second = approved(project, dict(op='record_check', observation=full(right)))
        kept = len(c.parse((lab / project / c.CHECKS).read_bytes())['checks'])
        rows.append(dict(pair=name, label=label, expected=want, actual=second['outcome'],
                         files=second['files'], observations=kept,
                         unchanged=before == (lab / project / c.CHECKS).read_bytes()))
    shutil.rmtree(lab, ignore_errors=True)
    mismatches = [r for r in rows if r['expected'] != r['actual']]
    merged = [r['pair'] for r in rows if r['actual'] == 'no_change']
    report = dict(line=args.line, version=VERSION, release_pin=PIN, pairs=len(rows),
                  repeat_pairs=sum(1 for r in rows if r['label']), different_pairs=sum(1 for r in rows if not r['label']),
                  merged=sorted(merged), merged_count=len(merged),
                  unexpected_merges=[n for n in merged if n not in MERGE],
                  missed_merges=[n for n in MERGE if n not in merged],
                  mismatches=mismatches,
                  bytes_unchanged=all(r['unchanged'] for r in rows if r['actual'] == 'no_change'),
                  corpus_sha256=hashlib.sha256(CORPUS.read_bytes()).hexdigest(),
                  outcome='pass' if not mismatches else 'fail')
    sys.stdout.write(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + '\n')
    return 0 if report['outcome'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
