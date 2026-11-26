#!/usr/bin/env python3
"""Адаптированные текущие пробы; не изменяют исторические архивы и не заменяют живой тест."""
import hashlib
import json
import os
import subprocess
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT/'research/audit/domain_regressions.py'


sys.path.insert(0, str(ROOT/'research/audit'))
import domain_regressions


class ProviderResultTests(unittest.TestCase):
    def test_only_known_results_are_classified(self):
        ok=b'Signature Verified Successfully\n'; bad=b'Signature Verification Failure\n'
        diagnostic=(b'40E7EF6332730000:error:030000EA:digital envelope routines:EVP_DigestVerify:'
                    b'provider signature failure:../crypto/evp/m_sigver.c:779:ED25519 digest_verify:\n')
        result=lambda code,out,err: types.SimpleNamespace(returncode=code,stdout=out,stderr=err)
        self.assertIs(domain_regressions.verifier_result(result(0,ok,b'')),True)
        self.assertIs(domain_regressions.verifier_result(result(1,bad,b'')),False)
        self.assertIs(domain_regressions.verifier_result(result(1,bad,diagnostic)),False)
        for case in ((0,ok,diagnostic),(0,bad,b''),(2,bad,diagnostic),
                     (1,bad,b'provider unavailable\n'),(1,bad,diagnostic+b'extra\n'),(1,b'',b'')):
            with self.subTest(case=case), self.assertRaises(ValueError):
                domain_regressions.verifier_result(result(*case))


class RetargetedTests(unittest.TestCase):
    def run_iteration(self, iteration, expected):
        paths = [ROOT/f'research/{n}/CASES.json' for n in (114, 115, 116, 119, 120)]
        paths += [ROOT/f'research/{n}/{name}' for n, name in
                  ((114,'test_promotion.py'), (115,'test_simulation.py'), (116,'test_conflict_review.py'),
                   (119,'test_bundle_trust.py'), (120,'test_bundle_rollback.py'))]
        before = [hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
        env = dict(os.environ, GIT_ALLOW_PROTOCOL='', PYTHONDONTWRITEBYTECODE='1')
        result = subprocess.run([sys.executable, '-I', '-S', '-B', str(HARNESS), str(iteration)],
                                cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout[-4000:])
        data = json.loads(result.stdout)
        self.assertEqual(data['counts'], {'pass': expected, 'fail': 0, 'not run': 0})
        self.assertEqual(before, [hashlib.sha256(p.read_bytes()).hexdigest() for p in paths])

    def test_promotion_114_with_new_path(self): self.run_iteration(114, 33)
    def test_simulation_115_with_new_path(self): self.run_iteration(115, 25)
    def test_conflicts_116_with_new_path(self): self.run_iteration(116, 33)
    @unittest.skipUnless(Path('/usr/bin/openssl').is_file(), 'OpenSSL И-119 недоступен; not run')
    def test_trust_119_new_domain_and_test_vectors(self): self.run_iteration(119, 51)
    def test_rollback_120_with_new_path_and_envelope(self): self.run_iteration(120, 50)


if __name__ == '__main__':
    unittest.main()
