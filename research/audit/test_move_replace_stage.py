#!/usr/bin/env python3
"""Однофайловый низкоуровневый примитив: только временные синтетические данные."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from kit import init_workspace as init, move_replace_stage as stage
from kit.base.registry_policy import StoreError

@unittest.skipUnless(init._supported() and os.rename in os.supports_dir_fd,'POSIX dirfd/xattr unavailable; not_run')
class ReplaceTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory(prefix='move-stage-');self.addCleanup(t.cleanup)
        self.root=Path(t.name);self.file=self.root/'registry.json';self.file.write_bytes(b'before');self.file.chmod(0o600)
        self.neighbor=self.root/'neighbor';self.neighbor.write_bytes(b'keep')
        self.fd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY);self.addCleanup(os.close,self.fd)
    def replace(self,before=b'before',after=b'after'):
        return stage._replace_for_move(self.fd,before=before,after=after)
    def error(self,code,fn,*args,**kwargs):
        with self.assertRaises(StoreError) as err:fn(*args,**kwargs)
        self.assertEqual(err.exception.code,code)
    def test_success_and_existing_neighbor(self):
        result=self.replace();self.assertEqual(result['outcome'],'single_file_replaced')
        self.assertEqual(result['move'],'not_implemented');self.assertEqual(self.file.read_bytes(),b'after')
        self.assertEqual(self.file.stat().st_mode&0o777,0o600);self.assertEqual(self.neighbor.read_bytes(),b'keep')
        self.assertFalse(list(self.root.glob('.move-stage-*')))
    def test_bad_input_or_original_refused_before_stage(self):
        self.error('move_replace_invalid',self.replace,before='before')
        self.error('move_replace_unavailable',self.replace,before=b'wrong')
        self.file.chmod(0o644);self.error('move_replace_unavailable',self.replace);self.file.chmod(0o600)
        os.link(self.file,self.root/'link');self.error('move_replace_unavailable',self.replace);(self.root/'link').unlink()
        self.file.unlink();self.file.symlink_to(self.neighbor);self.error('move_replace_unavailable',self.replace)
        self.assertEqual(self.neighbor.read_bytes(),b'keep');self.assertFalse(list(self.root.glob('.move-stage-*')))
    def test_visible_xattrs_refused(self):
        with patch.object(init.os,'listxattr',return_value=['user.synthetic']):self.error('move_replace_unavailable',self.replace)
        self.assertEqual(self.file.read_bytes(),b'before');self.assertFalse(list(self.root.glob('.move-stage-*')))
    def test_stage_error_keeps_old_file_and_partial_stage(self):
        with patch.object(stage.os,'write',side_effect=OSError('synthetic')):self.error('move_replace_unknown',self.replace)
        self.assertEqual(self.file.read_bytes(),b'before');self.assertEqual(len(list(self.root.glob('.move-stage-*'))),1)
    def test_fsync_and_replace_failures_are_unknown(self):
        for point in ('stage_sync','rename','parent_sync'):
            with self.subTest(point=point),tempfile.TemporaryDirectory() as t:
                root=Path(t);f=root/'registry.json';f.write_bytes(b'before');f.chmod(0o600);fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
                try:
                    real=os.fsync; calls=[]
                    def sync(fd):
                        calls.append(fd)
                        if len(calls)==(1 if point=='stage_sync' else 2):raise OSError('synthetic')
                        real(fd)
                    mock=patch.object(stage.os,'replace',side_effect=OSError('synthetic')) if point=='rename' else patch.object(stage.os,'fsync',side_effect=sync)
                    with mock:self.error('move_replace_unknown',stage._replace_for_move,fd,before=b'before',after=b'after')
                    self.assertEqual(f.read_bytes(),b'after' if point=='parent_sync' else b'before')
                    self.assertEqual(len(list(root.glob('.move-stage-*'))),0 if point=='parent_sync' else 1)
                finally:os.close(fd)
    def test_changes_during_staging_refuse_replacement(self):
        real=os.fsync
        def change(fd):real(fd);self.file.write_bytes(b'foreign');self.file.chmod(0o600)
        with patch.object(stage.os,'fsync',side_effect=change):self.error('move_replace_unknown',self.replace)
        self.assertEqual(self.file.read_bytes(),b'foreign');self.assertEqual(len(list(self.root.glob('.move-stage-*'))),1)
    def test_replaced_original_with_same_bytes_is_not_accepted(self):
        real=os.fsync
        def swap(fd):
            real(fd);self.file.rename(self.root/'original-retained');self.file.write_bytes(b'before');self.file.chmod(0o600)
        with patch.object(stage.os,'fsync',side_effect=swap):self.error('move_replace_unknown',self.replace)
        self.assertEqual(self.file.read_bytes(),b'before');self.assertEqual(len(list(self.root.glob('.move-stage-*'))),1)
    def test_unlink_recreate_same_bytes_refused_while_original_fd_is_held(self):
        real=os.fsync
        def swap(fd):
            real(fd);self.file.unlink();self.file.write_bytes(b'before');self.file.chmod(0o600)
        with patch.object(stage.os,'fsync',side_effect=swap):self.error('move_replace_unknown',self.replace)
        self.assertEqual(self.file.read_bytes(),b'before');self.assertEqual(len(list(self.root.glob('.move-stage-*'))),1)
    def test_changed_stage_and_zero_write_do_not_replace(self):
        real=os.fsync
        def change(fd):
            real(fd);path=next(self.root.glob('.move-stage-*'));path.write_bytes(b'foreign')
        with patch.object(stage.os,'fsync',side_effect=change):self.error('move_replace_unknown',self.replace)
        self.assertEqual(self.file.read_bytes(),b'before')
        with patch.object(stage.os,'write',return_value=0):self.error('move_replace_unknown',self.replace)
        self.assertEqual(self.file.read_bytes(),b'before');self.assertEqual(len(list(self.root.glob('.move-stage-*'))),2)
    def test_process_exit_before_and_after_replace(self):
        program=r'''import os,sys
sys.path.insert(0,sys.argv[1]);from kit import move_replace_stage as m
fd=os.open(sys.argv[2],os.O_RDONLY|os.O_DIRECTORY);point=sys.argv[3]
if point=='stage':
 real=os.fsync
 def stop(x):real(x);os._exit(77)
 os.fsync=stop
else:
 real=os.replace
 def stop(*a,**kw):real(*a,**kw);os._exit(77)
 os.replace=stop
m._replace_for_move(fd,before=b'before',after=b'after');os._exit(3)
'''
        for point in ('stage','replace'):
            with self.subTest(point=point), tempfile.TemporaryDirectory() as t:
                root=Path(t);f=root/'registry.json';f.write_bytes(b'before');f.chmod(0o600)
                proc=subprocess.run([sys.executable,'-I','-S','-B','-c',program,str(ROOT),str(root),point],capture_output=True,timeout=15)
                self.assertEqual(proc.returncode,77,proc.stderr);self.assertEqual(f.read_bytes(),b'before' if point=='stage' else b'after')
                self.assertEqual(len(list(root.glob('.move-stage-*'))),1 if point=='stage' else 0)

if __name__=='__main__':unittest.main()
