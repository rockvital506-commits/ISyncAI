#!/usr/bin/env python3
"""Проверки инвентаря имени только на синтетических текстах и временном дереве."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('name_inventory', ROOT/'research/audit/name_inventory.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class InventoryTests(unittest.TestCase):
    def test_variations_and_no_raw_text(self):
        hits = module.scan_content('AgentContractKit / Agent Contract Kit / domain-agent-kit / .agent-contract / .domain-agent-kit')
        self.assertEqual(hits['old_brand'], 2)
        self.assertEqual(hits['new_brand'], 2)
        self.assertEqual(hits['project_path'], 1)
        self.assertEqual(hits['new_project_path'], 1)
        self.assertNotIn('AgentContractKit', repr(hits))

    def test_limits_scope_and_excludes_sensitive_paths(self):
        for path in ('.isai/file.py', 'user/profile.json', '../kit/foo.py', '/kit/foo.py',
                     'kit/.env', 'kit/.env.json', 'kit/private_key.json',
                     'research/credentials.md', 'research/a.zip', 'kit/profiles/rules.json'):
            with self.subTest(path=path): self.assertFalse(module.allowed(path))
        for path in ('kit/base/schema_v2.py', 'research/kilo/ROADMAP.md', 'README.md'):
            self.assertTrue(module.allowed(path))

    def test_grouping(self):
        self.assertEqual(module.area('kit/base/schema.py'),'candidate_kit')
        self.assertEqual(module.area('research/kilo/ROADMAP.md'),'kilo_docs_and_history')
        self.assertEqual(module.area('research/121/report.md'),'historical_research_and_policy')
        self.assertEqual(module.area('research/audit/test.py'),'audit')

    def test_deterministic_inventory_skips_symlinks_and_never_exposes_content(self):
        with tempfile.TemporaryDirectory(prefix='name-inventory-') as d:
            root=Path(d); (root/'kit').mkdir(); (root/'research').mkdir()
            (root/'kit/file.md').write_text('AgentContractKit\nPRIVATE_TEST_PAYLOAD',encoding='utf8')
            (root/'kit/.env').write_text('PRIVATE_TEST_PAYLOAD',encoding='utf8')
            (root/'kit/data.json').write_bytes(b'\x00binary')
            (root/'research/AgentContractKit-archive.zip').write_bytes(b'not-read')
            names=['kit/file.md','kit/file.md','kit/.env','kit/data.json',
                   'research/AgentContractKit-archive.zip', 'dist/AgentContractKit-0.1.0.zip']
            try:
                (root/'kit/link.md').symlink_to(root/'kit/file.md'); names.append('kit/link.md')
            except OSError:
                pass
            a=module.build(root,names); b=module.build(root,list(reversed(names)))
            self.assertEqual(a,b)
            self.assertEqual(a['scanned_files'],1)
            self.assertEqual(a['matches'][0]['path'],'kit/file.md')
            self.assertIn('kit/data.json',a['skipped_files'])
            self.assertNotIn('kit/.env',repr(a))
            self.assertNotIn('PRIVATE_TEST_PAYLOAD',repr(a))
            self.assertEqual(a['archive_paths_only_not_opened'],['dist/AgentContractKit-0.1.0.zip',
                                                                  'research/AgentContractKit-archive.zip'])
            if 'kit/link.md' in names: self.assertIn('kit/link.md',a['skipped_files'])

    def test_directory_symlink_is_not_followed(self):
        with tempfile.TemporaryDirectory(prefix='name-inventory-') as d:
            root=Path(d); (root/'kit').mkdir(); (root/'real').mkdir()
            (root/'real/file.md').write_text('AgentContractKit',encoding='utf8')
            try: (root/'kit/link').symlink_to(root/'real',target_is_directory=True)
            except OSError: self.skipTest('symlink unsupported')
            result=module.build(root,['kit/link/file.md'])
            self.assertEqual(result['scanned_files'],0)
            self.assertEqual(result['skipped_files'],['kit/link/file.md'])


if __name__=='__main__': unittest.main()
