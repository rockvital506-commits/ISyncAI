#!/usr/bin/env python3
"""Регрессионные пробы статического инвентаря, не доказательство безопасности."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'research/audit'))
import entrypoint_inventory as audit


class EntrypointInventoryTests(unittest.TestCase):
    def test_recorded_inventory_is_current(self):
        expected = json.loads((ROOT / 'research/kilo/ENTRYPOINT-INVENTORY.json').read_bytes())
        self.assertEqual(expected, audit.inventory(ROOT))
        self.assertEqual(len(expected['entries']), len(audit.CLASSES))
    def test_unclassified_and_missing_entrypoints_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); kit = root / 'kit'; kit.mkdir()
            (kit / 'new.py').write_text("if __name__ == '__main__':\n    pass\n")
            with patch.dict(audit.CLASSES, {}, clear=True):
                with self.assertRaisesRegex(ValueError, 'unclassified_entrypoint:new.py'):
                    audit.inventory(root)
            (kit / 'new.py').unlink()
            with patch.dict(audit.CLASSES, {'old.py': 'diagnostic'}, clear=True):
                with self.assertRaisesRegex(ValueError, 'missing_classified_entrypoint:old.py'):
                    audit.inventory(root)
    def test_only_explicit_top_level_pattern_detected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); kit = root / 'kit'; kit.mkdir()
            file = kit / 'demo.py'; file.write_text("def f():\n    return '__main__'\n")
            with patch.dict(audit.CLASSES, {}, clear=True):
                self.assertEqual(audit.inventory(root)['entries'], [])
            file.write_text("if __name__ == '__main__':\n    pass\n")
            with patch.dict(audit.CLASSES, {'demo.py': 'diagnostic'}, clear=True):
                row = audit.inventory(root)['entries'][0]
                self.assertEqual((row['path'], row['category']), ('kit/demo.py', 'diagnostic'))

if __name__ == '__main__':
    unittest.main()
