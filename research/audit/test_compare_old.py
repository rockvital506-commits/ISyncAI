#!/usr/bin/env python3
"""Сравнение только синтетических байтов 0.1.36/v2; не миграция и не проверка живого Kit."""
import base64
import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from kit.base import profile_journal
from kit.compare_old import ComparisonError, MAX_BYTES, NOT_CHECKED, compare


def raw(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True)+'\n').encode('utf-8')


def old_entry(ident, kind, parent, text):
    return {'id':ident, 'kind':kind, 'contract':parent, 'title':'Название '+ident,
            'state':'active', 'scope':'.', 'text':text, 'basis':'основание', 'criterion':'критерий',
            'key':None, 'value':None, 'revision':1, 'updated_at':'2026-01-01T00:00:00Z',
            'reason':'синтетическая причина'}


def fixture():
    base_contract = old_entry('B-1','contract',None,'Системный тестовый контракт')
    contract = old_entry('P-1','contract',None,'Проектный тестовый контракт')
    rule = old_entry('P-2','rule','P-1','Синтетический текст правила')
    rule.update(key='color',value='blue',owner='Synthetic Owner',review_days=90,
                reviewed_at='2026-01-01T00:00:00Z',review_by='2026-04-01T00:00:00Z')
    state = {'schema_version':1, 'revision':2, 'next_id':10, 'entries':[contract,rule],
             'decisions':[{'revision':1,'at':'2026-01-01T00:00:00Z','op':'create','reason':'тест','subject':'P-1'},
                          {'revision':2,'at':'2026-01-01T00:00:00Z','op':'create','reason':'тест','subject':'P-2'}],
             'base':{'version':'0.1.36','pin':'a'*64,'origin':'synthetic','installed':{}},
             'adapter':None, 'retired':False, 'tombstones':[]}
    checks = {'schema_version':1,'checks':[{'at':'2026-01-01T00:00:00Z','revision':2,'base_version':'0.1.36',
                                           'adapter_version':None,'observation':{'case':'synthetic'}}]}
    base = {'schema_version':1,'entries':[base_contract]}
    entries = []
    for row in state['entries']:
        converted = {k:row[k] for k in ('id','kind','title','state','scope','text','basis','criterion')}
        converted.update(parent=row['contract'],authority='project_owner')
        if row['key'] is not None: converted.update(key=row['key'],value=row['value'])
        entries.append(converted)
    target = {'schema_version':2,'area':'L2','roots':['.domain-agent-kit'],'revision':2,'entries':entries}
    source = {'state':raw(state),'checks':raw(checks),'base_rules':raw(base)}
    candidate = {'registry':raw(target),**{'preserved_'+k:v for k,v in source.items()}}
    return state, checks, base, target, source, candidate


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.state,self.checks,self.base,self.target,self.source,self.candidate=fixture()

    def result(self): return compare(self.source,self.candidate)
    def source_state(self): self.source['state']=raw(self.state)
    def target_registry(self): self.candidate['registry']=raw(self.target)
    def error(self, code):
        with self.assertRaises(ComparisonError) as exc: self.result()
        self.assertEqual(exc.exception.code,code)

    def test_matching_core_and_archives_never_claims_ready(self):
        before=(copy.deepcopy(self.source),copy.deepcopy(self.candidate))
        with patch('builtins.open',side_effect=AssertionError('unexpected I/O')):
            first=self.result(); second=self.result()
        self.assertEqual(first,second)
        self.assertEqual((self.source,self.candidate),before)
        self.assertEqual(first['outcome'],'core_and_archives_equal')
        self.assertFalse(first['migration_ready'])
        self.assertEqual(first['not_checked'],list(NOT_CHECKED))
        self.assertIn('legacy_history_in_new_runtime',first['not_checked'])
        self.assertIn('scope_behavior_equivalence',first['not_checked'])
        self.assertEqual(first['blockers'],[]); self.assertEqual(first['differences'],[])
        self.assertNotIn('Синтетический текст правила',json.dumps(first,ensure_ascii=False))
        self.assertNotIn('Synthetic Owner',json.dumps(first,ensure_ascii=False))

    def test_each_core_field_and_key_pair_detected(self):
        values={'kind':'protocol','title':'другое','state':'draft','scope':'docs','text':'изменено',
                'basis':'другое основание','criterion':'другой критерий','value':'red'}
        original=copy.deepcopy(self.target)
        for field,value in values.items():
            with self.subTest(field=field):
                self.target=copy.deepcopy(original); self.target['entries'][1][field]=value; self.target_registry()
                result=self.result(); self.assertEqual(result['outcome'],'differences')
                expected='key_value' if field=='value' else field
                self.assertIn({'code':'field_changed','id':'P-2','field':expected},result['differences'])

    def test_parent_change_cannot_be_silent(self):
        parent=copy.deepcopy(self.target['entries'][0]); parent['id']='P-3'
        self.target['entries'].append(parent); self.target['entries'][1]['parent']='P-3'; self.target_registry()
        result=self.result()
        self.assertIn({'code':'entry_unexpected','id':'P-3'},result['differences'])
        self.assertIn({'code':'field_changed','id':'P-2','field':'parent'},result['differences'])

    def test_missing_entry_and_revision_detected(self):
        self.target['entries'].pop(); self.target['revision']=3; self.target_registry()
        result=self.result()
        self.assertIn({'code':'entry_missing','id':'P-2'},result['differences'])
        self.assertIn({'code':'project_revision_changed'},result['differences'])
        self.assertFalse(result['migration_ready'])

    def test_archives_are_compared_byte_for_byte(self):
        for name in ('state','checks','base_rules'):
            with self.subTest(name=name):
                candidate=copy.deepcopy(self.candidate); candidate['preserved_'+name]+=b' '
                result=compare(self.source,candidate)
                self.assertEqual(result['outcome'],'differences')
                self.assertIn({'code':'archive_changed','part':name},result['differences'])

    def test_cross_layer_parent_is_always_blocked(self):
        self.state['entries'][1]['contract']='B-1'; self.source_state()
        self.candidate['preserved_state']=self.source['state']
        result=self.result()
        self.assertEqual(result['outcome'],'blocked')
        self.assertIn({'code':'cross_layer_parent','id':'P-2','parent':'B-1'},result['blockers'])
        self.assertIn({'code':'field_changed','id':'P-2','field':'parent'},result['differences'])
        self.assertFalse(result['migration_ready'])

    def test_retired_project_and_tombstones_block_even_with_exact_archives(self):
        self.state['retired']=True
        self.state['tombstones']=[{'id':'P-9','kind':'rule','contract':'P-1','scope':'.','title':'старая',
                                   'at':'2026-01-01T00:00:00Z','reason':'синтетика','revision':1}]
        self.source_state(); self.candidate['preserved_state']=self.source['state']
        result=self.result()
        self.assertEqual(result['outcome'],'blocked')
        self.assertIn({'code':'project_retired'},result['blockers'])
        self.assertIn({'code':'legacy_tombstones','count':1},result['blockers'])
        self.assertEqual(result['differences'],[])
        self.assertFalse(result['migration_ready'])

    def test_invalid_retirement_or_tombstone_is_refused(self):
        self.state['retired']='yes'; self.source_state(); self.error('source_invalid')
        self.state['retired']=False; self.state['tombstones']=[{'id':'B-1'}]; self.source_state()
        self.error('source_invalid')

    def test_unknown_legacy_parent_refused(self):
        self.state['entries'][1]['contract']='B-99'; self.source_state()
        self.error('source_invalid')

    def test_missing_and_duplicate_old_fields_refused(self):
        self.state['entries'][1].pop('text'); self.source_state(); self.error('source_invalid')
        self.state,self.checks,self.base,self.target,self.source,self.candidate=fixture()
        self.state['entries'].append(copy.deepcopy(self.state['entries'][1])); self.source_state()
        self.error('source_invalid')

    def test_invalid_legacy_counter_and_incomplete_decisions_rejected(self):
        self.state['next_id']=2; self.source_state(); self.error('source_invalid')
        self.state['next_id']=10; self.state['decisions'].pop(); self.source_state(); self.error('source_invalid')
        self.state['decisions']=None; self.source_state(); self.error('source_invalid')

    def test_unknown_version_and_boolean_schema_rejected(self):
        for version in ('0.1.35','0.2.0','0.1.36+custom',None):
            with self.subTest(version=version):
                self.state['base']['version']=version; self.source_state(); self.error('unknown_version')
        self.state['base']['version']='0.1.36'; self.state['schema_version']=True; self.source_state()
        self.error('source_invalid')

    def test_invalid_target_and_json_rejected(self):
        self.target['entries'][1]['parent']='missing'; self.target_registry(); self.error('target_invalid')
        self.candidate['registry']=b'{"area":"L2","area":"L2"}'; self.error('target_invalid')
        self.source['state']=b'{"schema_version":1,"schema_version":1}'; self.error('source_invalid')

    def test_registry_journal_supported_without_assuming_legacy_history_imported(self):
        anchors={row['id']:profile_journal.entry_digest(row) for row in self.target['entries']}
        doc={'registry_format':2,'registry':self.target,'journal':{'base_revision':2,'base_entries':anchors,'decisions':[]}}
        self.candidate['registry']=raw(doc)
        result=self.result()
        self.assertEqual(result['outcome'],'core_and_archives_equal')
        self.assertIn('legacy_history_in_new_runtime',result['not_checked'])

    def test_wrong_shapes_and_size_refused(self):
        with self.assertRaises(ComparisonError) as exc: compare({},self.candidate)
        self.assertEqual(exc.exception.code,'input_shape')
        self.source['state']=b'x'*(MAX_BYTES+1); self.error('input_size_or_type')
        self.source['state']='not bytes'; self.error('input_size_or_type')

    def cli(self, source, candidate):
        request={'format':1,'source':{k:base64.b64encode(v).decode() for k,v in source.items()},
                 'candidate':{k:base64.b64encode(v).decode() for k,v in candidate.items()}}
        return subprocess.run([sys.executable,'-I','-S','-B',str(ROOT/'kit/compare_old.py')],
                              input=json.dumps(request).encode(),capture_output=True,timeout=30)

    def test_cli_equal_and_differences_are_not_migration_success(self):
        p=self.cli(self.source,self.candidate); self.assertEqual(p.returncode,0,p.stderr)
        result=json.loads(p.stdout); self.assertEqual(result['outcome'],'core_and_archives_equal')
        self.assertFalse(result['migration_ready'])
        self.assertNotIn('Синтетический текст правила'.encode(),p.stdout)
        self.candidate['preserved_checks']+=b' '
        p=self.cli(self.source,self.candidate); self.assertEqual(p.returncode,0)
        self.assertEqual(json.loads(p.stdout)['outcome'],'differences')

    def test_cli_rejects_malformed_base64_without_echo(self):
        request={'format':1,'source':{k:'!!!' for k in self.source},
                 'candidate':{k:'YQ==' for k in self.candidate}}
        p=subprocess.run([sys.executable,'-I','-S','-B',str(ROOT/'kit/compare_old.py')],
                         input=json.dumps(request).encode(),capture_output=True,timeout=30)
        self.assertEqual(p.returncode,1)
        self.assertEqual(json.loads(p.stdout)['code'],'input_encoding')
        self.assertNotIn(b'!!!',p.stdout+p.stderr)


if __name__=='__main__': unittest.main()
