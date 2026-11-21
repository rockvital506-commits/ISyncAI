"""Собрать полный синтетический срез L0/L1 из явных байтов, без файлового I/O."""
from hashlib import sha256
from io import BytesIO
from zipfile import LargeZipFile, ZIP_STORED, ZipFile, ZipInfo

from . import schema_v2
from .profile_journal import canonical_bytes
from .registry_policy import StoreError

BUNDLE_FORMAT = 1
_SYSTEM, _PROFILE = 'kit/base/registry.json', 'profiles/staged/registry.json'
_ROOTS = ('kit', 'profiles/staged')
_REQUIRED = frozenset({_PROFILE, *('kit/base/' + n for n in (
    'entry.txt', 'START.md', 'SCHEMA-V2.md', 'STORAGE-V2.md', 'OPERATION-CARD.md', 'OPERATION-PLAN.md',
    'bootstrap.py', 'operation_card.py', 'operation_plan.py', 'profile_journal.py', 'registry_journal.py',
    'registry_policy.py', 'registry_store.py', 'schema_v2.py', 'registry.json'))})
_MAX_FILE, _MAX_TOTAL = 1_048_576, 4_194_304
_MANIFEST = 'manifest.json'
_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


def _fail(where, reason):
    raise StoreError('bundle_incomplete', where, details={'reason': reason}) from None


def _hash(raw):
    return sha256(raw).hexdigest()


def _registry(raw, area, where, root):
    try:
        document = schema_v2.parse_json(raw)
        if area == 'L1' and type(document) is dict and {'profile_format', 'registry_format', 'journal'} & document.keys():
            _fail(where, 'local_history')
        schema_v2.validate_registry(document, expected_area=area)
    except schema_v2.SchemaError:
        _fail(where, 'registry')
    if document['roots'] != [root]:
        _fail(where, 'roots')
    return document


def _inputs(files):
    if type(files) is not dict:
        _fail('files', 'shape')
    if len(files) > len(_REQUIRED):
        _fail('files', 'unexpected')
    if any(type(p) is not str for p in files):
        _fail('files', 'shape')
    if files.keys() - _REQUIRED:
        _fail('files', 'unexpected')
    if _REQUIRED - files.keys():
        _fail('files', 'missing')
    payload = {p: files[p] for p in sorted(_REQUIRED)}
    if any(type(raw) is not bytes or not raw for raw in payload.values()):
        _fail('files', 'bytes')
    if any(len(raw) > _MAX_FILE for raw in payload.values()) or sum(map(len, payload.values())) > _MAX_TOTAL:
        _fail('files', 'limit')
    return payload


def _archive(members):
    try:
        with BytesIO() as target:
            with ZipFile(target, 'w', compression=ZIP_STORED, allowZip64=False) as archive:
                for path in sorted(members):
                    info = ZipInfo(path, date_time=_ZIP_TIME)
                    info.create_system = 3
                    info.external_attr = 0o100644 << 16
                    archive.writestr(info, members[path])
            return target.getvalue()
    except (OSError, ValueError, RuntimeError, LargeZipFile):
        _fail('archive', 'build')


def bundle(files, *, target='stand'):
    """Вернуть манифест и законченные байты ZIP; никакого выпуска, установки или проверки чужого ZIP."""
    if type(target) is not str or target != 'stand':
        _fail('target', 'stand_only')
    payload = _inputs(files)
    _registry(payload[_SYSTEM], 'L0', 'system', _ROOTS[0])
    profile = _registry(payload[_PROFILE], 'L1', 'profile', _ROOTS[1])
    manifest = {'revision': profile['revision'], 'roots': list(_ROOTS), 'files': [
        {'path': path, 'size': len(raw), 'sha256': _hash(raw)} for path, raw in payload.items()]}
    manifest['digest'] = _hash(canonical_bytes(manifest))
    data = _archive({**payload, _MANIFEST: canonical_bytes(manifest) + b'\n'})
    return {'bundle_format': BUNDLE_FORMAT, 'outcome': 'bundled', 'manifest': manifest, 'archive': data}
