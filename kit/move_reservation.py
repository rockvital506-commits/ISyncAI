"""Опытное резервирование нетронутого intent: не выполнение перемещения или recovery."""
from __future__ import annotations

import os
from pathlib import Path
import secrets
import threading

from kit import init_workspace as init, move_recovery_inspect as probe
from kit.base import move_intent, move_preview, registry_store as store
from kit.base.registry_policy import StoreError
from kit.verify_candidate import HEX

_MARKER='.move-pending'


def _root_and_project(layout):
    workspace=store._workspace(layout.workspace)
    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|getattr(os,'O_CLOEXEC',0)
    root=os.open(workspace,flags)
    try:
        info=os.fstat(root);named=os.stat(workspace,follow_symlinks=False)
        if (info.st_dev,info.st_ino)!=(named.st_dev,named.st_ino):raise OSError('workspace changed')
        project=probe._directory(root,'.domain-agent-kit')
        return root,project
    except BaseException:
        os.close(root);raise


def _locations(layout):
    root=project=None
    try:
        root,project=_root_and_project(layout)
        a,b=os.fstat(root),os.fstat(project)
        return (a.st_dev,a.st_ino,b.st_dev,b.st_ino)
    except OSError as error:
        raise StoreError('move_reservation_unavailable','workspace') from error
    finally:
        for fd in (project,root):
            if fd is not None:os.close(fd)


@store._serialized_write
def _reserve(layout, raw, pin, location):
    doc,before,_=move_intent._verified(raw,pin)
    current=store._load_unlocked(layout)
    if current.raw!=before:raise StoreError('stale_plan','inputs')
    root=project=None;reserved=False
    try:
        root,project=_root_and_project(layout)
        a,b=os.fstat(root),os.fstat(project)
        if (a.st_dev,a.st_ino,b.st_dev,b.st_ino)!=location:raise StoreError('stale_plan','workspace')
        try:fd=os.open(_MARKER,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|getattr(os,'O_CLOEXEC',0),0o600,dir_fd=project)
        except FileExistsError as error:raise StoreError('move_pending','.domain-agent-kit/.move-pending') from error
        reserved=True
        try:
            init._check_new_fd(fd,directory=False,uid=os.geteuid(),gid=os.getegid())
            remaining=memoryview(raw)
            while remaining:
                n=os.write(fd,remaining)
                if n<=0:raise OSError('short write')
                remaining=remaining[n:]
            init._check_new_fd(fd,directory=False,uid=os.geteuid(),gid=os.getegid())
            os.fsync(fd);os.lseek(fd,0,os.SEEK_SET);value=bytearray()
            while len(value)<len(raw):
                part=os.read(fd,min(65536,len(raw)-len(value)))
                if not part:raise OSError('short read')
                value.extend(part)
            if bytes(value)!=raw or os.read(fd,1):raise OSError('marker changed')
            init._check_new_fd(fd,directory=False,uid=os.geteuid(),gid=os.getegid())
            named=os.stat(_MARKER,dir_fd=project,follow_symlinks=False);opened=os.fstat(fd)
            if probe._identity(named)!=probe._identity(opened):raise OSError('marker changed')
            parent=os.stat('.domain-agent-kit',dir_fd=root,follow_symlinks=False);opened_parent=os.fstat(project)
            named_root=os.stat(store._workspace(layout.workspace),follow_symlinks=False);opened_root=os.fstat(root)
            if ((parent.st_dev,parent.st_ino)!=(opened_parent.st_dev,opened_parent.st_ino) or
                    (named_root.st_dev,named_root.st_ino)!=(opened_root.st_dev,opened_root.st_ino)):
                raise OSError('parent changed')
            os.fsync(project)
        finally:os.close(fd)
    except StoreError as error:
        if reserved:raise StoreError('move_reservation_unknown','workspace') from error
        raise
    except (OSError,ValueError,TypeError,init.InitializationError) as error:
        raise StoreError('move_reservation_unknown' if reserved else 'move_reservation_unavailable','workspace') from error
    finally:
        failure=None
        for fd in (project,root):
            if fd is not None:
                try:os.close(fd)
                except OSError as error:failure=error
        if failure is not None:raise StoreError('move_reservation_unknown' if reserved else 'move_reservation_unavailable','workspace') from failure
    return {'outcome':'reserved_not_moved','intent_sha256':pin,'source':doc['source'],'target':doc['target'],
            'recovery':'not_implemented','move':'not_implemented'}


@store._serialized_write
def _cancel_reservation(layout, pin, expected, location):
    result=probe._inspect(layout,intent_pin=pin,exclusive_held=True)
    if result['state']!='before_both' or result['observed_sha256']!=expected:
        raise StoreError('move_reservation_stale','inputs')
    root=project=None;attempted=False
    try:
        root,project=_root_and_project(layout)
        a,b=os.fstat(root),os.fstat(project)
        if (a.st_dev,a.st_ino,b.st_dev,b.st_ino)!=location:raise StoreError('stale_plan','workspace')
        prior=os.stat(_MARKER,dir_fd=project,follow_symlinks=False)
        raw=probe._read(project,_MARKER,move_intent.MAX_INTENT)
        move_intent._verified(raw,pin)
        fd=os.open(_MARKER,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|getattr(os,'O_CLOEXEC',0),dir_fd=project)
        try:
            init._check_new_fd(fd,directory=False,uid=os.geteuid(),gid=os.getegid())
            if probe._identity(prior)!=probe._identity(os.fstat(fd)):raise OSError('marker changed')
        finally:os.close(fd)
        after=os.stat(_MARKER,dir_fd=project,follow_symlinks=False)
        if probe._identity(prior)!=probe._identity(after):raise OSError('marker changed')
        parent=os.stat('.domain-agent-kit',dir_fd=root,follow_symlinks=False);opened=os.fstat(project)
        named_root=os.stat(store._workspace(layout.workspace),follow_symlinks=False);opened_root=os.fstat(root)
        if ((parent.st_dev,parent.st_ino)!=(opened.st_dev,opened.st_ino) or
                (named_root.st_dev,named_root.st_ino)!=(opened_root.st_dev,opened_root.st_ino)):
            raise OSError('parent changed')
        attempted=True
        os.unlink(_MARKER,dir_fd=project)
        os.fsync(project)
    except StoreError:
        raise
    except (OSError,ValueError,TypeError) as error:
        raise StoreError('move_cancel_unknown' if attempted else 'move_cancel_unavailable','workspace') from error
    finally:
        failure=None
        for fd in (project,root):
            if fd is not None:
                try:os.close(fd)
                except OSError as error:failure=error
        if failure is not None:raise StoreError('move_cancel_unknown' if attempted else 'move_cancel_unavailable','workspace') from failure
    return {'outcome':'reservation_cancelled','intent_sha256':pin,'move':'not_implemented'}


class ReservationSession:
    """Один план и отдельный билет; не проверяет владельца, права или доверенный источник."""
    def __init__(self,layout,*,intent_bytes,intent_pin):
        self.layout=layout;self.intent_bytes=intent_bytes;self.intent_pin=intent_pin
        self._pending=None;self._lock=threading.Lock()

    def cancel(self):
        if not self._lock.acquire(blocking=False):raise StoreError('session_busy','session')
        try:self._pending=None
        finally:self._lock.release()

    def plan(self, *, action):
        if not self._lock.acquire(blocking=False):raise StoreError('session_busy','session')
        try:
            self._pending=None
            if action not in ('reserve','cancel'):raise StoreError('move_action_invalid','action')
            doc,before,_=move_intent._verified(self.intent_bytes,self.intent_pin)
            if action=='reserve':
                current=store._load(self.layout)
                observation=move_intent.assess(self.intent_bytes,intent_pin=self.intent_pin,observed=current.raw)
            else:
                observation=probe.inspect(self.layout,intent_pin=self.intent_pin)
            if observation['state']!='before_both':raise StoreError('move_reservation_stale','inputs')
            location=_locations(self.layout)
            preview=move_preview.preview_move(before,source=doc['source'],target=doc['target'],
                      entry_id=doc['entry_id'],candidate=doc['candidate'],portability_context=doc['portability_context'])
            result={'outcome':'planned','action':action,'workspace':str(self.layout.workspace),
                    'profile_root':self.layout.profile_root,'intent_sha256':self.intent_pin,
                    'intent_utf8':self.intent_bytes.decode('utf-8'),'preview':preview,
                    'observed_sha256':observation['observed_sha256'],'location_identity':list(location),
                    'marker':'.domain-agent-kit/.move-pending', 'uid':os.geteuid(), 'gid':os.getegid(),
                    'file_mode':'0600', 'effect':'create_marker' if action=='reserve' else 'delete_marker',
                    'registries':'unchanged', 'failure':'leave_unknown_state',
                    'authorization':'not_checked','move':'not_implemented',
                    'ticket':secrets.token_hex(32)}
            self._pending=(init._canonical(result),self.layout,self.intent_bytes,self.intent_pin,observation['observed_sha256'],result['ticket'],action,location,(result['uid'],result['gid']))
            return result
        finally:self._lock.release()

    def apply(self, plan, *, confirmed_ticket):
        if not self._lock.acquire(blocking=False):raise StoreError('session_busy','session')
        try:
            if self._pending is None:raise StoreError('ticket_unknown','ticket')
            saved,layout,raw,pin,observed,ticket,action,location,identity=self._pending
            if type(confirmed_ticket) is not str or HEX.fullmatch(confirmed_ticket) is None or not secrets.compare_digest(ticket,confirmed_ticket):
                raise StoreError('confirmation_required','confirmed_ticket')
            self._pending=None
            try:
                if type(plan) is not dict or init._canonical(plan)!=saved:raise StoreError('plan_mismatch','plan')
                if (self.layout!=layout or self.intent_bytes!=raw or self.intent_pin!=pin
                        or (os.geteuid(),os.getegid())!=identity):raise StoreError('stale_plan','inputs')
            except (ValueError,TypeError,RecursionError,UnicodeError) as error:
                if isinstance(error,StoreError):raise
                raise StoreError('plan_mismatch','plan') from error
            if action=='reserve':return _reserve(layout,raw,pin,location)
            return _cancel_reservation(layout,pin,observed,location)
        finally:self._lock.release()
