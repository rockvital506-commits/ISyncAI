#!/usr/bin/env python3
"""И-115: два прогона имитации, приёмка и воспроизводимая печать."""
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
PREFIX = 'research/115/'
BOOK, PROBE = PREFIX + 'CASES.json', PREFIX + 'test_simulation.py'
sys.dont_write_bytecode = True
sys.path[:0] = [str(HERE), str(ROOT / 'research/strategy/harness')]
import run_iteration as seal_io
from render115 import page, report
from test_simulation import canonical, expected_observation

PINNED = sorted([*['kit/base/' + n for n in (
    'entry.txt', 'START.md', 'bootstrap.py', 'operation_card.py', 'operation_plan.py', 'profile_journal.py',
    'project_specificity.py', 'promotion.py', 'registry_journal.py', 'registry_policy.py', 'registry_store.py',
    'schema_v2.py', 'PROMOTION.md', 'OPERATION-PLAN.md')], *['research/114/' + n for n in (
    'CASES.json', 'PROMOTION.json', 'test_promotion.py')]])
TARGETS = sorted([BOOK, PROBE, *PINNED, 'kit/base/SIMULATION.md', 'kit/base/simulation.py'])
OUTPUTS = ('CHECKOUT', 'CLEANROOM', 'ACCEPTANCE', 'SIMULATION')
COUNTS = ('pass', 'fail', 'not run')
HASHES = ('entry_sha256', 'profile_sha256', 'control_sha256')


def get(name):
    return seal_io.read_json(HERE / (name + '.json'))


def sources(root, names):
    files = {}
    for n in names:
        p = root / n
        if p.resolve() != p or not p.is_file():
            raise ValueError('ordinary_input_required')
        files[n] = p.read_bytes()
    return files


def digests(files):
    return {n: sha256(raw).hexdigest() for n, raw in files.items()}


def control(book):
    return {'promotion_case': 'P01', 'promotion_exact': True, 'fixtures_valid': 2, 'working_port': 'unknown_operation',
            **{k: book['origin']['witness'][k] for k in HASHES}}


def load():
    spec = get('ITERATION')
    sealed = [*TARGETS, *[PREFIX + name + '.json' for name in OUTPUTS],
              *[PREFIX + n for n in ('DESIGN.md', 'ITERATION.json', 'RED.json', 'REPORT.md', 'run.py', 'render115.py')],
              'research/STRATEGY.md', 'research/strategy/SYNC-LOG.md',
              *['research/strategy/harness/' + n for n in ('render.py', 'run_iteration.py', 'probes.py')]]
    if (spec['id'] != '115' or spec['command'] != ['-B', '-I', '-S', '-X', 'utf8', PROBE]
            or spec['target_inputs'] != TARGETS or spec['seal_members'] != sorted(sealed)
            or any(seal_io.repo_path(n) != ROOT / n for n in sealed)):
        raise ValueError('spec_inputs')
    inputs = sources(ROOT, TARGETS)
    h = digests(inputs)
    if (h[BOOK] != spec['casebook_sha256'] or h[PROBE] != spec['test_sha256']
            or spec['pinned_inputs'] != {n: h[n] for n in PINNED}):
        raise ValueError('frozen_input_drift')
    book = json.loads(inputs[BOOK])
    ids = [r['id'] for r in book['cases']]
    if canonical(book['format']) != b'1' or ids != spec['case_ids'] or len(ids) != len(set(ids)) or book['origin']['baseline'] != spec['baseline']:
        raise ValueError('case_ids')
    return spec, book, get('RED'), inputs


def measure(root, spec, inputs):
    before = sources(root, inputs)
    if before != inputs:
        raise ValueError('different_input_bytes')
    run = subprocess.run([sys.executable, *spec['command']], cwd=root, capture_output=True, timeout=45)
    try:
        result = json.loads(run.stdout)
    except ValueError:
        result = None
    return {'rc': run.returncode, 'stderr_empty': not run.stderr, 'result': result,
            'inputs_sha256': digests(before), 'inputs_unchanged': sources(root, inputs) == before}


def snapshot(root):
    return {p.relative_to(root).as_posix(): (s.st_mode, s.st_ino, s.st_mtime_ns)
            for p in root.rglob('*') for s in (p.lstat(),)}


def clean_copy(spec, inputs):
    with tempfile.TemporaryDirectory(prefix='ack-i115-inputs-') as tmp:
        root = Path(tmp).resolve()
        for name, raw in inputs.items():
            p = root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(raw)
        before = snapshot(root)
        evidence = measure(root, spec, inputs)
        return dict(evidence, files=sorted(n for n in before if (root / n).is_file()), tree_unchanged=snapshot(root) == before)


def tally(rows):
    counts = Counter(r['status'] for r in rows)
    return {k: counts[k] for k in COUNTS}


def red_gate(spec, book, red):
    data = red['result']
    return (red['independent_baseline_match'] is True and canonical(red['rc']) == b'1'
            and all(red[k] == spec[k] for k in ('baseline', 'command', 'casebook_sha256', 'test_sha256', 'pinned_inputs'))
            and canonical(data['format']) == b'1' and canonical(data['control']) == canonical(control(book))
            and data['rows'] == [{'id': n, 'status': 'fail', 'reason': 'simulation_missing'} for n in spec['case_ids']]
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
        wanted = {'id': case['id'], 'status': 'pass', 'observation': expected_observation(book, case)}
        status = 'not run' if not pair else 'pass' if len(pair) == 1 and canonical(pair[0]) == canonical(wanted) else 'fail'
        checks.append({**{k: case[k] for k in ('id', 'basis', 'criterion')}, 'status': status})
    counts = tally(checks)
    ok = (canonical(evidence['rc']) == b'0' and evidence['stderr_empty'] is True and type(data) is dict
          and data.keys() == {'format', 'control', 'os', 'python', 'rows', 'counts'} and canonical(data['format']) == b'1'
          and canonical(data['control']) == canonical(control(book)) and type(rows) is list
          and [r.get('id') if type(r) is dict else None for r in rows] == spec['case_ids']
          and canonical(data['counts']) == canonical(counts) and counts == {'pass': len(checks), 'fail': 0, 'not run': 0})
    return ok, {'rc': evidence['rc'], 'counts': counts, 'cases': checks}


def summary(book, evidence):
    seen = {r['id']: r['observation'] for r in evidence['result']['rows']}
    rows = [{**{k: c[k] for k in ('id', 'basis', 'criterion')}, **seen[c['id']]} for c in book['cases']]
    positives = [r for r in rows if r['outcome'] == 'simulated']
    reference = seen['P01']['result']
    metrics = {'cases': len(rows), 'simulated': len(positives), 'refused': len(rows) - len(positives),
               'validated_projects': [v['fixture'] for v in reference['projects']],
               'paired_deployments': sum(len(r['result']['projects']) for r in positives),
               **{k: sum(r[k] for r in rows) for k in ('write_attempts', 'bootstrap_calls', 'list_calls', 'io_violations')},
               **{k + '_all': all(r[k] for r in rows) for k in ('cleaned', 'protected_unchanged', 'inputs_unchanged')}}
    return {'iteration': 'И-115', 'basis': 'CHECKOUT.json; CLEANROOM.json; ref И‑114 P01',
            'reference': reference, 'metrics': metrics, 'rows': rows}


def accept(spec, book, red, inputs, checkout, clean):
    gates, runs = [], {}

    def gate(name, passed, basis, criterion):
        gates.append({'check': name, 'status': 'pass' if passed else 'fail', 'basis': basis, 'criterion': criterion})

    gate('frozen_red', red_gate(spec, book, red), 'DESIGN.md; CASES.json; RED.json; ITERATION.json',
         'Тот же RED в checkout и из 46d99ca: P01 получен, обе формы проектов валидны, реализация simulate отсутствует.')
    ready = []
    for key, evidence in [('checkout', checkout), ('cleanroom', clean)]:
        ok, runs[key] = validate_run(spec, book, evidence)
        ready.append(ok)
        gate(key, ok, f'{key.upper()}.json; CASES.json',
             'Все ID ровно один раз, в том же порядке, rc0; факты, коды и счётчики эффектов точно совпали с оракулом.')
    data = summary(book, checkout) if all(ready) else None
    m = data['metrics'] if data else {}
    rows = {r['id']: r for r in data['rows']} if data else {}
    ref = data['reference'] if data else {}
    gate('exact_p01', bool(m) and all(ref[k] == book['origin']['witness'][k] for k in HASHES)
         and rows['P02']['result'] == rows['P03']['result'] == ref,
         'И‑114 PROMOTION.json P01; ITERATION.json; test_simulation.py: load_prior, checked_init; P01–P03',
         'Три отпечатка связаны с фактическим promote/stage и независимым P01; разложены точные байты, тот же результат при перестановке и другом хвосте START.')
    gate('two_projects', bool(m) and m['validated_projects'] == ['cli', 'docs']
         and [p['installed']['l2_rules'] for p in ref['projects']] == [1, 2]
         and all(p['control']['profile_revision'] == 3 and p['installed']['profile_revision'] == 4
                 and not p['control']['candidate_visible'] and p['installed']['candidate_visible'] and p['installed']['text_verified']
                 and not p['installed']['candidate_active'] for p in ref['projects']),
         'SIMULATION.json; P01; BootstrapSession.plan → PlanSession.plan (list)',
         'Две пары свежих раскладок, разный L2; черновик и точный текст доступны только в installed, не активны; все правила L2 прежние.')
    gate('reject_without_partial', bool(m) and m['refused'] > 0
         and all(rows[n]['outcome'] == 'simulation_failed' and rows[n]['result'] is None and rows[n]['where'] == 'project/docs'
                 for n in ('N19', 'N20', 'N21')),
         'CASES.json: N01–N22; test_simulation.py: Monitor и observed_plan',
         'Подмена входа не разворачивается; сбой чтения/записи или исхода во втором проекте не даёт даже частичного результата.')
    gate('no_external_effects', bool(m) and m['io_violations'] == 0 and m['cleaned_all']
         and m['protected_unchanged_all'] and m['inputs_unchanged_all']
         and all(p[v]['unchanged'] for p in ref['projects'] for v in ('control', 'installed')),
         'test_simulation.py: Monitor, снимки; CHECKOUT.json; CLEANROOM.json',
         'Создание только новых шести файлов на раскладку; рабочие и исходные контрольные байты прежние, временное дерево убрано.')
    gate('isolation', clean['files'] == TARGETS and clean['tree_unchanged'] is True,
         'ITERATION.json; CLEANROOM.json', 'Свежий каталог из объявленных и закреплённых входов, без Git, донора, ISAI и установки.')
    gate('repeat', all(ready) and checkout['inputs_unchanged'] is True and clean['inputs_unchanged'] is True
         and checkout['inputs_sha256'] == clean['inputs_sha256'] == digests(inputs)
         and canonical(checkout['result']) == canonical(clean['result']),
         'CHECKOUT.json; CLEANROOM.json', 'Повторены те же байты, порядок исходов и все свидетельства; точные временные имена в результат не входят.')
    deferred = [dict(row, status='not run') for row in spec['not_run']]
    counts = tally(gates + deferred)
    obs = checkout['result'] if type(checkout['result']) is dict else {}
    result = {'iteration': 'И-115', 'outcome': 'accepted' if not counts['fail'] else 'rejected', 'counts': counts,
              'checks': gates, 'runs': runs, 'not_run': deferred, 'os': obs.get('os'), 'python': obs.get('python'),
              'scope': 'П5 · синтетическое размещение и просмотр, не исполнение или рабочий перенос; П9 проверяется отдельно по Git'}
    return result, data if not counts['fail'] else {'iteration': 'И-115', 'reference': None, 'metrics': None, 'rows': None}


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
    reply = seal_io.replay_seal(spec, HERE)
    seal_io.dump_json(HERE / 'REPLAY.json', reply)
    (HERE / seal_io.page_name(spec)).write_text(page(spec, accepted, data, seal, reply), encoding='utf-8', newline='\n')
    seal_io.emit(dict(info, seal=seal, replay=reply['outcome']))
    return int(reply['outcome'] != 'ok')


def verify(spec, book, red, inputs):
    reply = seal_io.replay_seal(spec, HERE)
    accepted, data = accept(spec, book, red, inputs, get('CHECKOUT'), get('CLEANROOM'))
    ok = (reply['outcome'] == 'ok' and accepted['outcome'] == 'accepted' and canonical(reply) == canonical(get('REPLAY'))
          and canonical(accepted) == canonical(get('ACCEPTANCE')) and canonical(data) == canonical(get('SIMULATION'))
          and (HERE / 'REPORT.md').read_bytes() == report(spec, red, accepted, data).encode('utf-8')
          and (HERE / seal_io.page_name(spec)).read_bytes() == page(spec, accepted, data, get('SEAL'), reply).encode('utf-8'))
    seal_io.emit(dict(reply, record_and_page_match=ok))
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
