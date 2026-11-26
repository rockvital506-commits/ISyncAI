#!/usr/bin/env python3
"""Наблюдение после копирования: только временные синтетические фикстуры."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import json
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'research/audit')]
import core_audit as audit
import test_profile_copy as fixture
from kit import profile_copy
from kit.base import registry_store as store
from kit.base.registry_policy import StoreError

@unittest.skipUnless(fixture.atomic_tests.SUPPORTED and store.fcntl is not None,'POSIX/Linux unavailable; not_run')
class InspectTests(unittest.TestCase):
    def setUp(self):
        self.ctx=fixture.ProfileCopyTests();self.ctx.setUp();self.addCleanup(self.ctx.doCleanups)
        self.plan=self.ctx.session().plan();self.stage=self.ctx.b1.parent/self.plan['stage_name']
        self.before=hashlib.sha256(self.ctx.b1.read_bytes()).hexdigest()
        self.after=hashlib.sha256(self.ctx.a1.read_bytes()).hexdigest()
    def observe(self):
        return profile_copy.inspect_target(self.ctx.b,stage_name=self.stage.name,before_sha256=self.before,after_sha256=self.after)
    def error(self,code,fn,*args,**kw):
        with self.assertRaises(StoreError) as e:fn(*args,**kw)
        self.assertEqual(e.exception.code,code)
    def test_before_partial_complete_and_after_never_modify(self):
        for payload in (None,b'partial',self.ctx.a1.read_bytes()):
            if payload is not None:self.stage.write_bytes(payload)
            before=audit.tree_digest(self.ctx.root);r=self.observe()
            self.assertEqual(r['registry']['matches'],['before']);self.assertEqual(r['completion'],'not_verified')
            if payload is None:self.assertEqual(r['stage']['state'],'absent')
            elif payload==b'partial':self.assertEqual(r['stage']['matches'],[])
            else:self.assertEqual(r['stage']['matches'],['after'])
            self.assertEqual(before,audit.tree_digest(self.ctx.root))
        self.stage.unlink();self.ctx.b1.write_bytes(self.ctx.a1.read_bytes())
        r=self.observe();self.assertEqual(r['registry']['matches'],['after']);self.assertEqual(r['stage']['state'],'absent')
        self.assertEqual(r['durability'],'not_verified')
    def test_symlink_directory_hardlink_and_oversized_not_read(self):
        for kind in ('symlink','directory','hardlink','large'):
            with self.subTest(kind=kind):
                if kind=='symlink':self.stage.symlink_to(self.ctx.a1)
                elif kind=='directory':self.stage.mkdir()
                elif kind=='hardlink':os.link(self.ctx.a1,self.stage)
                else:
                    with self.stage.open('wb') as f:f.truncate(profile_copy.MAX_PROFILE+1)
                before=audit.tree_digest(self.ctx.root);r=self.observe()
                self.assertEqual(r['stage']['state'],'too_large' if kind=='large' else 'unsafe_type_or_links')
                self.assertEqual(before,audit.tree_digest(self.ctx.root))
                if kind=='directory':self.stage.rmdir()
                else:self.stage.unlink()
    def test_inputs_lock_and_error(self):
        for name in ('../registry.json','.profile-copy-stage-abc','registry.json'):
            self.error('profile_copy_inspect_invalid',profile_copy.inspect_target,self.ctx.b,stage_name=name,before_sha256=self.before,after_sha256=self.after)
        self.error('profile_copy_inspect_invalid',profile_copy.inspect_target,self.ctx.b,stage_name=self.stage.name,before_sha256='x',after_sha256=self.after)
        fd=os.open(self.ctx.b.workspace,os.O_RDONLY|os.O_DIRECTORY)
        try:
            store.fcntl.flock(fd,store.fcntl.LOCK_EX|store.fcntl.LOCK_NB)
            self.error('profile_copy_inspect_busy',self.observe)
        finally:os.close(fd)
        with patch.object(profile_copy.probe,'_read',side_effect=OSError('synthetic')):
            self.error('profile_copy_inspect_unavailable',self.observe)
    def test_json_cli_inspect_does_not_clear_barrier(self):
        self.stage.write_bytes(b'partial');before=audit.tree_digest(self.ctx.root)
        request={'type':'inspect','stage_name':self.stage.name,'before_sha256':self.before,'after_sha256':self.after}
        cmd=[sys.executable,'-I','-S','-B',str(ROOT/'kit/profile_copy.py'),'--source-workspace',str(self.ctx.a.workspace),'--target-workspace',str(self.ctx.b.workspace),'--profile-root','profiles/pilot','--system-pin',self.ctx.pin]
        result=subprocess.run(cmd,input=json.dumps(request)+'\n',text=True,capture_output=True,timeout=10,check=True)
        observed=json.loads(result.stdout);self.assertEqual(observed['stage']['matches'],[])
        self.error('profile_copy_pending',store.status,self.ctx.b)
        self.assertEqual(before,audit.tree_digest(self.ctx.root))

if __name__=='__main__':unittest.main()
