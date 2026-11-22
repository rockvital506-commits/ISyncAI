#!/usr/bin/env python3
"""И-120: П3–П8, независимый повтор и проверка исследовательской печати без записи."""
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
P = 'research/120/'
sys.dont_write_bytecode = True
sys.path[:0] = [str(HERE), str(ROOT/'research/strategy/harness')]
import run_iteration as io
from render120 import page, report
from test_bundle_rollback import BASELINE, BOOK, COUNTS, MODULE, PUBLIC, SOURCE, TEST, canon, expected_observation, setup

PINNED = sorted([SOURCE, PUBLIC, *('kit/base/' + n for n in ('bundle_verify.py', 'bundle_trust.py', 'schema_v2.py',
                'registry_policy.py', 'registry_store.py', 'profile_journal.py', 'registry_journal.py'))])
INPUTS = sorted([*PINNED, BOOK, TEST, MODULE, 'kit/base/BUNDLE-ROLLBACK.md'])
OUTPUTS = ('CHECKOUT', 'CLEANROOM', 'ACCEPTANCE', 'ROLLOUT')
IDS = [f'{k}{i:02}' for k, n in (('P', 7), ('R', 11), ('T', 10), ('C', 8), ('J', 10), ('W', 1), ('N', 3)) for i in range(1, n+1)]
PASSED = dict(zip(COUNTS, (len(IDS), 0, 0)))
BRANCH = 'arena/4e000a5e-isyncai'


def read(name):
    return io.read_json(io.repo_path(P+name+'.json'))


def inputs(root, names):
    data = {}
    for n in names:
        f = root/n
        if f.resolve() != f or not f.is_file():
            raise ValueError('ordinary_file_required')
        data[n] = f.read_bytes()
    return data


def hashes(files):
    return {n: sha256(b).hexdigest() for n, b in files.items()}


def load():
    s = read('ITERATION')
    members = sorted([*INPUTS, *(P+n+'.json' for n in OUTPUTS),
                      *(P+n for n in ('DESIGN.md', 'ITERATION.json', 'RED.json', 'run.py', 'render120.py', 'REPORT.md')),
                      'research/STRATEGY.md', 'research/strategy/SYNC-LOG.md',
                      *('research/strategy/harness/'+n for n in ('run_iteration.py', 'render.py', 'probes.py'))])
    records = [*members, *(P+n for n in ('SEAL.json', 'REPLAY.json', io.seal_name(s), io.page_name(s)))]
    if (s['id'] != '120' or s['baseline'] != BASELINE or s['branch'] != BRANCH or s['case_ids'] != IDS
            or s['target_inputs'] != INPUTS or s['seal_members'] != members or s['command'] != ['-B', '-I', '-S', '-X', 'utf8', TEST]
            or any(io.repo_path(n) != ROOT/n for n in records)):
        raise ValueError('iteration_contract')
    files = inputs(ROOT, INPUTS); h = hashes(files)
    if (h[BOOK] != s['casebook_sha256'] or h[TEST] != s['test_sha256'] or {n: h[n] for n in PINNED} != s['pinned_inputs']):
        raise ValueError('input_drift')
    book = json.loads(files[BOOK])
    ctl = {'profiles': {k:book['readbacks'][k] for k in ('A', 'B', 'C')}, 'rebuild_integrity': book['integrity']['B_rebuilt'],
           'working_port': dict.fromkeys(('rollout', 'rollback', 'rollout_status'), 'unknown_operation')}
    if (canon(book['format']) != b'1' or book['baseline'] != BASELINE or [c['id'] for c in book['cases']] != IDS
            or canon(s['expected_control']) != canon(ctl) or canon(book['expected_control']) != canon(ctl)):
        raise ValueError('corpus_contract')
    setup(book)  # Независимая сборка фикстур, ещё без запуска продукта И-120.
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
    with TemporaryDirectory(prefix='ack-i120-inputs-') as d:
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
            and canon(data['format']) == b'1' and canon(data['control']) == canon(s['expected_control'])
            and all(type(data[k]) is str and data[k] for k in ('os', 'python')))


def accepted_red(s, red):
    return (red['independent_baseline_match'] is True and red['stderr_empty'] is True and canon(red['rc']) == b'1'
            and all(red[k] == s[k] for k in ('baseline', 'command', 'casebook_sha256', 'test_sha256', 'pinned_inputs'))
            and header(s, red['result']) and canon(red['result']['counts']) == canon(dict(zip(COUNTS, (0, len(IDS), 0))))
            and red['result']['rows'] == [dict(id=n, status='fail', reason='bundle_rollback_missing') for n in IDS])


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
        state = 'not run' if not matches else 'pass' if len(matches) == 1 and canon(matches[0]) == canon(want) else 'fail'
        checks.append({**{k: c[k] for k in ('id', 'basis', 'criterion')}, 'status': state})
    count = tally(checks)
    ok = (canon(evidence['rc']) == b'0' and evidence['stderr_empty'] is True and header(s, d) and type(rows) is list
          and [r.get('id') if type(r) is dict else None for r in rows] == IDS and canon(d['counts']) == canon(count) and count == PASSED)
    return ok, {'rc': evidence['rc'], 'counts': count, 'cases': checks}


def summary(book, observed):
    got = {r['id']: r['observation'] for r in observed['rows']}
    rows = [{**{k:c[k] for k in ('id', 'basis', 'criterion', 'action', 'candidate')}, **got[c['id']]} for c in book['cases']]
    applied = [r['result']['event'] for r in rows if r['result'] is not None]
    refused = [r for r in rows if r['error'] is not None]
    attempts = [x for r in rows for x in r['replace']]
    metrics = {'cases': len(rows), 'applied': len(applied), 'preview_only': len(rows)-len(applied)-len(refused), 'refused': len(refused),
               'by_error': dict(Counter(r['error']['code'] for r in refused)), 'by_action': dict(Counter(e['action'] for e in applied)),
               'replace_attempts': len(attempts), 'successful_replaces': sum(x['completed'] for x in attempts),
               'unchanged_refusals': sum(r['file_effect'] in ('unchanged', 'absent') and r['state_before'] == r['state_after'] for r in refused),
               'restored_readbacks': sum(r['readback']['previous'] == r['readback']['restored'] for r in rows if r['readback'] is not None),
               'quiet_clean_unchanged_inputs': all(r['quiet'] and r['cleanup'] and r['context_unchanged'] for r in rows)}
    return {'iteration': 'И-120', 'basis': 'CASES.json; CHECKOUT.json; CLEANROOM.json', 'metrics': metrics,
            'references': book['integrity'], 'reader_control': observed['control']['profiles'], 'working_port': observed['control']['working_port'], 'rows': rows}


def accept(s, book, red, files, checkout, clean):
    gates, ready, runs = [], [], {}

    def gate(name, ok, basis, criterion):
        gates.append(dict(check=name, status='pass' if ok else 'fail', basis=basis, criterion=criterion))

    gate('frozen_red', accepted_red(s, red), 'CASES.json; RED.json; ITERATION.json',
         '50 случаев и оракул закреплены до продукта; RED 0/50/0 равен базовому Git-снимку.')
    for name, result in (('checkout', checkout), ('cleanroom', clean)):
        ok, runs[name] = accepted_run(s, book, result); ready.append(ok)
        gate(name, ok, f'{name.upper()}.json; CASES.json', 'Все 50 наблюдений, порядок и диагностики равны независимому оракулу; rc0 без stderr.')
    info = summary(book, checkout['result']) if all(ready) else None
    rows = {r['id']:r for r in info['rows']} if info else {}; m = info['metrics'] if info else {}

    def reason(n):
        e = rows[n]['error']; return e['code'], e['details']['reason']

    gate('exact_previous', bool(m) and m['by_action'] == {'rollout': 2, 'rollback': 4}
         and all(rows[n]['result']['active_sha256'] == book['archive_sha256']['B'] for n in ('P01','P02','P07'))
         and all(reason(n) == ('rollback_unavailable','no_previous') for n in ('R01','R02','R03'))
         and all(reason(n) == ('rollback_unavailable','not_previous') for n in ('R04','R05','R06'))
         and reason('R07') == ('rollback_unavailable','missing') and reason('R10') == ('rollout_no_change','already_active'),
         'P01/P02/P05/P07; R01–R07/R10', 'Выбран непосредственный прежний SHA; нет подбора по revision, обхода, фиктивного шага или второго отката.')
    gate('v2_readback', bool(m) and m['restored_readbacks'] == 2
         and rows['P01']['readback']['current'] == book['readbacks']['C']
         and rows['P02']['readback']['current']['code'] == 'digest_mismatch'
         and all(rows[n]['readback']['restored'] == book['readbacks']['B'] for n in ('P01','P02'))
         and all(len({r[k] for r in info['reader_control'].values()}) == 1 for k in ('system_sha256','project_sha256','profile_revision'))
         and len({r['rule_text_sha256'] for r in info['reader_control'].values()}) == 3,
         'P01/P02; CASES.json:readbacks; штатный read_registry + status',
         'Чтение прежнего v2 L1 снова работает и совпало с исходным B; L0/L2 прежние, revision 7 не определяет текст.')
    gate('current_trust', bool(m) and rows['P03']['result']['event']['policy_decision'] == 'exception'
         and rows['P03']['result']['event']['signature_status'] == 'unsigned'
         and all(reason(n) == ('rollout_blocked','exception_expired') for n in ('T02','T03')) and rows['T03']['at'] == 'apply'
         and reason('T06') == ('rollout_blocked','verifier_unavailable') and reason('R08') == reason('T07') == ('digest_mismatch','sha256')
         and reason('R09') == ('bundle_incomplete','members') and reason('T08') == ('bundle_trust_invalid','utc'),
         'P03; T01–T10; R08/R09; И‑118 и И‑119',
         'Целостность первая, затем свежая политика; истечение на apply и неверная/непроверенная подпись блокируют, журнал не даёт исключения сам.')
    gate('confirmation', bool(m) and rows['P06']['result'] is None and rows['P06']['file_effect'] == 'unchanged' and rows['P06']['plan'] is not None
         and all(rows[n]['file_effect'] == 'unchanged' and rows[n]['at'] == 'apply' for n in IDS if n.startswith('C'))
         and all(reason(n) == ('rollout_unconfirmed','ticket') for n in ('C01','C02','C07','C08')) and rows['C08']['retry_rejected'] is True
         and reason('C05') == ('rollout_stale','changed') and rows['C05']['plan']['state_sha256'] != rows['C05']['state_before'],
         'P06; C01–C08; T04', 'План не пишет; чужое, повторное или устаревшее подтверждение не заменяет точный план и его входы.')
    gate('journal_and_limits', bool(m) and rows['P07']['result']['event']['seq'] == 32 and reason('R11') == ('rollout_limit','capacity')
         and all(r['prefix_preserved'] is True for r in rows.values() if r['result'] is not None)
         and all(rows[n]['error']['code'] == 'rollout_state_invalid' and rows[n]['file_effect'] == 'unchanged' for n in IDS if n.startswith('J')),
         'P07/R11; J01–J10; R03', 'Неверная форма, связь или квитанция не исправляется; предыстория сохранена, один слот по счётчику оставлен для N‑1.')
    gate('single_replace', bool(m) and m['replace_attempts'] == 7 and m['successful_replaces'] == m['applied'] == 6
         and m['unchanged_refusals'] == m['refused'] == 43
         and len(rows['W01']['replace']) == 1 and rows['W01']['replace'][0]['completed'] is False and rows['W01']['retry_rejected'] is True
         and all(r['file_effect'] == 'replaced' and len(r['replace']) == 1 and r['replace'][0]['one_file'] is True
                 and r['replace'][0]['old_sha256'] == r['state_before'] and r['replace'][0]['staged_sha256'] == r['state_after']
                 for r in rows.values() if r['result'] is not None),
         'W01; P01–P07; снимки файла и перехват replace', 'До замены виден целый прежний файл, после — целый новый; при отказе нет даже частичного события.')
    gate('stand_boundary', bool(m) and m['quiet_clean_unchanged_inputs'] and rows['N01']['file_effect'] == rows['N02']['file_effect'] == 'absent'
         and info['working_port'] == dict.fromkeys(('rollout','rollback','rollout_status'),'unknown_operation'),
         'N01–N03; снимки стендов; control.working_port', 'Никакой рабочей цели, операции порта или утечки пути, билета и текста ошибки в результат; стенды убраны.')
    gate('fresh_copy', clean['tree_unchanged'] is True and clean['files'] == INPUTS,
         'ITERATION.json; CLEANROOM.json', 'Чистая копия — только 13 входов; без рабочих данных, Git, сервера подписи или записи в дерево входов.')
    gate('repeat', all(ready) and checkout['inputs_unchanged'] is True and clean['inputs_unchanged'] is True
         and checkout['inputs_sha256'] == clean['inputs_sha256'] == hashes(files) and canon(checkout['result']) == canon(clean['result']),
         'CHECKOUT.json; CLEANROOM.json', 'Идентичные входные байты и полный одинаковый результат в двух процессах.')
    deferred = [dict(row, status='not run') for row in s['not_run']]
    counts = tally(gates + deferred); obs = checkout['result'] if type(checkout['result']) is dict else {}
    result = {'iteration': 'И-120', 'outcome': 'accepted' if not counts['fail'] else 'rejected', 'counts': counts,
              'checks': gates, 'runs': runs, 'not_run': deferred, 'os': obs.get('os'), 'python': obs.get('python'),
              'scope': 'П5 · один файл временного стенда, точный N‑1 и повтор штатного чтения v2'}
    return result, info if not counts['fail'] else {'iteration': 'И-120', 'metrics': None, 'rows': None}


def same_record(name, value):
    return io.repo_path(P+name+'.json').read_bytes() == (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)+'\n').encode('utf-8')


def replay(s):
    raw, expected = io.seal_bytes(s); record = read('SEAL'); saved = io.repo_path(P+expected['file']).read_bytes()
    return {'outcome': 'ok' if saved == raw and same_record('SEAL', expected) else 'mismatch',
            'recorded_sha256': record.get('sha256') if type(record) is dict else None,
            'archive_sha256': sha256(saved).hexdigest(), 'rebuilt_sha256': expected['sha256']}


def generate(s, book, red, files, only_measure):
    checkout, clean = measure(ROOT, s, files), cleanroom(s, files)
    a, info = accept(s, book, red, files, checkout, clean)
    for name, result in zip(OUTPUTS, (checkout, clean, a, info)):
        io.dump_json(io.repo_path(P+name+'.json'), result)
    io.repo_path(P+'REPORT.md').write_text(report(s, red, a, info), encoding='utf-8', newline='\n')
    facts = dict(outcome=a['outcome'], counts=a['counts'], metrics=info['metrics'], runs={n:r['counts'] for n,r in a['runs'].items()})
    if only_measure or a['outcome'] != 'accepted':
        io.emit(facts); return int(a['outcome'] != 'accepted')
    raw, seal = io.seal_bytes(s); io.repo_path(P+seal['file']).write_bytes(raw); io.dump_json(io.repo_path(P+'SEAL.json'), seal)
    rep = replay(s); io.dump_json(io.repo_path(P+'REPLAY.json'), rep)
    io.repo_path(P+io.page_name(s)).write_text(page(s, a, info, seal, rep), encoding='utf-8', newline='\n')
    io.emit(dict(facts, seal=seal, replay=rep['outcome']))
    return int(rep['outcome'] != 'ok')


def verify(s, book, red, files):
    rep = replay(s); co, cl = read('CHECKOUT'), read('CLEANROOM'); a, info = accept(s, book, red, files, co, cl)
    ok = (rep['outcome'] == 'ok' and a['outcome'] == 'accepted'
          and all(same_record(n, v) for n,v in zip((*OUTPUTS, 'REPLAY'), (co, cl, a, info, rep)))
          and io.repo_path(P+'REPORT.md').read_bytes() == report(s, red, a, info).encode('utf-8')
          and io.repo_path(P+io.page_name(s)).read_bytes() == page(s, a, info, read('SEAL'), rep).encode('utf-8'))
    io.emit(dict(rep, record_and_page_match=ok)); return int(not ok)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--measure-only', action='store_true', help='П3–П6 без печати')
    modes.add_argument('--verify-seal', action='store_true', help='Проверка печати и записей без записи')
    args = parser.parse_args()
    try:
        s, book, red, files = load()
        return verify(s, book, red, files) if args.verify_seal else generate(s, book, red, files, args.measure_only)
    except (AssertionError, AttributeError, IndexError, KeyError, OSError, TypeError, ValueError, subprocess.TimeoutExpired) as exc:
        io.emit({'outcome': 'rejected', 'error': type(exc).__name__}); return 1


if __name__ == '__main__':
    raise SystemExit(main())
