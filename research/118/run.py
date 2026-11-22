#!/usr/bin/env python3
"""И-118: независимые прогоны, приёмка и воспроизводимая исследовательская печать."""
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
PREFIX = 'research/118/'
PROBE = PREFIX + 'test_bundle_verify.py'
sys.dont_write_bytecode = True
sys.path[:0] = [str(HERE), str(ROOT/'research/strategy/harness')]
import run_iteration as seal_io
from render118 import page, report
from test_bundle_verify import BOOK, MODULE, SOURCE, canonical, context, expected_observation

PINNED = sorted([SOURCE, *('kit/base/' + n for n in ('profile_journal.py', 'registry_journal.py', 'registry_policy.py', 'schema_v2.py'))])
TARGETS = sorted([*PINNED, BOOK, PROBE, MODULE, 'kit/base/BUNDLE-VERIFY.md'])
OUTPUTS = ('CHECKOUT', 'CLEANROOM', 'ACCEPTANCE', 'VERIFICATION')
STATUSES = ('pass', 'fail', 'not run')
SOURCE_SHA256 = '5c95478a90f6328c21068527d44ed35462f1a5f36b8120835b49ef85f86494d3'
SOURCE_DIGEST = '300af66638088f51fc2e079d2cbf75bc30144f62f2e0c5ef8a12b6a7fc54bee5'
CONTROL = {'source_sha256': SOURCE_SHA256, 'source_members': 17, 'bare_revisions': [7, 0], 'history_formats': [1, 2],
           'working_port': {'bundle': 'unknown_operation', 'bundle_verify': 'unknown_operation'}}
GROUPS = {'P': 6, 'T': 16, 'A': 16, 'M': 16, 'B': 16, 'N': 46}
CASE_IDS = [f'{group}{n:02}' for group, count in GROUPS.items() for n in range(1, count+1)]


def read(name):
    return seal_io.read_json(HERE/(name + '.json'))


def take(root, names):
    inputs = {}
    for n in names:
        f = root/n
        if f.resolve() != f or not f.is_file():
            raise ValueError('ordinary_input_required')
        inputs[n] = f.read_bytes()
    return inputs


def hashes(files):
    return {n: sha256(b).hexdigest() for n, b in files.items()}


def load():
    spec = read('ITERATION')
    members = sorted([*TARGETS, *(PREFIX + n + '.json' for n in OUTPUTS),
                      *(PREFIX + n for n in ('DESIGN.md', 'ITERATION.json', 'RED.json', 'run.py', 'render118.py', 'REPORT.md')),
                      'research/STRATEGY.md', 'research/strategy/SYNC-LOG.md',
                      *('research/strategy/harness/' + n for n in ('run_iteration.py', 'render.py', 'probes.py'))])
    if (spec['id'] != '118' or spec['target_inputs'] != TARGETS or spec['seal_members'] != members or spec['case_ids'] != CASE_IDS
            or spec['command'] != ['-B', '-I', '-S', '-X', 'utf8', PROBE] or canonical(spec['expected_control']) != canonical(CONTROL)
            or any(seal_io.repo_path(n) != ROOT/n for n in members)):
        raise ValueError('spec_contract')
    inputs = take(ROOT, TARGETS); h = hashes(inputs)
    if (h[BOOK] != spec['casebook_sha256'] or h[PROBE] != spec['test_sha256'] or h[SOURCE] != SOURCE_SHA256
            or {n: h[n] for n in PINNED} != spec['pinned_inputs']):
        raise ValueError('input_drift')
    book = json.loads(inputs[BOOK]); cases = book['cases']; paths = book['required']
    if (canonical(book['format']) != b'1' or book['baseline'] != spec['baseline'] or [c['id'] for c in cases] != CASE_IDS
            or len(paths) != len(set(paths)) or len(paths) != 16 or paths != sorted(paths) or set(book['vectors']) != set(CASE_IDS)
            or any([c.get('path') for c in cases if c['id'].startswith(k)] != paths for k in ('T', 'A', 'M', 'B'))):
        raise ValueError('casebook_contract')
    context(book)  # независимо проверить закреплённый образец, не вызывать продукт
    return spec, book, read('RED'), inputs


def measure(root, spec, inputs):
    before = take(root, inputs)
    if before != inputs:
        raise ValueError('different_inputs')
    p = subprocess.run([sys.executable, *spec['command']], cwd=root, capture_output=True, timeout=45)
    try:
        result = json.loads(p.stdout)
    except ValueError:
        result = None
    return {'rc': p.returncode, 'stderr_empty': not p.stderr, 'result': result, 'inputs_sha256': hashes(before),
            'inputs_unchanged': take(root, inputs) == before}


def clean_copy(spec, inputs):
    with TemporaryDirectory(prefix='ack-i118-inputs-') as folder:
        work = Path(folder).resolve()
        for n, data in inputs.items():
            f = work/n; f.parent.mkdir(parents=True, exist_ok=True); f.write_bytes(data)

        def snapshot():
            return {f.relative_to(work).as_posix(): (st.st_mode, st.st_ino, st.st_size, st.st_mtime_ns)
                    for f in work.rglob('*') for st in (f.lstat(),)}

        before = snapshot(); observed = measure(work, spec, inputs)
        return dict(observed, files=sorted(n for n in before if (work/n).is_file()), tree_unchanged=before == snapshot())


def tally(rows):
    actual = Counter(row['status'] for row in rows)
    return {k: actual[k] for k in STATUSES}


def header(data):
    return (type(data) is dict and data.keys() == {'format', 'os', 'python', 'control', 'counts', 'rows'}
            and canonical(data['format']) == b'1' and canonical(data['control']) == canonical(CONTROL)
            and all(type(data[k]) is str and data[k] for k in ('os', 'python')))


def red_matches(spec, red):
    d = red['result']
    return (red['independent_baseline_match'] is True and red['stderr_empty'] is True and canonical(red['rc']) == b'1'
            and all(red[k] == spec[k] for k in ('baseline', 'command', 'casebook_sha256', 'test_sha256', 'pinned_inputs'))
            and header(d) and canonical(d['counts']) == canonical({'pass': 0, 'fail': len(CASE_IDS), 'not run': 0})
            and d['rows'] == [{'id': i, 'status': 'fail', 'reason': 'bundle_verify_missing'} for i in CASE_IDS])


def validate_run(book, evidence):
    result = evidence['result']; rows = result.get('rows') if type(result) is dict else None
    seen = {}
    if type(rows) is list:
        for row in rows:
            if type(row) is dict and type(row.get('id')) is str:
                seen.setdefault(row['id'], []).append(row)
    checks = []
    for c in book['cases']:
        options = seen.get(c['id'], [])
        expected = {'id': c['id'], 'status': 'pass', 'observation': expected_observation(book, c)}
        status = ('not run' if not options else
                  'pass' if len(options) == 1 and canonical(options[0]) == canonical(expected) else 'fail')
        checks.append({**{k: c[k] for k in ('id', 'basis', 'criterion')}, 'status': status})
    counts = tally(checks)
    ok = (canonical(evidence['rc']) == b'0' and evidence['stderr_empty'] is True and header(result)
          and type(rows) is list and [r.get('id') if type(r) is dict else None for r in rows] == CASE_IDS
          and canonical(result['counts']) == canonical(counts) and counts == {'pass': len(CASE_IDS), 'fail': 0, 'not run': 0})
    return ok, {'rc': evidence['rc'], 'counts': counts, 'cases': checks}


def summarize(book, observed):
    seen = {r['id']: r['observation'] for r in observed['rows']}
    rows = [{**{k: c[k] for k in ('id', 'basis', 'criterion', 'variant')}, 'input': book['vectors'][c['id']]['input'],
             **seen[c['id']]} for c in book['cases']]
    errs = Counter(r['error']['code'] for r in rows if r['error'])
    metrics = {'cases': len(rows), 'verified': sum(r['verified'] is not None for r in rows), 'refused': sum(errs.values()),
               'by_code': dict(errs), 'no_archive_open': sum(r['archives'] == 0 for r in rows),
               'no_member_read': sum(r['reads'] == 0 for r in rows), 'archive_attempts': sum(r['archives'] for r in rows),
               'member_reads': sum(r['reads'] for r in rows), 'effect_attempts': sum(len(r['effects']) for r in rows),
               'quiet_and_unchanged': all(r['quiet'] and r['input_unchanged'] for r in rows)}
    return {'iteration': 'И-118', 'basis': 'CASES.json; CHECKOUT.json; CLEANROOM.json', 'source': book['source'],
            'reference': seen['P01']['verified'], 'independent_rehash': seen['P03']['verified'], 'metrics': metrics, 'rows': rows}


def accept(spec, book, red, inputs, checkout, clean):
    checks, runs, ready = [], {}, []

    def gate(name, ok, basis, criterion):
        checks.append({'check': name, 'status': 'pass' if ok else 'fail', 'basis': basis, 'criterion': criterion})

    gate('frozen_red', red_matches(spec, red), 'ITERATION.json; CASES.json; RED.json',
         'Оракул, исходный пример и эталоны закреплены до продукта; RED 0/116/0 совпал с Git-снимком.')
    for name, evidence in (('checkout', checkout), ('cleanroom', clean)):
        ok, runs[name] = validate_run(book, evidence); ready.append(ok)
        gate(name, ok, f'{name.upper()}.json; CASES.json; test_bundle_verify.py',
             'Каждая обязательная строка сопоставлена по ID, статусу, выводу и эффектам; rc0, без stderr.')
    info = summarize(book, checkout['result']) if all(ready) else None
    rows = {r['id']: r for r in info['rows']} if info else {}
    m = info['metrics'] if info else {}

    def all_in(k, code, reads=None):
        matches = [r for n, r in rows.items() if n.startswith(k)]
        return len(matches) == GROUPS[k] and all(r['error']['code'] == code and r['verified'] is None
                                               and (reads is None or r['reads'] == reads) for r in matches)

    gate('valid_bundles_and_source', bool(m) and m['verified'] == 6
         and info['reference']['archive_sha256'] == SOURCE_SHA256 and info['reference']['manifest_digest'] == SOURCE_DIGEST
         and [rows[n]['verified']['revision'] for n in ('P01', 'P02', 'P04', 'P05', 'P06')] == [7, 0, 7, 8, 7],
         'P01/P02/P04–P06; Synthetic-Bundle-117.zip; закреплённые векторы',
         'Приняты исходный пример, пустой L1, иные байты JSON, новая ревизия и точная граница 1/4 МиБ.')
    gate('tamper_each_file', bool(m) and all_in('T', 'digest_mismatch')
         and all(r['error']['details']['reason'] == 'sha256' and r['input']['bytes'] == info['source']['bytes']
                 for n, r in rows.items() if n.startswith('T')),
         'T01–T16; CASES.json; N33–N35', 'Один байт каждого файла при правильном CRC и старой заявке — отказ SHA-256; размер и digest проверяются отдельно.')
    gate('both_directions', bool(m) and all(all_in(k, 'bundle_incomplete', n) for k, n in (('A', 0), ('M', 1), ('B', 0))),
         'A01–A16/M01–M16/B01–B16; N09–N14', '48 пропусков: из ZIP, манифеста и обоих. Лишнее или повторённое имя не покрывается digest.')
    gate('bounds_before_payload', bool(m) and m['no_member_read'] == 56 and m['no_archive_open'] == 9
         and all(rows[n]['reads'] == 0 for n in ('N16', 'N17', 'N18', 'N19', 'N21', 'N22', 'N23', 'N45', 'N46')),
         'N01–N08/N15–N23/N44–N46; Monitor', 'Ограничиваем части до чтения; не извлекаем ссылки, не декомпрессируем, не открываем вход-путь.')
    gate('registry_binding', bool(m) and all(rows[n]['error']['code'] == 'bundle_incomplete' and rows[n]['reads'] == 17
                                             for n in ('N36', 'N37', 'N38', 'N39', 'N40', 'N41', 'N42')),
         'N36–N42; положительный контроль истории; v2', 'Самосогласованный ZIP не заменяет проверку двух реестров, корней, A4 и соответствия revision.')
    gate('not_a_trust_claim', bool(m) and info['reference']['revision'] == info['independent_rehash']['revision'] == 7
         and all(info['reference'][k] != info['independent_rehash'][k] for k in ('manifest_digest', 'archive_sha256')),
         'P01/P03; T01–T16', 'Изменение файла и пересчёт всего манифеста может пройти как целостность, не подлинность.')
    gate('no_effects_or_partial_result', bool(m) and m['effect_attempts'] == 0 and m['quiet_and_unchanged']
         and m['by_code'] == {'bundle_incomplete': 91, 'digest_mismatch': 19}
         and m['archive_attempts'] == 107 and m['member_reads'] == 412
         and all(r['verified'] is None for r in rows.values() if r['error']),
         'Оба прогона; Monitor; VERIFICATION.json', 'Нет попыток I/O, запуска, записи ZIP или вывода; отказ не выдаёт полезные байты и частичный результат.')
    gate('fresh_copy', clean['files'] == TARGETS and clean['tree_unchanged'] is True,
         'ITERATION.json; CLEANROOM.json', 'В новой копии ровно девять входов; Git, донор и рабочие профили отсутствуют.')
    gate('repeat', all(ready) and checkout['inputs_unchanged'] is True and clean['inputs_unchanged'] is True
         and checkout['inputs_sha256'] == clean['inputs_sha256'] == hashes(inputs) and canonical(checkout['result']) == canonical(clean['result']),
         'CHECKOUT.json; CLEANROOM.json', 'Повтор из заявленных байтов дал те же значения всех наблюдений.')
    deferred = [dict(row, status='not run') for row in spec['not_run']]
    counts = tally(checks + deferred)
    data = checkout['result'] if type(checkout['result']) is dict else {}
    verdict = {'iteration': 'И-118', 'outcome': 'accepted' if not counts['fail'] else 'rejected', 'counts': counts,
               'checks': checks, 'runs': runs, 'not_run': deferred, 'os': data.get('os'), 'python': data.get('python'),
               'scope': 'П5 · целостность ZIP И-117, не подпись, установка или произвольный ZIP'}
    return verdict, info if not counts['fail'] else {'iteration': 'И-118', 'metrics': None, 'rows': None}


def replay(spec):
    raw, expected = seal_io.seal_bytes(spec)
    record = read('SEAL'); stored = (HERE/expected['file']).read_bytes()
    return {'outcome': 'ok' if stored == raw and canonical(record) == canonical(expected) else 'mismatch',
            'archive_sha256': sha256(stored).hexdigest(), 'recorded_sha256': record.get('sha256'), 'rebuilt_sha256': expected['sha256']}


def generate(spec, book, red, inputs, *, measure_only):
    checkout, clean = measure(ROOT, spec, inputs), clean_copy(spec, inputs)
    verdict, info = accept(spec, book, red, inputs, checkout, clean)
    for name, payload in zip(OUTPUTS, (checkout, clean, verdict, info)):
        seal_io.dump_json(HERE/(name + '.json'), payload)
    (HERE/'REPORT.md').write_text(report(spec, red, verdict, info), encoding='utf-8', newline='\n')
    summary = {'outcome': verdict['outcome'], 'counts': verdict['counts'], 'metrics': info['metrics'],
               'runs': {k: v['counts'] for k, v in verdict['runs'].items()}}
    if measure_only or verdict['outcome'] != 'accepted':
        seal_io.emit(summary)
        return int(verdict['outcome'] != 'accepted')
    raw, seal = seal_io.seal_bytes(spec)
    (HERE/seal['file']).write_bytes(raw)
    seal_io.dump_json(HERE/'SEAL.json', seal)
    result = replay(spec)
    seal_io.dump_json(HERE/'REPLAY.json', result)
    (HERE/seal_io.page_name(spec)).write_text(page(spec, verdict, info, seal, result), encoding='utf-8', newline='\n')
    seal_io.emit(dict(summary, seal=seal, replay=result['outcome']))
    return int(result['outcome'] != 'ok')


def verify(spec, book, red, inputs):
    rep = replay(spec)
    verdict, info = accept(spec, book, red, inputs, read('CHECKOUT'), read('CLEANROOM'))
    ok = (rep['outcome'] == 'ok' and verdict['outcome'] == 'accepted' and canonical(rep) == canonical(read('REPLAY'))
          and canonical(verdict) == canonical(read('ACCEPTANCE')) and canonical(info) == canonical(read('VERIFICATION'))
          and (HERE/'REPORT.md').read_bytes() == report(spec, red, verdict, info).encode('utf-8')
          and (HERE/seal_io.page_name(spec)).read_bytes() == page(spec, verdict, info, read('SEAL'), rep).encode('utf-8'))
    seal_io.emit(dict(rep, source_sha256=SOURCE_SHA256, record_and_page_match=ok))
    return int(not ok)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--measure-only', action='store_true', help='П3–П6 без печати')
    mode.add_argument('--verify-seal', action='store_true', help='Сверка печати, записей и страницы без записи')
    args = parser.parse_args()
    try:
        params = load()
        return verify(*params) if args.verify_seal else generate(*params, measure_only=args.measure_only)
    except (AssertionError, AttributeError, IndexError, KeyError, OSError, TypeError, ValueError, subprocess.TimeoutExpired) as exc:
        seal_io.emit({'outcome': 'rejected', 'error': type(exc).__name__})
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
