#!/usr/bin/env python3
"""Неизменяемые ожидания П2 и независимое измерение журнала на физических файлах."""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import sys
import tempfile
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'research/105'))
from test_layout import HASH, case_checks, changed, digests, encode, snapshot, under, write

PROFILE = 'profiles/pilot'
REGISTRY = PROFILE + '/registry.json'
RELEASE = '0.2.0-dev.106'
L0_FILES = ('SCHEMA-V2.md', 'STORAGE-V2.md', 'PROFILE-JOURNAL.md',
            'schema_v2.py', 'registry_store.py', 'profile_journal.py')
SERIES = ('P00-initial', *(f'P{i:02d}-create' for i in range(1, 11)))


def record(i, authority, *, parent=None):
    return {'id': i, 'kind': 'rule' if parent else 'contract', 'state': 'draft' if parent else 'active',
            'authority': authority, 'parent': parent, 'scope': 'docs' if parent else '.',
            'title': f'Тест {i}', 'text': f'Синтетическая запись {i}.',
            'basis': 'Фикстура И-106, не пользовательское решение.', 'criterion': 'Одно решение на одну запись.'}


def rule(n):
    return record(f'Q-{n:02d}', 'profile_owner', parent='Q-0')


def profile(revision, entries):
    return {'schema_version': 2, 'area': 'L1', 'roots': [PROFILE], 'revision': revision, 'entries': entries}


def expected_profile(n):
    # Эталон формируется независимо от журнала и портов Kit.
    rows = [rule(i) for i in range(1, n + 1)]
    decisions = []
    for i, row in enumerate(rows, start=1):
        raw = json.dumps(row, ensure_ascii=True, sort_keys=True, separators=(',', ':')).encode('ascii')
        decisions.append({'operation': 'create', 'entry_id': row['id'], 'profile_revision': i,
                          'entry_sha256': sha256(raw).hexdigest()})
    return {'profile_format': 1, 'registry': profile(n, [record('Q-0', 'profile_owner'), *rows]),
            'journal': {'base_revision': 0, 'decisions': decisions}}


def seed(work, base_revision=0):
    kit = work / 'kit/base'
    proj = work / '.agent-contract/project'
    write(kit / 'registry.json', {'schema_version': 2, 'area': 'L0', 'roots': ['kit'], 'release_version': RELEASE,
                                 'entries': [record('S-1', 'system_release')]})
    for name in L0_FILES:
        (kit / name).write_bytes((ROOT / 'kit/base' / name).read_bytes())
    write(kit / 'manifest.json', {'release_version': RELEASE, 'fixture_only': True,
          'files_sha256': {n: sha256((kit / n).read_bytes()).hexdigest() for n in (*L0_FILES, 'registry.json')}})
    write(proj / 'registry.json', {'schema_version': 2, 'area': 'L2', 'revision': 7, 'roots': ['.agent-contract'],
                                  'entries': [record('P-1', 'project_owner')]})
    (proj / 'handoff.txt').write_bytes(b'Independent local evidence.\n')
    write(work / REGISTRY, profile(base_revision, [record('Q-0', 'profile_owner')]))


def stamp(file):
    info = file.lstat()
    return info.st_dev, info.st_ino, info.st_mtime_ns, info.st_ctime_ns


def observe(store, work, case, action):
    before, file_before = snapshot(work), stamp(work / REGISTRY)
    try:
        observed = {'ok': True, **action(before, file_before)}
    except store.StoreError as error:
        observed = {'ok': False, 'error': error.diagnostic()}
    after = snapshot(work)
    observed.update(changed=changed(before, after), registry_untouched=stamp(work / REGISTRY) == file_before,
                    l0_l2_unchanged=all(under(before, root) == under(after, root) for root in ('kit', '.agent-contract')))
    return {'id': case, 'observed': observed, 'digest': {'before': digests(before, PROFILE), 'after': digests(after, PROFILE)}}


def shape(status, history):
    return {'status': status, 'base_revision': history['base_revision'],
            'decision_revisions': [r['profile_revision'] for r in history['decisions']]}


def inspect(store, layout):
    return shape(store.status(layout), store.profile_history(layout))


def audited_commit(store, layout, plan, expected, *, fail=False):
    """В точке единственной замены считывает подготовленный файл целиком."""
    target = layout.workspace / REGISTRY
    replace = os.replace
    attempted = []

    def audit(source, destination):
        attempted.append(Path(destination) == target and Path(source).parent == target.parent
                         and encode(json.loads(Path(source).read_bytes())) == encode(expected))
        if fail:
            raise PermissionError('synthetic replace refusal')
        replace(source, destination)

    with patch.object(os, 'replace', side_effect=audit):
        try:
            result = store.apply_create(layout, plan, confirmed_ticket=plan['ticket'])
        finally:
            if attempted != [True]:
                raise AssertionError('Нужна одна замена L1, подготовившая и реестр, и след принятого решения')
    return result


def register(store, layout, n, saved, before, before_stamp):
    work = layout.workspace
    if n == 10:  # Ещё в ревизии 9 готовим план для другого ID, который не будет создан.
        saved['old'] = store.plan_create(layout, rule(11))
    plan = store.plan_create(layout, rule(n))
    if n == 10:
        saved['used'] = deepcopy(plan)
    view = {**{k: plan[k] for k in ('operation', 'target', 'registry', 'revision')}, 'entry_id': plan['add']['id']}
    unchanged = before == snapshot(work) and before_stamp == stamp(work / REGISTRY)
    expected = expected_profile(n)
    applied = audited_commit(store, layout, plan, expected)
    readback = store.Layout(work, PROFILE)
    status, history = store.status(readback), store.profile_history(readback)
    persisted = json.loads((work / REGISTRY).read_bytes())
    return {**shape(status, history), 'diff': view, 'plan_unchanged': unchanged, 'one_replacement': True,
            'exact_persisted_pair': encode(persisted) == encode(expected) and encode(history) == encode(expected['journal']),
            'returned_matches_readback': encode(applied) == encode(status)}


def bare_view(store, layout):
    return {**inspect(store, layout),
            'bare': 'profile_format' not in json.loads((layout.workspace / REGISTRY).read_bytes())}


def series(store):
    with tempfile.TemporaryDirectory(prefix='ack-i106-series-') as tmp:
        work = Path(tmp).resolve()
        seed(work)
        file = work / REGISTRY
        ctx = store.Layout(work, PROFILE)
        saved = {}
        rows = [observe(store, work, SERIES[0], lambda *_: bare_view(store, ctx))]
        hashes = [sha256(file.read_bytes()).hexdigest()]
        for n, case in enumerate(SERIES[1:], start=1):
            rows.append(observe(store, work, case, lambda a, b: register(store, ctx, n, saved, a, b)))
            hashes.append(sha256(file.read_bytes()).hexdigest())
        final = json.loads(file.read_bytes())  # Снимок до попыток повтора, не ответ apply.

        def repeat(*_):
            requests = [store.plan_create(ctx, rule(10)), store.plan_create(ctx, rule(10))]
            return {**inspect(store, ctx), 'requests': requests}

        def submit(plan):
            return {'result': store.apply_create(ctx, plan, confirmed_ticket=plan['ticket'])}

        rows += [observe(store, work, 'P11-no-change', repeat),
                 observe(store, work, 'N01-old-plan', lambda *_: submit(saved['old'])),
                 observe(store, work, 'N02-used-ticket', lambda *_: submit(saved['used'])),
                 observe(store, work, 'N04-occupied-id', lambda *_: {
                     'plan': store.plan_create(ctx, dict(rule(10), text='Другое тело с тем же ID.'))}),
                 observe(store, work, 'N05-replace-failed', lambda *_: {
                     'result': audited_commit(store, ctx, store.plan_create(ctx, rule(11)), expected_profile(11), fail=True)})]
        return rows, hashes, final


def independent_cases(store):
    ids = ('P12-existing-base', 'N03-byte-drift', 'N06-missing-decision', 'N07-entry-digest', 'N08-bool-revision')
    for case in ids:
        with tempfile.TemporaryDirectory(prefix='ack-i106-fixture-') as tmp:
            work = Path(tmp).resolve()
            seed(work, base_revision=4 if case == 'P12-existing-base' else 0)
            ctx = store.Layout(work, PROFILE)
            file = work / REGISTRY
            if case == 'P12-existing-base':
                yield observe(store, work, case, lambda *_: bare_view(store, ctx))
            elif case == 'N03-byte-drift':
                plan = store.plan_create(ctx, rule(1))
                file.write_bytes(file.read_bytes() + b'\n')  # Та же семантика и ревизия, другие байты.
                yield observe(store, work, case, lambda *_: {
                    'result': store.apply_create(ctx, plan, confirmed_ticket=plan['ticket'])})
            else:
                damaged = expected_profile(2)
                decisions = damaged['journal']['decisions']
                if case == 'N06-missing-decision':
                    decisions.pop()
                    action = lambda *_: {'status': store.status(ctx)}
                elif case == 'N07-entry-digest':
                    decisions[0]['entry_sha256'] = '0' * 64
                    action = lambda *_: {'plan': store.plan_create(ctx, rule(3))}
                else:
                    decisions[0]['profile_revision'] = True
                    action = lambda *_: {'history': store.profile_history(ctx)}
                write(file, damaged)
                yield observe(store, work, case, action)


def timeline(result):
    """П5: отдельно проверяет непрерывность замеров и фактический конечный документ."""
    if type(result) is not dict or type(result.get('rows')) is not list:
        return None
    rows = {row['id']: row for row in result['rows']}
    if any(case not in rows for case in SERIES) or encode(result.get('last_profile')) != encode(expected_profile(10)):
        return None
    chain = [rows[case] for case in SERIES]
    hashes = result.get('profile_file_sha256')
    if (type(hashes) is not list or len(hashes) != 11 or any(type(v) is not str or not HASH.fullmatch(v) for v in hashes)
            or len(set(hashes)) != 11):
        return None
    baseline = chain[0]['digest']['before']
    previous = baseline
    for i, row in enumerate(chain):
        digest = row['digest']
        if digest['before'] != previous or any(digest['after'][k] != baseline[k] for k in ('L0', 'L2', 'L0_manifest')):
            return None
        view = row['observed']['status']
        if encode(view['profile_revision']) != encode(i) or view['release_version'] != RELEASE:
            return None
        previous = digest['after']
    # Повторы и отказ замены должны относиться к этому же десятому состоянию,
    # а не пройти на отдельно подсунутом неизменном дереве.
    for case in ('P11-no-change', 'N01-old-plan', 'N02-used-ticket', 'N04-occupied-id', 'N05-replace-failed'):
        if case not in rows or rows[case]['digest'] != {'before': previous, 'after': previous}:
            return None
    return {'revisions': [r['observed']['status']['profile_revision'] for r in chain], 'distinct_l1_file_hashes': len(set(hashes)),
            'decisions': len(result['last_profile']['journal']['decisions']),
            'release_version': chain[-1]['observed']['status']['release_version'],
            'project_revision': chain[-1]['observed']['status']['project_revision'],
            'fixed_digests': {key: baseline[key] for key in ('L0', 'L2', 'L0_manifest')}}


def main():
    sys.path.insert(0, str(ROOT))
    from kit.base import registry_store

    if not callable(getattr(registry_store, 'profile_history', None)):
        raise AssertionError('П2: отсутствует порт чтения журнала profile_history')
    casebook = json.loads((HERE / 'CASES.json').read_bytes())
    cases = casebook['cases']
    if encode(casebook['format']) != b'1' or not cases or len({row['id'] for row in cases}) != len(cases):
        raise ValueError('Некорректный список П2')
    rows, hashes, final = series(registry_store)
    rows.extend(independent_cases(registry_store))
    result = {'os': platform.system(), 'rows': rows, 'profile_file_sha256': hashes, 'last_profile': final}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    valid_cases = all(row['status'] == 'pass' for row in case_checks(cases, result))
    return 0 if valid_cases and timeline(result) is not None else 1


if __name__ == '__main__':
    raise SystemExit(main())
