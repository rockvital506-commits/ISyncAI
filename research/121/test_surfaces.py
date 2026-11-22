#!/usr/bin/env python3
"""И-121: независимые наблюдения о матрице, исторических источниках и отсутствии I/O."""
import builtins
from collections import Counter
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from copy import deepcopy
from hashlib import sha256
from importlib import import_module
from io import BytesIO, StringIO
import json
import os
from pathlib import Path
import platform
import re
import socket
import subprocess
import sys
from unittest.mock import patch
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PREFIX = 'research/121/'
BOOK, TEST, MODULE, MATRIX = (PREFIX+n for n in ('CASES.json', 'test_surfaces.py', 'validate_surfaces.py', 'SURFACES.json'))
STRATEGY = 'research/STRATEGY.md'
BASE, REPEAT = 'research/strategy/BASELINE.json', 'research/102/BASELINE.json'
F0_REPORT, F0_RUN = 'research/101/REPORT.md', 'research/101/CLEANROOM.json'
F0_SEAL, F0_ZIP = 'research/101/SEAL.json', 'research/101/AgentContractKit-Iteration-101.zip'
BOOT = 'research/112/BOOTSTRAP.json'
REVIEW = 'research/strategy/pre-104/ARCHITECTURE-REVIEW.md'
PINNED = sorted((BASE, REPEAT, F0_REPORT, F0_RUN, F0_SEAL, F0_ZIP, BOOT, REVIEW))
BASELINE = '4159cb68d7a79583a8db0b0b1af23258b378412e'
STAGES = ('presence', 'detected', 'read', 'applied', 'repeat')
COUNTS = ('pass', 'fail', 'not run')
ANCHORS = ('1.2 Среды:', '| P8 |', '| P11 |', '| P12 |', '| P13 |', '### Ф5.', 'Имена точек входа',
           *(f'| И‑{n} |' for n in range(121,127)), *(f'| Д{n} |' for n in (1,2,3,6)), 'Сценарий пилота:')


def canon(obj):
    return json.dumps(obj, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def hash_bytes(raw):
    return sha256(raw).hexdigest()


def error(code, where, reason):
    return {'code': code, 'where': where, 'reason': reason}


def strategy_lines(raw):
    lines = raw.decode('utf-8').splitlines(); wanted = []
    for prefix in ANCHORS:
        matches = [line for line in lines if line.startswith(prefix)]
        assert len(matches) == 1, 'strategy_anchor'
        wanted.append(matches[0])
    return wanted


def sources(root=ROOT):
    """Читаются только установленные исторические артефакты, не код донора или клиента."""
    def data(n):
        f = root/n; assert f.resolve() == f and f.is_file()
        return f.read_bytes()
    anchor_lines = strategy_lines(data(STRATEGY)); inventory_raw = data(BASE); release = json.loads(inventory_raw)
    rerun = json.loads(data(REPEAT)); recorded = json.loads(data(F0_SEAL)); stamped = data(F0_ZIP)
    assert len(stamped) == recorded['bytes'] and hash_bytes(stamped) == recorded['sha256']
    assert release['release'] == rerun['release'] == '0.1.36'
    assert release['adapters'] == rerun['adapters'] and release['absent_adapters'] == rerun['absent_adapters'] == ['arena']
    report = data(F0_REPORT)
    with ZipFile(BytesIO(stamped)) as z:
        assert z.namelist().count(BASE) == z.namelist().count(F0_REPORT) == 1
        assert z.read(BASE) == inventory_raw and z.read(F0_REPORT) == report
    pattern = r'`copilot` \(documented, rank ([0-9]+)/([0-9]+)\)'
    mentions = re.findall(pattern, report.decode('utf-8')); assert len(mentions) == 1
    report_rank = [int(v) for v in mentions[0]]
    blob = json.loads(data(F0_RUN))
    arena_step, = [s for s in blob['steps'] if s['step'] == '7-adapter-arena']
    assert arena_step == {'step':'7-adapter-arena', 'rc':2, 'error':'adapter_unknown'}
    b = json.loads(data(BOOT)); s05, = [x for x in b['controls'] if x['id'] == 'S05']
    m = re.search(r'[0-9]+(?= байт)', s05['criterion']); assert m and s05['outcomes'] == ['invalid_start_section']
    witness, = [x for x in b['witness']['steps'] if x['step'] == 'bootstrap']
    section, = [x['bytes'] for x in witness['reads'] if x['file'] == 'kit/base/START.md']
    budget = re.search(r'([0-9]+)–([0-9]+) %', next(l for l in anchor_lines if l.startswith('| P8 |')))
    assert budget and 'Windows 11 и VS Code 1.146' in anchor_lines[-1]
    review = data(REVIEW).decode('utf-8'); assert 'До И‑125 нужно согласовать, как разделять прогоны и приёмку.' in review
    rank = lambda key: [release['adapters'][key]['rank'], release['adapters'][key]['of']]
    controls = {'anchors_sha256': hash_bytes(canon(anchor_lines)), 'legacy_release': release['release'],
                'legacy_arena': arena_step, 'kilo_inventory': rank('kilo'), 'copilot_inventory': rank('copilot'),
                'copilot_report': report_rank, 'printed_inventory_and_report_match': True, 'inventory_repeat_match': True,
                'start_section_max_bytes': int(m.group()), 'start_section_observed_bytes': section,
                'target_window_percent': [int(v) for v in budget.groups()], 'split_before_125': True}
    return release, report_rank, controls


def matrix_view(doc):
    envs = {}
    for k, r in doc['environments'].items():
        envs[k] = {'status': r['status'], 'surface': r['target']['surface'], 'pilot': r['target']['pilot'],
                   'identity_unknown': r['target']['observed_version'] is None and r['target']['observed_mode'] is None,
                   'stub_has_reason': bool(r['stub_reason']), 'paths': r['entry']['paths'], 'entry_status': r['entry']['status'],
                   'config_key': r['entry']['config_key'], 'manual': r['entry']['manual'], 'winner': r['priority']['winner'],
                   'hypotheses': r['priority']['hypotheses'], 'native_caps': r['caps'], 'unchanged': r['unchanged'],
                   'coverage': r['coverage'], 'metrics': r['metrics'], 'gaps': {n:g['next'] for n,g in r['gaps'].items()},
                   'donor': {n:r['donor'][n] for n in ('status','rank','of','entry')}}
    d = doc['donor_discrepancy']
    return {'environments': envs, 'protected': doc['protected'], 'limits': doc['limits'],
            'discrepancy': {k:d[k] for k in ('id','inventory','report','resolution','cause_known')}}


def change(raw, c):
    special = c.get('raw')
    if special == 'str': return raw.decode('utf-8')
    if special == 'empty': return b''
    if special == 'oversize': return b' ' * (96 * 1024 + 1)
    if special == 'broken': return b'{"SYNTHETIC_MATRIX_DO_NOT_ECHO_121"'
    if special == 'utf8': return b'{"format":1,"oops":"\xff"}'
    if special == 'duplicate': return b'{"format":1,' + raw.lstrip()[1:]
    if special == 'duplicate_row': return canon(json.loads(raw)).replace(b'"environments":{', b'"environments":{"arena":null,', 1)
    if special == 'nan': return b'{"format": NaN}'
    if not (c.get('path') or special): return raw
    doc = json.loads(raw)
    if special == 'reorder':
        doc = dict(reversed(tuple(doc.items()))); doc['environments'] = dict(reversed(tuple(doc['environments'].items())))
        return json.dumps(doc, ensure_ascii=False, indent=3).encode('utf-8')
    if c.get('path'):
        *parts, key = c['path']; node = doc
        for p in parts: node = node[p]
        if c.get('op') == 'drop': del node[key]
        else: node[key] = c['value']
    return canon(doc)


def expected_observation(book, case):
    return {'result': None if 'error' in case else book['expected_summary'], 'error': case.get('error'),
            'projection': book['expected_view'] if case.get('check_view') else None,
            'effects': [], 'quiet': True, 'unchanged': True}


def observe(m, raw, release, rank, c):
    inp = change(raw, c); before = deepcopy((release, rank)); effects = []; result = failure = project = None

    def trap(name):
        def stopped(*args, **kwargs):
            effects.append(name)
            raise AssertionError('effect_forbidden')
        return stopped

    with ExitStack() as guard:
        out = guard.enter_context(redirect_stdout(StringIO())); err = guard.enter_context(redirect_stderr(StringIO()))
        for obj, attr in ((builtins, 'open'), (Path, 'open'), (os, 'open'), (os,'scandir'), (os,'system'),
                          (socket,'socket'), (subprocess,'Popen')):
            guard.enter_context(patch.object(obj, attr, trap(f'{obj.__name__}.{attr}')))
        try:
            result = m.validate_surfaces(inp, baseline=release, report_rank=rank)
        except m.SurfaceError as e:
            failure = e.diagnostic()
    if c.get('check_view') and result is not None:
        project = matrix_view(json.loads(inp))
    return {'result': result, 'error': failure, 'projection': project, 'effects': effects,
            'quiet': not (out.getvalue() or err.getvalue()), 'unchanged': (release, rank) == before}


def main():
    book = json.loads((ROOT/BOOK).read_bytes()); release, rank, controls = sources()
    assert book['baseline'] == BASELINE and canon(controls) == canon(book['expected_control'])
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(HERE))
    m = import_module('validate_surfaces') if (ROOT/MODULE).is_file() and (ROOT/MATRIX).is_file() else None
    raw = (ROOT/MATRIX).read_bytes() if m else None; rows = []
    for c in book['cases']:
        row = {'id': c['id']}
        try:
            if m is None:
                rows.append(dict(row, status='fail', reason='surfaces_missing')); continue
            obs = observe(m, raw, release, rank, c)
            match = canon(obs) == canon(expected_observation(book, c))
        except Exception as e:
            rows.append(dict(row, status='fail', reason=type(e).__name__))
        else:
            rows.append(dict(row, status='pass', observation=obs) if match else dict(row, status='fail', reason='oracle_mismatch'))
    tally = Counter(r['status'] for r in rows)
    print(json.dumps({'format': 1, 'control': controls, 'os': platform.system(), 'python': platform.python_version(),
                      'rows':rows, 'counts':{k:tally[k] for k in COUNTS}}, ensure_ascii=False, sort_keys=True))
    return int(bool(tally['fail'] or tally['not run']))


if __name__ == '__main__':
    raise SystemExit(main())
