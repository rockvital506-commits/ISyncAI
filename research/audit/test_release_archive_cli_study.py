#!/usr/bin/env python3
"""Исследовательская файловая оболочка: синтетические байты и публичный тестовый ключ."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'research/audit')]
import release_archive_cli_study as cli
import release_archive_study as archive
import release_policy_study as policy
import test_release_policy_study as fixtures
import test_source_release_trust as signing


@unittest.skipUnless(signing.SUPPORTED,'OpenSSL/POSIX unavailable; not_run')
class ReleaseArchiveCliTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.ReleasePolicyStudyTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.tmp=tempfile.TemporaryDirectory(prefix='release-cli-test-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        self.archive=self.root/'candidate.zip';self.archive.write_bytes(archive.build(self.f.manifest,self.f.files))
        self.statement=self.root/'statement.json';self.statement.write_bytes(policy.canonical(self.f.doc))
        wire=copy.deepcopy(self.f.policy);wire['keys']={k:v.hex() for k,v in wire['keys'].items()}
        self.policy=self.root/'policy.json';self.policy.write_bytes(policy.canonical(wire))
        self.pin=hashlib.sha256(self.policy.read_bytes()).hexdigest();self.sig=self.f.sign().hex()
        self.provider_pin=hashlib.sha256(signing.OPENSSL.read_bytes()).hexdigest()
    def options(self):
        return dict(policy_pin=self.pin,signature=self.sig,openssl_path=signing.OPENSSL,openssl_pin=self.provider_pin)
    def inspect(self,**opts):
        kw=self.options();kw.update(opts)
        return cli.inspect(self.archive,self.statement,self.policy,**kw)
    def error(self,code,fn,*args,**kw):
        with self.assertRaises(cli.InputError) as exc:fn(*args,**kw)
        self.assertEqual(str(exc.exception),code)
    def test_success_and_read_only(self):
        before={p.name:p.read_bytes() for p in (self.archive,self.statement,self.policy)}
        result=self.inspect();self.assertEqual(result['outcome'],'study_policy_consistent')
        self.assertEqual(result['policy_pin_origin'],'assumed_not_verified')
        self.assertEqual(result['continuous_integrity'],'not_provided')
        self.assertEqual(before,{p.name:p.read_bytes() for p in (self.archive,self.statement,self.policy)})
    def test_bad_policy_pin_signature_provider_and_contents(self):
        self.error('policy_pin_mismatch',self.inspect,policy_pin='0'*64)
        self.error('policy_pin_required',self.inspect,policy_pin='bad')
        self.error('signature_invalid',self.inspect,signature='AA'*64)
        self.error('policy_refused:signature_invalid',self.inspect,signature='00'*64)
        self.error('policy_refused:signature_unchecked',self.inspect,openssl_pin='0'*64)
        self.archive.write_bytes(self.archive.read_bytes()+b'extra')
        self.error('archive_noncanonical',self.inspect)
    def test_no_follow_symlink_hardlink_relative_or_non_regular(self):
        target=self.root/'link';target.symlink_to(self.archive)
        self.error('input_unavailable',cli.read_regular,target,archive.MAX_ARCHIVE)
        self.error('input_path_invalid',cli.read_regular,Path('relative'),1024)
        self.error('input_unavailable',cli.read_regular,self.root,1024)
        hard=self.root/'hard';os.link(self.archive,hard)
        self.error('input_unavailable',cli.read_regular,self.archive,archive.MAX_ARCHIVE)
        hard.unlink();parent=self.root/'parent-link';parent.symlink_to(self.root, target_is_directory=True)
        self.error('input_unavailable',cli.read_regular,parent/self.archive.name,archive.MAX_ARCHIVE)
    def test_file_mutation_and_oversize_refuse(self):
        real=os.read;changed=[]
        def read(fd,size):
            data=real(fd,size)
            if not changed:
                changed.append(True);self.archive.write_bytes(b'changed')
            return data
        with patch.object(cli.os,'read',side_effect=read):
            self.error('input_unavailable',cli.read_regular,self.archive,archive.MAX_ARCHIVE)
        self.error('input_unavailable',cli.read_regular,self.policy,3)
    def test_policy_duplicate_members_rejected(self):
        raw=b'{"keys":{},"keys":{}}';self.policy.write_bytes(raw)
        self.error('policy_invalid',self.inspect,policy_pin=hashlib.sha256(raw).hexdigest())
    def test_relocated_trusted_tools_and_different_cwd(self):
        audit=self.root/'standalone-verifier';audit.mkdir()
        for name in ('release_archive_cli_study.py','release_archive_study.py','release_policy_study.py','release_ed25519_study.py'):
            shutil.copyfile(ROOT/'research/audit'/name,audit/name)
        fake=self.root/'kit';fake.mkdir()
        (fake/'__init__.py').write_text("from pathlib import Path; Path('untrusted-import-ran').write_text('bad')\n")
        cmd=[sys.executable,'-I','-S','-B',str(audit/'release_archive_cli_study.py'),
             '--archive',str(self.archive),'--statement',str(self.statement),'--policy',str(self.policy),
             '--policy-pin',self.pin,'--signature-hex',self.sig,'--openssl',str(signing.OPENSSL),'--openssl-pin',self.provider_pin]
        done=subprocess.run(cmd,cwd=self.root,capture_output=True,text=True,timeout=20)
        self.assertEqual(done.returncode,0,done.stderr+done.stdout)
        self.assertEqual(json.loads(done.stdout)['outcome'],'study_policy_consistent')
        self.assertFalse((self.root/'untrusted-import-ran').exists())
        unsafe=subprocess.run([sys.executable,str(audit/'release_archive_cli_study.py'),*cmd[5:]],
                              cwd=self.root,capture_output=True,text=True,timeout=20)
        self.assertEqual(unsafe.returncode,2)
        self.assertEqual(json.loads(unsafe.stdout)['reason'],'isolated_python_required')

if __name__=='__main__':unittest.main()
