#!/usr/bin/env python3
"""И-110: П3–П8 из целевых входов; проверка печати не меняет файлов."""
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
PREFIX = 'research/110/'
PROBE, CASEBOOK = PREFIX + 'test_actions.py', PREFIX + 'CASES.json'
OPERATIONS = ('create', 'list', 'edit', 'suspend', 'resume', 'revoke', 'delete')
AREAS = ('L1', 'L2')
sys.dont_write_bytecode = True
sys.path[:0] = [str(HERE), str(ROOT / 'research/strategy/harness')]
import run_iteration as sealing  # Только чтение/детерминированный ZIP; не запуск донора.
from render110 import page, report
from test_actions import FILES, HASH, WITNESSES, case_checks, encode, snapshot


def sources(root, names):
    inputs = {}
    for name in names:
        path = root / name
        if path.resolve() != path or not path.is_file():
            raise ValueError('Ожидался обычный файл: ' + name)
        inputs[name] = path.read_bytes()
    return inputs


def measure(root, inputs):
    run = subprocess.run([sys.executable, '-B', '-I', '-S', '-X', 'utf8', PROBE], cwd=root, capture_output=True, timeout=60)
    if run.stderr:
        sys.stderr.write(run.stderr.decode('utf-8', errors='replace'))
    try:
        result = json.loads(run.stdout)
    except ValueError:
        result = None
    return {'rc': run.returncode, 'result': result, 'sources_unchanged': sources(root, inputs) == inputs,
            'inputs_sha256': {k: sha256(v).hexdigest() for k, v in inputs.items()}}


def clean_copy(inputs):
    with tempfile.TemporaryDirectory(prefix='ack-i110-inputs-') as tmp:
        root = Path(tmp).resolve()
        for name, raw in inputs.items():
            name = root / name
            name.parent.mkdir(parents=True, exist_ok=True)
            name.write_bytes(raw)
        before = snapshot(root)
        result = measure(root, sources(root, inputs))
        after = snapshot(root)
        files = lambda tree: sorted(n for n, item in tree.items() if item[0] != 'dir')
        return {**result, 'files_before': files(before), 'files_after': files(after), 'copy_unchanged': before == after}


def load_cases(spec, inputs):
    if (sha256(inputs[CASEBOOK]).hexdigest() != spec['casebook_sha256']
            or sha256(inputs[PROBE]).hexdigest() != spec['test_sha256']):
        raise ValueError('Корпус или проба отличаются от замороженного П2')
    book = json.loads(inputs[CASEBOOK]); cases = book['cases']
    outcomes = [r['expected']['ok'] for r in cases]
    counts = {'positive': outcomes.count(True), 'negative': outcomes.count(False)}
    matrix = [(c['id'], c['operation'], c['target']) for c in cases if c['matrix'] is True]
    expected = sorted((f'M-{op}-{area}', op, area) for op in OPERATIONS for area in AREAS)
    if (encode(book['format']) != b'1' or not cases or len({r['id'] for r in cases}) != len(cases)
            or any(type(v) is not bool for v in outcomes) or encode(counts) != encode(spec['case_counts'])
            or sorted(matrix) != expected):
        raise ValueError('Не совпадает обязательный корпус или матрица 7×2')
    return cases


def tally(rows):
    counts = Counter(row['status'] for row in rows)
    return {key: counts[key] for key in ('pass', 'fail', 'not run')}


def ticket_free(value):
    if type(value) is dict:
        return 'ticket' not in value and all(ticket_free(x) for x in value.values())
    if type(value) is list:
        return all(ticket_free(x) for x in value)
    return True


def observations(evidence):
    return {r['id']: r for r in evidence['result']['rows']}


def valid_previews(evidence):
    try:
        rows = observations(evidence)
        for i in WITNESSES:
            r = rows[i]; p = r['preview']; d = p['diff']; card = p['card']; inputs = p['inputs_sha256']
            op, area = i.split('-')[1:]
            rev = r['observed']['revision']
            if not (p.keys() == {'plan_format', 'outcome', 'dry_run', 'card', 'inputs_sha256', 'diff'}
                    and encode(p['plan_format']) == b'1' and p['dry_run'] is True and p['outcome'] == 'planned'
                    and card['operation'] == op and card['params']['target'] == area and card['outcome'] == 'complete'
                    and d.keys() == {'file', 'revision', 'before_sha256', 'after_sha256', 'unified'}
                    and d['file'] == FILES[area] and encode(d['revision']) == encode({'from': rev[0], 'to': rev[1]})
                    and inputs.keys() == {'L0', 'L1', 'L2'} and inputs[area] == d['before_sha256']
                    and d['after_sha256'] != d['before_sha256'] and all(HASH.fullmatch(h) for h in (*inputs.values(), d['after_sha256']))
                    and d['unified'].startswith(f"--- a/{d['file']}\n+++ b/{d['file']}\n")
                    and '\\ No newline at end of file\n' in d['unified']):
                return False
        return ticket_free(evidence['result'])
    except (AttributeError, IndexError, KeyError, TypeError):
        return False


def accept(spec, cases, red, checkout, clean):
    gates, runs = [], {}

    def gate(name, ok, basis, criterion):
        gates.append({'check': name, 'status': 'pass' if ok else 'fail', 'basis': basis, 'criterion': criterion})

    matrix_ids = {c['id'] for c in cases if c['matrix']}
    gate('frozen_cases', red['base_commit'].startswith(spec['baseline'].split()[0]) and encode(red['rc']) == b'1'
         and all(red[k] == spec[k] for k in ('test_sha256', 'casebook_sha256'))
         and sum(red['counts'].values()) == len(cases) and red['counts']['fail'] > 0 and red['counts']['not run'] == 0
         and len(red['observed_matrix']) == 14 and {r['id'] for r in red['observed_matrix']} == matrix_ids,
         'DESIGN.md; CASES.json; test_actions.py; ITERATION.json; RED.json',
         'Хеши обязательного П2 совпали; контроль до изменения Kit завершился отказами при том же списке ячеек.')
    for key, evidence, file in (('checkout', checkout, 'CHECKOUT.json'), ('cleanroom', clean, 'CLEANROOM.json')):
        rows = case_checks(cases, evidence['result'])
        counts = tally(rows)
        runs[key] = {'counts': counts, 'rc': evidence['rc'], 'cases': rows}
        gate(key, encode(evidence['rc']) == b'0' and counts == {'pass': len(cases), 'fail': 0, 'not run': 0},
             f'{file}; CASES.json', 'Каждый ID ровно один раз: точные исход, диагностика, JSON-типы, байты, статус, решения и физические эффекты.')
    gate('execution_matrix', len(matrix_ids) == 14 and all(
        {r['id'] for r in run['cases'] if r['id'] in matrix_ids and r['status'] == 'pass'} == matrix_ids for run in runs.values()),
        'CASES.json (M-*); CHECKOUT.json; CLEANROOM.json',
        '7×2: чтение без диффа, билета и записи; все 12 мутационных ячеек с точным планом и одной заменой, не только допуск.')
    gate('masked_witnesses', all(valid_previews(r) for r in (checkout, clean)),
         'CHECKOUT.json; CLEANROOM.json: M-create-L1 и M-delete-L2',
         'Показаны точные диффы регистрации и purge с привязкой к SHA-256, ревизиям и файлам, без опубликованных билетов.')
    gate('isolated', clean['files_before'] == clean['files_after'] == sorted(spec['target_inputs']) and clean['copy_unchanged'] is True,
         'ITERATION.json; CLEANROOM.json', 'В чистой копии ровно указанные входы, без Git/ISAI/донора, все побайтно прежние.')
    gate('repeat', checkout['sources_unchanged'] is True and clean['sources_unchanged'] is True
         and checkout['inputs_sha256'] == clean['inputs_sha256'] and encode(checkout['result']) == encode(clean['result']),
         'CHECKOUT.json; CLEANROOM.json', 'Два изолированных процесса дали равные обязательные наблюдения и входные хеши.')
    skipped = [dict(row, status='not run') for row in spec['not_run']]
    counts = tally(gates + skipped)
    return {'iteration': 'И-110', 'outcome': 'accepted' if counts['fail'] == 0 else 'rejected', 'counts': counts,
            'checks': gates, 'runs': runs, 'not_run': skipped,
            'host_os': checkout['result'].get('os') if type(checkout['result']) is dict else None}


def actions(cases, checkout, acceptance):
    data = {'iteration': 'И-110', 'source': 'CHECKOUT.json', 'matrix': None, 'metrics': None, 'previews': None, 'chains': None}
    if acceptance['outcome'] != 'accepted':
        return data
    rows = observations(checkout)
    seen = {i: r['observed'] for i, r in rows.items()}
    matrix = {op: {} for op in OPERATIONS}
    for case in (c for c in cases if c['matrix']):
        i, op, area = case['id'], case['operation'], case['target']
        o = seen[i]
        matrix[op][area] = {'id': i, 'outcome': o['outcome'], 'revision': o.get('revision'),
                            'state': o.get('entry_state'), 'changed': o['changed'], 'replacements': o['replacements']}
    succeeded = [o for o in seen.values() if o.get('outcome') in ('applied', 'applied_chain')]
    return dict(data, matrix=matrix, previews={i: rows[i]['preview'] for i in sorted(WITNESSES)},
                chains={area: seen['P-chain-' + area] for area in AREAS}, metrics={
                    'cells': sum(map(len, matrix.values())),
                    'successful_replacements': sum(o['replacements'] for o in succeeded),
                    'writes_without_confirmation': sum(bool(o['changed']) for o in seen.values()
                                                       if o.get('outcome') not in ('applied', 'applied_chain')),
                    'read_only_lists': sum(o.get('outcome') == 'listed' for o in seen.values()),
                    'no_change': sum(o.get('outcome') == 'no_change' for o in seen.values()),
                    'refused_before_write': sum(not o['ok'] and not o['write_event'] for o in seen.values()),
                    'failed_replacements': sum(o['replacements'] for o in seen.values() if not o['ok']),
                })


def generate(spec, *, measure_only):
    inputs = sources(ROOT, spec['target_inputs'])
    cases, red = load_cases(spec, inputs), sealing.read_json(HERE / 'RED.json')
    checkout, clean = measure(ROOT, inputs), clean_copy(inputs)
    accepted = accept(spec, cases, red, checkout, clean)
    data = actions(cases, checkout, accepted)
    for name, value in (('CHECKOUT', checkout), ('CLEANROOM', clean), ('ACCEPTANCE', accepted), ('ACTIONS', data)):
        sealing.dump_json(HERE / (name + '.json'), value)
    (HERE / 'REPORT.md').write_text(report(spec, cases, red, checkout, accepted, data), encoding='utf-8', newline='\n')
    summary = {'outcome': accepted['outcome'], 'counts': accepted['counts'], 'metrics': data['metrics'],
               'runs': {k: r['counts'] for k, r in accepted['runs'].items()}}
    if accepted['outcome'] != 'accepted' or measure_only:
        sealing.emit(summary)
        return 0 if accepted['outcome'] == 'accepted' else 1
    raw, seal = sealing.seal_bytes(spec)
    (HERE / seal['file']).write_bytes(raw)
    sealing.dump_json(HERE / 'SEAL.json', seal)
    repeated = sealing.replay_seal(spec, HERE)
    sealing.dump_json(HERE / 'REPLAY.json', repeated)
    (HERE / sealing.page_name(spec)).write_text(page(spec, accepted, data, seal, repeated), encoding='utf-8', newline='\n')
    sealing.emit({**summary, 'seal': seal, 'replay': repeated['outcome']})
    return 0 if repeated['outcome'] == 'ok' else 1


def verify(spec):
    repeated = sealing.replay_seal(spec, HERE)
    get = lambda n: sealing.read_json(HERE / (n + '.json'))
    accepted, seal, data = get('ACCEPTANCE'), get('SEAL'), get('ACTIONS')
    ok = (repeated['outcome'] == 'ok' and accepted['outcome'] == 'accepted' and encode(repeated) == encode(get('REPLAY'))
          and (HERE / sealing.page_name(spec)).read_bytes() == page(spec, accepted, data, seal, repeated).encode('utf-8'))
    sealing.emit({**repeated, 'record_and_page_match': ok})
    return 0 if ok else 1


def read_spec():
    spec = sealing.read_json(HERE / 'ITERATION.json')
    if spec['id'] != '110':
        raise ValueError('Ожидалась спецификация И-110')
    for field in ('target_inputs', 'seal_members'):
        names = spec[field]
        if (type(names) is not list or not names or names != sorted(set(names))
                or any(Path(n).as_posix() != n or sealing.repo_path(n) != ROOT / n for n in names)):
            raise ValueError('Неканонический список: ' + field)
    inputs, members = set(spec['target_inputs']), set(spec['seal_members'])
    required = {PREFIX + n for n in ('ITERATION.json', 'RED.json', 'REPORT.md', 'ACCEPTANCE.json', 'ACTIONS.json',
                                     'CHECKOUT.json', 'CLEANROOM.json', 'run.py', 'render110.py')}
    excluded = {PREFIX + n for n in ('SEAL.json', 'REPLAY.json', sealing.seal_name(spec), sealing.page_name(spec))}
    if not {CASEBOOK, PROBE} <= inputs or not (inputs | required) <= members or members & excluded:
        raise ValueError('Печать не включает обязательные входы или включает производный файл')
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
