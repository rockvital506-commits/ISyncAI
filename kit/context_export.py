"""Опытный экспорт явно выбранного контекста; не доставка агенту и не авторизация."""
from __future__ import annotations

import errno
import hashlib
import json
import os
from pathlib import Path
import secrets
import stat
import threading

from kit import init_workspace as init
from kit.base import context_modes, registry_store as store
from kit.base.registry_policy import StoreError
from kit.verify_candidate import HEX


def _artifact(report):
    return (json.dumps({'context_export_format':1,'outcome':'review_required',
                       'origin':'not_verified','authorization':'not_checked',
                       'agent_delivery':'not_checked','agent_application':'not_checked',
                       'context':report},ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n').encode('utf-8')


def _destination(layout,path):
    if not isinstance(path,Path) or not path.is_absolute() or '..' in path.parts or not path.name or path.name=='.move-pending':
        raise StoreError('context_export_destination_invalid','destination')
    workspace=store._workspace(layout.workspace)
    try:
        parent=path.parent.resolve(strict=True)
        target=parent/path.name
        if target==workspace or workspace in target.parents:raise StoreError('context_export_destination_invalid','destination')
        fd,identity=init._open_parent(path.parent)
        return fd,identity,workspace
    except StoreError:raise
    except (OSError,ValueError,TypeError,RuntimeError) as error:
        raise StoreError('context_export_parent_unavailable','destination') from error


def _report(layout,mode,scope,choices):
    return context_modes.prepare(layout,mode=mode,scope=scope,choices=choices)


def _publish(layout,path,mode,scope,choices,expected,location,workspace_identity,uid,gid):
    root=parent=fd=None;created=False
    try:
        if (not init._supported() or store.fcntl is None or not hasattr(os,'O_NONBLOCK')):
            raise StoreError('context_export_unavailable','workspace')
        workspace=store._workspace(layout.workspace)
        root=os.open(workspace,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|getattr(os,'O_CLOEXEC',0))
        info=os.fstat(root);named=os.stat(workspace,follow_symlinks=False)
        if not stat.S_ISDIR(info.st_mode) or (info.st_dev,info.st_ino)!=(named.st_dev,named.st_ino):raise OSError('workspace changed')
        if (info.st_dev,info.st_ino)!=workspace_identity:raise StoreError('stale_plan','workspace')
        try:store.fcntl.flock(root,store.fcntl.LOCK_SH|store.fcntl.LOCK_NB)
        except OSError as error:
            if error.errno in (errno.EACCES,errno.EAGAIN):raise StoreError('context_export_busy','workspace') from error
            raise
        if _artifact(_report(layout,mode,scope,choices))!=expected:raise StoreError('stale_plan','inputs')
        parent,current,latest_workspace=_destination(layout,path)
        if current!=location or latest_workspace!=workspace:raise StoreError('stale_plan','destination')
        try:fd=os.open(path.name,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|getattr(os,'O_CLOEXEC',0),0o600,dir_fd=parent)
        except FileExistsError as error:raise StoreError('context_export_destination_occupied','destination') from error
        created=True
        init._check_new_fd(fd,directory=False,uid=uid,gid=gid)
        remaining=memoryview(expected)
        while remaining:
            n=os.write(fd,remaining)
            if n<=0:raise OSError('short write')
            remaining=remaining[n:]
        init._check_new_fd(fd,directory=False,uid=uid,gid=gid)
        os.fsync(fd);os.lseek(fd,0,os.SEEK_SET);value=bytearray()
        while len(value)<len(expected):
            chunk=os.read(fd,min(65536,len(expected)-len(value)))
            if not chunk:raise OSError('short read')
            value.extend(chunk)
        if bytes(value)!=expected or os.read(fd,1):raise OSError('output changed')
        init._check_new_fd(fd,directory=False,uid=uid,gid=gid)
        named_file=os.stat(path.name,dir_fd=parent,follow_symlinks=False);opened=os.fstat(fd)
        if (named_file.st_dev,named_file.st_ino)!=(opened.st_dev,opened.st_ino):raise OSError('output changed')
        check,identity,other_workspace=_destination(layout,path)
        try:
            if identity!=location or other_workspace!=workspace:raise OSError('parent changed')
        finally:os.close(check)
        if _artifact(_report(layout,mode,scope,choices))!=expected:raise OSError('context changed')
        named=os.stat(workspace,follow_symlinks=False);opened=os.fstat(root)
        if (named.st_dev,named.st_ino)!=(opened.st_dev,opened.st_ino):raise OSError('workspace changed')
        os.fsync(parent)
    except StoreError as error:
        if created:raise StoreError('context_export_unknown','destination') from error
        raise
    except (OSError,ValueError,TypeError,AttributeError,NotImplementedError) as error:
        raise StoreError('context_export_unknown' if created else 'context_export_unavailable','destination') from error
    finally:
        failure=None
        for handle in (fd,parent,root):
            if handle is not None:
                try:os.close(handle)
                except OSError as error:failure=error
        if failure is not None:raise StoreError('context_export_unknown' if created else 'context_export_unavailable','destination') from failure
    return {'outcome':'context_file_created','destination':str(path),'sha256':hashlib.sha256(expected).hexdigest(),
            'authorization':'not_checked','origin':'not_verified','agent_delivery':'not_checked',
            'agent_application':'not_checked','durability':'fsync_calls_completed'}


class ContextExportSession:
    """Один видимый план и отдельный билет; не подтверждает владельца или применение."""
    def __init__(self,layout,destination,*,mode,scope,choices):
        self.layout=layout;self.destination=Path(destination);self.mode=mode;self.scope=scope;self.choices=choices
        self._pending=None;self._lock=threading.Lock()
    def cancel(self):
        if not self._lock.acquire(blocking=False):raise StoreError('session_busy','session')
        try:self._pending=None
        finally:self._lock.release()
    def plan(self):
        if not self._lock.acquire(blocking=False):raise StoreError('session_busy','session')
        try:
            self._pending=None
            report=_report(self.layout,self.mode,self.scope,self.choices);raw=_artifact(report)
            parent,identity,workspace=_destination(self.layout,self.destination)
            try:
                root_info=os.stat(workspace,follow_symlinks=False)
                if not stat.S_ISDIR(root_info.st_mode) or root_info.st_ino<=0:raise OSError('invalid workspace')
                workspace_identity=(root_info.st_dev,root_info.st_ino)
                if init._occupied(parent,self.destination.name):raise StoreError('context_export_destination_occupied','destination')
            except OSError as error:raise StoreError('context_export_parent_unavailable','destination') from error
            finally:os.close(parent)
            result={'outcome':'planned','destination':str(self.destination),'content_utf8':raw.decode('utf-8'),
                    'content_sha256':hashlib.sha256(raw).hexdigest(),'content_bytes':len(raw),
                    'mode':self.mode,'scope':self.scope,'inputs_sha256':report['inputs_sha256'],
                    'workspace':str(workspace),'workspace_identity':list(workspace_identity),
                    'uid':os.geteuid(),'gid':os.getegid(),'file_mode':'0600','effect':'create_new_file',
                    'failure':'leave_partial_or_unverified','origin':'not_verified','authorization':'not_checked',
                    'agent_delivery':'not_checked','agent_application':'not_checked','ticket':secrets.token_hex(32)}
            self._pending=(init._canonical(result),self.layout,str(self.destination),self.mode,self.scope,
                           init._canonical(self.choices),raw,identity,workspace_identity,(result['uid'],result['gid']),result['ticket'])
            return result
        finally:self._lock.release()
    def apply(self,plan,*,confirmed_ticket):
        if not self._lock.acquire(blocking=False):raise StoreError('session_busy','session')
        try:
            if self._pending is None:raise StoreError('ticket_unknown','ticket')
            saved,layout,destination,mode,scope,choices,raw,identity,workspace_identity,uidgid,ticket=self._pending
            if type(confirmed_ticket) is not str or HEX.fullmatch(confirmed_ticket) is None or not secrets.compare_digest(ticket,confirmed_ticket):
                raise StoreError('confirmation_required','confirmed_ticket')
            self._pending=None
            try:
                if type(plan) is not dict or init._canonical(plan)!=saved:raise StoreError('plan_mismatch','plan')
                if (self.layout!=layout or str(self.destination)!=destination or self.mode!=mode or self.scope!=scope or
                        init._canonical(self.choices)!=choices or (os.geteuid(),os.getegid())!=uidgid):
                    raise StoreError('stale_plan','inputs')
            except (ValueError,TypeError,RecursionError,UnicodeError) as error:
                if isinstance(error,StoreError):raise
                raise StoreError('plan_mismatch','plan') from error
            return _publish(layout,Path(destination),mode,scope,json.loads(choices),raw,identity,workspace_identity,*uidgid)
        finally:self._lock.release()
