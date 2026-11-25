#!/usr/bin/env python3
"""Строгий пакет и диагностика переданных bytes, без записи или восстановления."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'research/audit')]
import core_audit as audit
from kit.base import move_intent as intent, registry_journal, schema_v2
from kit.base.registry_policy import StoreError


def wire(doc):return (json.dumps(doc,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
def pin(raw):return hashlib.sha256(raw).hexdigest()

class IntentTests(unittest.TestCase):
    def fixture(self,source='L1'):
        docs={'L0':{'schema_version':2,'area':'L0','roots':['kit'],'release_version':'0.2.0-synthetic','entries':[]},
              'L1':{'schema_version':2,'area':'L1','roots':['profiles/pilot'],'revision':0,'entries':[audit.entry('C-1','contract','profile_owner',None,'.')]},
              'L2':{'schema_version':2,'area':'L2','roots':['.domain-agent-kit'],'revision':0,'entries':[audit.entry('P-1','contract','project_owner',None,'.')]}}
        parent={'L1':'C-1','L2':'P-1'};auth={'L1':'profile_owner','L2':'project_owner'};target='L1' if source=='L2' else 'L2'
        docs[source]['entries'].append(audit.entry('SOURCE','rule',auth[source],parent[source],'docs',state='active'))
        inputs={k:wire(v) for k,v in docs.items()};candidate=audit.entry('TARGET','rule',auth[target],parent[target],'docs',state='draft')
        args={'source':source,'target':target,'entry_id':'SOURCE','candidate':candidate,
              'portability_context':None if source=='L1' else {'project_names':[],'machine_names':[],'project_paths':[]}}
        return inputs,args
    def error(self,code,fn,*args,**kwargs):
        with self.assertRaises(StoreError) as e:fn(*args,**kwargs)
        self.assertEqual(e.exception.code,code)
    def classify(self,raw,state,p=None):return intent.assess(raw,intent_pin=pin(raw) if p is None else p,observed=state)
    def test_both_directions_four_states_and_exact_history(self):
        for src in ('L1','L2'):
            with self.subTest(src=src):
                before,args=self.fixture(src);original=copy.deepcopy((before,args))
                report,raw=intent.build(before,**args);self.assertEqual((before,args),original)
                self.assertEqual(report['outcome'],'intent_draft_only');self.assertEqual(report['intent_sha256'],pin(raw))
                self.assertEqual(report['bytes'],len(raw));self.assertEqual(report['apply'],'not_implemented')
                after={row['area']:row['after_utf8'].encode() for row in report['preview']['diffs']};dst=args['target']
                states=((before,'before_both'),(dict(before,**{dst:after[dst]}),'target_after_source_before'),
                        (dict(before,**after),'after_both'),(dict(before,**{src:after[src]}),'impossible_order'))
                for state,expected in states:
                    result=self.classify(raw,state);self.assertEqual(result['state'],expected)
                    self.assertEqual(result['recovery'],'not_implemented');self.assertEqual(result['marker'],'not_checked')
                for area in ('L1','L2'):
                    doc,journal=registry_journal.unpack_registry(schema_v2.parse_json(after[area]),area=area)
                    ids={e['id'] for e in doc['entries']};self.assertNotIn('SOURCE',ids)
                    self.assertEqual('TARGET' in ids,area==dst)
                    self.assertEqual(journal['decisions'][-1]['operation'],'delete' if area==src else 'create')
    def test_foreign_inputs_and_bad_observation(self):
        before,args=self.fixture();_,raw=intent.build(before,**args)
        for area in ('L0','L1','L2'):
            changed=dict(before,**{area:before[area]+b' '})
            self.assertEqual(self.classify(raw,changed)['state'],'foreign_or_changed')
        for observed in ({},dict(before,L3=b''),dict(before,L0='text'),dict(before,L1=b'a'*(intent._MAX_INPUT+1))):
            self.error('move_observation_invalid',intent.assess,raw,intent_pin=pin(raw),observed=observed)
    def test_pin_is_separate_and_required(self):
        before,args=self.fixture();_,raw=intent.build(before,**args)
        for invalid in (None,'','A'*64,'0'*63,1):self.error('move_intent_pin_required',intent.assess,raw,intent_pin=invalid,observed=before)
        self.error('move_intent_pin_mismatch',intent.assess,raw,intent_pin='0'*64,observed=before)
        self.error('move_intent_invalid',intent.assess,'not bytes',intent_pin=pin(raw),observed=before)
    def test_repin_does_not_make_malformed_record_valid(self):
        before,args=self.fixture();_,raw=intent.build(before,**args);doc=json.loads(raw)
        variants=[]
        extra=dict(doc,unknown=True);variants.append(intent._wire(extra))
        bad=dict(doc,intent_format=True);variants.append(intent._wire(bad))
        bad=copy.deepcopy(doc);bad['after']['L2']=base64.b64encode(b'forged').decode();variants.append(intent._wire(bad))
        bad=copy.deepcopy(doc);bad['before']['L1']+='=';variants.append(intent._wire(bad))
        bad=copy.deepcopy(doc);bad['before']['L3']=bad['before']['L0'];variants.append(intent._wire(bad))
        bad=copy.deepcopy(doc);bad['candidate']['text']='modified';variants.append(intent._wire(bad))
        bad=copy.deepcopy(doc);bad['portability_context']={};variants.append(intent._wire(bad))
        variants.extend((raw+b'\n',b'{"intent_format":1,"intent_format":1}',b'{bad',b'x'*(intent.MAX_INTENT+1)))
        for variant in variants:
            with self.subTest(length=len(variant)):
                self.error('move_intent_invalid',intent.assess,variant,intent_pin=pin(variant),observed=before)
    def test_forged_intent_and_forged_pin_do_not_establish_authority(self):
        before,args=self.fixture();doc=json.loads(before['L1']);doc['entries'][-1]['text']='untrusted synthetic modification';before['L1']=wire(doc)
        report,raw=intent.build(before,**args)
        result=intent.assess(raw,intent_pin=report['intent_sha256'],observed=before)
        self.assertEqual(result['state'],'before_both');self.assertEqual(result['origin'],'not_verified')
        self.assertEqual(result['authorization'],'not_checked')
    def test_no_file_io_and_context_validation(self):
        before,args=self.fixture();saved=copy.deepcopy((before,args))
        with patch('builtins.open',side_effect=AssertionError('no file access')),patch.object(Path,'open',side_effect=AssertionError('no file access')):
            _,raw=intent.build(before,**args);self.assertEqual(self.classify(raw,before)['state'],'before_both')
        self.assertEqual(saved,(before,args))
        self.error('invalid_context',intent.build,before,**dict(args,portability_context={}))
        inputs,args=self.fixture('L2');self.error('invalid_context',intent.build,inputs,**dict(args,portability_context=None))

if __name__=='__main__':unittest.main()
