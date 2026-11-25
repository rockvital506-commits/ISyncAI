#!/usr/bin/env python3
"""Черновик L0 и явные пределы guard; только синтетические временные раскладки."""
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'research/audit')]
import core_audit as fixture
import l0_proposal_audit as audit
from kit.base import registry_policy, schema_v2
from kit.base.operation_card import compile_prompt
from kit.base.operation_plan import PlanSession
from kit.base.registry_store import Layout, StoreError
from kit.guard import guard
from kit.render_rule import render, RenderError


class L0ProposalTests(unittest.TestCase):
    def setUp(self):
        self.road = (ROOT/'research/kilo/ROADMAP.md').read_bytes()
        self.manifest = (ROOT/'kit/KIT-VERSION.json').read_bytes()
        self.proposal = schema_v2.parse_json((ROOT/'research/kilo/l0-proposal/DRAFT.json').read_bytes())

    def check(self, proposal=None, road=None, manifest=None):
        return audit.check(self.proposal if proposal is None else proposal,
                           self.road if road is None else road,
                           self.manifest if manifest is None else manifest)

    def invalid(self, data, reason):
        with self.assertRaises(audit.AuditError) as error:
            self.check(data)
        self.assertEqual(str(error.exception), reason)

    def test_shape_trace_and_no_active_rules(self):
        self.assertEqual(self.check(), {'outcome':'draft_shape_pass', 'entries':10, 'active_entries':0,
                                         'semantic_review':'not_run', 'independent_origin':'not_verified'})
        registry = self.proposal['registry']
        self.assertEqual(registry_policy.active_entries(registry), [])
        self.assertTrue(all(row['state'] == 'draft' for row in registry['entries']))
        manifest = json.loads(self.manifest)
        self.assertNotIn('kit/base/registry.json', manifest['files'])
        self.assertNotIn('research/kilo/l0-proposal/DRAFT.json', manifest['files'])

    def test_rejects_activation_missing_records_and_invalid_relations(self):
        changed = copy.deepcopy(self.proposal); changed['registry']['entries'][0]['state'] = 'active'
        self.invalid(changed, 'draft_entry_invalid')
        changed = copy.deepcopy(self.proposal); changed['registry']['entries'].pop()
        self.invalid(changed, 'draft_coverage')
        changed = copy.deepcopy(self.proposal); changed['registry']['entries'][1]['parent'] = 'absent'
        self.invalid(changed, 'registry_or_source_invalid')
        changed = copy.deepcopy(self.proposal); changed['registry']['entries'][1]['authority'] = 'profile_owner'
        self.invalid(changed, 'registry_or_source_invalid')
        changed = copy.deepcopy(self.proposal); changed['registry']['entries'][1]['scope'] = '../escape'
        self.invalid(changed, 'registry_or_source_invalid')
        changed = copy.deepcopy(self.proposal); changed['registry']['roots'] = ['other']
        self.invalid(changed, 'candidate_reference_mismatch')

    def test_rejects_unbound_wrong_version_or_invented_trace(self):
        changed = copy.deepcopy(self.proposal); changed['registry']['release_version'] = '0.0.1'
        self.invalid(changed, 'candidate_reference_mismatch')
        changed = copy.deepcopy(self.proposal); changed['candidate_manifest_sha256'] = '0'*64
        self.invalid(changed, 'source_snapshot_mismatch')
        changed = copy.deepcopy(self.proposal); changed['trace'][0]['roadmap_quote'] = 'несуществующая цитата'
        self.invalid(changed, 'trace_invalid')
        changed = copy.deepcopy(self.proposal); changed['trace'][0]['proposed_mode'] = 'project'
        self.invalid(changed, 'trace_invalid')
        changed = copy.deepcopy(self.proposal); changed['trace'][1] = copy.deepcopy(changed['trace'][0])
        self.invalid(changed, 'trace_invalid')
        with self.assertRaises(audit.AuditError):
            self.check(road=self.road+b'\n')

    def test_mechanical_anchor_check_is_not_semantic_review(self):
        changed = copy.deepcopy(self.proposal)
        row = next(r for r in changed['registry']['entries'] if r['id'] == 'SYS-MOVE')
        row['text'] = 'Синтетическое противоречие: источник сохраняется после перемещения.'
        self.assertEqual(self.check(changed)['outcome'], 'draft_shape_pass')
        # Совпадение цитаты не доказывает согласованность перефразированного текста.

    def test_modes_are_metadata_not_enforced_by_schema_or_renderer(self):
        changed = copy.deepcopy(self.proposal['registry'])
        changed['entries'][1]['mode'] = 'kit'
        with self.assertRaises(schema_v2.SchemaError):
            schema_v2.validate_registry(changed, expected_area='L0')
        with tempfile.TemporaryDirectory(prefix='l0-render-synthetic-') as d:
            root = Path(d).resolve(); fixture.make_workspace(root)
            from kit.base.registry_store import _load
            docs = _load(Layout(root, 'profiles/pilot')).documents
            docs['L0'] = copy.deepcopy(self.proposal['registry'])
            with self.assertRaises(RenderError):
                render(docs, area='L0', entry_id='SYS-CONFIRM')

    def test_matrix_forbids_l0_mutation_not_initialization_or_moves(self):
        for operation in ('create', 'edit', 'activate', 'suspend', 'resume', 'revoke', 'delete'):
            with self.subTest(operation=operation):
                with self.assertRaises(StoreError) as caught:
                    registry_policy.check_operation(operation, target='L0')
                self.assertEqual(caught.exception.code, 'system_immutable')
        with self.assertRaises(StoreError) as caught:
            registry_policy.check_operation('move', target='L0')
        self.assertEqual(caught.exception.code, 'unknown_operation')

    def guard_workspace(self, workspace):
        pin = hashlib.sha256(self.manifest).hexdigest()
        l0 = workspace/'kit/base/registry.json'
        return guard(ROOT, Layout(workspace, 'profiles/pilot'), manifest_pin=pin,
                     system_pin=hashlib.sha256(l0.read_bytes()).hexdigest())

    def test_guard_accepts_draft_and_empty_l0_without_validating_content(self):
        with tempfile.TemporaryDirectory(prefix='l0-guard-synthetic-') as d:
            workspace = Path(d).resolve(); fixture.make_workspace(workspace, parent_scope='.')
            l0 = workspace/'kit/base/registry.json'
            draft = copy.deepcopy(self.proposal['registry']); fixture.write(l0, draft)
            self.assertEqual(self.guard_workspace(workspace)['outcome'], 'pass')
            draft['entries'] = []
            draft['release_version'] = '0.2.0-audit'  # явно несовпадающая версия на стенде
            fixture.write(l0, draft)
            self.assertEqual(self.guard_workspace(workspace)['outcome'], 'pass')
            with self.assertRaises(audit.AuditError):
                changed = copy.deepcopy(self.proposal); changed['registry'] = draft; self.check(changed)

    def test_guard_does_not_resolve_contradictory_text(self):
        with tempfile.TemporaryDirectory(prefix='l0-conflict-synthetic-') as d:
            workspace = Path(d).resolve(); fixture.make_workspace(workspace, parent_scope='.')
            draft = copy.deepcopy(self.proposal['registry'])
            # Активность только в одноразовом тестовом дереве, не в черновике и не у пользователя.
            for row in draft['entries']:
                row['state'] = 'active'
            fixture.write(workspace/'kit/base/registry.json', draft)
            profile = workspace/'profiles/pilot/registry.json'
            l1 = json.loads(profile.read_bytes())
            l1['entries'].append(fixture.entry('R-OPPOSITE', 'rule', 'profile_owner', 'C-1', '.',
                                      text='Эксплуатационные операции L1 и L2 могут изменять L0.'))
            fixture.write(profile, l1)
            report = self.guard_workspace(workspace)
            self.assertEqual(report['outcome'], 'pass')
            self.assertEqual(report['text_conflicts'], 'not_checked')
            self.assertGreater(report['unstructured_active_entries'], 0)

    def test_confirmed_synthetic_l1_create_preserves_draft_l0(self):
        with tempfile.TemporaryDirectory(prefix='l0-immutability-synthetic-') as d:
            workspace = Path(d).resolve(); fixture.make_workspace(workspace, parent_scope='.')
            l0 = workspace/'kit/base/registry.json'; fixture.write(l0, self.proposal['registry'])
            before = l0.read_bytes(); profile = workspace/'profiles/pilot/registry.json'
            self.assertEqual(self.guard_workspace(workspace)['outcome'], 'pass')
            session = PlanSession(Layout(workspace, 'profiles/pilot'), profile_id='Pilot')
            request = ('Создай черновик контракта C-9 в профиле Pilot, постоянное, '
                       'область «docs», название «Пример», основание «Проба», '
                       'критерий «Запись существует»: Согласуем порядок чтения.')
            plan = session.plan(compile_prompt(request)); self.assertEqual(plan['outcome'], 'planned')
            before_profile = profile.read_bytes()
            with self.assertRaises(StoreError) as caught:
                session.apply(plan, confirmed_ticket='')
            self.assertEqual(caught.exception.code, 'confirmation_required')
            self.assertEqual(before_profile, profile.read_bytes()); self.assertEqual(before, l0.read_bytes())
            self.assertEqual(session.apply(plan, confirmed_ticket=plan['ticket'])['outcome'], 'applied')
            self.assertEqual(before, l0.read_bytes())
            self.assertEqual(self.guard_workspace(workspace)['outcome'], 'pass')


if __name__ == '__main__':
    unittest.main()
