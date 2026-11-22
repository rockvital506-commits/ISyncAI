#!/usr/bin/env python3
"""И-119: независимые векторы, настоящий Ed25519 на стенде, аудит границы доверия."""
from collections import Counter
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from hashlib import sha256
from io import BytesIO, StringIO
import json
from pathlib import Path
import platform
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zipfile import ZipFile, ZipInfo

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BOOK = 'research/119/CASES.json'
TEST = 'research/119/test_bundle_trust.py'
MODULE = 'kit/base/bundle_trust.py'
SOURCE = 'research/117/Synthetic-Bundle-117.zip'
START, META = 'kit/base/START.md', 'manifest.json'
OPENSSL = '/usr/bin/openssl'
SPKI = bytes.fromhex('302a300506032b6570032100')
DOMAIN = b'AgentContractKit:bundle-signature:v1\x00'
# RFC 8032, §7.1, TEST 2: только опубликованные открытые значения.
RFC_KEY = bytes.fromhex('3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c')
RFC_SIG = bytes.fromhex('92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da08'
                        '5ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00')
NOW, LATER, EARLIER = '2026-11-18T12:00:00Z', '2026-11-18T12:00:01Z', '2026-11-18T11:59:59Z'
APPROVER = 'stand-approver-119'
MARK = 'SYNTHETIC_DO_NOT_ECHO_119'
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
from kit.base.bundle_verify import bundle_verify
from kit.base.registry_policy import StoreError, check_operation


def canonical(d):
    return json.dumps(d, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def digest(raw):
    return sha256(raw).hexdigest()


def flip(sig):
    return sig[:-1] + bytes((sig[-1] ^ 1,))


def openssl(root, *args):
    env = {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'HOME': str(root), 'OPENSSL_CONF': '/dev/null'}
    return subprocess.run([OPENSSL, *args], cwd=root, env=env, stdin=subprocess.DEVNULL, capture_output=True, timeout=8)


def ed25519_check(key, message, signature):
    assert type(key) is type(message) is type(signature) is bytes and len(key) == 32 and len(signature) == 64
    with TemporaryDirectory(prefix='ack-i119-verify-') as d:
        root = Path(d)
        for n, data in (('public.der', SPKI + key), ('message.bin', message), ('signature.bin', signature)):
            (root/n).write_bytes(data)
        p = openssl(root, 'pkeyutl', '-verify', '-pubin', '-keyform', 'DER', '-inkey', 'public.der',
                    '-rawin', '-in', 'message.bin', '-sigfile', 'signature.bin')
        if p.returncode == 0 and p.stdout.strip() == b'Signature Verified Successfully' and not p.stderr:
            return True
        if p.returncode == 1 and p.stdout.strip() == b'Signature Verification Failure' and not p.stderr:
            return False
        raise ValueError('openssl_verifier_unavailable')


def compose(files):
    with BytesIO() as out:
        with ZipFile(out, 'w', allowZip64=False) as z:
            for name, raw in sorted(files.items()):
                i = ZipInfo(name)
                i.create_system, i.external_attr = 3, 0o100644 << 16
                z.writestr(i, raw)
        return out.getvalue()


def fixtures():
    """Контрольные байты строятся независимо от сборщика и оценщика доверия."""
    raw = (ROOT/SOURCE).read_bytes()
    with ZipFile(BytesIO(raw)) as z:
        assert len(z.namelist()) == 17 and z.testzip() is None
        files = {n: z.read(n) for n in z.namelist() if n != META}
        mf = json.loads(z.read(META)); assert z.read(META) == canonical(mf) + b'\n'
    revision = json.loads(files['profiles/staged/registry.json'])['revision']; assert revision == mf['revision'] == 7

    def manifest(payload):
        body = {'revision': revision, 'roots': ['kit', 'profiles/staged'],
                'files': [{'path': n, 'size': len(b), 'sha256': digest(b)} for n, b in sorted(payload.items())]}
        return {**body, 'digest': digest(canonical(body))}

    assert manifest(files) == mf and compose({**files, META: canonical(mf) + b'\n'}) == raw
    altered = dict(files); assert altered[START].endswith(b'\n'); altered[START] = flip(altered[START])
    alt = manifest(altered); assert alt['digest'] != mf['digest']
    archives = {'source': raw, 'alternate': compose({**altered, META: canonical(alt) + b'\n'}),
                'tampered': compose({**altered, META: canonical(mf) + b'\n'}), 'incomplete': compose(files)}
    integrity = {k: {'bundle_format': 1, 'outcome': 'verified', 'revision': revision, 'archive_sha256': digest(archives[k]),
                     'manifest_digest': m['digest']} for k, m in (('source', mf), ('alternate', alt))}
    return archives, integrity


def statement(key_id, archive_sha256):
    return DOMAIN + bytes.fromhex(key_id) + bytes.fromhex(archive_sha256)


def setup(book):
    archives, integrity = fixtures()
    assert canonical(integrity) == canonical(book['integrity']) and {k: digest(v) for k, v in archives.items()} == book['archive_sha256']
    public = bytes.fromhex(book['public']['key']); key_id = digest(public)
    assert len(public) == 32 and key_id == book['public']['key_id'] and public != RFC_KEY
    sig = {k: bytes.fromhex(v) for k, v in book['public']['signatures'].items()}
    assert sig.keys() == integrity.keys() and all(len(v) == 64 for v in sig.values())
    return archives, integrity, public, key_id, sig


def control(book, ctx):
    archives, integrity, public, key_id, sig = ctx
    with TemporaryDirectory(prefix='ack-i119-version-') as d:
        version = openssl(d, 'version'); assert version.returncode == 0 and not version.stderr
    assert ed25519_check(RFC_KEY, b'\x72', RFC_SIG) is True
    assert ed25519_check(RFC_KEY, b'\x73', RFC_SIG) is False
    for n in ('source', 'alternate'):
        message = statement(key_id, integrity[n]['archive_sha256'])
        assert ed25519_check(public, message, sig[n]) is True and ed25519_check(public, message, flip(sig[n])) is False
        assert canonical(bundle_verify(archives[n])) == canonical(integrity[n])
    assert ed25519_check(public, statement(key_id, integrity['alternate']['archive_sha256']), sig['source']) is False
    working = {}
    for name in ('bundle', 'bundle_verify', 'assess_bundle_trust'):
        try:
            check_operation(name, target='L1')
        except StoreError as e:
            assert e.code == 'unknown_operation'; working[name] = e.code
        else:
            raise AssertionError('working_port_changed')
    return {'openssl': version.stdout.decode('ascii').strip(), 'rfc_public_vector': True, 'reference_signatures_valid': 2,
            'mismatches_rejected': 4, 'source_sha256': integrity['source']['archive_sha256'], 'working_port': working}


def args_for(ctx, case):
    archives, integrity, key, key_id, signatures = ctx
    label = case['id'][0]; variant = case['variant']; name = case['archive']
    raw = archives[name]
    explicit = label == 'S' or variant == 'tampered_signed'
    sig = ({'format': 1, 'algorithm': 'ed25519', 'key_id': key_id,
            'signature': signatures[case.get('signed_for', name if name in signatures else 'source')]}
           if explicit else None)
    policy = {'require_signature': variant not in ('optional', 'optional_with_exception', 'unknown_optional'),
              'public_keys': (key,), 'exception_approvers': (APPROVER,)}
    now, target = NOW, 'stand'
    exception = {'archive_sha256': digest(raw), 'expiry': LATER, 'approver': APPROVER}
    exceptions = ()
    use_exception = {'active', 'equal_expiry', 'past_expiry', 'foreign_approver', 'wrong_zip', 'manifest_is_not_zip',
                     'optional_with_exception', 'revoked_approver', 'active_alternate', 'unknown_optional', 'bad_bits',
                     'signed_reused', 'empty_signature', 'tampered_unsigned', 'no_manifest', 'bad_envelope', 'unavailable'}
    if variant in use_exception or label == 'N':
        exceptions = (exception,)
    if variant == 'equal_expiry': exception['expiry'] = NOW
    if variant == 'past_expiry': exception['expiry'] = EARLIER
    if variant == 'foreign_approver': exception['approver'] = 'not-approved-119'
    if variant == 'wrong_zip': exception['archive_sha256'] = integrity['source']['archive_sha256']
    if variant == 'manifest_is_not_zip': exception['archive_sha256'] = integrity['source']['manifest_digest']
    if variant in ('revoked_approver',): policy['exception_approvers'] = ()
    if variant == 'unknown_optional': policy['public_keys'] = ()
    if variant == 'bad_bits': sig['signature'] = flip(sig['signature'])
    if variant == 'algorithm': sig['algorithm'] = 'unknown-synthetic'
    if variant == 'empty_signature': sig['signature'] = b''
    if variant == 'bool_format': sig['format'] = True
    if variant == 'bad_envelope': sig = {}
    if variant == 'embedded_key': sig['public_key'] = key
    if variant == 'unknown_id': sig['key_id'] = '0'*64
    if variant == 'bad_key_id': sig['key_id'] = 'A'*64
    if variant == 'substituted_approved_key':
        policy['public_keys'] = (key, RFC_KEY); sig['key_id'] = digest(RFC_KEY)
    if variant == 'tampered_signed': policy = {}  # недопустимая политика не должна заслонить ошибку байтов
    if variant == 'path_input': raw = Path(MARK + '.zip')
    if variant == 'live': target = 'live'
    if variant == 'require_type': policy['require_signature'] = 1
    if variant == 'policy_extra': policy['extra'] = MARK
    if variant == 'keys_duplicate': policy['public_keys'] = (key, key)
    if variant == 'public_length': policy['public_keys'] = (b'0'*31,)
    if variant == 'approver_id': policy['exception_approvers'] = ('not an id',)
    if variant == 'approver_duplicate': policy['exception_approvers'] = (APPROVER, APPROVER)
    if variant == 'too_many_keys': policy['public_keys'] = tuple(bytes([n])*32 for n in range(17))
    if variant == 'now_offset': now = '2026-11-18T13:00:00+01:00'
    if variant == 'invalid_now': now = '2026-02-29T12:00:00Z'
    if variant == 'missing_expiry': del exception['expiry']
    if variant == 'missing_approver': del exception['approver']
    if variant == 'duplicate_exception': exceptions = (exception, deepcopy(exception))
    if variant == 'upper_hash': exception['archive_sha256'] = 'A'*64
    if variant == 'expiry_offset': exception['expiry'] = '2026-11-18T13:00:01+01:00'
    if variant == 'invalid_expiry': exception['expiry'] = '2026-11-31T12:00:01Z'
    if variant == 'exception_extra': exception['extra'] = MARK
    if variant == 'too_many_exceptions': exceptions = tuple(dict(exception, archive_sha256=f'{n:064x}') for n in range(33))
    if variant == 'exceptions_list': exceptions = list(exceptions)
    return raw, {'policy': policy, 'now': now, 'signature': sig, 'exceptions': exceptions, 'target': target}


def expected_call(ctx, case):
    if not case.get('check'):
        return None
    _, integrity, key, key_id, _ = ctx
    sig = args_for(ctx, case)[1]['signature']
    if case['variant'] == 'substituted_approved_key': key = RFC_KEY; key_id = digest(key)
    expected = statement(key_id, integrity[case['archive']]['archive_sha256'])
    return key, expected, sig['signature']


def call_digest(triple):
    key, message, sig = triple
    return {'key_id': digest(key), 'message_sha256': digest(message), 'signature_sha256': digest(sig)}


def expected_observation(book, case):
    result = error = None
    if 'error' in case:
        code, where, reason = case['error']; error = {'code': code, 'where': where, 'details': {'reason': reason}}
    else:
        status, decision, reason = case['result']
        result = {'trust_format': 1, 'outcome': 'assessed', 'integrity': book['integrity'][case['archive']],
                  'signature_status': status, 'policy_decision': decision, 'reason': reason}
    return {'result': result, 'error': error, 'order': ['integrity'] + (['verifier'] if case.get('check') else []),
            'verifier_input': case.get('verifier_input'), 'effects': [], 'quiet': True, 'unchanged': True}


class NoEffects(RuntimeError):
    pass


class Monitor:
    def __init__(self):
        self.active = False
        self.effects = []
        sys.addaudithook(self.audit)

    def audit(self, event, _args):
        if self.active and (event == 'open' or event.startswith(('os.', 'socket.', 'subprocess.', 'ctypes.', 'shutil.', 'import'))):
            self.effects.append(event); raise NoEffects('effect')

    def observe(self, module, ctx, case):
        raw, params = args_for(ctx, case); before = deepcopy((raw, params)); wanted = expected_call(ctx, case)
        self.effects = []; order = []; presented = None
        out, err = StringIO(), StringIO(); result = error = None

        def integrity(archive, *, target):
            order.append('integrity')
            assert archive == raw and target == params['target']
            return bundle_verify(archive, target=target)

        def checker(key, message, sig):
            nonlocal presented
            order.append('verifier')
            if (key, message, sig) != wanted:
                raise NoEffects('unexpected_verifier_arguments')
            presented = call_digest(wanted)
            mode = case['check']
            if mode == 'error': raise ValueError(MARK)
            if mode == 'truthy': return 1
            assert mode == 'openssl'
            self.active = False  # только явно переданный синтетический проверяющий, не модуль
            try:
                return ed25519_check(key, message, sig)
            finally:
                self.active = True

        with patch.object(module, 'bundle_verify', integrity), redirect_stdout(out), redirect_stderr(err):
            self.active = True
            try:
                result = module.assess_bundle_trust(raw, verify_signature=None if case['variant'] == 'unavailable' else checker, **params)
            except StoreError as e:
                error = e.diagnostic()
            finally:
                self.active = False
        return {'result': result, 'error': error, 'order': order, 'verifier_input': presented, 'effects': list(self.effects),
                'quiet': not (out.getvalue() or err.getvalue()), 'unchanged': (raw, params) == before}


def main():
    book = json.loads((ROOT/BOOK).read_bytes()); assert canonical(book['format']) == b'1'
    ctx = setup(book); controls = control(book, ctx)
    ready = (ROOT/MODULE).is_file()
    if ready:
        from kit.base import bundle_trust
        monitor = Monitor()
    rows = []
    for c in book['cases']:
        row = {'id': c['id']}
        try:
            args_for(ctx, c)
            fixture = expected_call(ctx, c)
            assert (call_digest(fixture) if fixture else None) == c.get('verifier_input')
            if not ready:
                rows.append(dict(row, status='fail', reason='bundle_trust_missing')); continue
            got = monitor.observe(bundle_trust, ctx, c)
            match = canonical(got) == canonical(expected_observation(book, c))
        except Exception as e:
            rows.append(dict(row, status='fail', reason=type(e).__name__))
        else:
            rows.append(dict(row, status='pass', observation=got) if match else dict(row, status='fail', reason='oracle_mismatch'))
    count = Counter(r['status'] for r in rows)
    data = {'format': 1, 'control': controls, 'os': platform.system(), 'python': platform.python_version(), 'rows': rows,
            'counts': {k: count[k] for k in ('pass', 'fail', 'not run')}}
    print(json.dumps(data, ensure_ascii=False, sort_keys=True))
    return int(bool(count['fail'] or count['not run']))


if __name__ == '__main__':
    raise SystemExit(main())
