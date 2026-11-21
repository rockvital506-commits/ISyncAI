"""Исполнимый контракт v2: JSON, форма и связи. Только чтение данных, не runtime Kit."""
import json
import re

SCHEMA_VERSION = 2
_AUTHORITY = {'L0': 'system_release', 'L1': 'profile_owner', 'L2': 'project_owner'}
_KINDS = frozenset(('contract', 'rule', 'constraint', 'protocol', 'preference'))
_STATES = frozenset(('draft', 'active', 'suspended', 'revoked'))
_HEADER = frozenset(('schema_version', 'area', 'roots', 'entries'))
_ENTRY = frozenset(('id', 'kind', 'authority', 'state', 'parent', 'scope', 'title', 'text', 'basis', 'criterion'))
_PAIR = frozenset(('key', 'value'))
_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}')
_KEY = re.compile(r'[A-Za-z][A-Za-z0-9._-]{0,63}')
_NUMBER = r'(?:0|[1-9][0-9]*)'
_PRE = rf'(?:{_NUMBER}|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)'
_SEMVER = re.compile(rf'{_NUMBER}\.{_NUMBER}\.{_NUMBER}(?:-{_PRE}(?:\.{_PRE})*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?')
_BAD_PATH_CHAR = re.compile(r'[\\:<>"|?*\x00-\x1f\x7f]')
_DEVICE = re.compile(r'(?i:CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])')


class SchemaError(ValueError):
    """Первая диагностика: стадия, машинный код и JSON Pointer ('' — весь вход)."""

    def __init__(self, stage, code, path):
        self.stage = stage
        self.code = code
        self.path = path
        super().__init__(f'{stage}:{code} at {path or "<root>"}')


def _ptr(path, key):
    return path + '/' + str(key).replace('~', '~0').replace('/', '~1')


def _need(condition, code, path, stage='shape'):
    if not condition:
        raise SchemaError(stage, code, path)


def _object(doc, path):
    _need(type(doc) is dict and all(type(key) is str for key in doc), 'type', path)


def _require(doc, fields, path):
    missing = fields - doc.keys()
    if missing:
        raise SchemaError('shape', 'missing_field', _ptr(path, min(missing)))


def _closed(doc, fields, path):
    unknown = doc.keys() - fields
    if unknown:
        raise SchemaError('shape', 'unknown_field', _ptr(path, min(unknown)))


def _text(value, path):
    _need(type(value) is str, 'type', path)
    _need(bool(value.strip()), 'blank', path)
    try:
        value.encode('utf-8')
    except UnicodeEncodeError as error:
        raise SchemaError('shape', 'unicode', path) from error


def _parts(path):
    return () if path == '.' else tuple(path.split('/'))


def _portable_path(value, path, *, allow_dot=False):
    _text(value, path)
    if allow_dot and value == '.':
        return
    _need(not _BAD_PATH_CHAR.search(value) and all(
        part and part not in ('.', '..') and not part.endswith((' ', '.'))
        and not part.startswith(' ') and not _DEVICE.fullmatch(part.split('.', 1)[0].rstrip(' '))
        for part in value.split('/')), 'path', path)


def _matches(value, pattern, code, path):
    _text(value, path)
    _need(pattern.fullmatch(value) is not None, code, path)


def _entry_shape(row, area, path):
    _object(row, path)
    _require(row, _ENTRY, path)
    _closed(row, _ENTRY | _PAIR, path)
    _matches(row['id'], _ID, 'id', path + '/id')
    for field, choices, code in (('kind', _KINDS, 'kind'), ('state', _STATES, 'state'),
                                 ('authority', _AUTHORITY.values(), 'authority')):
        value = row[field]
        _text(value, _ptr(path, field))
        _need(value in choices, code, _ptr(path, field))
    _need(row['authority'] == _AUTHORITY[area], 'authority_area', path + '/authority')
    if row['kind'] == 'contract':
        _need(row['parent'] is None, 'parent_forbidden', path + '/parent')
    else:
        _matches(row['parent'], _ID, 'id', path + '/parent')
    _portable_path(row['scope'], path + '/scope', allow_dot=True)
    for field in ('title', 'text', 'basis', 'criterion'):
        _text(row[field], _ptr(path, field))
    if 'key' in row or 'value' in row:
        _need('key' in row, 'key_pair', path + '/key')
        _need('value' in row, 'key_pair', path + '/value')
        _matches(row['key'], _KEY, 'key', path + '/key')
        _text(row['value'], path + '/value')


def _shape(doc, path, expected_area):
    _object(doc, path)
    _require(doc, _HEADER, path)
    _need(type(doc['schema_version']) is int, 'type', path + '/schema_version')
    _need(doc['schema_version'] == SCHEMA_VERSION, 'schema_version', path + '/schema_version')
    area = doc['area']
    _text(area, path + '/area')
    _need(area in _AUTHORITY, 'unknown_area', path + '/area')
    _need(expected_area is None or area == expected_area, 'area_mismatch', path + '/area')
    version_field = 'release_version' if area == 'L0' else 'revision'
    fields = _HEADER | {version_field}
    _require(doc, fields, path)
    _closed(doc, fields, path)
    if area == 'L0':
        _matches(doc['release_version'], _SEMVER, 'release_version', path + '/release_version')
    else:
        _need(type(doc['revision']) is int, 'type', path + '/revision')
        _need(doc['revision'] >= 0, 'revision', path + '/revision')
    _need(type(doc['roots']) is list, 'type', path + '/roots')
    _need(bool(doc['roots']), 'roots_empty', path + '/roots')
    for i, root in enumerate(doc['roots']):
        _portable_path(root, f'{path}/roots/{i}')
    _need(type(doc['entries']) is list, 'type', path + '/entries')
    for i, entry in enumerate(doc['entries']):
        _entry_shape(entry, area, f'{path}/entries/{i}')


def _within(child, parent):
    return child[:len(parent)] == parent


def _entry_links(entries, path):
    by_id = {}
    for i, row in enumerate(entries):
        _need(row['id'] not in by_id, 'duplicate_id', f'{path}/entries/{i}/id', 'links')
        by_id[row['id']] = row
    for i, row in enumerate(entries):
        if row['kind'] != 'contract':
            current = f'{path}/entries/{i}'
            parent = by_id.get(row['parent'])
            _need(parent is not None, 'parent_missing', current + '/parent', 'links')
            _need(parent['kind'] == 'contract', 'parent_kind', current + '/parent', 'links')
            _need(_within(_parts(row['scope']), _parts(parent['scope'])), 'scope_outside', current + '/scope', 'links')


def _disjoint_roots(documents):
    seen = []
    for path, doc in documents:
        for i, root in enumerate(doc['roots']):
            parts = _parts(root.casefold())
            _need(not any(_within(parts, previous) or _within(previous, parts) for previous in seen),
                  'roots_overlap', f'{path}/roots/{i}', 'links')
            seen.append(parts)


def validate_registry(document, *, expected_area=None):
    """Проверить один документ v2 в памяти. Не нормализует и не меняет его."""
    if expected_area is not None and (type(expected_area) is not str or expected_area not in _AUTHORITY):
        raise ValueError('expected_area: ожидается доверенный контекст L0, L1 или L2')
    _shape(document, '', expected_area)
    _entry_links(document['entries'], '')
    _disjoint_roots((('', document),))


def validate_catalog(documents):
    """Проверить явно переданный набор {area: registry}. Корни сравниваются лексически."""
    _object(documents, '')
    _need(bool(documents), 'empty_set', '')
    _closed(documents, _AUTHORITY.keys(), '')
    selected = [(_ptr('', area), documents[area], area) for area in _AUTHORITY if area in documents]
    for path, document, area in selected:
        _shape(document, path, area)
    for path, document, _ in selected:
        _entry_links(document['entries'], path)
    _disjoint_roots((path, document) for path, document, _ in selected)


def _unique_object(pairs):
    obj = {}
    for key, value in pairs:
        _need(key not in obj, 'duplicate_member', '', 'parse')
        obj[key] = value
    return obj


def _reject_constant(_token):
    raise SchemaError('parse', 'non_finite', '')


def validate_json(data, *, expected_area=None):
    """Прочитать строгий UTF-8 JSON и вернуть исходные разобранные данные после проверки."""
    _need(type(data) in (str, bytes), 'type', '', 'parse')
    try:
        text = data.decode('utf-8') if type(data) is bytes else data
        parsed = json.loads(text, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except SchemaError:
        raise
    except (ValueError, RecursionError) as error:
        raise SchemaError('parse', 'invalid_json', '') from error
    validate_registry(parsed, expected_area=expected_area)
    return parsed
