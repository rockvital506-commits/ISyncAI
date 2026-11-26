#!/usr/bin/env python3
"""Опытное восстановление трёх реестров в новый workspace; не полное восстановление Kit."""
import errno
import hashlib
import hmac
import os
from pathlib import Path
import secrets
import stat
import threading

from kit import atomic_init as atomic, init_workspace as init
from kit.base import registry_store
from kit.verify_candidate import HEX
import registry_backup_study as backup

ROOT=Path(__file__).resolve().parents[2]
PREFIX='.registry-restore-stage-'


class RestoreError(ValueError):pass


def _checked(wire,snapshot_pin,system_pin):
    if type(snapshot_pin) is not str or HEX.fullmatch(snapshot_pin) is None:
        raise RestoreError('snapshot_pin_required')
    if type(wire) is not bytes or not 0<len(wire)<=backup.MAX_WIRE:
        raise RestoreError('snapshot_invalid')
    if not hmac.compare_digest(hashlib.sha256(wire).hexdigest(),snapshot_pin):
        raise RestoreError('snapshot_pin_mismatch')
    try:report,data=backup.inspect(wire,system_pin=system_pin)
    except backup.BackupError as error:raise RestoreError('snapshot_unusable') from error
    profile=report['profile_root']
    files={'kit/base/registry.json':data['L0'],profile+'/registry.json':data['L1'],
           '.domain-agent-kit/project/registry.json':data['L2']}
    if len(files)!=3 or any('/'.join(p.split('/')[:i]) in files
            for p in files for i in range(1,len(p.split('/')))):
        raise RestoreError('snapshot_unusable')
    return report,files


def _parent(dest):
    if (not dest.is_absolute() or '..' in dest.parts or not dest.name or
        dest==ROOT or ROOT in dest.parents or dest in ROOT.parents):raise RestoreError('destination_invalid')
    parent=None
    try:
        parent,identity=init._open_parent(dest.parent)
        if init._occupied(parent,dest.name):raise RestoreError('destination_occupied')
        if any(name.startswith(PREFIX) for name in os.listdir(parent)):raise RestoreError('stage_pending')
        return identity
    except RestoreError:raise
    except (init.InitializationError,OSError,ValueError,TypeError,AttributeError,NotImplementedError) as error:
        raise RestoreError('destination_unavailable') from error
    finally:
        if parent is not None:
            try:os.close(parent)
            except OSError as error:raise RestoreError('destination_unavailable') from error


class RestoreSession:
    def __init__(self,destination,*,wire,snapshot_pin,system_pin):
        self.destination=Path(destination);self.wire=wire
        self.snapshot_pin=snapshot_pin;self.system_pin=system_pin
        self.pending=None;self.lock=threading.Lock()

    def cancel(self):
        if not self.lock.acquire(False):raise RestoreError('session_busy')
        try:self.pending=None
        finally:self.lock.release()

    def plan(self):
        if not self.lock.acquire(False):raise RestoreError('session_busy')
        try:
            self.pending=None
            try:
                atomic._rename_function()
                if registry_store.fcntl is None:raise RestoreError('platform_unavailable')
                report,files=_checked(self.wire,self.snapshot_pin,self.system_pin)
                identity=_parent(self.destination)
                uid,gid=os.geteuid(),os.getegid()
                p={'outcome':'planned','destination':str(self.destination),'stage_name':PREFIX+secrets.token_hex(16),
                   'snapshot_sha256':self.snapshot_pin,'system_sha256':self.system_pin,
                   'profile_root':report['profile_root'],'process_uid':uid,'process_gid':gid,
                   'files':[{'path':path,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
                            for path,data in sorted(files.items())],
                   'effect':'restore_only_three_registries_in_new_workspace',
                   'scope':'not_kit_or_project_files','source_origin':'not_verified','pin_origin':'assumed_not_verified',
                   'authorization':'not_checked','failure':'unknown_do_not_retry_or_delete','ticket':secrets.token_hex(32)}
                self.pending=(init._canonical(p),p['ticket'],files,identity,self.destination,self.wire,
                              self.snapshot_pin,self.system_pin,(uid,gid))
                return p
            except RestoreError:raise
            except (init.InitializationError,OSError,ValueError,TypeError,RecursionError) as error:
                raise RestoreError('plan_unavailable') from error
        finally:self.lock.release()

    def apply(self,plan,*,confirmed_ticket):
        if not self.lock.acquire(False):raise RestoreError('session_busy')
        try:
            if self.pending is None:raise RestoreError('ticket_unknown')
            saved,ticket,files,identity,dest,wire,snapshot_pin,system_pin,uidgid=self.pending
            if (type(confirmed_ticket) is not str or len(confirmed_ticket)!=64 or
                any(c not in '0123456789abcdef' for c in confirmed_ticket) or
                not secrets.compare_digest(ticket,confirmed_ticket)):raise RestoreError('confirmation_required')
            self.pending=None
            try:
                if type(plan) is not dict or init._canonical(plan)!=saved:raise RestoreError('plan_mismatch')
                if (self.destination,self.wire,self.snapshot_pin,self.system_pin,(os.geteuid(),os.getegid()))!=(dest,wire,snapshot_pin,system_pin,uidgid):
                    raise RestoreError('stale_plan')
                if _checked(wire,snapshot_pin,system_pin)[1]!=files or _parent(dest)!=identity:
                    raise RestoreError('stale_plan')
            except RestoreError:raise
            except (ValueError,TypeError,RecursionError) as error:raise RestoreError('plan_mismatch') from error
            parent=stagefd=None;made=attempted=False
            try:
                parent,current=init._open_parent(dest.parent)
                if current!=identity:raise RestoreError('stale_parent')
                try:registry_store.fcntl.flock(parent,registry_store.fcntl.LOCK_EX|registry_store.fcntl.LOCK_NB)
                except OSError as error:
                    if error.errno in (errno.EACCES,errno.EAGAIN):raise RestoreError('publication_busy') from error
                    raise
                if _parent(dest)!=identity:raise RestoreError('stale_parent')
                os.mkdir(plan['stage_name'],0o700,dir_fd=parent);made=True
                stagefd=os.open(plan['stage_name'],os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|getattr(os,'O_CLOEXEC',0),dir_fd=parent)
                stage_id=atomic._identity(os.fstat(stagefd))
                init._build(stagefd,files,*uidgid);atomic._sync_verified_tree(stagefd,files,*uidgid)
                named=os.stat(plan['stage_name'],dir_fd=parent,follow_symlinks=False)
                if not stat.S_ISDIR(named.st_mode) or atomic._identity(named)!=stage_id:raise OSError('stage changed')
                check,latest=init._open_parent(dest.parent)
                try:
                    if latest!=identity:raise OSError('parent changed')
                finally:os.close(check)
                os.fsync(parent);attempted=True
                atomic._rename_noreplace(parent,plan['stage_name'],dest.name)
                named=os.stat(dest.name,dir_fd=parent,follow_symlinks=False)
                if not stat.S_ISDIR(named.st_mode) or atomic._identity(named)!=stage_id:raise OSError('destination changed')
                atomic._sync_verified_tree(stagefd,files,*uidgid)
                check,latest=init._open_parent(dest.parent)
                try:
                    if latest!=identity:raise OSError('parent changed')
                finally:os.close(check)
                os.fsync(parent)
                named=os.stat(dest.name,dir_fd=parent,follow_symlinks=False)
                if not stat.S_ISDIR(named.st_mode) or atomic._identity(named)!=stage_id:raise OSError('destination changed')
            except RestoreError:raise
            except (init.InitializationError,OSError,ValueError,TypeError,AttributeError,NotImplementedError) as error:
                raise RestoreError('publication_unknown' if attempted else 'stage_partial_or_unverified' if made else 'publication_unavailable') from error
            finally:
                failed=False
                for fd in (stagefd,parent):
                    if fd is not None:
                        try:os.close(fd)
                        except OSError:failed=True
                if failed:raise RestoreError('publication_unknown' if attempted else 'stage_partial_or_unverified' if made else 'publication_unavailable')
            return {'outcome':'study_registries_restored_unverified_origin','destination':str(dest),
                    'snapshot_sha256':snapshot_pin,'scope':'three_registries_and_embedded_histories_only',
                    'kit_and_project_files':'not_restored','authorization':'not_checked',
                    'durability':'fsync_calls_completed'}
        finally:self.lock.release()
