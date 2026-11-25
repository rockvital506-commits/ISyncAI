#!/usr/bin/env python3
"""Опытная сессия из закреплённых исходных байтов; не установщик и не sandbox."""
from __future__ import annotations

import argparse
import hashlib
import importlib.abc
import importlib.util
import json
import os
import re
import stat
import sys
from pathlib import Path

MAX_INPUT = 2_097_152
HEX = re.compile(r'[0-9a-f]{64}')
# Закрытый список только для данного сценария; другие команды не поддерживаются.
MODULES = {
    'kit.verify_candidate': 'kit/verify_candidate.py',
    'kit.guard': 'kit/guard.py',
    'kit.session_cli': 'kit/session_cli.py',
    'kit.base.schema_v2': 'kit/base/schema_v2.py',
    'kit.base.registry_policy': 'kit/base/registry_policy.py',
    'kit.base.profile_journal': 'kit/base/profile_journal.py',
    'kit.base.registry_journal': 'kit/base/registry_journal.py',
    'kit.base.registry_store': 'kit/base/registry_store.py',
    'kit.base.operation_card': 'kit/base/operation_card.py',
    'kit.base.operation_plan': 'kit/base/operation_plan.py',
    'kit.base.bootstrap': 'kit/base/bootstrap.py',
}
START_FILES = {'entry': 'kit/base/entry.txt', 'start': 'kit/base/START.md'}


class SnapshotError(ValueError):
    pass


def _read_regular(path):
    """Не следует конечной ссылке при доступной поддержке; не защита от гонок каталогов."""
    try:
        before = path.lstat()
        reparse = getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or getattr(before, 'st_file_attributes', 0) & reparse or before.st_size > MAX_INPUT):
            raise SnapshotError('source_file_invalid')
        flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
        fd = os.open(path, flags)
        with os.fdopen(fd, 'rb') as stream:
            opened = os.fstat(stream.fileno())
            if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
                    or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)):
                raise SnapshotError('source_file_invalid')
            raw = stream.read(MAX_INPUT + 1)
        if len(raw) > MAX_INPUT:
            raise SnapshotError('source_file_invalid')
        return raw
    except (OSError, ValueError) as exc:
        raise SnapshotError('source_file_invalid') from exc


def capture(candidate_root, manifest_pin, verifier):
    """Проверить срез, затем закрепить исполняемые модули по тому же pin в памяти."""
    if type(manifest_pin) is not str or HEX.fullmatch(manifest_pin) is None:
        raise SnapshotError('pin_required')
    try:
        root = Path(candidate_root)
        if not root.is_absolute():
            raise SnapshotError('candidate_root_invalid')
        root = root.resolve(strict=True)
        verifier.verify(root, pin=manifest_pin)
        raw = _read_regular(root / 'kit/KIT-VERSION.json')
        if hashlib.sha256(raw).hexdigest() != manifest_pin:
            raise SnapshotError('candidate_unverified')
        doc = json.loads(raw.decode('utf-8'), object_pairs_hook=verifier.no_duplicates)
        def read_pinned(path):
            expected = doc['files'].get(path)
            if type(expected) is not str or HEX.fullmatch(expected) is None:
                raise SnapshotError('candidate_unverified')
            content = _read_regular(root / path)
            if hashlib.sha256(content).hexdigest() != expected:
                raise SnapshotError('candidate_unverified')
            return content
        sources = {name: read_pinned(path) for name, path in MODULES.items()}
        start = {name: read_pinned(path) for name, path in START_FILES.items()}
        return root, sources, start
    except SnapshotError:
        raise
    except (verifier.VerificationError, OSError, TypeError, ValueError, KeyError, UnicodeError, RecursionError) as exc:
        raise SnapshotError('candidate_unverified') from exc


class SnapshotFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Закрытый набор kit-модулей загружается только из переданных проверенных байтов."""
    def __init__(self, sources):
        if set(sources) != set(MODULES) or any(type(value) is not bytes for value in sources.values()):
            raise SnapshotError('module_set_invalid')
        self.sources = dict(sources)

    def find_spec(self, fullname, path=None, target=None):
        if fullname in ('kit', 'kit.base'):
            return importlib.util.spec_from_loader(fullname, self, is_package=True)
        if fullname in self.sources:
            return importlib.util.spec_from_loader(fullname, self, is_package=False)
        if fullname.startswith('kit.'):
            raise ModuleNotFoundError('module is not in verified session allowlist', name=fullname)
        return None

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        name = module.__name__
        if name in ('kit', 'kit.base'):
            module.__path__ = []
            return
        raw = self.sources[name]
        module.__file__ = '<verified:' + MODULES[name] + '>'
        code = compile(raw, module.__file__, 'exec', dont_inherit=True)
        exec(code, module.__dict__)


def _trusted_verifier():
    # Загрузчик и этот соседний проверяющий доверяются ДО любых действий с кандидатом.
    path = Path(__file__).resolve().parent / 'verify_candidate.py'
    spec = importlib.util.spec_from_file_location('_trusted_snapshot_verifier', path)
    if spec is None or spec.loader is None:
        raise SnapshotError('trusted_verifier_unavailable')
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise SnapshotError('trusted_verifier_unavailable') from exc
    return module


def run(args):
    if not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode):
        raise SnapshotError('isolated_python_required')
    if type(args.system_pin) is not str or HEX.fullmatch(args.system_pin) is None:
        raise SnapshotError('pin_required')
    if not args.workspace.is_absolute():
        raise SnapshotError('workspace_invalid')
    if any(name == 'kit' or name.startswith('kit.') for name in sys.modules):
        raise SnapshotError('module_namespace_already_loaded')
    root, sources, start = capture(args.candidate_root, args.manifest_pin, _trusted_verifier())
    sys.meta_path.insert(0, SnapshotFinder(sources))
    from kit.guard import guard
    from kit.base.bootstrap import extract_start
    from kit.base.registry_store import Layout
    from kit import session_cli
    try:
        bootstrap = extract_start(start['entry'], start['start'])
        bootstrap.update(outcome='bootstrap', manifest_sha256=args.manifest_pin,
                         start_file_sha256=hashlib.sha256(start['start']).hexdigest())
    except Exception as exc:
        raise SnapshotError('bootstrap_unverified') from exc
    layout = Layout(args.workspace, args.profile_root)

    def preflight():
        guard(root, layout, manifest_pin=args.manifest_pin, system_pin=args.system_pin)

    try:
        preflight()  # Не читать пользовательские команды, если вход уже неверен.
    except Exception as exc:
        raise SnapshotError('runtime_unverified') from exc
    sys.argv = ['verified-session', '--workspace', str(args.workspace),
                '--profile-root', args.profile_root, '--profile-id', args.profile_id]
    return session_cli.main(preflight=preflight, bootstrap=bootstrap)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate-root', type=Path, required=True)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--profile-root', required=True)
    parser.add_argument('--profile-id', required=True)
    parser.add_argument('--manifest-pin', required=True)
    parser.add_argument('--system-pin', required=True)
    args = parser.parse_args()
    try:
        return run(args)
    except SnapshotError as exc:
        print(json.dumps({'outcome': 'violation', 'reason': str(exc)}, sort_keys=True), file=sys.stderr)
        return 1
    except Exception:
        # Ошибка после начала работы не является утверждением, что записи не было.
        print(json.dumps({'outcome': 'error', 'reason': 'runtime_failure'}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
