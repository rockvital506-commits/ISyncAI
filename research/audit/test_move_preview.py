#!/usr/bin/env python3
"""Двухсторонний гипотетический diff в памяти, не испытание выполнения переноса."""
import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'research/audit')]
import core_audit as audit
from kit.base import move_preview as move, registry_journal, schema_v2
from kit.base.registry_policy import StoreError


def wire(value):return (json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()


class MovePreviewTests(unittest.TestCase):
    def setUp(self):
        self.l0={'schema_version':2,'area':'L0','roots':['kit'],'release_version':'0.2.0-synthetic','entries':[]}
        self.l1={'schema_version':2,'area':'L1','roots':['profiles/pilot'],'revision':0,
                 'entries':[audit.entry('C-1','contract','profile_owner',None,'.')]}
        self.l2={'schema_version':2,'area':'L2','roots':['.domain-agent-kit'],'revision':0,
                 'entries':[audit.entry('P-1','contract','project_owner',None,'.')]}
        self.context={'project_names':[],'machine_names':[],'project_paths':[]}

    def inputs(self):return {area:wire(doc) for area,doc in (('L0',self.l0),('L1',self.l1),('L2',self.l2))}
    def entry(self,area,id,parent,**kwargs):
        return audit.entry(id,'rule',{'L1':'profile_owner','L2':'project_owner'}[area],parent,'docs',**kwargs)
    def error(self,code,inputs,**kwargs):
        with self.assertRaises(StoreError) as err:move.preview_move(inputs,**kwargs)
        self.assertEqual(err.exception.code,code)

    def test_both_directions_exact_diff_and_history_without_io(self):
        for src,dst,sp,tp in (('L1','L2','C-1','P-1'),('L2','L1','P-1','C-1')):
            with self.subTest(source=src):
                self.setUp();original=self.entry(src,'X-1',sp,state='active');getattr(self,src.lower())['entries'].append(original)
                candidate=self.entry(dst,'X-2',tp,state='draft',text='Explicitly revised synthetic text')
                inputs=self.inputs();snapshot=copy.deepcopy(inputs);copy_candidate=copy.deepcopy(candidate)
                args={'source':src,'target':dst,'entry_id':'X-1','candidate':candidate,
                      'portability_context':self.context if src=='L2' else None}
                with patch('builtins.open',side_effect=AssertionError('no file access')), \
                     patch.object(Path,'open',side_effect=AssertionError('no file access')):
                    plan=move.preview_move(inputs,**args);again=move.preview_move(inputs,**args)
                self.assertEqual(plan,again);self.assertEqual(inputs,snapshot);self.assertEqual(candidate,copy_candidate)
                self.assertEqual((plan['outcome'],plan['apply'],plan['confirmation'],plan['recovery']),
                                 ('hypothetical_only','not_implemented','not_implemented','not_implemented'))
                self.assertNotIn('ticket',plan)
                self.assertEqual(plan['changes']['id'],{'before':'X-1','after':'X-2'})
                self.assertEqual(plan['changes']['state'],{'before':'active','after':'draft'})
                self.assertEqual(plan['inputs_sha256'],{k:hashlib.sha256(v).hexdigest() for k,v in inputs.items()})
                by_area={d['area']:d for d in plan['diffs']}
                for area in (src,dst):
                    row=by_area[area]; raw=row['after_utf8'].encode()
                    self.assertEqual(row['before_sha256'],hashlib.sha256(inputs[area]).hexdigest())
                    self.assertEqual(row['after_sha256'],hashlib.sha256(raw).hexdigest())
                    self.assertEqual(row['revision'],{'from':0,'to':1})
                    self.assertIn('--- a/'+area,row['unified']);self.assertIn('+++ b/'+area,row['unified'])
                    doc,journal=registry_journal.unpack_registry(schema_v2.parse_json(raw),area=area)
                    self.assertEqual(journal['decisions'][-1],row['hypothetical_decision'])
                    self.assertEqual(row['hypothetical_decision']['operation'],'delete' if area==src else 'create')
                    self.assertEqual(any(e['id']==('X-1' if area==src else 'X-2') for e in doc['entries']),area==dst)
                self.assertEqual(plan['source_entry'],original);self.assertEqual(plan['target_entry'],candidate)
                self.assertEqual(plan['structural_effectiveness'],{'source_before':True,'target_after':False})
                self.assertEqual(plan['source_parent']['id'],sp);self.assertEqual(plan['target_parent']['id'],tp)

    def test_wrong_inputs_direction_candidate_and_children(self):
        self.l2['entries'].append(self.entry('L2','X-1','P-1'))
        inputs=self.inputs();candidate=self.entry('L1','X-2','C-1')
        opts={'source':'L2','target':'L1','entry_id':'X-1','candidate':candidate,'portability_context':self.context}
        self.error('move_direction_invalid',inputs,**dict(opts,target='L0'))
        self.error('move_direction_invalid',inputs,**dict(opts,target='L2'))
        self.error('entry_id_invalid',inputs,**dict(opts,entry_id='../bad'))
        self.error('entry_not_found',inputs,**dict(opts,entry_id='MISSING'))
        self.error('invalid_inputs',dict(inputs,L3=b''),**opts)
        broken=dict(inputs,L1=b'not json');self.error('invalid_registry',broken,**opts)
        wrong=dict(candidate,authority='project_owner');self.error('invalid_entry',inputs,**dict(opts,candidate=wrong))
        oversized=dict(candidate,text='x'*(move.MAX_CANDIDATE+1));self.error('invalid_entry',inputs,**dict(opts,candidate=oversized))
        wrong=audit.entry('X-2','protocol','profile_owner','C-1','docs')
        self.error('kind_change_forbidden',inputs,**dict(opts,candidate=wrong))
        missing=dict(candidate,parent='ABSENT');self.error('invalid_result',inputs,**dict(opts,candidate=missing))
        self.error('invalid_context',inputs,**dict(opts,portability_context=None))
        marked=dict(candidate,text='Use /home/synthetic/project');self.error('project_specific',inputs,**dict(opts,candidate=marked))
        # Нельзя удалить контракт с оставляемыми дочерними сущностями.
        self.error('source_has_children',inputs,**dict(opts,entry_id='P-1',candidate=audit.entry('X-3','contract','profile_owner',None,'.')))
        self.assertEqual(inputs,self.inputs())

    def test_target_id_occupied_or_retired(self):
        self.l2['entries'].append(self.entry('L2','X-1','P-1'))
        self.l1['entries'].append(self.entry('L1','X-2','C-1'))
        candidate=self.entry('L1','X-2','C-1');opts={'source':'L2','target':'L1','entry_id':'X-1',
                                                   'candidate':candidate,'portability_context':self.context}
        self.error('target_id_unavailable',self.inputs(),**opts)
        prior=copy.deepcopy(self.l1);deleted=prior['entries'][-1]
        after=dict(prior,entries=prior['entries'][:-1],revision=1)
        pack=registry_journal.with_change(after,prior,{'base_revision':0,'decisions':[]},
                                          operation='delete',before=deleted,after=None)
        inputs=self.inputs();inputs['L1']=wire(pack)
        self.error('target_id_unavailable',inputs,**opts)

    def test_structural_conflict_before_and_after_is_not_resolved(self):
        self.l2['entries'].append(dict(self.entry('L2','X-1','P-1',state='active'),key='build.style',value='A'))
        existing=dict(self.entry('L1','E-1','C-1',state='active'),key='build.style',value='B')
        self.l1['entries'].append(existing)
        candidate=dict(self.entry('L1','X-2','C-1',state='active'),key='build.style',value='A')
        opts={'source':'L2','target':'L1','entry_id':'X-1','candidate':candidate,'portability_context':self.context}
        self.error('rule_conflict',self.inputs(),**opts)
        self.l2['entries'][-1]['state']='draft'
        self.error('rule_conflict',self.inputs(),**opts)
        candidate['state']='draft';plan=move.preview_move(self.inputs(),**opts)
        self.assertEqual(plan['text_conflicts'],'not_checked')

    def test_retains_existing_journal_history(self):
        original=self.entry('L2','X-1','P-1');prior=copy.deepcopy(self.l2)
        after=dict(prior,entries=prior['entries']+[original],revision=1)
        pack=registry_journal.with_change(after,prior,{'base_revision':0,'decisions':[]},
                                          operation='create',before=None,after=original)
        inputs=self.inputs();inputs['L2']=wire(pack)
        plan=move.preview_move(inputs,source='L2',target='L1',entry_id='X-1',
                               candidate=self.entry('L1','X-1','C-1'),portability_context=self.context)
        row=plan['diffs'][0];doc,journal=registry_journal.unpack_registry(schema_v2.parse_json(row['after_utf8']),area='L2')
        self.assertEqual(journal['decisions'][:-1],pack['journal']['decisions'])
        self.assertEqual(journal['decisions'][-1]['operation'],'delete');self.assertEqual(doc['revision'],2)
        self.assertTrue(registry_journal.is_retired(journal,'X-1'))


if __name__=='__main__':unittest.main()
