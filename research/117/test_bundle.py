#!/usr/bin/env python3
"""И-117: независимый оракул состава, байтов и отказа до выдачи архива."""
from collections import Counter
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from hashlib import sha256
from io import BytesIO, StringIO
import json
from pathlib import Path
import platform
import sys
from unittest.mock import patch
from zipfile import ZipFile, ZIP_STORED

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
from kit.base import registry_journal, registry_policy, schema_v2

BOOK = 'research/117/CASES.json'
MODULE = 'kit/base/bundle.py'
SYSTEM = 'kit/base/registry.json'
PROFILE = 'profiles/staged/registry.json'
START = 'kit/base/START.md'
META = 'manifest.json'
ROOTS = ['kit', 'profiles/staged']
BAD = 'SYNTHETIC_DO_NOT_ECHO_117'


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def hash_bytes(data):
    return sha256(data).hexdigest()


def wire(value):
    return canonical(value) + b'\n'


def context(book):
    paths = book['required']
    assert len(paths) == len(set(paths)) == 16 and paths == sorted(paths) and {SYSTEM, PROFILE} <= set(paths)
    sources = {n: (ROOT / n).read_bytes() for n in paths if n not in (SYSTEM, PROFILE)}
    assert sources['kit/base/entry.txt'] == b'kit/base/START.md#0\n'
    assert sources[START].startswith(b'## 0. ') and all(type(v) is bytes and v for v in sources.values())
    return sources


def payload(book, ctx, fixture):
    profile = deepcopy(book['fixtures']['profile'])
    if fixture == 'empty':
        profile.update(entries=[], revision=0)
    elif fixture == 'changed_text':
        profile['entries'][1]['text'] = 'Вторая синтетическая редакция с прежней ревизией.'
    elif fixture == 'next_revision':
        profile['revision'] += 1
    else:
        assert fixture in ('populated', 'reordered', 'different_encoding')
    profile_raw = wire(profile)
    if fixture == 'different_encoding':
        profile_raw = (json.dumps(profile, ensure_ascii=False, indent=2) + '\n\n').encode('utf-8')
    materials = dict(ctx)
    materials[SYSTEM], materials[PROFILE] = wire(book['fixtures']['system']), profile_raw
    if fixture == 'reordered':
        materials = {n: materials[n] for n in sorted(materials, reverse=True)}
    return materials


def old_box(doc, version):
    if version == 1:
        return {'profile_format': 1, 'registry': doc, 'journal': {'base_revision': doc['revision'], 'decisions': []}}
    hashes = {r['id']: hash_bytes(canonical(r)) for r in doc['entries']}
    return {'registry_format': 2, 'registry': doc,
            'journal': {'base_revision': doc['revision'], 'base_entries': hashes, 'decisions': []}}


def args_for(book, ctx, case):
    data = payload(book, ctx, case['fixture'])
    target = 'stand'
    action = case.get('inject')
    if action == 'missing':
        del data[case['path']]
    elif action == 'live':
        target = 'live'
    elif action == 'path_input':
        data = Path('not-a-bundle-' + BAD)
    elif action == 'non_text_name':
        data[123] = data.pop(START)
    elif action in ('include_l2', 'include_local_log', 'include_foreign', 'supplied_manifest'):
        name = {'include_l2': '.agent-contract/project/registry.json', 'include_local_log': 'profiles/staged/decisions.json',
                'include_foreign': '.isai/fixture.txt', 'supplied_manifest': META}[action]
        data[name] = BAD.encode('ascii')
    elif action == 'parent_path':
        data['kit/base/../START.md'] = data.pop(START)
    elif action == 'case_alias':
        data['kit/base/start.md'] = data.pop(START)
    elif action == 'mutable_bytes':
        data[START] = bytearray(data[START])
    elif action == 'empty_start':
        data[START] = b''
    elif action == 'oversize_file':
        data[START] = b'x' * 1_048_577
    elif action == 'oversize_total':
        chunk = b'x' * 1_048_576
        for name in sorted(ctx)[:4]:
            data[name] = chunk
        assert sum(len(b) for b in data.values()) > 4 * 1_048_576 and all(len(b) <= 1_048_576 for b in data.values())
    elif action == 'duplicate_json':
        data[SYSTEM] = b'{"area":"L0","area":"L2"}'
    elif action == 'invalid_utf8':
        data[PROFILE] = b'{"bad": "\xff"}'
    elif action in ('bad_semver', 'wrong_system_root'):
        doc = json.loads(data[SYSTEM])
        if action == 'bad_semver':
            doc['release_version'] = '117'
        else:
            doc['roots'] = ['kit/another']
        data[SYSTEM] = wire(doc)
    elif action in ('wrong_profile_root', 'foreign_area', 'history_two', 'history_one', 'bad_parent', 'bool_revision'):
        doc = json.loads(data[PROFILE])
        if action == 'wrong_profile_root':
            doc['roots'] = ['kit/overlap']
        elif action == 'foreign_area':
            doc = dict(schema_version=2, area='L2', roots=['.agent-contract'], revision=7, entries=[])
        elif action in ('history_two', 'history_one'):
            doc = old_box(doc, 1 if action.endswith('one') else 2)
        elif action == 'bad_parent':
            doc['entries'][1]['parent'] = BAD
        else:
            doc['revision'] = True
        data[PROFILE] = wire(doc)
    else:
        assert action in (None, 'late_archive')
    return {'files': data, 'target': target}


def manifest_for(book, files):
    # Состав задан корпусом до продукта: не читаем имена или ожидания из сборщика.
    base = {'revision': json.loads(files[PROFILE])['revision'], 'roots': ROOTS[:], 'files': [
        {'path': n, 'size': len(files[n]), 'sha256': hash_bytes(files[n])} for n in book['required']]}
    return dict(base, digest=hash_bytes(canonical(base)))


def positive_facts(book, ctx, fixture):
    manifest = manifest_for(book, payload(book, ctx, fixture))
    gold = book['golden'][fixture]
    assert gold['manifest_digest'] == manifest['digest']
    return {'manifest': manifest, 'archive_sha256': gold['archive_sha256'], 'archive_bytes': gold['archive_bytes'],
            'archive_members': 17, 'payload_exact': True, 'fixed_metadata': True}


def inspect_known_archive(book, ctx, fixture, raw):
    """Читатель фиксированного учебного результата, не будущий bundle_verify."""
    facts = positive_facts(book, ctx, fixture)
    assert type(raw) is bytes and len(raw) == facts['archive_bytes'] and hash_bytes(raw) == facts['archive_sha256']
    expected = payload(book, ctx, fixture); expected[META] = wire(facts['manifest'])
    with ZipFile(BytesIO(raw), 'r') as z:
        assert z.namelist() == sorted(expected) and not z.comment
        for member in z.infolist():
            assert (member.date_time, member.create_system, member.external_attr, member.compress_type) == (
                (1980, 1, 1, 0, 0, 0), 3, 0o100644 << 16, ZIP_STORED)
            assert not member.comment and not member.extra and not member.flag_bits
            assert z.read(member) == expected[member.filename]
    return facts


def inspect_packet(book, ctx, fixture, packet):
    assert type(packet) is dict and set(packet) == {'bundle_format', 'outcome', 'manifest', 'archive'}
    assert canonical(packet['bundle_format']) == b'1' and packet['outcome'] == 'bundled'
    facts = inspect_known_archive(book, ctx, fixture, packet['archive'])
    assert canonical(packet['manifest']) == canonical(facts['manifest'])
    return facts


def expected_observation(book, ctx, case):
    if 'error' in case:
        where, reason = case['error']
        error = {'code': 'bundle_incomplete', 'where': where, 'details': {'reason': reason}}
        package = None
        rows = case.get('member_attempts', 0)
        builds = int(bool(rows))
    else:
        error, package = None, positive_facts(book, ctx, case['fixture'])
        builds, rows = 1, 17
    return {'error': error, 'package': package, 'archive_attempts': builds, 'member_attempts': rows,
            'effects': [], 'inputs_unchanged': True, 'quiet': True}


def control(book, ctx):
    for fixture in ('populated', 'empty'):
        files = payload(book, ctx, fixture)
        docs = {'L0': json.loads(files[SYSTEM]), 'L1': json.loads(files[PROFILE])}
        schema_v2.validate_catalog(docs)
    source = book['fixtures']['profile']
    for version in (1, 2):
        doc, journal = registry_journal.unpack_registry(old_box(source, version), area='L1')
        assert doc == source and journal['base_revision'] == 7 and not journal['decisions']
    working = {}
    for name in ('bundle', 'bundle_verify'):
        assert name not in registry_policy.operation_matrix()
        try:
            registry_policy.check_operation(name, target='L1')
        except registry_policy.StoreError as e:
            assert e.code == 'unknown_operation'
            working[name] = e.code
        else:
            raise AssertionError('working_port_changed')
    return {'required_files': 16, 'valid_layouts': 2, 'bare_revisions': [7, 0], 'valid_history_formats': [1, 2],
            'working_port': working}


class Monitor:
    def __init__(self):
        self.enabled = False
        self.effects = []
        sys.addaudithook(self.audit)

    def audit(self, event, _args):
        if self.enabled and (event == 'open' or event.startswith(('os.', 'socket.', 'subprocess.', 'ctypes.', 'shutil.'))):
            self.effects.append(event)
            raise RuntimeError('unexpected_io')

    def call(self, function, kwargs, *, late):
        self.effects = []
        original = deepcopy(kwargs)
        builds = rows = 0
        init, put = ZipFile.__init__, ZipFile.writestr
        out = err = None
        so, se = StringIO(), StringIO()

        def new(obj, *args, **opts):
            nonlocal builds
            builds += 1
            return init(obj, *args, **opts)

        def record(obj, *args, **opts):
            nonlocal rows
            rows += 1
            if late and rows == 8:
                raise OSError(BAD)
            return put(obj, *args, **opts)

        with patch.object(ZipFile, '__init__', new), patch.object(ZipFile, 'writestr', record), redirect_stdout(so), redirect_stderr(se):
            self.enabled = True
            try:
                out = function(**kwargs)
            except registry_policy.StoreError as e:
                err = e.diagnostic()
            finally:
                self.enabled = False
        return out, {'error': err, 'archive_attempts': builds, 'member_attempts': rows, 'effects': list(self.effects),
                     'inputs_unchanged': original == kwargs, 'quiet': not (so.getvalue() or se.getvalue())}


def main():
    book = json.loads((ROOT / BOOK).read_bytes())
    assert book['format'] == 1 and len({c['id'] for c in book['cases']}) == len(book['cases'])
    ctx = context(book); observed_control = control(book, ctx)
    ready = (ROOT / MODULE).is_file()
    if ready:
        from kit.base.bundle import bundle
        monitor = Monitor()
    results = []
    for case in book['cases']:
        base = {'id': case['id']}
        if not ready:
            results.append(dict(base, status='fail', reason='bundle_missing'))
            continue
        try:
            packet, record = monitor.call(bundle, args_for(book, ctx, case), late=case.get('inject') == 'late_archive')
            record['package'] = None if packet is None else inspect_packet(book, ctx, case['fixture'], packet)
            match = canonical(record) == canonical(expected_observation(book, ctx, case))
        except Exception as e:
            results.append(dict(base, status='fail', reason=type(e).__name__))
        else:
            results.append(dict(base, status='pass', observation=record) if match else dict(base, status='fail', reason='oracle_mismatch'))
    count = Counter(r['status'] for r in results)
    data = {'format': 1, 'control': observed_control, 'counts': {k: count[k] for k in ('pass', 'fail', 'not run')},
            'os': platform.system(), 'python': platform.python_version(), 'rows': results}
    print(json.dumps(data, ensure_ascii=False, sort_keys=True))
    return int(bool(count['fail'] or count['not run']))


if __name__ == '__main__':
    raise SystemExit(main())
