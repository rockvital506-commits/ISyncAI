#!/usr/bin/env python3
"""Гипотетическая политика, только синтетические bytes и без файловых операций."""
import copy
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'research/audit')]
import test_move_intent as fixtures
from kit.base import move_intent, move_recovery_plan
from kit.base.registry_policy import StoreError


class RecoveryPlanTests(unittest.TestCase):
    def test_states_both_directions_and_no_side_effects(self):
        for source in ('L1','L2'):
            before,args=fixtures.IntentTests().fixture(source)
            report,raw=move_intent.build(before,**args); pin=report['intent_sha256']
            after={r['area']:r['after_utf8'].encode() for r in report['preview']['diffs']}
            target=args['target']
            marker='verify_and_sync_marker_and_parent'; tgt='verify_and_sync_target_and_parent'; src='verify_and_sync_source_and_parent'
            cases=[(before,'before_both','target_replace',target,[marker]),
                   (dict(before,**{target:after[target]}),'target_after_source_before','source_replace',source,[marker,tgt]),
                   (dict(before,**after),'after_both','no_registry_replace',None,[marker,tgt,src]),
                   (dict(before,**{source:after[source]}),'impossible_order','stop',None,[])]
            for area in ('L0','L1','L2'):
                cases.append((dict(before,**{area:before[area]+b' '}),'foreign_or_changed','stop',None,[]))
            for observed,state,step,area,barriers in cases:
                with self.subTest(source=source,state=state,area=area):
                    saved=copy.deepcopy(observed)
                    with patch('builtins.open',side_effect=AssertionError('filesystem access')), patch.object(Path,'open',side_effect=AssertionError('filesystem access')), patch.object(os,'open',side_effect=AssertionError('filesystem access')):
                        result=move_recovery_plan.plan(raw,intent_pin=pin,observed=observed)
                    self.assertEqual(observed,saved)
                    self.assertEqual((result['state'],result['next_step'],result['area'],result['required_prior_barriers']),
                                     (state,step,area,barriers))
                    self.assertEqual(result['outcome'],'hypothetical_only')
                    self.assertEqual(result['marker'],'not_checked_or_removed')
                    for key in ('execution','recovery','confirmation'):self.assertEqual(result[key],'not_implemented')
                    self.assertEqual(result['authorization'],'not_checked')
    def test_rejects_wrong_pin_and_invalid_inputs(self):
        before,args=fixtures.IntentTests().fixture();report,raw=move_intent.build(before,**args)
        for pin,observed,code in [('0'*64,before,'move_intent_pin_mismatch'),
                                   (report['intent_sha256'],{},'move_observation_invalid'),
                                   (None,before,'move_intent_pin_required')]:
            with self.subTest(code=code),self.assertRaises(StoreError) as error:
                move_recovery_plan.plan(raw,intent_pin=pin,observed=observed)
            self.assertEqual(error.exception.code,code)

if __name__=='__main__':unittest.main()
