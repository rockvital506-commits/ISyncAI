#!/usr/bin/env python3
"""Модель явной политики выпуска в памяти. Не запускать как проверку поставки."""
import hashlib
import json
import re

# Заранее доверенная копия схемы; код проверяемого архива не импортируется.
import release_schema_v2_study as schema

DOMAIN = b'DomainAgentKit:release-policy:study:v1\x00'
MAX_DOCUMENT = 2_097_152
MAX_FILES = 1024
MAX_TOTAL = 16 * 1024 * 1024
HEX = re.compile(r'[0-9a-f]{64}\Z')
VERSION = re.compile(r'[0-9A-Za-z.+-]{1,128}\Z')
NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z')
STATEMENT = frozenset(('format', 'product', 'channel', 'sequence', 'version', 'key_id',
                       'manifest_sha256', 'system_sha256', 'loader_sha256', 'verifier_sha256'))
POLICY = frozenset(('format', 'product', 'channel', 'keys', 'revoked', 'required_paths',
                    'loader_sha256', 'verifier_sha256', 'checkpoint'))


class PolicyError(ValueError):
    pass


def canonical(obj):
    return json.dumps(obj, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _pairs(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj: raise ValueError('duplicate')
        obj[key] = value
    return obj


def _parse(raw):
    def reject(_): raise ValueError('constant')
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_DOCUMENT: raise ValueError('size')
    return json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs, parse_constant=reject)


def _hash(value):
    return type(value) is str and HEX.fullmatch(value) is not None


def _path(value):
    if type(value) is not str: return False
    parts = value.split('/')
    return len(parts) in (2, 3) and parts[0] == 'kit' and all(NAME.fullmatch(p) for p in parts) and (len(parts) == 2 or parts[1] == 'base')


def _compatible_paths(paths):
    """Состав файлов не должен требовать файл и каталог с одним именем."""
    names = set(paths)
    return ('kit/KIT-VERSION.json' not in names and
            not any('/'.join(path.split('/')[:i]) in names
                    for path in names for i in range(1, len(path.split('/')))))


def assess(statement, signature, *, policy, files, manifest, verify_signature):
    """Предполагает ВНЕШНИЕ доверенные policy и callback; не читает и не изменяет файлы."""
    try:
        doc = _parse(statement)
        if (type(doc) is not dict or set(doc) != STATEMENT or canonical(doc) != statement or
                type(doc['format']) is not int or doc['format'] != 1 or doc['product'] != 'DomainAgentKit' or
                not isinstance(doc['channel'],str) or not NAME.fullmatch(doc['channel']) or
                type(doc['sequence']) is not int or not 1 <= doc['sequence'] <= 2**63-1 or
                type(doc['version']) is not str or not VERSION.fullmatch(doc['version']) or
                any(not _hash(doc[k]) for k in ('key_id','manifest_sha256','system_sha256','loader_sha256','verifier_sha256'))):
            raise PolicyError('statement_invalid')
    except PolicyError: raise
    except (TypeError,ValueError,UnicodeError,RecursionError,KeyError) as error:
        raise PolicyError('statement_invalid') from error
    try:
        if (type(policy) is not dict or set(policy) != POLICY or type(policy['format']) is not int or policy['format'] != 1 or
                policy['product'] != 'DomainAgentKit' or type(policy['channel']) is not str or
                not NAME.fullmatch(policy['channel']) or type(policy['keys']) is not dict or not 1 <= len(policy['keys']) <= 16 or
                type(policy['revoked']) is not list or len(policy['revoked']) > 16 or
                any(not _hash(k) for k in policy['revoked']) or len(set(policy['revoked'])) != len(policy['revoked']) or
                type(policy['required_paths']) is not list or not 1 <= len(policy['required_paths']) <= MAX_FILES or
                any(not _path(p) for p in policy['required_paths']) or len(set(policy['required_paths'])) != len(policy['required_paths']) or
                not _compatible_paths(policy['required_paths']) or
                any(not _hash(policy[k]) for k in ('loader_sha256','verifier_sha256'))):
            raise PolicyError('policy_invalid')
        for key_id,key in policy['keys'].items():
            if not _hash(key_id) or type(key) is not bytes or len(key) != 32 or sha(key) != key_id:
                raise PolicyError('policy_invalid')
        if not set(policy['revoked']) <= set(policy['keys']): raise PolicyError('policy_invalid')
        checkpoint = policy['checkpoint']
        if (type(checkpoint) is not dict or set(checkpoint) != {'sequence','statement_sha256'} or
                type(checkpoint['sequence']) is not int or not 0 <= checkpoint['sequence'] <= 2**63-1 or
                (checkpoint['sequence'] == 0 and checkpoint['statement_sha256'] is not None) or
                (checkpoint['sequence'] > 0 and not _hash(checkpoint['statement_sha256']))):
            raise PolicyError('policy_invalid')
    except PolicyError: raise
    except (TypeError,ValueError,KeyError) as error: raise PolicyError('policy_invalid') from error
    if doc['channel'] != policy['channel']: raise PolicyError('channel_mismatch')
    if doc['key_id'] not in policy['keys'] or doc['key_id'] in policy['revoked']: raise PolicyError('key_untrusted_or_revoked')
    if (doc['loader_sha256'] != policy['loader_sha256'] or doc['verifier_sha256'] != policy['verifier_sha256']):
        raise PolicyError('bootstrap_untrusted')
    if type(signature) is not bytes or len(signature) != 64 or not callable(verify_signature): raise PolicyError('signature_unchecked')
    try: verified = verify_signature(policy['keys'][doc['key_id']], DOMAIN + statement, signature)
    except Exception as error: raise PolicyError('signature_unchecked') from error
    if type(verified) is not bool: raise PolicyError('signature_unchecked')
    if not verified: raise PolicyError('signature_invalid')
    if doc['sequence'] < checkpoint['sequence']: raise PolicyError('rollback_refused')
    if doc['sequence'] == checkpoint['sequence'] and sha(statement) != checkpoint['statement_sha256']:
        raise PolicyError('sequence_conflict')
    try:
        parsed = _parse(manifest)
        if (type(parsed) is not dict or set(parsed) != {'format','product','version','status','scope','files'} or
                type(parsed['format']) is not int or parsed['format'] != 2 or parsed['product'] != doc['product'] or
                parsed['version'] != doc['version'] or parsed['status'] != 'candidate' or parsed['scope'] != 'source-l0-only' or
                type(parsed['files']) is not dict or
                not parsed['files'] or len(parsed['files']) > MAX_FILES or
                any(not _path(k) or not _hash(v) for k,v in parsed['files'].items()) or
                set(parsed['files']) != set(policy['required_paths']) or type(files) is not dict or
                set(files) != set(parsed['files']) or sha(manifest) != doc['manifest_sha256']):
            raise PolicyError('manifest_invalid')
        if any(type(v) is not bytes or len(v)>MAX_DOCUMENT for v in files.values()) or sum(map(len,files.values())) > MAX_TOTAL:
            raise PolicyError('files_invalid')
        if any(sha(files[path]) != digest for path,digest in parsed['files'].items()):
            raise PolicyError('files_mismatch')
        for path, field in (('kit/SYSTEM-L0.json','system_sha256'),('kit/snapshot_session.py','loader_sha256'),('kit/verify_candidate.py','verifier_sha256')):
            if path not in files or sha(files[path]) != doc[field]: raise PolicyError('binding_mismatch')
        system = _parse(files['kit/SYSTEM-L0.json'])
        if (type(system) is not dict or system.get('area') != 'L0' or system.get('roots') != ['kit'] or
                system.get('release_version') != doc['version']): raise PolicyError('system_invalid')
        try:
            schema.validate_json(files['kit/SYSTEM-L0.json'],expected_area='L0')
        except schema.SchemaError as error:
            raise PolicyError('system_schema_invalid') from error
    except PolicyError: raise
    except (TypeError,ValueError,UnicodeError,RecursionError,KeyError) as error: raise PolicyError('artifact_invalid') from error
    return {'outcome':'study_policy_consistent', 'statement_sha256':sha(statement), 'sequence':doc['sequence'],
            'key_origin':'assumed_not_verified', 'policy_origin':'assumed_not_verified',
            'checkpoint_integrity':'assumed_not_verified', 'freshness':'not_proved',
            'l0_schema':'checked_by_pretrusted_study_schema', 'l0_semantics':'not_checked',
            'installation':'not_performed', 'release':'not_authorized'}
