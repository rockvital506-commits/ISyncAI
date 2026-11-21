"""Внутренний контейнер L1: v2 и последовательно принятые регистрации."""
from hashlib import sha256
import json

from . import schema_v2

PROFILE_FORMAT = 1


def canonical_bytes(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def entry_digest(entry):
    return sha256(canonical_bytes(entry)).hexdigest()


def _require(condition, code, path):
    if not condition:
        raise schema_v2.SchemaError('history', code, path)


def _closed(obj, fields, path):
    _require(type(obj) is dict and obj.keys() == fields, 'shape', path)


def unpack_profile(document):
    """Проверить состояние L1, в том числе соответствие журнала сохранённым записям."""
    if type(document) is not dict or 'profile_format' not in document:
        schema_v2.validate_registry(document, expected_area='L1')
        # Читаем обычный v2 из И-105, не приписывая ему отсутствующую историю.
        return document, {'base_revision': document['revision'], 'decisions': []}
    _closed(document, {'profile_format', 'registry', 'journal'}, '')
    tag = document['profile_format']
    _require(type(tag) is int and tag == PROFILE_FORMAT, 'profile_format', '/profile_format')
    registry, journal = document['registry'], document['journal']
    try:
        schema_v2.validate_registry(registry, expected_area='L1')
    except schema_v2.SchemaError as error:
        raise schema_v2.SchemaError(error.stage, error.code, '/registry' + error.path) from error
    _closed(journal, {'base_revision', 'decisions'}, '/journal')
    base = journal['base_revision']
    revision = registry['revision']
    _require(type(base) is int and 0 <= base <= revision, 'base_revision', '/journal/base_revision')
    rows = journal['decisions']
    entries = registry['entries']
    _require(type(rows) is list, 'shape', '/journal/decisions')
    _require(len(rows) == revision - base and len(rows) <= len(entries), 'length', '/journal/decisions')
    for i, (row, entry) in enumerate(zip(rows, entries[len(entries) - len(rows):])):
        at = f'/journal/decisions/{i}'
        _closed(row, {'operation', 'entry_id', 'profile_revision', 'entry_sha256'}, at)
        n = row['profile_revision']
        _require(type(n) is int and n == base + i + 1, 'sequence', at + '/profile_revision')
        _require(row['operation'] == 'create' and entry['kind'] == 'rule' and entry['state'] == 'draft',
                 'operation', at + '/operation')
        _require(row['entry_id'] == entry['id'], 'entry_id', at + '/entry_id')
        _require(row['entry_sha256'] == entry_digest(entry), 'entry_digest', at + '/entry_sha256')
    return registry, journal


def with_creation(registry, previous):
    """Собрать пару для одной принятой операции; сама функция не пишет."""
    entry = registry['entries'][-1]
    decision = {'operation': 'create', 'entry_id': entry['id'], 'profile_revision': registry['revision'],
                'entry_sha256': entry_digest(entry)}
    return {'profile_format': PROFILE_FORMAT, 'registry': registry,
            'journal': {'base_revision': previous['base_revision'], 'decisions': [*previous['decisions'], decision]}}
