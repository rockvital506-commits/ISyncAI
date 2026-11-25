#!/usr/bin/env python3
"""Стендовая привязка манифеста, L0 и пары: публичный тестовый ключ, не выпуск."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'research/audit')]
import bootstrap_binding_study as study
import core_audit as audit

# Опубликованный тестовый вектор RFC 8032; этот ключ нельзя использовать для реальной поставки.
SEED = bytes.fromhex('9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60')
PUBLIC = bytes.fromhex('d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a')
OTHER_SEED = bytes.fromhex('4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb')
OLD_DOMAIN = b'DomainAgentKit:bundle-signature:v2\x00'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':')).encode('ascii')


class BindingStudyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='domain-binding-study-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.private = self.root/'test-private.der'
        self.private.write_bytes(bytes.fromhex('302e020100300506032b657004220420') + SEED)
        self.other_private = self.root/'other-test-private.der'
        self.other_private.write_bytes(bytes.fromhex('302e020100300506032b657004220420') + OTHER_SEED)
        self.manifest = (ROOT/'kit/KIT-VERSION.json').read_bytes()
        self.version = json.loads(self.manifest)['version']
        self.loader = (ROOT/'kit/snapshot_session.py').read_bytes()
        self.verifier = (ROOT/'kit/verify_candidate.py').read_bytes()
        self.system = self.l0(self.version)
        self.statement = self.make_statement()

    def l0(self, version, entries=None):
        doc = {'schema_version':2, 'area':'L0', 'roots':['kit'], 'release_version':version,
               'entries': [] if entries is None else entries}
        return (json.dumps(doc, sort_keys=True)+'\n').encode()

    def make_statement(self, **changes):
        doc = {'format':1, 'product':'DomainAgentKit', 'candidate_version':self.version,
               'key_id':sha(PUBLIC), 'manifest_sha256':sha(self.manifest), 'system_sha256':sha(self.system),
               'loader_sha256':sha(self.loader), 'verifier_sha256':sha(self.verifier)}
        doc.update(changes)
        return canonical(doc)

    def sign(self, statement, *, domain=study.DOMAIN, private=None):
        if not shutil.which('openssl'): self.skipTest('OpenSSL недоступен; криптография not run')
        inp, out = self.root/'sign-input', self.root/'sign-output'
        inp.write_bytes(domain + statement)
        result = subprocess.run(['openssl','pkeyutl','-sign','-rawin','-inkey',str(private or self.private),
                                 '-keyform','DER','-in',str(inp),'-out',str(out)], capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
        return out.read_bytes()

    def verify(self, public, message, signature):
        key, inp, sig = self.root/'verify-key.der', self.root/'verify-input', self.root/'verify-signature'
        key.write_bytes(bytes.fromhex('302a300506032b6570032100') + public)
        inp.write_bytes(message); sig.write_bytes(signature)
        result = subprocess.run(['openssl','pkeyutl','-verify','-rawin','-pubin','-inkey',str(key),
                                 '-keyform','DER','-in',str(inp),'-sigfile',str(sig)],
                                capture_output=True, timeout=20)
        return result.returncode == 0

    def assess(self, statement=None, signature=None, **changes):
        if statement is None: statement = self.statement
        if signature is None: signature = self.sign(statement)
        kwargs = {'public_key':PUBLIC, 'verify_signature':self.verify, 'manifest':self.manifest,
                  'system':self.system, 'loader':self.loader, 'verifier':self.verifier}
        kwargs.update(changes)
        return study.assess(statement, signature, **kwargs)

    def refusal(self, code, statement=None, signature=None, **changes):
        with self.assertRaises(study.BindingError) as raised:
            self.assess(statement, signature, **changes)
        self.assertEqual(str(raised.exception), code)

    def test_real_ed25519_binding_and_no_candidate_execution(self):
        signature = self.sign(self.statement)
        calls = []
        def verify(public, message, sig):
            calls.append((public, message, sig))
            return self.verify(public, message, sig)
        result = self.assess(signature=signature, verify_signature=verify)
        self.assertEqual(calls, [(PUBLIC, study.DOMAIN+self.statement, signature)])
        self.assertEqual(result['outcome'], 'study_binding_checked')
        self.assertEqual(result['manifest_sha256'], sha(self.manifest))
        self.assertEqual(result['system_sha256'], sha(self.system))
        self.assertEqual((result['key_origin'], result['semantic_review'], result['freshness'], result['installation']),
                         ('not_verified', 'not_run', 'not_checked', 'not_implemented'))

    def test_individual_artifact_and_role_swaps_are_rejected(self):
        signature = self.sign(self.statement)
        for name in ('manifest','system','loader','verifier'):
            with self.subTest(role=name):
                self.refusal('artifact_mismatch', signature=signature, **{name:getattr(self, name)+b'x'})
        self.refusal('artifact_mismatch', signature=signature, loader=self.verifier, verifier=self.loader)
        self.refusal('artifact_invalid', signature=signature, loader=b'')
        self.refusal('artifact_invalid', signature=signature, system=b'x'*(study.MAX_ARTIFACT+1))

    def test_wrong_domain_wrong_key_and_statement_tamper(self):
        self.refusal('signature_invalid', signature=self.sign(self.statement, domain=OLD_DOMAIN))
        self.refusal('signature_invalid', signature=self.sign(self.statement, private=self.other_private))
        self.refusal('key_mismatch', signature=self.sign(self.statement), public_key=b'\x01'*32)
        changed = self.make_statement(system_sha256='0'*64)
        self.refusal('signature_invalid', statement=changed, signature=self.sign(self.statement))
        invalid = bytearray(self.sign(self.statement)); invalid[0] ^= 1
        self.refusal('signature_invalid', signature=bytes(invalid))

    def test_signed_mismatch_between_manifest_l0_and_pair(self):
        l0 = self.l0('9.9.9')
        statement = self.make_statement(system_sha256=sha(l0))
        self.refusal('identity_mismatch', statement=statement, system=l0)
        for name in ('kit/snapshot_session.py', 'kit/verify_candidate.py'):
            altered = json.loads(self.manifest)
            altered['files'][name] = '0'*64
            manifest_bytes = canonical(altered)
            statement = self.make_statement(manifest_sha256=sha(manifest_bytes))
            self.refusal('identity_mismatch', statement=statement, manifest=manifest_bytes)
        for key, value in (('product', 'OtherProduct'), ('version', '9.9.9')):
            altered = json.loads(self.manifest); altered[key] = value
            manifest_bytes = canonical(altered)
            statement = self.make_statement(manifest_sha256=sha(manifest_bytes))
            self.refusal('identity_mismatch', statement=statement, manifest=manifest_bytes)
        for key, value in (('area', 'L1'), ('roots', ['other'])):
            altered = json.loads(self.system); altered[key] = value
            l0 = canonical(altered)
            statement = self.make_statement(system_sha256=sha(l0))
            self.refusal('identity_mismatch', statement=statement, system=l0)
        bad_json = b'{"product":"DomainAgentKit","product":"DomainAgentKit"}'
        statement = self.make_statement(manifest_sha256=sha(bad_json))
        self.refusal('identity_mismatch', statement=statement, manifest=bad_json)

    def test_statement_shape_canonical_and_strict_json(self):
        doc = json.loads(self.statement)
        malformed = [b'{"format":1,"format":1}', b'{"format":NaN}', b'\xff',
                     json.dumps(doc, indent=2).encode(), b'x'*(study.MAX_STATEMENT+1)]
        for raw in malformed:
            with self.subTest(size=len(raw)):
                code = 'input_invalid' if len(raw)>study.MAX_STATEMENT else 'statement_invalid'
                self.refusal(code, statement=raw, signature=b'0'*64, verify_signature=lambda *_: True)
        for mutation in ({'format':True}, {'format':2}, {'extra':True}, {'candidate_version':'bad version'},
                         {'key_id':'A'*64}, {'product':'AgentContractKit'}):
            altered = dict(doc); altered.update(mutation)
            self.refusal('statement_invalid', statement=canonical(altered), signature=b'0'*64,
                         verify_signature=lambda *_: True)

    def test_verifier_failure_is_not_signature_acceptance(self):
        def raises(*_): raise RuntimeError('synthetic')
        for callback in (None, lambda *_: 1, raises):
            with self.subTest(callback=repr(callback)):
                self.refusal('signature_unchecked', signature=b'0'*64, verify_signature=callback)
        self.refusal('signature_invalid', signature=b'0'*64, verify_signature=lambda *_: False)
        self.refusal('input_invalid', signature=b'bad', verify_signature=lambda *_: True)

    def test_fake_verifier_and_underspecified_l0_show_limits(self):
        # Поддельный проверяющий принимает произвольную подпись — источник доверия к нему вне модели.
        result = self.assess(signature=b'0'*64, verify_signature=lambda *_: True)
        self.assertEqual(result['key_origin'], 'not_verified')
        self.assertEqual(result['freshness'], 'not_checked')
        # Даже подписанная конструкция не доказывает валидность всей схемы или смысл L0.
        malformed_l0 = self.l0(self.version, entries='not a valid entries list')
        statement = self.make_statement(system_sha256=sha(malformed_l0))
        result = self.assess(statement=statement, system=malformed_l0)
        self.assertEqual(result['outcome'], 'study_binding_checked')
        self.assertEqual(result['semantic_review'], 'not_run')

    def test_signed_replay_not_detected(self):
        signature = self.sign(self.statement)
        first = self.assess(signature=signature)
        second = self.assess(signature=signature)
        self.assertEqual(first, second)
        self.assertEqual(second['freshness'], 'not_checked')

    def test_minimal_manifest_does_not_prove_full_candidate_composition(self):
        minimal = canonical({'product':'DomainAgentKit', 'version':self.version,
                             'files':{'kit/snapshot_session.py':sha(self.loader),
                                      'kit/verify_candidate.py':sha(self.verifier)}})
        statement = self.make_statement(manifest_sha256=sha(minimal))
        result = self.assess(statement=statement, manifest=minimal)
        self.assertEqual(result['outcome'], 'study_binding_checked')
        # Отсутствуют остальные манифестные члены; отдельная проверка кандидата обязательна.
        self.assertEqual(len(json.loads(minimal)['files']), 2)

    def test_function_never_opens_or_executes_inputs(self):
        kwargs = {'public_key':PUBLIC, 'verify_signature':lambda *_: True, 'manifest':self.manifest,
                  'system':self.system, 'loader':self.loader, 'verifier':self.verifier}
        with patch('builtins.open', side_effect=AssertionError('filesystem access')), \
             patch.object(Path, 'open', side_effect=AssertionError('filesystem access')), \
             patch('os.open', side_effect=AssertionError('filesystem access')), \
             patch('os.stat', side_effect=AssertionError('filesystem access')), \
             patch('subprocess.run', side_effect=AssertionError('execution')):
            result = study.assess(self.statement, b'0'*64, **kwargs)
        self.assertEqual(result['outcome'], 'study_binding_checked')

    def test_verified_study_then_synthetic_snapshot_session(self):
        result = self.assess()  # Ключ и OpenSSL доверяются только в этом синтетическом стенде.
        source = self.root/'source'; source.mkdir()
        trusted = self.root/'trusted'; trusted.mkdir()
        workspace = self.root/'workspace'; workspace.mkdir()
        manifest = json.loads(self.manifest)
        for rel in ('kit/KIT-VERSION.json', *manifest['files']):
            target = source/rel; target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT/rel, target)
        (trusted/'snapshot_session.py').write_bytes(self.loader)
        (trusted/'verify_candidate.py').write_bytes(self.verifier)
        audit.make_workspace(workspace, parent_scope='.')
        (workspace/'kit/base/registry.json').write_bytes(self.system)
        before = audit.tree_digest(workspace)
        run = subprocess.run([sys.executable,'-I','-S','-B',str(trusted/'snapshot_session.py'),
              '--candidate-root',str(source),'--workspace',str(workspace),'--profile-root','profiles/pilot',
              '--profile-id','Pilot','--manifest-pin',result['manifest_sha256'],'--system-pin',result['system_sha256']],
              input='{"type":"bootstrap"}\n', capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)['outcome'], 'bootstrap')
        self.assertEqual(audit.tree_digest(workspace), before)
        # Связывание байтов и их использование не атомарны с конкурентной заменой.


if __name__ == '__main__':
    unittest.main()
