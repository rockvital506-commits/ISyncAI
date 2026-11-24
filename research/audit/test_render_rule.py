#!/usr/bin/env python3
"""Проверка чистого преобразования: только синтетические реестры в памяти."""
import copy
import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'research/audit'))
from core_audit import entry
from kit.render_rule import render, RenderError
from kit.base.profile_journal import canonical_bytes


def fixture():
    return {
        'L0': {'schema_version':2,'area':'L0','roots':['kit'],'release_version':'0.2.0-mvp.2',
               'entries':[entry('S-1','contract','system_release',None,'.')]},
        'L1': {'schema_version':2,'area':'L1','roots':['profiles/pilot'],'revision':3,
               'entries':[entry('C-1','contract','profile_owner',None,'.'),
                          entry('R-1','rule','profile_owner','C-1','.',text='Проверяй перед записью.')]},
        'L2': {'schema_version':2,'area':'L2','roots':['.agent-contract'],'revision':7,
               'entries':[entry('P-1','contract','project_owner',None,'.'),
                          entry('Q-1','protocol','project_owner','P-1','.',text='Проверь проект.')]},
    }


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.data = fixture()

    def test_deterministic_source_and_no_mutation(self):
        before = copy.deepcopy(self.data)
        out = render(self.data, area='L1', entry_id='R-1')
        self.assertEqual(out, render(self.data, area='L1', entry_id='R-1'))
        self.assertEqual(self.data, before)
        row = self.data['L1']['entries'][1]
        fingerprint = hashlib.sha256(canonical_bytes(row)).hexdigest()
        self.assertIn(fingerprint.encode(), out)
        self.assertTrue(out.endswith((row['text'] + '\n').encode()))
        self.assertIn(b'area=L1 id=R-1 revision=3', out)

    def test_l2_and_identity(self):
        out = render(self.data, area='L2', entry_id='Q-1')
        self.assertIn(b'area=L2 id=Q-1 revision=7', out)
        self.assertIn('Проверь проект.'.encode(), out)

    def test_draft_and_inactive_parent_rejected(self):
        self.data['L1']['entries'][1]['state'] = 'draft'
        with self.assertRaises(RenderError): render(self.data, area='L1', entry_id='R-1')
        self.data['L1']['entries'][1]['state'] = 'active'
        self.data['L1']['entries'][0]['state'] = 'suspended'
        with self.assertRaises(RenderError): render(self.data, area='L1', entry_id='R-1')

    def test_narrow_scope_rejected(self):
        self.data['L1']['entries'][1]['scope'] = 'docs'
        with self.assertRaises(RenderError): render(self.data, area='L1', entry_id='R-1')

    def test_conflicting_key_value_rejected(self):
        self.data['L1']['entries'][1].update(key='example', value='a')
        self.data['L2']['entries'][1].update(key='example', value='b')
        with self.assertRaises(RenderError): render(self.data, area='L1', entry_id='R-1')

    def test_missing_invalid_and_l0_rejected(self):
        for area, ident in (('L0','S-1'),('L1','unknown'),('L1','C-1')):
            with self.subTest(area=area, ident=ident), self.assertRaises(RenderError):
                render(self.data, area=area, entry_id=ident)
        del self.data['L2']
        with self.assertRaises(RenderError): render(self.data, area='L1', entry_id='R-1')

    def test_control_char_and_length_rejected(self):
        self.data['L1']['entries'][1]['title'] = 'подмена\n# другое'
        with self.assertRaises(RenderError): render(self.data, area='L1', entry_id='R-1')
        self.data['L1']['entries'][1]['title'] = 'Название'
        self.data['L1']['entries'][1]['text'] = 'x' * 16385
        with self.assertRaises(RenderError): render(self.data, area='L1', entry_id='R-1')

    def test_cli_success_and_error(self):
        payload={'catalog':self.data,'area':'L1','entry_id':'R-1'}
        p=subprocess.run([sys.executable,'-B',str(ROOT/'kit/render_rule.py')],
                         input=json.dumps(payload,ensure_ascii=False).encode(),capture_output=True,check=True)
        self.assertEqual(p.stdout,render(self.data,area='L1',entry_id='R-1'))
        p=subprocess.run([sys.executable,'-B',str(ROOT/'kit/render_rule.py')],input=b'{"area":1,"area":2}',capture_output=True)
        self.assertNotEqual(p.returncode,0)
        self.assertEqual(p.stdout,b'')


if __name__ == '__main__': unittest.main()
