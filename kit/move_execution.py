"""Опытное выполнение закреплённого переноса; marker остаётся, практическая готовность не заявлена."""
from __future__ import annotations

import os
import secrets
import stat
import threading

from kit import init_workspace as init, move_recovery_inspect as probe, move_replace_stage as stage
from kit.base import move_intent, move_preview, registry_store as store
from kit.base.registry_policy import StoreError
from kit.verify_candidate import HEX


class _Directories:
    """Открытые dir-fd; удостоверение согласованности только против кооперативной среды."""
    def __init__(self, layout):
        self.opened=[];self.bindings=[];self.workspace=store._workspace(layout.workspace)
        try:
            flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|getattr(os,'O_CLOEXEC',0)
            self.root=os.open(self.workspace,flags);self.opened.append(self.root)
            self.roots={};self.parents={}
            def child(parent,name):
                fd=probe._directory(parent,name);self.opened.append(fd);self.bindings.append((parent,name,fd));return fd
            for area,path in store._declared_roots(layout).items():
                fd=self.root
                for part in path.split('/'):fd=child(fd,part)
                self.roots[area]=fd
                for part in store._SUFFIX[area].split('/')[:-1]:fd=child(fd,part)
                self.parents[area]=fd
            roots=[self._id(fd) for fd in self.roots.values()]
            if len(set(roots))!=3:raise OSError('root alias')
            self.check()
        except BaseException:
            self.close();raise

    @staticmethod
    def _id(fd):
        info=os.fstat(fd)
        if not stat.S_ISDIR(info.st_mode) or info.st_ino<=0:raise OSError('invalid directory')
        return (info.st_dev,info.st_ino)

    def check(self):
        named=os.stat(self.workspace,follow_symlinks=False)
        if not stat.S_ISDIR(named.st_mode) or self._id(self.root)!=(named.st_dev,named.st_ino):raise OSError('root changed')
        for parent,name,fd in self.bindings:
            named=os.stat(name,dir_fd=parent,follow_symlinks=False)
            if not stat.S_ISDIR(named.st_mode) or self._id(fd)!=(named.st_dev,named.st_ino):raise OSError('directory changed')
        return [list(self._id(fd)) for fd in self.opened]

    def close(self):
        failure=None
        for fd in reversed(self.opened):
            try:os.close(fd)
            except OSError as error:failure=error
        self.opened=[]
        if failure:raise failure


def _check_file(parent, name, expected, limit):
    initial=os.stat(name,dir_fd=parent,follow_symlinks=False)
    fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|getattr(os,'O_CLOEXEC',0),dir_fd=parent)
    try:
        init._check_new_fd(fd,directory=False,uid=os.geteuid(),gid=os.getegid())
        if (probe._identity(initial)!=probe._identity(os.fstat(fd)) or probe._read(parent,name,limit)!=expected
                or probe._identity(initial)!=probe._identity(os.stat(name,dir_fd=parent,follow_symlinks=False))):
            raise OSError('file changed')
    finally:os.close(fd)


def _sync_file(parent, name, expected, limit):
    flags=os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|getattr(os,'O_CLOEXEC',0)
    initial=os.stat(name,dir_fd=parent,follow_symlinks=False)
    fd=os.open(name,flags,dir_fd=parent)
    try:
        init._check_new_fd(fd,directory=False,uid=os.geteuid(),gid=os.getegid())
        if probe._identity(initial)!=probe._identity(os.fstat(fd)) or probe._read(parent,name,limit)!=expected:
            raise OSError('file changed')
        os.fsync(fd)
        init._check_new_fd(fd,directory=False,uid=os.geteuid(),gid=os.getegid())
        if (probe._identity(initial)!=probe._identity(os.fstat(fd)) or
                probe._identity(initial)!=probe._identity(os.stat(name,dir_fd=parent,follow_symlinks=False))):
            raise OSError('file changed')
        os.fsync(parent)
    finally:os.close(fd)


def _locations(layout):
    dirs=None
    try:
        dirs=_Directories(layout);return dirs.check()
    except (OSError,ValueError,TypeError,AttributeError,NotImplementedError) as error:
        raise StoreError('move_execution_unavailable','workspace') from error
    finally:
        if dirs is not None:
            try:dirs.close()
            except OSError as error:raise StoreError('move_execution_unavailable','workspace') from error


@store._serialized_write
def _execute(layout, raw, pin, expected_state, expected_hashes, identities):
    doc,before,after=move_intent._verified(raw,pin)
    dirs=None; started=False
    try:
        dirs=_Directories(layout)
        if dirs.check()!=identities:raise StoreError('stale_plan','workspace')
        observed=probe._inspect(layout,intent_pin=pin,exclusive_held=True)
        if observed['state']!=expected_state or observed['observed_sha256']!=expected_hashes:
            raise StoreError('stale_plan','inputs')
        if expected_state not in ('before_both','target_after_source_before','after_both'):
            raise StoreError('move_execution_stale','inputs')
        started=True
        _sync_file(dirs.roots['L2'],'.move-pending',raw,move_intent.MAX_INTENT)
        if dirs.check()!=identities:raise OSError('directory changed')
        for area in (doc['target'],doc['source']):
            is_after=(area==doc['target'] and expected_state!='before_both') or expected_state=='after_both'
            _check_file(dirs.parents[area],'registry.json',after[area] if is_after else before[area],move_intent._MAX_INPUT)
        if dirs.check()!=identities:raise OSError('directory changed')
        if expected_state=='before_both':
            stage._replace_for_move(dirs.parents[doc['target']],before=before[doc['target']],after=after[doc['target']])
        # Не удалять источник до повторного подтверждения и синхронизации цели.
        if dirs.check()!=identities:raise OSError('directory changed')
        observed=probe._inspect(layout,intent_pin=pin,exclusive_held=True)
        next_state='after_both' if expected_state=='after_both' else 'target_after_source_before'
        if observed['state']!=next_state:raise OSError('unexpected state')
        _sync_file(dirs.parents[doc['target']],'registry.json',after[doc['target']],move_intent._MAX_INPUT)
        if dirs.check()!=identities:raise OSError('directory changed')
        if expected_state!='after_both':
            observed=probe._inspect(layout,intent_pin=pin,exclusive_held=True)
            if observed['state']!='target_after_source_before':raise OSError('unexpected state')
            stage._replace_for_move(dirs.parents[doc['source']],before=before[doc['source']],after=after[doc['source']])
        if dirs.check()!=identities:raise OSError('directory changed')
        if probe._inspect(layout,intent_pin=pin,exclusive_held=True)['state']!='after_both':raise OSError('unexpected state')
        _sync_file(dirs.parents[doc['source']],'registry.json',after[doc['source']],move_intent._MAX_INPUT)
        if dirs.check()!=identities:raise OSError('directory changed')
        if probe._inspect(layout,intent_pin=pin,exclusive_held=True)['state']!='after_both':raise OSError('unexpected state')
    except StoreError as error:
        if started:raise StoreError('move_execution_unknown','workspace') from error
        raise
    except (OSError,ValueError,TypeError,AttributeError,NotImplementedError) as error:
        raise StoreError('move_execution_unknown' if started else 'move_execution_unavailable','workspace') from error
    finally:
        if dirs is not None:
            try:dirs.close()
            except OSError as error:raise StoreError('move_execution_unknown' if started else 'move_execution_unavailable','workspace') from error
    return {'outcome':'registries_updated_marker_retained','intent_sha256':pin,
            'state':'after_both','marker':'retained','completion':'not_implemented',
            'authorization':'not_checked','durability':'fsync_calls_completed'}


class MoveExecutionSession:
    """Опытный отдельный план и билет, не удостоверяют права или согласие человека."""
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
            if observation['state'] not in ('before_both','target_after_source_before','after_both'):
                raise StoreError('move_execution_stale','inputs')
            identities=_locations(self.layout)
            preview=move_preview.preview_move(before,source=doc['source'],target=doc['target'],entry_id=doc['entry_id'],
                         candidate=doc['candidate'],portability_context=doc['portability_context'])
            result={'outcome':'planned','workspace':str(self.layout.workspace),'profile_root':self.layout.profile_root,
                    'intent_sha256':self.intent_pin,'intent_utf8':self.intent_bytes.decode('utf-8'),'preview':preview,
                    'state':observation['state'],'observed_sha256':observation['observed_sha256'],
                    'directory_identities':identities,'uid':os.geteuid(),'gid':os.getegid(),
                    'effect':'target_before_source_marker_retained','authorization':'not_checked',
                    'completion':'not_implemented','failure':'unknown_marker_retained','ticket':secrets.token_hex(32)}
            self._pending=(init._canonical(result),self.layout,self.intent_bytes,self.intent_pin,
                           observation['state'],observation['observed_sha256'],identities,result['ticket'],(result['uid'],result['gid']))
            return result
        finally:self._lock.release()

    def apply(self,plan,*,confirmed_ticket):
        if not self._lock.acquire(blocking=False):raise StoreError('session_busy','session')
        try:
            if self._pending is None:raise StoreError('ticket_unknown','ticket')
            saved,layout,raw,pin,state,hashes,identities,ticket,identity=self._pending
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
            return _execute(layout,raw,pin,state,hashes,identities)
        finally:self._lock.release()
