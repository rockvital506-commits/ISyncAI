"""Ограниченный Ed25519-проверяющий через явно доверенный OpenSSL; без управления ключами."""
from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path
import stat
import subprocess
import tempfile

from kit.verify_candidate import HEX

# RFC 8410 SubjectPublicKeyInfo: алгоритм Ed25519 и 32 байта публичного ключа.
_SPKI_PREFIX=bytes.fromhex('302a300506032b6570032100')
_MAX_EXECUTABLE=64*1024*1024


class ProviderError(ValueError):
    pass


def _check_provider(path,pin):
    if not isinstance(path,Path) or not path.is_absolute() or '..' in path.parts:
        raise ProviderError('provider_path_invalid')
    if type(pin) is not str or HEX.fullmatch(pin) is None:raise ProviderError('provider_pin_required')
    fd=None
    try:
        info=path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_size<=0 or info.st_size>_MAX_EXECUTABLE
                or not hasattr(os,'O_NOFOLLOW')):raise OSError('unsafe executable')
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|getattr(os,'O_CLOEXEC',0))
        first=os.fstat(fd)
        identity=lambda s:(s.st_dev,s.st_ino,s.st_mode,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
        if identity(first)!=identity(info):raise OSError('provider changed')
        digest=hashlib.sha256();count=0
        while True:
            data=os.read(fd,65536)
            if not data:break
            count+=len(data)
            if count>_MAX_EXECUTABLE:raise OSError('provider too large')
            digest.update(data)
        if count!=first.st_size or identity(first)!=identity(os.fstat(fd)) or identity(first)!=identity(path.lstat()):
            raise OSError('provider changed')
        if not hmac.compare_digest(digest.hexdigest(),pin):raise ProviderError('provider_pin_mismatch')
    except ProviderError:raise
    except (OSError,ValueError,TypeError,AttributeError) as error:raise ProviderError('provider_unavailable') from error
    finally:
        if fd is not None:
            try:os.close(fd)
            except OSError as error:raise ProviderError('provider_unavailable') from error


def verify(public_key,message,signature,*,executable,executable_pin):
    """True только при успешном OpenSSL; False не различает плохую подпись и ошибку провайдера."""
    if (type(public_key) is not bytes or len(public_key)!=32 or type(message) is not bytes or len(message)>4096
            or type(signature) is not bytes or len(signature)!=64):raise ProviderError('provider_input_invalid')
    try:path=Path(executable)
    except (TypeError,ValueError) as error:raise ProviderError('provider_path_invalid') from error
    _check_provider(path,executable_pin)
    try:
        with tempfile.TemporaryDirectory(prefix='domain-ed25519-') as tmp:
            root=Path(tmp)
            for name,content in (('public.der',_SPKI_PREFIX+public_key),('message.bin',message),('signature.bin',signature)):
                target=root/name
                fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
                try:
                    remaining=memoryview(content)
                    while remaining:
                        n=os.write(fd,remaining)
                        if n<=0:raise OSError('short write')
                        remaining=remaining[n:]
                finally:os.close(fd)
            command=[str(path),'pkeyutl','-verify','-pubin','-keyform','DER','-inkey',str(root/'public.der'),
                     '-rawin','-in',str(root/'message.bin'),'-sigfile',str(root/'signature.bin')]
            result=subprocess.run(command,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                                  cwd=root,env={'PATH':os.defpath,'OPENSSL_CONF':os.devnull,'LC_ALL':'C'},timeout=10,check=False)
            return result.returncode==0
    except (OSError,ValueError,subprocess.TimeoutExpired) as error:raise ProviderError('provider_unavailable') from error
