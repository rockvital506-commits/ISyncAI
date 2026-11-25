#!/usr/bin/env python3
"""Сравнение выбранных полей 0.1.36 и v2 по переданным байтам; не мигратор."""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kit.base import registry_journal, schema_v2

MAX_BYTES = 2 * 1024 * 1024
MAX_ENVELOPE = 20_000_000
SOURCE_KEYS = {'state', 'checks', 'base_rules'}
CANDIDATE_KEYS = {'registry', 'preserved_state', 'preserved_checks', 'preserved_base_rules'}
LEGACY_ID = re.compile(r'[BP]-[1-9][0-9]{0,11}')
LEGACY_KEY = re.compile(r'[a-z][a-z0-9_.-]{0,63}')
FIELDS = {'id', 'kind', 'contract', 'title', 'state', 'scope', 'text', 'basis', 'criterion',
          'key', 'value', 'revision', 'updated_at', 'reason'}
OPTIONAL = {'owner', 'review_days', 'reviewed_at', 'review_by'}
KINDS = {'contract', 'rule', 'constraint', 'protocol', 'preference'}
STATES = {'draft', 'active', 'suspended', 'revoked'}
CORE = ('kind', 'title', 'state', 'scope', 'text', 'basis', 'criterion')
NOT_CHECKED = ('source_health', 'source_authenticity', 'pending_transactions', 'source_base_integrity',
               'source_conflicts', 'target_conflicts', 'legacy_history_in_new_runtime',
               'legacy_checks_in_new_runtime', 'legacy_base_in_new_runtime',
               'scope_behavior_equivalence', 'legacy_entry_metadata_in_new_runtime', 'legacy_id_allocation',
               'legacy_project_retirement_in_new_runtime', 'target_runtime', 'rollback', 'iteration_131')


class ComparisonError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _inputs(value, keys):
    if type(value) is not dict or value.keys() != keys:
        raise ComparisonError('input_shape')
    if any(type(raw) is not bytes or not raw or len(raw) > MAX_BYTES for raw in value.values()):
        raise ComparisonError('input_size_or_type')


def _json(raw, code):
    try:
        return schema_v2.parse_json(raw)
    except (schema_v2.SchemaError, RecursionError) as exc:
        raise ComparisonError(code) from exc


def _text(value):
    if type(value) is not str or not value.strip() or '\x00' in value:
        return False
    try:
        value.encode('utf-8')
    except UnicodeError:
        return False
    return True


def _legacy_rows(rows, prefix):
    if type(rows) is not list or len(rows) > 4096:
        raise ComparisonError('source_invalid')
    result = {}
    for row in rows:
        if type(row) is not dict or not FIELDS <= row.keys() or row.keys() - FIELDS - OPTIONAL:
            raise ComparisonError('source_invalid')
        ident = row['id']
        if type(ident) is not str or LEGACY_ID.fullmatch(ident) is None or not ident.startswith(prefix + '-') or ident in result:
            raise ComparisonError('source_invalid')
        if type(row['kind']) is not str or row['kind'] not in KINDS or type(row['state']) is not str or row['state'] not in STATES:
            raise ComparisonError('source_invalid')
        if any(not _text(row[k]) for k in ('title', 'scope', 'text', 'basis', 'criterion')):
            raise ComparisonError('source_invalid')
        parent = row['contract']
        if row['kind'] == 'contract':
            if parent is not None or row['key'] is not None or row['value'] is not None:
                raise ComparisonError('source_invalid')
        elif type(parent) is not str or LEGACY_ID.fullmatch(parent) is None:
            raise ComparisonError('source_invalid')
        key, val = row['key'], row['value']
        if not (key is None and val is None or type(key) is str and LEGACY_KEY.fullmatch(key) and _text(val)):
            raise ComparisonError('source_invalid')
        result[ident] = row
    return result


def compare(source, candidate):
    """Сравнивает только указанный объём; одинаковые байты не доказывают миграцию."""
    _inputs(source, SOURCE_KEYS)
    _inputs(candidate, CANDIDATE_KEYS)
    state = _json(source['state'], 'source_invalid')
    checks = _json(source['checks'], 'source_invalid')
    base = _json(source['base_rules'], 'source_invalid')
    if (type(state) is not dict or type(state.get('schema_version')) is not int
            or type(state.get('base')) is not dict or type(base) is not dict or type(checks) is not dict):
        raise ComparisonError('source_invalid')
    if (state['schema_version'] != 1 or state['base'].get('version') != '0.1.36'
            or type(base.get('schema_version')) is not int or base['schema_version'] != 1
            or type(checks.get('schema_version')) is not int or checks['schema_version'] != 1):
        raise ComparisonError('unknown_version')
    if (type(state.get('revision')) is not int or not 0 <= state['revision'] <= 10**12
            or type(state.get('next_id')) is not int or not 1 <= state['next_id'] <= 10**12
            or type(state.get('decisions')) is not list or len(state['decisions']) != state['revision']
            or type(state.get('retired')) is not bool or type(state.get('tombstones', [])) is not list
            or type(checks.get('checks')) is not list or 'entries' not in state or 'entries' not in base):
        raise ComparisonError('source_invalid')
    project = _legacy_rows(state['entries'], 'P')
    if any(int(ident[2:]) >= state['next_id'] for ident in project):
        raise ComparisonError('source_invalid')
    base_rows = _legacy_rows(base['entries'], 'B')
    all_rows = {**base_rows, **project}
    tombstones = state.get('tombstones', [])
    if any(type(row) is not dict or type(row.get('id')) is not str
           or LEGACY_ID.fullmatch(row['id']) is None or not row['id'].startswith('P-') for row in tombstones):
        raise ComparisonError('source_invalid')
    blockers = []
    if state['retired']:
        blockers.append({'code': 'project_retired'})
    if tombstones:
        blockers.append({'code': 'legacy_tombstones', 'count': len(tombstones)})
    for ident, row in sorted(project.items()):
        parent = row['contract']
        if parent is not None:
            if parent not in all_rows or all_rows[parent]['kind'] != 'contract':
                raise ComparisonError('source_invalid')
            if parent.startswith('B-'):
                blockers.append({'code': 'cross_layer_parent', 'id': ident, 'parent': parent})
    try:
        registry, _ = registry_journal.unpack_registry(_json(candidate['registry'], 'target_invalid'), area='L2')
    except (schema_v2.SchemaError, RecursionError) as exc:
        raise ComparisonError('target_invalid') from exc
    current = {row['id']: row for row in registry['entries']}
    differences = []
    if state['revision'] != registry['revision']:
        differences.append({'code': 'project_revision_changed'})
    for ident in sorted(project.keys() - current.keys()):
        differences.append({'code': 'entry_missing', 'id': ident})
    for ident in sorted(current.keys() - project.keys()):
        differences.append({'code': 'entry_unexpected', 'id': ident})
    for ident in sorted(project.keys() & current.keys()):
        old, new = project[ident], current[ident]
        for field in CORE:
            if old[field] != new[field]:
                differences.append({'code': 'field_changed', 'id': ident, 'field': field})
        if old['contract'] != new['parent']:
            differences.append({'code': 'field_changed', 'id': ident, 'field': 'parent'})
        old_pair = None if old['key'] is None else (old['key'], old['value'])
        new_pair = None if 'key' not in new else (new['key'], new['value'])
        if old_pair != new_pair:
            differences.append({'code': 'field_changed', 'id': ident, 'field': 'key_value'})
    for name in sorted(SOURCE_KEYS):
        if source[name] != candidate['preserved_' + name]:
            differences.append({'code': 'archive_changed', 'part': name})
    outcome = 'blocked' if blockers else ('differences' if differences else 'core_and_archives_equal')
    digest = lambda raw: hashlib.sha256(raw).hexdigest()
    return {'comparison_format': 1, 'outcome': outcome, 'migration_ready': False,
            'source_version_declared': '0.1.36', 'source_schema': 1, 'target_schema': 2,
            'source_sha256': {k: digest(source[k]) for k in sorted(SOURCE_KEYS)},
            'candidate_sha256': {k: digest(candidate[k]) for k in sorted(CANDIDATE_KEYS)},
            'source_project_entries': len(project), 'target_project_entries': len(current),
            'blockers': blockers, 'differences': differences, 'not_checked': list(NOT_CHECKED)}


def _decode_map(value, keys):
    if type(value) is not dict or value.keys() != keys:
        raise ComparisonError('input_shape')
    output = {}
    for key, text in value.items():
        if type(text) is not str or len(text) > ((MAX_BYTES + 2) // 3) * 4:
            raise ComparisonError('input_size_or_type')
        try:
            output[key] = base64.b64decode(text, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ComparisonError('input_encoding') from exc
    return output


def main():
    try:
        raw = sys.stdin.buffer.read(MAX_ENVELOPE + 1)
        if len(raw) > MAX_ENVELOPE:
            raise ComparisonError('input_size_or_type')
        request = _json(raw, 'input_shape')
        if (type(request) is not dict or request.keys() != {'format', 'source', 'candidate'}
                or type(request['format']) is not int or request['format'] != 1):
            raise ComparisonError('input_shape')
        result = compare(_decode_map(request['source'], SOURCE_KEYS), _decode_map(request['candidate'], CANDIDATE_KEYS))
    except ComparisonError as exc:
        print(json.dumps({'comparison_format': 1, 'outcome': 'error', 'code': exc.code}, sort_keys=True))
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
