#!/usr/bin/env python3
"""Текущие байты L0 в исторических случаях И-117; независимый ZIP-эталон в памяти."""
import copy
import importlib.util
import json
import sys
import unittest
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('historical_bundle_117', ROOT / 'research/117/test_bundle.py')
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
from kit.base.bundle import bundle


def independent_archive(files, manifest):
    files = {**files, 'manifest.json': old.canonical(manifest) + b'\n'}
    buffer = BytesIO()
    with ZipFile(buffer, 'w', compression=ZIP_STORED, allowZip64=False) as z:
        for name in sorted(files):
            info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            z.writestr(info, files[name])
    return buffer.getvalue()


class CurrentBundleTests(unittest.TestCase):
    def test_all_117_cases_with_current_explicit_bytes(self):
        book = json.loads((ROOT / old.BOOK).read_bytes())
        original = copy.deepcopy(book)
        ctx = old.context(book)
        old.control(book, ctx)
        for fixture in book['golden']:
            files = old.payload(book, ctx, fixture)
            manifest = old.manifest_for(book, files)
            raw = independent_archive(files, manifest)
            book['golden'][fixture] = {'manifest_digest': manifest['digest'],
                                       'archive_sha256': old.hash_bytes(raw),
                                       'archive_bytes': len(raw)}
        self.assertEqual(json.loads((ROOT / old.BOOK).read_bytes()), original)
        monitor = old.Monitor()
        failures = []
        for case in book['cases']:
            try:
                packet, record = monitor.call(bundle, old.args_for(book, ctx, case),
                                              late=case.get('inject') == 'late_archive')
                record['package'] = None if packet is None else old.inspect_packet(book, ctx, case['fixture'], packet)
                if old.canonical(record) != old.canonical(old.expected_observation(book, ctx, case)):
                    failures.append((case['id'], 'oracle_mismatch'))
            except Exception as exc:
                failures.append((case['id'], type(exc).__name__))
        self.assertEqual(len(book['cases']), 46)
        self.assertEqual(failures, [])


if __name__ == '__main__':
    unittest.main()
