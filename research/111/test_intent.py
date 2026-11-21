#!/usr/bin/env python3
"""П2: классификация фразы, граница сессии и физические эффекты проверяются отдельно."""
from collections import Counter
import json
import os
from pathlib import Path
import platform
import sys
import tempfile
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'research/110'))
from test_actions import (Audit, FILES, HASH, PROFILE, REV_FIELD, changed, digests, encode, entry_hash,
                          expected_plan, file_stamps, fingerprints, redacted, row, serialized, snapshot, step)

VERSION = '0.2.0-dev.111'
WITNESSES = {'NL01', 'NL02', 'NL20'}


def make_cases(book):
    inputs = {r['id']: r for r in book['phrases']}
    cases = []
    for r in book['phrases']:
        code, where = ('confirmation_required', 'confirmed_ticket') if r['plan']['outcome'] == 'planned' else ('ticket_unknown', 'ticket')
        cases.append({'id': r['id'], 'group': 'nl', 'basis': r['basis'], 'category': r['category'], 'steps': [r['id']],
                      'trial': 'unapproved', 'write_target': None, 'final': {'outcome': 'refused', 'error': {'code': code, 'where': where}}})
    cases.extend(dict(r, group='control', category=None) for r in book['controls'])
    for ref, item in book['control_inputs'].items():
        if ref in inputs:
            raise ValueError('Повтор входа: ' + ref)
        inputs[ref] = item
    return [dict(case, subjects=[(ref, inputs[ref]) for ref in case['steps']]) for case in cases]


def seed(work):
    docs = {}
    for area, root, revision in [('L0', 'kit', None), ('L1', PROFILE, 4), ('L2', '.agent-contract', 7)]:
        id_ = 'S-1' if area == 'L0' else 'R-A'
        doc = {'schema_version': 2, 'area': area, 'roots': [root], 'entries': [
            row(area, 'C-A'), row(area, id_, kind='rule', parent='C-A', scope='docs/guide', text='Исходное правило.')]}
        doc.update({'release_version': VERSION} if area == 'L0' else {'revision': revision})
        file = work / FILES[area]
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(encode(doc))
        docs[area] = doc
    (work / 'kit/base/manifest.json').write_bytes(encode({'release_version': VERSION}))
    (work / PROFILE / 'note.txt').write_bytes(b'Profile side file.\n')
    (work / '.agent-contract/project/note.txt').write_bytes(b'Project side file.\n')
    return docs


def oracle(docs, card):
    """Будущий файл вычисляется из исходной фикстуры и утверждений П2, не из карты Kit."""
    params, op = card['params'], card['operation']
    area = params['target']
    saved = docs[area]
    base, entries = saved['revision'], saved['entries']
    revision, id_ = base + 1, params['entry_id']
    if op == 'create':
        item = {**row(area, id_, kind=params['kind'], parent=params['contract'], scope=params['scope'], state='draft'),
                **{f: params[f] for f in ('title', 'text', 'basis', 'criterion')}}
        registry = dict(saved, revision=revision, entries=[*entries, item])
        return {'profile_format': 1, 'registry': registry, 'journal': {'base_revision': base, 'decisions': [
                {'operation': 'create', 'entry_id': id_, 'profile_revision': revision, 'entry_sha256': entry_hash(item)}]}}
    if op == 'edit':
        before = next(e for e in entries if e['id'] == id_)
        after = dict(before, text=params['text'])
        registry = dict(saved, revision=revision, entries=[after if e is before else e for e in entries])
        return {'registry_format': 2, 'registry': registry, 'journal': {'base_revision': base,
                'base_entries': fingerprints(entries), 'decisions': [step('edit', area, revision, before, after)]}}
    raise AssertionError('Неожиданный маршрут независимого оракула')


def expected_card(subject):
    return {**subject['card'], 'request': subject['request']}


def expected_full_plan(subject, work, docs):
    card = expected_card(subject)
    outcome = subject['plan']['outcome']
    result = {'plan_format': 1, 'dry_run': True, 'card': card, 'outcome': outcome}
    if outcome == 'planned':
        area = card['params']['target']
        return expected_plan(card, work, area, docs[area]['revision'], serialized(oracle(docs, card)))
    if outcome == 'listed':
        doc = docs[card['params']['target']]
        item = doc['entries'][1]  # Одна активная rule под C-A, остальные виды не запрашивались.
        result['result'] = {'target': doc['area'], 'revision': doc['revision'], 'entries': [
            {k: item[k] for k in ('id', 'kind', 'state', 'parent', 'scope', 'title')}]}
    return result


def call(store, audit, loads, fn):
    count = loads.call_count
    try:
        value = audit.run(fn)
        error = None
    except store.StoreError as e:
        value, error = None, e.diagnostic()
    return value, error, {'reads': audit.reads != 0, 'load_called': loads.call_count != count, 'writes': audit.writes}


def plan_step(store, compiler, session, work, docs, audit, loads, ref, subject, *, compile_only=False):
    initial = snapshot(work)
    stamps = file_stamps(work, initial)
    steady = lambda: snapshot(work) == initial and file_stamps(work, initial) == stamps
    card, error, io = call(store, audit, loads, lambda: compiler(subject['request']))
    if error is not None:
        raise AssertionError('Компиляция вернула ошибку хранилища')
    measured = {'ref': ref, 'card': card, 'compile_io': io, 'compile_untouched': steady()}
    if compile_only:
        return dict(measured, plan={'outcome': 'not_requested'}), None
    expected = expected_full_plan(subject, work, docs)
    plan, refusal, io = call(store, audit, loads, lambda: session.plan(card))
    seen = {'outcome': 'refused', 'error': refusal} if refusal is not None else {'outcome': plan['outcome']}
    issued = plan is not None and type(plan.get('ticket')) is str and HASH.fullmatch(plan['ticket']) is not None
    if refusal is not None:
        exact = encode(seen) == encode(subject['plan'])
    else:
        exact = (encode(redacted(plan)) == encode(expected)
                 and ('ticket' in plan) == (expected['outcome'] == 'planned') == issued)
    measured.update(plan=seen, plan_exact=exact, ticket_issued=issued, plan_io=io, plan_untouched=steady())
    return measured, plan


def applied(store, session, layout, work, docs, subject, plan):
    # Единственный вызываемый ветвью confirm путь; нужно наблюдённое совпадение переданного диффа.
    result = session.apply(plan, confirmed_ticket=plan['ticket'])
    card = expected_card(subject)
    area = card['params']['target']
    expected = oracle(docs, card)
    actual = store.read_registry(layout, target=area)
    status = {'schema_version': 2, 'release_version': VERSION, 'profile_root': PROFILE, 'profile_revision': 4, 'project_revision': 7}
    status[REV_FIELD[area]] = expected['registry']['revision']
    history = store.registry_history(layout, target=area)
    return {'outcome': result['outcome'], 'target': actual['area'], 'revision': [docs[area]['revision'], actual['revision']],
            'operation': history['decisions'][-1]['operation'],
            'exact_status': encode(result) == encode({'outcome': 'applied', 'status': status}) and encode(store.status(layout)) == encode(status),
            'exact_history': encode(history) == encode(expected['journal']),
            'exact_file': (work / FILES[area]).read_bytes() == serialized(expected) and encode(actual) == encode(expected['registry'])}


def run_trial(store, session, layout, work, docs, audit, loads, case, measured, issued):
    trial, last = case['trial'], issued[-1]
    settled = measured[-1]
    if trial == 'blocked':
        if settled['plan']['outcome'] != 'refused':
            raise AssertionError('Запрет должен сработать до apply')
        return {'outcome': 'blocked_before_apply'}, {'reads': False, 'load_called': False, 'writes': False}
    if trial == 'confirm':
        if not (settled['plan_exact'] and settled['ticket_issued'] and settled['plan_untouched'] and not settled['plan_io']['writes']):
            raise AssertionError('Отдельное согласие только на независимо сверенный dry-run')
        action = lambda: applied(store, session, layout, work, docs, case['subjects'][-1][1], last)
    elif trial == 'replay':
        first = issued[0]
        action = lambda: session.apply(first, confirmed_ticket=first['ticket'])
    elif trial == 'forge_card':
        forged = {**settled['card'], 'operation': 'create', 'outcome': 'complete',
                  'params': {**settled['card']['params'], 'persistence': 'permanent'}}
        action = lambda: session.plan(forged)
    elif trial == 'transplant':
        fake = {'plan_format': 1, 'outcome': 'non_registry', 'dry_run': True, 'card': settled['card'], 'ticket': issued[0]['ticket']}
        action = lambda: session.apply(fake, confirmed_ticket=fake['ticket'])
    elif case['subjects'][-1][1]['plan']['outcome'] == 'planned':
        action = lambda: session.apply(last)  # Не извлекать подтверждение из самого плана.
    else:
        fake = dict(last or {}, ticket='0' * 64)
        action = lambda: session.apply(fake, confirmed_ticket=fake['ticket'])
    value, err, io = call(store, audit, loads, action)
    if err is not None:
        return {'outcome': 'refused', 'error': err}, io
    return value if trial == 'confirm' else {'outcome': 'unexpected_acceptance'}, io


def observe(store, compiler, session_class, audit, case):
    with tempfile.TemporaryDirectory(prefix='ack-i111-work-') as tmp:
        work = Path(tmp).resolve()
        docs = seed(work)
        before = snapshot(work)
        stamps = file_stamps(work, before)
        target = case['write_target']
        rel, raw = (None, None) if target is None else (
            FILES[target], serialized(oracle(docs, expected_card(case['subjects'][-1][1]))))
        layout = store.Layout(work, PROFILE)
        session = session_class(layout, profile_id='Pilot')
        trace, replace = [], os.replace

        def witness(src, dst):
            src, dst = Path(src), Path(dst)
            trace.append(rel is not None and dst == work / rel and src != dst and src.parent == dst.parent and src.read_bytes() == raw)
            return replace(src, dst)

        measured, issued = [], []
        with patch.object(os, 'replace', side_effect=witness), patch.object(store, '_load', wraps=store._load) as loads:
            for j, (ref, subject) in enumerate(case['subjects']):
                m, plan = plan_step(store, compiler, session, work, docs, audit, loads, ref, subject,
                                    compile_only=case['trial'] == 'transplant' and j == 1)
                measured.append(m)
                issued.append(plan)
            final, trial_io = run_trial(store, session, layout, work, docs, audit, loads, case, measured, issued)
        after = snapshot(work)
        post = file_stamps(work, after)
        paths = changed(before, after)
        untouched = all(p == rel for p in paths) and all(post.get(p) == s for p,s in stamps.items() if p != rel)
        observation = {'steps': measured, 'final': final, 'trial_io': trial_io, 'changed': paths, 'other_unchanged': untouched,
                       'replacements': len(trace), 'prepared_exact': bool(trace) and all(trace),
                       'selected_replaced': rel is not None and (stamps[rel][:2] != post[rel][:2])}
        data = {'observed': observation, 'digest': {'before': digests(before, PROFILE), 'after': digests(after, PROFILE)}}
        if case['id'] in WITNESSES and issued[-1] is not None:
            data['preview'] = redacted(issued[-1])
        return data


def expected_observation(case):
    quiet = {'reads': False, 'load_called': False, 'writes': False}
    steps = []
    for j, (ref, subject) in enumerate(case['subjects']):
        record = {'ref': ref, 'card': expected_card(subject), 'compile_io': quiet, 'compile_untouched': True}
        if case['trial'] == 'transplant' and j == 1:
            record['plan'] = {'outcome': 'not_requested'}
        else:
            plan = subject['plan']
            reads = plan['outcome'] in ('planned', 'listed')
            record.update(plan=plan, plan_exact=True, ticket_issued=plan['outcome'] == 'planned',
                          plan_io={'reads': reads, 'load_called': reads, 'writes': False}, plan_untouched=True)
        steps.append(record)
    target = case['write_target']
    return {'steps': steps, 'final': case['final'], 'trial_io': {k: bool(target) for k in quiet},
            'changed': [] if target is None else [FILES[target]], 'other_unchanged': True,
            'replacements': int(target is not None), 'prepared_exact': target is not None, 'selected_replaced': target is not None}


def case_checks(cases, evidence):
    rows = evidence.get('rows') if type(evidence) is dict else None
    if type(rows) is not list or any(type(r) is not dict or type(r.get('id')) is not str for r in rows):
        rows = []
    seen = Counter(r['id'] for r in rows)
    by_id = {r['id']: r for r in rows}
    result = []
    for case in cases:
        id_, target = case['id'], case['write_target']
        issue = 'missing' if seen[id_] == 0 else 'duplicate' if seen[id_] != 1 else None
        if issue is None:
            record = by_id[id_]
            digest = record.get('digest')
            if encode(record.get('observed')) != encode(expected_observation(case)):
                issue = 'observation_mismatch'
            elif (type(digest) is not dict or digest.keys() != {'before', 'after'}
                  or any(type(d) is not dict or d.keys() != {'L0', 'L1', 'L2', 'L0_manifest'}
                         or any(type(v) is not str or not HASH.fullmatch(v) for v in d.values()) for d in digest.values())):
                issue = 'missing_digest'
            elif {k for k in digest['before'] if digest['before'][k] != digest['after'][k]} != ({target} if target else set()):
                issue = 'digest_mismatch'
        result.append({'id': id_, 'status': 'pass' if issue is None else 'fail', 'issue': issue})
    result.extend({'id': i, 'status': 'fail', 'issue': 'unexpected'} for i in sorted(seen.keys() - {r['id'] for r in cases}))
    return result


def main():
    sys.path.insert(0, str(ROOT))
    from kit.base import registry_store
    from kit.base.operation_card import compile_prompt
    from kit.base.operation_plan import PlanSession

    book = json.loads((HERE / 'CASES.json').read_bytes())
    cases = make_cases(book)
    if encode(book['format']) != b'1' or len(book['phrases']) != 20 or len({r['id'] for r in cases}) != len(cases):
        raise ValueError('Некорректный корпус П2')
    audit, rows = Audit(), []
    for case in cases:
        try:
            data = observe(registry_store, compile_prompt, PlanSession, audit, case)
        except (AttributeError, AssertionError, KeyError, TypeError, registry_store.StoreError) as error:
            data = {'probe_error': error.diagnostic() if isinstance(error, registry_store.StoreError) else str(error)}
        rows.append({'id': case['id'], **data})
    evidence = {'os': platform.system(), 'rows': rows}
    print(json.dumps(evidence, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if all(r['status'] == 'pass' for r in case_checks(cases, evidence)) else 1


if __name__ == '__main__':
    raise SystemExit(main())
