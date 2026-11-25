#!/usr/bin/env python3
"""Ограниченный fail-closed для видимых xattr синтетических реестров."""
import errno
import os
import stat
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'research/audit')]
import core_audit as audit
from test_plan_mode_freshness import ModePlanBase
from kit.base import registry_store as store
from kit.base.registry_policy import StoreError

SUPPORTED = os.name == 'posix' and all(hasattr(os, name) for name in ('listxattr','setxattr','getxattr'))
NAME = 'user.domainagentkit_guard_probe'
VALUE = b'synthetic-not-sensitive'


@unittest.skipUnless(SUPPORTED, 'POSIX xattr API unavailable; not_run')
class Guard(ModePlanBase):
    def setUp(self):
        super().setUp()
        for p in self.files.values(): p.chmod(0o600)
        try:
            os.setxattr(self.files['L1'],NAME,VALUE)
            self.assertIn(NAME,os.listxattr(self.files['L1']))
            os.removexattr(self.files['L1'],NAME)
        except OSError as error:
            if error.errno in {errno.ENOTSUP, errno.EPERM, errno.EACCES, errno.ENOSYS}:
                self.skipTest('test xattr unsupported; not_run')
            raise

    def setup_path(self, native):
        if native:
            entry=audit.entry('Q-9','rule','profile_owner','C-1','docs',state='draft')
            plan=store.plan_create(self.layout,entry)
            return lambda: store.apply_create(self.layout,plan,confirmed_ticket=plan['ticket'])
        plan=self.make_plan()
        return lambda: self.session.apply(plan,confirmed_ticket=plan['ticket'])

    def test_present_target_refused_before_temp_for_both_paths(self):
        for native in (False,True):
            with self.subTest(native=native):
                os.setxattr(self.files['L1'],NAME,VALUE); before=self.observed(); apply=self.setup_path(native)
                with patch.object(store.tempfile,'NamedTemporaryFile') as temp:
                    with self.assertRaises(StoreError) as failure:apply()
                self.assertEqual(failure.exception.code,'replacement_xattrs_present');temp.assert_not_called()
                self.assertEqual(self.observed(),before);self.assertEqual(os.getxattr(self.files['L1'],NAME),VALUE)
                os.removexattr(self.files['L1'],NAME)

    def test_stage_attribute_before_or_after_write_refused_and_removed(self):
        real=os.listxattr
        for native in (False,True):
            for stage_at in (1,2):
                with self.subTest(native=native,stage_at=stage_at):
                    apply=self.setup_path(native);before=self.observed();fd_calls=[]
                    def inject(path,*args,**kw):
                        if isinstance(path,int):
                            fd_calls.append(os.fstat(path).st_size)
                            if len(fd_calls)==stage_at:os.setxattr(path,NAME,VALUE)
                        return real(path,*args,**kw)
                    with patch.object(store.os,'listxattr',side_effect=inject), patch.object(store.os,'replace') as replace:
                        with self.assertRaises(StoreError) as failure:apply()
                    self.assertEqual(failure.exception.code,'replacement_xattrs_present');replace.assert_not_called()
                    self.assertEqual(self.observed(),before);self.assertEqual(fd_calls[0],0)
                    if stage_at==2:self.assertGreater(fd_calls[1],0)
                    self.assertEqual(list(self.files['L1'].parent.glob('.registry-*.tmp')),[])

    def test_attribute_appearing_on_target_before_last_check_is_preserved(self):
        real=os.listxattr;calls=[];apply=self.setup_path(False);before=self.observed()
        def inject(path,*args,**kw):
            if not isinstance(path,int):
                calls.append(path)
                if len(calls)==2:os.setxattr(path,NAME,VALUE)
            return real(path,*args,**kw)
        with patch.object(store.os,'listxattr',side_effect=inject), patch.object(store.os,'replace') as replace:
            with self.assertRaises(StoreError) as failure:apply()
        self.assertEqual(failure.exception.code,'replacement_xattrs_present');replace.assert_not_called()
        self.assertEqual(self.observed(),before);self.assertEqual(os.getxattr(self.files['L1'],NAME),VALUE)
        self.assertEqual(list(self.files['L1'].parent.glob('.registry-*.tmp')),[])

    def test_api_and_io_failures_never_replace(self):
        for native in (False,True):
            for stage in (1,2,3,4):
                with self.subTest(native=native,stage=stage):
                    apply=self.setup_path(native);before=self.observed();real=os.listxattr;seen=[]
                    def failed(path,*args,**kwargs):
                        seen.append(path)
                        if len(seen)==stage:raise OSError(errno.EIO,'synthetic')
                        return real(path,*args,**kwargs)
                    with patch.object(store.os,'listxattr',side_effect=failed),patch.object(store.os,'replace') as replace:
                        with self.assertRaises(StoreError) as error:apply()
                    self.assertEqual(error.exception.code,'xattrs_unavailable');replace.assert_not_called()
                    self.assertEqual(self.observed(),before)
                    self.assertEqual(list(self.files['L1'].parent.glob('.registry-*.tmp')),[])
        apply=self.setup_path(False);before=self.observed()
        with patch.object(store.os,'listxattr',None),patch.object(store.os,'replace') as replace:
            with self.assertRaises(StoreError) as error:apply()
        self.assertEqual(error.exception.code,'xattrs_unavailable');replace.assert_not_called();self.assertEqual(self.observed(),before)

    def test_removal_after_planning_is_not_bound_to_plan(self):
        os.setxattr(self.files['L1'],NAME,VALUE)
        apply=self.setup_path(False)
        os.removexattr(self.files['L1'],NAME)
        before=self.observed();self.assertEqual(apply()['outcome'],'applied')
        self.assertNotEqual(self.observed()['L1'][0],before['L1'][0])

    def test_nothing_visible_succeeds(self):
        apply=self.setup_path(False);before=self.observed();self.assertEqual(apply()['outcome'],'applied')
        self.assertNotEqual(self.observed()['L1'][0],before['L1'][0]);self.assertEqual(os.listxattr(self.files['L1']),[])

    def test_change_after_final_check_still_can_be_lost(self):
        real_replace=os.replace;apply=self.setup_path(False)
        def uncooperative(src,dst):
            os.setxattr(dst,NAME,VALUE)
            self.assertEqual(os.getxattr(dst,NAME),VALUE)
            real_replace(src,dst)
        with patch.object(store.os,'replace',side_effect=uncooperative):self.assertEqual(apply()['outcome'],'applied')
        self.assertNotIn(NAME,os.listxattr(self.files['L1']))


if __name__ == '__main__': unittest.main()
