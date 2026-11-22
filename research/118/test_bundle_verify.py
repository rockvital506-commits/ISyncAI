#!/usr/bin/env python3
"""И-118: независимый корпус и оракул целостности, без файлового извлечения."""
from collections import Counter
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from hashlib import sha256
from io import BytesIO, StringIO
import json
from pathlib import Path
import platform
import struct
import sys
from unittest.mock import patch
import warnings
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BOOK = 'research/118/CASES.json'
SOURCE = 'research/117/Synthetic-Bundle-117.zip'
MODULE = 'kit/base/bundle_verify.py'
SYSTEM, PROFILE, META, START = 'kit/base/registry.json', 'profiles/staged/registry.json', 'manifest.json', 'kit/base/START.md'
ROOTS = ['kit', 'profiles/staged']
MIB = 1_048_576
MAX_ARCHIVE, MAX_MANIFEST = 5*MIB + 65_536, MIB + 8_192
STAMP = (1980, 1, 1, 0, 0, 0)
MODE = 0o100644 << 16
MARK = b'SYNTHETIC_DO_NOT_ECHO_118'
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
from kit.base import registry_journal, registry_policy, schema_v2


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def digest(raw):
    return sha256(raw).hexdigest()


def wire(obj):
    return canonical(obj) + b'\n'


def cover(manifest):
    body = {k: v for k, v in manifest.items() if k != 'digest'}
    return {**body, 'digest': digest(canonical(body))}


def manifest_for(files, *, revision=None):
    return cover({'revision': json.loads(files[PROFILE])['revision'] if revision is None else revision, 'roots': ROOTS,
                  'files': [{'path': p, 'size': len(data), 'sha256': digest(data)} for p, data in sorted(files.items())]})


def assemble(rows, *, change_meta=None):
    """Генератор только своих данных, не вызывает продукт или его сериализатор."""
    with BytesIO() as target, warnings.catch_warnings():
        warnings.simplefilter('ignore', UserWarning)  # отдельный случай повторённого имени
        with ZipFile(target, 'w', allowZip64=False) as z:
            for name, data in rows:
                info = ZipInfo(name, date_time=STAMP)
                info.create_system, info.external_attr = 3, MODE
                if change_meta:
                    change_meta(info)
                z.writestr(info, data)
        return target.getvalue()


def with_manifest(files, raw_manifest, **options):
    return assemble(sorted({**files, META: raw_manifest}.items()), **options)


def positive_facts(raw, book):
    with ZipFile(BytesIO(raw)) as z:
        assert z.namelist() == sorted([*book['required'], META]) and not z.comment and z.testzip() is None
        m = json.loads(z.read(META)); files = {n: z.read(n) for n in book['required']}
        assert all(i.compress_type == ZIP_STORED and i.date_time == STAMP and i.external_attr == MODE
                   and i.create_system == 3 and not (i.flag_bits or i.extra or i.comment) for i in z.infolist())
        assert m == manifest_for(files) and z.read(META) == wire(m)
        assert all(0 < len(b) <= MIB for b in files.values()) and sum(map(len, files.values())) <= 4*MIB
        docs = {area: json.loads(files[path]) for area, path in (('L0', SYSTEM), ('L1', PROFILE))}
        schema_v2.validate_catalog(docs)
        assert docs['L0']['roots'] + docs['L1']['roots'] == ROOTS
    return {'bundle_format': 1, 'outcome': 'verified', 'revision': m['revision'],
            'manifest_digest': m['digest'], 'archive_sha256': digest(raw)}


def journal(doc, version):
    if version == 1:
        return {'profile_format': 1, 'registry': doc, 'journal': {'base_revision': doc['revision'], 'decisions': []}}
    hashes = {row['id']: digest(canonical(row)) for row in doc['entries']}
    return {'registry_format': 2, 'registry': doc,
            'journal': {'base_revision': doc['revision'], 'base_entries': hashes, 'decisions': []}}


def context(book):
    raw = (ROOT / SOURCE).read_bytes()
    f = positive_facts(raw, book)
    assert f['archive_sha256'] == book['source']['archive_sha256'] and f['manifest_digest'] == book['source']['manifest_digest']
    assert f['revision'] == book['source']['revision'] == 7 and len(raw) == book['source']['bytes'] == 109297
    with ZipFile(BytesIO(raw)) as z:
        files = {p: z.read(p) for p in book['required']}; m = z.read(META)
    return {'raw': raw, 'files': files, 'manifest': m}


def fill_limit(files, *, overflow=False):
    selected = ['kit/base/OPERATION-CARD.md', 'kit/base/OPERATION-PLAN.md', 'kit/base/SCHEMA-V2.md', START]
    rest = sum(len(b) for p, b in files.items() if p not in selected)
    assert 1 < rest < MIB
    for p in selected[:3]:
        files[p] = b'z' * MIB
    files[START] = b'z' * (MIB - rest + int(overflow))
    assert max(map(len, files.values())) == MIB and sum(map(len, files.values())) == 4*MIB + int(overflow)


def positive(ctx, mode):
    if mode == 'sample':
        return ctx['raw']
    files = dict(ctx['files']); doc = json.loads(files[PROFILE])
    if mode == 'independent_rehash':
        files[START] = files[START][:-1] + bytes((files[START][-1] ^ 1,))
    elif mode == 'boundary':
        fill_limit(files)
    else:
        if mode == 'empty_profile':
            doc.update(entries=[], revision=0)
        elif mode == 'next_revision':
            doc['revision'] += 1
        else:
            assert mode == 'raw_profile'
        files[PROFILE] = ((json.dumps(doc, ensure_ascii=False, indent=2) + '\n\n').encode('utf-8')
                          if mode == 'raw_profile' else wire(doc))
    return with_manifest(files, wire(manifest_for(files)))


def edited(raw, kind):
    """Точечные повреждения только эталонного учебного контейнера."""
    data = bytearray(raw)
    if kind == 'local_header':
        assert raw[:4] == b'PK\x03\x04'
        struct.pack_into('<H', data, 6, 1)
    elif kind == 'encrypted_flag':
        offset = struct.unpack_from('<I', raw, len(raw)-6)[0]
        assert raw[offset:offset+4] == b'PK\x01\x02'
        struct.pack_into('<H', data, offset+8, 1)
    else:
        assert kind == 'data_crc'
        with ZipFile(BytesIO(raw)) as z:
            i = z.getinfo(START)
        offset = i.header_offset + 30 + len(START)
        assert raw[offset:offset+i.file_size].startswith(b'## 0. ')
        data[offset] ^= 1  # CRC заголовков оставляем прежним
    return bytes(data)


def archive_for(book, ctx, c):
    k = c['variant']; raw = ctx['raw']; manifest_raw = ctx['manifest']
    if 'error' not in c:
        return positive(ctx, k)
    if k == 'live': return raw
    if k == 'path': return Path(MARK.decode('ascii') + '.zip')
    if k == 'bytearray': return bytearray(raw)
    if k == 'empty': return b''
    if k == 'archive_limit': return b'x' * (MAX_ARCHIVE + 1)
    if k == 'truncated': return raw[:-1]
    if k == 'prefix': return MARK + raw
    if k == 'tail': return raw + MARK
    if k in ('local_header', 'encrypted_flag', 'data_crc'): return edited(raw, k)
    if k == 'directory_limit': return assemble([(f'only-synthetic-{n:02}.txt', b'x') for n in range(33)])
    files = dict(ctx['files']); m = json.loads(manifest_raw)
    if k in ('tamper', 'archive_missing', 'manifest_missing', 'both_missing'):
        p = c['path']
        if k == 'tamper':
            assert files[p].endswith(b'\n'), p
            files[p] = files[p][:-1] + b' '
        if k in ('archive_missing', 'both_missing'): files.pop(p)
        if k in ('manifest_missing', 'both_missing'):
            m['files'] = [r for r in m['files'] if r['path'] != p]
            manifest_raw = wire(cover(m))
        return with_manifest(files, manifest_raw)
    if k == 'no_manifest': return assemble(sorted(files.items()))
    if k == 'duplicate_zip': return assemble(sorted([*files.items(), (META, manifest_raw), (START, files[START])]))
    if k == 'zip_order': return assemble(sorted([*files.items(), (META, manifest_raw)], reverse=True))
    if k in ('symlink', 'compressed'):
        def meta(info):
            if info.filename == START:
                if k == 'symlink': info.external_attr = 0o120777 << 16
                else: info.compress_type = ZIP_DEFLATED
        return with_manifest(files, manifest_raw, change_meta=meta)
    foreign = '.agent-contract/project/registry.json' if k != 'extra_both' else 'profiles/staged/local-history.json'
    if k in ('extra_zip', 'extra_both'): files[foreign] = MARK
    if k in ('extra_manifest', 'extra_both'):
        m['files'] = sorted([*m['files'], {'path': foreign, 'size': len(MARK), 'sha256': digest(MARK)}], key=lambda r: r['path'])
        manifest_raw = wire(cover(m))
    if k in ('extra_zip', 'extra_manifest', 'extra_both'): return with_manifest(files, manifest_raw)
    if k in ('case_alias', 'traversal'):
        alias = 'kit/base/start.md' if k == 'case_alias' else 'kit/base/../START.md'
        files[alias] = files.pop(START)
        return with_manifest(files, manifest_raw)
    if k == 'file_limit': files[START] = b'z' * (MIB + 1)
    if k == 'total_limit': fill_limit(files, overflow=True)
    if k == 'empty_payload': files[START] = b''
    if k in ('file_limit', 'total_limit', 'empty_payload'): return with_manifest(files, wire(manifest_for(files)))
    if k == 'manifest_limit': return with_manifest(files, b' ' * (MAX_MANIFEST+1))
    if k == 'duplicate_json': return with_manifest(files, b'{"digest":"duplicate","digest":"duplicate"}\n')
    if k == 'bad_utf8': return with_manifest(files, b'{"value":"\xff"}\n')
    if k == 'manifest_whitespace': return with_manifest(files, manifest_raw + b'\n')
    row = next(r for r in m['files'] if r['path'] == START)
    if k == 'unknown_field': m['extra'] = MARK.decode('ascii')
    elif k == 'bool_size': row['size'] = True
    elif k == 'bool_revision': m['revision'] = True
    elif k == 'bad_sha': row['sha256'] = 'A' * 64
    elif k == 'duplicate_row': m['files'].append(dict(row))
    elif k == 'wrong_roots': m['roots'] = ['profiles/staged', 'kit']
    elif k == 'manifest_order': m['files'].reverse()
    elif k == 'wrong_digest': return with_manifest(files, wire(dict(m, digest='0'*64)))
    elif k == 'wrong_file_hash': row['sha256'] = '0'*64
    elif k == 'wrong_size': row['size'] += 1
    elif k == 'wrong_revision': m['revision'] += 1
    else:
        p = SYSTEM if k in ('bad_l0', 'wrong_l0_root') else PROFILE
        doc = json.loads(files[p]); revision = m['revision']
        if k == 'bad_l0': doc['release_version'] = '118'
        elif k == 'wrong_l0_root': doc['roots'] = ['kit/other']
        elif k == 'wrong_l1_root': doc['roots'] = ['profiles/other']
        elif k in ('history_one', 'history_two'): doc = journal(doc, 1 if k == 'history_one' else 2)
        else:
            assert k == 'bad_parent'
            next(r for r in doc['entries'] if r['kind'] != 'contract')['parent'] = 'absent-synthetic-parent-118'
        files[p] = wire(doc)
        return with_manifest(files, wire(manifest_for(files, revision=revision)))
    return with_manifest(files, wire(cover(m)))


def fingerprint(raw):
    if type(raw) in (bytes, bytearray):
        return {'type': type(raw).__name__, 'bytes': len(raw), 'sha256': digest(raw)}
    assert isinstance(raw, Path)
    return {'type': 'path'}


def fixture(book, ctx, case):
    raw = archive_for(book, ctx, case)
    if 'error' not in case:
        good = positive_facts(raw, book)
    else:
        good = None
    return raw, ('live' if case['variant'] == 'live' else 'stand'), {'input': fingerprint(raw), 'verified': good}


def expected_observation(book, c):
    error = dict(zip(('code', 'where', 'reason'), c['error'])) if 'error' in c else None
    if error:
        error['details'] = {'reason': error.pop('reason')}
    return {'error': error, 'verified': book['vectors'][c['id']]['verified'], 'archives': c['archives'],
            'reads': c['reads'], 'effects': [], 'quiet': True, 'input_unchanged': True}


def control(book, ctx):
    doc = json.loads(ctx['files'][PROFILE]); revisions = []
    for kind in ('sample', 'empty_profile'):
        revisions.append(positive_facts(positive(ctx, kind), book)['revision'])
    for v in (1, 2):
        d, h = registry_journal.unpack_registry(journal(doc, v), area='L1')
        assert d == doc and h['base_revision'] == doc['revision'] and h['decisions'] == []
    working = {}
    for name in ('bundle', 'bundle_verify'):
        assert name not in registry_policy.operation_matrix()
        try:
            registry_policy.check_operation(name, target='L1')
        except registry_policy.StoreError as exc:
            assert exc.code == 'unknown_operation'
            working[name] = exc.code
        else:
            raise AssertionError('working_operation')
    return {'source_sha256': digest(ctx['raw']), 'source_members': len(ctx['files']) + 1, 'bare_revisions': revisions,
            'history_formats': [1, 2], 'working_port': working}


class NoEffects(RuntimeError):
    pass


class Monitor:
    def __init__(self):
        self.active = False
        self.effects = []
        sys.addaudithook(self.audit)

    def audit(self, event, _args):
        if self.active and (event == 'open' or event.startswith(('os.', 'socket.', 'subprocess.', 'ctypes.', 'shutil.', 'import'))):
            self.effects.append(event)
            raise NoEffects('effect')

    def invoke(self, module, raw, target):
        before = fingerprint(raw); self.effects = []; archives = reads = 0
        original_open = ZipFile.open

        def construct(*args, **kwargs):
            nonlocal archives
            archives += 1
            return ZipFile(*args, **kwargs)

        def member(z, name, mode='r', *args, **kwargs):
            nonlocal reads
            if mode != 'r':
                self.effects.append('zip_write')
                raise NoEffects('zip_write')
            reads += 1
            return original_open(z, name, mode, *args, **kwargs)

        out, err = StringIO(), StringIO()
        result = error = None
        with patch.object(module, 'ZipFile', construct), patch.object(ZipFile, 'open', member), redirect_stdout(out), redirect_stderr(err):
            self.active = True
            try:
                result = module.bundle_verify(raw, target=target)
            except registry_policy.StoreError as exc:
                error = exc.diagnostic()
            finally:
                self.active = False
        return {'error': error, 'verified': result, 'archives': archives, 'reads': reads, 'effects': list(self.effects),
                'quiet': not (out.getvalue() or err.getvalue()), 'input_unchanged': fingerprint(raw) == before}


def main():
    book = json.loads((ROOT/BOOK).read_bytes()); assert type(book['format']) is int and book['format'] == 1
    assert len(book['required']) == len(set(book['required'])) == 16 and book['required'] == sorted(book['required'])
    ids = [r['id'] for r in book['cases']]; assert len(ids) == len(set(ids)) and set(ids) == book['vectors'].keys()
    ctx = context(book); baseline_control = control(book, ctx)
    ready = (ROOT/MODULE).is_file()
    if ready:
        from kit.base import bundle_verify
        monitor = Monitor()
    rows = []
    for c in book['cases']:
        head = {'id': c['id']}
        try:
            raw, target, vector = fixture(book, ctx, c)
            assert canonical(vector) == canonical(book['vectors'][c['id']]), 'fixture_drift'
            if not ready:
                rows.append(dict(head, status='fail', reason='bundle_verify_missing'))
                continue
            got = monitor.invoke(bundle_verify, raw, target)
            ok = canonical(got) == canonical(expected_observation(book, c))
        except Exception as exc:
            rows.append(dict(head, status='fail', reason=type(exc).__name__))
        else:
            rows.append(dict(head, status='pass', observation=got) if ok else dict(head, status='fail', reason='oracle_mismatch'))
    counts = Counter(r['status'] for r in rows)
    result = {'format': 1, 'os': platform.system(), 'python': platform.python_version(), 'control': baseline_control, 'rows': rows,
              'counts': {k: counts[k] for k in ('pass', 'fail', 'not run')}}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return int(bool(counts['fail'] or counts['not run']))


if __name__ == '__main__':
    raise SystemExit(main())
