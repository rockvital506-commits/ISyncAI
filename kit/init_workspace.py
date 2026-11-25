"""Опытное создание нового workspace; не доверенная доставка и не готовый установщик."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import secrets
import stat
import threading

from kit.base import registry_policy, schema_v2
from kit.verify_candidate import CANDIDATE_VERSION, HEX

MAX_L0 = 2_097_152


class InitializationError(ValueError):
    pass


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def _wire(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf-8')


def _files(raw, system_pin, profile_root):
    if type(raw) is not bytes or len(raw) > MAX_L0:
        raise InitializationError('system_invalid')
    if type(system_pin) is not str or HEX.fullmatch(system_pin) is None:
        raise InitializationError('system_pin_required')
    if hashlib.sha256(raw).hexdigest() != system_pin:
        raise InitializationError('system_pin_mismatch')
    try:
        l0 = schema_v2.validate_json(raw, expected_area='L0')
        if l0['roots'] != ['kit'] or l0['release_version'] != CANDIDATE_VERSION:
            raise InitializationError('system_incompatible')
        l1 = {'schema_version': 2, 'area': 'L1', 'roots': [profile_root], 'revision': 0, 'entries': []}
        l2 = {'schema_version': 2, 'area': 'L2', 'roots': ['.domain-agent-kit'], 'revision': 0, 'entries': []}
        documents = {'L0': l0, 'L1': l1, 'L2': l2}
        schema_v2.validate_catalog(documents)
        if registry_policy.find_conflicts(documents):
            raise InitializationError('structural_conflict')
        return {'kit/base/registry.json': raw, profile_root + '/registry.json': _wire(l1),
                '.domain-agent-kit/project/registry.json': _wire(l2)}
    except InitializationError:
        raise
    except (schema_v2.SchemaError, TypeError, ValueError, KeyError, RecursionError) as error:
        raise InitializationError('catalog_invalid') from error


def _supported():
    return (os.name == 'posix' and all(hasattr(os, n) for n in
            ('O_DIRECTORY', 'O_NOFOLLOW', 'getuid', 'geteuid', 'getegid', 'listxattr'))
            and os.open in os.supports_dir_fd and os.mkdir in os.supports_dir_fd
            and os.stat in os.supports_dir_fd)


def _open_parent(path):
    """Не следует ссылкам: открывает каждый существующий компонент от корня."""
    if not _supported():
        raise InitializationError('platform_unsupported')
    if not path.is_absolute() or '..' in path.parts:
        raise InitializationError('destination_invalid')
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, 'O_CLOEXEC', 0)
    fd = None
    try:
        fd = os.open(path.anchor, flags)
        for part in path.parts[1:]:
            next_fd = os.open(part, flags, dir_fd=fd)
            os.close(fd); fd = next_fd
        info = os.fstat(fd)
        if (not stat.S_ISDIR(info.st_mode) or info.st_ino <= 0 or info.st_dev < 0):
            raise OSError('invalid directory identity')
        return fd, (info.st_dev, info.st_ino)
    except (OSError, ValueError, TypeError) as error:
        if fd is not None: os.close(fd)
        raise InitializationError('parent_unavailable') from error


def _check_new_fd(fd, *, directory, uid, gid):
    info = os.fstat(fd)
    if (not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
            or stat.S_IMODE(info.st_mode) != (0o700 if directory else 0o600)
            or info.st_uid != uid or info.st_gid != gid or (not directory and info.st_nlink != 1)):
        raise InitializationError('new_metadata_unacceptable')
    try:
        if os.listxattr(fd):
            raise InitializationError('new_xattrs_present')
    except (OSError, TypeError, ValueError, NotImplementedError) as error:
        if isinstance(error, InitializationError): raise
        raise InitializationError('new_xattrs_unavailable') from error


def _occupied(fd, name):
    try:
        os.stat(name, dir_fd=fd, follow_symlinks=False)
        return True
    except FileNotFoundError:
        return False


def _build(fd, files, uid, gid):
    """Создаёт только новые объекты относительно открытого зарезервированного корня."""
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, 'O_CLOEXEC', 0)
    _check_new_fd(fd, directory=True, uid=uid, gid=gid)
    directories = set()
    for path in files:
        parts = path.split('/')[:-1]
        for i in range(1, len(parts)+1): directories.add('/'.join(parts[:i]))
    opened = {'': fd}
    try:
        for path in sorted(directories, key=lambda p: (p.count('/'), p)):
            parent, _, name = path.rpartition('/')
            os.mkdir(name, 0o700, dir_fd=opened[parent])
            child = os.open(name, flags, dir_fd=opened[parent]); opened[path] = child
            _check_new_fd(child, directory=True, uid=uid, gid=gid)
        for path, data in sorted(files.items()):
            parent, _, name = path.rpartition('/')
            f = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW |
                        getattr(os, 'O_CLOEXEC', 0), 0o600, dir_fd=opened[parent])
            try:
                _check_new_fd(f, directory=False, uid=uid, gid=gid)
                remaining = memoryview(data)
                while remaining:
                    n = os.write(f, remaining)
                    if n <= 0: raise OSError('short write')
                    remaining = remaining[n:]
                _check_new_fd(f, directory=False, uid=uid, gid=gid)
                os.lseek(f, 0, os.SEEK_SET)
                chunks = []; remaining_bytes = len(data)
                while remaining_bytes:
                    part = os.read(f, min(remaining_bytes, 65536))
                    if not part: raise OSError('short read')
                    chunks.append(part); remaining_bytes -= len(part)
                if b''.join(chunks) != data or os.read(f, 1):
                    raise OSError('verification failed')
            finally:
                os.close(f)
    finally:
        for path in reversed(list(opened)):
            if path: os.close(opened[path])


class InitializationSession:
    """Один план; локальный pin и билет не удостоверяют источник, полномочия или согласие."""
    def __init__(self, destination, *, profile_root, l0_bytes, system_pin):
        self.destination = Path(destination)
        self.profile_root, self.l0_bytes, self.system_pin = profile_root, l0_bytes, system_pin
        self._pending = None
        self._lock = threading.Lock()

    def plan(self):
        if not self._lock.acquire(blocking=False): raise InitializationError('session_busy')
        try:
            self._pending = None
            path = self.destination
            if not path.is_absolute() or '..' in path.parts or not path.name or path.name in ('.', '..'):
                raise InitializationError('destination_invalid')
            files = _files(self.l0_bytes, self.system_pin, self.profile_root)
            parent_fd, identity = _open_parent(path.parent)
            try:
                if _occupied(parent_fd, path.name): raise InitializationError('destination_occupied')
            except OSError as error:
                raise InitializationError('parent_unavailable') from error
            finally: os.close(parent_fd)
            uid, gid = os.geteuid(), os.getegid()
            directories = sorted({'/'.join(p.split('/')[:i]) for p in files
                                  for i in range(1, len(p.split('/')))}, key=lambda p: (p.count('/'), p))
            rows = [{'path': p, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                     'content_utf8': data.decode('utf-8')} for p, data in sorted(files.items())]
            plan = {'outcome':'planned', 'destination':str(path), 'candidate_version':CANDIDATE_VERSION,
                    'system_pin':self.system_pin, 'profile_root':self.profile_root, 'uid':uid, 'gid':gid,
                    'directory_mode':'0700', 'file_mode':'0600', 'directories':directories, 'files':rows,
                    'origin':'not_verified', 'l0_semantics':'not_checked', 'publication':'non_atomic_partial_on_failure',
                    'existing_destination':'refuse', 'ticket':secrets.token_hex(32)}
            self._pending = (_canonical(plan), files, identity, uid, gid, plan['ticket'])
            return plan
        finally: self._lock.release()

    def apply(self, plan, *, confirmed_ticket):
        if not self._lock.acquire(blocking=False): raise InitializationError('session_busy')
        try:
            if self._pending is None: raise InitializationError('ticket_unknown')
            saved, files, identity, uid, gid, ticket = self._pending
            if (type(confirmed_ticket) is not str or HEX.fullmatch(confirmed_ticket) is None
                    or not secrets.compare_digest(confirmed_ticket, ticket)):
                raise InitializationError('confirmation_required')
            self._pending = None
            try:
                if type(plan) is not dict or _canonical(plan) != saved: raise InitializationError('plan_mismatch')
                if (self.system_pin != plan['system_pin'] or self.profile_root != plan['profile_root']
                        or str(self.destination) != plan['destination'] or self.l0_bytes != files['kit/base/registry.json']
                        or (os.geteuid(), os.getegid()) != (uid, gid)):
                    raise InitializationError('stale_plan')
            except (TypeError, ValueError, RecursionError) as error:
                if isinstance(error, InitializationError): raise
                raise InitializationError('plan_mismatch') from error
            parent_fd, current_identity = _open_parent(self.destination.parent)
            try:
                if current_identity != identity: raise InitializationError('stale_parent')
                try:
                    os.mkdir(self.destination.name, 0o700, dir_fd=parent_fd)
                except FileExistsError as error:
                    raise InitializationError('destination_occupied') from error
                except OSError as error:
                    raise InitializationError('destination_unavailable') from error
                try:
                    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, 'O_CLOEXEC', 0)
                    root = os.open(self.destination.name, flags, dir_fd=parent_fd)
                    try: _build(root, files, uid, gid)
                    finally: os.close(root)
                except (OSError, InitializationError, ValueError) as error:
                    raise InitializationError('destination_partial_or_unverified') from error
            finally: os.close(parent_fd)
            return {'outcome':'created_unverified_origin', 'destination':str(self.destination),
                    'system_pin':self.system_pin, 'files':len(files)}
        finally: self._lock.release()
