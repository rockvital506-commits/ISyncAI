#!/usr/bin/env python3
"""Никаких настоящих проектов: изолированные L2-фикстуры и их планы."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'research/audit')]
import core_audit as a
from kit.base import registry_store, schema_v2
from kit.base.operation_card import compile_prompt
from kit.base.operation_plan import PlanSession
from kit.render_rule import render, RenderError

FIXTURES = ROOT / 'kit/examples/projects'


class ProjectCandidates(unittest.TestCase):
    def fixtures(self):
        return {n: schema_v2.validate_json((FIXTURES / (n + '.json')).read_bytes(), expected_area='L2')
                for n in ('cli', 'docs')}

    def test_valid_distinct_drafts(self):
        docs = self.fixtures()
        self.assertNotEqual(docs['cli']['entries'][1]['text'], docs['docs']['entries'][1]['text'])
        self.assertNotEqual(docs['cli']['entries'][1]['id'], docs['docs']['entries'][1]['id'])
        for doc in docs.values():
            self.assertEqual(doc['revision'], 0)
            self.assertEqual(doc['roots'], ['.domain-agent-kit'])
            self.assertTrue(all(row['state'] == 'draft' for row in doc['entries']))
            self.assertEqual(doc['entries'][1]['parent'], doc['entries'][0]['id'])

    def test_isolated_project_activation_and_render(self):
        fixtures = self.fixtures()
        rendered = {}
        for name, doc in fixtures.items():
            with self.subTest(project=name), tempfile.TemporaryDirectory(prefix='kit-project-example-') as tmp:
                root = Path(tmp)
                layout = a.make_workspace(root)
                file = root / '.domain-agent-kit/project/registry.json'
                a.write(file, copy.deepcopy(doc))
                l0 = (root / 'kit/base/registry.json').read_bytes()
                l1 = (root / 'profiles/pilot/registry.json').read_bytes()
                session = PlanSession(layout, profile_id='Pilot')
                catalog = {area: registry_store.read_registry(layout, target=area) for area in ('L0','L1','L2')}
                with self.assertRaises(RenderError):
                    render(catalog, area='L2', entry_id=doc['entries'][1]['id'])
                for row in doc['entries']:
                    noun = 'контракт' if row['kind'] == 'contract' else 'правило'
                    plan = session.plan(compile_prompt(f'Активируй {noun} {row["id"]} в проекте.'))
                    self.assertEqual(plan['outcome'], 'planned')
                    # Только синтетическое согласие для временного стенда.
                    session.apply(plan, confirmed_ticket=plan['ticket'])
                catalog = {area: registry_store.read_registry(layout, target=area) for area in ('L0','L1','L2')}
                rendered[name] = render(catalog, area='L2', entry_id=doc['entries'][1]['id'])
                self.assertIn(doc['entries'][1]['text'].encode('utf-8'), rendered[name])
                self.assertEqual((root / 'kit/base/registry.json').read_bytes(), l0)
                self.assertEqual((root / 'profiles/pilot/registry.json').read_bytes(), l1)
                self.assertEqual(catalog['L2']['revision'], 2)
        self.assertNotEqual(rendered['cli'], rendered['docs'])
        self.assertNotIn(fixtures['docs']['entries'][1]['text'].encode(), rendered['cli'])
        self.assertNotIn(fixtures['cli']['entries'][1]['text'].encode(), rendered['docs'])

    def test_wrong_layer_rejected(self):
        for doc in self.fixtures().values():
            with self.assertRaises(schema_v2.SchemaError):
                schema_v2.validate_registry(doc, expected_area='L1')


if __name__ == '__main__': unittest.main()
