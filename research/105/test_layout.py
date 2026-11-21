#!/usr/bin/env python3
"""П2: физические фикстуры и независимые наблюдения для И-105."""
from collections import Counter
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import re
import stat
import sys
import tempfile
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
L0 = 'kit'
L2 = '.agent-contract'
PROFILE = 'profiles/pilot'
BASE_FILES = ('schema_v2.py', 'registry_store.py', 'SCHEMA-V2.md', 'STORAGE-V2.md')
RELEASE = '0.2.0-dev.105'
MANIFEST = 'kit/base/manifest.json'
HASH = re.compile(r'[0-9a-f]{64}')


def encode(data):
    return json.dumps(data, sort_keys=True, ensure_ascii=True, allow_nan=False).encode('ascii')


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encode(data) + b'\n')


def entry(i, authority, *, parent=None):
    return {'id': i, 'kind': 'rule' if parent else 'contract', 'state': 'draft' if parent else 'active',
            'authority': authority, 'parent': parent, 'scope': 'docs/guide' if parent else '.',
            'title': 'Синтетическая запись ' + i, 'text': 'Хранить материал отдельно от записи.',
            'basis': 'И-105: отдельный тестовый проект', 'criterion': 'Только выбранная область меняет байты.'}


def seed(workspace, case):
    profile = {'P03-explicit-root': 'kit-profile/pilot', 'N01-within-L0': 'kit/profiles/pilot',
               'N02-within-L2': '.agent-contract/profiles/pilot'}.get(case, PROFILE)
    files = {'L0': workspace / 'kit/base/registry.json', 'L1': workspace / profile / 'registry.json',
             'L2': workspace / '.agent-contract/project/registry.json'}
    docs = {'L0': {'roots': [L0], 'release_version': RELEASE, 'entries': [entry('S-1', 'system_release')]},
            'L1': {'roots': [profile], 'revision': 0, 'entries': [entry('T-1', 'profile_owner')]},
            'L2': {'roots': [L2], 'revision': 7, 'entries': [entry('P-1', 'project_owner')]}}
    for area, document in docs.items():
        document.update(area=area, schema_version=2)
    for area in ('L0', 'L2'):
        write(files[area], docs[area])
    for name in BASE_FILES:
        (files['L0'].parent / name).write_bytes((ROOT / 'kit/base' / name).read_bytes())
    write(workspace / MANIFEST, {'release_version': RELEASE, 'fixture_only': True,
          'files_sha256': {name: sha256((files['L0'].parent / name).read_bytes()).hexdigest()
                           for name in (*BASE_FILES, 'registry.json')}})
    (files['L2'].parent / 'handoff.txt').write_bytes(b'Independent project evidence.\n')

    dst = files['L1']
    if case == 'N07-root-symlink':
        dst.parent.parent.mkdir(parents=True)
        dst.parent.symlink_to(os.path.relpath(workspace / L0, dst.parent.parent), target_is_directory=True)
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if case == 'N08-file-symlink':
            dst.symlink_to(os.path.relpath(files['L0'], dst.parent))
        elif case == 'N09-file-hardlink':
            os.link(files['L0'], dst)
        elif case != 'N06-missing':
            document = docs['L2'] if case == 'N05-area-mismatch' else docs['L1']
            if case == 'N04-roots-mismatch':
                document = dict(document, roots=['another-profile'])
            write(dst, document)
    return profile, files


def snapshot(workspace):
    data = {}

    def visit(directory):
        for path in directory.iterdir():
            rel = path.relative_to(workspace).as_posix()
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                data[rel] = ('symlink', os.readlink(path))
            elif stat.S_ISDIR(mode):
                data[rel] = ('dir',)
                visit(path)
            elif stat.S_ISREG(mode):
                data[rel] = ('file', path.read_bytes())
            else:
                raise AssertionError(f'Непредусмотренный тип в испытательной зоне: {rel}')
    visit(workspace)
    return data


def under(snapshot_data, root):
    return {k: v for k, v in snapshot_data.items() if k == root or k.startswith(root + '/')}


def digest_tree(data):
    # Тип, относительный путь и байты, не mtime, абсолютный путь или inode.
    index = {path: ['file', sha256(v[1]).hexdigest()] if v[0] == 'file' else v for path, v in data.items()}
    return sha256(encode(index)).hexdigest()


def digests(data, profile):
    return {'L0': digest_tree(under(data, L0)), 'L1': digest_tree(under(data, profile)),
            'L2': digest_tree(under(data, L2)), 'L0_manifest': sha256(data[MANIFEST][1]).hexdigest()}


def changed(a, b):
    return sorted(k for k in a.keys() | b.keys() if a.get(k) != b.get(k))


def attempt(store, workspace, profile, files, case, before):
    layout = store.Layout(workspace, profile)
    if case in ('P01-status', 'P03-explicit-root'):
        observed = store.status(layout)
        directories = [(workspace / root).lstat() for root in (L0, profile, L2)]
        return {'status': observed, 'distinct_directories': all(stat.S_ISDIR(x.st_mode) for x in directories)
                and len({(x.st_dev, x.st_ino) for x in directories}) == 3}
    if case == 'N06-missing':
        return {'status': store.status(layout)}  # Сам status не достраивает реестр.
    new = entry('T-2', 'profile_owner', parent='T-1')
    if case == 'N12-no-parent':
        new['parent'] = 'absent'
    if case == 'N13-active-entry':
        new['state'] = 'active'
    initial = store.status(layout) if case == 'P02-create' else None
    plan = store.plan_create(layout, new)
    after_plan = snapshot(workspace)
    confirmed = plan['ticket']  # Согласие в сценарии, не имитация реального пользователя.
    if case == 'N03-write-L0':
        plan['target'] = 'L0'
    if case == 'N10-no-confirmation':
        confirmed = None
    if case == 'N11-altered-plan':
        plan['add']['text'] = 'Это уже другой дифф, не показанный при согласии.'
    if case == 'N14-replace-denied':
        with patch.object(store.os, 'replace', side_effect=PermissionError('synthetic refusal')) as replace:
            try:
                return {'result': store.apply_create(layout, plan, confirmed_ticket=confirmed)}
            finally:
                replace.assert_called_once()
                source, destination = replace.call_args.args
                if Path(destination) != files['L1'] or Path(source).parent != files['L1'].parent:
                    raise AssertionError('Замена должна брать временный файл рядом только с реестром L1')
    profile_stat = files['L1'].lstat()
    expected = json.loads(before[files['L1'].relative_to(workspace).as_posix()][1])
    expected['entries'].append(new)
    expected['revision'] += 1
    applied = store.apply_create(layout, plan, confirmed_ticket=confirmed)
    readback = store.status(store.Layout(workspace, profile))
    final_stat = files['L1'].lstat()
    return {'before': initial, 'after': readback, 'plan_changed': changed(before, after_plan),
            'diff': {**{k: plan[k] for k in ('operation', 'target', 'registry', 'revision')},
                     'added': {k: plan['add'][k] for k in ('id', 'kind', 'state', 'parent')}},
            'exact_append': encode(json.loads(files['L1'].read_bytes())) == encode(expected),
            'returned_matches_readback': encode(applied) == encode(readback),
            'registry_replaced': (profile_stat.st_dev, profile_stat.st_ino) != (final_stat.st_dev, final_stat.st_ino)}


def observe(store, case):
    with tempfile.TemporaryDirectory(prefix='ack-i105-workspace-') as tmp:
        root = Path(tmp).resolve()
        profile, files = seed(root, case)
        before = snapshot(root)
        try:
            result = {'ok': True, **attempt(store, root, profile, files, case, before)}
        except store.StoreError as error:
            result = {'ok': False, 'error': error.diagnostic()}
        after = snapshot(root)
        result['changed'] = changed(before, after)
        result['l0_l2_unchanged'] = all(under(before, path) == under(after, path) for path in (L0, L2))
        return {'id': case, 'observed': result, 'digest': {'before': digests(before, profile), 'after': digests(after, profile)}}


def case_checks(cases, result):
    """П5 сравнивает факты, а не верит сводкам или успешному коду процесса."""
    rows = result.get('rows') if type(result) is dict else None
    if type(rows) is not list or any(type(r) is not dict or type(r.get('id')) is not str for r in rows):
        rows = []
    seen = Counter(row['id'] for row in rows)
    expected = {case['id']: case['expected'] for case in cases}
    by_id = {row['id']: row for row in rows}
    results = []
    for i, planned in expected.items():
        issue = 'missing' if seen[i] == 0 else 'duplicate' if seen[i] != 1 else None
        if issue is None:
            row = by_id[i]
            digest = row.get('digest')
            if encode(row.get('observed')) != encode(planned):
                issue = 'observation_mismatch'
            elif (type(digest) is not dict or digest.keys() != {'before', 'after'}
                  or any(type(kind) is not dict or kind.keys() != {'L0', 'L1', 'L2', 'L0_manifest'}
                         or any(type(v) is not str or not HASH.fullmatch(v) for v in kind.values())
                         for kind in digest.values())):
                issue = 'missing_digest'
            elif (any(digest['before'][k] != digest['after'][k] for k in ('L0', 'L2', 'L0_manifest'))
                  or (digest['before']['L1'] != digest['after']['L1']) != bool(planned['changed'])):
                issue = 'digest_mismatch'
        results.append({'id': i, 'status': 'pass' if issue is None else 'fail', 'issue': issue})
    results.extend({'id': i, 'status': 'fail', 'issue': 'unexpected'} for i in sorted(seen.keys() - expected.keys()))
    return results


def main():
    sys.path.insert(0, str(ROOT))
    from kit.base import registry_store

    casebook = json.loads((HERE / 'CASES.json').read_bytes())
    cases = casebook['cases']
    if encode(casebook['format']) != b'1' or not cases or len({case['id'] for case in cases}) != len(cases):
        raise ValueError('Некорректный список обязательных случаев')
    result = {'os': platform.system(), 'rows': [observe(registry_store, case['id']) for case in cases]}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if all(row['status'] == 'pass' for row in case_checks(cases, result)) else 1


if __name__ == '__main__':
    raise SystemExit(main())
