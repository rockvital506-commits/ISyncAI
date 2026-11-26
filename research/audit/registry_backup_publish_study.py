#!/usr/bin/env python3
"""Опытная публикация снимка реестров в новый каталог, не полная резервная копия."""
import errno
import hashlib
import os
from pathlib import Path
import secrets
import stat
import threading

from kit import atomic_init as atomic, init_workspace as init
from kit.base import registry_store
import registry_backup_study as backup

ROOT=Path(__file__).resolve().parents[2]
PREFIX='.registry-backup-stage-'


class PublishError(ValueError):pass


def _digest(raw):return hashlib.sha256(raw).hexdigest()


def _topology(source,dest):
    if (not source.is_absolute() or not dest.is_absolute() or '..' in source.parts or '..' in dest.parts or
        not dest.name or source==dest or source in dest.parents or dest in source.parents or
        dest==ROOT or ROOT in dest.parents or dest in ROOT.parents):
        raise PublishError('destination_invalid')
    root=parent=None
    try:
        root,a=init._open_parent(source);parent,b=init._open_parent(dest.parent)
        if a==b:raise PublishError('destination_invalid')
        if init._occupied(parent,dest.name):raise PublishError('destination_occupied')
        if any(name.startswith(PREFIX) for name in os.listdir(parent)):raise PublishError('stage_pending')
        return a,b
    except PublishError:raise
    except (init.InitializationError,OSError,ValueError,TypeError,AttributeError,NotImplementedError) as error:
        raise PublishError('destination_unavailable') from error
    finally:
        for fd in (parent,root):
            if fd is not None:
                try:os.close(fd)
                except OSError as error:raise PublishError('destination_unavailable') from error


class BackupSession:
    def __init__(self,layout,destination,*,system_pin):
        if not isinstance(layout,registry_store.Layout):raise PublishError('layout_invalid')
        self.layout=layout;self.destination=Path(destination);self.system_pin=system_pin
        self.pending=None;self.lock=threading.Lock()

    def cancel(self):
        if not self.lock.acquire(False):raise PublishError('session_busy')
        try:self.pending=None
        finally:self.lock.release()

    def plan(self):
        if not self.lock.acquire(False):raise PublishError('session_busy')
        try:
            self.pending=None
            try:
                atomic._rename_function()
                source=Path(self.layout.workspace);dest=self.destination
                topology=_topology(source,dest)
                wire,report=backup.capture(self.layout,system_pin=self.system_pin)
                if topology!=_topology(source,dest):raise PublishError('stale_plan')
                stage=PREFIX+secrets.token_hex(16)
                p={'outcome':'planned','source':str(source),'destination':str(dest),'stage_name':stage,
                   'profile_root':self.layout.profile_root,'system_pin':self.system_pin,'snapshot_sha256':_digest(wire),
                   'snapshot_bytes':len(wire),'snapshot_report':report,'file':'backup.json',
                   'effect':'write_new_directory_only','scope':'three_registries_and_embedded_histories_only',
                   'confidentiality':'not_provided_sensitive_data','authenticity':'not_provided',
                   'failure':'unknown_do_not_retry_or_delete','ticket':secrets.token_hex(32)}
                self.pending=(init._canonical(p),p['ticket'],wire,topology,self.layout,dest,self.system_pin)
                return p
            except PublishError:raise
            except (backup.BackupError,init.InitializationError,OSError,ValueError,TypeError,RecursionError) as error:
                raise PublishError('plan_unavailable') from error
        finally:self.lock.release()

    def apply(self,plan,*,confirmed_ticket):
        if not self.lock.acquire(False):raise PublishError('session_busy')
        try:
            if self.pending is None:raise PublishError('ticket_unknown')
            saved,ticket,wire,topology,layout,dest,pin=self.pending
            if (type(confirmed_ticket) is not str or len(confirmed_ticket)!=64 or
                any(c not in '0123456789abcdef' for c in confirmed_ticket) or
                not secrets.compare_digest(ticket,confirmed_ticket)):raise PublishError('confirmation_required')
            self.pending=None
            try:
                if type(plan) is not dict or init._canonical(plan)!=saved:raise PublishError('plan_mismatch')
                if (self.layout,self.destination,self.system_pin)!=(layout,dest,pin):raise PublishError('stale_plan')
                if _topology(Path(layout.workspace),dest)!=topology:raise PublishError('stale_plan')
                current,_=backup.capture(layout,system_pin=pin)
                if current!=wire:raise PublishError('stale_plan')
            except PublishError:raise
            except (backup.BackupError,ValueError,TypeError,RecursionError) as error:raise PublishError('stale_plan') from error
            parent=stagefd=None;made=attempted=False
            try:
                parent,identity=init._open_parent(dest.parent)
                if identity!=topology[1]:raise PublishError('stale_parent')
                try:registry_store.fcntl.flock(parent,registry_store.fcntl.LOCK_EX|registry_store.fcntl.LOCK_NB)
                except OSError as error:
                    if error.errno in (errno.EACCES,errno.EAGAIN):raise PublishError('publication_busy') from error
                    raise
                if _topology(Path(layout.workspace),dest)!=topology:raise PublishError('stale_parent')
                os.mkdir(plan['stage_name'],0o700,dir_fd=parent);made=True
                stagefd=os.open(plan['stage_name'],os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|getattr(os,'O_CLOEXEC',0),dir_fd=parent)
                stage_id=atomic._identity(os.fstat(stagefd));files={'backup.json':wire};uid,gid=os.geteuid(),os.getegid()
                init._build(stagefd,files,uid,gid);atomic._sync_verified_tree(stagefd,files,uid,gid)
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
                atomic._sync_verified_tree(stagefd,files,uid,gid)
                check,latest=init._open_parent(dest.parent)
                try:
                    if latest!=identity:raise OSError('parent changed')
                finally:os.close(check)
                os.fsync(parent)
                named=os.stat(dest.name,dir_fd=parent,follow_symlinks=False)
                if not stat.S_ISDIR(named.st_mode) or atomic._identity(named)!=stage_id:raise OSError('destination changed')
            except PublishError:raise
            except (init.InitializationError,OSError,ValueError,TypeError,AttributeError,NotImplementedError) as error:
                raise PublishError('publication_unknown' if attempted else 'stage_partial_or_unverified' if made else 'publication_unavailable') from error
            finally:
                failed=False
                for fd in (stagefd,parent):
                    if fd is not None:
                        try:os.close(fd)
                        except OSError:failed=True
                if failed:raise PublishError('publication_unknown' if attempted else 'stage_partial_or_unverified' if made else 'publication_unavailable')
            return {'outcome':'study_snapshot_published','destination':str(dest),'sha256':_digest(wire),
                    'scope':'three_registries_and_embedded_histories_only','authenticity':'not_provided',
                    'confidentiality':'not_provided','recovery':'not_performed','durability':'fsync_calls_completed'}
        finally:self.lock.release()
