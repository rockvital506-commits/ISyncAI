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
MAX_MEMBERS = 1024
HEX = re.compile(r'[0-9a-f]{64}')
# Закрытый список только для данного сценария; другие команды не поддерживаются.
MODULES = {
    'kit.verify_candidate': 'kit/verify_candidate.py',
    'kit.guard': 'kit/guard.py',
    'kit.session_cli': 'kit/session_cli.py',
    'kit.base.applicability': 'kit/base/applicability.py',
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


def _strict_source(root, manifest_pin, verifier):
    """Закрытая раскладка только для этой сессии; не атомарна с проверкой/исполнением."""
    reparse = getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0)
    for directory in (root, root / 'kit', root / 'kit/base'):
        info = directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or getattr(info, 'st_file_attributes', 0) & reparse:
            raise SnapshotError('candidate_unverified')
    raw = _read_regular(root / 'kit/KIT-VERSION.json')
    if hashlib.sha256(raw).hexdigest() != manifest_pin:
        raise SnapshotError('candidate_unverified')
    doc = json.loads(raw.decode('utf-8'), object_pairs_hook=verifier.no_duplicates)
    if type(doc) is not dict or type(doc.get('files')) is not dict:
        raise SnapshotError('candidate_unverified')
    files = doc['files']
    if not files or len(files) > MAX_MEMBERS:
        raise SnapshotError('candidate_unverified')
    for path, expected in files.items():
        if type(path) is not str or type(expected) is not str or HEX.fullmatch(expected) is None:
            raise SnapshotError('candidate_unverified')
        if path not in verifier.EXTRA and not (path.startswith('kit/base/')
                                               and verifier.NAME.fullmatch(path[len('kit/base/'):])):
            raise SnapshotError('candidate_unverified')
    top = {path.removeprefix('kit/') for path in verifier.EXTRA}
    base = {path.removeprefix('kit/base/') for path in files if path.startswith('kit/base/')}
    if (set(files) != verifier.EXTRA | {'kit/base/' + name for name in base}
            or {p.name for p in root.iterdir()} != {'kit'}
            or {p.name for p in (root / 'kit').iterdir()} != top | {'base', 'KIT-VERSION.json'}
            or {p.name for p in (root / 'kit/base').iterdir()} != base):
        raise SnapshotError('candidate_unverified')
    # Каждый заявленный файл читается с лимитом, проверкой типа и без конечной ссылки.
    for path, expected in files.items():
        if hashlib.sha256(_read_regular(root / path)).hexdigest() != expected:
            raise SnapshotError('candidate_unverified')
    verifier.verify(root, pin=manifest_pin)  # Строгая проверка полей манифеста и версии.
    return doc


def capture(candidate_root, manifest_pin, verifier):
    """Проверить срез, затем закрепить исполняемые модули по тому же pin в памяти."""
    if type(manifest_pin) is not str or HEX.fullmatch(manifest_pin) is None:
        raise SnapshotError('pin_required')
    try:
        root = Path(candidate_root)
        if not root.is_absolute():
            raise SnapshotError('candidate_root_invalid')
        root = root.resolve(strict=True)
        doc = _strict_source(root, manifest_pin, verifier)
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


def _roots(candidate, workspace):
    """Пути и идентичности корней; сравнение не атомарно с использованием."""
    try:
        paths = (Path(candidate).resolve(strict=True), Path(workspace).resolve(strict=True),
                 Path(__file__).resolve(strict=True).parent)
        identities = []
        for path in paths:
            info = path.stat()
            if (not stat.S_ISDIR(info.st_mode) or type(info.st_dev) is not int
                    or info.st_dev < 0 or type(info.st_ino) is not int or info.st_ino <= 0):
                raise SnapshotError('roots_invalid')
            identities.append((info.st_dev, info.st_ino))
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        if isinstance(exc, SnapshotError):
            raise
        raise SnapshotError('roots_invalid') from exc
    for i, a in enumerate(paths):
        for j in range(i + 1, len(paths)):
            b = paths[j]
            if a == b or a in b.parents or b in a.parents or identities[i] == identities[j]:
                raise SnapshotError('roots_overlap')
    return paths, tuple(identities)


def run(args):
    if not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode):
        raise SnapshotError('isolated_python_required')
    if type(args.system_pin) is not str or HEX.fullmatch(args.system_pin) is None:
        raise SnapshotError('pin_required')
    if not args.workspace.is_absolute():
        raise SnapshotError('workspace_invalid')
    if not args.candidate_root.is_absolute():
        raise SnapshotError('candidate_root_invalid')
    if any(name == 'kit' or name.startswith('kit.') for name in sys.modules):
        raise SnapshotError('module_namespace_already_loaded')
    roots, identities = _roots(args.candidate_root, args.workspace)
    verifier = _trusted_verifier()
    root, sources, start = capture(roots[0], args.manifest_pin, verifier)
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
    layout = Layout(roots[1], args.profile_root)

    def preflight():
        if _roots(args.candidate_root, args.workspace) != (roots, identities):
            raise SnapshotError('roots_changed')
        _strict_source(root, args.manifest_pin, verifier)
        guard(root, layout, manifest_pin=args.manifest_pin, system_pin=args.system_pin)

    try:
        preflight()  # Не читать пользовательские команды, если вход уже неверен.
    except Exception as exc:
        raise SnapshotError('runtime_unverified') from exc
    sys.argv = ['verified-session', '--workspace', str(roots[1]),
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
