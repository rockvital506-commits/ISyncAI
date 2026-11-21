#!/usr/bin/env python3
"""П2: матрица допусков и инварианты на отдельных физических фикстурах."""
from hashlib import sha256
import json
from pathlib import Path
import platform
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'research/105'))
from test_layout import case_checks, changed, digests, encode, snapshot, under, write

PROFILE = 'profiles/pilot'
KEY = 'workflow.evidence'
RELEASE = '0.2.0-dev.107'
AUTHORITY = {'L0': 'system_release', 'L1': 'profile_owner', 'L2': 'project_owner'}
BASE_FILES = ('schema_v2.py', 'profile_journal.py', 'registry_store.py', 'registry_policy.py',
              'SCHEMA-V2.md', 'STORAGE-V2.md', 'PROFILE-JOURNAL.md', 'OPERATION-MATRIX.md')


def entry(area, id_, scope='.', *, kind='contract', parent=None, state='active', value=None):
    row = {'id': id_, 'kind': kind, 'state': state, 'parent': parent, 'authority': AUTHORITY[area], 'scope': scope,
           'title': f'Фикстура {id_}', 'text': f'Синтетическая формулировка {id_}.',
           'basis': 'И-107: синтетические данные', 'criterion': 'Проверить причину допуска или отказа.'}
    if value is not None:
        row.update(key=KEY, value=value, text=f'Синтетическая формулировка {id_}: {value}.')
    return row


def keyed(area, id_, scope, value, *, state='active', parent=None):
    return entry(area, id_, scope, kind='rule', parent=parent or {'L0': 'S-1', 'L1': 'T-1', 'L2': 'P-1'}[area],
                 state=state, value=value)


def seed(work, i):
    profile = {'A1-equal': 'kit', 'A1-system-nested': 'kit/pilot', 'A1-project-nested': '.agent-contract/pilot'}.get(i, PROFILE)
    loc = {'L0': 'kit/base/registry.json', 'L1': profile + '/registry.json', 'L2': '.agent-contract/project/registry.json'}
    docs = {'L0': {'roots': ['kit'], 'release_version': RELEASE, 'entries': [entry('L0', 'S-1')]},
            'L1': {'roots': [profile], 'revision': 0, 'entries': [entry('L1', 'T-1', 'docs'),
                    entry('L1', 'T-ref', 'docs/assets', kind='preference', parent='T-1', state='draft')]},
            'L2': {'roots': ['.agent-contract'], 'revision': 7, 'entries': [entry('L2', 'P-1')]}}
    if i in ('A3-plan', 'P-A3-report', 'P-A3-equal', 'P-A3-inactive', 'P-A3-draft-write'):
        docs['L0']['entries'].append(keyed('L0', 'S-key', '.', 'required'))
    if i in ('A3-plan', 'P-A3-report'):
        docs['L1']['entries'].append(keyed('L1', 'T-key', 'docs', 'skip'))
    if i in ('A3-apply-drift', 'P-A3-equal', 'P-A3-siblings', 'P-A3-same-area'):
        docs['L1']['entries'].append(keyed('L1', 'T-key', 'docs', 'required'))
    if i == 'P-A3-report':
        docs['L2']['entries'].append(keyed('L2', 'P-key', 'docs/guide', 'required'))
    if i == 'P-A3-siblings':
        docs['L2']['entries'].append(keyed('L2', 'P-key', 'docs2/guide', 'skip'))
    if i == 'P-A3-inactive':
        docs['L1']['entries'].append(entry('L1', 'T-inactive', 'docs', state='suspended'))
        docs['L1']['entries'].append(keyed('L1', 'T-key', 'docs', 'skip', parent='T-inactive'))
        docs['L1']['entries'].extend(keyed('L1', 'T-' + state, 'docs', 'skip', state=state)
                                     for state in ('draft', 'suspended', 'revoked'))
    if i == 'P-A3-same-area':
        docs['L1']['entries'].insert(0, keyed('L1', 'T-other', 'docs/guide', 'skip'))  # обратный порядок пары
    for area, doc in docs.items():
        doc.update(area=area, schema_version=2)
        write(work / loc[area], doc)
    base = work / 'kit/base'
    for name in BASE_FILES:
        (base / name).write_bytes((ROOT / 'kit/base' / name).read_bytes())
    write(base / 'manifest.json', {'release_version': RELEASE, 'fixture_only': True,
          'files_sha256': {n: sha256((base / n).read_bytes()).hexdigest() for n in (*BASE_FILES, 'registry.json')}})
    (work / '.agent-contract/project/local.txt').write_bytes(b'Independent project content.\n')
    return profile, loc


def stamp(file):
    st = file.lstat()
    return st.st_dev, st.st_ino, st.st_mtime_ns, st.st_ctime_ns


def new_entry():
    return entry('L1', 'T-new', 'docs', kind='rule', state='draft', parent='T-1')


def commit(store, layout, loc, new, before, file_before):
    work = layout.workspace
    file = work / loc['L1']
    first = store.status(layout)
    plan = store.plan_create(layout, new)
    read_only = snapshot(work) == before and stamp(file) == file_before
    applied = store.apply_create(layout, plan, confirmed_ticket=plan['ticket'])  # только тестовое согласие
    final = store.status(layout)
    old = json.loads(before[loc['L1']][1])
    expected = dict(old, entries=[*old['entries'], new], revision=old['revision'] + 1)
    raw_entry = json.dumps(new, ensure_ascii=True, sort_keys=True, separators=(',', ':')).encode('ascii')
    history = {'base_revision': 0, 'decisions': [{'operation': 'create', 'profile_revision': 1, 'entry_id': new['id'],
                                                'entry_sha256': sha256(raw_entry).hexdigest()}]}
    saved = {'profile_format': 1, 'registry': expected, 'journal': history}
    reread = store.profile_history(layout)
    plan_diff = {k: v for k, v in plan.items() if k != 'ticket'}
    expected_diff = {'operation': 'create', 'target': 'L1', 'registry': loc['L1'], 'add': new,
                     'revision': {'from': old['revision'], 'to': expected['revision']}}
    return {'entry_id': plan['add']['id'], 'profile_revision': [first['profile_revision'], final['profile_revision']],
            'project_revision': [first['project_revision'], final['project_revision']], 'plan_read_only': read_only,
            'journal': [[row['profile_revision'], row['entry_id']] for row in reread['decisions']],
            'exact_transition': (encode(json.loads(file.read_bytes())) == encode(saved) and encode(reread) == encode(history)
                                 and encode(store.read_registry(layout, target='L1')) == encode(expected)
                                 and encode(plan_diff) == encode(expected_diff) and encode(applied) == encode(final)
                                 and final['release_version'] == first['release_version'] == RELEASE),
            'conflicts_after': store.report_conflicts(layout)}


def attempt(store, layout, loc, case, before, file_before, pending):
    work, i = layout.workspace, case['id']
    if 'cell' in case:
        op, target = case['cell']['operation'], case['cell']['area']
        try:
            route = store.check_operation(op, target=target)
        except store.StoreError as denied:
            if op == 'create':
                try:
                    store.plan_create(layout, new_entry(), target=target)
                except store.StoreError as port_error:
                    if encode(port_error.diagnostic()) != encode(denied.diagnostic()):
                        raise AssertionError('Диагноз плана расходится с реестром операций') from port_error
                else:
                    raise AssertionError(f'Диагноз есть в реестре, но порт допустил create:{target}')
            raise
        result = {'route': route}
        if op == 'read':
            document = store.read_registry(layout, target=target)
            result.update(area_read=document['area'], ids=[e['id'] for e in document['entries']],
                          exact_read=encode(document) == encode(json.loads(before[loc[target]][1])))
        elif op == 'create':
            result.update(commit(store, layout, loc, new_entry(), before, file_before))
        return result
    if i == 'N-unknown-operation':
        return {'route': store.check_operation('extra', target='L1')}
    if i == 'N-unknown-area':
        return {'registry': store.read_registry(layout, target='L9')}
    if i in ('A2-apply-L0', 'N-apply-L2'):
        plan = store.plan_create(layout, new_entry())
        plan['target'] = i[-2:]
        return {'apply': store.apply_create(layout, plan, confirmed_ticket=plan['ticket'])}
    if i == 'A3-apply-drift':
        return {'apply': store.apply_create(layout, pending, confirmed_ticket=pending['ticket'])}
    if i == 'P-A3-draft-write':
        return commit(store, layout, loc, keyed('L1', 'T-new', 'docs/guide', 'skip', state='draft'), before, file_before)
    if i.startswith('P-A3-'):
        return {'conflicts': store.report_conflicts(layout)}
    new = new_entry()
    if i in ('A2-claim-L0', 'N-claim-L1'):
        new['authority'] = 'system_release'
    changes = {'A4-null': ('parent', None), 'A4-dangling': ('parent', 'missing'),
               'A4-wrong-kind': ('parent', 'T-ref'), 'A4-foreign': ('parent', 'P-1'), 'A4-scope': ('scope', 'docs2/guide'),
               'A4-contract-parent': ('kind', 'contract')}
    if i == 'A4-no-field':
        del new['parent']
    if i in changes:
        field, value = changes[i]
        new[field] = value
    return {'plan': store.plan_create(layout, new, target='L0' if i == 'A2-claim-L0' else 'L1')}


def observe(store, case):
    with tempfile.TemporaryDirectory(prefix='ack-i107-work-') as tmp:
        work = Path(tmp).resolve()
        profile, loc = seed(work, case['id'])
        layout = store.Layout(work, profile)
        old_file = work / loc['L1']
        pending = None
        if case['id'] == 'A3-apply-drift':
            first = snapshot(work)
            pending = store.plan_create(layout, new_entry())
            if snapshot(work) != first:
                raise AssertionError('Подготовка плана до появления противоречия не должна менять файлы')
            path = work / loc['L2']
            doc = json.loads(path.read_bytes())
            doc['entries'].append(keyed('L2', 'P-key', 'docs/guide', 'skip'))
            doc['revision'] += 1
            write(path, doc)  # Смена входной фикстуры после выдачи плана, не действие порта.
            if changed(first, snapshot(work)) != [loc['L2']]:
                raise AssertionError('До apply должен измениться только L2, а не согласованный L1')
        before, file_before = snapshot(work), stamp(old_file)
        protected = ('kit', '.agent-contract')
        protected_stamps = {path: stamp(work / path) for root in protected for path, item in under(before, root).items()
                            if item[0] == 'file'}
        try:
            actual = {'ok': True, **attempt(store, layout, loc, case, before, file_before, pending)}
        except store.StoreError as error:
            actual = {'ok': False, 'error': error.diagnostic()}
        after = snapshot(work)
        actual.update(changed=changed(before, after), registry_untouched=stamp(old_file) == file_before,
                      l0_l2_unchanged=(all(under(before, root) == under(after, root) for root in protected)
                                       and all(stamp(work / path) == old for path, old in protected_stamps.items())))
        return {'id': case['id'], 'observed': actual,
                'digest': {'before': digests(before, profile), 'after': digests(after, profile)}}


def expected_matrix(cases):
    matrix = {}
    for case in cases:
        if cell := case.get('cell'):
            slots = matrix.setdefault(cell['operation'], {})
            if cell['area'] in slots:
                raise ValueError('Повтор ячейки П2')
            slots[cell['area']] = {k: cell[k] for k in ('state', 'code')}
    return matrix


def matrix_matches(cases, result):
    return type(result) is dict and encode(expected_matrix(cases)) == encode(result.get('matrix'))


def main():
    sys.path.insert(0, str(ROOT))
    from kit.base import registry_store

    if not callable(getattr(registry_store, 'check_operation', None)):
        raise AssertionError('П2: отсутствует исполняемый допуск check_operation')
    casebook = json.loads((HERE / 'CASES.json').read_bytes())
    cases = casebook['cases']
    if encode(casebook['format']) != b'1' or not cases or len({r['id'] for r in cases}) != len(cases):
        raise ValueError('Некорректный список испытаний')
    result = {'os': platform.system(), 'matrix': registry_store.operation_matrix(),
              'rows': [observe(registry_store, case) for case in cases]}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if matrix_matches(cases, result) and all(r['status'] == 'pass' for r in case_checks(cases, result)) else 1


if __name__ == '__main__':
    raise SystemExit(main())
