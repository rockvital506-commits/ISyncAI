"""И-119: целостность, отделённая подпись и явная политика стенда."""
from datetime import datetime
from hashlib import sha256
import re

from .bundle_verify import bundle_verify
from .registry_policy import StoreError

_DOMAIN = b'AgentContractKit:bundle-signature:v1\x00'
_HASH = re.compile('[0-9a-f]{64}')
_ID = re.compile('[A-Za-z0-9][A-Za-z0-9._-]{0,63}')
_UTC = re.compile('[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z')
_POLICY = {'require_signature', 'public_keys', 'exception_approvers'}
_EXCEPTION = {'archive_sha256', 'expiry', 'approver'}
_SIGNATURE = {'format', 'algorithm', 'key_id', 'signature'}


def _bad(where, reason):
    raise StoreError('bundle_trust_invalid', where, details={'reason': reason}) from None


def _closed(obj, fields):
    return (type(obj) is dict and len(obj) == len(fields)
            and all(type(k) is str for k in obj) and obj.keys() == fields)


def _matches(expr, value):
    return type(value) is str and expr.fullmatch(value) is not None


def _time(value, where, reason):
    if not _matches(_UTC, value):
        _bad(where, reason)
    try:
        return datetime.fromisoformat(value[:-1] + '+00:00')
    except ValueError:
        _bad(where, reason)


def _policy(policy):
    if (not _closed(policy, _POLICY) or type(policy['require_signature']) is not bool
            or type(policy['public_keys']) is not tuple or type(policy['exception_approvers']) is not tuple):
        _bad('policy', 'shape')
    keys, approvers = policy['public_keys'], policy['exception_approvers']
    if len(keys) > 16 or len(approvers) > 32:
        _bad('policy', 'limit')
    if any(type(k) is not bytes or len(k) != 32 for k in keys) or any(not _matches(_ID, a) for a in approvers):
        _bad('policy', 'shape')
    public = {sha256(k).hexdigest(): k for k in keys}
    approved = frozenset(approvers)
    if len(public) != len(keys) or len(approved) != len(approvers):
        _bad('policy', 'duplicate')
    return policy['require_signature'], public, approved


def _exceptions(exceptions):
    if type(exceptions) is not tuple:
        _bad('exceptions', 'shape')
    if len(exceptions) > 32:
        _bad('exceptions', 'limit')
    by_zip = {}
    for row in exceptions:
        if not _closed(row, _EXCEPTION) or not _matches(_HASH, row['archive_sha256']) or not _matches(_ID, row['approver']):
            _bad('exceptions', 'shape')
        key = row['archive_sha256']
        if key in by_zip:
            _bad('exceptions', 'duplicate')
        by_zip[key] = (_time(row['expiry'], 'exceptions', 'expiry'), row['approver'])
    return by_zip


def _assessment(integrity, status, decision, reason):
    return {'trust_format': 1, 'outcome': 'assessed', 'integrity': integrity, 'signature_status': status,
            'policy_decision': decision, 'reason': reason}


def _unsigned(integrity, required, exception, approved, now):
    if not required:
        decision, reason = 'optional', 'signature_optional'
    elif exception is None:
        decision, reason = 'blocked', 'signature_required'
    elif exception[1] not in approved:
        decision, reason = 'blocked', 'exception_approver'
    elif now >= exception[0]:
        decision, reason = 'blocked', 'exception_expired'
    else:
        decision, reason = 'exception', 'exception_active'
    return _assessment(integrity, 'unsigned', decision, reason)


def _signed(integrity, signature, public, verifier):
    if (not _closed(signature, _SIGNATURE) or type(signature['format']) is not int or signature['format'] != 1
            or type(signature['algorithm']) is not str or not _matches(_HASH, signature['key_id'])
            or type(signature['signature']) is not bytes or len(signature['signature']) != 64):
        return _assessment(integrity, 'signature_invalid', 'blocked', 'shape')
    if signature['algorithm'] != 'ed25519':
        return _assessment(integrity, 'signature_invalid', 'blocked', 'algorithm')
    key_id = signature['key_id']
    if key_id not in public:
        return _assessment(integrity, 'untrusted_signer', 'blocked', 'key_not_approved')
    if not callable(verifier):
        return _assessment(integrity, 'signature_unchecked', 'blocked', 'verifier_unavailable')
    message = _DOMAIN + bytes.fromhex(key_id) + bytes.fromhex(integrity['archive_sha256'])
    try:
        ok = verifier(public[key_id], message, signature['signature'])
    except Exception:
        # Проверяющий передан доверенным вызывающим; его сбой не равен чужой подписи.
        return _assessment(integrity, 'signature_unchecked', 'blocked', 'verifier_error')
    if type(ok) is not bool:
        return _assessment(integrity, 'signature_unchecked', 'blocked', 'verifier_result')
    if not ok:
        return _assessment(integrity, 'signature_invalid', 'blocked', 'mismatch')
    return _assessment(integrity, 'trusted_signature', 'satisfied', 'signature_verified')


def assess_bundle_trust(archive, *, policy, now, signature=None, exceptions=(), verify_signature=None, target='stand'):
    """На стенде оценить явную политику, не выдавая права на установку или запись."""
    integrity = bundle_verify(archive, target=target)
    required, public, approved = _policy(policy)
    observed_at = _time(now, 'clock', 'utc')
    by_zip = _exceptions(exceptions)
    if signature is None:
        return _unsigned(integrity, required, by_zip.get(integrity['archive_sha256']), approved, observed_at)
    return _signed(integrity, signature, public, verify_signature)
