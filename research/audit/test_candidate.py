#!/usr/bin/env python3
"""Только синтетические копии кандидата, без изменения рабочего Kit."""
import copy
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('verify_candidate', ROOT / 'kit/verify_candidate.py')
verify_candidate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify_candidate)


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='kit-candidate-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT / 'kit', self.root / 'kit', ignore=shutil.ignore_patterns('__pycache__'))
        self.manifest = self.root / 'kit/KIT-VERSION.json'
        self.doc = json.loads(self.manifest.read_text(encoding='utf-8'))

    def save(self, doc):
        self.manifest.write_text(json.dumps(doc, ensure_ascii=False), encoding='utf-8')

    def test_pass_and_pin(self):
        result = verify_candidate.verify(self.root)
        self.assertEqual(result['status'], 'pass')
        self.assertEqual(result['files'], len(self.doc['files']))
        self.assertFalse(result['pin_checked'])
        self.assertTrue(verify_candidate.verify(self.root, pin=result['manifest_sha256'])['pin_checked'])
        with self.assertRaises(verify_candidate.VerificationError):
            verify_candidate.verify(self.root, pin='0' * 64)

    def test_modified_file(self):
        p = self.root / 'kit/base/SCHEMA-V2.md'
        p.write_bytes(p.read_bytes() + b'changed')
        with self.assertRaises(verify_candidate.VerificationError):
            verify_candidate.verify(self.root)

    def test_missing_and_extra(self):
        (self.root / 'kit/base/SCHEMA-V2.md').unlink()
        with self.assertRaises(verify_candidate.VerificationError):
            verify_candidate.verify(self.root)
        shutil.copyfile(ROOT / 'kit/base/SCHEMA-V2.md', self.root / 'kit/base/SCHEMA-V2.md')
        (self.root / 'kit/base/new.py').write_text('test', encoding='utf-8')
        with self.assertRaises(verify_candidate.VerificationError):
            verify_candidate.verify(self.root)

    def test_pinned_manifest_detects_rewritten_manifest(self):
        pin = verify_candidate.verify(self.root)['manifest_sha256']
        p = self.root / 'kit/base/SCHEMA-V2.md'
        p.write_bytes(p.read_bytes() + b'changed')
        self.doc['files']['kit/base/SCHEMA-V2.md'] = verify_candidate.digest(p.read_bytes())
        self.save(self.doc)
        self.assertEqual(verify_candidate.verify(self.root)['status'], 'pass')
        with self.assertRaises(verify_candidate.VerificationError):
            verify_candidate.verify(self.root, pin=pin)

    def test_invalid_or_escaping_path(self):
        for path in ('../secrets', 'kit/base/../x', '/etc/passwd', 'kit/base/x/y'):
            with self.subTest(path=path):
                doc = copy.deepcopy(self.doc)
                doc['files'][path] = '0' * 64
                self.save(doc)
                with self.assertRaises(verify_candidate.VerificationError):
                    verify_candidate.verify(self.root)

    def test_duplicate_json_field(self):
        self.manifest.write_text('{"format":1,"format":1}', encoding='utf-8')
        with self.assertRaises(verify_candidate.VerificationError):
            verify_candidate.verify(self.root)

    def test_symlink_fails(self):
        file = self.root / 'kit/base/SCHEMA-V2.md'
        file.unlink()
        try:
            file.symlink_to(ROOT / 'kit/base/SCHEMA-V2.md')
        except OSError as exc:
            self.skipTest(f'нет права создавать символьные ссылки: {exc}')
        with self.assertRaises(verify_candidate.VerificationError):
            verify_candidate.verify(self.root)

    def test_no_write(self):
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        verify_candidate.verify(self.root)
        after = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)


if __name__ == '__main__':
    unittest.main()
