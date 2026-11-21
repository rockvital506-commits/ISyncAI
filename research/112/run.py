#!/usr/bin/env python3
"""И-112: checkout, чистый повтор, приёмка и неизменяемая проверка печати."""
import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PREFIX = 'research/112/'
BOOK, PROBE = PREFIX + 'CASES.json', PREFIX + 'test_bootstrap.py'
sys.dont_write_bytecode = True
sys.path[:0] = [str(HERE), str(ROOT / 'research/strategy/harness')]
import run_iteration as seal_io
from render112 import page, report
from test_bootstrap import (CALLS, DOCS, ENTRY, FILES, LAYERS, MODULE, START, canonical, changes,
                            digest, expected, expected_plan, expected_step, fixture, snapshot)


def sources(root, names):
    files = {}
    for name in names:
        path = root / name
        if path.resolve() != path or not path.is_file():
            raise ValueError('Ожидался обычный вход: ' + name)
        files[name] = path.read_bytes()
    return files


def hashes(files):
    return {name: digest(raw) for name, raw in files.items()}


def get(name):
    return seal_io.read_json(HERE / (name + '.json'))


def load():
    spec = get('ITERATION')
    if spec['id'] != '112' or spec['command'] != ['-B', '-I', '-S', '-X', 'utf8', PROBE]:
        raise ValueError('Ожидалась целевая проба И-112 в изолированном процессе')
    for field in ('target_inputs', 'seal_members'):
        names = spec[field]
        if (type(names) is not list or not names or names != sorted(set(names))
                or any(seal_io.repo_path(n) != ROOT / n for n in names)):
            raise ValueError('Неканонический список: ' + field)
    targets, members = set(spec['target_inputs']), set(spec['seal_members'])
    generated = {PREFIX + n for n in ('CHECKOUT.json', 'CLEANROOM.json', 'ACCEPTANCE.json', 'BOOTSTRAP.json', 'REPORT.md')}
    required = {PREFIX + n for n in ('DESIGN.md', 'ITERATION.json', 'RED.json', 'run.py', 'render112.py')} | generated | {
        'research/STRATEGY.md', 'research/strategy/SYNC-LOG.md', 'research/strategy/COMPATIBILITY.json'}
    outside = {PREFIX + n for n in ('SEAL.json', 'REPLAY.json', seal_io.page_name(spec), seal_io.seal_name(spec))}
    if (not {BOOK, PROBE, ENTRY, START, MODULE, *DOCS} <= targets or not (targets | required) <= members or outside & members
            or any(not n.startswith('kit/base/') and n not in (BOOK, PROBE) for n in targets)):
        raise ValueError('Не совпадает ограниченный состав пробы или печати')
    inputs = sources(ROOT, spec['target_inputs'])
    if (digest(inputs[BOOK]) != spec['casebook_sha256'] or digest(inputs[PROBE]) != spec['test_sha256']):
        raise ValueError('Корпус или код пробы расходятся с закреплённым П2')
    book = json.loads(inputs[BOOK])
    ids = [c['id'] for c in book['cases']]
    if (canonical(book['format']) != b'1' or ids != spec['case_ids'] or len(ids) != len(set(ids))
            or [c['id'] for c in book['cases'] if c.get('trial') == 'confirm'] != ['B01']):
        raise ValueError('Корпус не совпал: требуется один B01 и все его обязательные контроли')
    return spec, book, get('RED'), inputs


def measure(root, spec, inputs):
    before = sources(root, inputs)
    if before != inputs:
        raise ValueError('Входы перед запуском не совпали')
    run = subprocess.run([sys.executable, *spec['command']], cwd=root, capture_output=True, timeout=60)
    stderr = run.stderr.decode('utf-8', errors='replace')
    if stderr:
        sys.stderr.write(stderr)
    try:
        result = json.loads(run.stdout)
    except ValueError:
        result = None
    return {'rc': run.returncode, 'stderr_empty': not stderr, 'result': result,
            'inputs_sha256': hashes(before), 'inputs_unchanged': sources(root, inputs) == before}


def clean_copy(spec, inputs):
    with tempfile.TemporaryDirectory(prefix='ack-i112-inputs-') as tmp:
        root = Path(tmp).resolve()
        for name, contents in inputs.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(contents)
        before = snapshot(root)
        run = measure(root, spec, inputs)
        after = snapshot(root)
        filenames = lambda tree: sorted(n for n, info in tree.items() if info[0][0] != 'dir')
        return dict(run, files_before=filenames(before), files_after=filenames(after), tree_unchanged=not changes(before, after))


def tally(rows):
    counts = Counter(row['status'] for row in rows)
    return {k: counts[k] for k in ('pass', 'fail', 'not run')}


def red_gate(spec, book, red):
    files, _ = fixture({}, {})
    plan = expected_plan(book['phrases']['create'], files)
    direct = expected_step('direct-plan', plan, [(FILES[a], files[FILES[a]]) for a in LAYERS], before=CALLS)
    before = red['result']
    return (canonical(red['rc']) == b'1' and red['replay_from_git_archive'] is True
            and all(red[k] == spec[k] for k in ('baseline', 'casebook_sha256', 'test_sha256', 'command'))
            and canonical(before['baseline']) == canonical({'missing': [ENTRY, START, MODULE], 'direct_plan_matches': True,
                                                           'direct_plan': direct})
            and before['rows'] == [{'id': i, 'status': 'fail', 'reason': 'bootstrap_missing'} for i in spec['case_ids']]
            and canonical(before['counts']) == canonical({'pass': 0, 'fail': len(spec['case_ids']), 'not run': 0}))


def check_run(run, spec, book, docs):
    result = run['result']
    observed = (result.get('rows') if type(result) is dict else None) or []
    by_id = {}
    for row in observed:
        by_id.setdefault(row['id'], []).append(row)
    cases = []
    for c in book['cases']:
        rows = by_id.get(c['id'], [])
        if not rows:
            status = 'not run'
        elif len(rows) == 1 and canonical(rows[0]) == canonical({
                'id': c['id'], 'status': 'pass', 'observed': expected(c, book, docs), 'mismatches': []}):
            status = 'pass'
        else:
            status = 'fail'
        cases.append({'id': c['id'], 'status': status, 'basis': c['basis'], 'criterion': c['criterion']})
    counts = tally(cases)
    ok = (canonical(run['rc']) == b'0' and run['stderr_empty'] is True and type(result) is dict
          and canonical(result.get('format')) == b'1' and 'baseline' in result and result['baseline'] is None
          and [r['id'] for r in observed] == spec['case_ids'] and canonical(result.get('counts')) == canonical(counts)
          and counts == {'pass': len(cases), 'fail': 0, 'not run': 0})
    return ok, {'rc': run['rc'], 'counts': counts, 'cases': cases}


def index(run):
    return {row['id']: row['observed'] for row in run['result']['rows']}


def fact_summary(run):
    rows = index(run)
    steps = rows['B01']['steps']
    changes_by_case = {i: sorted({n for step in r['steps'] for n in step['changed']}) for i, r in rows.items()}
    write_attempts = [i for i, r in rows.items() if any(e.startswith(('stage:', 'allocate:', 'write:', 'replace:'))
                                                      for step in r['steps'] for e in step['events'])]
    return {'steps': len(steps), 'max_start_read_bytes': max(sum(r['bytes'] for r in v['steps'][0]['reads']) for v in rows.values()),
            'unique_bootstrap_files': sorted({r['file'] for v in rows.values() for r in v['steps'][0]['reads']}),
            'replacement_count': sum(e.startswith('replace:') for v in rows.values() for step in v['steps'] for e in step['events']),
            'write_attempt_cases': write_attempts, 'changed_by_product': {i: n for i, n in changes_by_case.items() if n}}


def accept(spec, book, red, inputs, checkout, clean):
    checks, runs = [], {}

    def gate(name, passed, basis, criterion):
        checks.append({'check': name, 'status': 'pass' if passed else 'fail', 'basis': basis, 'criterion': criterion})

    docs = {name: inputs[name] for name in [ENTRY, START, *DOCS]}
    gate('red_frozen', red_gate(spec, book, red), 'CASES.json; DESIGN.md; ITERATION.json; RED.json',
         'Прежний c5fec24 даёт точный план без записи, но всех трёх входов bootstrap нет; исправление измерителя воспроизводит тот же RED.')
    ran = []
    for k, evidence, file in (('checkout', checkout, 'CHECKOUT.json'), ('cleanroom', clean, 'CLEANROOM.json')):
        ok, runs[k] = check_run(evidence, spec, book, docs)
        ran.append(ok)
        gate(k, ok, f'{file}; CASES.json', 'Все ID ровно один раз, rc0; точные ответы, фактические прочитанные байты, след, изменения и запись по независимому эталону.')
    gate('isolation', clean['files_before'] == clean['files_after'] == spec['target_inputs'] and clean['tree_unchanged'] is True,
         'ITERATION.json; CLEANROOM.json', 'Только заявленные входы без Git, донора, ISAI; чистая копия не меняется побайтно или по составу.')
    metrics = fact_summary(checkout) if all(ran) else None
    if metrics is not None:
        witness = index(checkout)['B01']['steps'][0]['reads']
        metrics['unread_start_tail_bytes'] = len(inputs[START]) - witness[1]['bytes']
    gate('three_steps_and_consent', metrics is not None and metrics['steps'] == 3 and metrics['replacement_count'] == 1
         and metrics['write_attempt_cases'] == ['B01'] and metrics['changed_by_product'] == {'B01': [FILES['L1']]},
         'CASES.json B01, C01–C05; CHECKOUT.json; CLEANROOM.json',
         'Старт → фраза и точный неизменяющий дифф → отдельное согласие. Только B01 заменяет ровно один реестр, сохраняя contract/draft и решение.')
    gate('bounded_reads', all(ran) and metrics['unique_bootstrap_files'] == sorted([ENTRY, START])
         and metrics['unread_start_tail_bytes'] > 0,
         'CHECKOUT.json; CLEANROOM.json; B01, S05, S09, P01–P02',
         'Префикс §0 ограничен 4096 B, хвост не читается; компиляция и проверка карточки раньше реестров. Уточнение и временное без порта и записи.')
    gate('repeat', all(ran) and checkout['inputs_unchanged'] is True and clean['inputs_unchanged'] is True
         and checkout['inputs_sha256'] == clean['inputs_sha256'] == hashes(inputs)
         and canonical(checkout['result']) == canonical(clean['result']),
         'CHECKOUT.json; CLEANROOM.json', 'Идентичные целевые входы и обязательные наблюдения; в артефактах признак выдачи, не билет.')
    skipped = [dict(row, status='not run') for row in spec['not_run']]
    counts = tally(checks + skipped)
    result = checkout['result'] or {}
    accepted = {'iteration': 'И-112', 'outcome': 'accepted' if not counts['fail'] else 'rejected', 'counts': counts,
                'checks': checks, 'runs': runs, 'not_run': skipped, 'host_os': result.get('os'), 'python': result.get('python'),
                'scope': 'П5 · испытания bootstrap на фикстурах; не релиз/установка; П9 проверяется отдельно по Git'}
    if counts['fail']:
        return accepted, {'iteration': 'И-112', 'metrics': None, 'witness': None, 'controls': None}
    rows = index(checkout)
    controls = []
    for c in book['cases']:
        if c['id'] == 'B01':
            continue
        steps = rows[c['id']]['steps']
        controls.append({'id': c['id'], 'basis': c['basis'], 'criterion': c['criterion'],
                         'outcomes': [s['reply'].get('error', {}).get('code', s['reply']['outcome']) for s in steps]})
    return accepted, {'iteration': 'И-112', 'source': 'CHECKOUT.json; подтверждено CLEANROOM.json',
                      'metrics': metrics, 'witness': rows['B01'], 'controls': controls}


def generate(spec, book, red, inputs, *, measure_only):
    checkout, clean = measure(ROOT, spec, inputs), clean_copy(spec, inputs)
    accepted, data = accept(spec, book, red, inputs, checkout, clean)
    for name, value in (('CHECKOUT', checkout), ('CLEANROOM', clean), ('ACCEPTANCE', accepted), ('BOOTSTRAP', data)):
        seal_io.dump_json(HERE / (name + '.json'), value)
    (HERE / 'REPORT.md').write_text(report(spec, red, accepted, data), encoding='utf-8', newline='\n')
    summary = {'outcome': accepted['outcome'], 'counts': accepted['counts'], 'metrics': data['metrics'],
               'runs': {name: run['counts'] for name, run in accepted['runs'].items()}}
    if measure_only or accepted['outcome'] != 'accepted':
        seal_io.emit(summary)
        return int(accepted['outcome'] != 'accepted')
    raw, seal = seal_io.seal_bytes(spec)
    (HERE / seal['file']).write_bytes(raw)
    seal_io.dump_json(HERE / 'SEAL.json', seal)
    replay = seal_io.replay_seal(spec, HERE)
    seal_io.dump_json(HERE / 'REPLAY.json', replay)
    (HERE / seal_io.page_name(spec)).write_text(page(spec, accepted, data, seal, replay), encoding='utf-8', newline='\n')
    seal_io.emit(dict(summary, seal=seal, replay=replay['outcome']))
    return int(replay['outcome'] != 'ok')


def verify(spec, book, red, inputs):
    replay = seal_io.replay_seal(spec, HERE)
    accepted, data = accept(spec, book, red, inputs, get('CHECKOUT'), get('CLEANROOM'))
    ok = (replay['outcome'] == 'ok' and accepted['outcome'] == 'accepted' and canonical(replay) == canonical(get('REPLAY'))
          and canonical(accepted) == canonical(get('ACCEPTANCE')) and canonical(data) == canonical(get('BOOTSTRAP'))
          and (HERE / 'REPORT.md').read_bytes() == report(spec, red, accepted, data).encode('utf-8')
          and (HERE / seal_io.page_name(spec)).read_bytes() == page(spec, accepted, data, get('SEAL'), replay).encode('utf-8'))
    seal_io.emit(dict(replay, record_and_page_match=ok))
    return int(not ok)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    switches = parser.add_mutually_exclusive_group()
    switches.add_argument('--measure-only', action='store_true', help='Измерить П3–П6, не собирая печать/страницу')
    switches.add_argument('--verify-seal', action='store_true', help='Сверить архив, отчёт и страницу без записи')
    args = parser.parse_args()
    try:
        params = load()
        return verify(*params) if args.verify_seal else generate(*params, measure_only=args.measure_only)
    except (AttributeError, KeyError, IndexError, OSError, TypeError, ValueError, subprocess.TimeoutExpired) as error:
        seal_io.emit({'outcome': 'rejected', 'error': str(error)})
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
