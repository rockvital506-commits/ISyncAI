#!/usr/bin/env python3
"""Механическая проверка исследовательского черновика L0; не активация и не смысловой аудит."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from kit.base import schema_v2

ROADMAP_SHA = '7712160f17edda9db74dbf9045f0662c0d7cee90c788e389a0ab68bb1b286e94'
# Явный перечень именно текущей исследовательской гипотезы; не системная политика.
ANCHORS = {
    'SYS-CONTRACT': ('contract', None, 'both', 'системные контракты, механизмы и правила операций самого Kit;'),
    'SYS-ROOTS': ('constraint', 'SYS-CONTRACT', 'kit', 'A1: корни областей не пересекаются;'),
    'SYS-IMMUTABLE': ('constraint', 'SYS-CONTRACT', 'kit', 'A2: L0 не изменяется операциями L1/L2;'),
    'SYS-CONFLICT': ('constraint', 'SYS-CONTRACT', 'both', 'нет молчаливого победителя;'),
    'SYS-PARENT': ('constraint', 'SYS-CONTRACT', 'kit', 'дочерняя сущность имеет допустимый контракт-родитель и не\n  выходит за его scope.'),
    'SYS-CONFIRM': ('protocol', 'SYS-CONTRACT', 'kit', 'план с точным диффом → отдельное подтверждение\n  актуального плана → применение и проверка.'),
    'SYS-MOVE': ('protocol', 'SYS-CONTRACT', 'kit', 'области **с удалением исходной записи**; это не копирование с сохранением источника.'),
    'SYS-PROJECT-MODE': ('rule', 'SYS-CONTRACT', 'project', 'сущности, необходимые для решения; Kit не становится предметом проектной задачи.'),
    'SYS-KIT-MODE': ('rule', 'SYS-CONTRACT', 'kit', 'проектные сведения допустимы лишь если нужны самой операции.'),
    'SYS-RECOVERY': ('constraint', 'SYS-CONTRACT', 'kit', 'поддерживаемое обновление собственного Kit сохраняет зарегистрированные сущности и\n  их нужную историю; сбой и восстановление проверены на копии.'),
}


class AuditError(ValueError):
    pass


def check(proposal, roadmap_bytes, manifest_bytes):
    """Проверяет ограниченную форму и точные цитаты, но не их смысл или авторство."""
    if (type(proposal) is not dict or set(proposal) != {'proposal_format', 'status', 'roadmap_version',
            'roadmap_sha256', 'candidate_manifest_sha256', 'registry', 'trace'}
            or type(proposal['proposal_format']) is not int or proposal['proposal_format'] != 1
            or proposal['status'] != 'draft_not_active' or proposal['roadmap_version'] != '3.1.0'):
        raise AuditError('proposal_shape')
    if (hashlib.sha256(roadmap_bytes).hexdigest() != ROADMAP_SHA
            or proposal['roadmap_sha256'] != ROADMAP_SHA
            or proposal['candidate_manifest_sha256'] != hashlib.sha256(manifest_bytes).hexdigest()):
        raise AuditError('source_snapshot_mismatch')
    try:
        manifest = schema_v2.parse_json(manifest_bytes)
        registry = proposal['registry']
        schema_v2.validate_registry(registry, expected_area='L0')
        roadmap = roadmap_bytes.decode('utf-8')
    except (ValueError, TypeError, UnicodeError, KeyError, RecursionError) as exc:
        raise AuditError('registry_or_source_invalid') from exc
    if (type(manifest) is not dict or manifest.get('product') != 'DomainAgentKit'
            or registry['release_version'] != manifest.get('version') or registry['roots'] != ['kit']):
        raise AuditError('candidate_reference_mismatch')
    rows = registry['entries']
    if len(rows) != len(ANCHORS) or {r['id'] for r in rows} != set(ANCHORS):
        raise AuditError('draft_coverage')
    for row in rows:
        kind, parent, _, _ = ANCHORS[row['id']]
        if (row['state'] != 'draft' or row['kind'] != kind or row['parent'] != parent
                or row['scope'] != '.' or row['authority'] != 'system_release'
                or 'key' in row or 'value' in row or not row['basis'].startswith('ROADMAP.md §')):
            raise AuditError('draft_entry_invalid')
    trace = proposal['trace']
    if type(trace) is not list or len(trace) != len(ANCHORS):
        raise AuditError('trace_invalid')
    seen = set()
    for item in trace:
        if type(item) is not dict or set(item) != {'id', 'proposed_mode', 'roadmap_quote'}:
            raise AuditError('trace_invalid')
        ident = item['id']
        if type(ident) is not str or ident not in ANCHORS or ident in seen:
            raise AuditError('trace_invalid')
        seen.add(ident)
        _, _, mode, quote = ANCHORS[ident]
        if item['proposed_mode'] != mode or item['roadmap_quote'] != quote or quote not in roadmap:
            raise AuditError('trace_invalid')
    return {'outcome': 'draft_shape_pass', 'entries': len(rows), 'active_entries': 0,
            'semantic_review': 'not_run', 'independent_origin': 'not_verified'}


def main():
    try:
        proposal = schema_v2.parse_json((ROOT/'research/kilo/l0-proposal/DRAFT.json').read_bytes())
        result = check(proposal, (ROOT/'research/kilo/ROADMAP.md').read_bytes(),
                       (ROOT/'kit/KIT-VERSION.json').read_bytes())
    except (AuditError, OSError, ValueError, TypeError, RecursionError):
        print(json.dumps({'outcome': 'fail', 'reason': 'proposal_invalid'}), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
