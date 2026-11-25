"""Ограниченное наблюдение имени после atomic init; никогда не восстанавливает и не удаляет."""
from __future__ import annotations

import os
from pathlib import Path
import re
import stat

from kit import init_workspace as init
from kit.init_workspace import InitializationError

_STAGING = re.compile(r'\.domain-init-[0-9a-f]{32}\Z')


def _observe(parent, name, files, uid, gid):
    """Однократный осмотр, без утверждения об атомарном снимке или авторстве дерева."""
    try:
        os.stat(name, dir_fd=parent, follow_symlinks=False)
    except FileNotFoundError:
        return 'absent'
    except OSError:
        return 'unavailable'
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, 'O_CLOEXEC', 0)
    opened = {}
    try:
        root = os.open(name, flags, dir_fd=parent); opened[''] = root
        init._check_new_fd(root, directory=True, uid=uid, gid=gid)
        directories = {''}
        for path in files:
            parts = path.split('/')[:-1]
            for n in range(1, len(parts)+1): directories.add('/'.join(parts[:n]))
        expected = {path:set() for path in directories}
        for path in directories - {''}:
            parent_path, _, child = path.rpartition('/'); expected[parent_path].add(child)
        for path in files:
            parent_path, _, child = path.rpartition('/'); expected[parent_path].add(child)
        for path in sorted(directories - {''}, key=lambda x:(x.count('/'), x)):
            parent_path, _, child = path.rpartition('/')
            fd = os.open(child, flags, dir_fd=opened[parent_path]); opened[path] = fd
            init._check_new_fd(fd, directory=True, uid=uid, gid=gid)
        for path, fd in opened.items():
            if set(os.listdir(fd)) != expected[path]: return 'different'
        for path, data in sorted(files.items()):
            parent_path, _, child = path.rpartition('/')
            info = os.stat(child, dir_fd=opened[parent_path], follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode): return 'different'
            fd = os.open(child, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK |
                         getattr(os, 'O_CLOEXEC', 0), dir_fd=opened[parent_path])
            try:
                init._check_new_fd(fd, directory=False, uid=uid, gid=gid)
                before = os.fstat(fd)
                if before.st_size != len(data): return 'different'
                chunks = bytearray()
                while len(chunks) < len(data):
                    part = os.read(fd, min(65536, len(data)-len(chunks)))
                    if not part: return 'different'
                    chunks.extend(part)
                after = os.fstat(fd)
                if (bytes(chunks) != data or os.read(fd, 1) or
                        (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) !=
                        (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
                    return 'different'
                init._check_new_fd(fd, directory=False, uid=uid, gid=gid)
            finally: os.close(fd)
        # Имя root могло быть заменено во время осмотра.
        current = os.stat(name, dir_fd=parent, follow_symlinks=False)
        root_info = os.fstat(root)
        if not stat.S_ISDIR(current.st_mode) or (current.st_dev,current.st_ino) != (root_info.st_dev,root_info.st_ino):
            return 'unavailable'
        return 'matches_observation'
    except InitializationError:
        return 'different'
    except (FileNotFoundError, NotADirectoryError, IsADirectoryError):
        return 'different'
    except OSError:
        return 'unavailable'
    finally:
        for fd in reversed(list(opened.values())): os.close(fd)


def inspect(destination, staging, *, profile_root, l0_bytes, system_pin):
    """Сравнить оба явных имени с исходным ожидаемым деревом; не менять состояние."""
    if not init._supported() or os.listdir not in os.supports_fd or not hasattr(os, 'O_NONBLOCK'):
        raise InitializationError('inspection_platform_unsupported')
    try:
        destination, staging = Path(destination), Path(staging)
        if (not destination.is_absolute() or '..' in destination.parts or not destination.name
                or not staging.is_absolute() or '..' in staging.parts or staging.parent != destination.parent
                or _STAGING.fullmatch(staging.name) is None or staging == destination):
            raise InitializationError('inspection_paths_invalid')
    except (TypeError, ValueError) as error:
        if isinstance(error, InitializationError): raise
        raise InitializationError('inspection_paths_invalid') from error
    files = init._files(l0_bytes, system_pin, profile_root)
    parent, identity = init._open_parent(destination.parent)
    try:
        uid, gid = os.geteuid(), os.getegid()
        target = _observe(parent, destination.name, files, uid, gid)
        stage = _observe(parent, staging.name, files, uid, gid)
        check, latest = init._open_parent(destination.parent)
        os.close(check)
        if identity != latest: raise InitializationError('inspection_parent_changed')
    finally: os.close(parent)
    return {'outcome':'observation_only', 'destination':str(destination), 'staging':str(staging),
            'destination_state':target, 'staging_state':stage, 'system_pin':system_pin,
            'origin':'not_verified', 'authorization':'not_verified', 'durability':'not_verified',
            'recovery':'not_performed', 'snapshot':'not_atomic'}
