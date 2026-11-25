#!/usr/bin/env python3
"""Сравнение двух переданных L1 в памяти; исследование, не перенос/слияние."""
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from kit.base import registry_journal, schema_v2

MAX_INPUT = 2_097_152


class ComparisonError(ValueError):
    pass


def _read(raw, label):
    if type(raw) is not bytes or len(raw) > MAX_INPUT:
        raise ComparisonError(label + '_invalid')
    try:
        doc = schema_v2.parse_json(raw)
        registry, journal = registry_journal.unpack_registry(doc, area='L1')
    except (schema_v2.SchemaError, ValueError, TypeError, KeyError, RecursionError) as exc:
        raise ComparisonError(label + '_invalid') from exc
    kind = ('registry_format_2' if 'registry_format' in doc else
            'profile_format_1' if 'profile_format' in doc else 'bare_v2')
    return doc, registry, journal, kind


def compare(left_bytes, right_bytes):
    """Описать только наблюдаемое сравнение; авторство, общий предок и право неизвестны."""
    left_doc, left, lj, lf = _read(left_bytes, 'left')
    right_doc, right, rj, rf = _read(right_bytes, 'right')
    result = {
        'outcome': 'study_only',
        'left_sha256': hashlib.sha256(left_bytes).hexdigest(),
        'right_sha256': hashlib.sha256(right_bytes).hexdigest(),
        'left_format': lf, 'right_format': rf,
        'left_revision': left['revision'], 'right_revision': right['revision'],
        'roots_equal': left['roots'] == right['roots'],
        'profile_identity': 'not_verified', 'history_authenticity': 'not_verified',
        'semantic_conflicts': 'not_checked', 'merge': 'not_implemented',
        'common_prefix_decisions': None, 'shorter_record': None,
    }
    if left['roots'] != right['roots']:
        relation = 'different_roots'
    elif left_bytes == right_bytes:
        relation = 'same_bytes'
    elif left_doc == right_doc:
        relation = 'same_document_different_bytes'
    elif lf != 'registry_format_2' or rf != 'registry_format_2':
        relation = 'incomparable_history_formats'
    elif lj['base_revision'] != rj['base_revision'] or lj['base_entries'] != rj['base_entries']:
        relation = 'different_recorded_baselines'
    else:
        ldec, rdec = lj['decisions'], rj['decisions']
        common = 0
        for lrow, rrow in zip(ldec, rdec):
            if lrow != rrow:
                break
            common += 1
        result['common_prefix_decisions'] = common
        if common < min(len(ldec), len(rdec)):
            relation = 'different_recorded_decisions'
        elif len(ldec) != len(rdec):
            relation = 'recorded_prefix_compatible'
            result['shorter_record'] = 'left' if len(ldec) < len(rdec) else 'right'
        else:
            relation = 'same_recorded_history_different_document'
    result['relation'] = relation
    return result
