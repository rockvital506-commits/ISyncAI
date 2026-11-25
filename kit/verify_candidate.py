#!/usr/bin/env python3
"""Проверка локального исходного среза кандидата; чтение без установки и записи."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import sys
from pathlib import Path

FORMAT = 2
PRODUCT = 'DomainAgentKit'
CANDIDATE_VERSION = '0.2.0-mvp.46'
MANIFEST = 'kit/KIT-VERSION.json'
EXTRA = {'kit/atomic_init_inspect.py', 'kit/ATOMIC-INIT-INSPECT.md', 'kit/atomic_init.py', 'kit/ATOMIC-INIT.md', 'kit/SYSTEM-L0.json', 'kit/init_workspace_cli.py', 'kit/INIT-WORKSPACE-CLI.md', 'kit/init_workspace.py', 'kit/INIT-WORKSPACE.md', 'kit/verify_candidate.py', 'kit/LAYERS.md', 'kit/IDENTITY.md', 'kit/snapshot_session.py', 'kit/SNAPSHOT-SESSION.md', 'kit/snapshot_export.py', 'kit/SNAPSHOT-EXPORT.md', 'kit/render_rule.py', 'kit/RENDER-RULE.md', 'kit/preview_rule.py', 'kit/PREVIEW-RULE.md', 'kit/session_cli.py', 'kit/SESSION-CLI.md', 'kit/ENVIRONMENTS.json', 'kit/ENVIRONMENTS.md', 'kit/kilo_deploy.py', 'kit/KILO-DEPLOY.md', 'kit/kilo_inspect.py', 'kit/KILO-INSPECT.md', 'kit/guard.py', 'kit/GUARD.md', 'kit/guard_tree.py', 'kit/GUARD-TREE.md', 'kit/compare_old.py', 'kit/COMPARE-OLD.md', 'kit/legacy_capsule.py', 'kit/LEGACY-CAPSULE.md', 'kit/legacy_projection.py', 'kit/LEGACY-PROJECTION.md'}
HEX = re.compile(r'^[0-9a-f]{64}$')
NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]*$')


class VerificationError(ValueError):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise VerificationError('повторное поле JSON: ' + key)
        result[key] = value
    return result


def regular_file(path):
    try:
        if not stat.S_ISREG(path.lstat().st_mode):
            raise VerificationError(f'не обычный файл: {path.name}')
        return path.read_bytes()
    except OSError as exc:
        raise VerificationError(f'файл недоступен: {path.name}') from exc


def verify(root, *, pin=None):
    """Проверка состава и байтов. Не следует ссылкам; не доказывает доверие к манифесту."""
    root = Path(root)
    kit, base = root / 'kit', root / 'kit' / 'base'
    for path in (kit, base):
        try:
            if not stat.S_ISDIR(path.lstat().st_mode):
                raise VerificationError(f'не обычный каталог: {path.name}')
        except OSError as exc:
            raise VerificationError(f'каталог недоступен: {path.name}') from exc
    raw = regular_file(root / MANIFEST)
    manifest_hash = digest(raw)
    if pin is not None and (not isinstance(pin, str) or not HEX.fullmatch(pin) or pin != manifest_hash):
        raise VerificationError('контрольный хеш манифеста не совпадает')
    try:
        doc = json.loads(raw.decode('utf-8'), object_pairs_hook=no_duplicates,
                         parse_constant=lambda _: (_ for _ in ()).throw(VerificationError('недопустимое число')))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise VerificationError('манифест не является UTF-8 JSON') from exc
    if type(doc) is not dict or set(doc) != {'format', 'product', 'version', 'status', 'scope', 'files'}:
        raise VerificationError('неверные поля манифеста')
    if doc['product'] != PRODUCT:
        raise VerificationError('неверная идентичность продукта')
    if type(doc['format']) is not int or doc['format'] != FORMAT or doc['version'] != CANDIDATE_VERSION:
        raise VerificationError('неподдерживаемая версия манифеста или кандидата')
    if doc['status'] != 'candidate' or doc['scope'] != 'source-l0-only':
        raise VerificationError('неверный статус или область')
    files = doc['files']
    if type(files) is not dict or not files:
        raise VerificationError('пустой или некорректный состав')
    for path, value in files.items():
        if type(path) is not str or type(value) is not str or not HEX.fullmatch(value):
            raise VerificationError('неверный путь или хеш')
        if path not in EXTRA and not (path.startswith('kit/base/') and NAME.fullmatch(path[len('kit/base/'):])):
            raise VerificationError('путь вне кандидата: ' + path)
    try:
        discovered = set()
        for path in base.iterdir():
            if path.name == '__pycache__' and path.is_dir() and not path.is_symlink():
                continue
            if not NAME.fullmatch(path.name) or not stat.S_ISREG(path.lstat().st_mode):
                raise VerificationError('неожиданный объект в kit/base: ' + path.name)
            discovered.add('kit/base/' + path.name)
    except OSError as exc:
        raise VerificationError('не удалось прочитать состав kit/base') from exc
    expected = discovered | EXTRA
    if set(files) != expected:
        raise VerificationError(f'состав отличается: отсутствуют={sorted(set(files)-expected)}, лишние={sorted(expected-set(files))}')
    for path in sorted(files):
        if digest(regular_file(root / path)) != files[path]:
            raise VerificationError('хеш не совпадает: ' + path)
    return {'status': 'pass', 'product': PRODUCT, 'candidate': doc['version'], 'files': len(files),
            'manifest_sha256': manifest_hash, 'pin_checked': pin is not None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument('--pin', help='заранее доверенный SHA-256 манифеста')
    args = parser.parse_args()
    try:
        report = verify(args.root, pin=args.pin)
    except VerificationError as exc:
        print(json.dumps({'status': 'fail', 'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
