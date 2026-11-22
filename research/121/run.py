#!/usr/bin/env python3
"""И-121: два офлайн-прогона матрицы, приёмка и печать."""
import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.dont_write_bytecode = True
sys.path[:0] = [str(HERE), str(ROOT/'research/strategy/harness')]
import run_iteration as io
from render121 import page, report
from test_surfaces import (BASELINE, BOOK, COUNTS, MATRIX, MODULE, PINNED, PREFIX, STRATEGY, TEST,
                           canon, expected_observation, hash_bytes, matrix_view, sources, strategy_lines)

BRANCH = 'arena/4e000a5e-isyncai'
OUTPUTS = ('CHECKOUT', 'CLEANROOM', 'ACCEPTANCE')
INPUTS = sorted([*PINNED, STRATEGY, BOOK, TEST, MATRIX, MODULE])
IDS = [f'{k}{i:02}' for k, n in (('P',3), ('I',11), ('R',9), ('S',22), ('D',6)) for i in range(1,n+1)]
PASSED = dict(zip(COUNTS, (len(IDS), 0, 0)))


def dest(name):
    return io.repo_path(PREFIX+name)


def read(name):
    return io.read_json(dest(name+'.json'))


def inputs(root, names):
    data = {}
    for n in names:
        f = root/n
        if not f.is_file() or f.resolve() != f:
            raise ValueError('ordinary_file_required')
        data[n] = f.read_bytes()
    return data


def hashes(files):
    # Фиксируем читаемую проверкой рамку, а вся стратегия включена байтами в печать.
    return {n:hash_bytes(b) for n,b in files.items() if n != STRATEGY}


def anchors(files):
    return hash_bytes(canon(strategy_lines(files[STRATEGY])))


def load():
    s = read('ITERATION')
    members = sorted([*INPUTS, *(PREFIX+n+'.json' for n in OUTPUTS),
                      *(PREFIX+n for n in ('DESIGN.md','ITERATION.json','RED.json','run.py','render121.py','REPORT.md')),
                      'research/strategy/SYNC-LOG.md', *('research/strategy/harness/'+n for n in ('run_iteration.py','render.py','probes.py'))])
    records = [*members, *(PREFIX+n for n in ('SEAL.json','REPLAY.json', io.seal_name(s), io.page_name(s)))]
    if (s['id'] != '121' or s['baseline'] != BASELINE or s['branch'] != BRANCH or s['case_ids'] != IDS
            or s['command'] != ['-B','-I','-S','-X','utf8',TEST] or s['target_inputs'] != INPUTS or s['seal_members'] != members
            or any(io.repo_path(n) != ROOT/n for n in records)):
        raise ValueError('iteration_contract')
    files = inputs(ROOT, INPUTS); h = hashes(files)
    if (h[BOOK] != s['casebook_sha256'] or h[TEST] != s['test_sha256'] or {n:h[n] for n in PINNED} != s['pinned_inputs']
            or anchors(files) != s['strategy_anchors_sha256']):
        raise ValueError('input_drift')
    book = json.loads(files[BOOK]); _, _, control = sources(ROOT)
    if (canon(book['format']) != b'1' or book['baseline'] != BASELINE or [c['id'] for c in book['cases']] != IDS
            or not canon(control) == canon(s['expected_control']) == canon(book['expected_control'])):
        raise ValueError('corpus_contract')
    return s, book, read('RED'), files


def measure(root, s, files):
    before = inputs(root, files)
    if before != files:
        raise ValueError('different_inputs')
    p = subprocess.run([sys.executable,*s['command']], cwd=root, capture_output=True, timeout=35)
    try:
        result = json.loads(p.stdout)
    except ValueError:
        result = None
    return {'rc':p.returncode, 'stderr_empty':not p.stderr, 'inputs_sha256':hashes(before), 'strategy_anchors_sha256':anchors(before),
            'inputs_unchanged':inputs(root, files)==before, 'result':result}


def cleanroom(s, files):
    with TemporaryDirectory(prefix='ack-i121-inputs-') as folder:
        root = Path(folder).resolve()
        for n, data in files.items():
            f = root/n; f.parent.mkdir(parents=True,exist_ok=True); f.write_bytes(data)

        def snapshot():
            return {f.relative_to(root).as_posix():(st.st_mode,st.st_ino,st.st_mtime_ns,st.st_size)
                    for f in root.rglob('*') for st in (f.lstat(),)}

        before = snapshot(); e = measure(root,s,files)
        return dict(e, files=sorted(n for n in before if (root/n).is_file()), tree_unchanged=snapshot()==before)


def tally(rows):
    c = Counter(r['status'] for r in rows)
    return {k:c[k] for k in COUNTS}


def header(s, d):
    return (type(d) is dict and d.keys()=={'format','control','os','python','rows','counts'} and canon(d['format'])==b'1'
            and canon(d['control'])==canon(s['expected_control']) and all(type(d[k]) is str and d[k] for k in ('os','python')))


def accepted_red(s, red):
    d = red['result']
    return (red['independent_baseline_match'] is True and red['stderr_empty'] is True and canon(red['rc'])==b'1'
            and all(red[k]==s[k] for k in ('baseline','command','casebook_sha256','test_sha256','pinned_inputs','strategy_anchors_sha256'))
            and header(s,d) and canon(d['counts'])==canon(dict(zip(COUNTS,(0,len(IDS),0))))
            and d['rows']==[dict(id=n,status='fail',reason='surfaces_missing') for n in IDS])


def accepted_run(s, book, evidence):
    d = evidence['result']; rows = d.get('rows') if type(d) is dict else None; seen = {}
    if type(rows) is list:
        for row in rows:
            if type(row) is dict and type(row.get('id')) is str:
                seen.setdefault(row['id'],[]).append(row)
    checks = []
    for c in book['cases']:
        found = seen.get(c['id'],[]); wanted = dict(id=c['id'],status='pass',observation=expected_observation(book,c))
        state = 'not run' if not found else 'pass' if len(found)==1 and canon(found[0])==canon(wanted) else 'fail'
        checks.append({**{k:c[k] for k in ('id','basis','criterion')}, 'status':state})
    count = tally(checks)
    ok = (canon(evidence['rc'])==b'0' and evidence['stderr_empty'] is True and header(s,d) and type(rows) is list
          and [r.get('id') if type(r) is dict else None for r in rows]==IDS and canon(d['counts'])==canon(count) and count==PASSED)
    return ok, {'rc':evidence['rc'], 'counts':count, 'cases':checks}


def accept(s, book, red, files, checkout, clean):
    gates, ready, runs = [], [], {}

    def gate(name, ok, basis, criterion):
        gates.append(dict(check=name, status='pass' if ok else 'fail', basis=basis, criterion=criterion))

    gate('frozen_red', accepted_red(s,red), 'CASES.json; ITERATION.json; RED.json',
         'Корпус и исторические входы закреплены до матрицы и валидатора; RED 0/51/0 совпал с архивом базы.')
    for name, result in (('checkout',checkout), ('cleanroom',clean)):
        ok, runs[name] = accepted_run(s,book,result); ready.append(ok)
        gate(name,ok,f'{name.upper()}.json; CASES.json','Весь корпус, порядок и диагностики совпадают с ожиданиями; rc0 без stderr.')
    doc = json.loads(files[MATRIX]); ctl = s['expected_control']
    obs = {r['id']:r['observation'] for r in checkout['result']['rows']} if all(ready) else {}
    m = obs['P01']['result'] if obs else {}; view = matrix_view(doc) if obs else {}
    rows = view['environments'] if view else {}

    def code(id):
        return obs[id]['error']['code']

    gate('roster_and_scope', bool(m) and m['by_status']=={'candidate':3,'stub':3} and canon(view)==canon(book['expected_view'])
         and all(r['stub_has_reason'] and not r['paths'] and r['manual'] is None for r in rows.values() if r['status']=='stub')
         and code('R05')==code('R06')=='surfaces_status' and code('S09')==code('S10')=='surfaces_guard',
         'P01; R01–R09; S09/S10; §1.2', 'Три кандидата, три заглушки с причиной; нет новой среды или отмены охраны путей.')
    gate('entry_and_priority', bool(m) and m['entry_candidates']==7 and all(r['winner'] is None and r['config_key'] is None for r in rows.values())
         and 'nearest-wins' in rows['copilot']['hypotheses'] and code('S01')==code('S02')==code('S03')=='surfaces_entry'
         and code('S05')==code('S06')=='surfaces_priority',
         'S01–S06; SURFACES.json:entry/priority', 'Указаны кандидаты и проверяемые конфликты; догадка о ключе или старшинстве не становится фактом.')
    gate('limits_separated', bool(m) and view['limits']['context_percent']==ctl['target_window_percent']==[25,30]
         and view['limits']['start_section_max_bytes']==ctl['start_section_max_bytes']==4096
         and ctl['start_section_observed_bytes']==2363
         and all(all(r['native_caps'][k] is None for k in ('context_tokens','instruction_bytes','truncation')) for r in rows.values())
         and code('S07')==code('S08')=='surfaces_caps',
         'P8; И‑112 B01/S05; S07/S08', 'Проектный процент, байты локального §0 и неизвестные капы клиентов различаются.')
    gate('no_claimed_coverage', bool(m) and m['client_runs']==0 and m['by_coverage']=={'not run':15,'out_of_scope':15}
         and all(r['metrics'][k] is None for r in rows.values() for k in ('read_rate','apply_rate','false_positive'))
         and all(code(id)=='surfaces_coverage' for id in ('S11','S12','S13','S14','S15','S16','S17')),
         'P01; S11–S17; SURFACES.json:coverage/metrics', '0 запусков; пять разных незапущенных стадий на клиента, отсутствие наблюдения не равно нулевой доле.')
    gate('donor_only', bool(m) and view['discrepancy']['inventory']==ctl['copilot_inventory']==[3,5]
         and view['discrepancy']['report']==ctl['copilot_report']==[3,4] and view['discrepancy']['resolution']=='inventory_for_donor_only'
         and ctl['printed_inventory_and_report_match'] is True and ctl['inventory_repeat_match'] is True
         and ctl['legacy_arena']=={'step':'7-adapter-arena','rc':2,'error':'adapter_unknown'}
         and all(code(id)=='surfaces_donor' for id in ('D01','D02','D03','D04','D05','D06')),
         'Печать И‑101; И‑102/BASELINE.json; D01–D06', 'Обе исторические цифры сохранены; первичен инвентарь только для 0.1.36. Нет доказательства порядка цели.')
    gate('gaps_traced', bool(m) and ctl['split_before_125'] is True
         and len([g for r in rows.values() for g in r['gaps']])==18
         and all(code(id)=='surfaces_gaps' for id in ('S18','S19','S20','S21','S22')),
         'SURFACES.json:gaps; ARCHITECTURE-REVIEW.md; S18–S22', 'Пробелы имеют основания и критерии; заглушки не включены; разбиение И‑125 не принято за владельца.')
    gate('offline_readonly', bool(m) and all(o['effects']==[] and o['quiet'] and o['unchanged'] for o in obs.values()),
         'Все 51 случая; перехват файлов, системы, socket и процесса', 'Вызовы валидатора не наблюдались вне памяти; нет вывода, изменения источников или исполнения текста.')
    gate('fresh_copy', clean['tree_unchanged'] is True and clean['files']==INPUTS,
         'ITERATION.json; CLEANROOM.json', 'Новая копия из 13 входов, без установленного клиента или выполнения донора.')
    gate('repeat', all(ready) and checkout['inputs_unchanged'] is True and clean['inputs_unchanged'] is True
         and checkout['strategy_anchors_sha256']==clean['strategy_anchors_sha256']==s['strategy_anchors_sha256']
         and checkout['inputs_sha256']==clean['inputs_sha256']==hashes(files) and canon(checkout['result'])==canon(clean['result']),
         'CHECKOUT.json; CLEANROOM.json; якорь стратегии', 'Полное одинаковое наблюдение и неизменяемые входы; якорь не меняется при записи факта в стратегию.')
    deferred = [dict(r,status='not run') for r in s['not_run']]
    counts = tally(gates+deferred); d = checkout['result'] if type(checkout['result']) is dict else {}
    return {'iteration':'И-121','outcome':'accepted' if not counts['fail'] else 'rejected','counts':counts,
            'checks':gates,'runs':runs,'not_run':deferred,'summary':m if not counts['fail'] else None,
            'os':d.get('os'),'python':d.get('python'),'scope':'П5 · покрытие матрицы, не клиентских запусков'}


def same_record(name, value):
    return dest(name+'.json').read_bytes()==(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode('utf-8')


def replay(s):
    raw, expected = io.seal_bytes(s); saved = dest(expected['file']).read_bytes(); record = read('SEAL')
    return {'outcome':'ok' if saved==raw and same_record('SEAL',expected) else 'mismatch',
            'recorded_sha256':record.get('sha256') if type(record) is dict else None,
            'archive_sha256':hash_bytes(saved), 'rebuilt_sha256':expected['sha256']}


def generate(s, book, red, files, only_measure):
    co, cl = measure(ROOT,s,files), cleanroom(s,files); a = accept(s,book,red,files,co,cl)
    doc = json.loads(files[MATRIX])
    for name, value in zip(OUTPUTS,(co,cl,a)):
        io.dump_json(dest(name+'.json'),value)
    dest('REPORT.md').write_text(report(s,book,red,a,doc),encoding='utf-8',newline='\n')
    facts = dict(outcome=a['outcome'],counts=a['counts'],summary=a['summary'],runs={n:r['counts'] for n,r in a['runs'].items()})
    if only_measure or a['outcome']!='accepted':
        io.emit(facts); return int(a['outcome']!='accepted')
    raw, seal = io.seal_bytes(s); dest(seal['file']).write_bytes(raw); io.dump_json(dest('SEAL.json'),seal)
    rep = replay(s); io.dump_json(dest('REPLAY.json'),rep)
    dest(io.page_name(s)).write_text(page(s,a,doc,seal,rep),encoding='utf-8',newline='\n')
    io.emit(dict(facts,seal=seal,replay=rep['outcome'])); return int(rep['outcome']!='ok')


def verify(s, book, red, files):
    rep = replay(s); co, cl = read('CHECKOUT'), read('CLEANROOM'); a = accept(s,book,red,files,co,cl)
    doc = json.loads(files[MATRIX]); ok = (rep['outcome']=='ok' and a['outcome']=='accepted'
          and all(same_record(n,v) for n,v in zip((*OUTPUTS,'REPLAY'),(co,cl,a,rep)))
          and dest('REPORT.md').read_bytes()==report(s,book,red,a,doc).encode('utf-8')
          and dest(io.page_name(s)).read_bytes()==page(s,a,doc,read('SEAL'),rep).encode('utf-8'))
    io.emit(dict(rep,record_and_page_match=ok)); return int(not ok)


def main():
    parser = argparse.ArgumentParser(description=__doc__); modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--measure-only',action='store_true',help='П3–П6 без печати')
    modes.add_argument('--verify-seal',action='store_true',help='Проверка печати и записей без записи')
    args = parser.parse_args()
    try:
        s,book,red,files = load()
        return verify(s,book,red,files) if args.verify_seal else generate(s,book,red,files,args.measure_only)
    except (AssertionError,AttributeError,IndexError,KeyError,OSError,TypeError,ValueError,subprocess.TimeoutExpired) as exc:
        io.emit({'outcome':'rejected','error':type(exc).__name__}); return 1


if __name__=='__main__':
    raise SystemExit(main())
