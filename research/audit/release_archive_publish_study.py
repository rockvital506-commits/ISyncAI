#!/usr/bin/env python3
"""Стендовая публикация проверенных bytes в новую цель; не установщик выпуска."""
import copy
import errno
import hashlib
import os
from pathlib import Path
import re
import secrets
import stat
import threading

try:
    import fcntl
except ImportError:
    fcntl=None

import release_archive_study as archive
from kit import atomic_init as atomic, atomic_init_inspect as observer, init_workspace as init
from kit.init_workspace import InitializationError

ROOT=Path(__file__).resolve().parents[2]
STAGE=re.compile(r'\.domain-release-stage-[0-9a-f]{32}\Z')


class PublishError(ValueError):
    pass


def _digest(raw):return hashlib.sha256(raw).hexdigest()


class PublishSession:
    """Только данные в памяти и одна новая цель, без извлечения ZIP и запуска кода."""
    def __init__(self,destination,*,archive_bytes,statement,signature,policy,verify_signature):
        self.destination=Path(destination);self.archive_bytes=archive_bytes;self.statement=statement
        self.signature=signature;self.policy=copy.deepcopy(policy);self.verify_signature=verify_signature
        self.pending=None;self.lock=threading.Lock()

    def _capture(self):
        try:return archive.capture(self.archive_bytes,self.statement,self.signature,
                                   policy=self.policy,verify_signature=self.verify_signature)
        except archive.ArchiveError as error:raise PublishError('archive_unverified') from error

    def cancel(self):
        if not self.lock.acquire(False):raise PublishError('session_busy')
        try:self.pending=None
        finally:self.lock.release()

    def inspect(self, *, stage_name):
        """Наблюдение двух имён, без восстановления, удаления и гарантии атомарности."""
        if not self.lock.acquire(False):raise PublishError('session_busy')
        try:
            self.pending=None
            dest=self.destination
            if (type(stage_name) is not str or STAGE.fullmatch(stage_name) is None or
                    not dest.is_absolute() or '..' in dest.parts or not dest.name or stage_name==dest.name or
                    dest==ROOT or ROOT in dest.parents or dest in ROOT.parents):
                raise PublishError('inspection_invalid')
            if not init._supported() or os.listdir not in os.supports_fd or not hasattr(os,'O_NONBLOCK'):
                raise PublishError('inspection_unavailable')
            parent=None
            try:
                report,rows=self._capture();files=dict(rows)
                parent,identity=init._open_parent(dest.parent)
                uid,gid=os.geteuid(),os.getegid()
                target=observer._observe(parent,dest.name,files,uid,gid)
                stage=observer._observe(parent,stage_name,files,uid,gid)
                check,latest=init._open_parent(dest.parent)
                try:
                    if identity!=latest:raise OSError('parent changed')
                finally:os.close(check)
                return {'outcome':'observation_only','destination':str(dest),'stage_name':stage_name,
                        'destination_state':target,'stage_state':stage,'verification':report,
                        'origin':'not_verified','authorization':'not_checked','completion':'not_verified',
                        'durability':'not_verified','recovery':'not_performed','snapshot':'not_atomic'}
            except PublishError:raise
            except (InitializationError,OSError,ValueError,TypeError,AttributeError,NotImplementedError) as error:
                raise PublishError('inspection_unavailable') from error
            finally:
                if parent is not None:
                    try:os.close(parent)
                    except OSError as error:raise PublishError('inspection_unavailable') from error
        finally:self.lock.release()

    def plan(self):
        if not self.lock.acquire(False):raise PublishError('session_busy')
        try:
            self.pending=None
            try:
                atomic._rename_function()
                if fcntl is None or not hasattr(fcntl,'flock'):raise PublishError('publication_lock_unavailable')
                dest=self.destination
                if (not dest.is_absolute() or '..' in dest.parts or not dest.name or
                        dest==ROOT or ROOT in dest.parents or dest in ROOT.parents):
                    raise PublishError('destination_invalid')
                report,rows=self._capture()
                fd,identity=init._open_parent(dest.parent)
                try:
                    if init._occupied(fd,dest.name):raise PublishError('destination_occupied')
                    if any(name.startswith('.domain-release-stage-') for name in os.listdir(fd)):
                        raise PublishError('stage_pending')
                finally:os.close(fd)
                stage='.domain-release-stage-'+secrets.token_hex(16)
                summary={'channel':self.policy['channel'],'key_ids':sorted(self.policy['keys']),
                         'revoked':sorted(self.policy['revoked']),'checkpoint':copy.deepcopy(self.policy['checkpoint']),
                         'loader_sha256':self.policy['loader_sha256'],'verifier_sha256':self.policy['verifier_sha256']}
                result={'outcome':'planned','destination':str(dest),'stage_name':stage,'parent_identity':list(identity),
                        'process_uid':os.geteuid(),'process_gid':os.getegid(),'archive_sha256':_digest(self.archive_bytes),
                        'statement_sha256':_digest(self.statement),'signature_sha256':_digest(self.signature),
                        'verification':report,'external_policy_summary':summary,
                        'files':[{'path':path,'bytes':len(data),'sha256':_digest(data)} for path,data in rows],
                        'effect':'publish_new_snapshot_only','failure':'stage_or_destination_unknown_do_not_retry',
                        'concurrency':'cooperative_parent_flock_only',
                        'authorization':'not_checked','trust_anchor':'assumed_not_verified','ticket':secrets.token_hex(32)}
                self.pending=(init._canonical(result),dest,identity,rows,report,copy.deepcopy(self.policy),
                              self.archive_bytes,self.statement,self.signature,self.verify_signature,result['ticket'],
                              (result['process_uid'],result['process_gid']))
                return result
            except PublishError:raise
            except (InitializationError,OSError,ValueError,TypeError,RecursionError) as error:
                raise PublishError('plan_unavailable') from error
        finally:self.lock.release()

    def apply(self,plan,*,confirmed_ticket):
        if not self.lock.acquire(False):raise PublishError('session_busy')
        try:
            if self.pending is None:raise PublishError('ticket_unknown')
            saved,dest,identity,rows,report,pol,raw,statement,signature,callback,ticket,uidgid=self.pending
            if type(confirmed_ticket) is not str or not secrets.compare_digest(confirmed_ticket,ticket):
                raise PublishError('confirmation_required')
            self.pending=None
            try:
                if type(plan) is not dict or init._canonical(plan)!=saved:raise PublishError('plan_mismatch')
                if (self.destination!=dest or self.policy!=pol or self.archive_bytes!=raw or self.statement!=statement or
                        self.signature!=signature or self.verify_signature is not callback or (os.geteuid(),os.getegid())!=uidgid):
                    raise PublishError('stale_plan')
                current_report,current_rows=self._capture()
                if ((current_report,current_rows)!=(report,rows) or self.policy!=pol or self.destination!=dest or
                        self.archive_bytes!=raw or self.statement!=statement or self.signature!=signature or
                        self.verify_signature is not callback or (os.geteuid(),os.getegid())!=uidgid):
                    raise PublishError('stale_plan')
            except PublishError:raise
            except (ValueError,TypeError,RecursionError,UnicodeError) as error:raise PublishError('plan_mismatch') from error
            parent=None;stage_fd=None;made=False;attempted=False
            try:
                atomic._rename_function()
                parent,current=init._open_parent(dest.parent)
                if current!=identity:raise PublishError('stale_parent')
                if fcntl is None or not hasattr(fcntl,'flock'):raise PublishError('publication_lock_unavailable')
                try:fcntl.flock(parent,fcntl.LOCK_EX|fcntl.LOCK_NB)
                except OSError as error:
                    if error.errno in (errno.EACCES,errno.EAGAIN):raise PublishError('publication_busy') from error
                    raise PublishError('publication_lock_unavailable') from error
                check,latest=init._open_parent(dest.parent)
                try:
                    if latest!=identity:raise PublishError('stale_parent')
                finally:os.close(check)
                if init._occupied(parent,dest.name):raise PublishError('destination_occupied')
                if any(name.startswith('.domain-release-stage-') for name in os.listdir(parent)):
                    raise PublishError('stage_pending')
                os.mkdir(plan['stage_name'],0o700,dir_fd=parent);made=True
                stage_fd=os.open(plan['stage_name'],os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|getattr(os,'O_CLOEXEC',0),dir_fd=parent)
                stage_id=atomic._identity(os.fstat(stage_fd));data=dict(rows)
                init._build(stage_fd,data,*uidgid)
                atomic._sync_verified_tree(stage_fd,data,*uidgid)
                named=os.stat(plan['stage_name'],dir_fd=parent,follow_symlinks=False)
                if atomic._identity(named)!=stage_id:raise OSError('stage changed')
                check,latest=init._open_parent(dest.parent)
                try:
                    if latest!=identity:raise OSError('parent changed')
                finally:os.close(check)
                os.fsync(parent)
                attempted=True
                atomic._rename_noreplace(parent,plan['stage_name'],dest.name)
                named=os.stat(dest.name,dir_fd=parent,follow_symlinks=False)
                if not stat.S_ISDIR(named.st_mode) or atomic._identity(named)!=stage_id:
                    raise OSError('published name changed')
                atomic._sync_verified_tree(stage_fd,data,*uidgid)
                check,latest=init._open_parent(dest.parent)
                try:
                    if latest!=identity:raise OSError('parent changed')
                finally:os.close(check)
                os.fsync(parent)
                named=os.stat(dest.name,dir_fd=parent,follow_symlinks=False)
                if not stat.S_ISDIR(named.st_mode) or atomic._identity(named)!=stage_id:
                    raise OSError('published name changed')
            except PublishError:raise
            except (InitializationError,OSError,ValueError,TypeError,AttributeError,NotImplementedError) as error:
                raise PublishError('publication_unknown' if attempted else 'stage_partial_or_unverified' if made else 'publication_unavailable') from error
            finally:
                failure=None
                for fd in (stage_fd,parent):
                    if fd is not None:
                        try:os.close(fd)
                        except OSError as error:failure=error
                if failure is not None:
                    raise PublishError('publication_unknown' if attempted else 'stage_partial_or_unverified' if made else 'publication_unavailable') from failure
            return {'outcome':'snapshot_published_unverified_origin','destination':str(dest),'files':len(rows),
                    'archive_sha256':_digest(raw),'authorization':'not_checked','installation':'not_performed',
                    'durability':'fsync_calls_completed','trust_anchor':'assumed_not_verified'}
        finally:self.lock.release()
