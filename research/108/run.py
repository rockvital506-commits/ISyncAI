#!/usr/bin/env python3
"""И-108: две целевые копии, строгая приёмка карточек, офлайн-печать."""
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
PROBE = 'research/108/test_cards.py'
CASEBOOK = 'research/108/CASES.json'
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / 'research/strategy/harness'))
import run_iteration as sealing  # Общий формат ZIP; evaluator 0.1.36 не запускается.
from render108 import page, report
from test_cards import case_checks, encode, snapshot


def sources(root, names):
    data = {}
    for n in names:
        path = root / n
        if not path.is_file() or path.resolve() != path:
            raise ValueError('Ожидался обычный вход: ' + n)
        data[n] = path.read_bytes()
    return data


def measure(root, initial):
    process = subprocess.run([sys.executable, '-B', '-I', '-S', '-X', 'utf8', PROBE], cwd=root,
                             capture_output=True, timeout=60)
    if process.stderr:
        sys.stderr.write(process.stderr.decode('utf-8', errors='replace'))
    try:
        result = json.loads(process.stdout)
    except ValueError:
        result = None
    return {'rc': process.returncode, 'result': result, 'sources_unchanged': sources(root, initial) == initial,
            'inputs_sha256': {n: sha256(raw).hexdigest() for n, raw in initial.items()}}


def clean_copy(inputs):
    with tempfile.TemporaryDirectory(prefix='ack-i108-inputs-') as tmp:
        root = Path(tmp).resolve()
        for n, raw in inputs.items():
            path = root / n
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        initial = snapshot(root)
        evidence = measure(root, sources(root, inputs))
        final = snapshot(root)
        files = lambda tree: sorted(n for n, state in tree.items() if state[0] != 'dir')
        return {**evidence, 'files_before': files(initial), 'files_after': files(final), 'copy_unchanged': initial == final}


def load_cases(spec, inputs):
    if (sha256(inputs[CASEBOOK]).hexdigest() != spec['casebook_sha256']
            or sha256(inputs[PROBE]).hexdigest() != spec['test_sha256']):
        raise ValueError('Входы отличаются от замороженного П2')
    book = json.loads(inputs[CASEBOOK])
    cases = book['cases']
    ids = [c['id'] for c in cases]
    texts = [c['request'] for c in cases]
    groups = Counter(c['group'] for c in cases)
    if (encode(book['format']) != b'1' or len(set(ids)) != len(cases) or len(set(texts)) != len(cases)
            or groups['nl'] != 12 or encode(dict(groups)) != encode(spec['case_counts'])
            or any(c['expected']['request'] != c['request'] for c in cases)):
        raise ValueError('Неполный или неоднозначный корпус П2')
    return cases


def tally(rows):
    counts = Counter(r['status'] for r in rows)
    return {status: counts[status] for status in ('pass', 'fail', 'not run')}


def accept(spec, cases, checkout, cleanroom):
    checks, runs = [], {}

    def gate(name, ok, basis, criterion):
        checks.append({'check': name, 'status': 'pass' if ok else 'fail', 'basis': basis, 'criterion': criterion})

    gate('frozen_cases', True, 'ITERATION.json; CASES.json; test_cards.py',
         'Хеши зафиксированы до кода; ID и формулировки различны; основной и контрольный наборы полны.')
    nl_ok = True
    for key, evidence, name in (('checkout', checkout, 'CHECKOUT.json'), ('cleanroom', cleanroom, 'CLEANROOM.json')):
        rows = case_checks(cases, evidence['result'])
        counts = tally(rows)
        groups = {g: tally(r for r in rows if r['group'] == g) for g in spec['case_counts']}
        runs[key] = {'cases': rows, 'counts': counts, 'groups': groups, 'rc': evidence['rc']}
        gate(key, encode(evidence['rc']) == b'0' and counts == {'pass': len(cases), 'fail': 0, 'not run': 0},
             name + '; test_cards.py: case_checks', 'Каждый обязательный ID один раз. Полная карточка и типы совпали; '
             'в обоих стендах ноль аудируемых обращений и ни одного изменения состава, байтов и меток файлов.')
        nl_ok &= groups['nl'] == {'pass': 12, 'fail': 0, 'not run': 0}
    gate('nl_12_without_guesses', nl_ok, 'CASES.json: NL01–NL12; CHECKOUT.json; CLEANROOM.json',
         '12 точных карточек в каждом прогоне, включая отсутствующие поля, код отказа, явные значения и лимит вопросов.')
    gate('isolated_copy', cleanroom['files_before'] == cleanroom['files_after'] == sorted(spec['target_inputs'])
         and cleanroom['copy_unchanged'] is True, 'ITERATION.json; CLEANROOM.json',
         'В П4 только перечисленные входы; нет Git, ISAI, 0.1.36, пользовательских профилей и новых файлов после прогона.')
    gate('repeat', checkout['sources_unchanged'] is True and cleanroom['sources_unchanged'] is True
         and checkout['inputs_sha256'] == cleanroom['inputs_sha256'] and encode(checkout['result']) == encode(cleanroom['result']),
         'CHECKOUT.json; CLEANROOM.json', 'Байты входов и все измерения совпали в двух независимых процессах.')
    skipped = [dict(item, status='not run') for item in spec['not_run']]
    counts = tally(checks + skipped)
    return {'iteration': 'И-108', 'outcome': 'rejected' if counts['fail'] else 'accepted', 'counts': counts,
            'checks': checks, 'runs': runs, 'not_run': skipped,
            'host_os': checkout['result'].get('os') if type(checkout['result']) is dict else None}


def collected(cases, checkout, acceptance):
    data = {'iteration': 'И-108', 'source': 'CHECKOUT.json: result.rows[].observed.empty.card', 'cards': [], 'metrics': None}
    if acceptance['outcome'] != 'accepted':
        return data
    rows = {row['id']: row['observed'] for row in checkout['result']['rows']}
    nl = [c for c in cases if c['group'] == 'nl']
    data['cards'] = [{'id': c['id'], 'basis': c['basis'], 'card': rows[c['id']]['empty']['card']} for c in nl]
    # В карточке-догадке есть неназванное либо иначе заданное действие или реквизит.
    def guess(card, expected):
        return (card['operation'] is not None and card['operation'] != expected['operation']) or any(
            k not in expected['params'] or encode(v) != encode(expected['params'][k]) for k, v in card['params'].items())

    data['metrics'] = {
        'nl_phrases': len(nl), 'nl_cards': len(data['cards']),
        'nl_outcomes': dict(Counter(r['card']['outcome'] for r in data['cards'])),
        'nl_silent_guesses': sum(any(guess(obs['card'], c['expected']) for obs in rows[c['id']].values()) for c in nl),
        'max_questions': max(len(r['card']['questions']) for m in rows.values() for r in m.values()),
        'compilations_per_run': sum(len(r) for r in rows.values()),
        'audited_io_events_per_run': sum(len(r['io_events']) for m in rows.values() for r in m.values()),
    }
    return data


def replay(spec):
    recorded = sealing.read_json(HERE / 'SEAL.json')
    raw, rebuilt = sealing.seal_bytes(spec)
    archived = (HERE / sealing.seal_name(spec)).read_bytes()
    return {'outcome': 'ok' if encode(recorded) == encode(rebuilt) and raw == archived else 'mismatch',
            'recorded_sha256': recorded.get('sha256') if type(recorded) is dict else None,
            'rebuilt_sha256': rebuilt['sha256'], 'archive_sha256': sha256(archived).hexdigest()}


def generate(spec, *, measure_only):
    inputs = sources(ROOT, spec['target_inputs'])
    cases = load_cases(spec, inputs)
    checkout, cleanroom = measure(ROOT, inputs), clean_copy(inputs)
    result = accept(spec, cases, checkout, cleanroom)
    cards = collected(cases, checkout, result)
    for name, payload in (('CHECKOUT', checkout), ('CLEANROOM', cleanroom), ('ACCEPTANCE', result), ('CARDS', cards)):
        sealing.dump_json(HERE / (name + '.json'), payload)
    (HERE / 'REPORT.md').write_text(report(spec, cases, checkout, result, cards), encoding='utf-8', newline='\n')
    summary = {'outcome': result['outcome'], 'counts': result['counts'], 'metrics': cards['metrics'],
               'runs': {k: r['counts'] for k, r in result['runs'].items()}}
    if result['outcome'] != 'accepted' or measure_only:
        sealing.emit(summary)
        return 1 if result['outcome'] == 'rejected' else 0
    raw, seal = sealing.seal_bytes(spec)
    (HERE / seal['file']).write_bytes(raw)
    sealing.dump_json(HERE / 'SEAL.json', seal)
    repeated = replay(spec)
    sealing.dump_json(HERE / 'REPLAY.json', repeated)
    (HERE / sealing.page_name(spec)).write_text(page(spec, result, cards, seal, repeated), encoding='utf-8', newline='\n')
    sealing.emit({**summary, 'seal': seal, 'replay': repeated['outcome']})
    return 0 if repeated['outcome'] == 'ok' else 1


def verify(spec):
    repeated = replay(spec)
    accepted = sealing.read_json(HERE / 'ACCEPTANCE.json')
    ok = (repeated['outcome'] == 'ok' and accepted['outcome'] == 'accepted'
          and encode(repeated) == encode(sealing.read_json(HERE / 'REPLAY.json')))
    if ok:
        expected = page(spec, accepted, sealing.read_json(HERE / 'CARDS.json'), sealing.read_json(HERE / 'SEAL.json'), repeated)
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
    excluded = {'research/108/' + n for n in ('SEAL.json', 'REPLAY.json', sealing.seal_name(spec), sealing.page_name(spec))}
    members, inputs = set(spec['seal_members']), set(spec['target_inputs'])
    if not {PROBE, CASEBOOK} <= inputs <= members or members & excluded:
        raise ValueError('Утеряны входы или печать включает саму себя')
    return spec


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--measure-only', action='store_true', help='П3–П6 без печати и страницы')
    group.add_argument('--verify-seal', action='store_true', help='Сверить печать и страницу без записи')
    args = parser.parse_args()
    try:
        spec = read_spec()
        return verify(spec) if args.verify_seal else generate(spec, measure_only=args.measure_only)
    except (KeyError, OSError, TypeError, ValueError, subprocess.TimeoutExpired) as error:
        sealing.emit({'error': 'run_error', 'reason': str(error)})
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
