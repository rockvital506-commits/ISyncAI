#!/usr/bin/env python3
"""Синтетическая абстракция двух ячеек; реальные обновления и запись не выполняются."""
import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import checkpoint_rehearsal as model

A = model.Release(1, 'a'*64)
B = model.Release(2, 'b'*64)
C = model.Release(3, 'c'*64)


class CheckpointRehearsalTests(unittest.TestCase):
    def relation(self, checkpoint, active):
        return model.observe(model.State(checkpoint, active))['relation']

    def test_matching_is_observation_only(self):
        result = model.observe(model.State(A, A))
        self.assertEqual(result, {'relation':'matches_checkpoint',
            'checkpoint_trust':'assumed_not_verified', 'signature':'not_checked',
            'authorization':'not_checked', 'data_preservation':'not_checked',
            'execution':'not_implemented', 'recovery':'not_implemented'})

    def test_missing_and_conflicting_inputs_never_match(self):
        for checkpoint, active, expected in (
            (None,None,'both_missing'), (None,A,'checkpoint_missing'),
            (A,None,'active_missing'), (B,A,'active_behind'), (A,B,'active_ahead'),
            (A,model.Release(1,'b'*64),'same_sequence_conflict')):
            with self.subTest(expected=expected):
                self.assertEqual(self.relation(checkpoint, active), expected)

    def test_small_state_space_match_iff_both_pairs_equal(self):
        values = (None,A,B,C,model.Release(1,'f'*64))
        for checkpoint in values:
            for active in values:
                with self.subTest(checkpoint=checkpoint,active=active):
                    is_match = self.relation(checkpoint,active) == 'matches_checkpoint'
                    self.assertEqual(is_match, checkpoint is not None and checkpoint == active)

    def test_checkpoint_first_has_intermediate_unavailable_old_active(self):
        expected = [(A,A,'matches_checkpoint'), (B,A,'active_behind'), (B,B,'matches_checkpoint')]
        for steps, (checkpoint, active, relation) in enumerate(expected):
            state = model.simulate(A,B,order='checkpoint_first',completed_steps=steps)
            self.assertEqual((state.checkpoint,state.active),(checkpoint,active))
            self.assertEqual(model.observe(state)['relation'], relation)
        # Подставленный старый объект не совпадает с предполагаемо защищённым новым checkpoint.
        self.assertEqual(self.relation(B,A),'active_behind')

    def test_active_first_has_intermediate_ahead_and_old_still_matches_old_checkpoint(self):
        expected = [(A,A,'matches_checkpoint'), (A,B,'active_ahead'), (B,B,'matches_checkpoint')]
        for steps, (checkpoint, active, relation) in enumerate(expected):
            state = model.simulate(A,B,order='active_first',completed_steps=steps)
            self.assertEqual((state.checkpoint,state.active),(checkpoint,active))
            self.assertEqual(model.observe(state)['relation'], relation)
        # Замена активной ячейки старым объектом после промежуточного шага даёт прежнюю пару.
        interrupted = model.simulate(A,B,order='active_first',completed_steps=1)
        reverted_active = model.State(interrupted.checkpoint,A)
        self.assertEqual(reverted_active,model.State(A,A))
        self.assertEqual(model.observe(reverted_active)['relation'],'matches_checkpoint')

    def test_restored_old_checkpoint_makes_rollback_indistinguishable(self):
        initial = model.State(A,A)
        completed = model.simulate(A,B,order='checkpoint_first',completed_steps=2)
        # Гипотетическая подмена обеих ячеек: восстановление checkpoint не предотвращается моделью.
        replayed = model.State(initial.checkpoint,initial.active)
        self.assertNotEqual(completed, replayed)
        self.assertEqual(initial, replayed)
        self.assertEqual(model.observe(initial), model.observe(replayed))
        self.assertEqual(model.observe(replayed)['checkpoint_trust'], 'assumed_not_verified')

    def test_same_number_different_digest_refused_even_after_forward_transition(self):
        alt = model.Release(2,'f'*64)
        done = model.simulate(A,B,order='active_first',completed_steps=2)
        self.assertEqual(self.relation(done.checkpoint,alt),'same_sequence_conflict')
        self.assertEqual(self.relation(alt,done.active),'same_sequence_conflict')

    def test_order_and_boundaries_for_multiple_successive_sequences(self):
        for old, new in ((A,B),(B,C),(A,C)):
            for order in ('checkpoint_first','active_first'):
                with self.subTest(old=old.sequence, new=new.sequence, order=order):
                    self.assertEqual(model.simulate(old,new,order=order,completed_steps=0),model.State(old,old))
                    self.assertEqual(model.simulate(old,new,order=order,completed_steps=2),model.State(new,new))
                    intermediate = model.simulate(old,new,order=order,completed_steps=1)
                    self.assertNotEqual(intermediate.checkpoint,intermediate.active)
                    self.assertNotEqual(model.observe(intermediate)['relation'],'matches_checkpoint')

    def test_sequence_is_not_a_version_or_proof_of_a_newer_safe_release(self):
        same_digest = model.Release(2,A.digest)
        self.assertEqual(self.relation(A,same_digest),'active_ahead')
        self.assertEqual(self.relation(same_digest,A),'active_behind')
        # Даже бо́льший номер и совпадающие ячейки не дают сведений о подписи и правах.
        result = model.observe(model.State(C,C))
        self.assertEqual(result['signature'],'not_checked')
        self.assertEqual(result['authorization'],'not_checked')

    def test_invalid_release_and_state_rejected(self):
        for seq, digest in ((True,'a'*64),(0,'a'*64),(-1,'a'*64),(2**63,'a'*64),
                            ('1','a'*64),(1,'A'*64),(1,'a'*63),(1,None)):
            with self.subTest(sequence=seq,digest=digest):
                with self.assertRaisesRegex(ValueError,'release_invalid'):
                    model.Release(seq,digest)
        for x,y in (({},A),(A,'b'),(A,True)):
            with self.assertRaisesRegex(ValueError,'state_invalid'): model.State(x,y)
        with self.assertRaisesRegex(ValueError,'state_invalid'): model.observe({})

    def test_invalid_transition_and_cut_rejected(self):
        for old,new in ((B,A),(A,A),(None,A),(A,None)):
            with self.subTest(old=old,new=new):
                with self.assertRaisesRegex(ValueError,'transition_invalid'):
                    model.simulate(old,new,order='checkpoint_first',completed_steps=0)
        for order in (None, 'both', 'active-first'):
            with self.assertRaisesRegex(ValueError,'order_invalid'):
                model.simulate(A,B,order=order,completed_steps=0)
        for steps in (-1,3,True,1.0,None):
            with self.assertRaisesRegex(ValueError,'cut_invalid'):
                model.simulate(A,B,order='active_first',completed_steps=steps)

    def test_immutable_and_no_selected_filesystem_or_process_calls(self):
        with self.assertRaises(FrozenInstanceError): A.sequence=2
        with self.assertRaises(FrozenInstanceError): model.State(A,A).active=B
        with patch('builtins.open',side_effect=AssertionError('filesystem')), \
             patch.object(Path,'open',side_effect=AssertionError('filesystem')), \
             patch('os.open',side_effect=AssertionError('filesystem')), \
             patch('os.stat',side_effect=AssertionError('filesystem')), \
             patch('subprocess.run',side_effect=AssertionError('process')):
            state = model.simulate(A,B,order='checkpoint_first',completed_steps=1)
            self.assertEqual(model.observe(state)['relation'],'active_behind')


if __name__ == '__main__':
    unittest.main()
