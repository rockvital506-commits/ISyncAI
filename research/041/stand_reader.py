#!/usr/bin/env python3
"""И-036: имитатор читателя для уровня достоверности 3.

Отдельный процесс: находит вход по документированному порядку, читает его и сообщает отпечаток, размер,
число строк и признак того, что в файле есть строка-указатель на `START.md`. Комплект ничего не
импортирует отсюда — это вторая реализация чтения, а не его собственная.

Это **не** проверка того, что содержимое прочитала модель: Kilo и Copilot не запускаются.

Запуск: python3 stand_reader.py --tree <проект> --environment kilo --marker "<строка>"
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib

ORDER = {
    'kilo': ['.kilo/kilo.jsonc', 'AGENTS.md'],
    'copilot': ['.github/instructions', '.github/copilot-instructions.md', 'AGENTS.md'],
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--tree', required=True)
    ap.add_argument('--environment', required=True, choices=sorted(ORDER))
    ap.add_argument('--marker', default='')
    args = ap.parse_args()
    root = pathlib.Path(args.tree)
    found = [path for path in ORDER[args.environment] if (root / path).exists()]
    chosen = found[0] if found else None
    read = None
    if chosen is not None and (root / chosen).is_file():
        raw = (root / chosen).read_bytes()
        text = raw.decode('utf-8', errors='replace')
        read = {'path': chosen, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                'lines': text.count('\n') + (0 if text.endswith('\n') else 1),
                'marker_found': bool(args.marker) and args.marker in text}
    print(json.dumps({'environment': args.environment, 'chosen': chosen, 'read': read},
                     ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
