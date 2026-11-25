#!/usr/bin/env python3
"""Только синтетические байты; не миграция, установка или чтение рабочего проекта."""
import base64
import copy
import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'research/audit')]
from test_compare_old import fixture, raw
from kit.compare_old import MAX_BYTES, compare
from kit.legacy_capsule import MAX_REQUEST, CapsuleError, extract, inspect, prepare, read_history


def digest(data): return hashlib.sha256(data).hexdigest()
def canon(value): return (json.dumps(value,ensure_ascii=True,sort_keys=True,separators=(',',':'))+'\n').encode('ascii')


class CapsuleTests(unittest.TestCase):
    def setUp(self):
        self.state,self.checks,self.base,self.target,self.source,self.candidate=fixture()
        self.state['tombstones']=[{'id':'P-9','reason':'синтетическое удаление'}]
        self.source['state']=raw(self.state)
        self.item=prepare(self.source)
        self.archive=self.item['archive']; self.pin=self.item['archive_sha256']

    def denied(self, fn, code):
        with self.assertRaises(CapsuleError) as exc: fn()
        self.assertEqual(exc.exception.code,code)

    def test_determinism_exact_round_trip_and_no_io(self):
        before=copy.deepcopy(self.source)
        with patch('builtins.open',side_effect=AssertionError('unexpected I/O')):
            repeated=prepare(dict(reversed(list(self.source.items()))))
            extracted=extract(self.archive,pin=self.pin)
            info=inspect(self.archive,pin=self.pin)
        self.assertEqual(repeated,self.item)
        self.assertEqual(extracted,self.source)
        self.assertEqual(self.source,before)
        self.assertEqual(info['outcome'],'verified_bytes')
        self.assertEqual(info['source_health'],'not_checked')
        self.assertFalse(info['migration_ready'])
        self.assertEqual(set(info['members']),set(self.source))
        self.assertNotIn('синтетическое удаление',json.dumps(info,ensure_ascii=False))

    def test_history_is_explicit_and_not_v2_import(self):
        result=read_history(self.archive,pin=self.pin)
        self.assertEqual(result['decisions'],self.state['decisions'])
        self.assertEqual(result['tombstones'],self.state['tombstones'])
        self.assertEqual(result['checks'],self.checks['checks'])
        self.assertEqual(result['project_revision'],self.state['revision'])
        self.assertFalse(result['legacy_history_imported'])
        self.assertEqual(result['source_health'],'not_checked')
        self.assertFalse(result['migration_ready'])

    def test_preserved_bytes_flow_to_comparison_but_tombstones_block(self):
        contents=extract(self.archive,pin=self.pin)
        candidate={**self.candidate,**{'preserved_'+k:v for k,v in contents.items()}}
        result=compare(self.source,candidate)
        self.assertEqual(result['outcome'],'blocked')
        self.assertIn({'code':'legacy_tombstones','count':1},result['blockers'])
        self.assertEqual(result['differences'],[])
        self.assertFalse(result['migration_ready'])

    def test_pin_is_required_and_tampering_rejected(self):
        for pin in (None,'','A'*64,'0'*63,123):
            with self.subTest(pin=pin): self.denied(lambda: inspect(self.archive,pin=pin),'pin_required')
        self.denied(lambda: inspect(self.archive,pin='0'*64),'capsule_digest_mismatch')
        self.denied(lambda: inspect(self.archive+b' ',pin=self.pin),'capsule_digest_mismatch')

    def test_internally_consistent_alternative_is_not_authenticity(self):
        other=dict(self.source); other['state']+=b' '
        changed=prepare(other)
        self.denied(lambda: inspect(changed['archive'],pin=self.pin),'capsule_digest_mismatch')
        # Если вызывающий доверяет новому pin без независимого основания, подмена не доказывается.
        self.assertEqual(extract(changed['archive'],pin=changed['archive_sha256']),other)

    def test_member_digest_and_size_checked_independently_of_archive_pin(self):
        for field,value in [('sha256','0'*64),('size',1)]:
            with self.subTest(field=field):
                doc=json.loads(self.archive);doc['members']['state'][field]=value; changed=canon(doc)
                self.denied(lambda: inspect(changed,pin=digest(changed)),'member_digest_mismatch')

    def test_noncanonical_duplicate_and_unknown_fields_rejected(self):
        doc=json.loads(self.archive)
        pretty=json.dumps(doc,indent=2).encode()
        self.denied(lambda: inspect(pretty,pin=digest(pretty)),'capsule_noncanonical')
        duplicate=b'{"format":1,"format":1}'
        self.denied(lambda: inspect(duplicate,pin=digest(duplicate)),'capsule_invalid')
        doc['unexpected']=True; changed=canon(doc)
        self.denied(lambda: inspect(changed,pin=digest(changed)),'capsule_invalid')

    def test_missing_extra_parts_bad_fields_and_boolean_size_rejected(self):
        for mutation in ('missing','extra','field','boolean'):
            with self.subTest(mutation=mutation):
                doc=json.loads(self.archive)
                if mutation=='missing': del doc['members']['checks']
                if mutation=='extra': doc['members']['unexpected']=doc['members']['checks']
                if mutation=='field': doc['members']['checks']['extra']='x'
                if mutation=='boolean': doc['members']['checks']['size']=True
                changed=canon(doc)
                self.denied(lambda: inspect(changed,pin=digest(changed)),'capsule_invalid')

    def test_bad_and_noncanonical_base64_rejected(self):
        for value in ('!!!','YQ','YQ==\n',''):
            with self.subTest(value=value):
                doc=json.loads(self.archive);doc['members']['checks']['base64']=value;changed=canon(doc)
                self.denied(lambda: inspect(changed,pin=digest(changed)),'invalid_encoding')

    def test_invalid_source_is_preserved_but_not_accepted_as_history(self):
        source=dict(self.source); source['state']=b'{damaged-json'
        prepared=prepare(source)
        self.assertEqual(extract(prepared['archive'],pin=prepared['archive_sha256']),source)
        self.denied(lambda: read_history(prepared['archive'],pin=prepared['archive_sha256']),'legacy_data_invalid')

    def test_unknown_version_and_malformed_history_rejected(self):
        for mutation,code in [('version','unknown_version'),('schema_bool','legacy_data_invalid'),('gap','legacy_data_invalid'),
                              ('bad_item','legacy_data_invalid')]:
            with self.subTest(mutation=mutation):
                state=copy.deepcopy(self.state)
                if mutation=='version':state['base']['version']='0.1.35'
                if mutation=='schema_bool':state['schema_version']=True
                if mutation=='gap':state['decisions'].pop()
                if mutation=='bad_item':state['decisions'][0]='not an object'
                source={**self.source,'state':raw(state)}; item=prepare(source)
                self.denied(lambda: read_history(item['archive'],pin=item['archive_sha256']),code)

    def test_nonfinite_numeric_history_cannot_escape_as_json(self):
        state=copy.deepcopy(self.state); state['decisions'][0]['reason']='OVERFLOW'
        encoded=raw(state).replace(b'"OVERFLOW"',b'1e999')
        item=prepare({**self.source,'state':encoded})
        self.denied(lambda: read_history(item['archive'],pin=item['archive_sha256']),'legacy_data_invalid')

    def test_maximum_sized_parts_round_trip(self):
        source={name:bytes([65+i])*MAX_BYTES for i,name in enumerate(sorted(self.source))}
        item=prepare(source)
        self.assertEqual(extract(item['archive'],pin=item['archive_sha256']),source)
        self.assertEqual({name:info['size'] for name,info in inspect(item['archive'],pin=item['archive_sha256'])['members'].items()},
                         {name:MAX_BYTES for name in source})

    def test_bad_source_shape_and_sizes_rejected(self):
        self.denied(lambda: prepare({}),'source_shape')
        self.denied(lambda: prepare({**self.source,'extra':b'x'}),'source_shape')
        self.denied(lambda: prepare({**self.source,'state':b''}),'source_size_or_type')
        self.denied(lambda: prepare({**self.source,'state':b'x'*(MAX_BYTES+1)}),'source_size_or_type')
        self.denied(lambda: prepare({**self.source,'state':'text'}),'source_size_or_type')

    def cli(self,request):
        return subprocess.run([sys.executable,'-I','-S','-B',str(ROOT/'kit/legacy_capsule.py')],
                              input=json.dumps(request).encode(),capture_output=True,timeout=30)

    def test_cli_prepare_inspect_history_and_errors(self):
        source={k:base64.b64encode(v).decode('ascii') for k,v in self.source.items()}
        p=self.cli({'format':1,'action':'prepare','source':source}); self.assertEqual(p.returncode,0,p.stderr)
        package=json.loads(p.stdout)
        self.assertEqual(package['archive_sha256'],self.pin)
        encoded=package['archive_base64']
        p=self.cli({'format':1,'action':'inspect','archive_base64':encoded,'pin':self.pin})
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(json.loads(p.stdout)['outcome'],'verified_bytes')
        self.assertNotIn('синтетическое удаление'.encode(),p.stdout)
        p=self.cli({'format':1,'action':'history','archive_base64':encoded,'pin':self.pin})
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(json.loads(p.stdout)['tombstones'],self.state['tombstones'])
        p=self.cli({'format':1,'action':'inspect','archive_base64':encoded,'pin':'0'*64})
        self.assertEqual(p.returncode,1)
        self.assertEqual(json.loads(p.stdout)['code'],'capsule_digest_mismatch')

    def test_cli_history_handles_escaped_surrogate_without_crashing(self):
        state=copy.deepcopy(self.state); state['decisions'][0]['reason']=chr(0xd800)
        source={**self.source,'state':json.dumps(state,ensure_ascii=True).encode('ascii')}
        item=prepare(source)
        p=self.cli({'format':1,'action':'history','archive_base64':base64.b64encode(item['archive']).decode(),
                    'pin':item['archive_sha256']})
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(json.loads(p.stdout)['decisions'][0]['reason'],chr(0xd800))

    def test_cli_maximum_sized_parts_round_trip(self):
        source={name:bytes([65+i])*MAX_BYTES for i,name in enumerate(sorted(self.source))}
        encoded={name:base64.b64encode(value).decode('ascii') for name,value in source.items()}
        p=self.cli({'format':1,'action':'prepare','source':encoded})
        self.assertEqual(p.returncode,0,p.stderr)
        package=json.loads(p.stdout)
        p=self.cli({'format':1,'action':'inspect','archive_base64':package['archive_base64'],
                    'pin':package['archive_sha256']})
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(set(json.loads(p.stdout)['members']),set(source))
        self.assertEqual(extract(base64.b64decode(package['archive_base64']),pin=package['archive_sha256']),source)

    def test_cli_oversized_request_rejected(self):
        p=subprocess.run([sys.executable,'-I','-S','-B',str(ROOT/'kit/legacy_capsule.py')],
                         input=b'x'*(MAX_REQUEST+1),capture_output=True,timeout=30)
        self.assertEqual(p.returncode,1)
        self.assertEqual(json.loads(p.stdout)['code'],'request_size')
        self.assertLess(len(p.stdout),100)

    def test_cli_invalid_input_does_not_echo(self):
        p=self.cli({'format':1,'action':'prepare','source':{'state':'!!!','checks':'YQ==','base_rules':'YQ=='}})
        self.assertEqual(p.returncode,1)
        self.assertEqual(json.loads(p.stdout)['code'],'invalid_encoding')
        self.assertNotIn(b'!!!',p.stdout+p.stderr)


if __name__=='__main__': unittest.main()
