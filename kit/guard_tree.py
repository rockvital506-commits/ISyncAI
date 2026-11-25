#!/usr/bin/env python3
"""Проверить L0 кандидата в Git tree или commit, не выполняя код снимка."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kit.verify_candidate import (CANDIDATE_VERSION, EXTRA, FORMAT, HEX, MANIFEST, NAME,
                                  VerificationError, no_duplicates)

MAX_BLOB = 2_097_152
MAX_LIST = 1_048_576
OID = re.compile(r'(?:[0-9a-f]{40}|[0-9a-f]{64})')


class TreeViolation(ValueError):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def _environment():
    # Не наследуем GIT_DIR, GIT_INDEX_FILE, конфигурации пользователя и протоколы сети.
    env = {'PATH': os.defpath, 'LC_ALL': 'C', 'GIT_CONFIG_NOSYSTEM': '1',
           'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_TERMINAL_PROMPT': '0',
           'GIT_NO_REPLACE_OBJECTS': '1', 'GIT_NO_LAZY_FETCH': '1',
           'GIT_ALLOW_PROTOCOL': '', 'GIT_OPTIONAL_LOCKS': '0'}
    for key in ('SYSTEMROOT', 'WINDIR', 'COMSPEC', 'TMP', 'TEMP'):
        if key in os.environ:
            env[key] = os.environ[key]
    return env


class _Git:
    def __init__(self, root):
        exe = shutil.which('git')
        if not exe:
            raise TreeViolation('git_unavailable')
        try:
            self.root = Path(root).resolve(strict=True)
        except (OSError, RuntimeError, TypeError) as exc:
            raise TreeViolation('repository_invalid') from exc
        self.exe = exe
        self.env = _environment()
        top = self.run('rev-parse', '--show-toplevel').rstrip(b'\n')
        try:
            if not os.path.samefile(os.fsdecode(top), self.root):
                raise TreeViolation('repository_invalid')
        except (OSError, ValueError) as exc:
            raise TreeViolation('repository_invalid') from exc
        fmt = self.run('rev-parse', '--show-object-format').strip()
        if fmt not in (b'sha1', b'sha256'):
            raise TreeViolation('object_format_unsupported')
        self.object_format = fmt.decode('ascii')
        self.oid_length = 40 if fmt == b'sha1' else 64

    def run(self, *args):
        command = [self.exe, '--no-optional-locks', '-c', 'core.fsmonitor=false',
                   '-c', 'credential.helper=', '-C', str(self.root), *args]
        try:
            p = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, env=self.env, timeout=30, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise TreeViolation('git_unavailable') from exc
        if p.returncode != 0:
            raise TreeViolation('git_failed')
        return p.stdout

    def blob(self, oid):
        raw_size = self.run('cat-file', '-s', oid).strip()
        if not raw_size.isdigit() or len(raw_size) > 12 or int(raw_size) > MAX_BLOB:
            raise TreeViolation('blob_too_large')
        raw = self.run('cat-file', 'blob', oid)
        if len(raw) != int(raw_size):
            raise TreeViolation('blob_invalid')
        return raw


def _manifest(raw, pin):
    if hashlib.sha256(raw).hexdigest() != pin:
        raise TreeViolation('manifest_pin_mismatch')
    try:
        doc = json.loads(raw.decode('utf-8'), object_pairs_hook=no_duplicates,
                         parse_constant=lambda _: (_ for _ in ()).throw(VerificationError('number')))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise TreeViolation('manifest_invalid') from exc
    if (type(doc) is not dict or set(doc) != {'format', 'version', 'status', 'scope', 'files'}
            or type(doc['format']) is not int or doc['format'] != FORMAT
            or doc['version'] != CANDIDATE_VERSION or doc['status'] != 'candidate'
            or doc['scope'] != 'source-l0-only' or type(doc['files']) is not dict):
        raise TreeViolation('manifest_invalid')
    files = doc['files']
    if not EXTRA.issubset(files) or not any(p.startswith('kit/base/') for p in files):
        raise TreeViolation('manifest_invalid')
    for path, digest in files.items():
        if (type(path) is not str or type(digest) is not str or HEX.fullmatch(digest) is None
                or not (path in EXTRA or (path.startswith('kit/base/')
                                         and NAME.fullmatch(path[len('kit/base/'):])))):
            raise TreeViolation('manifest_invalid')
    return files


def _check_pin(manifest_pin):
    if type(manifest_pin) is not str or HEX.fullmatch(manifest_pin) is None:
        raise TreeViolation('pin_required')


def _check_tree(git, tree_oid, manifest_pin):
    if len(tree_oid) != git.oid_length or git.run('cat-file', '-t', tree_oid).strip() != b'tree':
        raise TreeViolation('tree_invalid')
    raw = git.run('ls-tree', '-r', '-z', '--full-tree', tree_oid, '--', 'kit/base', MANIFEST, *sorted(EXTRA))
    if len(raw) > MAX_LIST or (raw and not raw.endswith(b'\0')):
        raise TreeViolation('tree_listing_invalid')
    entries = {}
    for row in raw.split(b'\0'):
        if not row:
            continue
        try:
            meta, path_bytes = row.split(b'\t', 1)
            mode, kind, oid_bytes = meta.split(b' ')
            path = path_bytes.decode('ascii')
            oid = oid_bytes.decode('ascii')
        except (ValueError, UnicodeError) as exc:
            raise TreeViolation('tree_listing_invalid') from exc
        if (mode != b'100644' or kind != b'blob' or len(oid) != git.oid_length
                or OID.fullmatch(oid) is None or path in entries):
            raise TreeViolation('tree_entry_invalid')
        if path != MANIFEST and path not in EXTRA and not (path.startswith('kit/base/')
                                                           and NAME.fullmatch(path[len('kit/base/'):])):
            raise TreeViolation('tree_entry_invalid')
        entries[path] = oid
    if MANIFEST not in entries:
        raise TreeViolation('manifest_missing')
    files = _manifest(git.blob(entries[MANIFEST]), manifest_pin)
    if set(entries) != set(files) | {MANIFEST}:
        raise TreeViolation('candidate_members_mismatch')
    for path in sorted(files):
        if hashlib.sha256(git.blob(entries[path])).hexdigest() != files[path]:
            raise TreeViolation('candidate_digest_mismatch')
    return {'guard_tree_format': 1, 'outcome': 'pass', 'tree_oid': tree_oid,
            'git_object_format': git.object_format, 'manifest_sha256': manifest_pin,
            'candidate': CANDIDATE_VERSION, 'files': len(files), 'checked': 'candidate_l0_only'}


def guard_tree(repo, *, tree_oid, manifest_pin):
    """Только выбранный tree и части L0 в нём; не проверяет index, commit или рабочие файлы."""
    _check_pin(manifest_pin)
    if type(tree_oid) is not str or OID.fullmatch(tree_oid) is None:
        raise TreeViolation('tree_invalid')
    return _check_tree(_Git(repo), tree_oid, manifest_pin)


def guard_commit(repo, *, commit_oid, manifest_pin):
    """Сверяет L0 в root tree указанного commit, без проверки PR, подписи или родительства."""
    _check_pin(manifest_pin)
    if type(commit_oid) is not str or OID.fullmatch(commit_oid) is None:
        raise TreeViolation('commit_invalid')
    git = _Git(repo)
    if len(commit_oid) != git.oid_length or git.run('cat-file', '-t', commit_oid).strip() != b'commit':
        raise TreeViolation('commit_invalid')
    raw = git.run('rev-parse', '--verify', '--end-of-options', commit_oid + '^{tree}').strip()
    try:
        tree_oid = raw.decode('ascii')
    except UnicodeError as exc:
        raise TreeViolation('commit_invalid') from exc
    if len(tree_oid) != git.oid_length or OID.fullmatch(tree_oid) is None:
        raise TreeViolation('commit_invalid')
    result = _check_tree(git, tree_oid, manifest_pin)
    del result['guard_tree_format']
    return {'guard_commit_format': 1, 'commit_oid': commit_oid, **result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True, help='корень выбранного Git-репозитория')
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--tree', help='полный OID Git tree')
    source.add_argument('--commit', help='полный OID Git commit')
    parser.add_argument('--manifest-pin', help='заранее доверенный SHA-256 манифеста')
    args = parser.parse_args()
    format_key = 'guard_commit_format' if args.commit is not None else 'guard_tree_format'
    try:
        result = (guard_commit(args.repo, commit_oid=args.commit, manifest_pin=args.manifest_pin)
                  if args.commit is not None else guard_tree(args.repo, tree_oid=args.tree, manifest_pin=args.manifest_pin))
    except TreeViolation as exc:
        print(json.dumps({format_key: 1, 'outcome': 'violation', 'reason': exc.reason}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
