#!/usr/bin/env python3
"""Превью правила из заданного Layout v2: только чтение, без установки."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kit.base.registry_store import Layout, StoreError
from kit.base import registry_store
from kit.render_rule import RenderError, render


def preview(layout, *, area, entry_id):
    """Возвращает Markdown и хеши исходных файлов; не удостоверяет пользователя."""
    # Один физически проверенный набор входов с распакованными журналами.
    # Эта привязка к внутреннему порту зафиксирована тестами и не обеспечивает блокировок.
    loaded = registry_store._load(layout)
    content = render(loaded.documents, area=area, entry_id=entry_id)
    return {'format': 1, 'outcome': 'preview', 'area': area, 'entry_id': entry_id,
            'inputs_sha256': dict(loaded.inputs_sha256), 'content_sha256': hashlib.sha256(content).hexdigest(),
            'content': content.decode('utf-8')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True, help='абсолютный путь к существующему дереву')
    parser.add_argument('--profile-root', required=True, help='относительный корень выбранного профиля')
    parser.add_argument('--area', choices=('L1', 'L2'), required=True)
    parser.add_argument('--entry-id', required=True)
    args = parser.parse_args()
    try:
        data = preview(Layout(args.workspace, args.profile_root), area=args.area, entry_id=args.entry_id)
    except (StoreError, RenderError) as exc:
        diagnostic = exc.diagnostic() if isinstance(exc, StoreError) else {'code': 'render_failed', 'reason': str(exc)}
        print(json.dumps({'outcome': 'error', 'diagnostic': diagnostic}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(data, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
