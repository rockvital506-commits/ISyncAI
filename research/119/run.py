#!/usr/bin/env python3
"""И-119: два прогона, приёмка и воспроизводимая исследовательская печать."""
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
P = 'research/119/'
sys.dont_write_bytecode = True
sys.path[:0] = [str(HERE), str(ROOT/'research/strategy/harness')]
import run_iteration as io
from render119 import report, page
from test_bundle_trust import BOOK, MODULE, SOURCE, TEST, canonical, expected_observation, setup

PINNED = sorted([SOURCE, *('kit/base/' + n for n in ('bundle_verify.py', 'schema_v2.py', 'profile_journal.py', 'registry_policy.py'))])
INPUTS = sorted([*PINNED, BOOK, TEST, MODULE, 'kit/base/BUNDLE-TRUST.md'])
COUNTS = ('pass', 'fail', 'not run')
OUTPUTS = ('CHECKOUT', 'CLEANROOM', 'ACCEPTANCE', 'TRUST')
IDS = [f'{k}{i:02}' for k, n in (('U', 11), ('S', 17), ('I', 5), ('N', 18)) for i in range(1, n+1)]
PASSED = {'pass': len(IDS), 'fail': 0, 'not run': 0}
REF_SHA = '5c95478a90f6328c21068527d44ed35462f1a5f36b8120835b49ef85f86494d3'
ALT_SHA = 'aeb8d8224efe9dc606193d159f3b405ad780e64cdee85a4d7591ce4afd740c4f'


def read(name):
    return io.read_json(HERE/(name + '.json'))


def inputs(root, names):
    result = {}
    for n in names:
        f = root/n
        if f.resolve() != f or not f.is_file():
            raise ValueError('ordinary_file_required')
        result[n] = f.read_bytes()
    return result


def hashes(files):
    return {n: sha256(b).hexdigest() for n, b in files.items()}


def load():
    s = read('ITERATION')
    members = sorted([*INPUTS, *(P+n+'.json' for n in OUTPUTS),
                      *(P+n for n in ('DESIGN.md', 'ITERATION.json', 'RED.json', 'run.py', 'render119.py', 'REPORT.md')),
                      'research/STRATEGY.md', 'research/strategy/SYNC-LOG.md',
                      *('research/strategy/harness/'+n for n in ('run_iteration.py', 'render.py', 'probes.py'))])
    if (s['id'] != '119' or s['case_ids'] != IDS or s['target_inputs'] != INPUTS or s['seal_members'] != members
            or s['command'] != ['-B', '-I', '-S', '-X', 'utf8', TEST]
            or any(io.repo_path(n) != ROOT/n for n in members)):
        raise ValueError('iteration_contract')
    files = inputs(ROOT, INPUTS); h = hashes(files)
    if (h[BOOK] != s['casebook_sha256'] or h[TEST] != s['test_sha256'] or h[SOURCE] != REF_SHA
            or {n: h[n] for n in PINNED} != s['pinned_inputs']):
        raise ValueError('input_drift')
    book = json.loads(files[BOOK]); ctl = s['expected_control']
    wanted = {'openssl': ctl['openssl'], 'rfc_public_vector': True, 'source_sha256': REF_SHA, 'reference_signatures_valid': 2,
              'mismatches_rejected': 4, 'working_port': dict.fromkeys(('bundle', 'bundle_verify', 'assess_bundle_trust'), 'unknown_operation')}
    if (canonical(book['format']) != b'1' or book['baseline'] != s['baseline'] or [c['id'] for c in book['cases']] != IDS
            or canonical(ctl) != canonical(wanted) or not ctl['openssl'].startswith('OpenSSL ')
            or [book['integrity'][k]['archive_sha256'] for k in ('source', 'alternate')] != [REF_SHA, ALT_SHA]):
        raise ValueError('corpus_contract')
    setup(book)  # Проверка закреплённых входов без запуска OpenSSL и без продукта И-119.
    return s, book, read('RED'), files


def measure(root, s, files):
    before = inputs(root, files)
    if before != files:
        raise ValueError('different_inputs')
    p = subprocess.run([sys.executable, *s['command']], cwd=root, capture_output=True, timeout=45)
    try:
        result = json.loads(p.stdout)
    except ValueError:
        result = None
    return {'rc': p.returncode, 'stderr_empty': not p.stderr, 'inputs_sha256': hashes(before),
            'inputs_unchanged': inputs(root, files) == before, 'result': result}


def cleanroom(s, files):
    with TemporaryDirectory(prefix='ack-i119-inputs-') as d:
        root = Path(d).resolve()
        for n, data in files.items():
            f = root/n; f.parent.mkdir(parents=True, exist_ok=True); f.write_bytes(data)

        def snapshot():
            return {f.relative_to(root).as_posix(): (st.st_mode, st.st_ino, st.st_mtime_ns, st.st_size)
                    for f in root.rglob('*') for st in (f.lstat(),)}

        before = snapshot(); evidence = measure(root, s, files)
        return dict(evidence, files=sorted(n for n in before if (root/n).is_file()), tree_unchanged=snapshot() == before)


def tally(rows):
    c = Counter(r['status'] for r in rows)
    return {k: c[k] for k in COUNTS}


def header(s, data):
    return (type(data) is dict and data.keys() == {'format', 'control', 'os', 'python', 'rows', 'counts'}
            and canonical(data['format']) == b'1' and canonical(data['control']) == canonical(s['expected_control'])
            and all(type(data[k]) is str and data[k] for k in ('os', 'python')))


def accepted_red(s, red):
    d = red['result']
    return (red['independent_baseline_match'] is True and red['stderr_empty'] is True and canonical(red['rc']) == b'1'
            and all(red[k] == s[k] for k in ('baseline', 'command', 'casebook_sha256', 'test_sha256', 'pinned_inputs'))
            and header(s, d) and canonical(d['counts']) == canonical({'pass': 0, 'fail': len(IDS), 'not run': 0})
            and d['rows'] == [dict(id=n, status='fail', reason='bundle_trust_missing') for n in IDS])


def accepted_run(s, book, evidence):
    d = evidence['result']; rows = d.get('rows') if type(d) is dict else None; seen = {}
    if type(rows) is list:
        for r in rows:
            if type(r) is dict and type(r.get('id')) is str:
                seen.setdefault(r['id'], []).append(r)
    checks = []
    for c in book['cases']:
        matches = seen.get(c['id'], [])
        want = dict(id=c['id'], status='pass', observation=expected_observation(book, c))
        state = 'not run' if not matches else 'pass' if len(matches) == 1 and canonical(matches[0]) == canonical(want) else 'fail'
        checks.append({**{k: c[k] for k in ('id', 'basis', 'criterion')}, 'status': state})
    count = tally(checks)
    ok = (canonical(evidence['rc']) == b'0' and evidence['stderr_empty'] is True and header(s, d)
          and type(rows) is list and [r.get('id') if type(r) is dict else None for r in rows] == IDS
          and canonical(d['counts']) == canonical(count) and count == PASSED)
    return ok, {'rc': evidence['rc'], 'counts': count, 'cases': checks}


def summary(book, observed):
    found = {r['id']: r['observation'] for r in observed['rows']}
    rows = [{**{k: c[k] for k in ('id', 'archive', 'variant', 'basis', 'criterion')}, **found[c['id']]} for c in book['cases']]
    assessed = [r['result'] for r in rows if r['result']]
    metrics = {'cases': len(rows), 'assessed': len(assessed), 'refused': len(rows)-len(assessed),
               'by_signature': dict(Counter(r['signature_status'] for r in assessed)),
               'by_decision': dict(Counter(r['policy_decision'] for r in assessed)),
               'by_error': dict(Counter(r['error']['code'] for r in rows if r['error'])),
               'verifier_calls': sum(r['order'].count('verifier') for r in rows),
               'effect_attempts': sum(len(r['effects']) for r in rows),
               'quiet_and_unchanged': all(r['quiet'] and r['unchanged'] for r in rows)}
    return {'iteration': 'И-119', 'basis': 'CASES.json; CHECKOUT.json; CLEANROOM.json', 'metrics': metrics,
            'references': book['integrity'], 'public_key_id': book['public']['key_id'], 'rows': rows}


def accept(s, book, red, files, checkout, clean):
    gates, ready, runs = [], [], {}

    def gate(name, ok, basis, criterion):
        gates.append(dict(check=name, status='pass' if ok else 'fail', basis=basis, criterion=criterion))

    gate('frozen_red', accepted_red(s, red), 'CASES.json; RED.json; ITERATION.json', 'Открытые векторы закреплены до продукта; RED 0/51/0 подтверждён из Git-снимка.')
    for name, result in (('checkout', checkout), ('cleanroom', clean)):
        ok, runs[name] = accepted_run(s, book, result); ready.append(ok)
        gate(name, ok, f'{name.upper()}.json; CASES.json', 'Все строки, порядок и диагностики совпали с независимым оракулом; rc0 без stderr.')
    info = summary(book, checkout['result']) if all(ready) else None
    rows = {r['id']: r for r in info['rows']} if info else {}; m = info['metrics'] if info else {}

    def decision(n, state, verdict, reason):
        obs = rows[n]['result']
        return (obs['signature_status'], obs['policy_decision'], obs['reason']) == (state, verdict, reason)

    gate('integrity_first', bool(m) and m['by_error'] == {'digest_mismatch': 2, 'bundle_incomplete': 3, 'bundle_trust_invalid': 18}
         and all(rows[n]['order'] == ['integrity'] and rows[n]['result'] is None for n in IDS if n.startswith('I')),
         'I01–I05; неизменная И‑118', 'Подмена/неполнота возвращается раньше политики; ни подпись, ни исключение их не отменяют.')
    gate('unsigned_is_separate', bool(m) and m['by_signature']['unsigned'] == 11
         and decision('U01', 'unsigned', 'optional', 'signature_optional')
         and decision('U02', 'unsigned', 'blocked', 'signature_required'),
         'U01/U02; P9 стратегии; I01/I02', 'Нет подписи не означает ошибку хеша и блокирует только согласно переданной политике.')
    gate('exception_scope_time_authority', bool(m) and all(decision(n, 'unsigned', 'exception', 'exception_active') for n in ('U03', 'U11'))
         and all(decision(n, 'unsigned', 'blocked', 'exception_expired') for n in ('U04', 'U05'))
         and all(decision(n, 'unsigned', 'blocked', 'exception_approver') for n in ('U06', 'U10'))
         and all(decision(n, 'unsigned', 'blocked', 'signature_required') for n in ('U07', 'U08')),
         'U03–U11; N10–N18', 'Действуют только точный SHA ZIP, разрешённый approver и now < expiry; digest манифеста не заменяет SHA ZIP.')
    gate('real_signature_binding', bool(m) and m['by_signature']['trusted_signature'] == 2
         and all(decision(n, 'trusted_signature', 'satisfied', 'signature_verified') for n in ('S01', 'S02'))
         and all(decision(n, 'signature_invalid', 'blocked', 'mismatch') for n in ('S04', 'S05', 'S06', 'S17')),
         'S01/S02/S04–S06/S17; контроль RFC 8032 §7.1', 'OpenSSL принимает две подписи, но не их изменение, обмен ZIP или другого ключа.')
    gate('fail_closed', bool(m) and decision('S03', 'untrusted_signer', 'blocked', 'key_not_approved')
         and all(decision(n, 'signature_unchecked', 'blocked', reason)
                 for n, reason in zip(('S13', 'S14', 'S15'), ('verifier_unavailable', 'verifier_error', 'verifier_result'))),
         'S03/S07–S17', 'Чужой ключ и неисправный проверяющий не дают доверия и не становятся unsigned.')
    gate('config_exact', bool(m) and all(rows[n]['error']['code'] == 'bundle_trust_invalid' and rows[n]['result'] is None
                                        for n in IDS if n.startswith('N')),
         'N01–N18', 'Некорректная политика, время и реестр исключений отклоняются без подбора значений.')
    gate('no_effects', bool(m) and m['effect_attempts'] == 0 and m['quiet_and_unchanged'] and m['verifier_calls'] == 8
         and m['by_decision'] == {'blocked': 22, 'optional': 2, 'exception': 2, 'satisfied': 2},
         'Monitor; оба прогона', 'Только 8 явных вызовов проверяющего; нет побочного I/O модуля, вывода, изменений входов или частичного допуска.')
    gate('fresh_copy', clean['tree_unchanged'] is True and clean['files'] == INPUTS,
         'ITERATION.json; CLEANROOM.json', 'В новой копии только девять входов, без рабочего профиля, Git и закрытого ключа.')
    gate('repeat', all(ready) and checkout['inputs_unchanged'] is True and clean['inputs_unchanged'] is True
         and checkout['inputs_sha256'] == clean['inputs_sha256'] == hashes(files)
         and canonical(checkout['result']) == canonical(clean['result']),
         'CHECKOUT.json; CLEANROOM.json', 'Байты входов и все наблюдения совпадают в двух процессах.')
    deferred = [dict(row, status='not run') for row in s['not_run']]
    counts = tally(gates + deferred); obs = checkout['result'] if type(checkout['result']) is dict else {}
    result = {'iteration': 'И-119', 'outcome': 'accepted' if not counts['fail'] else 'rejected',
              'counts': counts, 'checks': gates, 'runs': runs, 'not_run': deferred, 'os': obs.get('os'), 'python': obs.get('python'),
              'scope': 'П5 · диагностика явно заданной доверенной политики на синтетических данных'}
    return result, info if not counts['fail'] else {'iteration': 'И-119', 'metrics': None, 'rows': None}


def replay(s):
    raw, expected = io.seal_bytes(s); record = read('SEAL'); saved = (HERE/expected['file']).read_bytes()
    return {'outcome': 'ok' if saved == raw and canonical(record) == canonical(expected) else 'mismatch',
            'recorded_sha256': record.get('sha256'), 'archive_sha256': sha256(saved).hexdigest(), 'rebuilt_sha256': expected['sha256']}


def generate(s, book, red, files, only_measure):
    checkout, clean = measure(ROOT, s, files), cleanroom(s, files)
    a, info = accept(s, book, red, files, checkout, clean)
    for name, result in zip(OUTPUTS, (checkout, clean, a, info)):
        io.dump_json(HERE/(name+'.json'), result)
    (HERE/'REPORT.md').write_text(report(s, red, a, info), encoding='utf-8', newline='\n')
    facts = dict(outcome=a['outcome'], counts=a['counts'], metrics=info['metrics'], runs={n:r['counts'] for n,r in a['runs'].items()})
    if only_measure or a['outcome'] != 'accepted':
        io.emit(facts); return int(a['outcome'] != 'accepted')
    raw, seal = io.seal_bytes(s); (HERE/seal['file']).write_bytes(raw); io.dump_json(HERE/'SEAL.json', seal)
    rep = replay(s); io.dump_json(HERE/'REPLAY.json', rep)
    (HERE/io.page_name(s)).write_text(page(s, a, info, seal, rep), encoding='utf-8', newline='\n')
    io.emit(dict(facts, seal=seal, replay=rep['outcome']))
    return int(rep['outcome'] != 'ok')


def verify(s, book, red, files):
    rep = replay(s); a, info = accept(s, book, red, files, read('CHECKOUT'), read('CLEANROOM'))
    ok = (rep['outcome'] == 'ok' and a['outcome'] == 'accepted' and canonical(rep) == canonical(read('REPLAY'))
          and canonical(a) == canonical(read('ACCEPTANCE')) and canonical(info) == canonical(read('TRUST'))
          and (HERE/'REPORT.md').read_bytes() == report(s, red, a, info).encode('utf-8')
          and (HERE/io.page_name(s)).read_bytes() == page(s, a, info, read('SEAL'), rep).encode('utf-8'))
    io.emit(dict(rep, record_and_page_match=ok)); return int(not ok)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--measure-only', action='store_true', help='П3–П6 без печати')
    modes.add_argument('--verify-seal', action='store_true', help='Сверка печати и записей без записи')
    args = parser.parse_args()
    try:
        s, book, red, files = load()
        return verify(s, book, red, files) if args.verify_seal else generate(s, book, red, files, args.measure_only)
    except (AssertionError, AttributeError, IndexError, KeyError, OSError, TypeError, ValueError, subprocess.TimeoutExpired) as exc:
        io.emit({'outcome': 'rejected', 'error': type(exc).__name__}); return 1


if __name__ == '__main__':
    raise SystemExit(main())
