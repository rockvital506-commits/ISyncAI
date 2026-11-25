#!/usr/bin/env python3
"""Исследовательские модельные пробы D08; всё состояние — только в памяти."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'research/audit')]
import core_audit as audit
import move_recovery_model as model
from kit.base import registry_journal, schema_v2


def wire(doc):return (json.dumps(doc,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()

class MoveRecoveryTests(unittest.TestCase):
    def setup_move(self,src):
        dst='L2' if src=='L1' else 'L1'
        docs={'L0':{'schema_version':2,'area':'L0','roots':['kit'],'release_version':'0.2.0-synthetic','entries':[]},
              'L1':{'schema_version':2,'area':'L1','roots':['profiles/pilot'],'revision':0,
                    'entries':[audit.entry('C-1','contract','profile_owner',None,'.')]},
              'L2':{'schema_version':2,'area':'L2','roots':['.domain-agent-kit'],'revision':0,
                    'entries':[audit.entry('P-1','contract','project_owner',None,'.')]}}
        parents={'L1':'C-1','L2':'P-1'};auth={'L1':'profile_owner','L2':'project_owner'}
        docs[src]['entries'].append(audit.entry('SOURCE','rule',auth[src],parents[src],'docs',state='active'))
        candidate=audit.entry('TARGET','rule',auth[dst],parents[dst],'docs',state='draft',text='explicit synthetic revision')
        inputs={k:wire(v) for k,v in docs.items()}
        args={'source':src,'target':dst,'entry_id':'SOURCE','candidate':candidate,
              'portability_context':{'project_names':[],'machine_names':[],'project_paths':[]} if src=='L2' else None}
        preview,intent=model.prepare(inputs,**args)
        return {'registries':copy.deepcopy(inputs),'intent':None},preview,intent
    def error_unchanged(self,code,state,func,*args,**kwargs):
        saved=copy.deepcopy(state)
        with self.assertRaisesRegex(model.ModelError,'^'+code+'$'):func(state,*args,**kwargs)
        self.assertEqual(state,saved)
    def test_crash_after_every_atomic_model_step_and_recovery_idempotent(self):
        for src in ('L1','L2'):
            for crash in range(3):
                with self.subTest(source=src,crash=crash):
                    state,preview,intent=self.setup_move(src);base=copy.deepcopy(state)
                    model.start(state,preview,intent,confirmed=True)
                    for _ in range(crash):model.advance(state)
                    interrupted=copy.deepcopy(state)  # Идеализированное сохранение, не процесс или ФС.
                    while model.advance(interrupted)!='complete_intent_retained':pass
                    self.assertEqual(model.advance(interrupted),'complete_intent_retained')
                    self.assertEqual(interrupted['registries']['L0'],base['registries']['L0'])
                    self.assertIsNotNone(interrupted['intent'])
                    for area in ('L1','L2'):
                        self.assertEqual(interrupted['registries'][area],intent['after'][area])
                        doc,journal=registry_journal.unpack_registry(schema_v2.parse_json(interrupted['registries'][area]),area=area)
                        ids={row['id'] for row in doc['entries']}
                        self.assertEqual('SOURCE' in ids,False);self.assertEqual('TARGET' in ids,area!=src)
                        self.assertEqual(journal['decisions'][-1]['operation'],'delete' if area==src else 'create')
    def test_confirmation_freshness_and_duplicate_pending(self):
        state,preview,intent=self.setup_move('L2')
        self.error_unchanged('confirmation_required',state,model.start,preview,intent,confirmed=False)
        changed=copy.deepcopy(preview);changed['source_entry']['text']='modified'
        self.error_unchanged('preview_mismatch',state,model.start,changed,intent,confirmed=True)
        state['registries']['L0']+=b' '
        self.error_unchanged('stale_inputs',state,model.start,preview,intent,confirmed=True)
        state['registries']=copy.deepcopy(intent['before']);model.start(state,preview,intent,confirmed=True)
        self.error_unchanged('pending_intent',state,model.start,preview,intent,confirmed=True)
    def test_foreign_bytes_on_any_area_stop_without_any_write(self):
        for src in ('L1','L2'):
            for phase in range(3):
                for area in ('L0','L1','L2'):
                    with self.subTest(source=src,phase=phase,area=area):
                        state,preview,intent=self.setup_move(src);model.start(state,preview,intent,confirmed=True)
                        for _ in range(phase):model.advance(state)
                        state['registries'][area]+=b'changed externally'
                        self.error_unchanged('foreign_state',state,model.advance)
    def test_impossible_order_and_tampered_intent_stop(self):
        state,preview,intent=self.setup_move('L1');model.start(state,preview,intent,confirmed=True)
        state['registries']['L1']=intent['after']['L1']
        self.error_unchanged('impossible_order',state,model.advance)
        state['registries']=copy.deepcopy(intent['before']);state['intent']['after']['L2']+=b'\n'
        self.error_unchanged('intent_invalid',state,model.advance)
        state['intent']=None;self.error_unchanged('intent_missing',state,model.advance)
    def test_regeneration_refuses_forged_after_but_does_not_authenticate_intent(self):
        state,preview,intent=self.setup_move('L1')
        payload=b'{"not":"a registry"}\n';intent['after']['L2']=payload
        for row in intent['preview']['diffs']:
            if row['area']=='L2':row['after_utf8']=payload.decode();row['after_sha256']=hashlib.sha256(payload).hexdigest()
        self.error_unchanged('intent_invalid',state,model.start,intent['preview'],intent,confirmed=True)
        # Подмена исходных байтов вместе с их новой полноценной моделью не может быть выявлена
        # локальным хешированием: у этих данных нет независимой подписи/канала подтверждения.
        state,preview,intent=self.setup_move('L1')
        docs=schema_v2.parse_json(state['registries']['L1']);docs['entries'][-1]['text']='foreign synthetic'
        state['registries']['L1']=wire(docs)
        candidate=preview['target_entry'];forged_preview,forged=model.prepare(state['registries'],source='L1',target='L2',entry_id='SOURCE',candidate=candidate)
        model.start(state,forged_preview,forged,confirmed=True)
        self.assertEqual(model.advance(state),'target_written')
    def test_partial_move_exposes_two_active_entries_without_reader_exclusion(self):
        state,preview,intent=self.setup_move('L1')
        candidate=dict(preview['target_entry'],state='active')
        preview,intent=model.prepare(state['registries'],source='L1',target='L2',entry_id='SOURCE',candidate=candidate)
        model.start(state,preview,intent,confirmed=True);self.assertEqual(model.advance(state),'target_written')
        src,_=registry_journal.unpack_registry(schema_v2.parse_json(state['registries']['L1']),area='L1')
        dst,_=registry_journal.unpack_registry(schema_v2.parse_json(state['registries']['L2']),area='L2')
        self.assertEqual(next(e for e in src['entries'] if e['id']=='SOURCE')['state'],'active')
        self.assertEqual(next(e for e in dst['entries'] if e['id']=='TARGET')['state'],'active')
        # Это наблюдаемое промежуточное состояние, а не безопасная атомарная публикация.

    def test_no_file_access_and_inputs_are_not_mutated(self):
        state,preview,intent=self.setup_move('L2');old=copy.deepcopy((preview,intent))
        with patch('builtins.open',side_effect=AssertionError('no I/O')), patch.object(Path,'open',side_effect=AssertionError('no I/O')):
            model.start(state,preview,intent,confirmed=True);model.advance(state);model.advance(state)
        self.assertEqual((preview,intent),old)

if __name__=='__main__':unittest.main()
