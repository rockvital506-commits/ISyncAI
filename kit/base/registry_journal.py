"""Локальная история L1/L2: цепочка версий записей, а не архив их тел."""
import re

from . import profile_journal, schema_v2

REGISTRY_FORMAT = 2
_REVISION = {'L1': 'profile_revision', 'L2': 'project_revision'}
_DIGEST = re.compile(r'[0-9a-f]{64}')
_OPERATIONS = ('create', 'edit', 'suspend', 'resume', 'revoke', 'delete')


def _need(condition, code, path):
    if not condition:
        raise schema_v2.SchemaError('history', code, path)


def _closed(value, fields, path):
    _need(type(value) is dict and value.keys() == fields, 'shape', path)


def _fingerprints(entries):
    return {entry['id']: profile_journal.entry_digest(entry) for entry in entries}


def _is_id(value):
    return type(value) is str and schema_v2._ID.fullmatch(value) is not None


def _is_digest(value):
    return type(value) is str and _DIGEST.fullmatch(value) is not None


def unpack_registry(document, *, area):
    """Читать голый v2, историю регистраций L1 (1) или историю манипуляций (2)."""
    revision_field = _REVISION[area]
    if type(document) is not dict or 'registry_format' not in document:
        if area == 'L1':
            return profile_journal.unpack_profile(document)
        schema_v2.validate_registry(document, expected_area=area)
        return document, {'base_revision': document['revision'], 'decisions': []}

    _closed(document, {'registry_format', 'registry', 'journal'}, '')
    tag = document['registry_format']
    _need(type(tag) is int and tag == REGISTRY_FORMAT, 'registry_format', '/registry_format')
    registry, journal = document['registry'], document['journal']
    try:
        schema_v2.validate_registry(registry, expected_area=area)
    except schema_v2.SchemaError as error:
        raise schema_v2.SchemaError(error.stage, error.code, '/registry' + error.path) from error
    _closed(journal, {'base_revision', 'base_entries', 'decisions'}, '/journal')
    base, anchor, decisions = journal['base_revision'], journal['base_entries'], journal['decisions']
    revision = registry['revision']
    _need(type(base) is int and 0 <= base <= revision, 'base_revision', '/journal/base_revision')
    _need(type(anchor) is dict and all(_is_id(k) and _is_digest(v) for k, v in anchor.items()),
          'base_entries', '/journal/base_entries')
    path = '/journal/decisions'
    _need(type(decisions) is list, 'shape', path)
    _need(len(decisions) == revision - base, 'length', path)

    hashes, retired = dict(anchor), set()
    for i, decision in enumerate(decisions):
        at = f'{path}/{i}'
        _closed(decision, {'operation', 'entry_id', revision_field, 'before_sha256', 'after_sha256'}, at)
        n = decision[revision_field]
        _need(type(n) is int and n == base + i + 1, 'sequence', at + '/' + revision_field)
        operation, id_ = decision['operation'], decision['entry_id']
        before, after = decision['before_sha256'], decision['after_sha256']
        _need(type(operation) is str and operation in _OPERATIONS, 'operation', at + '/operation')
        _need(_is_id(id_) and id_ not in retired, 'entry_id', at + '/entry_id')
        _need(before is None if operation == 'create' else _is_digest(before), 'entry_digest', at + '/before_sha256')
        _need(hashes.get(id_) == before, 'entry_chain', at + '/before_sha256')
        _need(after is None if operation == 'delete' else _is_digest(after) and after != before,
              'entry_digest', at + '/after_sha256')
        if operation == 'delete':
            del hashes[id_]
            retired.add(id_)
        else:
            hashes[id_] = after
    _need(hashes == _fingerprints(registry['entries']), 'final_entries', path)
    return registry, journal


def is_retired(journal, entry_id):
    return any(row['operation'] == 'delete' and row['entry_id'] == entry_id for row in journal['decisions'])


def with_change(registry, previous, journal, *, operation, before, after):
    """Добавить ровно одно решение к уже проверенной истории; ничего не записывает."""
    decisions = journal['decisions']
    if 'base_entries' in journal:
        anchor = journal['base_entries']
    else:
        entries = previous['entries']
        # У формата 1 именно последние записи соответствуют известным решениям create.
        anchor = _fingerprints(entries[:len(entries) - len(decisions)])
        decisions = [{'operation': 'create', 'entry_id': row['entry_id'], 'profile_revision': row['profile_revision'],
                      'before_sha256': None, 'after_sha256': row['entry_sha256']} for row in decisions]
    decision = {'operation': operation, 'entry_id': (after if after is not None else before)['id'],
                _REVISION[registry['area']]: registry['revision'],
                'before_sha256': None if before is None else profile_journal.entry_digest(before),
                'after_sha256': None if after is None else profile_journal.entry_digest(after)}
    return {'registry_format': REGISTRY_FORMAT, 'registry': registry,
            'journal': {'base_revision': journal['base_revision'], 'base_entries': anchor,
                        'decisions': [*decisions, decision]}}
