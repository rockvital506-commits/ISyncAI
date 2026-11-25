#!/usr/bin/env python3
"""Опытная move-сессия из закреплённых исходных bytes; не sandbox и не авторизация."""
from __future__ import annotations

import argparse
import hashlib
import importlib.abc
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys

# Закрытый набор определяется доверенным загрузчиком, не выбранным кандидатом.
MODULES={
    'kit.verify_candidate':'kit/verify_candidate.py',
    'kit.init_workspace':'kit/init_workspace.py',
    'kit.move_session_cli':'kit/move_session_cli.py',
    'kit.move_reservation':'kit/move_reservation.py',
    'kit.move_intent_export':'kit/move_intent_export.py',
    'kit.move_execution':'kit/move_execution.py',
    'kit.move_finalize':'kit/move_finalize.py',
    'kit.move_partial_cancel':'kit/move_partial_cancel.py',
    'kit.move_recovery_inspect':'kit/move_recovery_inspect.py',
    'kit.move_replace_stage':'kit/move_replace_stage.py',
    'kit.move_stage_cleanup':'kit/move_stage_cleanup.py',
    'kit.base.move_intent':'kit/base/move_intent.py',
    'kit.base.move_preview':'kit/base/move_preview.py',
    'kit.base.project_specificity':'kit/base/project_specificity.py',
    'kit.base.schema_v2':'kit/base/schema_v2.py',
    'kit.base.registry_policy':'kit/base/registry_policy.py',
    'kit.base.registry_store':'kit/base/registry_store.py',
    'kit.base.registry_journal':'kit/base/registry_journal.py',
    'kit.base.profile_journal':'kit/base/profile_journal.py',
}


class MoveSnapshotError(ValueError):
    pass


def _trusted_loader():
    path=Path(__file__).resolve().parent/'snapshot_session.py'
    spec=importlib.util.spec_from_file_location('_trusted_move_snapshot_loader',path)
    if spec is None or spec.loader is None:raise MoveSnapshotError('trusted_loader_unavailable')
    module=importlib.util.module_from_spec(spec)
    try:spec.loader.exec_module(module)
    except Exception as error:raise MoveSnapshotError('trusted_loader_unavailable') from error
    return module


class MoveFinder(importlib.abc.MetaPathFinder,importlib.abc.Loader):
    def __init__(self,sources):
        if set(sources)!=set(MODULES) or any(type(v) is not bytes for v in sources.values()):
            raise MoveSnapshotError('module_set_invalid')
        self.sources=dict(sources)
    def find_spec(self,fullname,path=None,target=None):
        if fullname in ('kit','kit.base'):return importlib.util.spec_from_loader(fullname,self,is_package=True)
        if fullname in self.sources:return importlib.util.spec_from_loader(fullname,self,is_package=False)
        if fullname.startswith('kit.'):raise ModuleNotFoundError('module is not in verified move allowlist',name=fullname)
        return None
    def create_module(self,spec):return None
    def exec_module(self,module):
        name=module.__name__
        if name in ('kit','kit.base'):module.__path__=[];return
        module.__file__='<verified:'+MODULES[name]+'>'
        exec(compile(self.sources[name],module.__file__,'exec',dont_inherit=True),module.__dict__)


def _capture(root,pin,loader,verifier):
    try:
        doc=loader._strict_source(root,pin,verifier)
        result={}
        for name,path in MODULES.items():
            expected=doc['files'].get(path)
            if type(expected) is not str or loader.HEX.fullmatch(expected) is None:raise MoveSnapshotError('candidate_unverified')
            raw=loader._read_regular(root/path)
            if hashlib.sha256(raw).hexdigest()!=expected:raise MoveSnapshotError('candidate_unverified')
            result[name]=raw
        return result
    except MoveSnapshotError:raise
    except Exception as error:raise MoveSnapshotError('candidate_unverified') from error


def _l0_preflight(workspace,system_pin,version):
    """Проверка одного L0 под SH flock; она намеренно не читает или снимает marker."""
    from kit import move_recovery_inspect as probe
    from kit.base import registry_store, schema_v2
    if (os.name!='posix' or registry_store.fcntl is None or not hasattr(os,'O_NOFOLLOW')
            or not hasattr(os,'O_DIRECTORY') or not hasattr(os,'O_NONBLOCK')
            or os.open not in os.supports_dir_fd or os.stat not in os.supports_dir_fd):
        raise MoveSnapshotError('platform_unsupported')
    opened=[]
    try:
        root=os.open(workspace,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|getattr(os,'O_CLOEXEC',0));opened.append(root)
        registry_store.fcntl.flock(root,registry_store.fcntl.LOCK_SH|registry_store.fcntl.LOCK_NB)
        kit=probe._directory(root,'kit');opened.append(kit)
        base=probe._directory(kit,'base');opened.append(base)
        raw=probe._read(base,'registry.json',probe.move_intent._MAX_INPUT)
        if hashlib.sha256(raw).hexdigest()!=system_pin:raise MoveSnapshotError('system_digest_mismatch')
        document=schema_v2.validate_json(raw,expected_area='L0')
        if document['roots']!=['kit'] or document['release_version']!=version:raise MoveSnapshotError('system_incompatible')
        for parent,name,fd in ((root,'kit',kit),(kit,'base',base)):
            info=os.fstat(fd);named=os.stat(name,dir_fd=parent,follow_symlinks=False)
            if not stat.S_ISDIR(named.st_mode) or (info.st_dev,info.st_ino)!=(named.st_dev,named.st_ino):
                raise MoveSnapshotError('directory_changed')
        info=os.fstat(root);named=os.stat(workspace,follow_symlinks=False)
        if not stat.S_ISDIR(named.st_mode) or (info.st_dev,info.st_ino)!=(named.st_dev,named.st_ino):
            raise MoveSnapshotError('workspace_changed')
    finally:
        failure=None
        for fd in reversed(opened):
            try:os.close(fd)
            except OSError as error:failure=error
        if failure is not None:raise MoveSnapshotError('lock_release_failed') from failure


def run(args):
    if not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode):raise MoveSnapshotError('isolated_python_required')
    if not args.workspace.is_absolute() or not args.candidate_root.is_absolute():raise MoveSnapshotError('root_invalid')
    if any(name=='kit' or name.startswith('kit.') for name in sys.modules):raise MoveSnapshotError('module_namespace_already_loaded')
    loader=_trusted_loader()
    if (type(args.manifest_pin) is not str or loader.HEX.fullmatch(args.manifest_pin) is None or
            type(args.system_pin) is not str or loader.HEX.fullmatch(args.system_pin) is None):raise MoveSnapshotError('pin_required')
    try:roots,identities=loader._roots(args.candidate_root,args.workspace)
    except Exception as error:raise MoveSnapshotError('roots_invalid_or_overlap') from error
    verifier=loader._trusted_verifier()
    sources=_capture(roots[0],args.manifest_pin,loader,verifier)
    sys.meta_path.insert(0,MoveFinder(sources))
    from kit import move_session_cli
    from kit.verify_candidate import CANDIDATE_VERSION
    def preflight():
        if loader._roots(args.candidate_root,args.workspace)!=(roots,identities):raise MoveSnapshotError('roots_changed')
        loader._strict_source(roots[0],args.manifest_pin,verifier)
        _l0_preflight(roots[1],args.system_pin,CANDIDATE_VERSION)
    try:preflight()
    except Exception as error:raise MoveSnapshotError('runtime_unverified') from error
    sys.argv=['verified-move-session','--workspace',str(roots[1]),'--profile-root',args.profile_root]
    return move_session_cli.main(preflight=preflight)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate-root',type=Path,required=True);parser.add_argument('--workspace',type=Path,required=True)
    parser.add_argument('--profile-root',required=True);parser.add_argument('--manifest-pin',required=True);parser.add_argument('--system-pin',required=True)
    args=parser.parse_args()
    try:return run(args)
    except MoveSnapshotError as error:
        print(json.dumps({'outcome':'violation','reason':str(error)},sort_keys=True),file=sys.stderr);return 1
    except Exception:
        print(json.dumps({'outcome':'error','reason':'runtime_failure'},sort_keys=True),file=sys.stderr);return 1

if __name__=='__main__':raise SystemExit(main())
