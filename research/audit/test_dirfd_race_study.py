#!/usr/bin/env python3
"""Исследовательские примитивы в частном временном каталоге; не механизм записи Kit."""
import errno
import os
import stat
import tempfile
import unittest
from pathlib import Path

SUPPORTED = (os.name == 'posix' and all(hasattr(os, x) for x in ('O_DIRECTORY', 'O_NOFOLLOW'))
             and all(fn in os.supports_dir_fd for fn in (os.open, os.stat, os.unlink, os.rename)))
UNSUPPORTED = {getattr(errno, n) for n in ('ENOTSUP', 'EOPNOTSUPP', 'ENOSYS') if hasattr(errno, n)}
OLD = b'synthetic-original\n'
NEW = b'synthetic-approved\n'
POISON = b'synthetic-unapproved\n'
DECOY = b'synthetic-decoy\n'


@unittest.skipUnless(SUPPORTED, 'POSIX dir_fd/O_NOFOLLOW API unavailable; not_run')
class DirfdStudy(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='isync-dirfd-study-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.parent = self.root/'catalog'; self.parent.mkdir()
        self.target = self.parent/'registry.json'; self.target.write_bytes(OLD)
        self.decoy = self.root/'decoy'; self.decoy.mkdir()
        (self.decoy/'registry.json').write_bytes(DECOY)
        self.fd = os.open(self.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        self.addCleanup(os.close, self.fd)
        try:
            # Независимая capability-проба; не делает отказ тестируемого сценария пропуском.
            fd = os.open('capability', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=self.fd)
            os.close(fd)
            os.stat('capability', dir_fd=self.fd, follow_symlinks=False)
            os.rename('capability', 'capability-renamed', src_dir_fd=self.fd, dst_dir_fd=self.fd)
            os.unlink('capability-renamed', dir_fd=self.fd)
            link = self.root/'capability-link'; link.symlink_to(self.decoy, target_is_directory=True); link.unlink()
        except OSError as error:
            if error.errno in UNSUPPORTED:
                self.skipTest('ФС не поддерживает capability-пробу; not_run')
            raise

    def identity(self, name):
        s = os.stat(name, dir_fd=self.fd, follow_symlinks=False)
        return (s.st_dev, s.st_ino, stat.S_IFMT(s.st_mode))

    def stage(self):
        fd = os.open('staged', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(NEW); stream.flush()
                info = os.fstat(stream.fileno())
                return info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode)
        except BaseException:
            # fdopen owns the descriptor after a successful call.
            raise

    def replace(self):
        os.rename('staged', 'registry.json', src_dir_fd=self.fd, dst_dir_fd=self.fd)

    def swap_stage(self):
        # Сохранить исходный inode занятым: после unlink ФС может переиспользовать его номер.
        os.rename('staged', 'staged-moved', src_dir_fd=self.fd, dst_dir_fd=self.fd)
        fd = os.open('staged', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        with os.fdopen(fd, 'wb') as f: f.write(POISON)

    def swap_target(self):
        os.rename('registry.json', 'original-moved', src_dir_fd=self.fd, dst_dir_fd=self.fd)
        fd = os.open('registry.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        with os.fdopen(fd, 'wb') as f: f.write(DECOY)

    def test_normal_rename(self):
        identity = self.stage(); self.assertEqual(identity, self.identity('staged'))
        self.replace(); self.assertEqual(self.target.read_bytes(), NEW)
        self.assertEqual((self.decoy/'registry.json').read_bytes(), DECOY)

    def test_directory_rename_keeps_fd_bound_but_changes_visible_location(self):
        self.stage()
        parked = self.root/'parked'; self.parent.rename(parked)
        (self.decoy/'staged').write_bytes(POISON)
        self.parent.symlink_to(self.decoy, target_is_directory=True)
        self.replace()
        self.assertEqual((parked/'registry.json').read_bytes(), NEW)
        self.assertEqual((self.decoy/'registry.json').read_bytes(), DECOY)
        self.assertEqual(self.target.read_bytes(), DECOY)
        self.assertEqual((self.decoy/'staged').read_bytes(), POISON)

    def test_open_directory_nofollow_rejects_final_symlink(self):
        link = self.root/'link'; link.symlink_to(self.decoy, target_is_directory=True)
        with self.assertRaises(OSError):
            fd = os.open(link, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            os.close(fd)

    def test_open_staged_nofollow_rejects_final_symlink(self):
        (self.parent/'staged').symlink_to(self.decoy/'registry.json')
        with self.assertRaises(OSError):
            fd = os.open('staged', os.O_RDONLY | os.O_NOFOLLOW, dir_fd=self.fd)
            os.close(fd)
        self.assertEqual((self.decoy/'registry.json').read_bytes(), DECOY)

    def test_stage_name_can_be_substituted_after_open_fd_closed(self):
        identity = self.stage(); self.swap_stage()
        self.assertNotEqual(identity, self.identity('staged'))
        self.replace(); self.assertEqual(self.target.read_bytes(), POISON)

    def test_stage_identity_check_detects_early_substitution(self):
        identity = self.stage(); self.swap_stage()
        self.assertNotEqual(identity, self.identity('staged'))
        self.assertEqual(self.target.read_bytes(), OLD)

    def test_stage_identity_check_does_not_close_later_window(self):
        identity = self.stage(); self.assertEqual(identity, self.identity('staged'))
        self.swap_stage(); self.replace()
        self.assertEqual(self.target.read_bytes(), POISON)

    def test_same_inode_can_have_different_bytes(self):
        identity = self.stage()
        fd = os.open('staged', os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW, dir_fd=self.fd)
        with os.fdopen(fd, 'wb') as f: f.write(POISON)
        self.assertEqual(identity, self.identity('staged'))
        self.replace(); self.assertEqual(self.target.read_bytes(), POISON)

    def test_target_change_after_identity_check_is_overwritten(self):
        original = self.identity('registry.json'); self.stage()
        self.assertEqual(original, self.identity('registry.json'))
        self.swap_target(); self.assertNotEqual(original, self.identity('registry.json'))
        self.replace()
        self.assertEqual(self.target.read_bytes(), NEW)
        self.assertEqual((self.parent/'original-moved').read_bytes(), OLD)
        # Файл DECOY был на целевом имени и перезаписан; compare-then-rename не CAS.

    def test_target_identity_check_detects_early_substitution(self):
        original = self.identity('registry.json'); self.stage(); self.swap_target()
        self.assertNotEqual(original, self.identity('registry.json'))
        self.assertEqual(self.target.read_bytes(), DECOY)
        self.assertEqual((self.parent/'original-moved').read_bytes(), OLD)


if __name__ == '__main__': unittest.main()
