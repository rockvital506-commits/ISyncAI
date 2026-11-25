"""Опытная Linux-публикация нового workspace; не доверенная поставка или восстановление."""
from __future__ import annotations

import ctypes
import os
from pathlib import Path
import secrets
import sys
import threading

from kit import init_workspace as init
from kit.init_workspace import InitializationError
from kit.verify_candidate import HEX


def _rename_function():
    if sys.platform != 'linux' or not init._supported() or os.listdir not in os.supports_fd:
        raise InitializationError('atomic_platform_unsupported')
    try:
        function = ctypes.CDLL(None, use_errno=True).renameat2
        function.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
        function.restype = ctypes.c_int
        return function
    except (OSError, AttributeError) as error:
        raise InitializationError('atomic_platform_unsupported') from error


def _rename_noreplace(fd, old, new):
    function = _rename_function()
    if function(fd, os.fsencode(old), fd, os.fsencode(new), 1) != 0:  # RENAME_NOREPLACE
        number = ctypes.get_errno()
        raise OSError(number, os.strerror(number))


def _identity(info):
    return info.st_dev, info.st_ino


def _sync_verified_tree(root, files, uid, gid):
    """Проверяет закрытый состав и точные байты, fsync файлов и каталогов снизу вверх."""
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, 'O_CLOEXEC', 0)
    directories = {''}
    for path in files:
        components = path.split('/')[:-1]
        for i in range(1, len(components)+1): directories.add('/'.join(components[:i]))
    expected = {directory:set() for directory in directories}
    for path in directories - {''}:
        parent, _, name = path.rpartition('/'); expected[parent].add(name)
    for path in files:
        parent, _, name = path.rpartition('/'); expected[parent].add(name)
    opened = {'':root}
    try:
        init._check_new_fd(root, directory=True, uid=uid, gid=gid)
        for path in sorted(directories - {''}, key=lambda value:(value.count('/'), value)):
            parent, _, name = path.rpartition('/')
            fd = os.open(name, flags, dir_fd=opened[parent]); opened[path] = fd
            init._check_new_fd(fd, directory=True, uid=uid, gid=gid)
        for path, fd in opened.items():
            if set(os.listdir(fd)) != expected[path]: raise OSError('unexpected staging entries')
        for path, content in sorted(files.items()):
            parent, _, name = path.rpartition('/')
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, 'O_CLOEXEC', 0), dir_fd=opened[parent])
            try:
                init._check_new_fd(fd, directory=False, uid=uid, gid=gid)
                data = bytearray()
                while len(data) <= len(content):
                    part = os.read(fd, min(65536, len(content)+1-len(data)))
                    if not part: break
                    data.extend(part)
                if bytes(data) != content: raise OSError('staging contents changed')
                os.fsync(fd)
                init._check_new_fd(fd, directory=False, uid=uid, gid=gid)
            finally: os.close(fd)
        for path in sorted(opened, key=lambda value:(value.count('/'),value), reverse=True):
            os.fsync(opened[path])
    finally:
        for path in reversed(list(opened)):
            if path: os.close(opened[path])


class AtomicInitializationSession:
    """Один план и отдельное подтверждение; staging никогда не удаляется автоматически."""
    def __init__(self, destination, *, profile_root, l0_bytes, system_pin):
        self.destination = Path(destination)
        self.profile_root, self.l0_bytes, self.system_pin = profile_root, l0_bytes, system_pin
        self._pending = None
        self._lock = threading.Lock()

    def plan(self):
        if not self._lock.acquire(blocking=False): raise InitializationError('session_busy')
        try:
            self._pending = None
            _rename_function()
            destination = self.destination
            if not destination.is_absolute() or '..' in destination.parts or not destination.name:
                raise InitializationError('destination_invalid')
            fd, identity = init._open_parent(destination.parent)
            try:
                if init._occupied(fd, destination.name): raise InitializationError('destination_occupied')
            except OSError as error:
                raise InitializationError('parent_unavailable') from error
            finally: os.close(fd)
            staging = destination.parent / ('.domain-init-' + secrets.token_hex(16))
            inner = init.InitializationSession(staging, profile_root=self.profile_root,
                                               l0_bytes=self.l0_bytes, system_pin=self.system_pin)
            inner_plan = inner.plan()
            # Внутренний билет — деталь исполнения, а не второе пользовательское согласие.
            shown_staging = dict(inner_plan); del shown_staging['ticket']
            result = {'atomic_init_format':1, 'outcome':'planned', 'destination':str(destination),
                      'staging':shown_staging, 'publication':'linux_rename_noreplace_after_verified_fsync',
                      'failure':'leave_staging_or_outcome_unknown', 'ticket':secrets.token_hex(32)}
            self._pending = (init._canonical(result), inner, inner_plan, identity, result['ticket'], str(destination))
            return result
        finally: self._lock.release()

    def apply(self, plan, *, confirmed_ticket):
        if not self._lock.acquire(blocking=False): raise InitializationError('session_busy')
        try:
            if self._pending is None: raise InitializationError('ticket_unknown')
            saved, inner, inner_plan, identity, ticket, destination = self._pending
            if (type(confirmed_ticket) is not str or HEX.fullmatch(confirmed_ticket) is None
                    or not secrets.compare_digest(ticket, confirmed_ticket)):
                raise InitializationError('confirmation_required')
            self._pending = None
            try:
                if type(plan) is not dict or init._canonical(plan) != saved: raise InitializationError('plan_mismatch')
                if (str(self.destination) != destination or self.profile_root != inner.profile_root
                        or self.l0_bytes != inner.l0_bytes or self.system_pin != inner.system_pin):
                    raise InitializationError('stale_plan')
            except (TypeError, ValueError, RecursionError) as error:
                if isinstance(error, InitializationError): raise
                raise InitializationError('plan_mismatch') from error
            parent_fd, current = init._open_parent(self.destination.parent)
            try:
                if current != identity: raise InitializationError('stale_parent')
                try:
                    if init._occupied(parent_fd, self.destination.name): raise InitializationError('destination_occupied')
                except OSError as error:
                    raise InitializationError('parent_unavailable') from error
                # Любой сбой на этой стадии может оставить только staging; ничего не удаляем.
                try:
                    inner.apply(inner_plan, confirmed_ticket=inner_plan['ticket'])
                except InitializationError as error:
                    raise InitializationError('staging_partial_or_unverified') from error
                files = {row['path']:row['content_utf8'].encode('utf-8') for row in inner_plan['files']}
                stage_name = Path(inner_plan['destination']).name
                try:
                    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, 'O_CLOEXEC', 0)
                    stage_fd = os.open(stage_name, flags, dir_fd=parent_fd)
                    try:
                        stage_id = _identity(os.fstat(stage_fd))
                        _sync_verified_tree(stage_fd, files, inner_plan['uid'], inner_plan['gid'])
                        info = os.stat(stage_name, dir_fd=parent_fd, follow_symlinks=False)
                        if _identity(info) != stage_id: raise OSError('staging changed')
                        check_fd, latest = init._open_parent(self.destination.parent)
                        os.close(check_fd)
                        if latest != identity: raise OSError('parent changed')
                        os.fsync(parent_fd)
                    finally: os.close(stage_fd)
                except (OSError, ValueError, TypeError) as error:
                    raise InitializationError('staging_unverified') from error
                # Любой отказ или прерывание после вызова rename — неопределённый исход;
                # в том числе когда конечный каталог появился, но ответ не был доставлен.
                try:
                    _rename_noreplace(parent_fd, stage_name, self.destination.name)
                    os.fsync(parent_fd)
                except (OSError, InitializationError) as error:
                    raise InitializationError('publication_unknown') from error
            finally: os.close(parent_fd)
            return {'outcome':'published_unverified_origin', 'destination':destination,
                    'system_pin':self.system_pin, 'files':len(files)}
        finally: self._lock.release()
