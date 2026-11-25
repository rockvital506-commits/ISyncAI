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


def _write_exclusive(path, data):
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
    with os.fdopen(os.open(path, flags, 0o600), 'wb') as stream:
        stream.write(data)


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
        _directory(self.source)
        parent_identity = _directory(self.destination.parent)
        if self.destination.is_relative_to(self.source) or self.source.is_relative_to(self.destination):
            raise ExportError('path_overlap')
        if _exists(self.destination):
            raise ExportError('destination_occupied')
        return parent_identity

    def plan(self):
        self.pending = None
        try:
            parent = self._paths()
            data = _source(self.source, self.pin, self.loader, self.verifier)
            if self._paths() != parent:
                raise ExportError('destination_changed')
            rows = [{'path': path, 'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest()}
                    for path, content in sorted(data.items())]
            result = {'outcome': 'planned', 'source': str(self.source), 'destination': str(self.destination),
                      'manifest_sha256': self.pin, 'directories': ['kit', 'kit/base'], 'files': rows,
                      'publication': {'existing_destination': 'refuse', 'failure': 'leave_unverified',
                                      'directory_mode': '0700_before_umask', 'file_mode': '0600_before_umask'},
                      'total_bytes': sum(row['bytes'] for row in rows), 'ticket': secrets.token_hex(32)}
            self.pending = (_canonical(result), data, parent, result['ticket'])
            return result
        except ExportError:
            raise
        except (OSError, ValueError, TypeError, RecursionError) as exc:
            raise ExportError('plan_failed') from exc

    def apply(self, plan, confirmed_ticket):
        if self.pending is None:
            raise ExportError('ticket_unknown')
        saved, data, parent, ticket = self.pending
        if (type(confirmed_ticket) is not str or self.loader.HEX.fullmatch(confirmed_ticket) is None
                or not secrets.compare_digest(confirmed_ticket, ticket)):
            raise ExportError('confirmation_required')
        try:
            if type(plan) is not dict or _canonical(plan) != saved:
                raise ExportError('plan_mismatch')
            if self._paths() != parent or _source(self.source, self.pin, self.loader, self.verifier) != data:
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
        except Exception as exc:
            # Никогда не удалять даже частично созданный каталог; автоматического отката нет.
            raise ExportError('destination_partial_or_unverified') from exc
        return {'outcome': 'created', 'destination': str(self.destination), 'manifest_sha256': self.pin,
                'files': len(data), 'total_bytes': sum(map(len, data.values()))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--manifest-pin', required=True)
    args = parser.parse_args()
    if not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode):
        print('isolated_python_required', file=sys.stderr)
        return 2
    try:
        loader = _trusted_loader()
        session = ExportSession(args.source, args.destination, args.manifest_pin, loader, loader._trusted_verifier())
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
                session.pending = None
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
