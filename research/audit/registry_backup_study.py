#!/usr/bin/env python3
"""Закрытый in-memory снимок трёх реестров, не готовая резервная копия."""
import base64
import binascii
import errno
import hashlib
import json
import os
from pathlib import Path
import stat

from kit import init_workspace as init, move_recovery_inspect as probe
from kit.base import registry_journal, registry_policy, registry_store, schema_v2
from kit.base.registry_policy import StoreError
from kit.verify_candidate import HEX

MAX_ENTRY=2_097_152
MAX_WIRE=9_000_000
AREAS=('L0','L1','L2')


class BackupError(ValueError):
    pass


def _hash(data):return hashlib.sha256(data).hexdigest()


def _canonical(obj):
    return json.dumps(obj,ensure_ascii=True,sort_keys=True,separators=(',',':'),allow_nan=False).encode('ascii')


def _pairs(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('duplicate')
        result[key]=value
    return result


def _check_data(profile_root, system_pin, data):
    if type(system_pin) is not str or HEX.fullmatch(system_pin) is None:raise BackupError('system_pin_required')
    if type(profile_root) is not str or type(data) is not dict or set(data)!=set(AREAS):
        raise BackupError('snapshot_invalid')
    if any(type(value) is not bytes or not 0<len(value)<=MAX_ENTRY for value in data.values()):
        raise BackupError('snapshot_invalid')
    if _hash(data['L0'])!=system_pin:raise BackupError('system_pin_mismatch')
    try:
        roots=registry_store._declared_roots(registry_store.Layout(None,profile_root))
        documents={'L0':schema_v2.validate_json(data['L0'],expected_area='L0')}
        for area in ('L1','L2'):
            documents[area],_=registry_journal.unpack_registry(schema_v2.parse_json(data[area]),area=area)
        for area in AREAS:
            if documents[area]['roots']!=[roots[area]]:raise BackupError('root_mismatch')
        schema_v2.validate_catalog(documents)
        if registry_policy.find_conflicts(documents):raise BackupError('catalog_conflict')
    except BackupError:raise
    except (StoreError,schema_v2.SchemaError,ValueError,TypeError,KeyError,RecursionError) as error:
        raise BackupError('snapshot_invalid') from error
    return documents


def _bounded_capture(layout):
    """Открытые dirfd и ограниченные чтения; не защита от произвольного писателя."""
    if (not init._supported() or registry_store.fcntl is None or not hasattr(os,'O_NONBLOCK')
            or os.listdir not in os.supports_fd):raise BackupError('source_unavailable:platform')
    try:
        workspace=Path(layout.workspace)
        if not workspace.is_absolute() or '..' in workspace.parts:raise BackupError('layout_invalid')
        roots=registry_store._declared_roots(layout)
    except StoreError as error:raise BackupError('source_unavailable:'+error.code) from error
    except (ValueError,TypeError) as error:raise BackupError('layout_invalid') from error
    opened=[];bindings=[]
    def child(parent,name):
        fd=probe._directory(parent,name);opened.append(fd);bindings.append((parent,name,fd));return fd
    def barriers(fds):
        registry_store._refuse_profile_copy_stages_fd(fds['L1'])
        try:os.stat('.move-pending',dir_fd=fds['L2'],follow_symlinks=False)
        except FileNotFoundError:return
        raise BackupError('source_unavailable:move_pending')
    try:
        root,identity=init._open_parent(workspace);opened.append(root)
        try:registry_store.fcntl.flock(root,registry_store.fcntl.LOCK_SH|registry_store.fcntl.LOCK_NB)
        except OSError as error:
            if error.errno in (errno.EAGAIN,errno.EACCES):raise BackupError('source_unavailable:read_busy') from error
            raise
        fds={}
        for area,path in roots.items():
            fd=root
            for component in path.split('/'):fd=child(fd,component)
            fds[area]=fd
        ids=[(os.fstat(fd).st_dev,os.fstat(fd).st_ino) for fd in fds.values()]
        if len(set(ids))!=3:raise OSError('root alias')
        barriers(fds)
        registry_dirs={}
        for area in AREAS:
            fd=fds[area];components=registry_store._SUFFIX[area].split('/')
            for component in components[:-1]:fd=child(fd,component)
            registry_dirs[area]=(fd,components[-1])
        data={area:probe._read(fd,name,MAX_ENTRY) for area,(fd,name) in registry_dirs.items()}
        for area,(fd,name) in registry_dirs.items():
            if probe._read(fd,name,MAX_ENTRY)!=data[area]:raise OSError('registry changed')
        barriers(fds)
        for parent,name,fd in bindings:
            current=os.stat(name,dir_fd=parent,follow_symlinks=False);held=os.fstat(fd)
            if not stat.S_ISDIR(current.st_mode) or (current.st_dev,current.st_ino)!=(held.st_dev,held.st_ino):
                raise OSError('directory changed')
        check,latest=init._open_parent(workspace)
        try:
            if identity!=latest:raise OSError('workspace changed')
        finally:os.close(check)
        return workspace,data
    except BackupError:raise
    except StoreError as error:raise BackupError('source_unavailable:'+error.code) from error
    except (init.InitializationError,OSError,ValueError,TypeError,AttributeError,NotImplementedError) as error:
        raise BackupError('source_unavailable:unsafe_or_changed') from error
    finally:
        failed=False
        for fd in reversed(opened):
            try:os.close(fd)
            except OSError:failed=True
        if failed:raise BackupError('source_unavailable:close_failed')


def capture(layout, *, system_pin):
    """Только чтение, cooperative SH flock во время ограниченной загрузки."""
    if not isinstance(layout,registry_store.Layout):raise BackupError('layout_invalid')
    workspace,data=_bounded_capture(layout)
    _check_data(layout.profile_root,system_pin,data)
    doc={'format':1,'product':'DomainAgentKit','profile_root':layout.profile_root,
         'system_sha256':system_pin,
         'registries':{area:{'sha256':_hash(data[area]),'bytes':len(data[area]),
                             'base64':base64.b64encode(data[area]).decode('ascii')} for area in AREAS}}
    wire=_canonical(doc)
    if len(wire)>MAX_WIRE:raise BackupError('snapshot_too_large')
    return wire, {'outcome':'memory_snapshot_captured','source':str(workspace),
                  'file_sha256':_hash(wire),'scope':'three_registries_and_embedded_histories_only',
                  'concurrency':'cooperative_lock_during_read_only','origin':'not_verified',
                  'authenticity':'not_verified','backup_file':'not_written','restore':'not_performed'}


def inspect(wire, *, system_pin):
    """Проверка границ и структуры; самохеши не являются подтверждением авторства."""
    if type(wire) is not bytes or not 0<len(wire)<=MAX_WIRE:raise BackupError('snapshot_invalid')
    try:
        def reject(_):raise ValueError('constant')
        obj=json.loads(wire.decode('ascii'),object_pairs_hook=_pairs,parse_constant=reject)
        if (type(obj) is not dict or set(obj)!={'format','product','profile_root','system_sha256','registries'} or
            type(obj['format']) is not int or obj['format']!=1 or obj['product']!='DomainAgentKit' or
            type(obj['registries']) is not dict or set(obj['registries'])!=set(AREAS) or _canonical(obj)!=wire):
            raise BackupError('snapshot_invalid')
        if obj['system_sha256']!=system_pin:raise BackupError('system_pin_mismatch')
        data={}
        for area,row in obj['registries'].items():
            if (type(row) is not dict or set(row)!={'sha256','bytes','base64'} or
                type(row['bytes']) is not int or not 0<row['bytes']<=MAX_ENTRY or
                type(row['sha256']) is not str or HEX.fullmatch(row['sha256']) is None or
                type(row['base64']) is not str or len(row['base64'])>4*((MAX_ENTRY+2)//3)):
                raise BackupError('snapshot_invalid')
            raw=base64.b64decode(row['base64'],validate=True)
            if len(raw)!=row['bytes'] or _hash(raw)!=row['sha256'] or base64.b64encode(raw).decode('ascii')!=row['base64']:
                raise BackupError('snapshot_invalid')
            data[area]=raw
        _check_data(obj['profile_root'],system_pin,data)
        return {'outcome':'memory_snapshot_structurally_valid','profile_root':obj['profile_root'],
                'file_sha256':_hash(wire),'registries_sha256':{a:_hash(data[a]) for a in AREAS},
                'scope':'three_registries_and_embedded_histories_only','origin':'not_verified',
                'authenticity':'not_verified','restore':'not_performed'},data
    except BackupError:raise
    except (ValueError,TypeError,UnicodeError,RecursionError,KeyError,binascii.Error) as error:
        raise BackupError('snapshot_invalid') from error
