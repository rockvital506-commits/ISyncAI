#!/usr/bin/env python3
"""Исследовательская проверка подписи набора входов, без импорта кандидата и установки."""
import hashlib
import json
import re

DOMAIN = b'DomainAgentKit:bootstrap-binding:study:v1\x00'
MAX_STATEMENT = 8192
MAX_ARTIFACT = 2_097_152
HEX = re.compile(r'[0-9a-f]{64}')
VERSION = re.compile(r'[0-9A-Za-z.+-]{1,128}')
FIELDS = frozenset({'format', 'product', 'candidate_version', 'key_id', 'manifest_sha256',
                    'system_sha256', 'loader_sha256', 'verifier_sha256'})


class BindingError(ValueError):
    pass


def _unique(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError('duplicate')
        obj[key] = value
    return obj


def _parse(raw):
    def no_constant(_):
        raise ValueError('non_finite')
    return json.loads(raw.decode('utf-8'), object_pairs_hook=_unique, parse_constant=no_constant)


def _canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'),
                      allow_nan=False).encode('ascii')


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def assess(statement, signature, *, public_key, verify_signature, manifest, system, loader, verifier):
    """Оценить согласованную подпись с явно доверенными ключом и callback; не выпуск."""
    if (type(statement) is not bytes or not 0 < len(statement) <= MAX_STATEMENT
            or type(signature) is not bytes or len(signature) != 64
            or type(public_key) is not bytes or len(public_key) != 32):
        raise BindingError('input_invalid')
    try:
        doc = _parse(statement)
        if (type(doc) is not dict or set(doc) != FIELDS or type(doc['format']) is not int
                or doc['format'] != 1 or doc['product'] != 'DomainAgentKit'
                or type(doc['candidate_version']) is not str or VERSION.fullmatch(doc['candidate_version']) is None
                or any(type(doc[k]) is not str or HEX.fullmatch(doc[k]) is None
                       for k in ('key_id', 'manifest_sha256', 'system_sha256', 'loader_sha256', 'verifier_sha256'))
                or _canonical(doc) != statement):
            raise BindingError('statement_invalid')
    except BindingError:
        raise
    except (ValueError, TypeError, UnicodeError, KeyError, RecursionError) as exc:
        raise BindingError('statement_invalid') from exc
    if doc['key_id'] != _sha(public_key):
        raise BindingError('key_mismatch')
    if not callable(verify_signature):
        raise BindingError('signature_unchecked')
    try:
        verdict = verify_signature(public_key, DOMAIN + statement, signature)
    except Exception as exc:
        raise BindingError('signature_unchecked') from exc
    if type(verdict) is not bool:
        raise BindingError('signature_unchecked')
    if not verdict:
        raise BindingError('signature_invalid')
    artifacts = {'manifest_sha256': manifest, 'system_sha256': system,
                 'loader_sha256': loader, 'verifier_sha256': verifier}
    if any(type(raw) is not bytes or not 0 < len(raw) <= MAX_ARTIFACT for raw in artifacts.values()):
        raise BindingError('artifact_invalid')
    if any(_sha(raw) != doc[role] for role, raw in artifacts.items()):
        raise BindingError('artifact_mismatch')
    try:
        manifest_doc = _parse(manifest)
        system_doc = _parse(system)
        if (type(manifest_doc) is not dict or type(manifest_doc.get('files')) is not dict
                or manifest_doc.get('product') != doc['product']
                or manifest_doc.get('version') != doc['candidate_version']
                or manifest_doc['files'].get('kit/snapshot_session.py') != doc['loader_sha256']
                or manifest_doc['files'].get('kit/verify_candidate.py') != doc['verifier_sha256']
                or type(system_doc) is not dict or system_doc.get('area') != 'L0'
                or system_doc.get('roots') != ['kit']
                or system_doc.get('release_version') != doc['candidate_version']):
            raise BindingError('identity_mismatch')
    except BindingError:
        raise
    except (ValueError, TypeError, UnicodeError, KeyError, RecursionError) as exc:
        raise BindingError('identity_mismatch') from exc
    return {'outcome': 'study_binding_checked', 'candidate_version': doc['candidate_version'],
            'key_id': doc['key_id'], 'manifest_sha256': doc['manifest_sha256'],
            'system_sha256': doc['system_sha256'], 'key_origin': 'not_verified',
            'semantic_review': 'not_run', 'freshness': 'not_checked', 'installation': 'not_implemented'}
