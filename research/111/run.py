#!/usr/bin/env python3
"""И-111: П3–П8 из целевых входов; проверка печати не меняет файлов."""
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
PREFIX = 'research/111/'
PROBE, CASEBOOK = PREFIX + 'test_intent.py', PREFIX + 'CASES.json'
NL_IDS = [f'NL{i:02d}' for i in range(1, 21)]
sys.dont_write_bytecode = True
sys.path[:0] = [str(HERE), str(ROOT / 'research/strategy/harness')]
import run_iteration as sealing  # Только чтение/детерминированный ZIP; не запуск донора.
from render111 import page, report
from test_intent import FILES, HASH, WITNESSES, case_checks, encode, make_cases, snapshot


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
    with tempfile.TemporaryDirectory(prefix='ack-i111-inputs-') as tmp:
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
    book = json.loads(inputs[CASEBOOK])
    phrases, cases = book['phrases'], make_cases(book)
    if (encode(book['format']) != b'1' or [r['id'] for r in phrases] != NL_IDS
            or len({r['request'] for r in phrases}) != 20 or len({r['id'] for r in cases}) != len(cases)
            or encode(dict(Counter(r['group'] for r in cases))) != encode(spec['case_counts'])):
        raise ValueError('Не совпадает обязательный корпус: 20 разных NL и отдельные контроли')
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
            area = card['params']['target']
            start = {'L1': 4, 'L2': 7}[area]
            if not (p.keys() == {'plan_format', 'outcome', 'dry_run', 'card', 'inputs_sha256', 'diff'}
                    and encode(p['plan_format']) == b'1' and p['dry_run'] is True and p['outcome'] == 'planned'
                    and encode(card) == encode(r['observed']['steps'][0]['card'])
                    and d.keys() == {'file', 'revision', 'before_sha256', 'after_sha256', 'unified'}
                    and d['file'] == FILES[area] and encode(d['revision']) == encode({'from': start, 'to': start + 1})
                    and inputs.keys() == {'L0', 'L1', 'L2'} and inputs[area] == d['before_sha256']
                    and d['after_sha256'] != d['before_sha256'] and all(HASH.fullmatch(h) for h in (*inputs.values(), d['after_sha256']))
                    and d['unified'].startswith(f"--- a/{d['file']}\n+++ b/{d['file']}\n")
                    and '\\ No newline at end of file\n' in d['unified']):
                return False
        return ticket_free(evidence['result'])
    except (AttributeError, IndexError, KeyError, TypeError):
        return False


def measured_corpus(cases, evidence):
    samples = observations(evidence)
    rows, cases_with_writes = [], []
    for c in cases:
        if c['group'] != 'nl':
            continue
        id_ = c['id']
        o = samples[id_]['observed']; step = o['steps'][0]
        if o['changed'] or o['replacements'] or any(phase['writes'] for phase in (step['compile_io'], step['plan_io'], o['trial_io'])):
            cases_with_writes.append(id_)
        rows.append({'id': id_, 'category': c['category'], 'basis': c['basis'], 'card': step['card'],
                     'plan': step['plan']['outcome'], 'ticket_issued': step['ticket_issued'], 'plan_io': step['plan_io'],
                     'apply': o['final'], 'changed': o['changed']})
    return rows, cases_with_writes


def corpus_gate(cases, evidence):
    try:
        rows, writes = measured_corpus(cases, evidence)
        if ([r['id'] for r in rows] != NL_IDS or writes or any(len(r['card']['questions']) > 3 for r in rows)
                or Counter(r['plan'] for r in rows) != {'planned': 3, 'listed': 1, 'missing_params': 8, 'non_registry': 8}):
            return False
        non_registry = {'temporary', 'proposal', 'hypothesis'}
        return all(
            (r['plan'] == 'missing_params' and 'persistence' not in r['card']['params']
             and r['card']['questions'][0]['field'] == 'persistence') if r['category'] == 'ambiguous'
            else (r['plan'] == 'non_registry' and r['card']['params']['persistence'] == r['category']
                  and r['card']['operation'] is None and not r['ticket_issued']
                  and r['plan_io'] == {'reads': False, 'load_called': False, 'writes': False}) if r['category'] in non_registry
            else True for r in rows)
    except (AttributeError, IndexError, KeyError, TypeError):
        return False


def accept(spec, cases, red, checkout, clean):
    gates, runs = [], {}

    def gate(name, ok, basis, criterion):
        gates.append({'check': name, 'status': 'pass' if ok else 'fail', 'basis': basis, 'criterion': criterion})

    before = {r['id']: r for r in red['rows']}
    gate('frozen_cases', red['base_commit'].startswith(spec['baseline'].split()[0]) and encode(red['rc']) == b'1'
         and all(red[k] == spec[k] for k in ('test_sha256', 'casebook_sha256'))
         and sum(red['counts'].values()) == len(cases) and red['counts']['fail'] > 0 and red['counts']['not run'] == 0
         and len(red['rows']) == len(cases) and before.keys() == {r['id'] for r in cases}
         and before['NL14']['plan'] == ['planned'] and before['NL14']['status'] == 'fail',
         'DESIGN.md; CASES.json; test_intent.py; ITERATION.json; RED.json',
         'Хеши П2 совпали; до изменений полный «Сделай черновик» давал план вместо вопроса о режиме.')
    for key, evidence, file in (('checkout', checkout, 'CHECKOUT.json'), ('cleanroom', clean, 'CLEANROOM.json')):
        rows = case_checks(cases, evidence['result'])
        counts = tally(rows)
        runs[key] = {'counts': counts, 'rc': evidence['rc'], 'cases': rows}
        gate(key, encode(evidence['rc']) == b'0' and counts == {'pass': len(cases), 'fail': 0, 'not run': 0},
             f'{file}; CASES.json', 'Каждый ID ровно один раз: точные исход, диагностика, JSON-типы, байты, статус, решения и физические эффекты.')
    gate('intent_corpus', all(corpus_gate(cases, e) for e in (checkout, clean)),
         'CASES.json (NL01–NL20); CHECKOUT.json; CLEANROOM.json',
         'Ровно 20 фраз, четыре режима различимы; неясный режим даёт вопрос о режиме, незаписываемый не читает и не получает билет. '
         'В трёх этапах нет побочных изменений, замен или попыток записи на корпусе.')
    gate('masked_witnesses', all(valid_previews(r) for r in (checkout, clean)),
         'CHECKOUT.json; CLEANROOM.json: NL01, NL02 и NL20',
         'Точные диффы по обоим слоям и контроль слов режима в данных; SHA-256, функции вывода и поля без билета.')
    gate('isolated', clean['files_before'] == clean['files_after'] == sorted(spec['target_inputs']) and clean['copy_unchanged'] is True,
         'ITERATION.json; CLEANROOM.json', 'В чистой копии ровно указанные входы, без Git/ISAI/донора, все побайтно прежние.')
    gate('repeat', checkout['sources_unchanged'] is True and clean['sources_unchanged'] is True
         and checkout['inputs_sha256'] == clean['inputs_sha256'] and encode(checkout['result']) == encode(clean['result']),
         'CHECKOUT.json; CLEANROOM.json', 'Два изолированных процесса дали равные обязательные наблюдения и входные хеши.')
    skipped = [dict(row, status='not run') for row in spec['not_run']]
    counts = tally(gates + skipped)
    return {'iteration': 'И-111', 'outcome': 'accepted' if counts['fail'] == 0 else 'rejected', 'counts': counts,
            'checks': gates, 'runs': runs, 'not_run': skipped,
            'host_os': checkout['result'].get('os') if type(checkout['result']) is dict else None}


def intents(cases, checkout, acceptance):
    data = {'iteration': 'И-111', 'source': 'CHECKOUT.json', 'phrases': None, 'metrics': None, 'previews': None, 'controls': None}
    if acceptance['outcome'] != 'accepted':
        return data
    rows = observations(checkout)
    phrases, false_writes = measured_corpus(cases, checkout)
    controls = {c['id']: rows[c['id']]['observed'] for c in cases if c['group'] == 'control'}
    plan_counts = Counter(r['plan'] for r in phrases)
    return dict(data, phrases=phrases, controls=controls, previews={i: rows[i]['preview'] for i in sorted(WITNESSES)}, metrics={
        'phrases': len(phrases), 'plan_outcomes': dict(plan_counts), 'false_write_cases': false_writes,
        'ambiguous_intent_questions': sum(r['category'] == 'ambiguous' and r['card']['questions'][0]['field'] == 'persistence' for r in phrases),
        'non_registry_reads': sum(r['plan_io']['reads'] for r in phrases if r['plan'] == 'non_registry'),
        'max_questions': max(len(s['card']['questions']) for row in rows.values() for s in row['observed']['steps']),
        'confirmed_replacements': sum(o['replacements'] for o in controls.values() if o['final']['outcome'] == 'applied')})


def generate(spec, *, measure_only):
    inputs = sources(ROOT, spec['target_inputs'])
    cases, red = load_cases(spec, inputs), sealing.read_json(HERE / 'RED.json')
    checkout, clean = measure(ROOT, inputs), clean_copy(inputs)
    accepted = accept(spec, cases, red, checkout, clean)
    data = intents(cases, checkout, accepted)
    for name, value in (('CHECKOUT', checkout), ('CLEANROOM', clean), ('ACCEPTANCE', accepted), ('INTENTS', data)):
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
    accepted, seal, data = get('ACCEPTANCE'), get('SEAL'), get('INTENTS')
    ok = (repeated['outcome'] == 'ok' and accepted['outcome'] == 'accepted' and encode(repeated) == encode(get('REPLAY'))
          and (HERE / sealing.page_name(spec)).read_bytes() == page(spec, accepted, data, seal, repeated).encode('utf-8'))
    sealing.emit({**repeated, 'record_and_page_match': ok})
    return 0 if ok else 1


def read_spec():
    spec = sealing.read_json(HERE / 'ITERATION.json')
    if spec['id'] != '111':
        raise ValueError('Ожидалась спецификация И-111')
    for field in ('target_inputs', 'seal_members'):
        names = spec[field]
        if (type(names) is not list or not names or names != sorted(set(names))
                or any(Path(n).as_posix() != n or sealing.repo_path(n) != ROOT / n for n in names)):
            raise ValueError('Неканонический список: ' + field)
    inputs, members = set(spec['target_inputs']), set(spec['seal_members'])
    required = {PREFIX + n for n in ('ITERATION.json', 'RED.json', 'REPORT.md', 'ACCEPTANCE.json', 'INTENTS.json',
                                     'CHECKOUT.json', 'CLEANROOM.json', 'run.py', 'render111.py')}
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
