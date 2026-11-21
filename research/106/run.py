#!/usr/bin/env python3
"""И-106: два целевых процесса, приёмка последовательности и read-only повтор печати."""
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
import run_iteration as sealing  # Только формат печати; ни одна проба донора не вызывается.
from render106 import page, report
from test_history import case_checks, encode, snapshot, timeline


def sources(root, names):
    data = {}
    for name in names:
        path = root / name
        if path.resolve() != path or not path.is_file():
            raise ValueError(f'Ожидался обычный вход: {name}')
        data[name] = path.read_bytes()
    return data


def measure(root, before):
    run = subprocess.run([sys.executable, '-B', '-I', '-S', '-X', 'utf8', 'research/106/test_history.py'],
                         cwd=root, capture_output=True, timeout=60)
    if run.stderr:
        sys.stderr.write(run.stderr.decode('utf-8', errors='replace'))
    try:
        observed = json.loads(run.stdout)
    except ValueError:
        observed = None
    return {'rc': run.returncode, 'result': observed, 'sources_unchanged': sources(root, before) == before,
            'inputs_sha256': {name: sha256(raw).hexdigest() for name, raw in before.items()}}


def clean_copy(initial):
    with tempfile.TemporaryDirectory(prefix='ack-i106-inputs-') as tmp:
        root = Path(tmp).resolve()
        for name, raw in initial.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        before = snapshot(root)
        measured = measure(root, sources(root, initial))
        after = snapshot(root)
        return {**measured, 'files_before': sorted(n for n, v in before.items() if v[0] != 'dir'),
                'files_after': sorted(n for n, v in after.items() if v[0] != 'dir'), 'copy_unchanged': before == after}


def load_cases(spec, raw):
    if sha256(raw).hexdigest() != spec['casebook_sha256']:
        raise ValueError('Ожидания отличаются от замороженного П2')
    casebook = json.loads(raw)
    cases = casebook['cases']
    expected = [row['expected']['ok'] for row in cases]
    if (encode(casebook['format']) != b'1' or not cases or len({c['id'] for c in cases}) != len(cases)
            or any(type(v) is not bool for v in expected)
            or {'positive': expected.count(True), 'negative': expected.count(False)} != spec['case_counts']):
        raise ValueError('Некорректные ожидания П2')
    return cases


def tally(rows):
    counts = Counter(row['status'] for row in rows)
    return {k: counts[k] for k in ('pass', 'fail', 'not run')}


def accept(spec, cases, checkout, clean):
    gates, runs, series = [], {}, []

    def gate(name, ok, basis, criterion):
        gates.append({'check': name, 'status': 'pass' if ok else 'fail', 'basis': basis, 'criterion': criterion})

    gate('frozen_cases', True, 'DESIGN.md; CASES.json; ITERATION.json', 'Список П2, его SHA-256, ID и количества совпали.')
    for key, evidence, name in (('checkout', checkout, 'CHECKOUT.json'), ('cleanroom', clean, 'CLEANROOM.json')):
        checks = case_checks(cases, evidence['result'])
        complete = all(r['status'] == 'pass' for r in checks)
        runs[key] = {'cases': checks, 'counts': tally(checks), 'rc': evidence['rc']}
        gate(key, complete and evidence['rc'] == 0, name + '; CASES.json',
             'Каждый обязательный ID ровно один раз, тип, исход, затронутый путь и диагноз точны; пропуски не принимаются.')
        series.append(timeline(evidence['result']) if complete else None)
    gate('ten_with_history', series[0] is not None and series[0] == series[1], 'CHECKOUT.json; CLEANROOM.json: rows, last_profile',
         'Десять регистраций, 11 непрерывных точек и хешей L1, десять точных решений, неизменные L0/L2.'
         ' Повторы X03 и отказ замены не меняют десятое состояние.')
    gate('isolated', clean['files_before'] == clean['files_after'] == sorted(spec['target_inputs']) and clean['copy_unchanged'] is True,
         'ITERATION.json; CLEANROOM.json', 'Ровно названные неизменные файлы; нет Git, ISAI и ZIP 0.1.36.')
    gate('repeat', checkout['sources_unchanged'] is True and clean['sources_unchanged'] is True
         and checkout['inputs_sha256'] == clean['inputs_sha256'] and encode(checkout['result']) == encode(clean['result']),
         'CHECKOUT.json; CLEANROOM.json', 'Байты входов не менялись; оба результата совпали.')
    skipped = [dict(item, status='not run') for item in spec['not_run']]
    counts = tally(gates + skipped)
    passed = counts['fail'] == 0
    return {'iteration': 'И-106', 'outcome': 'accepted' if passed else 'rejected', 'checks': gates,
            'counts': counts, 'runs': runs, 'not_run': skipped, 'series': series[0] if passed else None,
            'host_os': checkout['result'].get('os') if type(checkout['result']) is dict else None}


def generate(spec):
    filenames = spec['target_inputs']
    if len(filenames) != len(set(filenames)) or any(sealing.repo_path(n) != ROOT / n for n in filenames):
        raise ValueError('Неканонический список входов')
    source = sources(ROOT, filenames)
    cases = load_cases(spec, source['research/106/CASES.json'])
    checkout, clean = measure(ROOT, source), clean_copy(source)
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
    sealing.emit({'outcome': result['outcome'], 'counts': result['counts'], 'runs': {k: v['counts'] for k, v in result['runs'].items()},
                  'series': result['series'], 'seal': seal, 'replay': replay['outcome']})
    return 0 if result['outcome'] == 'accepted' and replay['outcome'] == 'ok' else 1


def verify(spec):
    replay = sealing.replay_seal(spec, HERE)
    ok = replay['outcome'] == 'ok' and replay == sealing.read_json(HERE / 'REPLAY.json')
    if ok:
        expected = page(spec, sealing.read_json(HERE / 'ACCEPTANCE.json'), sealing.read_json(HERE / 'SEAL.json'), replay)
        ok = (HERE / sealing.page_name(spec)).read_bytes() == expected.encode('utf-8')
    sealing.emit({**replay, 'record_and_page_match': ok})
    return 0 if ok else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-seal', action='store_true', help='Сверить сохранённый ZIP и страницу без записи')
    args = parser.parse_args()
    try:
        spec = sealing.read_json(HERE / 'ITERATION.json')
        return verify(spec) if args.verify_seal else generate(spec)
    except (KeyError, OSError, TypeError, ValueError, subprocess.TimeoutExpired) as error:
        sealing.emit({'error': 'run_error', 'reason': str(error)})
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
