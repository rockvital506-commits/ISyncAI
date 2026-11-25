"""Опытная отдельная уборка выбранной стадии; не удостоверяет её происхождение."""
from __future__ import annotations

import hashlib
import os
import re
import secrets
import threading

from kit import init_workspace as init, move_execution as execution, move_recovery_inspect as probe
from kit.base import move_intent, move_preview, registry_store as store
from kit.base.registry_policy import StoreError
from kit.verify_candidate import HEX

_STAGE=re.compile(r'\.move-stage-[0-9a-f]{32}\Z')
_STATES=('before_both','target_after_source_before','after_both')


def _read_stage(parent, name, after):
    """Вернуть метаданные, удерживаемый fd и bytes; caller обязан закрыть fd."""
    initial=os.stat(name,dir_fd=parent,follow_symlinks=False)
    fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|getattr(os,'O_CLOEXEC',0),dir_fd=parent)
    try:
        init._check_new_fd(fd,directory=False,uid=os.geteuid(),gid=os.getegid())
        if probe._identity(initial)!=probe._identity(os.fstat(fd)):raise OSError('stage changed')
        data=probe._read(parent,name,move_intent._MAX_INPUT)
        if (not after.startswith(data) or probe._identity(initial)!=probe._identity(os.fstat(fd)) or
                probe._identity(initial)!=probe._identity(os.stat(name,dir_fd=parent,follow_symlinks=False))):
            raise OSError('stage changed or foreign')
        return probe._identity(initial),fd,data
    except BaseException:
        os.close(fd);raise


def _observe(layout,area,name,after):
    dirs=None;fd=None
    try:
        dirs=execution._Directories(layout);location=dirs.check()
        identity,fd,data=_read_stage(dirs.parents[area],name,after)
        if dirs.check()!=location:raise OSError('directory changed')
        return location,identity,data
    except (OSError,ValueError,TypeError,AttributeError,NotImplementedError) as error:
        raise StoreError('move_stage_unavailable','stage') from error
    finally:
        failure=None
        if fd is not None:
            try:os.close(fd)
            except OSError as error:failure=error
        if dirs is not None:
            try:dirs.close()
            except OSError as error:failure=error
        if failure is not None:raise StoreError('move_stage_unavailable','stage') from failure


@store._serialized_write
def _remove(layout,raw,pin,area,name,expected_state,expected_hashes,location,identity,expected_data):
    _,_,after=move_intent._verified(raw,pin)
    dirs=None;fd=None;attempted=False
    try:
        dirs=execution._Directories(layout)
        if dirs.check()!=location:raise StoreError('stale_plan','workspace')
        observation=probe._inspect(layout,intent_pin=pin,exclusive_held=True)
        if observation['state']!=expected_state or observation['observed_sha256']!=expected_hashes:
            raise StoreError('stale_plan','inputs')
        stage_identity,fd,data=_read_stage(dirs.parents[area],name,after[area])
        if stage_identity!=identity or data!=expected_data:raise StoreError('stale_plan','stage')
        if dirs.check()!=location:raise StoreError('stale_plan','workspace')
        current=probe._inspect(layout,intent_pin=pin,exclusive_held=True)
        if current['state']!=expected_state or current['observed_sha256']!=expected_hashes:
            raise StoreError('stale_plan','inputs')
        init._check_new_fd(fd,directory=False,uid=os.geteuid(),gid=os.getegid())
        if (probe._identity(os.fstat(fd))!=identity or
                probe._identity(os.stat(name,dir_fd=dirs.parents[area],follow_symlinks=False))!=identity or
                probe._read(dirs.parents[area],name,move_intent._MAX_INPUT)!=data):
            raise StoreError('stale_plan','stage')
        attempted=True
        os.unlink(name,dir_fd=dirs.parents[area])
        os.fsync(dirs.parents[area])
    except StoreError as error:
        if attempted:raise StoreError('move_stage_cleanup_unknown','stage') from error
        raise
    except (OSError,ValueError,TypeError,AttributeError,NotImplementedError) as error:
        raise StoreError('move_stage_cleanup_unknown' if attempted else 'move_stage_unavailable','stage') from error
    finally:
        failure=None
        if fd is not None:
            try:os.close(fd)
            except OSError as error:failure=error
        if dirs is not None:
            try:dirs.close()
            except OSError as error:failure=error
        if failure is not None:raise StoreError('move_stage_cleanup_unknown' if attempted else 'move_stage_unavailable','stage') from failure
    return {'outcome':'selected_stage_removed','area':area,'name':name,'intent_sha256':pin,
            'marker':'retained','registries':'unchanged','origin':'not_verified',
            'authorization':'not_checked','durability':'fsync_call_completed'}


class MoveStageCleanupSession:
    """Удаление одной указанной стадии после отдельного плана и подтверждения."""
    def __init__(self,layout,*,intent_bytes,intent_pin):
        self.layout=layout;self.intent_bytes=intent_bytes;self.intent_pin=intent_pin
        self._pending=None;self._lock=threading.Lock()

    def cancel(self):
        if not self._lock.acquire(blocking=False):raise StoreError('session_busy','session')
        try:self._pending=None
        finally:self._lock.release()

    def plan(self,*,area,name):
        if not self._lock.acquire(blocking=False):raise StoreError('session_busy','session')
        try:
            self._pending=None
            if type(area) is not str or area not in ('L1','L2') or type(name) is not str or _STAGE.fullmatch(name) is None:
                raise StoreError('move_stage_invalid','stage')
            doc,before,after=move_intent._verified(self.intent_bytes,self.intent_pin)
            observation=probe.inspect(self.layout,intent_pin=self.intent_pin)
            if observation['state'] not in _STATES:raise StoreError('move_stage_stale','inputs')
            location,identity,data=_observe(self.layout,area,name,after[area])
            preview=move_preview.preview_move(before,source=doc['source'],target=doc['target'],entry_id=doc['entry_id'],
                        candidate=doc['candidate'],portability_context=doc['portability_context'])
            result={'outcome':'planned','workspace':str(self.layout.workspace),'profile_root':self.layout.profile_root,
                    'intent_sha256':self.intent_pin,'intent_utf8':self.intent_bytes.decode('utf-8'),'preview':preview,
                    'state':observation['state'],'observed_sha256':observation['observed_sha256'],
                    'directory_identities':location,'stage_identity':list(identity),'area':area,'name':name,
                    'stage_bytes':len(data),'stage_sha256':hashlib.sha256(data).hexdigest(),
                    'stage_matches':'after_prefix','uid':os.geteuid(),'gid':os.getegid(),
                    'effect':'delete_one_selected_stage','marker':'retained','registries':'unchanged',
                    'origin':'not_verified','authorization':'not_checked','failure':'outcome_may_be_unknown',
                    'ticket':secrets.token_hex(32)}
            self._pending=(init._canonical(result),self.layout,self.intent_bytes,self.intent_pin,area,name,
                           observation['state'],observation['observed_sha256'],location,identity,data,result['ticket'],(result['uid'],result['gid']))
            return result
        finally:self._lock.release()

    def apply(self,plan,*,confirmed_ticket):
        if not self._lock.acquire(blocking=False):raise StoreError('session_busy','session')
        try:
            if self._pending is None:raise StoreError('ticket_unknown','ticket')
            saved,layout,raw,pin,area,name,state,hashes,location,identity,data,ticket,uidgid=self._pending
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
            return _remove(layout,raw,pin,area,name,state,hashes,location,identity,data)
        finally:self._lock.release()
