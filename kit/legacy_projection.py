#!/usr/bin/env python3
"""Предварительная проекция части 0.1.36 в L2 v2, без записи и без миграции."""
from __future__ import annotations

import base64
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kit.base import schema_v2
from kit import compare_old, legacy_capsule


class ProjectionError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode('utf-8')


def _make(archive, *, pin, roots):
    try:
        source = legacy_capsule.extract(archive, pin=pin)
        # Чтение проверяет только объявленные версию и минимальную форму истории.
        legacy_capsule.read_history(archive, pin=pin)
        state, project, blockers = compare_old._source(source)
    except (legacy_capsule.CapsuleError, compare_old.ComparisonError) as exc:
        raise ProjectionError(exc.code) from exc

    empty = {'schema_version': 2, 'area': 'L2', 'roots': roots, 'revision': state['revision'], 'entries': []}
    try:
        schema_v2.validate_registry(empty, expected_area='L2')
    except (schema_v2.SchemaError, RecursionError) as exc:
        raise ProjectionError('invalid_roots') from exc

    report = {'projection_format': 1, 'outcome': 'blocked' if blockers else 'proposed',
              'migration_ready': False, 'archive_sha256': pin, 'source_health': 'not_checked',
              'source_project_revision': state['revision'], 'source_project_entries': len(project),
              'blockers': blockers, 'registry_sha256': None, 'comparison': None,
              'not_in_registry': ['legacy_record_metadata', 'legacy_project_metadata',
                                  'legacy_decisions', 'legacy_tombstones', 'legacy_checks', 'legacy_base'],
              'notice': 'legacy_history_not_imported; independent_snapshot_and_migration_required'}
    if blockers:
        return report, None

    entries = []
    for old in state['entries']:
        row = {k: old[k] for k in compare_old.CORE}
        row.update(id=old['id'], parent=old['contract'], authority='project_owner')
        if old['key'] is not None:
            row.update(key=old['key'], value=old['value'])
        entries.append(row)
    registry = {**empty, 'roots': list(roots), 'entries': entries}
    try:
        schema_v2.validate_registry(registry, expected_area='L2')
    except schema_v2.SchemaError as exc:
        report['outcome'] = 'blocked'
        report['blockers'] = [{'code': 'v2_schema', 'stage': exc.stage, 'schema_code': exc.code, 'path': exc.path}]
        return report, None
    except RecursionError as exc:
        raise ProjectionError('target_invalid') from exc
    candidate = _json_bytes(registry)
    if len(candidate) > compare_old.MAX_BYTES:
        report['outcome'] = 'blocked'
        report['blockers'] = [{'code': 'projection_too_large'}]
        return report, None
    try:
        comparison = compare_old.compare(source, {'registry': candidate,
            **{'preserved_' + name: data for name, data in source.items()}})
    except compare_old.ComparisonError as exc:
        raise ProjectionError(exc.code) from exc
    report['comparison'] = comparison
    if comparison['outcome'] != 'core_and_archives_equal':
        report['outcome'] = 'blocked'
        report['blockers'] = [{'code': 'comparison_not_equal'}]
        return report, None
    report['registry_sha256'] = hashlib.sha256(candidate).hexdigest()
    return report, candidate


def analyze(archive, *, pin, roots):
    """Только сводка без тел записей; остаётся чувствительной (ID и хеши)."""
    return _make(archive, pin=pin, roots=roots)[0]


def project(archive, *, pin, roots):
    """Явно возвращает (сводку, байты предложения или None); не записывает их."""
    return _make(archive, pin=pin, roots=roots)


def main():
    try:
        raw = sys.stdin.buffer.read(legacy_capsule.MAX_REQUEST + 1)
        if len(raw) > legacy_capsule.MAX_REQUEST:
            raise ProjectionError('request_size')
        try:
            request = schema_v2.parse_json(raw)
        except (schema_v2.SchemaError, RecursionError) as exc:
            raise ProjectionError('request_invalid') from exc
        if (type(request) is not dict or request.keys() != {'format', 'action', 'archive_base64', 'pin', 'roots'}
                or type(request['format']) is not int or request['format'] != 1
                or request['action'] not in ('analyze', 'project') or type(request['action']) is not str):
            raise ProjectionError('request_invalid')
        try:
            archive = legacy_capsule._decode(request['archive_base64'], legacy_capsule.MAX_CAPSULE)
        except legacy_capsule.CapsuleError as exc:
            raise ProjectionError(exc.code) from exc
        report, candidate = project(archive, pin=request['pin'], roots=request['roots'])
        result = {'report': report}
        if request['action'] == 'project':
            result['registry_base64'] = None if candidate is None else base64.b64encode(candidate).decode('ascii')
    except ProjectionError as exc:
        print(json.dumps({'outcome': 'error', 'code': exc.code}, sort_keys=True))
        return 1
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
