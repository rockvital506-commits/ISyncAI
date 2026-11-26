#!/usr/bin/env python3
"""Ограниченное чтение намерения переноса; не восстановление и не разрешение на запись."""
from __future__ import annotations

import argparse
import errno
import json
import os
from pathlib import Path
import stat
import sys

if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kit.base import move_intent, move_preview, registry_store
from kit.base.registry_policy import StoreError


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink, info.st_uid, info.st_gid,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _directory(parent, name):
    flags=os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os,'O_CLOEXEC',0)
    fd=os.open(name,flags,dir_fd=parent)
    try:
        opened=os.fstat(fd); named=os.stat(name,dir_fd=parent,follow_symlinks=False)
        if (not stat.S_ISDIR(opened.st_mode) or not stat.S_ISDIR(named.st_mode) or opened.st_ino <= 0
                or (opened.st_dev,opened.st_ino)!=(named.st_dev,named.st_ino)):
            raise OSError('directory changed')
        return fd
    except BaseException:
        os.close(fd);raise


def _read(parent, name, limit):
    before=os.stat(name,dir_fd=parent,follow_symlinks=False)
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size < 0 or before.st_size > limit:
        raise OSError('unsafe file')
    flags=os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os,'O_CLOEXEC',0)
    fd=os.open(name,flags,dir_fd=parent)
    try:
        first=os.fstat(fd)
        if _identity(first)!=_identity(before) or not stat.S_ISREG(first.st_mode):raise OSError('file changed')
        chunks=bytearray()
        while len(chunks) <= limit:
            part=os.read(fd,min(65536,limit+1-len(chunks)))
            if not part:break
            chunks.extend(part)
        last=os.fstat(fd);named=os.stat(name,dir_fd=parent,follow_symlinks=False)
        if len(chunks)>limit or len(chunks)!=first.st_size or _identity(first)!=_identity(last) or _identity(last)!=_identity(named):
            raise OSError('file changed')
        return bytes(chunks)
    finally:os.close(fd)


def _check_intent_roots(layout, before):
    """Привязать корни проверенного intent к явно выбранной физической раскладке."""
    roots=registry_store._declared_roots(layout)
    docs,_=move_preview._parse(before)
    for area in ('L0','L1','L2'):
        if docs[area]['roots']!=[roots[area]]:
            raise StoreError('move_probe_root_mismatch',area)


def _inspect(layout, *, intent_pin, exclusive_held):
    """exclusive_held допустим только внутри штатной EX-блокировки того же workspace."""
    if (os.name!='posix' or registry_store.fcntl is None or not hasattr(os,'O_NOFOLLOW')
            or not hasattr(os,'O_DIRECTORY') or not hasattr(os,'O_NONBLOCK')
            or os.open not in os.supports_dir_fd or os.stat not in os.supports_dir_fd):
        raise StoreError('move_probe_unavailable','workspace')
    roots=registry_store._declared_roots(layout)
    workspace=registry_store._workspace(layout.workspace)
    opened=[]; bindings=[]
    def child(parent,name):
        fd=_directory(parent,name);opened.append(fd);bindings.append((parent,name,fd));return fd
    try:
        flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|getattr(os,'O_CLOEXEC',0)
        root=os.open(workspace,flags);opened.append(root)
        info=os.fstat(root);named=os.stat(workspace,follow_symlinks=False)
        if (not stat.S_ISDIR(info.st_mode) or not stat.S_ISDIR(named.st_mode) or info.st_ino <= 0
                or (info.st_dev,info.st_ino)!=(named.st_dev,named.st_ino)):raise OSError('workspace changed')
        if not exclusive_held:
            try:registry_store.fcntl.flock(root,registry_store.fcntl.LOCK_SH|registry_store.fcntl.LOCK_NB)
            except OSError as error:
                if error.errno in (errno.EAGAIN,errno.EACCES):raise StoreError('move_probe_busy','workspace') from error
                raise
        # Только заранее валидированные компоненты; ссылки не проходят на каждом уровне.
        root_fds={}
        for area,path in roots.items():
            fd=root
            for component in path.split('/'):
                fd=child(fd,component)
            root_fds[area]=fd
        ids=[(os.fstat(fd).st_dev,os.fstat(fd).st_ino) for fd in root_fds.values()]
        if len(set(ids))!=3:raise OSError('root alias')
        registry_store._refuse_profile_copy_stages_fd(root_fds['L1'])
        marker=_read(root_fds['L2'],'.move-pending',move_intent.MAX_INTENT)
        # Некорректный marker/pin отвергаем до открытия реестров.
        _,before,_=move_intent._verified(marker,intent_pin)
        _check_intent_roots(layout,before)
        observed={}
        for area in ('L0','L1','L2'):
            components=registry_store._SUFFIX[area].split('/');fd=root_fds[area]
            for component in components[:-1]:
                fd=child(fd,component)
            observed[area]=_read(fd,components[-1],move_intent._MAX_INPUT)
        for parent,name,fd in bindings:
            expected=os.fstat(fd);current_child=os.stat(name,dir_fd=parent,follow_symlinks=False)
            if (not stat.S_ISDIR(current_child.st_mode) or
                    (expected.st_dev,expected.st_ino)!=(current_child.st_dev,current_child.st_ino)):
                raise OSError('directory changed')
        current=os.stat(workspace,follow_symlinks=False)
        if not stat.S_ISDIR(current.st_mode) or (info.st_dev,info.st_ino)!=(current.st_dev,current.st_ino):raise OSError('workspace changed')
        result=move_intent.assess(marker,intent_pin=intent_pin,observed=observed)
        result['marker']='present_and_pin_matched'
        result['snapshot']='cooperative_lock_only'
        return result
    except StoreError:
        raise
    except (OSError,ValueError,TypeError,AttributeError,NotImplementedError) as error:
        raise StoreError('move_probe_unavailable','workspace') from error
    finally:
        release_error=None
        for fd in reversed(opened):
            try:os.close(fd)
            except OSError as error:release_error=error
        if release_error is not None:raise StoreError('move_probe_release_failed','workspace') from release_error


def inspect(layout, *, intent_pin):
    """Не очищает marker, не исполняет восстановление; источник не удостоверяет."""
    return _inspect(layout,intent_pin=intent_pin,exclusive_held=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',type=Path,required=True)
    parser.add_argument('--profile-root',required=True)
    parser.add_argument('--intent-pin',required=True)
    args=parser.parse_args()
    try:result=inspect(registry_store.Layout(args.workspace,args.profile_root),intent_pin=args.intent_pin)
    except StoreError as error:
        print(json.dumps({'outcome':'error','diagnostic':error.diagnostic()},ensure_ascii=False,sort_keys=True));return 1
    print(json.dumps(result,ensure_ascii=False,sort_keys=True));return 0

if __name__=='__main__':raise SystemExit(main())
