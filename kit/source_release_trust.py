#!/usr/bin/env python3
"""Проверка подписи манифеста исходного кандидата; не установщик или обновление."""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import stat
import sys

if __name__=='__main__':sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from kit import openssl_ed25519
from kit.verify_candidate import HEX, VerificationError, verify

_DOMAIN=b'DomainAgentKit:source-manifest-signature:v1\x00'
_MAX_MANIFEST=2_097_152
_PUBLIC=re.compile(r'[0-9a-f]{64}\Z')
_SIGNATURE=re.compile(r'[0-9a-f]{128}\Z')


class SourceTrustError(ValueError):
    pass


def message(public_key,manifest_bytes):
    """Точные байты Ed25519-сообщения; не читает файлы и не подписывает."""
    if type(public_key) is not bytes or len(public_key)!=32 or type(manifest_bytes) is not bytes or len(manifest_bytes)>_MAX_MANIFEST:
        raise SourceTrustError('input_invalid')
    return _DOMAIN+hashlib.sha256(public_key).digest()+hashlib.sha256(manifest_bytes).digest()


def _manifest(root):
    if not isinstance(root,Path) or not root.is_absolute() or '..' in root.parts:raise SourceTrustError('root_invalid')
    if (os.name!='posix' or not hasattr(os,'O_DIRECTORY') or not hasattr(os,'O_NOFOLLOW')
            or not hasattr(os,'O_NONBLOCK') or os.open not in os.supports_dir_fd or os.stat not in os.supports_dir_fd):
        raise SourceTrustError('platform_unavailable')
    opened=[]
    def ident(v):return (v.st_dev,v.st_ino,v.st_mode,v.st_nlink,v.st_size,v.st_mtime_ns,v.st_ctime_ns)
    try:
        flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|getattr(os,'O_CLOEXEC',0)
        r=os.open(root,flags);opened.append(r);k=os.open('kit',flags,dir_fd=r);opened.append(k)
        info=os.stat('KIT-VERSION.json',dir_fd=k,follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_size<=0 or info.st_size>_MAX_MANIFEST:raise OSError('unsafe manifest')
        fd=os.open('KIT-VERSION.json',os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|getattr(os,'O_CLOEXEC',0),dir_fd=k);opened.append(fd)
        if ident(info)!=ident(os.fstat(fd)):raise OSError('manifest changed')
        data=bytearray()
        while len(data)<=_MAX_MANIFEST:
            part=os.read(fd,min(65536,_MAX_MANIFEST+1-len(data)))
            if not part:break
            data.extend(part)
        if (len(data)!=info.st_size or len(data)>_MAX_MANIFEST or ident(info)!=ident(os.fstat(fd)) or
                ident(info)!=ident(os.stat('KIT-VERSION.json',dir_fd=k,follow_symlinks=False))):raise OSError('manifest changed')
        nr=os.stat(root,follow_symlinks=False);nk=os.stat('kit',dir_fd=r,follow_symlinks=False)
        rr=os.fstat(r);kk=os.fstat(k)
        if (not stat.S_ISDIR(nr.st_mode) or not stat.S_ISDIR(nk.st_mode) or
                (nr.st_dev,nr.st_ino)!=(rr.st_dev,rr.st_ino) or (nk.st_dev,nk.st_ino)!=(kk.st_dev,kk.st_ino)):
            raise OSError('directory changed')
        return bytes(data)
    except (OSError,ValueError,TypeError,AttributeError,NotImplementedError) as error:
        raise SourceTrustError('manifest_unavailable') from error
    finally:
        failure=None
        for fd in reversed(opened):
            try:os.close(fd)
            except OSError as error:failure=error
        if failure is not None:raise SourceTrustError('manifest_unavailable') from failure


def verify_signed_source(root,*,public_key,trusted_key_id,signature,openssl_executable,openssl_pin):
    """Проверить независимый key id, Ed25519 манифеста и все файлы текущего кандидата."""
    if type(public_key) is not bytes or len(public_key)!=32 or type(signature) is not bytes or len(signature)!=64:
        raise SourceTrustError('input_invalid')
    if type(trusted_key_id) is not str or HEX.fullmatch(trusted_key_id) is None:raise SourceTrustError('trusted_key_id_required')
    key_id=hashlib.sha256(public_key).hexdigest()
    if not hmac.compare_digest(key_id,trusted_key_id):raise SourceTrustError('untrusted_key')
    try:root=Path(root)
    except (TypeError,ValueError) as error:raise SourceTrustError('root_invalid') from error
    raw=_manifest(root);pin=hashlib.sha256(raw).hexdigest()
    try:accepted=openssl_ed25519.verify(public_key,message(public_key,raw),signature,executable=openssl_executable,executable_pin=openssl_pin)
    except openssl_ed25519.ProviderError as error:raise SourceTrustError(str(error)) from error
    if accepted is not True:raise SourceTrustError('signature_not_verified')
    try:report=verify(root,pin=pin)
    except (VerificationError,ValueError,TypeError,RecursionError) as error:raise SourceTrustError('candidate_unverified') from error
    if _manifest(root)!=raw:raise SourceTrustError('candidate_unverified')
    return {'outcome':'signature_and_candidate_verified','candidate':report['candidate'],
            'manifest_sha256':pin,'key_id':key_id,'files':report['files'],
            'source_authentication':'under_explicit_key_and_provider','owner_identity':'not_checked',
            'installation':'not_performed','runtime_isolation':'not_provided'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate-root',type=Path,required=True);parser.add_argument('--public-key-hex',required=True)
    parser.add_argument('--trusted-key-id',required=True);parser.add_argument('--signature-hex',required=True)
    parser.add_argument('--openssl',type=Path,required=True);parser.add_argument('--openssl-pin',required=True)
    args=parser.parse_args()
    try:
        if _PUBLIC.fullmatch(args.public_key_hex) is None or _SIGNATURE.fullmatch(args.signature_hex) is None:
            raise SourceTrustError('input_invalid')
        result=verify_signed_source(args.candidate_root,public_key=bytes.fromhex(args.public_key_hex),
                    trusted_key_id=args.trusted_key_id,signature=bytes.fromhex(args.signature_hex),
                    openssl_executable=args.openssl,openssl_pin=args.openssl_pin)
    except SourceTrustError as error:
        print(json.dumps({'outcome':'violation','reason':str(error)},sort_keys=True));return 1
    print(json.dumps(result,sort_keys=True));return 0

if __name__=='__main__':raise SystemExit(main())
