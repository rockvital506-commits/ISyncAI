#!/usr/bin/env python3
"""Связанный подписанный экспорт на временных синтетических ключах, не поставка релиза."""
import copy
import hashlib
import json
from pathlib import Path
import select
import subprocess
import sys
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'research/audit')]
import test_source_release_trust as fixture
from kit import snapshot_export as export, source_release_trust as trust

@unittest.skipUnless(fixture.SUPPORTED,'OpenSSL/POSIX unavailable; not_run')
class SignedExportTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.SourceTrustTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.dest=self.f.ctx.root/'signed-snapshot';self.signature=self.f.sign()
        self.loader=export._trusted_loader();self.verifier=self.loader._trusted_verifier()
    def session(self,**kwargs):
        opts=dict(public_key=self.f.public,trusted_key_id=self.f.key_id,signature=self.signature,
                  openssl_executable=fixture.OPENSSL,openssl_pin=self.f.binary_pin,
                  loader=self.loader,verifier=self.verifier,trust=trust);opts.update(kwargs)
        return export.SignedExportSession(self.f.ctx.candidate,self.dest,**opts)
    def error(self,code,fn,*a,**kw):
        with self.assertRaises(export.ExportError) as e:fn(*a,**kw)
        self.assertEqual(str(e.exception),code)
    def test_signed_plan_confirmation_repeat_and_closed_export(self):
        s=self.session();p=s.plan();self.assertFalse(self.dest.exists())
        self.assertEqual(p['authentication']['manifest_sha256'],hashlib.sha256(self.f.manifest.read_bytes()).hexdigest())
        self.assertEqual(p['key_distribution'],'not_verified')
        self.error('confirmation_required',s.apply,p,'wrong');self.assertFalse(self.dest.exists())
        result=s.apply(p,p['ticket']);self.assertEqual(result['outcome'],'created')
        self.assertEqual(result['installation'],'not_performed')
        self.verifier.verify(self.dest,pin=p['authentication']['manifest_sha256'])
        self.error('ticket_unknown',s.apply,p,p['ticket'])
    def test_bad_signature_key_provider_refused_without_destination(self):
        for kw in ({'signature':bytes(64)},{'trusted_key_id':'0'*64},{'openssl_pin':'0'*64}):
            with self.subTest(kw=kw):self.error('signed_source_unverified',self.session(**kw).plan)
        self.assertFalse(self.dest.exists())
    def test_changed_candidate_signature_plan_and_parameters_revoke(self):
        s=self.session();p=s.plan();modified=copy.deepcopy(p);modified['authentication']['key_id']='0'*64
        self.error('plan_mismatch',s.apply,modified,p['ticket']);self.error('ticket_unknown',s.apply,p,p['ticket'])
        s=self.session();p=s.plan();s.signature=bytes(64)
        self.error('stale_plan',s.apply,p,p['ticket']);self.assertFalse(self.dest.exists())
        s=self.session();p=s.plan();target=self.f.ctx.candidate/'kit/base/operation_plan.py';target.write_bytes(target.read_bytes()+b'\n# drift\n')
        self.error('signed_source_unverified',s.apply,p,p['ticket']);self.error('ticket_unknown',s.apply,p,p['ticket']);self.assertFalse(self.dest.exists())
    def test_second_signature_verification_and_publication_failure(self):
        s=self.session();p=s.plan()
        with patch.object(trust.openssl_ed25519,'verify',return_value=False):self.error('signed_source_unverified',s.apply,p,p['ticket'])
        self.assertFalse(self.dest.exists());s=self.session();p=s.plan()
        with patch.object(export,'_write_exclusive',side_effect=OSError('synthetic')):
            self.error('destination_partial_or_unverified',s.apply,p,p['ticket'])
        self.assertTrue(self.dest.exists());self.error('ticket_unknown',s.apply,p,p['ticket'])
    def test_cli_signed_and_no_trust_mode_downgrade(self):
        cmd=[sys.executable,'-I','-S','-B',str(ROOT/'kit/snapshot_export.py'),'--source',str(self.f.ctx.candidate),
             '--destination',str(self.dest),'--public-key-hex',self.f.public.hex(),'--trusted-key-id',self.f.key_id,
             '--signature-hex',self.signature.hex(),'--openssl',str(fixture.OPENSSL),'--openssl-pin',self.f.binary_pin]
        bad=subprocess.run(cmd+['--manifest-pin','0'*64],capture_output=True,text=True,timeout=10)
        self.assertEqual(bad.returncode,2);self.assertFalse(self.dest.exists())
        p=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
        try:
            def send(obj):
                p.stdin.write(json.dumps(obj)+'\n');p.stdin.flush();ready,_,_=select.select([p.stdout],[],[],20)
                self.assertTrue(ready);return json.loads(p.stdout.readline())
            plan=send({'type':'plan'});self.assertEqual(plan['outcome'],'planned',plan)
            result=send({'type':'apply','plan':plan,'confirmed_ticket':plan['ticket']});self.assertEqual(result['outcome'],'created',result)
        finally:
            p.stdin.close();p.wait(timeout=10);p.stdout.close();p.stderr.close()

if __name__=='__main__':unittest.main()
