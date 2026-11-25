#!/usr/bin/env python3
"""Синтетическая проверка ограниченного структурного scope-отчёта."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'research/audit')]
import core_audit as audit
from kit.base import applicability
from kit.base.registry_policy import StoreError


class ApplicabilityTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='domain-applicability-');self.addCleanup(temp.cleanup)
        self.root=Path(temp.name).resolve();self.layout=audit.make_workspace(self.root,parent_scope='.')
        self.paths={'L0':self.root/'kit/base/registry.json','L1':self.root/'profiles/pilot/registry.json',
                    'L2':self.root/'.domain-agent-kit/project/registry.json'}
        self.docs={area:json.loads(path.read_bytes()) for area,path in self.paths.items()}
        e=audit.entry
        self.docs['L0']['entries'].append(e('SHARED','rule','system_release','S-1','.',text='system global'))
        self.docs['L1']['entries'] += [e('SHARED','rule','profile_owner','C-1','docs',text='profile docs'),
            e('DEEP','rule','profile_owner','C-1','docs/deep',text='profile deep'),
            e('DRAFT','rule','profile_owner','C-1','docs',state='draft'),
            e('SUSP','contract','profile_owner',None,'.',state='suspended'),
            e('CHILD','rule','profile_owner','SUSP','.',state='active')]
        self.docs['L2']['entries'].append(e('OTHER','rule','project_owner','P-1','docs2',text='other'))
        self.write()

    def write(self):
        for area,path in self.paths.items():audit.write(path,self.docs[area])

    def report(self,scope):return applicability.applicable(self.layout,scope=scope)
    def refs(self,result):return {(r['area'],r['entry']['id']) for r in result['entries']}

    def test_exact_scope_prefix_area_parent_status_and_source_fingerprints(self):
        before=audit.tree_digest(self.root);result=self.report('docs/deep/file.md')
        self.assertEqual(result['outcome'],'applicable')
        self.assertEqual(self.refs(result),{('L0','S-1'),('L0','SHARED'),('L1','C-1'),
                                           ('L1','SHARED'),('L1','DEEP'),('L2','P-1')})
        self.assertEqual(result['unstructured_active_entries'],3)
        self.assertEqual(result['coverage'],'selected_scope_only');self.assertEqual(result['text_conflicts'],'not_checked')
        for row in result['entries']:
            area=row['area'];self.assertEqual(row['source_sha256'],hashlib.sha256(self.paths[area].read_bytes()).hexdigest())
            self.assertEqual(row['source_version'],self.docs[area]['release_version'] if area=='L0' else 0)
        self.assertEqual(before,audit.tree_digest(self.root))
        self.assertEqual(self.report('docs')['outcome'],'applicable')
        self.assertNotIn(('L1','DEEP'),self.refs(self.report('docs')))
        self.assertNotIn(('L1','SHARED'),self.refs(self.report('docs2')))
        self.assertIn(('L2','OTHER'),self.refs(self.report('docs2/sub')))
        self.assertNotIn(('L1','SHARED'),self.refs(self.report('.')))
        self.assertEqual(result,self.report('docs/deep/file.md'))

    def test_active_conflict_returns_both_without_selected_winner(self):
        rows=self.docs['L1']['entries'];rows[1].update(key='style.requirement',value='one')
        self.docs['L2']['entries'].append(dict(audit.entry('CONFLICT','rule','project_owner','P-1','docs',
                                                          text='opposing'),key='style.requirement',value='two'))
        self.write();before=audit.tree_digest(self.root);result=self.report('docs/deep/file.md')
        self.assertEqual(result['outcome'],'structural_conflict');self.assertEqual(result['entries'],[])
        self.assertEqual({(e['area'],e['id'],e['value']) for e in result['conflicts'][0]['entries']},
                         {('L1','SHARED','one'),('L2','CONFLICT','two')})
        self.assertEqual(self.report('docs2/file')['outcome'],'applicable')
        self.assertEqual(before,audit.tree_digest(self.root))

    def test_scope_validation_and_inactive_text_conflict_is_not_semantically_checked(self):
        for scope in ('','/docs','docs//file','docs/../x','C:\\test',None,True):
            with self.subTest(scope=scope):
                with self.assertRaises(StoreError) as error:self.report(scope)
                self.assertEqual(error.exception.code,'scope_invalid')
        self.docs['L2']['entries'].append(audit.entry('CONTRARY','rule','project_owner','P-1','docs',text='contrary semantics'))
        self.write();result=self.report('docs/file')
        self.assertEqual(result['outcome'],'applicable');self.assertEqual(result['text_conflicts'],'not_checked')
        self.assertIn(('L2','CONTRARY'),self.refs(result))

    def test_no_active_entries_gives_empty_list(self):
        for doc in self.docs.values():doc['entries']=[]
        self.write();out=self.report('.')
        self.assertEqual(out['entries'],[]);self.assertEqual(out['unstructured_active_entries'],0)
        self.assertEqual(out['outcome'],'applicable')


if __name__=='__main__':unittest.main()
