#!/usr/bin/env python3
"""И-116: независимые прогоны, приёмка, детерминированная печать и просмотр без записи."""
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
PREFIX = 'research/116/'
BOOK, PROBE = (PREFIX + n for n in ('CASES.json', 'test_conflict_review.py'))
sys.dont_write_bytecode = True
sys.path[:0] = [str(HERE), str(ROOT / 'research/strategy/harness')]
import run_iteration as seal_io
from render116 import page, report
from test_conflict_review import canonical, context, expected_observation

PINNED = sorted([*['kit/base/' + n for n in ('schema_v2.py', 'profile_journal.py', 'registry_journal.py',
                                             'registry_policy.py', 'registry_store.py')],
                 'research/114/test_promotion.py', 'research/114/PROMOTION.json', 'research/115/CASES.json',
                 'research/115/SIMULATION.json', 'research/strategy/pre-104/SCHEMA-CASES.json'])
TARGETS = sorted([BOOK, PROBE, *PINNED, 'kit/base/CONFLICT-REVIEW.md', 'kit/base/conflict_review.py'])
OUTPUTS = ('CHECKOUT', 'CLEANROOM', 'ACCEPTANCE', 'CONFLICTS')
COUNTS = ('pass', 'fail', 'not run')
PRIMARY = tuple(f'C{i:02d}' for i in range(1, 7))


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
    sealed = [*TARGETS, *[PREFIX + n + '.json' for n in OUTPUTS],
              *[PREFIX + n for n in ('DESIGN.md', 'ITERATION.json', 'RED.json', 'REPORT.md', 'run.py', 'render116.py')],
              'research/STRATEGY.md', 'research/strategy/SYNC-LOG.md',
              *['research/strategy/harness/' + n for n in ('run_iteration.py', 'render.py', 'probes.py')]]
    if (spec['id'] != '116' or spec['command'] != ['-B', '-I', '-S', '-X', 'utf8', PROBE]
            or spec['target_inputs'] != TARGETS or spec['seal_members'] != sorted(sealed)
            or any(seal_io.repo_path(n) != ROOT / n for n in sealed)):
        raise ValueError('spec_inputs')
    inputs = inputs_from(ROOT, TARGETS)
    h = digests(inputs)
    if (h[BOOK] != spec['casebook_sha256'] or h[PROBE] != spec['test_sha256']
            or spec['pinned_inputs'] != {n: h[n] for n in PINNED}):
        raise ValueError('frozen_input_drift')
    book = json.loads(inputs[BOOK])
    ids = [r['id'] for r in book['cases']]
    if (canonical(book['format']) != b'1' or ids != spec['case_ids'] or len(ids) != len(set(ids))
            or tuple(ids[:6]) != PRIMARY or book['baseline'] != spec['baseline']):
        raise ValueError('case_ids')
    return spec, book, context(book), get('RED'), inputs


def measure(root, spec, inputs):
    before = inputs_from(root, inputs)
    if before != inputs:
        raise ValueError('different_input_bytes')
    run = subprocess.run([sys.executable, *spec['command']], cwd=root, capture_output=True, timeout=45)
    try:
        data = json.loads(run.stdout)
    except ValueError:
        data = None
    return {'rc': run.returncode, 'stderr_empty': not run.stderr, 'result': data,
            'inputs_sha256': digests(before), 'inputs_unchanged': inputs_from(root, inputs) == before}


def snapshot(root):
    return {p.relative_to(root).as_posix(): (s.st_mode, s.st_ino, s.st_size, s.st_mtime_ns)
            for p in root.rglob('*') for s in (p.lstat(),)}


def clean_copy(spec, inputs):
    with TemporaryDirectory(prefix='ack-i116-inputs-') as folder:
        root = Path(folder).resolve()
        for name, raw in inputs.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        before = snapshot(root)
        result = measure(root, spec, inputs)
        return dict(result, files=sorted(n for n in before if (root / n).is_file()), tree_unchanged=snapshot(root) == before)


def tally(rows):
    seen = Counter(r['status'] for r in rows)
    return {k: seen[k] for k in COUNTS}


def expected_control(book):
    return {'legacy_x07_pairs': 1, 'legacy_equal_pairs': 0, 'legacy_joint_pairs': 3,
            'system_mutation': 'system_immutable', 'working_port': 'unknown_operation',
            'p01_exact': book['prior'], 'p01_projects': ['cli', 'docs']}


def header_matches(data, book):
    return (type(data) is dict and data.keys() == {'format', 'control', 'os', 'python', 'rows', 'counts'}
            and canonical(data['format']) == b'1' and canonical(data['control']) == canonical(expected_control(book))
            and all(type(data[k]) is str and data[k] for k in ('os', 'python')))


def red_gate(spec, book, red):
    data = red['result']
    return (red['independent_baseline_match'] is True and canonical(red['rc']) == b'1'
            and all(red[k] == spec[k] for k in ('baseline', 'command', 'casebook_sha256', 'test_sha256', 'pinned_inputs'))
            and header_matches(data, book)
            and data['rows'] == [{'id': n, 'status': 'fail', 'reason': 'conflict_review_missing'} for n in spec['case_ids']]
            and canonical(data['counts']) == canonical({'pass': 0, 'fail': len(spec['case_ids']), 'not run': 0}))


def validate_run(spec, book, ctx, evidence):
    data = evidence['result']
    rows = data.get('rows') if type(data) is dict else None
    seen = {}
    if type(rows) is list:
        for row in rows:
            if type(row) is dict and type(row.get('id')) is str:
                seen.setdefault(row['id'], []).append(row)
    checks = []
    for case in book['cases']:
        actual = seen.get(case['id'], [])
        expected = {'id': case['id'], 'status': 'pass', 'observation': expected_observation(case, ctx)}
        status = 'not run' if not actual else 'pass' if len(actual) == 1 and canonical(actual[0]) == canonical(expected) else 'fail'
        checks.append({**{k: case[k] for k in ('id', 'basis', 'criterion')}, 'status': status})
    counts = tally(checks)
    ok = (canonical(evidence['rc']) == b'0' and evidence['stderr_empty'] is True and header_matches(data, book)
          and type(rows) is list and [r.get('id') if type(r) is dict else None for r in rows] == spec['case_ids']
          and canonical(data['counts']) == canonical(counts) and counts == {'pass': len(checks), 'fail': 0, 'not run': 0})
    return ok, {'rc': evidence['rc'], 'counts': counts, 'cases': checks}


def summary(book, result):
    actual = {r['id']: r['observation'] for r in result['rows']}
    rows = [{**{k: c[k] for k in ('id', 'basis', 'criterion')}, **actual[c['id']]} for c in book['cases']]
    reports = [r['report'] for r in rows if r['report'] is not None]
    primary = [p for id_ in PRIMARY for p in actual[id_]['report']['conflicts']]
    metrics = {'cases': len(rows), 'reviewed': len(reports), 'refused': len(rows) - len(reports),
               'primary_cases': len(PRIMARY), 'primary_pairs': len(primary),
               'prospective_primary_pairs': sum(p['comparison'] == 'prospective' for p in primary),
               'cases_with_conflicts': sum(bool(r['conflicts']) for r in reports),
               'unassessed_candidates': sum(r['outcome'] == 'unassessed_candidate' for r in reports),
               'effect_attempts': sum(len(r['effects']) for r in rows),
               'inputs_unchanged_all': all(r['inputs_unchanged'] for r in rows), 'quiet_all': all(r['quiet'] for r in rows)}
    return {'iteration': 'И-116', 'basis': 'CHECKOUT.json; CLEANROOM.json; CASES.json; X07/X08',
            'control': result['control'], 'metrics': metrics, 'rows': rows}


def accept(spec, book, ctx, red, inputs, checkout, clean):
    checks, runs = [], {}

    def gate(name, ok, basis, criterion):
        checks.append({'check': name, 'status': 'pass' if ok else 'fail', 'basis': basis, 'criterion': criterion})

    gate('frozen_red', red_gate(spec, book, red), 'DESIGN.md; CASES.json; ITERATION.json; RED.json',
         'Обязательные строки до продукта: 0/33/0 из базы и checkout; рабочий A3/A2 и контроль точного P01 проходят.')
    ready = []
    for name, evidence in (('checkout', checkout), ('cleanroom', clean)):
        ok, runs[name] = validate_run(spec, book, ctx, evidence)
        ready.append(ok)
        gate(name, ok, f'{name.upper()}.json; test_conflict_review.py',
             'Все ID ровно по одному, rc0; формулировки, связи, обе стороны, ранги, отпечатки и отказы совпали с отдельным оракулом.')
    data = summary(book, checkout['result']) if all(ready) else None
    m = data['metrics'] if data else {}
    rows = {r['id']: r for r in data['rows']} if data else {}
    pairs = [p for n in PRIMARY for p in rows[n]['report']['conflicts']] if data else []
    gate('six_cross_layer_cases', bool(m) and m['primary_cases'] == 6 and len(pairs) == 7
         and {tuple(s['area'] for s in p['entries']) for p in pairs} == {('L0', 'L1'), ('L1', 'L2')},
         'CASES.json C01–C06; CONFLICTS.json',
         'Шесть конфликтных сценариев, обе семьи, в C05 два результата, у C06 сохраняется черновик.')
    gate('declarations_not_decisions', bool(m)
         and all(rows[n]['report']['outcome'] == 'owner_decision_required' for n in PRIMARY)
         and all('owner_decision_required' in p['restrictions']
                 and not any(t['area'] == 'L0' for a in p['options'] for t in a['targets']) for p in pairs)
         and [r['declared_rank'] for r in pairs[0]['entries']] == [10, 90]
         and 'system_constraint_not_overridable' in pairs[0]['restrictions']
         and rows['C05']['report']['conflicts'] == rows['K06']['report']['conflicts']
         and rows['C05']['report']['priorities_sha256'] == rows['K06']['report']['priorities_sha256'],
         'C01, C02, C03, C04, C05, K06; A2/A3',
         'Больший, равный, нулевой или отсутствующий ранг только показывается. L0 не цель предложения, победителя/решения нет.')
    gate('draft_and_p01', bool(m) and m['prospective_primary_pairs'] == 1 and m['unassessed_candidates'] == 2
         and all(rows[n]['report']['candidate']['entry_sha256'] == book['prior']['entry_sha256']
                 and rows[n]['report']['candidate']['comparison'] == 'no_key'
                 and rows[n]['report']['inputs_sha256']['L1'] == book['prior']['profile_sha256'] for n in ('K07', 'K08'))
         and rows['K07']['report']['inputs_sha256']['L2'] != rows['K08']['report']['inputs_sha256']['L2']
         and rows['K10']['report']['conflicts'] == rows['C05']['report']['conflicts'],
         'C06; K04/K07/K08/K10; P01 И‑114 и И‑115',
         'Потенциальное не становится действующим; точный P01 без ключа не оценён в двух разных L2 и не скрывает другие пары.')
    gate('guards_and_effects', bool(m) and m['refused'] == 17 and m['effect_attempts'] == 0
         and m['inputs_unchanged_all'] and m['quiet_all']
         and all(r['report'] is None or r['report']['write_allowed'] is False for r in rows.values()),
         'N01–N17; Monitor, CHECKOUT.json, CLEANROOM.json',
         'Неверные данные не дают частичного результата; по всем вызовам ноль I/O и эха, входы не изменены, разрешение на запись не выдаётся.')
    gate('isolation', clean['files'] == TARGETS and clean['tree_unchanged'] is True,
         'ITERATION.json; CLEANROOM.json', 'Только объявленные входы; свежий временный каталог, без Git, донора и установки.')
    gate('repeat', all(ready) and checkout['inputs_unchanged'] is True and clean['inputs_unchanged'] is True
         and checkout['inputs_sha256'] == clean['inputs_sha256'] == digests(inputs)
         and canonical(checkout['result']) == canonical(clean['result']),
         'CHECKOUT.json; CLEANROOM.json', 'Результаты и хеши всех входов совпали в двух независимых процессах.')
    deferred = [dict(r, status='not run') for r in spec['not_run']]
    counts = tally(checks + deferred)
    obs = checkout['result'] if type(checkout['result']) is dict else {}
    acceptance = {'iteration': 'И-116', 'outcome': 'accepted' if not counts['fail'] else 'rejected', 'counts': counts,
                  'checks': checks, 'runs': runs, 'not_run': deferred, 'os': obs.get('os'), 'python': obs.get('python'),
                  'scope': 'П5 · структурный просмотр на синтетике; не запись, перенос, активация или Git'}
    return acceptance, data if not counts['fail'] else {'iteration': 'И-116', 'control': None, 'metrics': None, 'rows': None}


def generate(spec, book, ctx, red, inputs, *, measure_only):
    checkout, clean = measure(ROOT, spec, inputs), clean_copy(spec, inputs)
    verdict, observed = accept(spec, book, ctx, red, inputs, checkout, clean)
    for n, output in zip(OUTPUTS, (checkout, clean, verdict, observed)):
        seal_io.dump_json(HERE / (n + '.json'), output)
    (HERE / 'REPORT.md').write_text(report(spec, red, verdict, observed), encoding='utf-8', newline='\n')
    info = {'outcome': verdict['outcome'], 'counts': verdict['counts'], 'metrics': observed['metrics'],
            'runs': {n: row['counts'] for n, row in verdict['runs'].items()}}
    if measure_only or verdict['outcome'] != 'accepted':
        seal_io.emit(info)
        return int(verdict['outcome'] != 'accepted')
    raw, seal = seal_io.seal_bytes(spec)
    (HERE / seal['file']).write_bytes(raw)
    seal_io.dump_json(HERE / 'SEAL.json', seal)
    replay = seal_io.replay_seal(spec, HERE)
    seal_io.dump_json(HERE / 'REPLAY.json', replay)
    (HERE / seal_io.page_name(spec)).write_text(page(spec, verdict, observed, seal, replay), encoding='utf-8', newline='\n')
    seal_io.emit(dict(info, seal=seal, replay=replay['outcome']))
    return int(replay['outcome'] != 'ok')


def verify(spec, book, ctx, red, inputs):
    replay = seal_io.replay_seal(spec, HERE)
    verdict, observed = accept(spec, book, ctx, red, inputs, get('CHECKOUT'), get('CLEANROOM'))
    ok = (replay['outcome'] == 'ok' and verdict['outcome'] == 'accepted'
          and canonical(replay) == canonical(get('REPLAY')) and canonical(verdict) == canonical(get('ACCEPTANCE'))
          and canonical(observed) == canonical(get('CONFLICTS'))
          and (HERE / 'REPORT.md').read_bytes() == report(spec, red, verdict, observed).encode('utf-8')
          and (HERE / seal_io.page_name(spec)).read_bytes() == page(spec, verdict, observed, get('SEAL'), replay).encode('utf-8'))
    seal_io.emit(dict(replay, record_and_page_match=ok))
    return int(not ok)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--measure-only', action='store_true', help='П3–П6 без печати')
    mode.add_argument('--verify-seal', action='store_true', help='Проверка печати и страницы без записи')
    args = parser.parse_args()
    try:
        params = load()
        return verify(*params) if args.verify_seal else generate(*params, measure_only=args.measure_only)
    except (AssertionError, AttributeError, IndexError, KeyError, OSError, TypeError, ValueError, subprocess.TimeoutExpired) as e:
        seal_io.emit({'outcome': 'rejected', 'error': type(e).__name__})
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
