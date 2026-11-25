#!/usr/bin/env python3
"""Ограниченные POSIX проверки на синтетических временных реестрах."""
import os
import stat
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'research/audit')]
from test_plan_mode_freshness import ModePlanBase
from kit.base import registry_store as store
from kit.base.registry_policy import StoreError


@unittest.skipUnless(os.name == 'posix', 'POSIX not_run')
class ReplacementTests(ModePlanBase):
    def setUp(self):
        super().setUp()
        for path in self.files.values(): path.chmod(0o600)

    def test_matching_both_targets(self):
        for target in ('L1', 'L2'):
            with self.subTest(target=target):
                before = self.observed(); plan = self.make_plan(target)
                self.assertEqual(self.session.apply(plan, confirmed_ticket=plan['ticket'])['outcome'], 'applied')
                after = self.observed()
                self.assertNotEqual(before[target][0], after[target][0])
                self.assertEqual(after[target][1], 0o600)
                for other in set(self.files) - {target}: self.assertEqual(before[other], after[other])

    def test_mismatched_uid_gid_and_unavailable_metadata_before_write(self):
        real_fstat = store.os.fstat
        for variant in ('uid', 'gid', 'missing', 'invalid', 'oserror'):
            with self.subTest(variant=variant):
                plan = self.make_plan(); before = self.observed(); seen = []
                def altered(fd):
                    info = real_fstat(fd); seen.append(info.st_size)
                    if variant == 'oserror': raise OSError('synthetic')
                    if variant == 'missing': return SimpleNamespace(st_mode=info.st_mode)
                    return SimpleNamespace(st_mode=info.st_mode,
                        st_uid=(True if variant == 'invalid' else info.st_uid + (variant == 'uid')),
                        st_gid=info.st_gid + (variant == 'gid'))
                with patch.object(store.os, 'fstat', side_effect=altered), patch.object(store.os, 'replace') as replace:
                    self.reject('metadata_unavailable' if variant in ('missing','invalid','oserror')
                                else 'replacement_metadata_mismatch', plan)
                    replace.assert_not_called()
                self.assertEqual(seen, [0]); self.assertEqual(self.observed(), before)
                self.assertEqual(list(self.files['L1'].parent.glob('.registry-*.tmp')), [])
                self.reject('ticket_unknown', plan)

    def test_target_metadata_unavailable_before_temp_creation(self):
        plan = self.make_plan(); before = self.observed()
        real_metadata = store._posix_metadata
        with patch.object(store, '_posix_metadata', side_effect=lambda info, rel:
                          real_metadata(SimpleNamespace(st_mode=info.st_mode), rel)), \
             patch.object(store.tempfile, 'NamedTemporaryFile') as temporary:
            self.reject('metadata_unavailable', plan); temporary.assert_not_called()
        self.assertEqual(self.observed(), before); self.reject('ticket_unknown', plan)

    def test_cleanup_failure_reported_and_target_untouched(self):
        self.files['L1'].chmod(0o640)
        plan = self.make_plan(); before = self.observed()
        real_unlink = Path.unlink; leftover = []
        def denied(path, *args, **kwargs):
            if path.name.startswith('.registry-'):
                leftover.append((path, path.stat().st_size)); raise OSError('synthetic')
            return real_unlink(path, *args, **kwargs)
        with patch.object(Path, 'unlink', denied), patch.object(store.os, 'replace') as replace:
            self.reject('cleanup_failed', plan); replace.assert_not_called()
        self.assertEqual(len(leftover), 1); self.assertEqual(leftover[0][1], 0)
        self.assertEqual(self.observed(), before); self.reject('ticket_unknown', plan)
        real_unlink(leftover[0][0])

    def test_second_fstat_drift_refuses_after_staged_write(self):
        plan = self.make_plan(); before = self.observed(); real_fstat = store.os.fstat; sizes = []
        def changed(fd):
            info = real_fstat(fd); sizes.append(info.st_size)
            return SimpleNamespace(st_mode=info.st_mode, st_uid=info.st_uid + (len(sizes) == 2), st_gid=info.st_gid)
        with patch.object(store.os, 'fstat', side_effect=changed), patch.object(store.os, 'replace') as replace:
            self.reject('replacement_metadata_mismatch', plan); replace.assert_not_called()
        self.assertEqual(sizes[0], 0); self.assertGreater(sizes[1], 0)
        self.assertEqual(self.observed(), before)
        self.assertEqual(list(self.files['L1'].parent.glob('.registry-*.tmp')), [])
        self.reject('ticket_unknown', plan)


if __name__ == '__main__': unittest.main()
