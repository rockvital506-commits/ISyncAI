#!/usr/bin/env python3
"""Проверки локальной трассировки L0-кандидата, не независимое ревью."""
import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'research/audit')]
import l0_candidate_audit as audit
from kit.base import schema_v2


def wire(doc):return (json.dumps(doc,ensure_ascii=False,indent=2,sort_keys=True)+'\n').encode()


class CandidateL0Tests(unittest.TestCase):
    def setUp(self):
        self.proposal=schema_v2.parse_json((ROOT/'research/kilo/l0-proposal/DRAFT.json').read_bytes())
        self.road=(ROOT/'research/kilo/ROADMAP.md').read_bytes()
        self.manifest=(ROOT/'kit/KIT-VERSION.json').read_bytes()
        self.system=(ROOT/'kit/SYSTEM-L0.json').read_bytes()

    def check(self,proposal=None,road=None,manifest=None,system=None):
        return audit.check(self.proposal if proposal is None else proposal,self.road if road is None else road,
                           self.manifest if manifest is None else manifest,self.system if system is None else system)

    def test_candidate_exact_projection_with_no_independent_claim(self):
        result=self.check()
        self.assertEqual((result['entries'],result['active_entries']),(10,10))
        self.assertEqual((result['semantic_review'],result['independent_review'],result['independent_origin']),
                         ('author_only','not_run','not_verified'))
        self.assertTrue(all(e['state']=='draft' for e in self.proposal['registry']['entries']))
        self.assertTrue(all(e['state']=='active' for e in schema_v2.parse_json(self.system)['entries']))

    def test_changed_roadmap_manifest_or_system_fail(self):
        for which in ('road','manifest','system'):
            with self.subTest(which=which):
                args={which:getattr(self,which)+b' '}
                with self.assertRaises(audit.CandidateError):self.check(**args)

    def test_changed_projection_repin_does_not_hide_projection_drift(self):
        for change in ('text','state','missing','version'):
            with self.subTest(change=change):
                doc=schema_v2.parse_json(self.system)
                if change=='text':doc['entries'][0]['text']='Противоречащий синтетический текст'
                if change=='state':doc['entries'][1]['state']='draft'
                if change=='missing':doc['entries'].pop()
                if change=='version':doc['release_version']='0.2.0-invalid'
                raw=wire(doc);manifest=schema_v2.parse_json(self.manifest)
                manifest['files']['kit/SYSTEM-L0.json']=hashlib.sha256(raw).hexdigest()
                # Даже при переподтверждении обеих локальных привязок сравнение с draft откажет.
                mraw=wire(manifest);proposal=copy.deepcopy(self.proposal)
                proposal['candidate_manifest_sha256']=hashlib.sha256(mraw).hexdigest()
                with self.assertRaises(audit.CandidateError):self.check(proposal=proposal,manifest=mraw,system=raw)

    def test_coordinated_source_and_projection_text_changes_can_pass_mechanical_check(self):
        proposal=copy.deepcopy(self.proposal)
        proposal['registry']['entries'][0]['text']='Синтетическая противоположная формулировка'
        doc=schema_v2.parse_json(self.system)
        doc['entries'][0]['text']=proposal['registry']['entries'][0]['text']
        raw=wire(doc);manifest=schema_v2.parse_json(self.manifest)
        manifest['files']['kit/SYSTEM-L0.json']=hashlib.sha256(raw).hexdigest()
        mraw=wire(manifest);proposal['candidate_manifest_sha256']=hashlib.sha256(mraw).hexdigest()
        result=self.check(proposal=proposal,manifest=mraw,system=raw)
        self.assertEqual(result['outcome'],'local_candidate_shape_pass')
        self.assertEqual(result['independent_review'],'not_run')


if __name__=='__main__':unittest.main()
