#!/usr/bin/env python3
"""Барьер стадии L1: синтетические каталоги, без автоматической очистки."""
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'research/audit')]
import core_audit as audit
import test_profile_copy as fixtures
from kit import move_recovery_inspect, move_partial_cancel
from kit.base import move_intent, operation_card, operation_plan, registry_store as store
from kit.base.registry_policy import StoreError
from kit.move_reservation import ReservationSession


@unittest.skipUnless(fixtures.atomic_tests.SUPPORTED and store.fcntl is not None,'POSIX/Linux unavailable; not_run')
class CopyPendingTests(unittest.TestCase):
    def setUp(self):
        self.ctx=fixtures.ProfileCopyTests();self.ctx.setUp();self.addCleanup(self.ctx.doCleanups)
        self.profile=self.ctx.a1.parent
    def error(self,code,fn,*args,**kw):
        with self.assertRaises(StoreError) as err:fn(*args,**kw)
        self.assertEqual(err.exception.code,code)
    def test_file_directory_symlink_and_arbitrary_prefix_block_without_mutation(self):
        for kind in ('file','directory','symlink','broken'):
            with self.subTest(kind=kind):
                name=self.profile/('.profile-copy-stage-'+kind)
                if kind=='file':name.write_bytes(b'synthetic')
                elif kind=='directory':name.mkdir()
                elif kind=='symlink':name.symlink_to(self.ctx.a1)
                else:name.symlink_to(self.profile/'missing')
                before=audit.tree_digest(self.ctx.root)
                self.error('profile_copy_pending',store.status,self.ctx.a)
                self.error('profile_copy_pending',self.ctx.session().plan)
                self.assertEqual(before,audit.tree_digest(self.ctx.root))
                if kind=='directory':name.rmdir()
                else:name.unlink()  # Удаляется только созданная тестом временная фикстура.
        self.assertIsInstance(store.status(self.ctx.a),dict)
    def test_preplanned_operation_revoked_and_cannot_write(self):
        session=operation_plan.PlanSession(self.ctx.a,profile_id='Pilot')
        phrase='Создай черновик контракта C-10 в профиле Pilot, постоянное, область «docs», название «Пример», основание «Проба», критерий «Запись существует»: Проба.'
        p=session.plan(operation_card.compile_prompt(phrase));self.assertEqual(p['outcome'],'planned')
        stage=self.profile/'.profile-copy-stage-an-unknown-object';stage.write_bytes(b'preserve')
        before=audit.tree_digest(self.ctx.root)
        self.error('profile_copy_pending',session.apply,p,confirmed_ticket=p['ticket'])
        self.error('ticket_unknown',session.apply,p,confirmed_ticket=p['ticket'])
        self.assertEqual(before,audit.tree_digest(self.ctx.root));self.assertEqual(stage.read_bytes(),b'preserve')
    def test_unavailable_listing_fails_closed(self):
        with patch.object(store.os,'listdir',side_effect=PermissionError('synthetic')):
            self.error('profile_copy_state_unavailable',store.status,self.ctx.a)
        self.assertIsInstance(store.status(self.ctx.a),dict)
    def test_full_and_partial_move_diagnostics_respect_barrier(self):
        raw=store._load(self.ctx.a).raw
        candidate=audit.entry('TARGET','contract','project_owner',None,'docs',state='draft')
        report,intent=move_intent.build(raw,source='L1',target='L2',entry_id='C-9',candidate=candidate,portability_context=None)
        pin=report['intent_sha256'];session=ReservationSession(layout=self.ctx.a,intent_bytes=intent,intent_pin=pin)
        p=session.plan(action='reserve');session.apply(p,confirmed_ticket=p['ticket'])
        marker=self.ctx.a.workspace/'.domain-agent-kit/.move-pending'
        stage=self.profile/'.profile-copy-stage-synthetic';stage.write_bytes(b'preserve')
        before=audit.tree_digest(self.ctx.root)
        self.error('profile_copy_pending',move_recovery_inspect.inspect,self.ctx.a,intent_pin=pin)
        self.assertEqual(before,audit.tree_digest(self.ctx.root));self.assertTrue(marker.exists())
        marker.write_bytes(intent[:5]);before=audit.tree_digest(self.ctx.root)
        partial=move_partial_cancel.PartialReservationCancelSession(self.ctx.a,intent_bytes=intent,intent_pin=pin)
        self.error('profile_copy_pending',partial.plan)
        self.assertEqual(before,audit.tree_digest(self.ctx.root));self.assertEqual(stage.read_bytes(),b'preserve')

if __name__=='__main__':unittest.main()
