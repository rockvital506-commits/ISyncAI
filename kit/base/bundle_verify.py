"""Проверить только внутреннюю целостность ZIP формата И-117 из явных байтов."""
from hashlib import sha256
from io import BytesIO
import re
from struct import Struct, error as StructError
from zipfile import BadZipFile, ZIP_STORED, ZipFile

from . import schema_v2
from .profile_journal import canonical_bytes
from .registry_policy import StoreError

_SYSTEM, _PROFILE = 'kit/base/registry.json', 'profiles/staged/registry.json'
_ROOTS = ('kit', 'profiles/staged')
_MANIFEST = 'manifest.json'
# Закрытый набор формата 1, не список из входного манифеста и не вызов сборщика.
_FILES = frozenset({_SYSTEM, _PROFILE, *('kit/base/' + n for n in (
    'entry.txt', 'START.md', 'SCHEMA-V2.md', 'STORAGE-V2.md', 'OPERATION-CARD.md', 'OPERATION-PLAN.md',
    'bootstrap.py', 'operation_card.py', 'operation_plan.py', 'profile_journal.py', 'registry_journal.py',
    'registry_policy.py', 'registry_store.py', 'schema_v2.py'))})
_MEMBERS = _FILES | {_MANIFEST}
_MIB = 1_048_576
_MAX_FILE, _MAX_TOTAL = _MIB, 4*_MIB
_MAX_MANIFEST, _MAX_ARCHIVE = _MIB + 8_192, 5*_MIB + 65_536
_MAX_DIRECTORY, _MAX_ENTRIES = 8_192, 32
_DATE = (1980, 1, 1, 0, 0, 0)
_MODE = 0o100644 << 16
_END = Struct('<4s4H2IH')
_LOCAL = Struct('<4s5H3I2H')
_ZIP_ERRORS = (BadZipFile, OSError, EOFError, ValueError, OverflowError, RuntimeError, StructError)
_HEX = re.compile('[0-9a-f]{64}')
_MF_FIELDS = {'revision', 'roots', 'files', 'digest'}
_ROW_FIELDS = {'path', 'size', 'sha256'}
_HISTORY_FIELDS = {'profile_format', 'registry_format', 'journal'}


def _reject(where, reason, code='bundle_incomplete'):
    raise StoreError(code, where, details={'reason': reason}) from None


def _mismatch(where, reason):
    _reject(where, reason, 'digest_mismatch')


def _hash(data):
    return sha256(data).hexdigest()


def _end(raw):
    # Граница каталога проверяется до ZipFile: size/count в EOCD также недоверенные.
    if len(raw) < _END.size:
        _reject('archive', 'zip')
    end_at = len(raw) - _END.size
    magic, disk, directory_disk, in_disk, count, size, offset, comment = _END.unpack_from(raw, end_at)
    if (magic != b'PK\x05\x06' or disk or directory_disk or in_disk != count or comment
            or raw[max(0, end_at - 20):max(0, end_at - 16)] == b'PK\x06\x07'):
        _reject('archive', 'zip')
    if size > _MAX_DIRECTORY or count > _MAX_ENTRIES:
        _reject('archive', 'limit')
    if offset + size != end_at:
        _reject('archive', 'layout')
    return count, offset, size


def _regular(info):
    return (info.compress_type == ZIP_STORED and not info.flag_bits and not info.extra and not info.comment
            and info.create_system == 3 and info.create_version == info.extract_version == 20
            and not (info.reserved or info.volume or info.internal_attr)
            and info.external_attr == _MODE and info.date_time == _DATE
            and info.compress_size == info.file_size)


def _layout(raw, infos, directory):
    count, start, size = directory
    names = [i.filename for i in infos]
    if len(infos) != count:
        _reject('archive', 'layout')
    if len(set(names)) != len(names):
        _reject('archive', 'duplicate_member')
    if set(names) != _MEMBERS or any(i.orig_filename != i.filename for i in infos):
        _reject('archive', 'members')
    if names != sorted(names):
        _reject('archive', 'layout')
    if not all(_regular(i) for i in infos):
        _reject('archive', 'format')
    if (any(not 0 < i.file_size <= (_MAX_MANIFEST if i.filename == _MANIFEST else _MAX_FILE) for i in infos)
            or sum(i.file_size for i in infos if i.filename != _MANIFEST) > _MAX_TOTAL):
        _reject('archive', 'limit')
    if size != sum(46 + len(n) for n in names):
        _reject('archive', 'layout')
    # ZipFile сам по себе не исключает неизвестные области между членами. В этом
    # формате записи смежны; локальный заголовок совпадает с проверенным каталогом.
    at = 0
    for info in infos:
        name = info.filename.encode('ascii')
        header = _LOCAL.pack(b'PK\x03\x04', 20, 0, ZIP_STORED, 0, 0x21, info.CRC, info.file_size,
                             info.file_size, len(name), 0) + name
        data_at = at + len(header)
        if info.header_offset != at or raw[at:data_at] != header or data_at + info.file_size > start:
            _reject('archive', 'layout')
        at = data_at + info.file_size
    if at != start:
        _reject('archive', 'layout')
    return dict(zip(names, infos))


def _read(container, info):
    try:
        raw = container.read(info)
    except _ZIP_ERRORS:
        _reject('archive', 'read')
    if len(raw) != info.file_size:
        _reject('archive', 'read')
    return raw


def _hex(value):
    return type(value) is str and _HEX.fullmatch(value) is not None


def _manifest(raw):
    try:
        mf = schema_v2.parse_json(raw)
    except schema_v2.SchemaError:
        _reject('manifest', 'json')
    if (type(mf) is not dict or mf.keys() != _MF_FIELDS or not _hex(mf['digest'])
            or type(mf['revision']) is not int or mf['revision'] < 0 or type(mf['files']) is not list):
        _reject('manifest', 'shape')
    if mf['roots'] != list(_ROOTS):
        _reject('manifest', 'roots')
    rows = mf['files']
    if len(rows) > _MAX_ENTRIES:
        _reject('manifest', 'members')
    names = []
    for row in rows:
        if (type(row) is not dict or row.keys() != _ROW_FIELDS or type(row['path']) is not str
                or type(row['size']) is not int or not 0 < row['size'] <= _MAX_FILE or not _hex(row['sha256'])):
            _reject('manifest', 'shape')
        names.append(row['path'])
    if len(set(names)) != len(names):
        _reject('manifest', 'duplicate_member')
    if set(names) != _FILES:
        _reject('manifest', 'members')
    if sum(r['size'] for r in rows) > _MAX_TOTAL:
        _reject('manifest', 'limit')
    if names != sorted(names) or raw != canonical_bytes(mf) + b'\n':
        _reject('manifest', 'encoding')
    fields = {k: v for k, v in mf.items() if k != 'digest'}
    if _hash(canonical_bytes(fields)) != mf['digest']:
        _mismatch('manifest', 'digest')
    return mf


def _registry(raw, area, where, root):
    try:
        doc = schema_v2.parse_json(raw)
        if area == 'L1' and type(doc) is dict and _HISTORY_FIELDS & doc.keys():
            _reject(where, 'local_history')
        schema_v2.validate_registry(doc, expected_area=area)
    except schema_v2.SchemaError:
        _reject(where, 'registry')
    if doc['roots'] != [root]:
        _reject(where, 'roots')
    return doc


def bundle_verify(archive, *, target='stand'):
    """На успехе только наблюдаемые отпечатки и ревизия; не выдаёт файлы или доверие."""
    if type(target) is not str or target != 'stand':
        _reject('target', 'stand_only')
    if type(archive) is not bytes or not archive:
        _reject('archive', 'bytes')
    if len(archive) > _MAX_ARCHIVE:
        _reject('archive', 'limit')
    directory = _end(archive)
    try:
        container = ZipFile(BytesIO(archive), 'r', allowZip64=False)
    except _ZIP_ERRORS:
        _reject('archive', 'zip')
    with container:
        members = _layout(archive, container.infolist(), directory)
        mf = _manifest(_read(container, members[_MANIFEST]))
        if any(r['size'] != members[r['path']].file_size for r in mf['files']):
            _mismatch('files', 'size')
        registries = {}
        for row in mf['files']:
            name = row['path']
            raw = _read(container, members[name])
            if _hash(raw) != row['sha256']:
                _mismatch('files', 'sha256')
            if name in (_SYSTEM, _PROFILE):
                registries[name] = raw
    _registry(registries[_SYSTEM], 'L0', 'system', _ROOTS[0])
    profile = _registry(registries[_PROFILE], 'L1', 'profile', _ROOTS[1])
    if mf['revision'] != profile['revision']:
        _reject('profile', 'revision')
    return {'bundle_format': 1, 'outcome': 'verified', 'revision': profile['revision'],
            'manifest_digest': mf['digest'], 'archive_sha256': _hash(archive)}
