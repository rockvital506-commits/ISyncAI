#!/usr/bin/env python3
"""И-048: корпуса через опубликованную команду, а не импортом.

Каждая пара — отдельный проект: установка и подключение входа делаются один раз в «семени», дальше
проект копируется. Оба наблюдения пары записываются отдельными процессами через `contract.py`;
после склейки файл проверок обязан остаться байт в байт.

Наборы: punct (12 пар И-030), corpus80 (80 пар И-029), corpus112 (112 пар И-020/И-024).

Запуск: python3 pairs_cli.py --tree ../release-0.1.28/base/AgentContractLab --line base --set punct
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).absolute().parent


def _input(name, fallback):
    local = HERE / name
    return local if local.is_file() else fallback


CORPUS_DIR = HERE if (HERE / 'corpus.py').is_file() else HERE.parent / '020'
sys.path.insert(0, str(CORPUS_DIR))
import corpus  # noqa: E402

PACK_VERSION = '0.1.28'
SETS = {
    'punct': _input('pairs-030-corpus.json', HERE.parent / '030/pairs-030-corpus.json'),
    'corpus80': _input('pairs-029-corpus.json', HERE.parent / '030/pairs-029-corpus.json'),
}


def sha(path) -> str:
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def cli(lab, project, command, payload=None):
    proc = subprocess.run([sys.executable, '-I', '-B', str(lab / 'kit/tools/contract.py'),
                           '--lab', str(lab), '--project', project, command],
                          input=(json.dumps(payload).encode() if payload is not None else b''),
                          capture_output=True, cwd=str(lab))
    assert proc.stderr == b'', proc.stderr.decode()[-400:]
    return proc.returncode, json.loads(proc.stdout.decode())


def install_seed(lab, project):
    pin = sha(lab / f'releases/{PACK_VERSION}/manifest.json')
    request = dict(op='install', package=f'releases/{PACK_VERSION}', pin=pin)
    rc, plan = cli(lab, project, 'plan', request)
    assert rc == 0, plan
    rc, out = cli(lab, project, 'apply', dict(request=request, ticket=plan['ticket']))
    assert rc == 0 and out['outcome'] == 'committed', out
    rc, plan = cli(lab, project, 'plan', dict(op='connect'))
    assert rc == 0, plan
    rc, out = cli(lab, project, 'apply', dict(request=dict(op='connect'), ticket=plan['ticket']))
    assert rc == 0 and out['outcome'] == 'committed', out


def write(lab, project, observation):
    observation = dict(observation)
    observation.setdefault('status', 'pass')
    rc, plan = cli(lab, project, 'plan', dict(op='record_check', observation=dict(observation)))
    assert rc == 0, plan
    if not plan['changes']:
        return 'no_change'
    rc, out = cli(lab, project, 'apply',
                  dict(request=dict(op='record_check', observation=dict(observation)), ticket=plan['ticket']))
    assert rc == 0, out
    return out['outcome']


def load_pairs(name):
    if name == 'corpus112':
        return [dict(kind=label, label=merge, left=left, right=right)
                for merge, label, left, right in corpus.pairs()]
    payload = json.loads(SETS[name].read_text(encoding='utf-8'))
    return payload['pairs']


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--tree', required=True)
    ap.add_argument('--line', default='base')
    ap.add_argument('--set', required=True, choices=sorted(SETS) + ['corpus112'])
    args = ap.parse_args()

    source = pathlib.Path(args.tree).absolute()
    root = pathlib.Path(tempfile.mkdtemp(prefix='cli-' + args.set + '-'))
    lab = root / 'AgentContractLab'
    shutil.copytree(source, lab)

    pairs = load_pairs(args.set)
    rows, missed, false = [], [], []
    for index, pair in enumerate(pairs):
        project = f'p{index:03d}'
        # копировать установленный проект нельзя: журнал операций привязан к абсолютному пути,
        # поэтому каждый проект устанавливается заново — тем же путём, что у владельца
        (lab / project).mkdir()
        (lab / project / 'demo.txt').write_text('синтетический вход\n', encoding='utf-8')
        install_seed(lab, project)
        left_outcome = write(lab, project, pair['left'])
        path = lab / project / '.agent-contract/project/checks.json'
        before = path.read_bytes()
        right_outcome = write(lab, project, pair['right'])
        after = path.read_bytes()
        total = len(json.loads(after.decode())['checks'])
        merged = total == 1
        row = dict(kind=pair['kind'], label=bool(pair['label']), merged=merged,
                   left=left_outcome, right=right_outcome, records=total,
                   bytes_unchanged=before == after if merged else True)
        rows.append(row)
        if pair['label'] and not merged:
            missed.append(pair['kind'])
        if not pair['label'] and merged:
            false.append(pair['kind'])

    kinds: dict[str, dict] = {}
    for row in rows:
        slot = kinds.setdefault(row['kind'], {'pairs': 0, 'label_merge': 0, 'merged': 0})
        slot['pairs'] += 1
        slot['label_merge'] += int(row['label'])
        slot['merged'] += int(row['merged'])
    # И-025 объявил две группы расхождений явно: варианты 1 и 2 — намеренно другие события,
    # «изменён файл свидетельства» — намеренно склеивается, потому что место улики выведено из
    # сравнения. Всё остальное — неожиданность.
    declared_missed = [n for n in missed if n.endswith(('вар1', 'вар2'))]
    declared_false = [n for n in false if n.endswith('изменён файл свидетельства')]
    unexpected = [n for n in missed if n not in declared_missed] + [n for n in false if n not in declared_false]
    outcome = 'pass' if not unexpected else 'fail'
    result = dict(iteration='И-048', line=args.line, set=args.set, at='2026-11-18',
                  pairs=len(rows), merges_labeled=sum(1 for r in rows if r['label']),
                  merged=sum(1 for r in rows if r['merged']),
                  missed_merges=missed, false_merges=false,
                  declared_missed=declared_missed, declared_false=declared_false,
                  unexpected=unexpected,
                  bytes_unchanged=all(r['bytes_unchanged'] for r in rows),
                  interface='опубликованная команда в отдельном процессе',
                  outcome=outcome, kinds=dict(sorted(kinds.items())), rows=rows)
    target = HERE / f'pairs-048-cli-{args.set}-{args.line}.json'
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
                      encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('set', 'line', 'pairs', 'merged', 'unexpected',
                                             'bytes_unchanged', 'outcome')},
                     ensure_ascii=False))
    shutil.rmtree(root, ignore_errors=True)
    return 0 if outcome == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
