"""Опытная отмена неполного резерва; происхождение marker не удостоверяется."""
from __future__ import annotations

import errno
import hashlib
import os
import secrets
import threading

from kit import init_workspace as init, move_execution as execution, move_finalize as finalizer, move_recovery_inspect as probe
from kit.base import move_intent, move_preview, registry_store as store
from kit.base.registry_policy import StoreError
from kit.verify_candidate import HEX


def _read_before(dirs, before):
    observed={}
    for area in ('L0','L1','L2'):
        raw=probe._read(dirs.parents[area],'registry.json',move_intent._MAX_INPUT)
        if raw!=before[area]:raise StoreError('move_partial_stale','inputs')
        observed[area]=hashlib.sha256(raw).hexdigest()
    return observed


def _read_marker(dirs, raw):
    parent=dirs.roots['L2'];name='.move-pending'
    info=os.stat(name,dir_fd=parent,follow_symlinks=False)
    fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|getattr(os,'O_CLOEXEC',0),dir_fd=parent)
    try:
        init._check_new_fd(fd,directory=False,uid=os.geteuid(),gid=os.getegid())
        if probe._identity(info)!=probe._identity(os.fstat(fd)):raise OSError('marker changed')
        part=probe._read(parent,name,move_intent.MAX_INTENT)
        if (len(part)>=len(raw) or not raw.startswith(part) or
                probe._identity(info)!=probe._identity(os.fstat(fd)) or
                probe._identity(info)!=probe._identity(os.stat(name,dir_fd=parent,follow_symlinks=False))):
            raise OSError('not expected partial marker')
        return probe._identity(info),fd,part
    except BaseException:
        os.close(fd);raise


def _snapshot(layout,raw,before):
    probe._check_intent_roots(layout,before)
    dirs=None;fd=None
    try:
        if (store.fcntl is None or not hasattr(store.fcntl,'flock') or
                not init._supported() or os.listdir not in os.supports_fd):
            raise OSError('platform unsupported')
        dirs=execution._Directories(layout)
        try:store.fcntl.flock(dirs.root,store.fcntl.LOCK_SH|store.fcntl.LOCK_NB)
        except OSError as error:
            if error.errno in (errno.EACCES,errno.EAGAIN):raise StoreError('move_partial_busy','workspace') from error
            raise
        locations=dirs.check();finalizer._no_stages(dirs)
        identity,fd,part=_read_marker(dirs,raw)
        observed=_read_before(dirs,before)
        if dirs.check()!=locations:raise OSError('directory changed')
        finalizer._no_stages(dirs)
        if (probe._identity(os.fstat(fd))!=identity or
                probe._identity(os.stat('.move-pending',dir_fd=dirs.roots['L2'],follow_symlinks=False))!=identity):
            raise OSError('marker changed')
        return locations,identity,part,observed
    except StoreError:raise
    except (OSError,ValueError,TypeError,AttributeError,NotImplementedError) as error:
        raise StoreError('move_partial_unavailable','workspace') from error
    finally:
        failure=None
        if fd is not None:
            try:os.close(fd)
            except OSError as error:failure=error
        if dirs is not None:
            try:dirs.close()
            except OSError as error:failure=error
        if failure is not None:raise StoreError('move_partial_unavailable','workspace') from failure


@store._serialized_write
def _cancel(layout,raw,pin,expected_locations,expected_identity,expected_part,expected_hashes):
    _,before,_=move_intent._verified(raw,pin)
    probe._check_intent_roots(layout,before)
    dirs=None;fd=None;attempted=False
    try:
        dirs=execution._Directories(layout)
        if dirs.check()!=expected_locations:raise StoreError('stale_plan','workspace')
        finalizer._no_stages(dirs)
        identity,fd,part=_read_marker(dirs,raw)
        if identity!=expected_identity or part!=expected_part:raise StoreError('stale_plan','marker')
        if _read_before(dirs,before)!=expected_hashes:raise StoreError('stale_plan','inputs')
        if dirs.check()!=expected_locations:raise StoreError('stale_plan','workspace')
        finalizer._no_stages(dirs)
        init._check_new_fd(fd,directory=False,uid=os.geteuid(),gid=os.getegid())
        parent=dirs.roots['L2'];name='.move-pending'
        if (probe._identity(os.fstat(fd))!=identity or
                probe._identity(os.stat(name,dir_fd=parent,follow_symlinks=False))!=identity or
                probe._read(parent,name,move_intent.MAX_INTENT)!=part):raise StoreError('stale_plan','marker')
        if _read_before(dirs,before)!=expected_hashes:raise StoreError('stale_plan','inputs')
        attempted=True
        os.unlink(name,dir_fd=parent)
        os.fsync(parent)
    except StoreError as error:
        if attempted:raise StoreError('move_partial_cancel_unknown','workspace') from error
        raise
    except (OSError,ValueError,TypeError,AttributeError,NotImplementedError) as error:
        raise StoreError('move_partial_cancel_unknown' if attempted else 'move_partial_unavailable','workspace') from error
    finally:
        failure=None
        if fd is not None:
            try:os.close(fd)
            except OSError as error:failure=error
        if dirs is not None:
            try:dirs.close()
            except OSError as error:failure=error
        if failure is not None:raise StoreError('move_partial_cancel_unknown' if attempted else 'move_partial_unavailable','workspace') from failure
    return {'outcome':'partial_marker_removed','intent_sha256':pin,'registries':'unchanged',
            'origin':'not_verified','authorization':'not_checked','durability':'fsync_call_completed'}


class PartialReservationCancelSession:
    """Отдельный план/подтверждение, только точные before и отсутствующие стадии."""
    def __init__(self,layout,*,intent_bytes,intent_pin):
        self.layout=layout;self.intent_bytes=intent_bytes;self.intent_pin=intent_pin
        self._pending=None;self._lock=threading.Lock()

    def cancel(self):
        if not self._lock.acquire(blocking=False):raise StoreError('session_busy','session')
        try:self._pending=None
        finally:self._lock.release()

    def plan(self):
        if not self._lock.acquire(blocking=False):raise StoreError('session_busy','session')
        try:
            self._pending=None
            doc,before,_=move_intent._verified(self.intent_bytes,self.intent_pin)
            locations,identity,part,observed=_snapshot(self.layout,self.intent_bytes,before)
            preview=move_preview.preview_move(before,source=doc['source'],target=doc['target'],entry_id=doc['entry_id'],
                        candidate=doc['candidate'],portability_context=doc['portability_context'])
            result={'outcome':'planned','workspace':str(self.layout.workspace),'profile_root':self.layout.profile_root,
                    'intent_sha256':self.intent_pin,'intent_utf8':self.intent_bytes.decode('utf-8'),'preview':preview,
                    'observed_sha256':observed,'directory_identities':locations,'marker_identity':list(identity),
                    'marker_bytes':len(part),'marker_sha256':hashlib.sha256(part).hexdigest(),
                    'marker_matches':'strict_intent_prefix','uid':os.geteuid(),'gid':os.getegid(),
                    'effect':'remove_partial_marker_only','registries':'unchanged','origin':'not_verified',
                    'authorization':'not_checked','failure':'outcome_may_be_unknown','ticket':secrets.token_hex(32)}
            self._pending=(init._canonical(result),self.layout,self.intent_bytes,self.intent_pin,locations,identity,
                           part,observed,result['ticket'],(result['uid'],result['gid']))
            return result
        finally:self._lock.release()

    def apply(self,plan,*,confirmed_ticket):
        if not self._lock.acquire(blocking=False):raise StoreError('session_busy','session')
        try:
            if self._pending is None:raise StoreError('ticket_unknown','ticket')
            saved,layout,raw,pin,locations,identity,part,observed,ticket,uidgid=self._pending
            if type(confirmed_ticket) is not str or HEX.fullmatch(confirmed_ticket) is None or not secrets.compare_digest(ticket,confirmed_ticket):
                raise StoreError('confirmation_required','confirmed_ticket')
            self._pending=None
            try:
                if type(plan) is not dict or init._canonical(plan)!=saved:raise StoreError('plan_mismatch','plan')
                if self.layout!=layout or self.intent_bytes!=raw or self.intent_pin!=pin or (os.geteuid(),os.getegid())!=uidgid:
                    raise StoreError('stale_plan','inputs')
            except (ValueError,TypeError,RecursionError,UnicodeError) as error:
                if isinstance(error,StoreError):raise
                raise StoreError('plan_mismatch','plan') from error
            return _cancel(layout,raw,pin,locations,identity,part,observed)
        finally:self._lock.release()
