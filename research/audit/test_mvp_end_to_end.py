#!/usr/bin/env python3
"""Сквозной тест только в независимых временных деревьях, не запуск Kilo или Arena."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'research/audit')]
import core_audit as a
from kit.base import registry_store
from kit.base.operation_card import compile_prompt
from kit.base.operation_plan import PlanSession
from kit.render_rule import render

EXAMPLES = ROOT / 'kit/examples'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def run_project(name):
    """Строит одно независимое временное дерево. Ни один реальный проект не открывается."""
    with tempfile.TemporaryDirectory(prefix='kit-e2e-') as tmp:
        root = Path(tmp)
        layout = a.make_workspace(root)
        project = json.loads((EXAMPLES / 'projects' / (name + '.json')).read_text(encoding='utf-8'))
        a.write(root / '.agent-contract/project/registry.json', project)
        source = json.loads((EXAMPLES / 'profile-candidate.json').read_text(encoding='utf-8'))
        session = PlanSession(layout, profile_id='Pilot')
        l0_path = root / 'kit/base/registry.json'
        l0_before = l0_path.read_bytes()
        l2_path = root / '.agent-contract/project/registry.json'
        l2_before = l2_path.read_bytes()

        def confirmed(phrase):
            card = compile_prompt(phrase)
            if card['outcome'] != 'complete':
                raise AssertionError((phrase, card['outcome'], card['missing']))
            before = a.tree_digest(root)
            plan = session.plan(card)
            if plan['outcome'] != 'planned' or before != a.tree_digest(root):
                raise AssertionError('план не является неизменяющим planned')
            target = root / plan['diff']['file']
            if sha(target.read_bytes()) != plan['diff']['before_sha256']:
                raise AssertionError('план не соответствует исходным байтам')
            try:
                session.apply(plan)
            except registry_store.StoreError as exc:
                if exc.code != 'confirmation_required' or before != a.tree_digest(root):
                    raise AssertionError('неверный отказ без согласия') from exc
            else:
                raise AssertionError('запись без тестового согласия')
            # Тестовое согласие на один план, не согласие на реальное внедрение.
            result = session.apply(plan, confirmed_ticket=plan['ticket'])
            if result['outcome'] != 'applied' or sha(target.read_bytes()) != plan['diff']['after_sha256']:
                raise AssertionError('запись не соответствует плану')

        nouns = {'contract': 'контракта', 'protocol': 'протокола', 'rule': 'правила'}
        acc = {'contract': 'контракт', 'protocol': 'протокол', 'rule': 'правило'}
        for row in source['entries']:
            parent = '' if row['parent'] is None else f', по контракту {row["parent"]}'
            phrase = (f'Создай черновик {nouns[row["kind"]]} {row["id"]} в профиле Pilot, постоянное'
                      f'{parent}, область «{row["scope"]}», название «{row["title"]}», '
                      f'основание «{row["basis"]}», критерий «{row["criterion"]}»: {row["text"]}')
            confirmed(phrase)
            confirmed(f'Активируй {acc[row["kind"]]} {row["id"]} в профиле Pilot.')
        if l2_path.read_bytes() != l2_before or l0_path.read_bytes() != l0_before:
            raise AssertionError('изменились соседние области при работе с L1')
        profile_before_l2 = (root / 'profiles/pilot/registry.json').read_bytes()
        for row in project['entries']:
            confirmed(f'Активируй {acc[row["kind"]]} {row["id"]} в проекте.')
        if (root / 'profiles/pilot/registry.json').read_bytes() != profile_before_l2 or l0_path.read_bytes() != l0_before:
            raise AssertionError('изменились соседние области при работе с L2')
        catalog = {area: registry_store.read_registry(layout, target=area) for area in ('L0','L1','L2')}
        l1 = render(catalog, area='L1', entry_id='R-ROADMAP')
        l2 = render(catalog, area='L2', entry_id=project['entries'][1]['id'])
        return {'l1': l1, 'l2': l2, 'profile_revision': catalog['L1']['revision'],
                'project_revision': catalog['L2']['revision'],
                'l1_history': registry_store.registry_history(layout, target='L1'),
                'l2_history': registry_store.registry_history(layout, target='L2')}


class EndToEndTests(unittest.TestCase):
    def test_two_projects_same_portable_rule_distinct_project_rules(self):
        cli, docs = run_project('cli'), run_project('docs')
        self.assertEqual(cli['l1'], docs['l1'])
        self.assertNotEqual(cli['l2'], docs['l2'])
        self.assertEqual((cli['profile_revision'], cli['project_revision']), (6, 2))
        self.assertEqual((docs['profile_revision'], docs['project_revision']), (6, 2))
        self.assertEqual([x['operation'] for x in cli['l1_history']['decisions']],
                         ['create','activate','create','activate','create','activate'])
        self.assertEqual([x['operation'] for x in cli['l2_history']['decisions']], ['activate','activate'])

    def test_repeat_is_reproducible(self):
        first, second = run_project('cli'), run_project('cli')
        self.assertEqual(first, second)


if __name__ == '__main__': unittest.main()
