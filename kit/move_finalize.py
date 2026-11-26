"""Опытное подтверждённое завершение после переноса; не доверенная пользовательская поставка."""
from __future__ import annotations

import os
import secrets
import threading

from kit import init_workspace as init, move_execution as execution, move_recovery_inspect as probe
from kit.base import move_intent, move_preview, registry_store as store
from kit.base.registry_policy import StoreError
from kit.verify_candidate import HEX


def _no_stages(dirs):
    # Не читаем и не удаляем найденные объекты. Любой зарезервированный префикс блокирует завершение.
    if os.listdir not in os.supports_fd:raise OSError('listdir fd unsupported')
    for area in ('L1','L2'):
        if area == 'L1':store._refuse_profile_copy_stages_fd(dirs.parents[area])
        if any(name.startswith('.move-stage-') for name in os.listdir(dirs.parents[area])):
            raise StoreError('move_stages_present',area)


def _locations_without_stages(layout):
    dirs=None
    try:
        dirs=execution._Directories(layout);_no_stages(dirs);return dirs.check()
    except StoreError:raise
    except (OSError,ValueError,TypeError,AttributeError,NotImplementedError) as error:
        raise StoreError('move_finalize_unavailable','workspace') from error
    finally:
        if dirs is not None:
            try:dirs.close()
            except OSError as error:raise StoreError('move_finalize_unavailable','workspace') from error


@store._serialized_write
def _finalize(layout,raw,pin,expected_hashes,identities):
    doc,_,after=move_intent._verified(raw,pin)
    dirs=None;marker_fd=None;attempted=False
    try:
        dirs=execution._Directories(layout)
        if dirs.check()!=identities:raise StoreError('stale_plan','workspace')
        _no_stages(dirs)
        observed=probe._inspect(layout,intent_pin=pin,exclusive_held=True)
        if observed['state']!='after_both' or observed['observed_sha256']!=expected_hashes:
            raise StoreError('stale_plan','inputs')
        marker_parent=dirs.roots['L2'];name='.move-pending'
        info=os.stat(name,dir_fd=marker_parent,follow_symlinks=False)
        marker_fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|getattr(os,'O_CLOEXEC',0),dir_fd=marker_parent)
        init._check_new_fd(marker_fd,directory=False,uid=os.geteuid(),gid=os.getegid())
        if probe._identity(info)!=probe._identity(os.fstat(marker_fd)) or probe._read(marker_parent,name,move_intent.MAX_INTENT)!=raw:
            raise OSError('marker changed')
        execution._sync_file(marker_parent,name,raw,move_intent.MAX_INTENT)
        for area in (doc['target'],doc['source']):
            execution._sync_file(dirs.parents[area],'registry.json',after[area],move_intent._MAX_INPUT)
        if dirs.check()!=identities:raise StoreError('stale_plan','workspace')
        _no_stages(dirs)
        observed=probe._inspect(layout,intent_pin=pin,exclusive_held=True)
        if observed['state']!='after_both' or observed['observed_sha256']!=expected_hashes:
            raise StoreError('stale_plan','inputs')
        init._check_new_fd(marker_fd,directory=False,uid=os.geteuid(),gid=os.getegid())
        if (probe._identity(info)!=probe._identity(os.fstat(marker_fd)) or
                probe._identity(info)!=probe._identity(os.stat(name,dir_fd=marker_parent,follow_symlinks=False)) or
                probe._read(marker_parent,name,move_intent.MAX_INTENT)!=raw):
            raise OSError('marker changed')
        attempted=True
        os.unlink(name,dir_fd=marker_parent)
        os.fsync(marker_parent)
    except StoreError as error:
        if attempted:raise StoreError('move_finalize_unknown','workspace') from error
        raise
    except (OSError,ValueError,TypeError,AttributeError,NotImplementedError) as error:
        raise StoreError('move_finalize_unknown' if attempted else 'move_finalize_unavailable','workspace') from error
    finally:
        failure=None
        if marker_fd is not None:
            try:os.close(marker_fd)
            except OSError as error:failure=error
        if dirs is not None:
            try:dirs.close()
            except OSError as error:failure=error
        if failure is not None:raise StoreError('move_finalize_unknown' if attempted else 'move_finalize_unavailable','workspace') from failure
    return {'outcome':'marker_removed_after_both','intent_sha256':pin,'state':'after_both',
            'authorization':'not_checked','durability':'fsync_calls_completed',
            'independent_review':'not_run'}


class MoveFinalizationSession:
    """Отдельное подтверждение снятия marker, не проверка согласия или полномочий."""
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
            observation=probe.inspect(self.layout,intent_pin=self.intent_pin)
            if observation['state']!='after_both':raise StoreError('move_finalize_stale','inputs')
            identities=_locations_without_stages(self.layout)
            preview=move_preview.preview_move(before,source=doc['source'],target=doc['target'],entry_id=doc['entry_id'],
                         candidate=doc['candidate'],portability_context=doc['portability_context'])
            result={'outcome':'planned','workspace':str(self.layout.workspace),'profile_root':self.layout.profile_root,
                    'intent_sha256':self.intent_pin,'intent_utf8':self.intent_bytes.decode('utf-8'),'preview':preview,
                    'state':observation['state'],'observed_sha256':observation['observed_sha256'],
                    'directory_identities':identities,'uid':os.geteuid(),'gid':os.getegid(),
                    'effect':'remove_marker_after_checks_and_sync','registries':'unchanged',
                    'authorization':'not_checked','failure':'outcome_may_be_unknown','ticket':secrets.token_hex(32)}
            self._pending=(init._canonical(result),self.layout,self.intent_bytes,self.intent_pin,
                           observation['observed_sha256'],identities,result['ticket'],(result['uid'],result['gid']))
            return result
        finally:self._lock.release()

    def apply(self,plan,*,confirmed_ticket):
        if not self._lock.acquire(blocking=False):raise StoreError('session_busy','session')
        try:
            if self._pending is None:raise StoreError('ticket_unknown','ticket')
            saved,layout,raw,pin,hashes,identities,ticket,identity=self._pending
            if type(confirmed_ticket) is not str or HEX.fullmatch(confirmed_ticket) is None or not secrets.compare_digest(ticket,confirmed_ticket):
                raise StoreError('confirmation_required','confirmed_ticket')
            self._pending=None
            try:
                if type(plan) is not dict or init._canonical(plan)!=saved:raise StoreError('plan_mismatch','plan')
                if self.layout!=layout or self.intent_bytes!=raw or self.intent_pin!=pin or (os.geteuid(),os.getegid())!=identity:
                    raise StoreError('stale_plan','inputs')
            except (ValueError,TypeError,RecursionError,UnicodeError) as error:
                if isinstance(error,StoreError):raise
                raise StoreError('plan_mismatch','plan') from error
            return _finalize(layout,raw,pin,hashes,identities)
        finally:self._lock.release()
