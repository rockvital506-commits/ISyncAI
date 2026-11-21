#!/usr/bin/env python3
"""И-104: два целевых процесса, отдельный контроль, строгая приёмка и печать."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PRE = ROOT / 'research/strategy/pre-104'
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / 'research/strategy/harness'))
from accept import case_problems, encoded
from report104 import page, report
import run_iteration as sealing


def sha(data):
    return hashlib.sha256(data).hexdigest()


def run_json(root, script):
    result = subprocess.run([sys.executable, '-B', '-I', '-S', '-X', 'utf8', script], cwd=root,
                            capture_output=True, timeout=60)
    if result.stderr:
        sys.stderr.write(result.stderr.decode('utf-8', errors='replace'))
    try:
        value = json.loads(result.stdout)
    except ValueError:
        value = None
    return {'rc': result.returncode, 'result': value}


def snapshot(root, filenames):
    contents = {}
    for name in filenames:
        path = root / name
        if not path.is_file() or path.resolve() != path:
            raise ValueError(f'Ожидался обычный файл: {name}')
        contents[name] = path.read_bytes()
    return contents


def target(root, files):
    before = snapshot(root, files)
    measured = run_json(root, 'research/104/test_schema.py')
    return {'inputs_sha256': {name: sha(raw) for name, raw in before.items()},
            'inputs_unchanged': snapshot(root, files) == before, **measured}


def tree(root):
    return sorted(path.relative_to(root).as_posix() for path in root.rglob('*') if not path.is_dir())


def cleanroom(source):
    with tempfile.TemporaryDirectory(prefix='ack-i104-target-') as tmp:
        root = Path(tmp).resolve()
        for name, raw in source.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        before = tree(root)
        result = target(root, source)
        return {**result, 'files_before': before, 'files_after': tree(root),
                'donor_zip_present': any(root.rglob('AgentContractKit-0.1.36.zip')),
                'isai_present': (root / '.isai').exists() or any(root.rglob('isai'))}


def planned(cases):
    counts = Counter(row['expected']['ok'] for row in cases)
    return {'positive': counts[True], 'negative': counts[False]}


def tally(obs):
    result = obs['result']
    rows = result.get('rows') if type(result) is dict else None
    if type(rows) is not list:
        rows = []
    counts = Counter(row.get('status') for row in rows if type(row) is dict and type(row.get('status')) is str)
    return {key: counts[key] for key in ('pass', 'fail', 'not run')}


def accept(spec, casebook, checkout, clean, methods, donor):
    cases = casebook['cases']
    checks = []

    def check(name, ok, basis, criterion, detail=None):
        checks.append({'check': name, 'status': 'pass' if ok else 'fail',
                       'basis': basis, 'criterion': criterion, 'detail': detail})

    original = sealing.read_json(PRE / 'SCHEMA-CASES.json')
    listed = {row['id'] for row in original['cases'] if row['from_iteration'] == 'И-104'}
    covered = listed & {row['covers'] for row in cases}
    check('p2_casebook', sha((HERE / 'CASES.json').read_bytes()) == spec['casebook_sha256']
          and encoded(casebook['format']) == '1' and planned(cases) == spec['case_counts'] and covered == listed,
          'DESIGN.md; ITERATION.json; CASES.json; SCHEMA-CASES.json',
          'Список заморожен в П2; все 14 карточек И-104 разложены на обязательные случаи.', sorted(covered))
    for name, obs, file in (('checkout', checkout, 'CHECKOUT.json'), ('cleanroom', clean, 'CLEANROOM.json')):
        problems = case_problems(cases, obs['result'])
        check('target_' + name, obs['rc'] == 0 and not problems, 'CASES.json; ' + file,
              'Все обязательные ID ровно один раз; исход, тип, причина, путь и неизменность точны.',
              {'rc': obs['rc'], 'problems': problems})
    check('isolated_inputs', clean['files_before'] == clean['files_after'] == sorted(spec['target_inputs'])
          and clean['donor_zip_present'] is False and clean['isai_present'] is False,
          'ITERATION.json: target_inputs; CLEANROOM.json',
          'Чистая копия содержит только перечисленные входы; 0.1.36, ISAI и харнесс в неё не копируются.')
    check('source_repeat', checkout['inputs_unchanged'] is True and clean['inputs_unchanged'] is True
          and checkout['inputs_sha256'] == clean['inputs_sha256']
          and encoded(checkout['result']) == encoded(clean['result']),
          'CHECKOUT.json; CLEANROOM.json',
          'Входы по SHA-256 одинаковы и не меняются; результаты двух процессов совпадают.')
    expected_facts = {'entry_counts': {'L0': 2, 'L1': 3, 'L2': 2},
                      'candidate': {'id': 'R-2', 'kind': 'protocol', 'state': 'draft', 'parent': 'R-1'},
                      'candidate_body_sha256': sha((PRE / 'PHASED-PROMPT-PROTOCOL.md').read_bytes())}
    observed = checkout['result']
    check('filled_and_draft', type(observed) is dict and encoded(observed.get('schema_version')) == '2'
          and encoded(observed.get('facts')) == encoded(expected_facts),
          'CHECKOUT.json: facts; V01; PHASED-PROMPT-PROTOCOL.md',
          'Три наполненные области; текст кандидата точен, R-2 остаётся draft внутри R-1.')
    check('acceptance_selftest', methods['rc'] == 0 and encoded(methods['result']) == encoded(
          {'run': spec['method_tests'], 'fail': 0, 'errors': 0, 'skipped': 0}),
          'test_acceptance.py; ACCEPTANCE.json: checks',
          'Шлюз отклоняет пропуски, неверные ID, значения, типы и изменения входа.', methods)
    check('donor_control', donor['rc'] == 0 and donor['matches_saved_evidence'] is True,
          'DONOR-CONTROL.json; pre-104/EVIDENCE.json',
          'Отдельный закреплённый 0.1.36 повторяет черновик L2, отказ parent и неизменность его L0.')
    deferred = [dict(row, status='not run') for row in spec['not_run']]
    counts = Counter(row['status'] for row in checks + deferred)
    return {'iteration': 'И-104', 'phase': spec['phase'], 'outcome': 'rejected' if counts['fail'] else 'accepted',
            'checks': checks, 'not_run': deferred,
            'counts': {key: counts[key] for key in ('pass', 'fail', 'not run')},
            'target_cases': {'required_per_run': len(cases), **planned(cases),
                             'checkout': tally(checkout), 'cleanroom': tally(clean)}}


def generate(spec):
    # Список исполняемых проб локален: ITERATION.json не задаёт команды.
    paths = spec['target_inputs']
    if len(set(paths)) != len(paths) or any(sealing.repo_path(path) != ROOT / path for path in paths):
        raise ValueError('Неканонический список входов')
    source = snapshot(ROOT, paths)
    if sha(source['research/104/CASES.json']) != spec['casebook_sha256']:
        raise ValueError('Список обязательных случаев изменён после П2')
    casebook = json.loads(source['research/104/CASES.json'])
    checkout = target(ROOT, paths)
    clean = cleanroom(source)
    methods = run_json(ROOT, 'research/104/test_acceptance.py')
    donor = run_json(ROOT, 'research/strategy/pre-104/check_preparation.py')
    donor['matches_saved_evidence'] = encoded(donor['result']) == encoded(sealing.read_json(PRE / 'EVIDENCE.json'))
    result = accept(spec, casebook, checkout, clean, methods, donor)
    for name, data in (('CHECKOUT', checkout), ('CLEANROOM', clean), ('DONOR-CONTROL', donor), ('ACCEPTANCE', result)):
        sealing.dump_json(HERE / (name + '.json'), data)
    (HERE / 'REPORT.md').write_text(report(spec, result, casebook, checkout, clean, donor),
                                   encoding='utf-8', newline='\n')
    raw, seal = sealing.seal_bytes(spec)
    (HERE / seal['file']).write_bytes(raw)
    sealing.dump_json(HERE / 'SEAL.json', seal)
    replay = sealing.replay_seal(spec, HERE)
    sealing.dump_json(HERE / 'REPLAY.json', replay)
    (HERE / sealing.page_name(spec)).write_text(page(spec, result, donor, seal, replay),
                                                encoding='utf-8', newline='\n')
    sealing.emit({'outcome': result['outcome'], 'counts': result['counts'], 'target_cases': result['target_cases'],
                  'seal': seal, 'replay': replay['outcome']})
    return 0 if result['outcome'] == 'accepted' and replay['outcome'] == 'ok' else 1


def verify(spec):
    replay = sealing.replay_seal(spec, HERE)
    ok = replay['outcome'] == 'ok' and replay == sealing.read_json(HERE / 'REPLAY.json')
    if ok:
        expected = page(spec, sealing.read_json(HERE / 'ACCEPTANCE.json'), sealing.read_json(HERE / 'DONOR-CONTROL.json'),
                        sealing.read_json(HERE / 'SEAL.json'), replay)
        ok = (HERE / sealing.page_name(spec)).read_bytes() == expected.encode('utf-8')
    sealing.emit({**replay, 'record_and_page_match': ok})
    return 0 if ok else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-seal', action='store_true', help='Проверить печать и страницу без записи')
    args = parser.parse_args()
    try:
        spec = sealing.read_json(HERE / 'ITERATION.json')
        return verify(spec) if args.verify_seal else generate(spec)
    except (KeyError, OSError, TypeError, ValueError, subprocess.TimeoutExpired) as error:
        sealing.emit({'error': 'run_error', 'reason': str(error)})
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
