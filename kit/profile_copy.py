"""Опытное копирование L1 в строго пустой L1 другого workspace; не слияние."""
from __future__ import annotations

from contextlib import contextmanager
import argparse
from difflib import unified_diff
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys
import threading

if __name__ == '__main__':
    sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from kit import init_workspace as init, move_recovery_inspect as probe
from kit.base import registry_policy, registry_store as store, schema_v2
from kit.base.registry_policy import StoreError
from kit.verify_candidate import HEX

MAX_PROFILE = 2_097_152


def _fingerprint(info):
    return (info.st_dev,info.st_ino,info.st_mode,info.st_nlink,info.st_uid,info.st_gid,
            info.st_size,info.st_mtime_ns,info.st_ctime_ns)


@contextmanager
def _locked_pair(source, target, *, write):
    if (not init._supported() or store.fcntl is None or not hasattr(os,'O_NONBLOCK')
            or os.listdir not in os.supports_fd):
        raise StoreError('profile_copy_unavailable','workspace')
    paths = [store._workspace(source.workspace),store._workspace(target.workspace)]
    if paths[0] == paths[1] or paths[0] in paths[1].parents or paths[1] in paths[0].parents:
        raise StoreError('profile_copy_overlap','workspace')
    handles=[]; yielded=False
    try:
        for path in paths:
            fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|getattr(os,'O_CLOEXEC',0))
            handles.append(fd)
        identities=[(os.fstat(fd).st_dev,os.fstat(fd).st_ino) for fd in handles]
        if (len(set(identities))!=2 or any(ino<=0 or dev<0 for dev,ino in identities)):
            raise StoreError('profile_copy_overlap','workspace')
        for index in sorted(range(2),key=lambda i:identities[i]):
            try:
                mode=store.fcntl.LOCK_EX if write and index==1 else store.fcntl.LOCK_SH
                store.fcntl.flock(handles[index],mode|store.fcntl.LOCK_NB)
            except OSError as error:
                if error.errno in (errno.EACCES,errno.EAGAIN):raise StoreError('profile_copy_busy','workspace') from error
                raise
        def check_roots():
            for path,fd,identity in zip(paths,handles,identities):
                named=os.stat(path,follow_symlinks=False);opened=os.fstat(fd)
                if (not stat.S_ISDIR(named.st_mode) or not stat.S_ISDIR(opened.st_mode)
                        or (named.st_dev,named.st_ino)!=identity or (opened.st_dev,opened.st_ino)!=identity):
                    raise OSError('root changed')
        check_roots()
        yielded=True
        yield paths,tuple(identities),check_roots
        check_roots()
    except StoreError:
        raise
    except (OSError,ValueError,TypeError,AttributeError,NotImplementedError) as error:
        raise StoreError('profile_copy_unknown' if write and yielded else 'profile_copy_unavailable','workspace') from error
    finally:
        failure=None
        for fd in reversed(handles):
            try:os.close(fd)
            except OSError as error:failure=error
        if failure is not None:raise StoreError('profile_copy_unknown' if write else 'profile_copy_unavailable','workspace') from failure


def _capture(source,target,pin):
    if type(pin) is not str or HEX.fullmatch(pin) is None:raise StoreError('system_pin_required','L0')
    if source.profile_root!=target.profile_root:raise StoreError('profile_copy_root_mismatch','profile_root')
    a=store._load_unlocked(source);b=store._load_unlocked(target)
    if a.raw['L0']!=b.raw['L0'] or hashlib.sha256(a.raw['L0']).hexdigest()!=pin:
        raise StoreError('profile_copy_system_mismatch','L0')
    facts=[]
    for current in (a,b):
        per_area={}
        for area in ('L0','L1','L2'):
            raw=current.raw[area]
            if len(raw)>MAX_PROFILE:raise StoreError('profile_copy_too_large',area)
            parent=None
            try:
                parent,_=init._open_parent(current.files[area].parent)
                info=os.stat(current.files[area].name,dir_fd=parent,follow_symlinks=False)
                if (probe._read(parent,current.files[area].name,MAX_PROFILE)!=raw or
                    _fingerprint(info)!=_fingerprint(os.stat(current.files[area].name,dir_fd=parent,follow_symlinks=False))):
                    raise OSError('registry changed')
                per_area[area]=_fingerprint(info)
            except (init.InitializationError,OSError,ValueError,TypeError) as error:
                raise StoreError('profile_copy_unavailable',area) from error
            finally:
                if parent is not None:
                    try:os.close(parent)
                    except OSError as error:raise StoreError('profile_copy_unavailable',area) from error
        facts.append(per_area)
    try:empty=init._files(a.raw['L0'],pin,source.profile_root)[source.profile_root+'/registry.json']
    except init.InitializationError as error:raise StoreError('profile_copy_system_invalid','L0') from error
    parent=None
    try:
        parent,_=init._open_parent(b.files['L1'].parent)
        if any(name.startswith('.profile-copy-stage-') for name in os.listdir(parent)):
            raise StoreError('profile_copy_stage_present','L1')
    except StoreError:
        raise
    except (init.InitializationError,OSError,ValueError,TypeError) as error:
        raise StoreError('profile_copy_unavailable','L1') from error
    finally:
        if parent is not None:
            try:os.close(parent)
            except OSError as error:raise StoreError('profile_copy_unavailable','L1') from error
    if a.raw['L1']==b.raw['L1']:
        return a,b,None
    if b.raw['L1']!=empty:raise StoreError('profile_copy_target_not_pristine','L1')
    docs=dict(b.documents,L1=a.documents['L1'])
    try:schema_v2.validate_catalog(docs)
    except schema_v2.SchemaError as error:raise StoreError('profile_copy_catalog_invalid','L1',schema=error) from error
    if registry_policy.find_conflicts(docs):raise StoreError('profile_copy_conflict','L1')
    # Не допускаем общие физические корни областей двух workspace, насколько видны inode.
    identities=[]
    for current in (a,b):
        for area in ('L0','L1','L2'):
            info=os.stat(current.workspace/current.roots[area],follow_symlinks=False)
            identities.append((info.st_dev,info.st_ino))
    if len(set(identities))!=6:raise StoreError('profile_copy_overlap','roots')
    return a,b,tuple(facts)


def _replace(parent,stage,before,after):
    """Одна замена; stage остаётся при сбое, состояние после создания неизвестно."""
    fd=None;original=None;made=False
    try:
        first=os.stat('registry.json',dir_fd=parent,follow_symlinks=False)
        if probe._read(parent,'registry.json',MAX_PROFILE)!=before:raise OSError('target changed')
        original=os.open('registry.json',os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|getattr(os,'O_CLOEXEC',0),dir_fd=parent)
        init._check_new_fd(original,directory=False,uid=os.geteuid(),gid=os.getegid())
        if _fingerprint(os.fstat(original))!=_fingerprint(first):raise OSError('target changed')
        fd=os.open(stage,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|getattr(os,'O_CLOEXEC',0),0o600,dir_fd=parent);made=True
        init._check_new_fd(fd,directory=False,uid=os.geteuid(),gid=os.getegid())
        remaining=memoryview(after)
        while remaining:
            n=os.write(fd,remaining)
            if n<=0:raise OSError('short write')
            remaining=remaining[n:]
        init._check_new_fd(fd,directory=False,uid=os.geteuid(),gid=os.getegid());os.fsync(fd)
        staged=_fingerprint(os.fstat(fd))
        if (probe._read(parent,stage,MAX_PROFILE)!=after or
                _fingerprint(os.stat(stage,dir_fd=parent,follow_symlinks=False))!=staged or
                _fingerprint(os.fstat(original))!=_fingerprint(first) or
                _fingerprint(os.stat('registry.json',dir_fd=parent,follow_symlinks=False))!=_fingerprint(first) or
                probe._read(parent,'registry.json',MAX_PROFILE)!=before):raise OSError('target or stage changed')
        os.replace(stage,'registry.json',src_dir_fd=parent,dst_dir_fd=parent)
        os.fsync(parent)
        if probe._read(parent,'registry.json',MAX_PROFILE)!=after:raise OSError('result changed')
        named=os.stat('registry.json',dir_fd=parent,follow_symlinks=False)
        if (named.st_dev,named.st_ino)!=(staged[0],staged[1]):raise OSError('result changed')
    except (OSError,ValueError,TypeError,AttributeError,NotImplementedError,init.InitializationError) as error:
        raise StoreError('profile_copy_unknown' if made else 'profile_copy_unavailable','L1') from error
    finally:
        failure=None
        for handle in (fd,original):
            if handle is not None:
                try:os.close(handle)
                except OSError as error:failure=error
        if failure is not None:raise StoreError('profile_copy_unknown' if made else 'profile_copy_unavailable','L1') from failure


class ProfileCopySession:
    """Явная разовая копия в пустой L1; билет не удостоверяет право или согласие."""
    def __init__(self,source,target,*,system_pin):
        if not isinstance(source,store.Layout) or not isinstance(target,store.Layout):raise StoreError('invalid_layout','workspace')
        self.source,self.target,self.system_pin=source,target,system_pin
        self.pending=None;self.lock=threading.Lock()

    def cancel(self):
        if not self.lock.acquire(False):raise StoreError('session_busy','session')
        try:self.pending=None
        finally:self.lock.release()

    def plan(self):
        if not self.lock.acquire(False):raise StoreError('session_busy','session')
        try:
            self.pending=None
            with _locked_pair(self.source,self.target,write=False) as (paths,ids,_):
                a,b,facts=_capture(self.source,self.target,self.system_pin)
                if facts is None:return {'outcome':'no_change','reason':'same_bytes'}
                before,after=b.raw['L1'],a.raw['L1']
                diff=''.join(unified_diff(before.decode('utf-8').splitlines(keepends=True),after.decode('utf-8').splitlines(keepends=True),fromfile='target/L1-before',tofile='target/L1-after'))
                stage='.profile-copy-stage-'+secrets.token_hex(16)
                result={'outcome':'planned','source_workspace':str(paths[0]),'target_workspace':str(paths[1]),
                        'workspace_identities':[list(v) for v in ids],'profile_root':self.source.profile_root,
                        'system_pin':self.system_pin,'source_inputs_sha256':a.inputs_sha256,'target_inputs_sha256':b.inputs_sha256,
                        'source_input_modes':a.input_modes,'target_input_modes':b.input_modes,
                        'source_file_metadata':{area:list(value) for area,value in facts[0].items()},
                        'target_file_metadata':{area:list(value) for area,value in facts[1].items()},
                        'metadata_fields':['device','inode','mode','links','uid','gid','size','mtime_ns','ctime_ns'],
                        'process_uid':os.geteuid(),'process_gid':os.getegid(),
                        'target_before_utf8':before.decode('utf-8'),'target_after_utf8':after.decode('utf-8'),
                        'unified_diff':diff,'stage_name':stage,'ticket':secrets.token_hex(32),
                        'source_preserved':True,'target_policy':'exact_pristine_only','histories':'copied_exactly_not_authenticated',
                        'synchronization':'not_implemented','authorization':'not_checked',
                        'failure':'stage_or_target_unverified_do_not_retry_or_delete','concurrency':'cooperative_locks_only'}
                self.pending=(init._canonical(result),result['ticket'],ids,facts,dict(a.raw),dict(b.raw),self.source,self.target,self.system_pin)
                return result
        finally:self.lock.release()

    def apply(self,plan,*,confirmed_ticket):
        if not self.lock.acquire(False):raise StoreError('session_busy','session')
        try:
            if self.pending is None:raise StoreError('ticket_unknown','ticket')
            saved,ticket,ids,facts,araw,braw,source,target,pin=self.pending
            if type(confirmed_ticket) is not str or not secrets.compare_digest(confirmed_ticket,ticket):
                raise StoreError('confirmation_required','ticket')
            self.pending=None
            try:
                if type(plan) is not dict or init._canonical(plan)!=saved:raise StoreError('plan_mismatch','plan')
                if (self.source,self.target,self.system_pin)!=(source,target,pin):raise StoreError('stale_plan','layout')
                if (os.geteuid(),os.getegid())!=(plan['process_uid'],plan['process_gid']):raise StoreError('stale_plan','identity')
                with _locked_pair(source,target,write=True) as (paths,current_ids,check_roots):
                    a,b,current_facts=_capture(source,target,pin)
                    if current_ids!=ids or current_facts!=facts or a.raw!=araw or b.raw!=braw:
                        raise StoreError('stale_plan','inputs')
                    parent,identity=init._open_parent(b.files['L1'].parent)
                    try:
                        named=os.stat(b.files['L1'].parent,follow_symlinks=False)
                        if (named.st_dev,named.st_ino)!=identity:raise StoreError('stale_plan','parent')
                        check_roots()
                        _replace(parent,plan['stage_name'],braw['L1'],araw['L1'])
                        check_roots()
                    finally:
                        try:os.close(parent)
                        except OSError as error:raise StoreError('profile_copy_unknown','L1') from error
                return {'outcome':'profile_copied','source_sha256':hashlib.sha256(araw['L1']).hexdigest(),
                        'target_sha256':hashlib.sha256(araw['L1']).hexdigest(),
                        'source_preserved':True,'history_authenticity':'not_verified',
                        'authorization':'not_checked','sync':'not_implemented','durability':'fsync_calls_completed'}
            except (TypeError,ValueError,UnicodeError,RecursionError) as error:
                if isinstance(error,StoreError):raise
                raise StoreError('plan_mismatch','plan') from error
        finally:self.lock.release()


_STAGE_NAME = re.compile(r'\.profile-copy-stage-[0-9a-f]{32}\Z')


def inspect_target(layout, *, stage_name, before_sha256, after_sha256):
    """Только наблюдение сохранённых имён/хешей, без снятия барьера или авторизации."""
    if not isinstance(layout,store.Layout):raise StoreError('invalid_layout','workspace')
    if (type(stage_name) is not str or _STAGE_NAME.fullmatch(stage_name) is None or
            any(type(v) is not str or HEX.fullmatch(v) is None for v in (before_sha256,after_sha256))):
        raise StoreError('profile_copy_inspect_invalid','inputs')
    if not init._supported() or store.fcntl is None or not hasattr(os,'O_NONBLOCK'):
        raise StoreError('profile_copy_inspect_unavailable','workspace')
    roots=store._declared_roots(layout);workspace=store._workspace(layout.workspace)
    opened=[];bindings=[]
    def observe(parent,name):
        try:info=os.stat(name,dir_fd=parent,follow_symlinks=False)
        except FileNotFoundError:return {'state':'absent'}
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:
            return {'state':'unsafe_type_or_links'}
        if info.st_size<0 or info.st_size>MAX_PROFILE:return {'state':'too_large'}
        data=probe._read(parent,name,MAX_PROFILE)
        digest=hashlib.sha256(data).hexdigest()
        matches=[]
        if digest==before_sha256:matches.append('before')
        if digest==after_sha256:matches.append('after')
        return {'state':'read','sha256':digest,'size':len(data),'matches':matches}
    try:
        flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|getattr(os,'O_CLOEXEC',0)
        root=os.open(workspace,flags);opened.append(root)
        initial=os.fstat(root);named=os.stat(workspace,follow_symlinks=False)
        if (not stat.S_ISDIR(initial.st_mode) or not stat.S_ISDIR(named.st_mode) or initial.st_ino<=0 or
                (initial.st_dev,initial.st_ino)!=(named.st_dev,named.st_ino)):raise OSError('workspace changed')
        try:store.fcntl.flock(root,store.fcntl.LOCK_SH|store.fcntl.LOCK_NB)
        except OSError as error:
            if error.errno in (errno.EAGAIN,errno.EACCES):raise StoreError('profile_copy_inspect_busy','workspace') from error
            raise
        parent=root
        for component in roots['L1'].split('/'):
            child=probe._directory(parent,component);opened.append(child);bindings.append((parent,component,child));parent=child
        registry=observe(parent,'registry.json');stage=observe(parent,stage_name)
        for directory,name,child in bindings:
            a=os.fstat(child);b=os.stat(name,dir_fd=directory,follow_symlinks=False)
            if not stat.S_ISDIR(b.st_mode) or (a.st_dev,a.st_ino)!=(b.st_dev,b.st_ino):raise OSError('directory changed')
        named=os.stat(workspace,follow_symlinks=False)
        if not stat.S_ISDIR(named.st_mode) or (initial.st_dev,initial.st_ino)!=(named.st_dev,named.st_ino):raise OSError('workspace changed')
        return {'outcome':'observation_only','workspace':str(workspace),'profile_root':roots['L1'],
                'stage_name':stage_name,'registry':registry,'stage':stage,
                'before_sha256':before_sha256,'after_sha256':after_sha256,
                'origin':'not_verified','authorization':'not_verified','durability':'not_verified',
                'completion':'not_verified','recovery':'not_performed','snapshot':'cooperative_lock_only'}
    except StoreError:raise
    except (OSError,ValueError,TypeError,AttributeError,NotImplementedError) as error:
        raise StoreError('profile_copy_inspect_unavailable','workspace') from error
    finally:
        failure=None
        for fd in reversed(opened):
            try:os.close(fd)
            except OSError as error:failure=error
        if failure is not None:raise StoreError('profile_copy_inspect_unavailable','workspace') from failure


MAX_LINE=32*1024*1024


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-workspace',type=Path,required=True)
    parser.add_argument('--target-workspace',type=Path,required=True)
    parser.add_argument('--profile-root',required=True)
    parser.add_argument('--system-pin',required=True)
    args=parser.parse_args()
    if not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode):
        print('isolated_python_required',file=sys.stderr);return 2
    session=ProfileCopySession(store.Layout(args.source_workspace,args.profile_root),
                               store.Layout(args.target_workspace,args.profile_root),system_pin=args.system_pin)
    def respond(obj):print(json.dumps(obj,ensure_ascii=False,sort_keys=True,allow_nan=False),flush=True)
    while True:
        line=sys.stdin.buffer.readline(MAX_LINE+1)
        if not line:return 0
        if len(line)>MAX_LINE:
            session.cancel();respond({'outcome':'error','code':'input_too_large'});return 1
        try:
            request=schema_v2.parse_json(line)
            if request=={'type':'plan'}:
                result=session.plan()
                if result.get('outcome')=='planned':
                    sample={'type':'apply','plan':result,'confirmed_ticket':result['ticket']}
                    if len(json.dumps(sample,ensure_ascii=False).encode('utf-8'))+1>MAX_LINE:
                        session.cancel();raise StoreError('profile_copy_plan_too_large','plan')
            elif (type(request) is dict and set(request)=={'type','stage_name','before_sha256','after_sha256'}
                  and request['type']=='inspect'):
                session.cancel()
                result=inspect_target(session.target,stage_name=request['stage_name'],
                                      before_sha256=request['before_sha256'],after_sha256=request['after_sha256'])
            elif request=={'type':'cancel'}:
                session.cancel();result={'outcome':'cancelled'}
            elif (type(request) is dict and set(request)=={'type','plan','confirmed_ticket'} and request['type']=='apply'
                  and type(request['plan']) is dict and type(request['confirmed_ticket']) is str):
                result=session.apply(request['plan'],confirmed_ticket=request['confirmed_ticket'])
            else:
                session.cancel();raise ValueError('invalid request')
        except StoreError as error:
            result={'outcome':'error','diagnostic':error.diagnostic()}
        except (schema_v2.SchemaError,ValueError,TypeError,UnicodeError,RecursionError):
            session.cancel();result={'outcome':'error','code':'invalid_request'}
        respond(result)


if __name__=='__main__':raise SystemExit(main())
