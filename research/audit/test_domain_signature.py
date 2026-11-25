#!/usr/bin/env python3
"""Новый подписной домен: синтетический открытый RFC-ключ и локальный OpenSSL."""
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from kit.base.bundle import bundle
from kit.base.bundle_trust import assess_bundle_trust
from kit.base.bundle_rollback import RolloutSession
from kit.base.registry_policy import StoreError

spec = importlib.util.spec_from_file_location('bundle_fixture_117', ROOT/'research/117/test_bundle.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
# Опубликованный тестовый вектор RFC 8032, не рабочий ключ.
SEED = bytes.fromhex('9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60')
PUBLIC = bytes.fromhex('d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a')
NEW_DOMAIN = b'DomainAgentKit:bundle-signature:v2\x00'
OLD_DOMAIN = b'AgentContractKit:bundle-signature:v1\x00'


class DomainSignatureTests(unittest.TestCase):
    def setUp(self):
        if not shutil.which('openssl'):
            self.skipTest('OpenSSL недоступен; криптографическая проба not run')
        self.temp = tempfile.TemporaryDirectory(prefix='domainagentkit-signature-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.private = self.root/'test-key.der'
        self.public = self.root/'test-public.der'
        self.private.write_bytes(bytes.fromhex('302e020100300506032b657004220420') + SEED)
        self.public.write_bytes(bytes.fromhex('302a300506032b6570032100') + PUBLIC)
        book = json.loads((ROOT/fixture.BOOK).read_bytes())
        ctx = fixture.context(book)
        self.archive = bundle(fixture.payload(book, ctx, 'populated'))['archive']
        self.key_id = hashlib.sha256(PUBLIC).hexdigest()
        self.policy = {'require_signature': True, 'public_keys': (PUBLIC,), 'exception_approvers': ()}
        self.now = '2026-01-01T00:00:00Z'

    def statement(self, domain):
        return domain + bytes.fromhex(self.key_id) + hashlib.sha256(self.archive).digest()

    def sign(self, message):
        inp, out = self.root/'message', self.root/'signature'
        inp.write_bytes(message)
        p = subprocess.run(['openssl', 'pkeyutl', '-sign', '-rawin', '-inkey', str(self.private),
                            '-keyform', 'DER', '-in', str(inp), '-out', str(out)], capture_output=True, timeout=20)
        self.assertEqual(p.returncode, 0, p.stderr.decode(errors='replace'))
        return out.read_bytes()

    def check(self, key, message, signature):
        self.assertEqual(key, PUBLIC)
        inp, sig = self.root/'verify-message', self.root/'verify-signature'
        inp.write_bytes(message); sig.write_bytes(signature)
        result = subprocess.run(['openssl', 'pkeyutl', '-verify', '-rawin', '-pubin', '-inkey', str(self.public),
                                 '-keyform', 'DER', '-in', str(inp), '-sigfile', str(sig)], capture_output=True, timeout=20)
        return result.returncode == 0

    def assess(self, signature, verifier=None):
        return assess_bundle_trust(self.archive, policy=self.policy, now=self.now, signature=signature,
                                   verify_signature=verifier or self.check)

    def envelope(self, signature, version=2):
        return {'format': version, 'algorithm': 'ed25519', 'key_id': self.key_id, 'signature': signature}

    def test_new_domain_exact_message_signed_and_verified(self):
        message = self.statement(NEW_DOMAIN)
        signature = self.sign(message)
        calls = []
        def verify(key, actual, sig):
            calls.append(actual)
            return self.check(key, actual, sig)
        result = self.assess(self.envelope(signature), verify)
        self.assertEqual(calls, [message])
        self.assertEqual((result['signature_status'], result['policy_decision']), ('trusted_signature', 'satisfied'))

    def test_old_domain_signature_cannot_pass_as_new_format(self):
        old = self.sign(self.statement(OLD_DOMAIN))
        result = self.assess(self.envelope(old))
        self.assertEqual((result['signature_status'], result['reason']), ('signature_invalid', 'mismatch'))

    def test_old_format_and_boolean_rejected_without_fallback(self):
        signature = self.sign(self.statement(NEW_DOMAIN))
        for old_version in (1, True, '2', 3):
            with self.subTest(version=old_version):
                calls = []
                def verifier(*args):
                    calls.append(args)
                    return True
                result = self.assess(self.envelope(signature, old_version), verifier)
                self.assertEqual((result['signature_status'], result['policy_decision']), ('signature_invalid', 'blocked'))
                self.assertEqual(calls, [])

    def test_signed_rollout_and_rollback_recheck_new_domain(self):
        book = json.loads((ROOT/fixture.BOOK).read_bytes())
        other = bundle(fixture.payload(book, fixture.context(book), 'changed_text'))['archive']
        def signature_for(raw, domain=NEW_DOMAIN, version=2):
            message = domain + bytes.fromhex(self.key_id) + hashlib.sha256(raw).digest()
            return self.envelope(self.sign(message), version)
        a, b = self.archive, other
        sig_a, sig_b = signature_for(a), signature_for(b)
        common = {'policy': self.policy, 'now': self.now, 'verify_signature': self.check}
        with RolloutSession() as session:
            initial = session.status()
            with self.assertRaises(StoreError) as exc:
                session.plan(a, action='rollout', signature=signature_for(a, OLD_DOMAIN, 1), **common)
            self.assertEqual(exc.exception.code, 'rollout_blocked')
            self.assertEqual(session.status(), initial)
            for raw, sig in ((a, sig_a), (b, sig_b)):
                plan = session.plan(raw, action='rollout', signature=sig, **common)
                self.assertEqual(session.apply(plan, confirmed_ticket=plan['ticket'], archive=raw,
                                               signature=sig, **common)['outcome'], 'applied')
            plan = session.plan(a, action='rollback', signature=sig_a, **common)
            result = session.apply(plan, confirmed_ticket=plan['ticket'], archive=a, signature=sig_a, **common)
            self.assertEqual(result['active_sha256'], hashlib.sha256(a).hexdigest())
            self.assertEqual([event['action'] for event in session.status()['journal']],
                             ['rollout', 'rollout', 'rollback'])

    def test_changed_signature_and_unapproved_key_blocked(self):
        signature = self.sign(self.statement(NEW_DOMAIN))
        tampered = bytes([signature[0] ^ 1]) + signature[1:]
        result = self.assess(self.envelope(tampered))
        self.assertEqual((result['signature_status'], result['policy_decision']), ('signature_invalid', 'blocked'))
        bad = self.envelope(signature); bad['key_id'] = '0'*64
        result = self.assess(bad)
        self.assertEqual((result['signature_status'], result['policy_decision']), ('untrusted_signer', 'blocked'))


if __name__ == '__main__':
    unittest.main()
