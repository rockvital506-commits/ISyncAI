#!/usr/bin/env python3
"""Исследовательская модель входов D04 в памяти; не установщик и не доверенная поставка."""
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from kit.base import schema_v2

HEX = re.compile(r'[0-9a-f]{64}')
MAX_L0 = 2_097_152


class ModelError(ValueError):
    pass


def _wire(document):
    return (json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')


def model(l0_bytes, *, system_pin, candidate_version, profile_root):
    """Выдать описание и байты трёх реестров в памяти; не читает и не пишет ФС.

    Все входы — явные гипотезы вызывающего. Нет проверки манифеста, происхождения,
    прав, состояния цели, подтверждения или выполнения; возвращённые байты — не установка.
    """
    if type(l0_bytes) is not bytes or len(l0_bytes) > MAX_L0:
        raise ModelError('l0_invalid')
    if type(system_pin) is not str or HEX.fullmatch(system_pin) is None:
        raise ModelError('pin_invalid')
    if hashlib.sha256(l0_bytes).hexdigest() != system_pin:
        raise ModelError('pin_mismatch')
    try:
        l0 = schema_v2.validate_json(l0_bytes, expected_area='L0')
        if l0['roots'] != ['kit']:
            raise ModelError('l0_root_mismatch')
        if type(candidate_version) is not str or l0['release_version'] != candidate_version:
            raise ModelError('version_mismatch')
        l1 = {'schema_version': 2, 'area': 'L1', 'roots': [profile_root], 'revision': 0, 'entries': []}
        l2 = {'schema_version': 2, 'area': 'L2', 'roots': ['.domain-agent-kit'], 'revision': 0, 'entries': []}
        schema_v2.validate_catalog({'L0': l0, 'L1': l1, 'L2': l2})
    except ModelError:
        raise
    except (schema_v2.SchemaError, ValueError, TypeError, KeyError, RecursionError) as exc:
        raise ModelError('catalog_invalid') from exc
    files = {'kit/base/registry.json': l0_bytes,
             profile_root + '/registry.json': _wire(l1),
             '.domain-agent-kit/project/registry.json': _wire(l2)}
    rows = [{'path': path, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
            for path, data in sorted(files.items())]
    return {'outcome': 'study_only', 'files': rows, 'l0_semantics': 'not_checked',
            'origin': 'not_verified', 'destination': 'not_selected', 'apply': 'not_implemented'}, files
