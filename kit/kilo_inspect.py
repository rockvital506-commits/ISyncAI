#!/usr/bin/env python3
"""Разовая read-only сверка одного производного правила Kilo с текущим реестром."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kit.base import registry_store
from kit.base.registry_store import Layout, StoreError
from kit.kilo_deploy import DeployError, _dirs, target_name
from kit.render_rule import RenderError, render

MAX_TARGET_BYTES = 65_536


class InspectionError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _regular(info):
    return (stat.S_ISREG(info.st_mode) and info.st_nlink == 1
            and not getattr(info, 'st_file_attributes', 0) & registry_store._REPARSE)


def _identity(info):
    return (info.st_dev, info.st_ino)


def _version(info):
    return (_identity(info), info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _read_target(path):
    """Один ограниченный файл; нет гарантии от соперничающего процесса с теми же правами."""
    try:
        before = path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise InspectionError('target_unreadable') from exc
    if not _regular(before):
        raise InspectionError('unsafe_target')
    if before.st_size > MAX_TARGET_BYTES:
        raise InspectionError('target_too_large')
    flags = (os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
             | getattr(os, 'O_NONBLOCK', 0))
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise InspectionError('target_unreadable') from exc
    try:
        opened = os.fstat(fd)
        if not _regular(opened) or _version(opened) != _version(before):
            raise InspectionError('target_changed')
        data = bytearray()
        while len(data) <= MAX_TARGET_BYTES:
            chunk = os.read(fd, min(8192, MAX_TARGET_BYTES + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        if len(data) > MAX_TARGET_BYTES:
            raise InspectionError('target_too_large')
        after_fd = os.fstat(fd)
        after_path = path.lstat()
        if (not _regular(after_fd) or not _regular(after_path)
                or _version(opened) != _version(after_fd) or _version(after_fd) != _version(after_path)
                or len(data) != after_fd.st_size):
            raise InspectionError('target_changed')
        return bytes(data)
    except OSError as exc:
        raise InspectionError('target_unreadable') from exc
    finally:
        try:
            os.close(fd)
        except OSError as exc:
            raise InspectionError('target_unreadable') from exc


def inspect(layout, *, area, entry_id):
    """Только результат сравнения, не содержимое и не проверка выполнения средой."""
    name = target_name(area, entry_id)
    loaded = registry_store._load(layout)
    directory, _ = _dirs(loaded)
    try:
        expected = render(loaded.documents, area=area, entry_id=entry_id)
    except RenderError:
        expected = None
    actual = _read_target(directory / name)
    if expected is None:
        outcome = 'source_unrenderable'
    elif actual is None:
        outcome = 'missing'
    else:
        outcome = 'current' if actual == expected else 'different'
    return {'inspection_format': 1, 'outcome': outcome, 'area': area, 'entry_id': entry_id,
            'target': '.kilo/rules/' + name, 'target_present': actual is not None,
            'inputs_sha256': dict(loaded.inputs_sha256),
            'expected_sha256': None if expected is None else hashlib.sha256(expected).hexdigest(),
            'target_sha256': None if actual is None else hashlib.sha256(actual).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--profile-root', required=True)
    parser.add_argument('--area', choices=('L1', 'L2'), required=True)
    parser.add_argument('--entry-id', required=True)
    args = parser.parse_args()
    try:
        result = inspect(Layout(args.workspace, args.profile_root), area=args.area, entry_id=args.entry_id)
    except StoreError as exc:
        print(json.dumps({'outcome': 'error', 'diagnostic': exc.diagnostic()}, ensure_ascii=False), file=sys.stderr)
        return 1
    except (DeployError, InspectionError) as exc:
        print(json.dumps({'outcome': 'error', 'code': exc.code}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
