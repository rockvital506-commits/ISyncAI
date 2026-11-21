#!/usr/bin/env python3
"""И-114: приёмка подготовки L1, воспроизводимая печать и страница."""
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
PREFIX = 'research/114/'
BOOK, PROBE = PREFIX + 'CASES.json', PREFIX + 'test_promotion.py'
sys.dont_write_bytecode = True
sys.path[:0] = [str(HERE), str(ROOT / 'research/strategy/harness')]
import run_iteration as seal_io
from render114 import page, report
from test_promotion import canonical, editable, entry_hash, expected_observation

TARGETS = sorted([BOOK, PROBE, *['kit/base/' + n for n in (
    'OPERATION-MATRIX.md', 'PROFILE-JOURNAL.md', 'PROJECT-SPECIFICITY.md', 'PROMOTION.md', 'REGISTRY-JOURNAL.md',
    'SCHEMA-V2.md', 'STORAGE-V2.md', 'profile_journal.py', 'project_specificity.py', 'promotion.py',
    'registry_journal.py', 'registry_policy.py', 'registry_store.py', 'schema_v2.py')]])
OUTPUTS = ('CHECKOUT', 'CLEANROOM', 'ACCEPTANCE', 'PROMOTION')
CONTROL = {'source_v2': True, 'staged_profile_v2': True, 'working_port': 'unknown_operation'}
KINDS = {'contract', 'rule', 'constraint', 'protocol', 'preference'}
COUNTS = ('pass', 'fail', 'not run')


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
    return {name: sha256(raw).hexdigest() for name, raw in files.items()}


def load():
    spec = get('ITERATION')
    seal_names = [*TARGETS, *[PREFIX + name + '.json' for name in OUTPUTS],
                  *[PREFIX + n for n in ('DESIGN.md', 'ITERATION.json', 'RED.json', 'REPORT.md', 'run.py', 'render114.py')],
                  'research/STRATEGY.md', 'research/strategy/SYNC-LOG.md',
                  *['research/strategy/harness/' + n for n in ('render.py', 'run_iteration.py', 'probes.py')]]
    if (spec['id'] != '114' or spec['command'] != ['-B', '-I', '-S', '-X', 'utf8', PROBE]
            or spec['target_inputs'] != TARGETS or spec['seal_members'] != sorted(seal_names)
            or any(seal_io.repo_path(n) != ROOT / n for n in seal_names)):
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
    return {p.relative_to(root).as_posix(): (s.st_mode, s.st_ino, s.st_mtime_ns)
            for p in root.rglob('*') for s in (p.lstat(),)}


def clean_copy(spec, inputs):
    with tempfile.TemporaryDirectory(prefix='ack-i114-inputs-') as tmp:
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
    return {key: counts[key] for key in COUNTS}


def red_gate(spec, red):
    data = red['result']
    return (red['independent_baseline_match'] is True and canonical(red['rc']) == b'1'
            and all(red[k] == spec[k] for k in ('baseline', 'command', 'casebook_sha256', 'test_sha256'))
            and canonical(data['format']) == b'1' and canonical(data['control']) == canonical(CONTROL)
            and data['rows'] == [{'id': n, 'status': 'fail', 'reason': 'promotion_missing'} for n in spec['case_ids']]
            and canonical(data['counts']) == canonical({'pass': 0, 'fail': len(spec['case_ids']), 'not run': 0}))


def validate_run(spec, book, evidence):
    data = evidence['result']
    rows = data.get('rows') if type(data) is dict else None
    lookup = {}
    if type(rows) is list:
        for row in rows:
            if type(row) is dict and type(row.get('id')) is str:
                lookup.setdefault(row['id'], []).append(row)
    checks = []
    for case in book['cases']:
        pair = lookup.get(case['id'], [])
        wanted = {'id': case['id'], 'status': 'pass', 'observation': expected_observation(case)}
        status = 'not run' if not pair else 'pass' if len(pair) == 1 and canonical(pair[0]) == canonical(wanted) else 'fail'
        checks.append({**{k: case[k] for k in ('id', 'basis', 'criterion')}, 'status': status})
    counts = tally(checks)
    ok = (canonical(evidence['rc']) == b'0' and evidence['stderr_empty'] is True and type(data) is dict
          and data.keys() == {'format', 'control', 'os', 'python', 'rows', 'counts'} and canonical(data['format']) == b'1'
          and canonical(data['control']) == canonical(CONTROL) and type(rows) is list
          and [r.get('id') if type(r) is dict else None for r in rows] == spec['case_ids']
          and canonical(data['counts']) == canonical(counts) and counts == {'pass': len(checks), 'fail': 0, 'not run': 0})
    return ok, {'rc': evidence['rc'], 'counts': counts, 'cases': checks}


def summary(book, evidence):
    observations = {r['id']: r['observation'] for r in evidence['result']['rows']}
    rows = []
    for case in book['cases']:
        row = {**{k: case[k] for k in ('id', 'kind', 'basis', 'criterion')}, **observations[case['id']]}
        if row['revision'] is not None:
            # В пробе этот независимый отпечаток уже совпал и с планом, и с прочитанным журналом.
            row['candidate_sha256'] = entry_hash(dict(editable(case['kind'], case['driver']), kind=case['kind'],
                                                      authority='profile_owner', state='draft'))
        rows.append(row)
    staged = [r for r in rows if r['other_validated'] == 1]
    refused = Counter(step.split(':', 1)[0] for r in rows for step in r['steps'] if ':' in step)
    metrics = {'cases': len(rows), 'staged': len(staged), 'validated_kinds': sorted({r['kind'] for r in staged}),
               'write_attempts': sum(r['write_attempts'] for r in rows), 'io_violations': sum(r['io_violations'] for r in rows),
               'cross_project_readbacks': sum(r['other_validated'] for r in rows),
               'protected_trees_unchanged_all': all(r['protected_trees_unchanged'] for r in rows),
               'inputs_unchanged_all': all(r['inputs_unchanged'] for r in rows), 'all_cleaned': all(r['stage_empty'] for r in rows),
               'refusals_by_code': dict(sorted(refused.items()))}
    return {'iteration': 'И-114', 'basis': 'CHECKOUT.json и CLEANROOM.json; отпечатки сверены с независимым оракулом test_promotion.py',
            'metrics': metrics, 'rows': rows}


def accept(spec, book, red, inputs, checkout, clean):
    gates, runs = [], {}

    def gate(name, passed, basis, criterion):
        gates.append({'check': name, 'status': 'pass' if passed else 'fail', 'basis': basis, 'criterion': criterion})

    gate('frozen_red', red_gate(spec, red), 'DESIGN.md; CASES.json; RED.json; ITERATION.json',
         'Совпали хеши заморозки П2 и исходный контроль формы; на базовом коммите нет реализации. Повтор RED побайтно тот же.')
    ready = []
    for key, evidence in [('checkout', checkout), ('cleanroom', clean)]:
        ok, runs[key] = validate_run(spec, book, evidence)
        ready.append(ok)
        gate(key, ok, f'{key.upper()}.json; CASES.json',
             'Каждый обязательный ID ровно один раз, rc0, точное совпадение исходов, кодов и счётчиков эффектов.')
    data = summary(book, checkout) if all(ready) else None
    m = data['metrics'] if data else {}
    rows = {r['id']: r for r in data['rows']} if data else {}
    gate('draft_and_journal', bool(m) and set(m['validated_kinds']) == KINDS and m['staged'] == m['cross_project_readbacks']
         and rows['P01']['revision'] == {'from': 3, 'to': 4} and rows['P07']['revision'] == {'from': 4, 'to': 5}
         and {f['category'] for f in rows['P01']['findings']} == {'path', 'machine', 'project_name', 'secret'},
         'PROMOTION.json; P01–P07, R09; test_promotion.py: expected_file, stage_with',
         'Исправленный черновик и одно решение с тем же отпечатком читаются в отдельном проекте, пять видов v2; существующая история сохранена.')
    gate('refusals', bool(m) and {'promote_unverified', 'project_specific', 'promote_conflict', 'parent'} <= m['refusals_by_code'].keys(),
         'CASES.json: R01–R10, S01–S04, V01–V12; PROMOTION.json',
         'Обязательные коды до записи; на подмену плана, просроченное или недостающее согласие нет файловых эффектов.')
    gate('stand_only', bool(m) and m['write_attempts'] == m['staged'] + 1 and m['io_violations'] == 0
         and m['protected_trees_unchanged_all'] and m['inputs_unchanged_all'] and m['all_cleaned'],
         'test_promotion.py: Monitor; CHECKOUT.json; CLEANROOM.json; V12',
         'Исключительное создание только во временном каталоге после согласия; одна инъекция отказа, ноль иных эффектов или изменений защищённых копий.')
    gate('isolation', clean['files'] == TARGETS and clean['tree_unchanged'] is True,
         'CLEANROOM.json; ITERATION.json', 'Чистая копия ровно заявленных входов; нет Git, донора, ISAI или подготовленных реальных профилей.')
    gate('repeat', all(ready) and checkout['inputs_unchanged'] is True and clean['inputs_unchanged'] is True
         and checkout['inputs_sha256'] == clean['inputs_sha256'] == digests(inputs)
         and canonical(checkout['result']) == canonical(clean['result']),
         'CHECKOUT.json; CLEANROOM.json', 'Те же байты входов, тот же полный протокол, в результаты не попадают временные пути, исходники и билеты.')
    skipped = [dict(row, status='not run') for row in spec['not_run']]
    counts = tally(gates + skipped)
    obs = checkout['result'] if type(checkout['result']) is dict else {}
    result = {'iteration': 'И-114', 'outcome': 'accepted' if not counts['fail'] else 'rejected', 'counts': counts,
              'checks': gates, 'runs': runs, 'not_run': skipped, 'os': obs.get('os'), 'python': obs.get('python'),
              'scope': 'П5 · запись только в синтетический стенд; не рабочий перенос; П9 проверяется отдельно по Git'}
    return result, data if not counts['fail'] else {'iteration': 'И-114', 'metrics': None, 'rows': None}


def generate(spec, book, red, inputs, *, measure_only):
    checkout, clean = measure(ROOT, spec, inputs), clean_copy(spec, inputs)
    accepted, data = accept(spec, book, red, inputs, checkout, clean)
    for name, value in zip(OUTPUTS, (checkout, clean, accepted, data)):
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
          and canonical(accepted) == canonical(get('ACCEPTANCE')) and canonical(data) == canonical(get('PROMOTION'))
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
