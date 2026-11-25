"""Опытный экспорт intent в новый файл; не перемещение и не доверенная доставка."""
from __future__ import annotations

import os
from pathlib import Path
import secrets
import threading

from kit import init_workspace as init
from kit.base import move_intent, move_preview
from kit.base.registry_policy import StoreError
from kit.init_workspace import InitializationError
from kit.verify_candidate import HEX


class IntentExportError(ValueError):
    pass


def _parent(path):
    try:return init._open_parent(path)
    except InitializationError as error:raise IntentExportError(str(error)) from error


def _inspect(raw, pin):
    try:
        doc,before,_=move_intent._verified(raw,pin)
        return move_preview.preview_move(before,source=doc['source'],target=doc['target'],
                    entry_id=doc['entry_id'],candidate=doc['candidate'],portability_context=doc['portability_context'])
    except StoreError as error:raise IntentExportError(error.code) from error


class IntentExportSession:
    """Один план и отдельное подтверждение; готовый пакет может быть конфиденциальным."""
    def __init__(self, destination, *, intent_bytes, intent_pin):
        self.destination=Path(destination);self.intent_bytes=intent_bytes;self.intent_pin=intent_pin
        self._pending=None;self._lock=threading.Lock()

    def plan(self):
        if not self._lock.acquire(blocking=False):raise IntentExportError('session_busy')
        try:
            self._pending=None;path=self.destination
            if (not path.is_absolute() or '..' in path.parts or not path.name or path.name=='.move-pending'):
                raise IntentExportError('destination_invalid')
            preview=_inspect(self.intent_bytes,self.intent_pin)
            fd,identity=_parent(path.parent)
            try:
                if init._occupied(fd,path.name):raise IntentExportError('destination_occupied')
            except OSError as error:raise IntentExportError('parent_unavailable') from error
            finally:os.close(fd)
            plan={'outcome':'planned','destination':str(path),'intent_sha256':self.intent_pin,
                  'intent_bytes':len(self.intent_bytes),'intent_utf8':self.intent_bytes.decode('utf-8'),
                  'preview':preview,'file_mode':'0600','uid':os.geteuid(),'gid':os.getegid(),
                  'publication':'new_file_no_overwrite','failure':'leave_partial_or_unverified',
                  'origin':'not_verified','authorization':'not_checked','move':'not_implemented',
                  'ticket':secrets.token_hex(32)}
            self._pending=(init._canonical(plan),self.intent_bytes,self.intent_pin,identity,plan['uid'],plan['gid'],plan['ticket'],str(path))
            return plan
        finally:self._lock.release()

    def cancel(self):
        if not self._lock.acquire(blocking=False):raise IntentExportError('session_busy')
        try:self._pending=None
        finally:self._lock.release()

    def apply(self, plan, *, confirmed_ticket):
        if not self._lock.acquire(blocking=False):raise IntentExportError('session_busy')
        try:
            if self._pending is None:raise IntentExportError('ticket_unknown')
            saved,raw,pin,identity,uid,gid,ticket,destination=self._pending
            if type(confirmed_ticket) is not str or HEX.fullmatch(confirmed_ticket) is None or not secrets.compare_digest(ticket,confirmed_ticket):
                raise IntentExportError('confirmation_required')
            self._pending=None
            try:
                if type(plan) is not dict or init._canonical(plan)!=saved:raise IntentExportError('plan_mismatch')
                if (not isinstance(self.destination,Path) or str(self.destination)!=destination or self.intent_bytes!=raw or self.intent_pin!=pin
                        or (os.geteuid(),os.getegid())!=(uid,gid)):
                    raise IntentExportError('stale_plan')
                _inspect(raw,pin)
            except (ValueError,TypeError,RecursionError,UnicodeError) as error:
                if isinstance(error,IntentExportError):raise
                raise IntentExportError('plan_mismatch') from error
            path=self.destination;parent,current=_parent(path.parent);reserved=False
            try:
                if current!=identity:raise IntentExportError('stale_parent')
                try:
                    fd=os.open(path.name,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|getattr(os,'O_CLOEXEC',0),0o600,dir_fd=parent)
                except FileExistsError as error:raise IntentExportError('destination_occupied') from error
                except OSError as error:raise IntentExportError('destination_unavailable') from error
                reserved=True
                try:
                    try:
                        init._check_new_fd(fd,directory=False,uid=uid,gid=gid)
                        remaining=memoryview(raw)
                        while remaining:
                            count=os.write(fd,remaining)
                            if count<=0:raise OSError('short write')
                            remaining=remaining[count:]
                        init._check_new_fd(fd,directory=False,uid=uid,gid=gid)
                        os.fsync(fd)
                        os.lseek(fd,0,os.SEEK_SET);result=bytearray()
                        while len(result)<len(raw):
                            part=os.read(fd,min(65536,len(raw)-len(result)))
                            if not part:raise OSError('short read')
                            result.extend(part)
                        if bytes(result)!=raw or os.read(fd,1):raise OSError('verification failed')
                        init._check_new_fd(fd,directory=False,uid=uid,gid=gid)
                        current=os.stat(path.name,dir_fd=parent,follow_symlinks=False);opened=os.fstat(fd)
                        if (current.st_dev,current.st_ino)!=(opened.st_dev,opened.st_ino):raise OSError('target changed')
                        check,latest=_parent(path.parent);os.close(check)
                        if latest!=identity:raise OSError('parent changed')
                        os.fsync(parent)
                    finally:os.close(fd)
                except (OSError,InitializationError,IntentExportError,ValueError,TypeError) as error:
                    raise IntentExportError('destination_partial_or_unverified') from error
            finally:
                try:os.close(parent)
                except OSError as error:
                    raise IntentExportError('destination_partial_or_unverified' if reserved else 'parent_unavailable') from error
            return {'outcome':'exported_unverified_origin','destination':destination,'intent_sha256':pin,
                    'bytes':len(raw),'move':'not_implemented'}
        finally:self._lock.release()
