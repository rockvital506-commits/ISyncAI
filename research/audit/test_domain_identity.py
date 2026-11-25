#!/usr/bin/env python3
"""Идентичность текущей поставки и границы несовместимого переименования."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from kit.base import registry_store
from kit.verify_candidate import CANDIDATE_VERSION, PRODUCT, verify


class IdentityTests(unittest.TestCase):
    def test_manifest_identity_and_candidate_are_explicit(self):
        manifest = json.loads((ROOT/'kit/KIT-VERSION.json').read_text(encoding='utf-8'))
        self.assertEqual((PRODUCT, CANDIDATE_VERSION), ('DomainAgentKit', '0.2.0-mvp.41'))
        self.assertEqual((manifest['format'], manifest['product'], manifest['version']),
                         (2, PRODUCT, CANDIDATE_VERSION))
        self.assertEqual(verify(ROOT)['product'], PRODUCT)

    def test_current_source_and_examples_have_no_old_brand_or_old_project_root(self):
        manifest = json.loads((ROOT/'kit/KIT-VERSION.json').read_text(encoding='utf-8'))
        paths = list(manifest['files']) + ['kit/examples/projects/cli.json',
                                          'kit/examples/projects/docs.json',
                                          'kit/examples/projects/README.md',
                                          'kit/examples/profile-candidate.json']
        for name in paths:
            with self.subTest(path=name):
                text = (ROOT/name).read_text(encoding='utf-8')
                self.assertNotIn('AgentContractKit', text)
                self.assertNotIn('.agent-contract', text)

    def test_workspace_roots_are_explicit(self):
        roots = registry_store._declared_roots(registry_store.Layout(ROOT, 'profiles/pilot'))
        self.assertEqual(roots, {'L0': 'kit', 'L1': 'profiles/pilot', 'L2': '.domain-agent-kit'})
        for name in ('cli', 'docs'):
            doc = json.loads((ROOT/'kit/examples/projects'/f'{name}.json').read_text(encoding='utf-8'))
            self.assertEqual(doc['roots'], ['.domain-agent-kit'])


if __name__ == '__main__':
    unittest.main()
