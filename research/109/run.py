#!/usr/bin/env python3
"""И-109: обязательные пробы карточного плана, две копии, итоговая печать."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PROBE = 'research/109/test_plan.py'
CASEBOOK = 'research/109/CASES.json'
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / 'research/strategy/harness'))
import run_iteration as sealing  # Только печать, не запуск 0.1.36.
from render109 import page, report
from test_plan import case_checks, encode, snapshot


def sources(root, names):
    data = {}
    for name in names:
        file = root / name
        if file.resolve() != file or not file.is_file():
            raise ValueError('Ожидался обычный вход: ' + name)
        data[name] = file.read_bytes()
    return data


def measure(root, inputs):
    result = subprocess.run([sys.executable, '-B', '-I', '-S', '-X', 'utf8', PROBE], cwd=root,
                            capture_output=True, timeout=60)
    if result.stderr:
        sys.stderr.write(result.stderr.decode('utf-8', errors='replace'))
    try:
        evidence = json.loads(result.stdout)
    except ValueError:
        evidence = None
    return {'rc': result.returncode, 'result': evidence, 'sources_unchanged': sources(root, inputs) == inputs,
            'inputs_sha256': {k: sha256(raw).hexdigest() for k, raw in inputs.items()}}


def clean_copy(inputs):
    with tempfile.TemporaryDirectory(prefix='ack-i109-inputs-') as tmp:
        root = Path(tmp).resolve()
        for name, raw in inputs.items():
            dst = root / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(raw)
        before = snapshot(root)
        result = measure(root, sources(root, inputs))
        after = snapshot(root)
        files = lambda data: sorted(n for n, obj in data.items() if obj[0] != 'dir')
        return {**result, 'files_before': files(before), 'files_after': files(after), 'copy_unchanged': before == after}


def load_cases(spec, inputs):
    if (sha256(inputs[CASEBOOK]).hexdigest() != spec['casebook_sha256']
            or sha256(inputs[PROBE]).hexdigest() != spec['test_sha256']):
        raise ValueError('Фикстуры или тест отличаются от замороженного П2')
    book = json.loads(inputs[CASEBOOK]); cases = book['cases']
    values = [r['expected']['ok'] for r in cases]
    counts = {'positive': values.count(True), 'negative': values.count(False)}
    if (encode(book['format']) != b'1' or not cases or len({r['id'] for r in cases}) != len(cases)
            or any(type(v) is not bool for v in values) or encode(counts) != encode(spec['case_counts'])):
        raise ValueError('Не совпадает обязательный корпус П2')
    return cases


def tally(rows):
    counts = Counter(row['status'] for row in rows)
    return {key: counts[key] for key in ('pass', 'fail', 'not run')}


def valid_witness(result):
    try:
        row = next(r for r in result['rows'] if r['id'] == 'P01-dry-run')
        p = row['preview']; diff = p['diff']; file = diff['file']; sig = re.compile(r'[a-f0-9]{64}')
        return (p.keys() == {'plan_format', 'outcome', 'dry_run', 'card', 'inputs_sha256', 'diff'}
                and encode(p['plan_format']) == b'1' and p['outcome'] == 'planned' and p['dry_run'] is True
                and diff.keys() == {'file', 'revision', 'before_sha256', 'after_sha256', 'unified'}
                and file == 'profiles/pilot/registry.json' and diff['revision'] == {'from': 4, 'to': 5}
                and p['inputs_sha256'].keys() == {'L0', 'L1', 'L2'} and diff['before_sha256'] == p['inputs_sha256']['L1']
                and diff['before_sha256'] != diff['after_sha256']
                and all(sig.fullmatch(h) for h in (*p['inputs_sha256'].values(), diff['after_sha256']))
                and diff['unified'].startswith(f'--- a/{file}\n+++ b/{file}\n')
                and '\\ No newline at end of file\n' in diff['unified'] and 'Q-109' in diff['unified'])
    except (AttributeError, TypeError, KeyError, StopIteration):
        return False


def accept(spec, cases, checkout, clean):
    gates, runs = [], {}

    def gate(name, ok, basis, criterion):
        gates.append({'check': name, 'status': 'pass' if ok else 'fail', 'basis': basis, 'criterion': criterion})

    gate('frozen_cases', True, 'DESIGN.md; CASES.json; test_plan.py; ITERATION.json',
         'Два SHA-256 П2 и список обязательных случаев совпали; критерии не извлекаются из продукта.')
    for key, evidence, file in (('checkout', checkout, 'CHECKOUT.json'), ('cleanroom', clean, 'CLEANROOM.json')):
        rows = case_checks(cases, evidence['result'])
        counts = tally(rows)
        runs[key] = {'counts': counts, 'rc': evidence['rc'], 'cases': rows}
        gate(key, encode(evidence['rc']) == b'0' and counts == {'pass': len(cases), 'fail': 0, 'not run': 0},
             file + '; CASES.json', 'Каждый ID исполнен один раз, точны результат, код/путь/основание и типы. '
             'До допуска к записи нет аудируемых попыток; смена байтов совпадает с ожидаемыми путями и заменами.')
    gate('preview_witness', all(valid_witness(r['result']) for r in (checkout, clean)),
         'CHECKOUT.json; CLEANROOM.json: P01-dry-run; P02-confirmed',
         'Опубликован точный дифф с хешами и ревизиями, без живого билета. Запись проверена по подготовленным байтам.')
    gate('isolated', clean['files_before'] == clean['files_after'] == sorted(spec['target_inputs'])
         and clean['copy_unchanged'] is True, 'ITERATION.json; CLEANROOM.json',
         'Ровно указанные неизменные входы без донорских данных, Git и ISAI.')
    gate('repeat', checkout['sources_unchanged'] is True and clean['sources_unchanged'] is True
         and checkout['inputs_sha256'] == clean['inputs_sha256'] and encode(checkout['result']) == encode(clean['result']),
         'CHECKOUT.json; CLEANROOM.json', 'Результаты независимых процессов совпали без публикации случайных билетов.')
    skipped = [dict(r, status='not run') for r in spec['not_run']]
    counts = tally(gates + skipped)
    return {'iteration': 'И-109', 'outcome': 'rejected' if counts['fail'] else 'accepted', 'counts': counts,
            'checks': gates, 'runs': runs, 'not_run': skipped,
            'host_os': checkout['result'].get('os') if type(checkout['result']) is dict else None}


def plan_result(checkout, acceptance):
    result = {'iteration': 'И-109', 'source': 'CHECKOUT.json: P01-dry-run', 'preview': None, 'metrics': None}
    if acceptance['outcome'] != 'accepted':
        return result
    rows = {r['id']: r for r in checkout['result']['rows']}
    observations = {i: row['observed'] for i, row in rows.items()}
    result.update(preview=rows['P01-dry-run']['preview'], ticket_redacted=True, metrics={
        'applied_cases': [i for i, obs in observations.items() if obs.get('outcome') == 'applied'],
        'writes_without_confirmation': sum(bool(o['changed']) for o in observations.values() if o.get('outcome') != 'applied'),
        'refused_before_write': sum(not o['ok'] and not o['write_event'] for o in observations.values()),
        'failed_replacements': sum(not o['ok'] and o['replacements'] for o in observations.values()),
    })
    return result


def replay(spec):
    recorded = sealing.read_json(HERE / 'SEAL.json')
    raw, rebuilt = sealing.seal_bytes(spec)
    archive = (HERE / sealing.seal_name(spec)).read_bytes()
    return {'outcome': 'ok' if encode(recorded) == encode(rebuilt) and raw == archive else 'mismatch',
            'recorded_sha256': recorded.get('sha256') if type(recorded) is dict else None,
            'rebuilt_sha256': rebuilt['sha256'], 'archive_sha256': sha256(archive).hexdigest()}


def generate(spec, *, measure_only):
    inputs = sources(ROOT, spec['target_inputs'])
    cases = load_cases(spec, inputs)
    checkout, clean = measure(ROOT, inputs), clean_copy(inputs)
    acceptance = accept(spec, cases, checkout, clean)
    data = plan_result(checkout, acceptance)
    for name, value in (('CHECKOUT', checkout), ('CLEANROOM', clean), ('ACCEPTANCE', acceptance), ('PLAN', data)):
        sealing.dump_json(HERE / (name + '.json'), value)
    (HERE / 'REPORT.md').write_text(report(spec, cases, checkout, acceptance, data), encoding='utf-8', newline='\n')
    summary = {'outcome': acceptance['outcome'], 'counts': acceptance['counts'], 'metrics': data['metrics'],
               'runs': {k: r['counts'] for k, r in acceptance['runs'].items()}}
    if acceptance['outcome'] != 'accepted' or measure_only:
        sealing.emit(summary)
        return 0 if acceptance['outcome'] == 'accepted' else 1
    raw, seal = sealing.seal_bytes(spec)
    (HERE / seal['file']).write_bytes(raw)
    sealing.dump_json(HERE / 'SEAL.json', seal)
    repeated = replay(spec)
    sealing.dump_json(HERE / 'REPLAY.json', repeated)
    (HERE / sealing.page_name(spec)).write_text(page(spec, acceptance, data, seal, repeated), encoding='utf-8', newline='\n')
    sealing.emit({**summary, 'seal': seal, 'replay': repeated['outcome']})
    return 0 if repeated['outcome'] == 'ok' else 1


def verify(spec):
    repeated = replay(spec)
    accepted = sealing.read_json(HERE / 'ACCEPTANCE.json')
    ok = (repeated['outcome'] == 'ok' and accepted['outcome'] == 'accepted'
          and encode(repeated) == encode(sealing.read_json(HERE / 'REPLAY.json')))
    if ok:
        expected = page(spec, accepted, sealing.read_json(HERE / 'PLAN.json'), sealing.read_json(HERE / 'SEAL.json'), repeated)
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
    excluded = {'research/109/' + n for n in ('SEAL.json', 'REPLAY.json', sealing.seal_name(spec), sealing.page_name(spec))}
    members, inputs = set(spec['seal_members']), set(spec['target_inputs'])
    if not {CASEBOOK, PROBE} <= inputs <= members or members & excluded:
        raise ValueError('Входы П7 неполны или включают результат самой печати')
    return spec


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    options = parser.add_mutually_exclusive_group()
    options.add_argument('--measure-only', action='store_true', help='П3–П6 без печати и страницы')
    options.add_argument('--verify-seal', action='store_true', help='Повтор печати без записи')
    args = parser.parse_args()
    try:
        spec = read_spec()
        return verify(spec) if args.verify_seal else generate(spec, measure_only=args.measure_only)
    except (KeyError, OSError, TypeError, ValueError, subprocess.TimeoutExpired) as error:
        sealing.emit({'error': 'run_error', 'reason': str(error)})
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
