#!/usr/bin/env python3
"""Детерминированные вмешательства в синтетический _replace, не стресс-тест гонок."""
import hashlib
import os
import stat
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'research/audit')]
from test_plan_mode_freshness import ModePlanBase
from kit.base import registry_store as store
from kit.base.registry_policy import StoreError

POISON = b'synthetic-unapproved-bytes\n'
SENTINEL = b'synthetic-decoy-target\n'


@unittest.skipUnless(os.name == 'posix', 'POSIX rename/symlink experiment not_run')
class RaceDiagnosis(ModePlanBase):
    def metadata(self, path):
        info = path.stat()
        return stat.S_IMODE(info.st_mode), info.st_uid, info.st_gid

    def initial_plan(self, target):
        before = self.observed(); plan = self.make_plan(target)
        self.assertEqual(before, self.observed())
        with self.assertRaises(StoreError) as error: self.session.apply(plan)
        self.assertEqual(error.exception.code, 'confirmation_required')
        self.assertEqual(before, self.observed())
        return before, plan

    def control(self, target):
        before, plan = self.initial_plan(target)
        self.assertEqual(self.session.apply(plan, confirmed_ticket=plan['ticket'])['outcome'], 'applied')
        after = self.observed()
        self.assertEqual(hashlib.sha256(after[target][0]).hexdigest(), plan['diff']['after_sha256'])
        for other in set(self.files) - {target}: self.assertEqual(before[other], after[other])
        self.reject('ticket_unknown', plan)

    def staged_swap(self, target):
        before, plan = self.initial_plan(target)
        target_path = self.files[target]; expected_meta = self.metadata(target_path)
        real_replace = os.replace; calls = []
        def substitute(src, dst):
            src, dst = Path(src), Path(dst)
            self.assertEqual(dst, target_path)
            self.assertEqual(self.metadata(src), expected_meta)
            self.assertEqual(hashlib.sha256(src.read_bytes()).hexdigest(), plan['diff']['after_sha256'])
            # Второй участник может удалить и создать имя в каталоге; открытый файл уже закрыт.
            src.unlink(); src.write_bytes(POISON); src.chmod(0o600)
            calls.append((src, dst)); real_replace(src, dst)
        with patch.object(store.os, 'replace', side_effect=substitute):
            result = self.session.apply(plan, confirmed_ticket=plan['ticket'])
        self.assertEqual(len(calls), 1); self.assertEqual(result['outcome'], 'applied')
        self.assertEqual(target_path.read_bytes(), POISON)
        self.assertNotEqual(hashlib.sha256(POISON).hexdigest(), plan['diff']['after_sha256'])
        for other in set(self.files) - {target}: self.assertEqual(before[other], self.observed()[other])
        self.assertFalse(list(target_path.parent.glob('.registry-*.tmp')))
        self.reject('ticket_unknown', plan)

    def directory_swap(self, target):
        before, plan = self.initial_plan(target)
        target_path = self.files[target]; parent = target_path.parent
        parked = parent.with_name(parent.name + '-parked')
        decoy = self.root / ('decoy-' + target); decoy.mkdir()
        (decoy/'registry.json').write_bytes(SENTINEL)
        real_replace = os.replace; calls = []
        def redirect(src, dst):
            src, dst = Path(src), Path(dst)
            self.assertEqual(dst, target_path)
            self.assertEqual(hashlib.sha256(src.read_bytes()).hexdigest(), plan['diff']['after_sha256'])
            self.assertEqual(self.metadata(src), self.metadata(target_path))
            # Обе стороны ссылки находятся внутри выделенного тестового дерева.
            parent.rename(parked)
            (decoy/src.name).write_bytes((parked/src.name).read_bytes())
            parent.symlink_to(decoy, target_is_directory=True)
            calls.append((src, dst)); real_replace(src, dst)
        with patch.object(store.os, 'replace', side_effect=redirect):
            result = self.session.apply(plan, confirmed_ticket=plan['ticket'])
        self.assertEqual(len(calls), 1); self.assertEqual(result['outcome'], 'applied')
        self.assertEqual(hashlib.sha256((decoy/'registry.json').read_bytes()).hexdigest(), plan['diff']['after_sha256'])
        self.assertNotEqual((decoy/'registry.json').read_bytes(), SENTINEL)
        self.assertEqual((parked/'registry.json').read_bytes(), before[target][0])
        self.assertEqual(hashlib.sha256((parked/calls[0][0].name).read_bytes()).hexdigest(), plan['diff']['after_sha256'])
        parent.unlink(); parked.rename(parent)
        self.assertEqual(self.observed(), before)
        self.reject('ticket_unknown', plan)

    def swap_before_apply(self, target):
        before, plan = self.initial_plan(target)
        parent = self.files[target].parent; parked = parent.with_name(parent.name + '-parked')
        decoy = self.root / ('decoy-' + target); decoy.mkdir()
        (decoy/'registry.json').write_bytes(before[target][0]); (decoy/'registry.json').chmod(0o600)
        parent.rename(parked); parent.symlink_to(decoy, target_is_directory=True)
        try:
            with patch.object(store.os, 'replace') as replace:
                self.reject('unsafe_path', plan); replace.assert_not_called()
            self.assertEqual((parked/'registry.json').read_bytes(), before[target][0])
            self.assertEqual((decoy/'registry.json').read_bytes(), before[target][0])
        finally:
            parent.unlink(); parked.rename(parent)
        self.assertEqual(self.observed(), before); self.reject('ticket_unknown', plan)

    def test_control_l1(self): self.control('L1')
    def test_control_l2(self): self.control('L2')
    def test_staged_swap_l1(self): self.staged_swap('L1')
    def test_staged_swap_l2(self): self.staged_swap('L2')
    def test_directory_swap_l1(self): self.directory_swap('L1')
    def test_directory_swap_l2(self): self.directory_swap('L2')
    def test_swap_before_apply_l1(self): self.swap_before_apply('L1')
    def test_swap_before_apply_l2(self): self.swap_before_apply('L2')


if __name__ == '__main__': unittest.main()
