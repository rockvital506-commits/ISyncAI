#!/usr/bin/env python3
"""Ограниченная подготовка контекстов; не оценка применения живым агентом."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'research/audit')]
import core_audit as audit
from kit.base import context_modes
from kit.base.registry_policy import StoreError


def ref(area,id):return {'area':area,'id':id}


class ContextTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='domain-context-');self.addCleanup(temp.cleanup)
        self.root=Path(temp.name).resolve();self.layout=audit.make_workspace(self.root,parent_scope='.')
        self.paths={'L0':self.root/'kit/base/registry.json','L1':self.root/'profiles/pilot/registry.json',
                    'L2':self.root/'.domain-agent-kit/project/registry.json'}
        self.paths['L0'].write_bytes((ROOT/'kit/SYSTEM-L0.json').read_bytes())
        self.docs={a:json.loads(p.read_bytes()) for a,p in self.paths.items()}
        self.docs['L1']['entries'] += [audit.entry('IN','rule','profile_owner','C-1','docs',text='NEEDED_PROFILE'),
            audit.entry('OUT','rule','profile_owner','C-1','docs',text='EXCLUDED_PROFILE_SECRET'),
            audit.entry('SAFETY','constraint','profile_owner','C-1','docs',text='MANDATORY_PROFILE'),
            audit.entry('OFF','rule','profile_owner','C-1','docs',state='draft')]
        self.docs['L2']['entries'] += [audit.entry('PIN','protocol','project_owner','P-1','docs',text='MANDATORY_PROJECT'),
            audit.entry('OUT','preference','project_owner','P-1','docs',text='EXCLUDED_PROJECT_SECRET'),
            audit.entry('ELSE','rule','project_owner','P-1','docs2',text='NOT_FOR_THIS_SCOPE')]
        for a in ('L1','L2'):audit.write(self.paths[a],self.docs[a])
        self.choices={'include':[ref('L1','C-1'),ref('L1','IN'),ref('L1','SAFETY'),
                                 ref('L2','P-1'),ref('L2','PIN')],
                      'exclude':[ref('L1','OUT'),ref('L2','OUT')]}

    def get(self,mode='project',scope='docs/file',choices=None):
        return context_modes.prepare(self.layout,mode=mode,scope=scope,choices=self.choices if choices is None else choices)
    def error(self,code,**kwargs):
        with self.assertRaises(StoreError) as error:self.get(**kwargs)
        self.assertEqual(error.exception.code,code)
    def references(self,result):return {(r['area'],r['entry']['id']) for r in result['entries']}

    def test_modes_explicit_selection_preserve_mandatory_and_no_excluded_text(self):
        before=audit.tree_digest(self.root);p=self.get();k=self.get(mode='kit')
        self.assertEqual((p['outcome'],k['outcome']),('review_required','review_required'))
        self.assertEqual((p['mode'],k['mode']),('project','kit'))
        self.assertIn(('L0','SYS-PROJECT-MODE'),self.references(p))
        self.assertNotIn(('L0','SYS-KIT-MODE'),self.references(p))
        self.assertIn(('L0','SYS-KIT-MODE'),self.references(k))
        self.assertNotIn(('L0','SYS-PROJECT-MODE'),self.references(k))
        for result in (p,k):
            self.assertTrue({('L1','SAFETY'),('L2','PIN'),('L1','IN')} <= self.references(result))
            self.assertEqual(result['excluded_count'],2)
            self.assertNotIn('EXCLUDED_PROFILE_SECRET',repr(result));self.assertNotIn('EXCLUDED_PROJECT_SECRET',repr(result))
            self.assertNotIn('NOT_FOR_THIS_SCOPE',repr(result))
            for flag in ('safety_completeness','minimality','scope_completeness','text_conflicts','agent_application'):
                self.assertEqual(result[flag],'not_checked')
            self.assertEqual(result['delivery'],'not_implemented')
        self.assertEqual(before,audit.tree_digest(self.root));self.assertEqual(p,self.get())

    def test_wrong_incomplete_duplicate_unavailable_and_malformed_choices_refuse(self):
        self.error('context_mode_invalid',mode='other')
        self.error('scope_invalid',scope='../bad')
        self.error('context_choices_invalid',choices={})
        self.error('context_choices_invalid',choices={'include':[ref('L0','SYS-CONTRACT')],'exclude':[]})
        self.error('context_choices_invalid',choices={'include':[ref('L1','IN')], 'exclude':[ref('L1','IN')]})
        self.error('context_choices_incomplete',choices={'include':self.choices['include'], 'exclude':[]})
        self.error('context_choices_incomplete',choices={'include':self.choices['include']+[ref('L2','ELSE')],
                                                         'exclude':self.choices['exclude']})
        self.error('context_choices_incomplete',choices={'include':self.choices['include']+[ref('L1','OFF')],
                                                         'exclude':self.choices['exclude']})

    def test_mandatory_excluded_and_required_parent_excluded_refused(self):
        c={'include':[r for r in self.choices['include'] if r!=ref('L1','SAFETY')],
           'exclude':self.choices['exclude']+[ref('L1','SAFETY')]}
        self.error('context_mandatory_excluded',choices=c)
        c={'include':[r for r in self.choices['include'] if r!=ref('L1','C-1')],
           'exclude':self.choices['exclude']+[ref('L1','C-1')]}
        self.error('context_parent_excluded',choices=c)

    def test_changed_or_empty_l0_is_not_accepted_even_with_schema(self):
        l0=self.docs['L0'];l0['entries'][0]['text']+=' changed';audit.write(self.paths['L0'],l0)
        self.error('context_system_unbound')
        l0['entries']=[];audit.write(self.paths['L0'],l0);self.error('context_system_unbound')

    def test_unstructured_safety_rule_can_be_excluded_never_claim_safety(self):
        row=next(x for x in self.docs['L1']['entries'] if x['id']=='OUT')
        row['text']='SYNTHETIC_SAFETY_RULE_DO_NOT_DELETE_DATA'
        audit.write(self.paths['L1'],self.docs['L1'])
        result=self.get()
        self.assertNotIn('SYNTHETIC_SAFETY_RULE_DO_NOT_DELETE_DATA',repr(result))
        self.assertEqual(result['outcome'],'review_required')
        self.assertEqual(result['safety_completeness'],'not_checked')
        self.assertEqual(result['delivery'],'not_implemented')

    def test_structural_conflict_is_not_resolved(self):
        self.docs['L1']['entries'][1].update(key='test.key',value='a')
        self.docs['L2']['entries'][2].update(key='test.key',value='b')
        audit.write(self.paths['L1'],self.docs['L1']);audit.write(self.paths['L2'],self.docs['L2'])
        self.error('context_conflict')


if __name__=='__main__':unittest.main()
