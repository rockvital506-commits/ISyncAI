#!/usr/bin/env python3
"""Модель политики выпуска: публичный тестовый ключ, не фактический релиз."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'research/audit')]
import bootstrap_binding_study as previous
import release_policy_study as study
import test_bootstrap_binding_study as fixture


class ReleasePolicyStudyTests(unittest.TestCase):
    def setUp(self):
        self.fx=fixture.BindingStudyTests();self.fx.setUp();self.addCleanup(self.fx.doCleanups)
        self.manifest=(ROOT/'kit/KIT-VERSION.json').read_bytes();self.manifest_doc=json.loads(self.manifest)
        self.files={path:(ROOT/path).read_bytes() for path in self.manifest_doc['files']}
        self.key_id=study.sha(fixture.PUBLIC)
        self.doc={'format':1,'product':'DomainAgentKit','channel':'test','sequence':3,
                  'version':self.manifest_doc['version'],'key_id':self.key_id,
                  'manifest_sha256':study.sha(self.manifest),'system_sha256':study.sha(self.files['kit/SYSTEM-L0.json']),
                  'loader_sha256':study.sha(self.files['kit/snapshot_session.py']),
                  'verifier_sha256':study.sha(self.files['kit/verify_candidate.py'])}
        self.policy={'format':1,'product':'DomainAgentKit','channel':'test','keys':{self.key_id:fixture.PUBLIC},
                     'revoked':[],'required_paths':sorted(self.files),'loader_sha256':self.doc['loader_sha256'],
                     'verifier_sha256':self.doc['verifier_sha256'],
                     'checkpoint':{'sequence':0,'statement_sha256':None}}
    def sign(self,doc=None,domain=study.DOMAIN):
        return self.fx.sign(study.canonical(doc or self.doc),domain=domain)
    def assess(self,doc=None,signature=None,policy=None,files=None,manifest=None,verify=None,raw=None):
        statement=raw if raw is not None else study.canonical(self.doc if doc is None else doc)
        if signature is None:signature=self.fx.sign(statement,domain=study.DOMAIN)
        return study.assess(statement,signature,policy=self.policy if policy is None else policy,
                            files=self.files if files is None else files,manifest=self.manifest if manifest is None else manifest,
                            verify_signature=self.fx.verify if verify is None else verify)
    def error(self,code,**kw):
        with self.assertRaises(study.PolicyError) as e:self.assess(**kw)
        self.assertEqual(str(e.exception),code)
    def test_real_signature_full_manifest_and_explicit_limitations(self):
        result=self.assess();self.assertEqual(result['outcome'],'study_policy_consistent')
        self.assertEqual(result['freshness'],'not_proved');self.assertEqual(result['installation'],'not_performed')
        self.assertEqual(result['l0_schema_and_semantics'],'not_checked')
    def test_malformed_statement_and_wrong_domain(self):
        self.error('statement_invalid',raw=b'{"format":1,"format":1}')
        self.error('statement_invalid',raw=study.canonical(self.doc)+b' ')
        doc=dict(self.doc,sequence=True);self.error('statement_invalid',doc=doc)
        self.error('signature_invalid',signature=self.sign(domain=previous.DOMAIN))
        self.error('signature_invalid',signature=bytes(64))
        self.error('signature_unchecked',verify=lambda *_: 1)
    def test_external_policy_key_revocation_channel_and_bootstrap(self):
        p=copy.deepcopy(self.policy);p['revoked']=[self.key_id];self.error('key_untrusted_or_revoked',policy=p)
        p=copy.deepcopy(self.policy);p['keys']={study.sha(b'x'*32):b'x'*32};self.error('key_untrusted_or_revoked',policy=p)
        p=copy.deepcopy(self.policy);p['channel']='other';self.error('channel_mismatch',policy=p)
        p=copy.deepcopy(self.policy);p['loader_sha256']='0'*64;self.error('bootstrap_untrusted',policy=p)
        p=copy.deepcopy(self.policy);p['revoked']=['0'*64];self.error('policy_invalid',policy=p)
    def test_antirollback_only_if_external_checkpoint_trusted(self):
        digest=study.sha(study.canonical(self.doc));p=copy.deepcopy(self.policy)
        p['checkpoint']={'sequence':3,'statement_sha256':digest};self.assertEqual(self.assess(policy=p)['sequence'],3)
        p['checkpoint']['statement_sha256']='0'*64;self.error('sequence_conflict',policy=p)
        p['checkpoint']={'sequence':4,'statement_sha256':'0'*64};self.error('rollback_refused',policy=p)
        # Если обе внешние ячейки возвращены в старое состояние, модель не обнаружит подмену.
        p['checkpoint']={'sequence':0,'statement_sha256':None};self.assertEqual(self.assess(policy=p)['freshness'],'not_proved')
    def test_changed_or_missing_files_manifest_system_and_required_set(self):
        files=dict(self.files);files['kit/verify_candidate.py']+=b'\n# modified\n';self.error('files_mismatch',files=files)
        files=dict(self.files);del files['kit/SYSTEM-L0.json'];self.error('manifest_invalid',files=files)
        p=copy.deepcopy(self.policy);p['required_paths'].remove('kit/SYSTEM-L0.json');self.error('manifest_invalid',policy=p)
        self.error('manifest_invalid',manifest=self.manifest+b' ')
        p=copy.deepcopy(self.policy);p['required_paths'].append('../outside');self.error('policy_invalid',policy=p)
    def test_consistent_replacement_system_wrong_version_still_refused(self):
        files=dict(self.files);system=json.loads(files['kit/SYSTEM-L0.json']);system['release_version']='0.0.0'
        files['kit/SYSTEM-L0.json']=(json.dumps(system)+'\n').encode()
        manifest=copy.deepcopy(self.manifest_doc);manifest['files']['kit/SYSTEM-L0.json']=study.sha(files['kit/SYSTEM-L0.json'])
        raw=(json.dumps(manifest)+'\n').encode();doc=dict(self.doc,system_sha256=study.sha(files['kit/SYSTEM-L0.json']),manifest_sha256=study.sha(raw))
        self.error('system_invalid',doc=doc,files=files,manifest=raw)

if __name__=='__main__':unittest.main()
