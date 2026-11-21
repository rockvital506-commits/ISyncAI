#!/usr/bin/env python3
"""И-117: два прогона, синтетический продукт и отдельная воспроизводимая печать."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PREFIX = 'research/117/'
BOOK, PROBE = (PREFIX + n for n in ('CASES.json', 'test_bundle.py'))
SAMPLE = 'Synthetic-Bundle-117.zip'
sys.dont_write_bytecode = True
sys.path[:0] = [str(HERE), str(ROOT / 'research/strategy/harness')]
import run_iteration as seal_io
from render117 import page, report
from test_bundle import (PROFILE, SYSTEM, canonical, context, expected_observation, inspect_known_archive,
                         inspect_packet, payload)

PINNED = sorted('kit/base/' + n for n in (
    'entry.txt', 'START.md', 'SCHEMA-V2.md', 'STORAGE-V2.md', 'OPERATION-CARD.md', 'OPERATION-PLAN.md',
    'bootstrap.py', 'operation_card.py', 'operation_plan.py', 'profile_journal.py', 'registry_journal.py',
    'registry_policy.py', 'registry_store.py', 'schema_v2.py'))
TARGETS = sorted([BOOK, PROBE, *PINNED, 'kit/base/BUNDLE.md', 'kit/base/bundle.py'])
OUTPUTS = ('CHECKOUT', 'CLEANROOM', 'ACCEPTANCE', 'BUNDLE')
COUNTS = ('pass', 'fail', 'not run')


def get(name):
    return seal_io.read_json(HERE / (name + '.json'))


def inputs_from(root, names):
    files = {}
    for n in names:
        path = root / n
        if path.resolve() != path or not path.is_file():
            raise ValueError('ordinary_input_required')
        files[n] = path.read_bytes()
    return files


def digests(files):
    return {n: sha256(b).hexdigest() for n, b in files.items()}


def load():
    spec = get('ITERATION')
    members = [*TARGETS, *[PREFIX + n + '.json' for n in OUTPUTS],
               *[PREFIX + n for n in ('DESIGN.md', 'ITERATION.json', 'RED.json', 'REPORT.md', 'run.py', 'render117.py', SAMPLE)],
               'research/STRATEGY.md', 'research/strategy/SYNC-LOG.md',
               *['research/strategy/harness/' + n for n in ('run_iteration.py', 'render.py', 'probes.py')]]
    if (spec['id'] != '117' or spec['sample'] != SAMPLE or spec['command'] != ['-B', '-I', '-S', '-X', 'utf8', PROBE]
            or spec['target_inputs'] != TARGETS or spec['seal_members'] != sorted(members)
            or any(seal_io.repo_path(n) != ROOT / n for n in members)):
        raise ValueError('spec_inputs')
    inputs = inputs_from(ROOT, TARGETS)
    h = digests(inputs)
    if (h[BOOK] != spec['casebook_sha256'] or h[PROBE] != spec['test_sha256']
            or spec['pinned_inputs'] != {n: h[n] for n in PINNED}):
        raise ValueError('frozen_input_drift')
    book = json.loads(inputs[BOOK]); ids = [c['id'] for c in book['cases']]
    if (canonical(book['format']) != b'1' or book['baseline'] != spec['baseline']
            or book['required'] != sorted([*PINNED, SYSTEM, PROFILE])
            or ids != spec['case_ids'] or len(ids) != len(set(ids)) or len(ids) != 46
            or [c.get('path') for c in book['cases'] if c.get('inject') == 'missing'] != book['required']):
        raise ValueError('case_ids_or_required')
    return spec, book, context(book), get('RED'), inputs


def measure(root, spec, inputs):
    before = inputs_from(root, inputs)
    if before != inputs:
        raise ValueError('different_input_bytes')
    p = subprocess.run([sys.executable, *spec['command']], cwd=root, capture_output=True, timeout=45)
    try:
        data = json.loads(p.stdout)
    except ValueError:
        data = None
    return {'rc': p.returncode, 'stderr_empty': not p.stderr, 'result': data,
            'inputs_sha256': digests(before), 'inputs_unchanged': inputs_from(root, inputs) == before}


def snapshot(root):
    return {f.relative_to(root).as_posix(): (s.st_mode, s.st_ino, s.st_size, s.st_mtime_ns)
            for f in root.rglob('*') for s in (f.lstat(),)}


def clean_copy(spec, inputs):
    with TemporaryDirectory(prefix='ack-i117-inputs-') as folder:
        root = Path(folder).resolve()
        for n, data in inputs.items():
            p = root / n
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        before = snapshot(root)
        observed = measure(root, spec, inputs)
        return dict(observed, files=sorted(n for n in before if (root / n).is_file()), tree_unchanged=before == snapshot(root))


def tally(rows):
    got = Counter(r['status'] for r in rows)
    return {k: got[k] for k in COUNTS}


def expected_control():
    return {'required_files': 16, 'valid_layouts': 2, 'bare_revisions': [7, 0], 'valid_history_formats': [1, 2],
            'working_port': {'bundle': 'unknown_operation', 'bundle_verify': 'unknown_operation'}}


def header_matches(data):
    return (type(data) is dict and data.keys() == {'format', 'control', 'os', 'python', 'rows', 'counts'}
            and canonical(data['format']) == b'1' and canonical(data['control']) == canonical(expected_control())
            and all(type(data[k]) is str and data[k] for k in ('os', 'python')))


def red_gate(spec, red):
    data = red['result']; fix = red['fixture_correction']
    return (red['independent_baseline_match'] is True and canonical(red['rc']) == b'1'
            and all(spec[k] == red[k] for k in ('baseline', 'command', 'casebook_sha256', 'test_sha256', 'pinned_inputs'))
            and header_matches(data) and data['rows'] == [
                {'id': n, 'status': 'fail', 'reason': 'bundle_missing'} for n in spec['case_ids']]
            and canonical(data['counts']) == canonical({'pass': 0, 'fail': len(spec['case_ids']), 'not run': 0})
            and fix['case'] == 'P05' and fix['same_case_criteria_and_golden'] is True
            and fix['repeated_against_original_git_baseline'] is True
            and fix['reason'] == 'profile_json_member_order_after_casebook_serialization'
            and canonical(fix['first_green']) == canonical({'pass': 45, 'fail': 1, 'not run': 0, 'failed_id': 'P05'}))


def validate_run(spec, book, ctx, evidence):
    data = evidence['result']; rows = data.get('rows') if type(data) is dict else None
    seen = {}
    if type(rows) is list:
        for row in rows:
            if type(row) is dict and type(row.get('id')) is str:
                seen.setdefault(row['id'], []).append(row)
    checks = []
    for case in book['cases']:
        matches = seen.get(case['id'], [])
        wanted = {'id': case['id'], 'status': 'pass', 'observation': expected_observation(book, ctx, case)}
        status = 'not run' if not matches else 'pass' if len(matches) == 1 and canonical(matches[0]) == canonical(wanted) else 'fail'
        checks.append({**{k: case[k] for k in ('id', 'basis', 'criterion')}, 'status': status})
    counts = tally(checks)
    ok = (canonical(evidence['rc']) == b'0' and evidence['stderr_empty'] is True and header_matches(data)
          and type(rows) is list and [r.get('id') if type(r) is dict else None for r in rows] == spec['case_ids']
          and canonical(data['counts']) == canonical(counts) and counts == {'pass': len(checks), 'fail': 0, 'not run': 0})
    return ok, {'rc': evidence['rc'], 'counts': counts, 'cases': checks}


def summary(book, result):
    actual = {r['id']: r['observation'] for r in result['rows']}
    rows = [{**{k: c[k] for k in ('id', 'basis', 'criterion')}, **actual[c['id']]} for c in book['cases']]
    made = sum(r['package'] is not None for r in rows)
    metrics = {'cases': len(rows), 'bundled': made, 'refused': len(rows) - made,
               'missing_members_tested': sum(c.get('inject') == 'missing' for c in book['cases']),
               'refused_before_build': sum(r['error'] is not None and r['archive_attempts'] == 0 for r in rows),
               'archive_attempts': sum(r['archive_attempts'] for r in rows), 'member_attempts': sum(r['member_attempts'] for r in rows),
               'effect_attempts': sum(len(r['effects']) for r in rows),
               'inputs_unchanged_all': all(r['inputs_unchanged'] for r in rows), 'quiet_all': all(r['quiet'] for r in rows)}
    return {'iteration': 'И-117', 'basis': 'CHECKOUT.json; CLEANROOM.json; CASES.json: golden; P01',
            'reference': actual['P01']['package'], 'metrics': metrics, 'rows': rows}


def accept(spec, book, ctx, red, inputs, checkout, clean):
    checks, runs = [], {}

    def gate(name, ok, basis, criterion):
        checks.append({'check': name, 'status': 'pass' if ok else 'fail', 'basis': basis, 'criterion': criterion})

    gate('frozen_red', red_gate(spec, red), 'DESIGN.md; CASES.json; ITERATION.json; RED.json',
         'Исходный RED 0/46/0 до продукта; коррекция порядка полей P05 не меняла эталоны и критерии, тот же RED из базы.')
    ready = []
    for name, e in (('checkout', checkout), ('cleanroom', clean)):
        ok, runs[name] = validate_run(spec, book, ctx, e)
        ready.append(ok)
        gate(name, ok, f'{name.upper()}.json; CASES.json; test_bundle.py',
             'Ровно все ID в том же порядке, rc0: байты, манифесты, отказы и счётчики совпали с независимым оракулом.')
    data = summary(book, checkout['result']) if all(ready) else None
    m = data['metrics'] if data else {}
    rows = {r['id']: r for r in data['rows']} if data else {}
    ref = data['reference'] if data else {}
    package = {n: r['package'] for n, r in rows.items() if r['package'] is not None}
    gate('complete_package', bool(m) and m['bundled'] == 6 and ref['archive_members'] == 17
         and [r['path'] for r in ref['manifest']['files']] == book['required'] and package['P03']['manifest']['revision'] == 0
         and all(p['payload_exact'] and p['fixed_metadata'] and p['archive_sha256'] != p['manifest']['digest'] for p in package.values()),
         'P01–P06; CASES.json: golden; test_bundle.py: inspect_known_archive',
         '16 точных полезных членов и один манифест; пустой валидный L1 не ошибка, digest манифеста не SHA-256 ZIP.')
    gate('determinism_and_raw_bytes', bool(m) and package['P01'] == package['P02']
         and len({p['archive_sha256'] for p in package.values()}) == 5
         and len({p['manifest']['digest'] for p in package.values()}) == 5
         and [package[n]['manifest']['revision'] for n in ('P01', 'P04', 'P05', 'P06')] == [7, 7, 7, 8]
         and all([a['path'] for a, b in zip(ref['manifest']['files'], package[n]['manifest']['files']) if a != b] == [PROFILE]
                 for n in ('P04', 'P05', 'P06')),
         'P02/P04/P05/P06; golden; BUNDLE.json',
         'Перестановка ничего не меняет; изменение байтов меняет хеш даже при равной revision и при той же форме JSON.')
    gate('every_missing_member', bool(m) and m['missing_members_tested'] == 16
         and all(r['package'] is None and r['archive_attempts'] == 0 and r['member_attempts'] == 0
                 and r['error']['details']['reason'] == 'missing' for n, r in rows.items() if n.startswith('M')),
         'M01–M16; CASES.json; Monitor', 'Каждый пропуск отдельно даёт bundle_incomplete до ZIP, без частичного результата.')
    gate('source_boundaries', bool(m) and m['refused'] == 40 and m['refused_before_build'] == 39
         and all(rows[n]['error']['details']['reason'] == 'local_history' for n in ('N17', 'N18')),
         'N01–N20/N22–N24; контроль валидных журналов',
         'Вне разрешения: L2, история, чужие корни, пути, лимиты и неверные реестры; локальный валидный контейнер не экспортируется.')
    gate('no_effects_or_partial', bool(m) and m['effect_attempts'] == 0 and m['inputs_unchanged_all'] and m['quiet_all']
         and m['archive_attempts'] == 7 and m['member_attempts'] == 110
         and rows['N21']['package'] is None and rows['N21']['member_attempts'] == 8,
         'N21; Monitor; оба прогона', 'Поздняя ошибка не отдаёт буфер; побочного I/O и вывода нет, входы неизменны.')
    gate('isolation', clean['files'] == TARGETS and clean['tree_unchanged'] is True,
         'ITERATION.json; CLEANROOM.json', 'Свежая копия содержит только 18 входов; нет Git, донора, установки и рабочего профиля.')
    gate('repeat', all(ready) and checkout['inputs_unchanged'] is True and clean['inputs_unchanged'] is True
         and checkout['inputs_sha256'] == clean['inputs_sha256'] == digests(inputs)
         and canonical(checkout['result']) == canonical(clean['result']),
         'CHECKOUT.json; CLEANROOM.json', 'Одинаковые свидетельства и хеши входов в двух отдельных процессах.')
    deferred = [dict(r, status='not run') for r in spec['not_run']]
    counts = tally(checks + deferred)
    obs = checkout['result'] if type(checkout['result']) is dict else {}
    verdict = {'iteration': 'И-117', 'outcome': 'accepted' if not counts['fail'] else 'rejected', 'counts': counts,
               'checks': checks, 'runs': runs, 'not_run': deferred, 'os': obs.get('os'), 'python': obs.get('python'),
               'scope': 'П5 · сборка синтетического среза, не внешняя проверка, релиз, установка или доверие'}
    return verdict, data if not counts['fail'] else {'iteration': 'И-117', 'reference': None, 'metrics': None, 'rows': None}


def sample_bytes(book, ctx, reference):
    from kit.base.bundle import bundle
    packet = bundle(payload(book, ctx, 'populated'))
    if canonical(inspect_packet(book, ctx, 'populated', packet)) != canonical(reference):
        raise ValueError('sample_drift')
    return packet['archive']


def generate(spec, book, ctx, red, inputs, *, measure_only):
    checkout, clean = measure(ROOT, spec, inputs), clean_copy(spec, inputs)
    verdict, data = accept(spec, book, ctx, red, inputs, checkout, clean)
    emit_archive = not measure_only and verdict['outcome'] == 'accepted'
    sample = sample_bytes(book, ctx, data['reference']) if emit_archive else None
    for name, obj in zip(OUTPUTS, (checkout, clean, verdict, data)):
        seal_io.dump_json(HERE / (name + '.json'), obj)
    (HERE / 'REPORT.md').write_text(report(spec, red, verdict, data), encoding='utf-8', newline='\n')
    info = {'outcome': verdict['outcome'], 'counts': verdict['counts'], 'metrics': data['metrics'],
            'runs': {k: r['counts'] for k, r in verdict['runs'].items()}}
    if not emit_archive:
        seal_io.emit(info)
        return int(verdict['outcome'] != 'accepted')
    (HERE / SAMPLE).write_bytes(sample)
    raw, seal = seal_io.seal_bytes(spec)
    (HERE / seal['file']).write_bytes(raw)
    seal_io.dump_json(HERE / 'SEAL.json', seal)
    replay = seal_io.replay_seal(spec, HERE)
    seal_io.dump_json(HERE / 'REPLAY.json', replay)
    (HERE / seal_io.page_name(spec)).write_text(page(spec, verdict, data, seal, replay), encoding='utf-8', newline='\n')
    seal_io.emit(dict(info, seal=seal, replay=replay['outcome'], sample=data['reference']['archive_sha256']))
    return int(replay['outcome'] != 'ok')


def verify(spec, book, ctx, red, inputs):
    replay = seal_io.replay_seal(spec, HERE)
    verdict, data = accept(spec, book, ctx, red, inputs, get('CHECKOUT'), get('CLEANROOM'))
    try:
        facts = inspect_known_archive(book, ctx, 'populated', (HERE / SAMPLE).read_bytes())
        sample_ok = canonical(facts) == canonical(data['reference'])
    except (AssertionError, OSError):
        sample_ok = False
    ok = (replay['outcome'] == 'ok' and verdict['outcome'] == 'accepted' and sample_ok
          and canonical(replay) == canonical(get('REPLAY')) and canonical(verdict) == canonical(get('ACCEPTANCE'))
          and canonical(data) == canonical(get('BUNDLE'))
          and (HERE / 'REPORT.md').read_bytes() == report(spec, red, verdict, data).encode('utf-8')
          and (HERE / seal_io.page_name(spec)).read_bytes() == page(spec, verdict, data, get('SEAL'), replay).encode('utf-8'))
    seal_io.emit(dict(replay, sample_match=sample_ok, record_and_page_match=ok))
    return int(not ok)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--measure-only', action='store_true', help='П3–П6 без печати')
    mode.add_argument('--verify-seal', action='store_true', help='Проверка печати, примера и страницы без записи')
    args = parser.parse_args()
    try:
        params = load()
        return verify(*params) if args.verify_seal else generate(*params, measure_only=args.measure_only)
    except (AssertionError, AttributeError, IndexError, KeyError, OSError, TypeError, ValueError, subprocess.TimeoutExpired) as e:
        seal_io.emit({'outcome': 'rejected', 'error': type(e).__name__})
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
