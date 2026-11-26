#!/usr/bin/env python3
"""Опытный явный файл для ручного канала контекста; доставку агенту не выполняет."""
from pathlib import Path
import secrets
import threading

from kit import context_export, init_workspace as init
from kit.base.registry_policy import StoreError

ROOT=Path(__file__).resolve().parents[2]
ENVIRONMENTS=('arena','kilo','copilot')


class DeliveryError(ValueError):pass


class ManualContextSession:
    def __init__(self,layout,destination,*,environment,mode,scope,choices):
        if type(environment) is not str or environment not in ENVIRONMENTS:raise DeliveryError('environment_invalid')
        self.environment=environment;self.destination=Path(destination)
        self.inner=context_export.ContextExportSession(layout,self.destination,mode=mode,scope=scope,choices=choices)
        self.pending=None;self.lock=threading.Lock()

    def _check_destination(self):
        path=self.destination
        if (not path.is_absolute() or '..' in path.parts or not path.name or
            path==ROOT or ROOT in path.parents or path in ROOT.parents):raise DeliveryError('destination_invalid')

    def cancel(self):
        if not self.lock.acquire(False):raise DeliveryError('session_busy')
        try:self.pending=None;self.inner.cancel()
        except StoreError as error:raise DeliveryError(error.code) from error
        finally:self.lock.release()

    def plan(self):
        if not self.lock.acquire(False):raise DeliveryError('session_busy')
        try:
            self.pending=None;self.inner.cancel();self._check_destination()
            try:inner=self.inner.plan()
            except StoreError as error:raise DeliveryError(error.code) from error
            shown=dict(inner);shown.pop('ticket')
            ticket=secrets.token_hex(32)
            p={'outcome':'planned','environment':self.environment,'mechanism':'explicit_manual_transfer_json',
               'export_plan':shown,'ticket':ticket,'created':'not_run','detected':'not_run','read':'not_run',
               'applied':'not_run','delivery':'not_performed','automatic_discovery':'not_claimed',
               'authorization':'not_checked','failure':'unknown_do_not_retry_or_delete'}
            self.pending=(init._canonical(p),inner,ticket,self.environment,self.destination)
            return p
        except StoreError as error:raise DeliveryError(error.code) from error
        finally:self.lock.release()

    def apply(self,plan,*,confirmed_ticket):
        if not self.lock.acquire(False):raise DeliveryError('session_busy')
        try:
            if self.pending is None:raise DeliveryError('ticket_unknown')
            saved,inner,ticket,environment,destination=self.pending
            if (type(confirmed_ticket) is not str or len(confirmed_ticket)!=64 or
                any(c not in '0123456789abcdef' for c in confirmed_ticket) or
                not secrets.compare_digest(ticket,confirmed_ticket)):raise DeliveryError('confirmation_required')
            self.pending=None
            try:
                if type(plan) is not dict or init._canonical(plan)!=saved:raise DeliveryError('plan_mismatch')
                if (self.environment,self.destination)!=(environment,destination):raise DeliveryError('stale_plan')
                self._check_destination()
                result=self.inner.apply(inner,confirmed_ticket=inner['ticket'])
            except StoreError as error:
                self.inner.cancel();raise DeliveryError(error.code) from error
            except (DeliveryError,ValueError,TypeError,RecursionError) as error:
                self.inner.cancel()
                if isinstance(error,DeliveryError):raise
                raise DeliveryError('plan_mismatch') from error
            return dict(result,outcome='manual_context_file_created',environment=environment,
                        mechanism='explicit_manual_transfer_json',created='file_only',detected='not_run',
                        read='not_run',applied='not_run',delivery='not_performed')
        finally:self.lock.release()
