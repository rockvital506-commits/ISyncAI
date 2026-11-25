#!/usr/bin/env python3
"""План и активация исключительно на синтетических временных реестрах."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import core_audit as audit
from kit.base.operation_card import compile_prompt
from kit.base.operation_plan import PlanSession
from kit.base.registry_store import StoreError, read_registry, registry_history


class ActivationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='kit-activate-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.layout = audit.make_workspace(self.root, parent_state='draft')
        self.session = PlanSession(self.layout, profile_id='Pilot')
        self.path = self.root / 'profiles/pilot/registry.json'

    def plan(self, phrase):
        return self.session.plan(compile_prompt(phrase))

    def apply(self, plan):
        return self.session.apply(copy.deepcopy(plan), confirmed_ticket=plan['ticket'])

    def create_child(self):
        p = self.session.plan(audit.card())
        self.apply(p)

    def assert_denied(self, fn, code):
        before = audit.tree_digest(self.root)
        with self.assertRaises(StoreError) as error:
            fn()
        self.assertEqual(error.exception.diagnostic()['code'], code)
        self.assertEqual(before, audit.tree_digest(self.root))

    def test_parent_then_child_individual_tickets_and_history(self):
        self.create_child()
        self.assert_denied(lambda: self.plan('Активируй протокол Q-1 в профиле Pilot.'), 'parent')
        before = audit.tree_digest(self.root)
        parent = self.plan('Активируй контракт C-1 в профиле Pilot.')
        self.assertEqual(parent['outcome'], 'planned')
        self.assertEqual(audit.tree_digest(self.root), before)
        self.assert_denied(lambda: self.session.apply(parent), 'confirmation_required')
        self.apply(parent)
        self.assert_denied(lambda: self.apply(parent), 'ticket_unknown')
        child = self.plan('Активируй протокол Q-1 в профиле Pilot.')
        self.assertNotEqual(child['ticket'], parent['ticket'])
        self.apply(child)
        doc = read_registry(self.layout, target='L1')
        self.assertEqual({r['id']: r['state'] for r in doc['entries']}, {'C-1': 'active', 'Q-1': 'active'})
        self.assertEqual(doc['revision'], 3)
        history = registry_history(self.layout, target='L1')
        self.assertEqual([d['operation'] for d in history['decisions']], ['create', 'activate', 'activate'])
        repeat = self.plan('Активируй протокол Q-1 в профиле Pilot.')
        self.assertEqual(repeat['outcome'], 'no_change')
        self.assertNotIn('ticket', repeat)

    def test_already_active_child_with_inactive_parent_is_not_success(self):
        doc = json.loads(self.path.read_text(encoding='utf-8'))
        child = audit.entry('Q-1', 'protocol', 'profile_owner', 'C-1', 'docs', state='active')
        doc['entries'].append(child)
        audit.write(self.path, doc)
        self.assert_denied(lambda: self.plan('Активируй протокол Q-1 в профиле Pilot.'), 'parent')

    def test_l0_rejected(self):
        self.assert_denied(lambda: self.plan('Активируй правило S-1 в L0.'), 'system_immutable')

    def test_wrong_ticket_and_edited_plan_denied(self):
        plan = self.plan('Активируй контракт C-1 в профиле Pilot.')
        self.assert_denied(lambda: self.session.apply(plan, confirmed_ticket='0' * 64), 'confirmation_required')
        changed = copy.deepcopy(plan)
        changed['diff']['unified'] += 'подмена'
        self.assert_denied(lambda: self.session.apply(changed, confirmed_ticket=plan['ticket']), 'plan_mismatch')

    def test_stale_other_area_denied(self):
        plan = self.plan('Активируй контракт C-1 в профиле Pilot.')
        p = self.root / '.domain-agent-kit/project/registry.json'
        p.write_bytes(p.read_bytes() + b'\n')
        self.assert_denied(lambda: self.apply(plan), 'stale_plan')

    def test_wrong_transition_and_kind_denied(self):
        doc = json.loads(self.path.read_text(encoding='utf-8'))
        doc['entries'][0]['state'] = 'revoked'
        audit.write(self.path, doc)
        self.assert_denied(lambda: self.plan('Активируй контракт C-1 в профиле Pilot.'), 'invalid_transition')
        self.assert_denied(lambda: self.plan('Активируй правило C-1 в профиле Pilot.'), 'entry_kind_mismatch')

    def test_conflict_rejected(self):
        doc = json.loads(self.path.read_text(encoding='utf-8'))
        doc['entries'][0]['state'] = 'active'
        child = audit.entry('Q-1', 'rule', 'profile_owner', 'C-1', 'docs', state='draft')
        child.update(key='test-key', value='different')
        doc['entries'].append(child)
        audit.write(self.path, doc)
        l0 = self.root / 'kit/base/registry.json'
        system = json.loads(l0.read_text(encoding='utf-8'))
        item = audit.entry('S-rule', 'rule', 'system_release', 'S-1', '.', state='active')
        item.update(key='test-key', value='original')
        system['entries'].append(item)
        audit.write(l0, system)
        self.assert_denied(lambda: self.plan('Активируй правило Q-1 в профиле Pilot.'), 'rule_conflict')

    def test_l2_separate_and_l1_untouched(self):
        path = self.root / '.domain-agent-kit/project/registry.json'
        doc = json.loads(path.read_text(encoding='utf-8'))
        doc['entries'][0]['state'] = 'draft'
        audit.write(path, doc)
        before = self.path.read_bytes()
        plan = self.plan('Активируй контракт P-1 в проекте.')
        self.apply(plan)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(read_registry(self.layout, target='L2')['entries'][0]['state'], 'active')
        self.assertEqual(registry_history(self.layout, target='L2')['decisions'][0]['operation'], 'activate')


if __name__ == '__main__':
    unittest.main()
