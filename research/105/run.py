#!/usr/bin/env python3
"""И-105: целевые П3–П5, отчёт, воспроизводимая печать и страница."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / 'research/strategy/harness'))
import run_iteration as sealing  # Только детерминированный ZIP и JSON-вывод, не прогоны донора.
from render105 import page, report
from test_layout import case_checks, encode, snapshot


def contents(root, filenames):
    source = {}
    for name in filenames:
        path = root / name
        if path.resolve() != path or not path.is_file():
            raise ValueError(f'Ожидался обычный входной файл: {name}')
        source[name] = path.read_bytes()
    return source


def probe(root, initial):
    process = subprocess.run([sys.executable, '-B', '-I', '-S', '-X', 'utf8', 'research/105/test_layout.py'],
                             cwd=root, capture_output=True, timeout=60)
    if process.stderr:
        sys.stderr.write(process.stderr.decode('utf-8', errors='replace'))
    try:
        result = json.loads(process.stdout)
    except ValueError:
        result = None
    return {'rc': process.returncode, 'result': result, 'sources_unchanged': contents(root, initial) == initial,
            'inputs_sha256': {name: sha256(raw).hexdigest() for name, raw in initial.items()}}


def clean_probe(initial):
    with tempfile.TemporaryDirectory(prefix='ack-i105-inputs-') as tmp:
        root = Path(tmp).resolve()
        for name, raw in initial.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        before = snapshot(root)
        result = probe(root, contents(root, initial))
        after = snapshot(root)
        return {**result, 'files_before': sorted(p for p in before if before[p][0] != 'dir'),
                'files_after': sorted(p for p in after if after[p][0] != 'dir'), 'whole_copy_unchanged': before == after}


def casebook(spec, raw):
    if sha256(raw).hexdigest() != spec['casebook_sha256']:
        raise ValueError('Обязательные ожидания отличаются от замороженного П2')
    data = json.loads(raw)
    cases = data['cases']
    expected = [row['expected']['ok'] for row in cases]
    if (encode(data['format']) != b'1' or not cases or len({c['id'] for c in cases}) != len(cases)
            or any(type(ok) is not bool for ok in expected)
            or {'positive': expected.count(True), 'negative': expected.count(False)} != spec['case_counts']):
        raise ValueError('Некорректные ожидания П2')
    return cases


def tally(rows):
    counts = Counter(row['status'] for row in rows)
    return {key: counts[key] for key in ('pass', 'fail', 'not run')}


def accept(spec, cases, checkout, clean):
    checks, runs = [], {}

    def gate(name, passed, basis, criterion):
        checks.append({'check': name, 'status': 'pass' if passed else 'fail', 'basis': basis, 'criterion': criterion})

    gate('frozen_cases', True, 'DESIGN.md; CASES.json; ITERATION.json',
         'SHA-256 списка П2 и количество обязательных положительных и отрицательных случаев точно совпали.')
    for key, evidence, filename in (('checkout', checkout, 'CHECKOUT.json'), ('cleanroom', clean, 'CLEANROOM.json')):
        by_case = case_checks(cases, evidence['result'])
        runs[key] = {'rc': evidence['rc'], 'counts': tally(by_case), 'cases': by_case}
        gate(key, evidence['rc'] == 0 and all(row['status'] == 'pass' for row in by_case),
             filename + '; CASES.json', 'Ровно один результат на каждый ID. Точные коды, пути, типы, статусы, '
             'списки правок и измерения деревьев; обязательный случай нельзя пропустить.')
    gate('clean_inputs', clean['files_before'] == clean['files_after'] == sorted(spec['target_inputs'])
         and clean['whole_copy_unchanged'] is True, 'ITERATION.json: target_inputs; CLEANROOM.json',
         'Чистая копия состоит только из входов, неизменна; нет ZIP донора, ISAI, Git или исследовательского харнесса.')
    gate('equal_and_unchanged', checkout['sources_unchanged'] is True and clean['sources_unchanged'] is True
         and checkout['inputs_sha256'] == clean['inputs_sha256'] and encode(checkout['result']) == encode(clean['result']),
         'CHECKOUT.json; CLEANROOM.json', 'Хеши источников идентичны; наблюдения на физических файлах совпали.')
    deferred = [dict(row, status='not run') for row in spec['not_run']]
    counts = tally(checks + deferred)
    passed = counts['fail'] == 0
    mutation = next(row for row in checkout['result']['rows'] if row['id'] == 'P02-create') if passed else None
    return {'iteration': 'И-105', 'phase': spec['phase'], 'outcome': 'accepted' if passed else 'rejected',
            'counts': counts, 'checks': checks, 'not_run': deferred, 'runs': runs,
            'host_os': checkout['result'].get('os') if type(checkout['result']) is dict else None, 'mutation': mutation}


def generate(spec):
    names = spec['target_inputs']
    if len(names) != len(set(names)) or any(sealing.repo_path(p) != ROOT / p for p in names):
        raise ValueError('Неканонический список входов')
    initial = contents(ROOT, names)
    cases = casebook(spec, initial['research/105/CASES.json'])
    checkout, clean = probe(ROOT, initial), clean_probe(initial)
    result = accept(spec, cases, checkout, clean)
    for name, data in (('CHECKOUT', checkout), ('CLEANROOM', clean), ('ACCEPTANCE', result)):
        sealing.dump_json(HERE / (name + '.json'), data)
    (HERE / 'REPORT.md').write_text(report(spec, cases, checkout, result), encoding='utf-8', newline='\n')
    raw, seal = sealing.seal_bytes(spec)
    (HERE / seal['file']).write_bytes(raw)
    sealing.dump_json(HERE / 'SEAL.json', seal)
    replay = sealing.replay_seal(spec, HERE)
    sealing.dump_json(HERE / 'REPLAY.json', replay)
    (HERE / sealing.page_name(spec)).write_text(page(spec, result, seal, replay), encoding='utf-8', newline='\n')
    sealing.emit({'outcome': result['outcome'], 'counts': result['counts'],
                  'runs': {k: r['counts'] for k, r in result['runs'].items()}, 'seal': seal, 'replay': replay['outcome']})
    return 0 if result['outcome'] == 'accepted' and replay['outcome'] == 'ok' else 1


def verify(spec):
    replay = sealing.replay_seal(spec, HERE)
    ok = replay['outcome'] == 'ok' and replay == sealing.read_json(HERE / 'REPLAY.json')
    if ok:
        html = page(spec, sealing.read_json(HERE / 'ACCEPTANCE.json'), sealing.read_json(HERE / 'SEAL.json'), replay)
        ok = (HERE / sealing.page_name(spec)).read_bytes() == html.encode('utf-8')
    sealing.emit({**replay, 'record_and_page_match': ok})
    return 0 if ok else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-seal', action='store_true', help='Проверить сохранённый архив и страницу без записи')
    args = parser.parse_args()
    try:
        spec = sealing.read_json(HERE / 'ITERATION.json')
        return verify(spec) if args.verify_seal else generate(spec)
    except (KeyError, OSError, TypeError, ValueError, subprocess.TimeoutExpired) as error:
        sealing.emit({'error': 'run_error', 'reason': str(error)})
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
