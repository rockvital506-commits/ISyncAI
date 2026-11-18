#!/usr/bin/env python3
"""И-030: замороженный корпус «точка и идентификатор» через настоящий продукт 0.1.10.

Каждая пара записывается в отдельный проект: первое наблюдение, затем второе. Склейка видна по
числу записей: одна — склеено, две — разные наблюдения. Метка корпуса не подгоняется.
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
ap = argparse.ArgumentParser()
ap.add_argument('--tree', required=True)
ap.add_argument('--line', default='base')
args = ap.parse_args()
TREE = pathlib.Path(args.tree).absolute()
spec = importlib.util.spec_from_file_location('kit_contract', TREE / 'kit/tools/contract.py')
c = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = c
spec.loader.exec_module(c)
VERSION = c.parse((TREE / 'kit/base/manifest.json').read_bytes())['base_version']
PIN = c.digest((TREE / 'kit/base/manifest.json').read_bytes())
CORPUS = HERE / 'pairs-030-corpus.json'
KINDS = ('dot-identifier', 'dot-dotted-name', 'dot-exception', 'dot-version', 'dot-file',
         'dot-two-sentences', 'name-with-extension', 'name-version', 'name-changed',
         'name-dotted-longer', 'number-changed', 'dot-vs-underscore')


def main() -> int:
    corpus = json.loads(CORPUS.read_text(encoding='utf-8'))
    lab = pathlib.Path(tempfile.mkdtemp(prefix='i029-'))
    shutil.copytree(TREE / 'releases', lab / 'releases')
    rows = []
    total = 0

    def approved(project, request):
        view = c.dispatch(lab, project, 'plan', request)
        return c.dispatch(lab, project, 'apply', {'request': request, 'ticket': view['ticket']})

    for item in corpus['pairs']:
        total += 1
        project = f'p{total:03d}'
        (lab / project).mkdir()
        approved(project, dict(op='install', package=f'releases/{VERSION}', pin=PIN))
        approved(project, dict(op='connect'))
        approved(project, dict(op='record_check', observation=item['left']))
        before = (lab / project / c.CHECKS).read_bytes()
        approved(project, dict(op='record_check', observation=item['right']))
        after = (lab / project / c.CHECKS).read_bytes()
        count = len(c.dispatch(lab, project, 'status', {})['observations'])
        rows.append(dict(index=total, kind=item['kind'], label=item['label'],
                         merged=count == 1, records=count, bytes_unchanged=before == after))
    shutil.rmtree(lab, ignore_errors=True)
    counts = {}
    for kind in KINDS:
        sel = [r for r in rows if r['kind'] == kind]
        counts[kind] = dict(pairs=len(sel), label_merge=sum(1 for r in sel if r['label']),
                            merged=sum(1 for r in sel if r['merged']))
    misses = [f"{r['index']}:{r['kind']}" for r in rows if r['label'] and not r['merged']]
    false = [f"{r['index']}:{r['kind']}" for r in rows if not r['label'] and r['merged']]
    report = dict(iteration='И-030', line=args.line, version=VERSION, release_pin=PIN,
                  pairs=len(rows), corpus_sha256=hashlib.sha256(CORPUS.read_bytes()).hexdigest(),
                  kinds=counts, missed_merges=misses, false_merges=false,
                  bytes_unchanged=all(r['bytes_unchanged'] for r in rows if r['merged']),
                  outcome='pass' if not misses and not false else 'fail')
    sys.stdout.write(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + '\n')
    return 0 if report['outcome'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
