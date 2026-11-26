#!/usr/bin/env python3
"""Отдельный новый контейнер из проверенного архива, не восстановление старых данных."""
import os
import secrets
import threading
from pathlib import Path

import release_install_study as install
from kit import init_workspace as init
from kit.init_workspace import InitializationError


class RebuildError(ValueError):
    pass


def _parents_differ(old, new):
    """Не разрешаем одну и ту же директорию родителя или вложенные имена целей."""
    if (not old.is_absolute() or not new.is_absolute() or '..' in old.parts or '..' in new.parts or
            old == new or old in new.parents or new in old.parents):
        raise RebuildError('destinations_overlap')
    first=second=None
    try:
        first,a=init._open_parent(old.parent)
        second,b=init._open_parent(new.parent)
        if a==b:raise RebuildError('destinations_overlap')
    except InitializationError as error:
        raise RebuildError('parents_unavailable') from error
    finally:
        if second is not None: os.close(second)
        if first is not None: os.close(first)


class RebuildSession:
    def __init__(self, old_destination, stage_name, new_destination, *, profile_root,
                 archive_bytes, statement, signature, policy, verify_signature):
        self.old_destination=Path(old_destination);self.new_destination=Path(new_destination)
        self.stage_name=stage_name
        args=dict(profile_root=profile_root,archive_bytes=archive_bytes,statement=statement,
                  signature=signature,policy=policy,verify_signature=verify_signature)
        self._old=install.InstallSession(self.old_destination,**args)
        self._new=install.InstallSession(self.new_destination,**args)
        self._pending=None;self._lock=threading.Lock()

    def cancel(self):
        if not self._lock.acquire(False):raise RebuildError('session_busy')
        try:self._pending=None;self._new.cancel()
        finally:self._lock.release()

    def plan(self):
        if not self._lock.acquire(False):raise RebuildError('session_busy')
        try:
            self._pending=None
            try:
                self._new.cancel()
                _parents_differ(self.old_destination,self.new_destination)
                observation=self._old.inspect(stage_name=self.stage_name)
                newplan=self._new.plan()
            except install.InstallError as error:raise RebuildError(str(error)) from error
            ticket=secrets.token_hex(32)
            shown=dict(newplan);shown.pop('ticket')
            result={'outcome':'planned','old_observation':observation,'new_install_plan':shown,'ticket':ticket,
                    'effect':'new_empty_container_only','old_destination':str(self.old_destination),
                    'old_stage_name':self.stage_name,'new_destination':str(self.new_destination),
                    'old_objects':'not_modified','user_l1_l2_history':'not_copied_or_recovered',
                    'old_completion':'not_proved','trust_anchor':'assumed_not_verified',
                    'failure':'unknown_do_not_retry_or_delete'}
            self._pending=(init._canonical(result),init._canonical(observation),newplan,ticket,
                           self.old_destination,self.new_destination,self.stage_name)
            return result
        finally:self._lock.release()

    def apply(self,plan,*,confirmed_ticket):
        if not self._lock.acquire(False):raise RebuildError('session_busy')
        try:
            if self._pending is None:raise RebuildError('ticket_unknown')
            saved,observed,newplan,ticket,old,new,stage=self._pending
            if (type(confirmed_ticket) is not str or len(confirmed_ticket)!=64 or
                any(c not in '0123456789abcdef' for c in confirmed_ticket) or
                not secrets.compare_digest(ticket,confirmed_ticket)):
                raise RebuildError('confirmation_required')
            self._pending=None
            try:
                if type(plan) is not dict or init._canonical(plan)!=saved:raise RebuildError('plan_mismatch')
                if (old,new,stage)!=(self.old_destination,self.new_destination,self.stage_name):
                    raise RebuildError('stale_plan')
                _parents_differ(old,new)
                if init._canonical(self._old.inspect(stage_name=stage))!=observed:raise RebuildError('stale_observation')
                result=self._new.apply(newplan,confirmed_ticket=newplan['ticket'])
            except install.InstallError as error:
                self._new.cancel();raise RebuildError(str(error)) from error
            except (RebuildError,TypeError,ValueError,RecursionError) as error:
                self._new.cancel()
                if isinstance(error,RebuildError):raise
                raise RebuildError('plan_mismatch') from error
            return dict(result,outcome='study_new_empty_container_published',old_objects='not_modified_by_this_operation',
                        user_l1_l2_history='not_copied_or_recovered',old_completion='not_proved',
                        observation_atomicity='not_provided')
        finally:self._lock.release()
