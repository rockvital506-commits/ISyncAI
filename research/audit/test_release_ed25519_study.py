#!/usr/bin/env python3
"""Независимость импортов и известный вектор Ed25519 — синтетический стенд."""
import ast
import hashlib
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'research/audit')]
import release_ed25519_study as provider
import test_source_release_trust as fixture


@unittest.skipUnless(fixture.SUPPORTED,'OpenSSL/POSIX unavailable; not_run')
class ReleaseEd25519StudyTests(unittest.TestCase):
    def test_rfc8032_known_answer_and_wrong_message(self):
        key=bytes.fromhex('3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c')
        sig=bytes.fromhex('92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00')
        pin=hashlib.sha256(fixture.OPENSSL.read_bytes()).hexdigest()
        self.assertTrue(provider.verify(key,b'\x72',sig,executable=fixture.OPENSSL,executable_pin=pin))
        self.assertFalse(provider.verify(key,b'\x73',sig,executable=fixture.OPENSSL,executable_pin=pin))
        with self.assertRaisesRegex(provider.ProviderError,'provider_pin_mismatch'):
            provider.verify(key,b'\x72',sig,executable=fixture.OPENSSL,executable_pin='0'*64)
    def test_fixed_tool_modules_do_not_import_kit(self):
        names=('release_archive_cli_study.py','release_archive_study.py','release_policy_study.py','release_ed25519_study.py')
        for name in names:
            with self.subTest(name=name):
                tree=ast.parse((ROOT/'research/audit'/name).read_bytes())
                for node in ast.walk(tree):
                    if isinstance(node,ast.Import):
                        self.assertFalse(any(x.name=='kit' or x.name.startswith('kit.') for x in node.names))
                    if isinstance(node,ast.ImportFrom):
                        self.assertFalse(node.module=='kit' or (node.module or '').startswith('kit.'))

if __name__=='__main__':unittest.main()
