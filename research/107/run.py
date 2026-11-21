#!/usr/bin/env python3
"""И-107: целевые П3–П5, отчёт и воспроизводимая печать без запуска доноров."""
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
PROBE = 'research/107/test_policy.py'
CASEBOOK = 'research/107/CASES.json'
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / 'research/strategy/harness'))
import run_iteration as sealing  # Формат ZIP, не запуск evaluator донора.
from render107 import page, report
from test_policy import case_checks, encode, expected_matrix, matrix_matches, snapshot


def sources(root, names):
    result = {}
    for name in names:
        path = root / name
        if path.resolve() != path or not path.is_file():
            raise ValueError(f'Ожидался обычный файл: {name}')
        result[name] = path.read_bytes()
    return result


def measure(root, inputs):
    process = subprocess.run([sys.executable, '-B', '-I', '-S', '-X', 'utf8', PROBE], cwd=root,
                             capture_output=True, timeout=60)
    if process.stderr:
        sys.stderr.write(process.stderr.decode('utf-8', errors='replace'))
    try:
        observed = json.loads(process.stdout)
    except ValueError:
        observed = None
    return {'rc': process.returncode, 'result': observed, 'sources_unchanged': sources(root, inputs) == inputs,
            'inputs_sha256': {name: sha256(raw).hexdigest() for name, raw in inputs.items()}}


def clean_copy(inputs):
    with tempfile.TemporaryDirectory(prefix='ack-i107-inputs-') as tmp:
        root = Path(tmp).resolve()
        for name, raw in inputs.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        before = snapshot(root)
        evidence = measure(root, sources(root, inputs))
        after = snapshot(root)
        return {**evidence, 'files_before': sorted(n for n, v in before.items() if v[0] != 'dir'),
                'files_after': sorted(n for n, v in after.items() if v[0] != 'dir'), 'copy_unchanged': before == after}


def load_cases(spec, inputs):
    raw = inputs[CASEBOOK]
    if sha256(raw).hexdigest() != spec['casebook_sha256'] or sha256(inputs[PROBE]).hexdigest() != spec['test_sha256']:
        raise ValueError('Тест или ожидания отличаются от замороженного П2')
    book = json.loads(raw)
    cases = book['cases']
    expected = [r['expected']['ok'] for r in cases]
    matrix = expected_matrix(cases)
    counts = {'positive': expected.count(True), 'negative': expected.count(False),
              'matrix': sum(map(len, matrix.values()))}
    if (encode(book['format']) != b'1' or not cases or len({r['id'] for r in cases}) != len(cases)
            or any(type(v) is not bool for v in expected) or encode(counts) != encode(spec['case_counts'])
            or counts['matrix'] != sum('cell' in r for r in cases)
            or any(v.keys() != {'L0', 'L1', 'L2'} for v in matrix.values())):
        raise ValueError('Нарушена полнота списка П2')
    return cases


def tally(rows):
    totals = Counter(row['status'] for row in rows)
    return {status: totals[status] for status in ('pass', 'fail', 'not run')}


def accept(spec, cases, checkout, clean):
    gates, runs = [], {}

    def gate(name, ok, basis, criterion):
        gates.append({'check': name, 'status': 'pass' if ok else 'fail', 'basis': basis, 'criterion': criterion})

    gate('frozen_cases', True, 'DESIGN.md; CASES.json; test_policy.py; ITERATION.json',
         'Хеши замороженных ожиданий и теста, уникальность ID, количество случаев и полнота ячеек совпали.')
    for key, evidence, name in (('checkout', checkout, 'CHECKOUT.json'), ('cleanroom', clean, 'CLEANROOM.json')):
        checks = case_checks(cases, evidence['result'])
        counts = tally(checks)
        runs[key] = {'cases': checks, 'counts': counts, 'rc': evidence['rc']}
        gate(key, encode(evidence['rc']) == b'0' and counts == {'pass': len(cases), 'fail': 0, 'not run': 0},
             name + '; CASES.json', 'Все обязательные ID ровно один раз. Точные исход, причина, путь, тип, состав и байты.')
    table_ok = all(matrix_matches(cases, e['result']) for e in (checkout, clean))
    gate('operation_matrix', table_ok, 'CHECKOUT.json; CLEANROOM.json: result.matrix; CASES.json: cell',
         'Исполняемая матрица совпала со всеми независимыми ожиданиями: нет подмены available, planned и forbidden.')
    gate('isolated', clean['files_before'] == clean['files_after'] == sorted(spec['target_inputs'])
         and clean['copy_unchanged'] is True, 'ITERATION.json; CLEANROOM.json',
         'Только указанные входы; нет донора, ISAI, Git и остатков записи в копии.')
    gate('repeat', checkout['sources_unchanged'] is True and clean['sources_unchanged'] is True
         and checkout['inputs_sha256'] == clean['inputs_sha256'] and encode(checkout['result']) == encode(clean['result']),
         'CHECKOUT.json; CLEANROOM.json', 'Хеши исходных входов, матрица и все наблюдения двух процессов совпали.')
    skipped = [dict(item, status='not run') for item in spec['not_run']]
    counts = tally(gates + skipped)
    return {'iteration': 'И-107', 'outcome': 'rejected' if counts['fail'] else 'accepted', 'counts': counts,
            'checks': gates, 'runs': runs, 'not_run': skipped,
            'host_os': checkout['result'].get('os') if type(checkout['result']) is dict else None}


def matrix_result(checkout, accepted):
    matrix = checkout['result']['matrix'] if accepted['outcome'] == 'accepted' else None
    return {'iteration': 'И-107', 'source': 'kit/base/registry_policy.py:operation_matrix', 'matrix': matrix,
            'cells': dict(Counter(r['state'] for slots in matrix.values() for r in slots.values())) if matrix else {}}


def replay(spec):
    recorded = sealing.read_json(HERE / 'SEAL.json')
    raw, rebuilt = sealing.seal_bytes(spec)
    archived = (HERE / sealing.seal_name(spec)).read_bytes()
    return {'outcome': 'ok' if encode(recorded) == encode(rebuilt) and archived == raw else 'mismatch',
            'recorded_sha256': recorded.get('sha256') if type(recorded) is dict else None,
            'rebuilt_sha256': rebuilt['sha256'], 'archive_sha256': sha256(archived).hexdigest()}


def generate(spec, *, measure_only):
    inputs = sources(ROOT, spec['target_inputs'])
    cases = load_cases(spec, inputs)
    checkout, clean = measure(ROOT, inputs), clean_copy(inputs)
    result = accept(spec, cases, checkout, clean)
    matrix = matrix_result(checkout, result)
    for name, payload in (('CHECKOUT', checkout), ('CLEANROOM', clean), ('MATRIX', matrix), ('ACCEPTANCE', result)):
        sealing.dump_json(HERE / (name + '.json'), payload)
    (HERE / 'REPORT.md').write_text(report(spec, cases, checkout, result, matrix), encoding='utf-8', newline='\n')
    summary = {'outcome': result['outcome'], 'counts': result['counts'],
               'runs': {k: v['counts'] for k, v in result['runs'].items()}, 'cells': matrix['cells']}
    if result['outcome'] != 'accepted' or measure_only:
        sealing.emit(summary)
        return 1 if result['outcome'] == 'rejected' else 0
    raw, seal = sealing.seal_bytes(spec)
    (HERE / seal['file']).write_bytes(raw)
    sealing.dump_json(HERE / 'SEAL.json', seal)
    repeated = replay(spec)
    sealing.dump_json(HERE / 'REPLAY.json', repeated)
    (HERE / sealing.page_name(spec)).write_text(page(spec, result, matrix, seal, repeated), encoding='utf-8', newline='\n')
    sealing.emit({**summary, 'seal': seal, 'replay': repeated['outcome']})
    return 0 if repeated['outcome'] == 'ok' else 1


def verify(spec):
    repeated = replay(spec)
    accepted = sealing.read_json(HERE / 'ACCEPTANCE.json')
    ok = (repeated['outcome'] == 'ok' and accepted['outcome'] == 'accepted'
          and encode(repeated) == encode(sealing.read_json(HERE / 'REPLAY.json')))
    if ok:
        expected = page(spec, accepted, sealing.read_json(HERE / 'MATRIX.json'), sealing.read_json(HERE / 'SEAL.json'), repeated)
        ok = (HERE / sealing.page_name(spec)).read_bytes() == expected.encode('utf-8')
    sealing.emit({**repeated, 'record_and_page_match': ok})
    return 0 if ok else 1


def read_spec():
    spec = sealing.read_json(HERE / 'ITERATION.json')
    for field in ('target_inputs', 'seal_members'):
        names = spec[field]
        if (type(names) is not list or not names or sorted(set(names)) != names
                or any(Path(n).as_posix() != n or sealing.repo_path(n) != ROOT / n for n in names)):
            raise ValueError('Неканонический список: ' + field)
    members, inputs = set(spec['seal_members']), set(spec['target_inputs'])
    excluded = {'research/107/' + n for n in ('SEAL.json', 'REPLAY.json', sealing.seal_name(spec), sealing.page_name(spec))}
    if not {CASEBOOK, PROBE} <= inputs <= members or members & excluded:
        raise ValueError('Входы П7 неполны или включают результат самой печати')
    return spec


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--measure-only', action='store_true', help='П3–П6, без печати и страницы')
    group.add_argument('--verify-seal', action='store_true', help='Повтор П7–П8 без записи')
    args = parser.parse_args()
    try:
        spec = read_spec()
        return verify(spec) if args.verify_seal else generate(spec, measure_only=args.measure_only)
    except (KeyError, OSError, TypeError, ValueError, subprocess.TimeoutExpired) as error:
        sealing.emit({'error': 'run_error', 'reason': str(error)})
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
