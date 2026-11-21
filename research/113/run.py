#!/usr/bin/env python3
"""И-113: независимые проверки, приёмка, воспроизводимый ZIP и страница."""
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
PREFIX = 'research/113/'
BOOK, PROBE = PREFIX + 'CASES.json', PREFIX + 'test_specificity.py'
sys.dont_write_bytecode = True
sys.path[:0] = [str(HERE), str(ROOT / 'research/strategy/harness')]
import run_iteration as seal_io
from render113 import report, page
from test_specificity import CODES, MODULE, canonical, expected_observation

TARGETS = sorted([BOOK, PROBE, MODULE, 'kit/base/PROJECT-SPECIFICITY.md', 'kit/base/schema_v2.py', 'kit/base/SCHEMA-V2.md'])
SEALED_OUTPUTS = ('CHECKOUT', 'CLEANROOM', 'ACCEPTANCE', 'CLASSIFICATION')
KINDS = {'contract', 'rule', 'constraint', 'protocol', 'preference'}


def get(name):
    return seal_io.read_json(HERE / (name + '.json'))


def sources(root, names):
    files = {}
    for n in names:
        path = root / n
        if path.resolve() != path or not path.is_file():
            raise ValueError('ordinary_input_required')
        files[n] = path.read_bytes()
    return files


def digests(files):
    return {n: sha256(raw).hexdigest() for n, raw in files.items()}


def load():
    spec = get('ITERATION')
    filenames = [*TARGETS, *[PREFIX + name + '.json' for name in SEALED_OUTPUTS],
                 *[PREFIX + n for n in ('DESIGN.md', 'ITERATION.json', 'RED.json', 'REPORT.md', 'run.py', 'render113.py')],
                 'research/STRATEGY.md', 'research/strategy/SYNC-LOG.md',
                 *['research/strategy/harness/' + n for n in ('render.py', 'run_iteration.py', 'probes.py')]]
    if (spec['id'] != '113' or spec['command'] != ['-B', '-I', '-S', '-X', 'utf8', PROBE]
            or spec['target_inputs'] != TARGETS or spec['seal_members'] != sorted(filenames)
            or any(seal_io.repo_path(n) != ROOT / n for n in filenames)):
        raise ValueError('spec_inputs')
    inputs = sources(ROOT, TARGETS)
    hashes = digests(inputs)
    if hashes[BOOK] != spec['casebook_sha256'] or hashes[PROBE] != spec['test_sha256']:
        raise ValueError('frozen_input_drift')
    book = json.loads(inputs[BOOK])
    ids = [c['id'] for c in book['cases']]
    if canonical(book['format']) != b'1' or ids != spec['case_ids'] or len(ids) != len(set(ids)):
        raise ValueError('case_ids')
    return spec, book, get('RED'), inputs


def measure(root, spec, inputs):
    before = sources(root, inputs)
    if before != inputs:
        raise ValueError('different_input_bytes')
    p = subprocess.run([sys.executable, *spec['command']], cwd=root, capture_output=True, timeout=45)
    try:
        result = json.loads(p.stdout)
    except ValueError:
        result = None
    return {'rc': p.returncode, 'stderr_empty': not p.stderr, 'result': result,
            'inputs_sha256': digests(before), 'inputs_unchanged': sources(root, inputs) == before}


def snapshot(root):
    return {p.relative_to(root).as_posix(): (p.lstat().st_mode, p.lstat().st_ino, p.lstat().st_mtime_ns)
            for p in root.rglob('*')}


def clean_copy(spec, inputs):
    with tempfile.TemporaryDirectory(prefix='ack-i113-inputs-') as tmp:
        root = Path(tmp).resolve()
        for name, raw in inputs.items():
            p = root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(raw)
        before = snapshot(root)
        evidence = measure(root, spec, inputs)
        return dict(evidence, files=sorted(n for n in before if (root / n).is_file()), tree_unchanged=snapshot(root) == before)


def tally(rows):
    counts = Counter(c['status'] for c in rows)
    return {k: counts[k] for k in ('pass', 'fail', 'not run')}


def red_gate(spec, red):
    before = red['result']
    return (red['independent_baseline_match'] is True and canonical(red['rc']) == b'1'
            and all(red[k] == spec[k] for k in ('baseline', 'command', 'casebook_sha256', 'test_sha256'))
            and canonical(before['baseline']) == canonical({'missing': MODULE, 'control': 'S01', 'schema_accepted': True,
                                                           'unchanged': True, 'exception': False, 'io_events': 0, 'quiet': True})
            and before['rows'] == [{'id': n, 'status': 'fail', 'reason': 'detector_missing'} for n in spec['case_ids']]
            and before['counts'] == {'pass': 0, 'fail': len(spec['case_ids']), 'not run': 0})


def validate_run(spec, book, evidence):
    data = evidence['result']
    rows = (data.get('rows') if type(data) is dict else None) or []
    lookup = {}
    for row in rows:
        lookup.setdefault(row['id'], []).append(row)
    checks = []
    for c in book['cases']:
        pair = lookup.get(c['id'], [])
        wanted = {'id': c['id'], 'status': 'pass', 'observation': expected_observation(c)}
        status = 'not run' if not pair else 'pass' if len(pair) == 1 and canonical(pair[0]) == canonical(wanted) else 'fail'
        checks.append({'id': c['id'], 'basis': c['basis'], 'criterion': c['criterion'], 'status': status})
    counts = tally(checks)
    ok = (canonical(evidence['rc']) == b'0' and evidence['stderr_empty'] is True and type(data) is dict
          and canonical(data.get('format')) == b'1' and 'baseline' in data and data['baseline'] is None
          and spec['case_ids'] == [r['id'] for r in rows] and canonical(data['counts']) == canonical(counts)
          and counts == {'pass': len(checks), 'fail': 0, 'not run': 0})
    return ok, {'rc': evidence['rc'], 'counts': counts, 'cases': checks}


def summary(book, evidence):
    rows = {r['id']: r['observation'] for r in evidence['result']['rows']}
    data = [{**{k: c[k] for k in ('id', 'kind', 'basis', 'criterion')}, **rows[c['id']]['classification']} for c in book['cases']]
    counts = Counter(r['outcome'] for r in data)
    metrics = {'cases': len(data), 'valid_entries': len(data) - counts['invalid_input'], 'outcomes': dict(counts),
               'kinds': sorted({r['kind'] for r in data if r['outcome'] != 'invalid_input'}),
               'categories': sorted({f['category'] for r in data for f in r['findings']}),
               'calls': sum(r['calls'] for r in rows.values()), 'io_events': sum(r['io_events'] for r in rows.values()),
               'unchanged_all': all(r['inputs_unchanged'] for r in rows.values()),
               'quiet_safe_all': all(r['quiet'] and r['safe_shape'] for r in rows.values())}
    return {'iteration': 'И-113', 'source': 'CHECKOUT.json; подтверждено CLEANROOM.json', 'metrics': metrics, 'rows': data}


def accept(spec, book, red, inputs, checkout, clean):
    gates, runs = [], {}

    def gate(name, passed, basis, criterion):
        gates.append({'check': name, 'status': 'pass' if passed else 'fail', 'basis': basis, 'criterion': criterion})

    gate('frozen_red', red_gate(spec, red), 'DESIGN.md; CASES.json; ITERATION.json; RED.json',
         'Хеши замысла П2 совпадают; исходная схема принимала S01 как форму L2, детектора ещё не было. Повтор из базового коммита идентичен.')
    ready = []
    for key, evidence, path in [('checkout', checkout, 'CHECKOUT.json'), ('cleanroom', clean, 'CLEANROOM.json')]:
        ok, runs[key] = validate_run(spec, book, evidence)
        ready.append(ok)
        gate(key, ok, path + '; CASES.json', 'Каждый обязательный ID ровно один раз; rc0, точная классификация, коды и протокол отсутствия эффектов.')
    data = summary(book, checkout) if all(ready) else None
    m = data['metrics'] if data else {}
    rules = {(f['category'], f['code']) for r in data['rows'] for f in r['findings']} if data else set()
    gate('taxonomy', bool(m) and m['valid_entries'] >= 8 and set(m['kinds']) == KINDS
         and rules == {(c, rule) for c in CODES for rule in CODES[c]},
         'PROJECT-SPECIFICITY.md; CASES.json; CLASSIFICATION.json',
         'Не менее 8 верно размеченных валидных записей; все пять видов v2, четыре категории и все заявленные коды признаков.')
    gate('no_io_or_echo', bool(m) and m['calls'] == 2 * len(book['cases']) and m['io_events'] == 0
         and m['unchanged_all'] is True and m['quiet_safe_all'] is True,
         'test_specificity.py; CHECKOUT.json; CLEANROOM.json',
         'Основной и переставленный контексты: чистые коды, никаких вывода значений, доступа к среде/ФС/сети и изменения входов.')
    gate('isolation', clean['files'] == TARGETS and clean['tree_unchanged'] is True,
         'ITERATION.json; CLEANROOM.json', 'Новый каталог из ровно шести входов; без Git, донора, реестров и ISAI; копия неизменна.')
    gate('repeat', all(ready) and checkout['inputs_unchanged'] is True and clean['inputs_unchanged'] is True
         and checkout['inputs_sha256'] == clean['inputs_sha256'] == digests(inputs)
         and canonical(checkout['result']) == canonical(clean['result']),
         'CHECKOUT.json; CLEANROOM.json', 'Хеши входов, коды, порядок и наблюдения совпали в двух изолированных процессах.')
    skipped = [dict(row, status='not run') for row in spec['not_run']]
    counts = tally(gates + skipped)
    observed = checkout['result'] or {}
    result = {'iteration': 'И-113', 'outcome': 'accepted' if not counts['fail'] else 'rejected', 'counts': counts,
              'checks': gates, 'runs': runs, 'not_run': skipped, 'os': observed.get('os'), 'python': observed.get('python'),
              'scope': 'П5 · синтетический корпус детектора, не перенос; П9 проверяется отдельно по Git'}
    return result, data if not counts['fail'] else {'iteration': 'И-113', 'metrics': None, 'rows': None}


def generate(spec, book, red, inputs, *, measure_only):
    checkout, clean = measure(ROOT, spec, inputs), clean_copy(spec, inputs)
    accepted, data = accept(spec, book, red, inputs, checkout, clean)
    for name, value in zip(SEALED_OUTPUTS, (checkout, clean, accepted, data)):
        seal_io.dump_json(HERE / (name + '.json'), value)
    (HERE / 'REPORT.md').write_text(report(spec, red, accepted, data), encoding='utf-8', newline='\n')
    info = {'outcome': accepted['outcome'], 'counts': accepted['counts'], 'metrics': data['metrics'],
            'runs': {k: v['counts'] for k, v in accepted['runs'].items()}}
    if measure_only or accepted['outcome'] != 'accepted':
        seal_io.emit(info)
        return int(accepted['outcome'] != 'accepted')
    archive, seal = seal_io.seal_bytes(spec)
    (HERE / seal['file']).write_bytes(archive)
    seal_io.dump_json(HERE / 'SEAL.json', seal)
    replay = seal_io.replay_seal(spec, HERE)
    seal_io.dump_json(HERE / 'REPLAY.json', replay)
    (HERE / seal_io.page_name(spec)).write_text(page(spec, accepted, data, seal, replay), encoding='utf-8', newline='\n')
    seal_io.emit(dict(info, seal=seal, replay=replay['outcome']))
    return int(replay['outcome'] != 'ok')


def verify(spec, book, red, inputs):
    replay = seal_io.replay_seal(spec, HERE)
    accepted, data = accept(spec, book, red, inputs, get('CHECKOUT'), get('CLEANROOM'))
    ok = (replay['outcome'] == 'ok' and accepted['outcome'] == 'accepted' and canonical(replay) == canonical(get('REPLAY'))
          and canonical(accepted) == canonical(get('ACCEPTANCE')) and canonical(data) == canonical(get('CLASSIFICATION'))
          and (HERE / 'REPORT.md').read_bytes() == report(spec, red, accepted, data).encode('utf-8')
          and (HERE / seal_io.page_name(spec)).read_bytes() == page(spec, accepted, data, get('SEAL'), replay).encode('utf-8'))
    seal_io.emit(dict(replay, record_and_page_match=ok))
    return int(not ok)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--measure-only', action='store_true', help='П3–П6 без печати')
    modes.add_argument('--verify-seal', action='store_true', help='Проверка архива и страницы без записи')
    args = parser.parse_args()
    try:
        params = load()
        return verify(*params) if args.verify_seal else generate(*params, measure_only=args.measure_only)
    except (AttributeError, IndexError, KeyError, OSError, TypeError, ValueError, subprocess.TimeoutExpired) as error:
        seal_io.emit({'outcome': 'rejected', 'error': type(error).__name__})
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
