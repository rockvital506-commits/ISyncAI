#!/usr/bin/env python3
"""Локальная проверка ограниченных инвариантов; не установка hook или CI."""
from __future__ import annotations

import argparse
import hmac
import json
import sys
from pathlib import Path

# Код и зависимости берутся рядом с этим файлом, не из проверяемого корня кандидата.
if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kit.verify_candidate import HEX, VerificationError, verify
from kit.base import registry_policy, registry_store, schema_v2
from kit.base.registry_store import Layout, StoreError


class GuardViolation(ValueError):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def guard(candidate_root, layout, *, manifest_pin, system_pin):
    """Проверяет выбранные снимки; pin и код проверяющего должны быть доверенными извне."""
    if (type(manifest_pin) is not str or HEX.fullmatch(manifest_pin) is None
            or type(system_pin) is not str or HEX.fullmatch(system_pin) is None):
        raise GuardViolation('pins_required')
    try:
        candidate = verify(candidate_root, pin=manifest_pin)
    except (VerificationError, RecursionError) as exc:
        raise GuardViolation('candidate_unverified') from exc
    try:
        loaded = registry_store._load(layout)
    except (StoreError, RecursionError) as exc:
        raise GuardViolation('workspace_unverified') from exc
    if not hmac.compare_digest(loaded.inputs_sha256['L0'], system_pin):
        raise GuardViolation('system_digest_mismatch')
    try:
        schema_v2.validate_catalog(loaded.documents)
    except (schema_v2.SchemaError, RecursionError) as exc:
        raise GuardViolation('catalog_invalid') from exc
    if registry_policy.find_conflicts(loaded.documents):
        raise GuardViolation('structural_conflict')
    unstructured = sum(1 for doc in loaded.documents.values() for row in registry_policy.active_entries(doc)
                       if row['kind'] != 'contract' and 'key' not in row)
    return {'guard_format': 1, 'outcome': 'pass', 'candidate': candidate['candidate'],
            'manifest_sha256': candidate['manifest_sha256'],
            'inputs_sha256': dict(loaded.inputs_sha256), 'conflicts_checked': 'structured_key_value',
            'unstructured_active_entries': unstructured, 'text_conflicts': 'not_checked'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate-root', type=Path, required=True)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--profile-root', required=True)
    parser.add_argument('--manifest-pin', help='заранее доверенный SHA-256 манифеста кандидата')
    parser.add_argument('--system-pin', help='заранее доверенный SHA-256 системного реестра L0')
    args = parser.parse_args()
    try:
        result = guard(args.candidate_root, Layout(args.workspace, args.profile_root),
                       manifest_pin=args.manifest_pin, system_pin=args.system_pin)
    except GuardViolation as exc:
        print(json.dumps({'guard_format': 1, 'outcome': 'violation', 'reason': exc.reason}, sort_keys=True))
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
