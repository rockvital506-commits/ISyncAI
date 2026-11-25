#!/usr/bin/env python3
"""Нативный путь L1: сравнение метаданных при замене, временные данные."""
import os
import stat
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'research/audit')]
import core_audit as audit
from test_plan_mode_freshness import ModePlanBase
from kit.base import registry_store as store
from kit.base.registry_policy import StoreError


@unittest.skipUnless(os.name == 'posix', 'POSIX not_run')
class NativeMetadata(ModePlanBase):
    def setUp(self):
        super().setUp()
        for path in self.files.values(): path.chmod(0o600)
        self.entry = audit.entry('Q-9','rule','profile_owner','C-1','docs',state='draft')

    def planned(self, with_preview):
        if with_preview:
            preview=store.preview_create(self.layout,self.entry)
            return preview.store_plan, {'preview':preview}
        return store.plan_create(self.layout,self.entry), {}

    def apply(self, plan, options):
        return store.apply_create(self.layout,plan,confirmed_ticket=plan['ticket'],**options)

    def test_matching_metadata_both_paths(self):
        for with_preview in (False, True):
            with self.subTest(preview=with_preview):
                self.entry = audit.entry('Q-8' if with_preview else 'Q-9','rule',
                                         'profile_owner','C-1','docs',state='draft')
                plan,options=self.planned(with_preview); before=self.observed()
                self.apply(plan,options);after=self.observed()
                self.assertNotEqual(before['L1'][0],after['L1'][0])
                self.assertEqual(after['L1'][1],0o600)
                self.assertEqual(before['L0'],after['L0']);self.assertEqual(before['L2'],after['L2'])

    def test_temp_metadata_failure_is_fail_closed_both_paths(self):
        real_fstat=os.fstat
        for preview in (False,True):
            for variant in ('mode','uid','gid','missing','error','second'):
                with self.subTest(preview=preview,variant=variant):
                    plan,options=self.planned(preview);before=self.observed();sizes=[]
                    def changed(fd):
                        info=real_fstat(fd)
                        if stat.S_ISDIR(info.st_mode):return info
                        sizes.append(info.st_size)
                        if variant=='error':raise OSError('synthetic')
                        if variant=='missing':return SimpleNamespace(st_mode=info.st_mode)
                        late=variant=='second' and len(sizes)==2
                        return SimpleNamespace(st_mode=info.st_mode ^ (0o040 if variant=='mode' else 0),
                                               st_uid=info.st_uid+(variant=='uid' or late),
                                               st_gid=info.st_gid+(variant=='gid'))
                    with patch.object(store.os,'fstat',side_effect=changed), patch.object(store.os,'replace') as replace:
                        with self.assertRaises(StoreError) as error:self.apply(plan,options)
                    self.assertEqual(error.exception.code,'metadata_unavailable' if variant in ('missing','error')
                                     else 'replacement_metadata_mismatch')
                    replace.assert_not_called();self.assertEqual(self.observed(),before)
                    self.assertEqual(sizes[0],0)
                    if variant=='second':self.assertGreater(sizes[1],0)
                    self.assertEqual(list(self.files['L1'].parent.glob('.registry-*.tmp')),[])
        # Нативный билет не одноразовый; повтор допустим без изменения входных байтов.
        self.apply(plan,options);self.assertNotEqual(self.observed()['L1'][0],before['L1'][0])

    def test_target_metadata_unavailable_before_temp(self):
        plan,options=self.planned(False);before=self.observed()
        with patch.object(store,'_posix_metadata',side_effect=StoreError('metadata_unavailable','L1')), \
             patch.object(store.tempfile,'NamedTemporaryFile') as temporary:
            with self.assertRaises(StoreError) as error:self.apply(plan,options)
        self.assertEqual(error.exception.code,'metadata_unavailable');temporary.assert_not_called()
        self.assertEqual(self.observed(),before)

    def test_mode_changed_after_native_plan_not_a_staleness_input(self):
        self.files['L1'].chmod(0o640);plan,options=self.planned(True)
        self.files['L1'].chmod(0o600);before=self.observed()
        self.apply(plan,options);after=self.observed()
        self.assertNotEqual(before['L1'][0],after['L1'][0]);self.assertEqual(after['L1'][1],0o600)
        self.assertEqual(before['L0'],after['L0']);self.assertEqual(before['L2'],after['L2'])


if __name__ == '__main__': unittest.main()
