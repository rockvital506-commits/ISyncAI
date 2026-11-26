#!/usr/bin/env python3
"""Опытная подготовка отдельного исходного снимка: план и отдельное подтверждение."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import secrets
import stat
import sys
import threading
from pathlib import Path

MAX_TOTAL = 16 * 1024 * 1024
MAX_LINE = 1_048_576


class ExportError(ValueError):
    pass


def _trusted_loader():
    # Три соседних инструмента доверяются до работы с непроверенным источником.
    path = Path(__file__).resolve().parent / 'snapshot_session.py'
    spec = importlib.util.spec_from_file_location('_trusted_snapshot_export_loader', path)
    if spec is None or spec.loader is None:
        raise ExportError('trusted_loader_unavailable')
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise ExportError('trusted_loader_unavailable') from exc
    return module


def _canonical(data):
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def _directory(path):
    """Проверяет существующие компоненты без ссылок; не защищает от конкурентной замены."""
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise ExportError('path_invalid')
    reparse = getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0)
    for part in (Path(path.anchor), *(Path(path.anchor).joinpath(*path.parts[1:i])
                                      for i in range(2, len(path.parts) + 1))):
        info = part.lstat()
        if not stat.S_ISDIR(info.st_mode) or getattr(info, 'st_file_attributes', 0) & reparse:
            raise ExportError('path_invalid')
    info = path.lstat()
    if (type(info.st_dev) is not int or info.st_dev < 0
            or type(info.st_ino) is not int or info.st_ino <= 0):
        raise ExportError('path_invalid')
    return (info.st_dev, info.st_ino)


def _exists(path):
    try:
        path.lstat()
        return True
    except FileNotFoundError:
        return False


def _source(source, pin, loader, verifier):
    """Только данные и манифест; код выбранного источника не импортируется."""
    if type(pin) is not str or loader.HEX.fullmatch(pin) is None:
        raise ExportError('pin_required')
    try:
        _directory(source)
        _directory(source/'kit')
        _directory(source/'kit/base')
        raw = loader._read_regular(source/'kit/KIT-VERSION.json')
        if hashlib.sha256(raw).hexdigest() != pin:
            raise ExportError('source_unverified')
        doc = json.loads(raw.decode('utf-8'), object_pairs_hook=verifier.no_duplicates)
        if type(doc) is not dict or type(doc.get('files')) is not dict:
            raise ExportError('source_unverified')
        files = doc['files']
        if not files or len(files) > loader.MAX_MEMBERS:
            raise ExportError('source_unverified')
        data = {'kit/KIT-VERSION.json': raw}
        total = len(raw)
        for path, expected in sorted(files.items()):
            if type(path) is not str or type(expected) is not str or loader.HEX.fullmatch(expected) is None:
                raise ExportError('source_unverified')
            if path not in verifier.EXTRA and not (path.startswith('kit/base/')
                                                   and verifier.NAME.fullmatch(path[len('kit/base/'):])):
                raise ExportError('source_unverified')
            content = loader._read_regular(source/path)
            total += len(content)
            if total > MAX_TOTAL or hashlib.sha256(content).hexdigest() != expected:
                raise ExportError('source_unverified')
            data[path] = content
        verifier.verify(source, pin=pin)
        return data
    except ExportError:
        raise
    except (OSError, ValueError, TypeError, KeyError, RecursionError, UnicodeError) as exc:
        raise ExportError('source_unverified') from exc


def _require_sync():
    if (os.name != 'posix' or not hasattr(os, 'O_DIRECTORY') or not hasattr(os, 'O_NOFOLLOW')
            or not hasattr(os, 'fsync')):
        raise ExportError('sync_platform_unavailable')


def _write_exclusive(path, data):
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | getattr(os, 'O_CLOEXEC', 0)
    with os.fdopen(os.open(path, flags, 0o600), 'wb') as stream:
        if stream.write(data) != len(data):
            raise OSError('short write')
        stream.flush()
        os.fsync(stream.fileno())


def _sync_directory(path):
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, 'O_CLOEXEC', 0)
    fd = os.open(path, flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class ExportSession:
    """План/применение в одном процессе; билет не является идентификацией человека."""
    def __init__(self, source, destination, pin, loader, verifier):
        self.source, self.destination = Path(source), Path(destination)
        self.pin, self.loader, self.verifier = pin, loader, verifier
        self.pending = None

    def _paths(self):
        if (not self.source.is_absolute() or not self.destination.is_absolute()
                or '..' in self.source.parts or '..' in self.destination.parts
                or self.destination == Path(self.destination.anchor)):
            raise ExportError('path_invalid')
        source_identity = _directory(self.source)
        parent_identity = _directory(self.destination.parent)
        trusted = Path(__file__).resolve(strict=True).parent
        trusted_identity = _directory(trusted)
        for a, b in ((self.source, self.destination), (self.source, trusted), (self.destination, trusted)):
            if a == b or a.is_relative_to(b) or b.is_relative_to(a):
                raise ExportError('path_overlap')
        if len({source_identity, parent_identity, trusted_identity}) != 3:
            raise ExportError('path_overlap')
        if _exists(self.destination):
            raise ExportError('destination_occupied')
        return source_identity, parent_identity, trusted, trusted_identity

    def plan(self):
        self.pending = None
        try:
            _require_sync()
            topology = self._paths()
            data = _source(self.source, self.pin, self.loader, self.verifier)
            if self._paths() != topology:
                raise ExportError('paths_changed')
            rows = [{'path': path, 'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest()}
                    for path, content in sorted(data.items())]
            result = {'outcome': 'planned', 'source': str(self.source), 'destination': str(self.destination),
                      'manifest_sha256': self.pin, 'directories': ['kit', 'kit/base'], 'files': rows,
                      'publication': {'existing_destination': 'refuse', 'failure': 'leave_unverified',
                                      'directory_mode': '0700_before_umask', 'file_mode': '0600_before_umask',
                                      'sync': 'files_then_directories_bottom_up'},
                      'total_bytes': sum(row['bytes'] for row in rows), 'ticket': secrets.token_hex(32)}
            self.pending = (_canonical(result), data, topology, result['ticket'])
            return result
        except ExportError:
            raise
        except (OSError, ValueError, TypeError, RecursionError) as exc:
            raise ExportError('plan_failed') from exc

    def apply(self, plan, confirmed_ticket):
        if self.pending is None:
            raise ExportError('ticket_unknown')
        saved, data, topology, ticket = self.pending
        if (type(confirmed_ticket) is not str or self.loader.HEX.fullmatch(confirmed_ticket) is None
                or not secrets.compare_digest(confirmed_ticket, ticket)):
            raise ExportError('confirmation_required')
        try:
            if type(plan) is not dict or _canonical(plan) != saved:
                raise ExportError('plan_mismatch')
            _require_sync()
            if self._paths() != topology or _source(self.source, self.pin, self.loader, self.verifier) != data:
                raise ExportError('stale_plan')
        except ExportError:
            self.pending = None
            raise
        except (OSError, ValueError, TypeError, RecursionError) as exc:
            self.pending = None
            raise ExportError('stale_plan') from exc
        self.pending = None
        try:
            os.mkdir(self.destination, 0o700)  # Эксклюзивная резервация без перезаписи.
        except FileExistsError as exc:
            raise ExportError('destination_occupied') from exc
        except OSError as exc:
            raise ExportError('destination_unavailable') from exc
        try:
            os.mkdir(self.destination/'kit', 0o700)
            os.mkdir(self.destination/'kit/base', 0o700)
            for path, content in sorted(data.items()):
                _write_exclusive(self.destination/path, content)
            self.loader._strict_source(self.destination, self.pin, self.verifier)
            # Сначала содержимое, затем имена в каталогах до родителя нового снимка.
            for directory in (self.destination/'kit/base', self.destination/'kit',
                              self.destination, self.destination.parent):
                _sync_directory(directory)
        except Exception as exc:
            # Никогда не удалять даже частично созданный каталог; автоматического отката нет.
            raise ExportError('destination_partial_or_unverified') from exc
        return {'outcome': 'created', 'destination': str(self.destination), 'manifest_sha256': self.pin,
                'files': len(data), 'total_bytes': sum(map(len, data.values()))}


class SignedExportSession:
    """Подпись закрепляет pin для отдельного экспорта; доверие к ключу вне этого API."""
    def __init__(self, source, destination, *, public_key, trusted_key_id, signature,
                 openssl_executable, openssl_pin, loader, verifier, trust):
        self.source, self.destination = Path(source), Path(destination)
        self.public_key, self.trusted_key_id, self.signature = public_key, trusted_key_id, signature
        self.openssl_executable, self.openssl_pin = openssl_executable, openssl_pin
        self.loader, self.verifier, self.trust = loader, verifier, trust
        self.pending = None
        self.lock = threading.Lock()

    def _inputs(self):
        return (self.source,self.destination,self.public_key,self.trusted_key_id,self.signature,
                self.openssl_executable,self.openssl_pin,self.loader,self.verifier,self.trust)

    def _verify(self):
        try:
            return self.trust.verify_signed_source(self.source,public_key=self.public_key,
                    trusted_key_id=self.trusted_key_id,signature=self.signature,
                    openssl_executable=self.openssl_executable,openssl_pin=self.openssl_pin)
        except self.trust.SourceTrustError as error:
            raise ExportError('signed_source_unverified') from error

    def cancel(self):
        if not self.lock.acquire(False):raise ExportError('session_busy')
        try:self.pending=None
        finally:self.lock.release()

    def plan(self):
        if not self.lock.acquire(False):raise ExportError('session_busy')
        try:
            self.pending=None
            inputs=self._inputs();proof=self._verify()
            export=ExportSession(self.source,self.destination,proof['manifest_sha256'],self.loader,self.verifier)
            inner=export.plan()
            # Сводим доказательство и снимок к одному точно показанному билету.
            if self._inputs()!=inputs:raise ExportError('stale_plan')
            result={'outcome':'planned','authentication':proof,'export_plan':inner,
                    'signature_sha256':hashlib.sha256(self.signature).hexdigest(),
                    'openssl_path':str(self.openssl_executable),'openssl_sha256':self.openssl_pin,
                    'source_authentication':'under_explicit_key_and_provider',
                    'key_distribution':'not_verified','installation':'not_performed',
                    'ticket':inner['ticket']}
            self.pending=(_canonical(result),inputs,proof,export,inner,result['ticket'])
            return result
        finally:self.lock.release()

    def apply(self, plan, confirmed_ticket):
        if not self.lock.acquire(False):raise ExportError('session_busy')
        try:
            if self.pending is None:raise ExportError('ticket_unknown')
            saved,inputs,proof,export,inner,ticket=self.pending
            if (type(confirmed_ticket) is not str or self.loader.HEX.fullmatch(confirmed_ticket) is None
                    or not secrets.compare_digest(ticket,confirmed_ticket)):
                raise ExportError('confirmation_required')
            self.pending=None
            try:
                if type(plan) is not dict or _canonical(plan)!=saved:raise ExportError('plan_mismatch')
                if self._inputs()!=inputs or self._verify()!=proof:raise ExportError('stale_plan')
            except ExportError:raise
            except (ValueError,TypeError,RecursionError,UnicodeError) as error:raise ExportError('plan_mismatch') from error
            result=export.apply(inner,confirmed_ticket)
            return dict(result,source_authentication='under_explicit_key_and_provider',
                        key_distribution='not_verified',installation='not_performed')
        finally:self.lock.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--manifest-pin')
    parser.add_argument('--public-key-hex'); parser.add_argument('--trusted-key-id')
    parser.add_argument('--signature-hex'); parser.add_argument('--openssl', type=Path)
    parser.add_argument('--openssl-pin')
    args = parser.parse_args()
    signed = (args.public_key_hex,args.trusted_key_id,args.signature_hex,args.openssl,args.openssl_pin)
    if not ((args.manifest_pin is not None and all(v is None for v in signed)) or
            (args.manifest_pin is None and all(v is not None for v in signed))):
        print('choose_exactly_one_trust_mode', file=sys.stderr);return 2
    if not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode):
        print('isolated_python_required', file=sys.stderr)
        return 2
    try:
        loader = _trusted_loader()
        verifier = loader._trusted_verifier()
        if args.manifest_pin is not None:
            session = ExportSession(args.source, args.destination, args.manifest_pin, loader, verifier)
        else:
            # Вся соседняя копия kit — заранее доверенный инструмент, не source.
            sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
            from kit import source_release_trust as trust
            if trust._PUBLIC.fullmatch(args.public_key_hex) is None or trust._SIGNATURE.fullmatch(args.signature_hex) is None:
                raise ValueError('invalid_signature_input')
            session = SignedExportSession(args.source,args.destination,public_key=bytes.fromhex(args.public_key_hex),
                    trusted_key_id=args.trusted_key_id,signature=bytes.fromhex(args.signature_hex),
                    openssl_executable=args.openssl,openssl_pin=args.openssl_pin,loader=loader,verifier=verifier,trust=trust)
    except Exception:
        print('trusted_loader_unavailable', file=sys.stderr)
        return 2
    while True:
        line = sys.stdin.buffer.readline(MAX_LINE + 1)
        if not line:
            return 0
        if len(line) > MAX_LINE:
            print(json.dumps({'outcome': 'error', 'code': 'input_too_large'}), flush=True)
            return 1
        try:
            request = json.loads(line.decode('utf-8'), object_pairs_hook=session.verifier.no_duplicates,
                                 parse_constant=lambda _: (_ for _ in ()).throw(ValueError('constant')))
            if type(request) is not dict:
                raise ValueError('request')
            if request == {'type': 'plan'}:
                result = session.plan()
            elif (set(request) == {'type', 'plan', 'confirmed_ticket'} and request['type'] == 'apply'
                  and type(request['plan']) is dict and type(request['confirmed_ticket']) is str):
                result = session.apply(request['plan'], request['confirmed_ticket'])
            elif request == {'type': 'cancel'}:
                if isinstance(session,SignedExportSession):session.cancel()
                else:session.pending = None
                result = {'outcome': 'cancelled'}
            else:
                raise ValueError('request')
        except ExportError as exc:
            result = {'outcome': 'error', 'code': str(exc)}
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
            session.pending = None
            result = {'outcome': 'error', 'code': 'invalid_request'}
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False), flush=True)


if __name__ == '__main__':
    raise SystemExit(main())
