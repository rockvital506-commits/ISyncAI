#!/usr/bin/env python3
"""Опытная публикация одной глобальной инструкции Copilot; чтение агентом не проверяется."""
from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
from pathlib import Path
import secrets
import stat
import sys
import threading

if __name__=='__main__':sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from kit import init_workspace as init, move_recovery_inspect as probe
from kit.base import registry_store as store, schema_v2
from kit.base.registry_policy import StoreError
from kit.render_rule import RenderError, render
from kit.verify_candidate import HEX

_PREFIX=b'---\napplyTo: "**"\n---\n'
MAX_LINE=1_048_576


def _name(area,entry_id):
    if type(area) is not str or area not in ('L1','L2') or type(entry_id) is not str or schema_v2._ID.fullmatch(entry_id) is None:
        raise StoreError('copilot_target_invalid','entry_id')
    return 'kit-'+area.lower()+'-'+entry_id+'.instructions.md'


def _content(loaded,area,entry_id):
    try:return _PREFIX+render(loaded.documents,area=area,entry_id=entry_id)
    except RenderError as error:raise StoreError('copilot_render_failed','entry_id') from error


def _directories(layout):
    """Открыть и проверить имеющиеся .github/instructions без создания каталогов."""
    roots=store._declared_roots(layout)
    prefix=('.github','instructions')
    for value in roots.values():
        parts=tuple(x.casefold() for x in value.split('/'))
        if parts[:len(prefix)]==prefix or prefix[:len(parts)]==parts:raise StoreError('copilot_root_overlap','destination')
    workspace=store._workspace(layout.workspace);opened=[]
    try:
        root=os.open(workspace,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|getattr(os,'O_CLOEXEC',0));opened.append(root)
        github=probe._directory(root,'.github');opened.append(github)
        dest=probe._directory(github,'instructions');opened.append(dest)
        root_stat=os.fstat(root);named=os.stat(workspace,follow_symlinks=False)
        if not stat.S_ISDIR(named.st_mode) or (root_stat.st_dev,root_stat.st_ino)!=(named.st_dev,named.st_ino):raise OSError('workspace changed')
        identities=[]
        for area,path in roots.items():
            child=root
            for part in path.split('/'):
                child=probe._directory(child,part);opened.append(child)
            info=os.fstat(child);identities.append((info.st_dev,info.st_ino))
        d=os.fstat(dest);g=os.fstat(github)
        if (d.st_dev,d.st_ino) in identities or (g.st_dev,g.st_ino) in identities:raise StoreError('copilot_root_overlap','destination')
        result=(workspace,(root_stat.st_dev,root_stat.st_ino),(g.st_dev,g.st_ino),(d.st_dev,d.st_ino))
        return result
    except BaseException:
        raise
    finally:
        failure=None
        for fd in reversed(opened):
            try:os.close(fd)
            except OSError as error:failure=error
        if failure is not None:raise StoreError('copilot_directory_unavailable','destination') from failure


def _dir_info(layout):
    try:return _directories(layout)
    except StoreError:raise
    except (OSError,ValueError,TypeError,AttributeError,NotImplementedError) as error:
        raise StoreError('copilot_directory_unavailable','destination') from error


def _absent(parent,name):
    try:os.stat(name,dir_fd=parent,follow_symlinks=False)
    except FileNotFoundError:return
    raise StoreError('copilot_target_occupied','destination')


def _open_destination(workspace):
    opened=[]
    try:
        root=os.open(workspace,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|getattr(os,'O_CLOEXEC',0));opened.append(root)
        github=probe._directory(root,'.github');opened.append(github)
        dest=probe._directory(github,'instructions');opened.append(dest)
        return root,github,dest
    except BaseException:
        for fd in reversed(opened):os.close(fd)
        raise


def _ids(workspace,root,github,dest):
    r=os.fstat(root);g=os.fstat(github);d=os.fstat(dest)
    named=os.stat(workspace,follow_symlinks=False);ng=os.stat('.github',dir_fd=root,follow_symlinks=False)
    nd=os.stat('instructions',dir_fd=github,follow_symlinks=False)
    if (not all(stat.S_ISDIR(v.st_mode) for v in (named,ng,nd)) or
        (r.st_dev,r.st_ino)!=(named.st_dev,named.st_ino) or
        (g.st_dev,g.st_ino)!=(ng.st_dev,ng.st_ino) or (d.st_dev,d.st_ino)!=(nd.st_dev,nd.st_ino)):
        raise OSError('directory changed')
    return (workspace,(r.st_dev,r.st_ino),(g.st_dev,g.st_ino),(d.st_dev,d.st_ino))


def _publish(layout,area,entry_id,name,stage_name,content,hashes,identities,uid,gid):
    root=github=dest=stage_fd=None;created=False
    try:
        if (not init._supported() or store.fcntl is None or os.link not in os.supports_dir_fd or
                os.link not in os.supports_follow_symlinks or os.unlink not in os.supports_dir_fd or not hasattr(os,'O_NONBLOCK')):
            raise StoreError('copilot_platform_unavailable','destination')
        workspace=store._workspace(layout.workspace);root,github,dest=_open_destination(workspace)
        if _ids(workspace,root,github,dest)!=identities or _dir_info(layout)!=identities:raise StoreError('stale_plan','destination')
        try:store.fcntl.flock(root,store.fcntl.LOCK_SH|store.fcntl.LOCK_NB)
        except OSError as error:
            if error.errno in (errno.EAGAIN,errno.EACCES):raise StoreError('copilot_busy','workspace') from error
            raise
        loaded=store._load(layout)
        if loaded.inputs_sha256!=hashes or _content(loaded,area,entry_id)!=content:raise StoreError('stale_plan','inputs')
        _absent(dest,name);_absent(dest,stage_name)
        stage_fd=os.open(stage_name,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|getattr(os,'O_CLOEXEC',0),0o600,dir_fd=dest)
        created=True
        init._check_new_fd(stage_fd,directory=False,uid=uid,gid=gid)
        data=memoryview(content)
        while data:
            n=os.write(stage_fd,data)
            if n<=0:raise OSError('short write')
            data=data[n:]
        init._check_new_fd(stage_fd,directory=False,uid=uid,gid=gid);os.fsync(stage_fd)
        prior=probe._identity(os.fstat(stage_fd))
        if probe._read(dest,stage_name,len(content))!=content or probe._identity(os.fstat(stage_fd))!=prior:
            raise OSError('stage changed')
        loaded=store._load(layout)
        if loaded.inputs_sha256!=hashes or _content(loaded,area,entry_id)!=content:raise OSError('inputs changed')
        if _ids(workspace,root,github,dest)!=identities or _dir_info(layout)!=identities:raise OSError('directory changed')
        if probe._identity(os.stat(stage_name,dir_fd=dest,follow_symlinks=False))!=prior:raise OSError('stage changed')
        os.link(stage_name,name,src_dir_fd=dest,dst_dir_fd=dest,follow_symlinks=False)
        linked=os.stat(name,dir_fd=dest,follow_symlinks=False);opened=os.fstat(stage_fd)
        if (linked.st_dev,linked.st_ino)!=(opened.st_dev,opened.st_ino) or opened.st_nlink!=2:raise OSError('link changed')
        current=os.stat(stage_name,dir_fd=dest,follow_symlinks=False)
        if (current.st_dev,current.st_ino)!=(opened.st_dev,opened.st_ino):raise OSError('stage changed')
        os.unlink(stage_name,dir_fd=dest)
        init._check_new_fd(stage_fd,directory=False,uid=uid,gid=gid)
        if probe._read(dest,name,len(content))!=content:raise OSError('published content changed')
        final=os.stat(name,dir_fd=dest,follow_symlinks=False);opened=os.fstat(stage_fd)
        if (final.st_dev,final.st_ino)!=(opened.st_dev,opened.st_ino):raise OSError('published target changed')
        if _ids(workspace,root,github,dest)!=identities:raise OSError('directory changed')
        os.fsync(dest)
    except StoreError as error:
        if created:raise StoreError('copilot_publication_unknown','destination') from error
        raise
    except (OSError,ValueError,TypeError,AttributeError,NotImplementedError) as error:
        raise StoreError('copilot_publication_unknown' if created else 'copilot_unavailable','destination') from error
    finally:
        failure=None
        for fd in (stage_fd,dest,github,root):
            if fd is not None:
                try:os.close(fd)
                except OSError as error:failure=error
        if failure is not None:raise StoreError('copilot_publication_unknown' if created else 'copilot_unavailable','destination') from failure
    return {'outcome':'instruction_file_created','target':'.github/instructions/'+name,
            'content_sha256':hashlib.sha256(content).hexdigest(),'copilot_detected':'not_run',
            'copilot_read':'not_run','copilot_applied':'not_run','durability':'fsync_calls_completed'}


def inspect(layout,*,area,entry_id):
    """Сверить один производный файл с текущим рендером; не доказывает чтение агентом."""
    name=_name(area,entry_id);root=github=dest=None
    try:
        workspace=store._workspace(layout.workspace);root,github,dest=_open_destination(workspace)
        try:store.fcntl.flock(root,store.fcntl.LOCK_SH|store.fcntl.LOCK_NB)
        except OSError as error:
            if error.errno in (errno.EAGAIN,errno.EACCES):raise StoreError('copilot_busy','workspace') from error
            raise
        identities=_ids(workspace,root,github,dest)
        if _dir_info(layout)!=identities:raise OSError('directory changed')
        loaded=store._load(layout);expected=_content(loaded,area,entry_id)
        try:os.stat(name,dir_fd=dest,follow_symlinks=False)
        except FileNotFoundError:actual=None
        else:actual=probe._read(dest,name,65536)
        if _ids(workspace,root,github,dest)!=identities or _dir_info(layout)!=identities:raise OSError('directory changed')
        return {'outcome':'missing' if actual is None else ('matched' if actual==expected else 'different'),
                'target':'.github/instructions/'+name,'expected_sha256':hashlib.sha256(expected).hexdigest(),
                'actual_sha256':None if actual is None else hashlib.sha256(actual).hexdigest(),
                'inputs_sha256':dict(loaded.inputs_sha256),'snapshot':'cooperative_lock_only',
                'copilot_detected':'not_run','copilot_read':'not_run','copilot_applied':'not_run'}
    except StoreError:raise
    except (OSError,ValueError,TypeError,AttributeError,NotImplementedError) as error:
        raise StoreError('copilot_inspection_unavailable','destination') from error
    finally:
        failure=None
        for fd in (dest,github,root):
            if fd is not None:
                try:os.close(fd)
                except OSError as error:failure=error
        if failure is not None:raise StoreError('copilot_inspection_unavailable','destination') from failure


class CopilotDeploymentSession:
    """Один план и билет; не удостоверяет права, согласие, чтение или применение."""
    def __init__(self,layout):self.layout=layout;self._pending=None;self._lock=threading.Lock()
    def cancel(self):
        if not self._lock.acquire(blocking=False):raise StoreError('session_busy','session')
        try:self._pending=None
        finally:self._lock.release()
    def plan(self,*,area,entry_id):
        if not self._lock.acquire(blocking=False):raise StoreError('session_busy','session')
        try:
            self._pending=None;name=_name(area,entry_id);loaded=store._load(self.layout)
            content=_content(loaded,area,entry_id);identities=_dir_info(self.layout)
            root=github=dest=None
            try:
                root,github,dest=_open_destination(identities[0])
                if _ids(identities[0],root,github,dest)!=identities:raise OSError('directory changed')
                _absent(dest,name)
            except StoreError:raise
            except (OSError,ValueError,TypeError) as error:raise StoreError('copilot_directory_unavailable','destination') from error
            finally:
                for fd in (dest,github,root):
                    if fd is not None:os.close(fd)
            ticket=secrets.token_hex(32);stage_name='.copilot-stage-'+ticket+'.tmp'
            result={'outcome':'planned','area':area,'entry_id':entry_id,'target':'.github/instructions/'+name,
                    'staging_target':'.github/instructions/'+stage_name,'scope':'.','apply_to':'**',
                    'content_utf8':content.decode('utf-8'),'content_sha256':hashlib.sha256(content).hexdigest(),
                    'inputs_sha256':dict(loaded.inputs_sha256),'directory_identities':[list(v) for v in identities[1:]],
                    'workspace':str(identities[0]),'uid':os.geteuid(),'gid':os.getegid(),'file_mode':'0600',
                    'effect':'new_instruction_no_overwrite','failure':'leave_unknown_state',
                    'origin':'not_verified','authorization':'not_checked','copilot_read':'not_run',
                    'copilot_applied':'not_run','ticket':ticket}
            self._pending=(init._canonical(result),self.layout,area,entry_id,name,stage_name,content,
                           dict(loaded.inputs_sha256),identities,(result['uid'],result['gid']),ticket)
            return result
        finally:self._lock.release()
    def apply(self,plan,*,confirmed_ticket):
        if not self._lock.acquire(blocking=False):raise StoreError('session_busy','session')
        try:
            if self._pending is None:raise StoreError('ticket_unknown','ticket')
            saved,layout,area,entry_id,name,stage_name,content,hashes,identities,uidgid,ticket=self._pending
            if type(confirmed_ticket) is not str or HEX.fullmatch(confirmed_ticket) is None or not secrets.compare_digest(ticket,confirmed_ticket):
                raise StoreError('confirmation_required','confirmed_ticket')
            self._pending=None
            try:
                if type(plan) is not dict or init._canonical(plan)!=saved:raise StoreError('plan_mismatch','plan')
                if self.layout!=layout or (os.geteuid(),os.getegid())!=uidgid:raise StoreError('stale_plan','inputs')
            except (ValueError,TypeError,RecursionError,UnicodeError) as error:
                if isinstance(error,StoreError):raise
                raise StoreError('plan_mismatch','plan') from error
            return _publish(layout,area,entry_id,name,stage_name,content,hashes,identities,*uidgid)
        finally:self._lock.release()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',type=Path,required=True);parser.add_argument('--profile-root',required=True)
    args=parser.parse_args();session=CopilotDeploymentSession(store.Layout(args.workspace,args.profile_root))
    while True:
        line=sys.stdin.buffer.readline(MAX_LINE+1)
        if not line:return 0
        if len(line)>MAX_LINE:
            session.cancel();print(json.dumps({'outcome':'error','code':'input_too_large'}),flush=True);return 1
        try:
            obj=schema_v2.parse_json(line)
            if type(obj) is not dict:raise ValueError('request')
            if obj.get('type')=='plan' and set(obj)=={'type','area','entry_id'}:
                result=session.plan(area=obj['area'],entry_id=obj['entry_id'])
            elif obj.get('type')=='apply' and set(obj)=={'type','plan','confirmed_ticket'}:
                result=session.apply(obj['plan'],confirmed_ticket=obj['confirmed_ticket'])
            elif obj.get('type')=='inspect' and set(obj)=={'type','area','entry_id'}:
                session.cancel();result=inspect(session.layout,area=obj['area'],entry_id=obj['entry_id'])
            elif obj=={'type':'cancel'}:session.cancel();result={'outcome':'cancelled'}
            else:raise ValueError('request')
            print(json.dumps(result,ensure_ascii=False,sort_keys=True),flush=True)
        except StoreError as error:
            print(json.dumps({'outcome':'error','diagnostic':error.diagnostic()},ensure_ascii=False),flush=True)
        except (schema_v2.SchemaError,ValueError,TypeError,UnicodeError,RecursionError):
            session.cancel();print(json.dumps({'outcome':'error','code':'invalid_request'}),flush=True)

if __name__=='__main__':raise SystemExit(main())
