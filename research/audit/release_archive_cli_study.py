#!/usr/bin/env python3
"""Опытная проверка архива из заранее доверенного исследовательского checkout, не установка."""
import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import stat
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path[:0]=[str(HERE),str(ROOT)]
import release_archive_study as archive
import release_policy_study as policy_study
from kit import openssl_ed25519 as openssl

HEX=policy_study.HEX
SIGNATURE=re.compile(r'[0-9a-f]{128}\Z')
MAX_POLICY=2_097_152
MAX_STATEMENT=8192


class InputError(ValueError):
    pass


def _identity(info):
    return (info.st_dev,info.st_ino,info.st_mode,info.st_nlink,info.st_uid,info.st_gid,
            info.st_size,info.st_mtime_ns,info.st_ctime_ns)


def read_regular(path, limit):
    """Ограниченное однократное чтение без ссылок в компонентах; не защита от TOCTOU."""
    if (os.name!='posix' or not all(hasattr(os, name) for name in ('O_DIRECTORY','O_NOFOLLOW','O_NONBLOCK'))
            or os.open not in os.supports_dir_fd or os.stat not in os.supports_dir_fd):
        raise InputError('platform_unavailable')
    try:path=Path(path)
    except (ValueError,TypeError) as error:raise InputError('input_path_invalid') from error
    if not path.is_absolute() or '..' in path.parts or not path.name:raise InputError('input_path_invalid')
    opened=[];bindings=[]
    try:
        flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|getattr(os,'O_CLOEXEC',0)
        root=os.open(path.anchor,flags);opened.append(root);parent=root
        for name in path.parts[1:-1]:
            before=os.stat(name,dir_fd=parent,follow_symlinks=False)
            child=os.open(name,flags,dir_fd=parent);opened.append(child)
            actual=os.fstat(child)
            if not stat.S_ISDIR(before.st_mode) or (before.st_dev,before.st_ino)!=(actual.st_dev,actual.st_ino):
                raise OSError('directory changed')
            bindings.append((parent,name,child));parent=child
        before=os.stat(path.name,dir_fd=parent,follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or not 0<before.st_size<=limit:raise OSError('unsafe file')
        fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|getattr(os,'O_CLOEXEC',0),dir_fd=parent);opened.append(fd)
        if _identity(os.fstat(fd))!=_identity(before):raise OSError('file changed')
        data=bytearray()
        while len(data)<=limit:
            chunk=os.read(fd,min(65536,limit+1-len(data)))
            if not chunk:break
            data.extend(chunk)
        if (len(data)!=before.st_size or len(data)>limit or _identity(os.fstat(fd))!=_identity(before) or
                _identity(os.stat(path.name,dir_fd=parent,follow_symlinks=False))!=_identity(before)):
            raise OSError('file changed')
        for container,name,child in bindings:
            current=os.stat(name,dir_fd=container,follow_symlinks=False);held=os.fstat(child)
            if not stat.S_ISDIR(current.st_mode) or (current.st_dev,current.st_ino)!=(held.st_dev,held.st_ino):
                raise OSError('directory changed')
        return bytes(data)
    except (OSError,ValueError,TypeError,AttributeError,NotImplementedError) as error:
        raise InputError('input_unavailable') from error
    finally:
        failure=None
        for fd in reversed(opened):
            try:os.close(fd)
            except OSError as error:failure=error
        if failure is not None:raise InputError('input_unavailable') from failure


def parse_policy(raw, expected_pin):
    if type(expected_pin) is not str or HEX.fullmatch(expected_pin) is None:raise InputError('policy_pin_required')
    if not hmac.compare_digest(hashlib.sha256(raw).hexdigest(),expected_pin):raise InputError('policy_pin_mismatch')
    try:
        value=policy_study._parse(raw)
        if type(value) is not dict or type(value.get('keys')) is not dict:raise ValueError('keys')
        keys={}
        for key_id,pub_hex in value['keys'].items():
            if type(pub_hex) is not str or HEX.fullmatch(pub_hex) is None:raise ValueError('key')
            keys[key_id]=bytes.fromhex(pub_hex)
        return dict(value,keys=keys)
    except (ValueError,TypeError,UnicodeError,RecursionError) as error:raise InputError('policy_invalid') from error


def inspect(archive_path,statement_path,policy_path,*,policy_pin,signature,openssl_path,openssl_pin):
    if type(signature) is not str or SIGNATURE.fullmatch(signature) is None:raise InputError('signature_invalid')
    raw_policy=read_regular(policy_path,MAX_POLICY)
    trusted_policy=parse_policy(raw_policy,policy_pin)
    statement=read_regular(statement_path,MAX_STATEMENT)
    zip_bytes=read_regular(archive_path,archive.MAX_ARCHIVE)
    def verify(public,message,sig):
        return openssl.verify(public,message,sig,executable=Path(openssl_path),executable_pin=openssl_pin)
    try:result=archive.assess(zip_bytes,statement,bytes.fromhex(signature),policy=trusted_policy,verify_signature=verify)
    except archive.ArchiveError as error:raise InputError(str(error)) from error
    return dict(result,policy_sha256=policy_pin,archive_sha256=hashlib.sha256(zip_bytes).hexdigest(),
                policy_pin_origin='assumed_not_verified',provider_origin='assumed_not_verified',
                continuous_integrity='not_provided',authorization='not_checked')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',required=True,type=Path);parser.add_argument('--statement',required=True,type=Path)
    parser.add_argument('--policy',required=True,type=Path);parser.add_argument('--policy-pin',required=True)
    parser.add_argument('--signature-hex',required=True);parser.add_argument('--openssl',required=True,type=Path)
    parser.add_argument('--openssl-pin',required=True)
    args=parser.parse_args()
    if not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode):
        print(json.dumps({'outcome':'violation','reason':'isolated_python_required'}));return 2
    try:
        result=inspect(args.archive,args.statement,args.policy,policy_pin=args.policy_pin,signature=args.signature_hex,
                       openssl_path=args.openssl,openssl_pin=args.openssl_pin)
    except (InputError,ValueError,TypeError) as error:
        print(json.dumps({'outcome':'violation','reason':str(error)},sort_keys=True));return 1
    print(json.dumps(result,sort_keys=True));return 0


if __name__=='__main__':raise SystemExit(main())
