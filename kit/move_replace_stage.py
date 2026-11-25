"""Внутренняя опытная замена одного файла для будущего move; не публичная операция."""
from __future__ import annotations

import os
import secrets
import stat

from kit import init_workspace as init, move_recovery_inspect as probe
from kit.base import move_intent
from kit.base.registry_policy import StoreError


def _replace_for_move(parent_fd, *, before, after):
    """Заменить registry.json в уже закреплённом каталоге; caller обеспечивает все блокировки.

    Не выполняет перенос, не открывает marker, не проверяет остальные реестры, источник,
    разрешения, подтверждение или цепочку родительских каталогов. Нельзя применять к реальным
    данным: самостоятельного защищённого интерфейса этот примитив не предоставляет.
    """
    if (type(parent_fd) is not int or type(before) is not bytes or type(after) is not bytes
            or len(before) > move_intent._MAX_INPUT or len(after) > move_intent._MAX_INPUT):
        raise StoreError('move_replace_invalid', 'registry')
    if (not init._supported() or os.rename not in os.supports_dir_fd or not hasattr(os, 'O_NONBLOCK')):
        raise StoreError('move_replace_unavailable', 'registry')
    made = False
    fd = None
    original_fd = None
    stage = '.move-stage-' + secrets.token_hex(16)
    flags = os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, 'O_CLOEXEC', 0)

    def verify(name, expected):
        initial = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        data = probe._read(parent_fd, name, move_intent._MAX_INPUT)
        handle = os.open(name, os.O_RDONLY | flags, dir_fd=parent_fd)
        try:
            init._check_new_fd(handle, directory=False, uid=os.geteuid(), gid=os.getegid())
            if probe._identity(initial) != probe._identity(os.fstat(handle)) or data != expected:
                raise OSError('file changed')
            if probe._identity(initial) != probe._identity(os.stat(name, dir_fd=parent_fd, follow_symlinks=False)):
                raise OSError('file changed')
            return probe._identity(initial)
        finally:
            os.close(handle)

    try:
        if not stat.S_ISDIR(os.fstat(parent_fd).st_mode):
            raise OSError('parent not directory')
        initial = verify('registry.json', before)
        original_fd = os.open('registry.json', os.O_RDONLY | flags, dir_fd=parent_fd)
        init._check_new_fd(original_fd, directory=False, uid=os.geteuid(), gid=os.getegid())
        if probe._identity(os.fstat(original_fd)) != initial: raise OSError('registry changed')
        fd = os.open(stage, os.O_RDWR | os.O_CREAT | os.O_EXCL | flags, 0o600, dir_fd=parent_fd)
        made = True
        init._check_new_fd(fd, directory=False, uid=os.geteuid(), gid=os.getegid())
        remaining = memoryview(after)
        while remaining:
            written = os.write(fd, remaining)
            if written <= 0: raise OSError('short write')
            remaining = remaining[written:]
        init._check_new_fd(fd, directory=False, uid=os.geteuid(), gid=os.getegid())
        os.fsync(fd)
        stage_identity = probe._identity(os.fstat(fd))
        if verify(stage, after) != stage_identity: raise OSError('stage changed')
        if (verify('registry.json', before) != initial or
                probe._identity(os.fstat(original_fd)) != initial): raise OSError('registry changed')
        if probe._identity(os.stat(stage, dir_fd=parent_fd, follow_symlinks=False)) != stage_identity:
            raise OSError('stage changed')
        os.replace(stage, 'registry.json', src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        os.fsync(parent_fd)
        replaced = verify('registry.json', after)
        if replaced[:2] != stage_identity[:2]: raise OSError('replacement changed')
    except (OSError, ValueError, TypeError, AttributeError, NotImplementedError) as error:
        raise StoreError('move_replace_unknown' if made else 'move_replace_unavailable', 'registry') from error
    finally:
        failure = None
        for handle in (fd, original_fd):
            if handle is not None:
                try: os.close(handle)
                except OSError as error: failure = error
        if failure is not None:
            raise StoreError('move_replace_unknown' if made else 'move_replace_unavailable', 'registry') from failure
    return {'outcome': 'single_file_replaced', 'durability': 'fsync_calls_completed',
            'move': 'not_implemented', 'recovery': 'not_implemented'}
