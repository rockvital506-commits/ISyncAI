#!/usr/bin/env python3
"""Подписи только временным синтетическим ключом; не доверенная доставка реального релиза."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'research/audit')]
import test_snapshot_session as snapshot_fixtures
from kit import openssl_ed25519 as provider, source_release_trust as trust

OPENSSL=Path(shutil.which('openssl') or '/not-available').resolve()
SUPPORTED=OPENSSL.is_file() and os.name=='posix' and hasattr(os,'O_NOFOLLOW') and os.open in os.supports_dir_fd

@unittest.skipUnless(SUPPORTED,'OpenSSL/POSIX unavailable; not_run')
class SourceTrustTests(unittest.TestCase):
    def setUp(self):
        self.ctx=snapshot_fixtures.SnapshotTests();self.ctx.setUp();self.addCleanup(self.ctx.doCleanups)
        self.binary_pin=hashlib.sha256(OPENSSL.read_bytes()).hexdigest()
        self.private=self.ctx.root/'synthetic-private.pem';self.pub_der=self.ctx.root/'synthetic-public.der'
        subprocess.run([str(OPENSSL),'genpkey','-algorithm','ED25519','-out',str(self.private)],check=True,capture_output=True,timeout=15)
        subprocess.run([str(OPENSSL),'pkey','-in',str(self.private),'-pubout','-outform','DER','-out',str(self.pub_der)],check=True,capture_output=True,timeout=15)
        der=self.pub_der.read_bytes();self.assertEqual(der[:12],bytes.fromhex('302a300506032b6570032100'));self.public=der[12:]
        self.key_id=hashlib.sha256(self.public).hexdigest();self.manifest=self.ctx.candidate/'kit/KIT-VERSION.json'
    def sign(self,raw=None,key=None):
        message=trust.message(self.public if key is None else key,self.manifest.read_bytes() if raw is None else raw)
        msg=self.ctx.root/'message';sig=self.ctx.root/'signature';msg.write_bytes(message)
        subprocess.run([str(OPENSSL),'pkeyutl','-sign','-rawin','-inkey',str(self.private),'-in',str(msg),'-out',str(sig)],check=True,capture_output=True,timeout=15)
        return sig.read_bytes()
    def verify(self,signature=None,**kw):
        opts={'public_key':self.public,'trusted_key_id':self.key_id,'signature':self.sign() if signature is None else signature,
              'openssl_executable':OPENSSL,'openssl_pin':self.binary_pin};opts.update(kw)
        return trust.verify_signed_source(self.ctx.candidate,**opts)
    def error(self,code,fn,*args,**kwargs):
        with self.assertRaises(trust.SourceTrustError) as err:fn(*args,**kwargs)
        self.assertEqual(str(err.exception),code)
    def test_rfc8032_known_answer_and_changed_message(self):
        key=bytes.fromhex('3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c')
        sig=bytes.fromhex('92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00')
        self.assertTrue(provider.verify(key,b'\x72',sig,executable=OPENSSL,executable_pin=self.binary_pin))
        self.assertFalse(provider.verify(key,b'\x73',sig,executable=OPENSSL,executable_pin=self.binary_pin))
    def test_signed_candidate_and_reuse_pin_in_snapshot_session(self):
        result=self.verify();self.assertEqual(result['outcome'],'signature_and_candidate_verified')
        self.assertEqual(result['manifest_sha256'],hashlib.sha256(self.manifest.read_bytes()).hexdigest())
        self.assertEqual(result['key_id'],self.key_id);self.assertEqual(result['owner_identity'],'not_checked')
        command=self.ctx.args(manifest_pin=result['manifest_sha256'])
        proc=subprocess.run(command,input='{"type":"bootstrap"}\n',capture_output=True,text=True,timeout=25)
        self.assertEqual(proc.returncode,0,proc.stderr);self.assertEqual(json.loads(proc.stdout)['outcome'],'bootstrap')
    def test_unsigned_bad_key_provider_and_tampering_fail_closed(self):
        sig=self.sign()
        with patch.object(trust.openssl_ed25519,'verify',side_effect=AssertionError('no provider for wrong key')):
            self.error('untrusted_key',self.verify,sig,trusted_key_id='0'*64)
        self.error('trusted_key_id_required',self.verify,sig,trusted_key_id='bad')
        self.error('provider_pin_mismatch',self.verify,sig,openssl_pin='0'*64)
        modified=bytearray(sig);modified[-1]^=1;self.error('signature_not_verified',self.verify,bytes(modified))
        raw=self.manifest.read_bytes();self.manifest.write_bytes(raw+b' ');self.error('signature_not_verified',self.verify,sig);self.manifest.write_bytes(raw)
        target=self.ctx.candidate/'kit/base/operation_plan.py';target.write_bytes(target.read_bytes()+b'\n# changed\n')
        self.error('candidate_unverified',self.verify,sig)
    def test_domain_is_distinct_from_other_signature_and_manifest_version_validated(self):
        raw=self.manifest.read_bytes();msg=trust.message(self.public,raw)
        self.assertEqual(msg,b'DomainAgentKit:source-manifest-signature:v1\x00'+bytes.fromhex(self.key_id)+hashlib.sha256(raw).digest())
        self.assertNotEqual(msg[:len(b'DomainAgentKit:bundle-signature:v2')],b'DomainAgentKit:bundle-signature:v2')
        doc=json.loads(raw);doc['version']='0.2.0-not-current';self.manifest.write_text(json.dumps(doc,sort_keys=True)+'\n')
        self.error('candidate_unverified',self.verify,self.sign())
    def test_untrusted_provider_path_or_unavailable_provider(self):
        sig=self.sign();link=self.ctx.root/'openssl-link';link.symlink_to(OPENSSL)
        self.error('provider_unavailable',self.verify,sig,openssl_executable=link)
        self.error('provider_path_invalid',self.verify,sig,openssl_executable='relative-openssl')
        with patch.object(provider.subprocess,'run',side_effect=subprocess.TimeoutExpired('openssl',10)):
            self.error('provider_unavailable',self.verify,sig)
    def test_manifest_symlink_hardlink_and_invalid_input_refuse(self):
        sig=self.sign();raw=self.manifest.read_bytes();self.manifest.unlink();self.manifest.symlink_to(self.ctx.root/'other')
        self.error('manifest_unavailable',self.verify,sig);self.manifest.unlink();self.manifest.write_bytes(raw)
        os.link(self.manifest,self.ctx.root/'manifest-hardlink');self.error('manifest_unavailable',self.verify,sig)
        self.error('input_invalid',self.verify,b'too-short');self.error('input_invalid',trust.message,b'x',raw)
    def test_cli_strict_fields_and_signature(self):
        sig=self.sign();command=[sys.executable,'-I','-S','-B',str(ROOT/'kit/source_release_trust.py'),
            '--candidate-root',str(self.ctx.candidate),'--public-key-hex',self.public.hex(),'--trusted-key-id',self.key_id,
            '--signature-hex',sig.hex(),'--openssl',str(OPENSSL),'--openssl-pin',self.binary_pin]
        result=subprocess.run(command,capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(json.loads(result.stdout)['outcome'],'signature_and_candidate_verified')
        command[command.index('--signature-hex')+1]=sig.hex().upper()
        invalid=subprocess.run(command,capture_output=True,text=True,timeout=20)
        self.assertEqual(invalid.returncode,1);self.assertEqual(json.loads(invalid.stdout)['reason'],'input_invalid')
    def test_provider_is_a_trust_anchor_not_proof_itself(self):
        fake=self.ctx.root/'fake-openssl';fake.write_text('#!/bin/sh\nexit 0\n');fake.chmod(0o700)
        # Этот ложный провайдер явно выбран и закреплён фикстурой: его успех не свидетельствует о криптографии.
        result=self.verify(bytes(64),openssl_executable=fake,openssl_pin=hashlib.sha256(fake.read_bytes()).hexdigest())
        self.assertEqual(result['outcome'],'signature_and_candidate_verified');self.assertEqual(result['source_authentication'],'under_explicit_key_and_provider')

if __name__=='__main__':unittest.main()
