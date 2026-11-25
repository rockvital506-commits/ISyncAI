#!/usr/bin/env python3
"""Байтовый контейнер трёх явно переданных документов и отдельное чтение старой истории."""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kit.base import schema_v2
from kit.compare_old import MAX_BYTES, SOURCE_KEYS

MAX_CAPSULE = 9_000_000
MAX_REQUEST = 12_100_000
HEX = re.compile(r'[0-9a-f]{64}')


class CapsuleError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical(doc):
    return (json.dumps(doc, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode('ascii')


def _decode(text, limit):
    if type(text) is not str or len(text) > ((limit + 2) // 3) * 4:
        raise CapsuleError('invalid_encoding')
    try:
        raw = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise CapsuleError('invalid_encoding') from exc
    if not raw or len(raw) > limit or base64.b64encode(raw).decode('ascii') != text:
        raise CapsuleError('invalid_encoding')
    return raw


def _parse(raw, code):
    try:
        return schema_v2.parse_json(raw)
    except (schema_v2.SchemaError, RecursionError) as exc:
        raise CapsuleError(code) from exc


def prepare(source):
    """Детерминированный контейнер только переданных байтов; не подтверждает происхождение."""
    if type(source) is not dict or source.keys() != SOURCE_KEYS:
        raise CapsuleError('source_shape')
    if any(type(raw) is not bytes or not raw or len(raw) > MAX_BYTES for raw in source.values()):
        raise CapsuleError('source_size_or_type')
    members = {name: {'size': len(source[name]), 'sha256': _sha(source[name]),
                      'base64': base64.b64encode(source[name]).decode('ascii')} for name in sorted(SOURCE_KEYS)}
    archive = _canonical({'format': 1, 'kind': 'legacy-evidence', 'members': members})
    if len(archive) > MAX_CAPSULE:
        raise CapsuleError('capsule_size')
    return {'outcome': 'prepared', 'archive': archive, 'archive_sha256': _sha(archive),
            'source_health': 'not_checked', 'migration_ready': False}


def _unpack(archive, pin):
    if type(pin) is not str or HEX.fullmatch(pin) is None:
        raise CapsuleError('pin_required')
    if type(archive) is not bytes or not archive or len(archive) > MAX_CAPSULE:
        raise CapsuleError('capsule_size_or_type')
    if not hmac.compare_digest(_sha(archive), pin):
        raise CapsuleError('capsule_digest_mismatch')
    doc = _parse(archive, 'capsule_invalid')
    if (type(doc) is not dict or doc.keys() != {'format', 'kind', 'members'}
            or type(doc['format']) is not int or doc['format'] != 1 or doc['kind'] != 'legacy-evidence'
            or type(doc['members']) is not dict or doc['members'].keys() != SOURCE_KEYS):
        raise CapsuleError('capsule_invalid')
    output = {}
    for name in sorted(SOURCE_KEYS):
        part = doc['members'][name]
        if (type(part) is not dict or part.keys() != {'size', 'sha256', 'base64'}
                or type(part['size']) is not int or not 0 < part['size'] <= MAX_BYTES
                or type(part['sha256']) is not str or HEX.fullmatch(part['sha256']) is None):
            raise CapsuleError('capsule_invalid')
        payload = _decode(part['base64'], MAX_BYTES)
        if len(payload) != part['size'] or not hmac.compare_digest(_sha(payload), part['sha256']):
            raise CapsuleError('member_digest_mismatch')
        output[name] = payload
    if _canonical(doc) != archive:
        raise CapsuleError('capsule_noncanonical')
    return output


def extract(archive, *, pin):
    """Возвращает точные байты, включая потенциально чувствительные сведения."""
    return _unpack(archive, pin)


def inspect(archive, *, pin):
    """Выдаёт размеры и хеши, не возвращая тела документов."""
    source = _unpack(archive, pin)
    return {'outcome': 'verified_bytes', 'archive_sha256': pin,
            'members': {k: {'size': len(source[k]), 'sha256': _sha(source[k])} for k in sorted(SOURCE_KEYS)},
            'source_health': 'not_checked', 'migration_ready': False}


def read_history(archive, *, pin):
    """Явное чтение JSON; не утверждает подлинность, полноту или совместимость истории v2."""
    source = _unpack(archive, pin)
    state = _parse(source['state'], 'legacy_data_invalid')
    checks = _parse(source['checks'], 'legacy_data_invalid')
    if (type(state) is not dict or type(checks) is not dict
            or type(state.get('schema_version')) is not int or type(state.get('base')) is not dict
            or type(checks.get('schema_version')) is not int):
        raise CapsuleError('legacy_data_invalid')
    if (state['schema_version'] != 1 or state['base'].get('version') != '0.1.36'
            or checks['schema_version'] != 1):
        raise CapsuleError('unknown_version')
    decisions, removed, observations = state.get('decisions'), state.get('tombstones', []), checks.get('checks')
    revision = state.get('revision')
    if (type(revision) is not int or revision < 0 or type(decisions) is not list or len(decisions) != revision
            or type(removed) is not list or type(observations) is not list
            or any(type(x) is not dict for rows in (decisions, removed, observations) for x in rows)):
        raise CapsuleError('legacy_data_invalid')
    result = {'outcome': 'legacy_history_read', 'archive_sha256': pin, 'project_revision': revision,
              'decisions': decisions, 'tombstones': removed, 'checks': observations,
              'legacy_history_imported': False, 'source_health': 'not_checked', 'migration_ready': False}
    try:
        json.dumps(result, ensure_ascii=True, allow_nan=False)
    except (ValueError, TypeError, RecursionError) as exc:
        raise CapsuleError('legacy_data_invalid') from exc
    return result


def main():
    try:
        raw = sys.stdin.buffer.read(MAX_REQUEST + 1)
        if len(raw) > MAX_REQUEST:
            raise CapsuleError('request_size')
        request = _parse(raw, 'request_invalid')
        if (type(request) is not dict or type(request.get('format')) is not int
                or request['format'] != 1 or type(request.get('action')) is not str):
            raise CapsuleError('request_invalid')
        action = request['action']
        if action == 'prepare' and request.keys() == {'format', 'action', 'source'}:
            source = request['source']
            if type(source) is not dict or source.keys() != SOURCE_KEYS:
                raise CapsuleError('source_shape')
            result = prepare({name: _decode(source[name], MAX_BYTES) for name in SOURCE_KEYS})
            archive = result.pop('archive')
            result['archive_base64'] = base64.b64encode(archive).decode('ascii')
        elif action in ('inspect', 'history') and request.keys() == {'format', 'action', 'archive_base64', 'pin'}:
            archive = _decode(request['archive_base64'], MAX_CAPSULE)
            result = inspect(archive, pin=request['pin']) if action == 'inspect' else read_history(archive, pin=request['pin'])
        else:
            raise CapsuleError('request_invalid')
    except CapsuleError as exc:
        print(json.dumps({'outcome': 'error', 'code': exc.code}, sort_keys=True))
        return 1
    try:
        output = json.dumps(result, ensure_ascii=True, sort_keys=True, allow_nan=False)
    except (ValueError, TypeError, RecursionError):
        print(json.dumps({'outcome': 'error', 'code': 'legacy_data_invalid'}, sort_keys=True))
        return 1
    print(output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
