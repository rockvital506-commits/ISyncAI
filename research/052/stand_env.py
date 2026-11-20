#!/usr/bin/env python3
"""И-035: имитатор среды для уровня достоверности 2.

Среда здесь — отдельный процесс, который ищет вход по документированному порядку старшинства и, если
нашёл, читает файл. Это проверка того, что порядок в карточке исполним и что два независимых чтения
называют одно и то же. Это **не** проверка живого расширения: Kilo и Copilot не запускаются, модели не
вызываются. Порядок продублирован здесь намеренно — второй реализацией, а не импортом из комплекта.

Запуск: python3 stand_env.py --tree <проект> --environment kilo
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib

# Документированный порядок: что среда читает раньше. Взят из карточек адаптеров (0.1.6, 0.1.7).
ORDER = {
    'kilo': ['.kilo/kilo.jsonc', 'AGENTS.md'],
    'copilot': ['.github/instructions', '.github/copilot-instructions.md', 'AGENTS.md'],
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--tree', required=True)
    ap.add_argument('--environment', required=True, choices=sorted(ORDER))
    args = ap.parse_args()
    root = pathlib.Path(args.tree)
    order = ORDER[args.environment]
    found = [path for path in order if (root / path).exists()]
    chosen = found[0] if found else None
    read = None
    if chosen is not None and (root / chosen).is_file():
        read = {'path': chosen, 'sha256': hashlib.sha256((root / chosen).read_bytes()).hexdigest()}
    print(json.dumps({'environment': args.environment, 'order': order, 'found': found,
                      'chosen': chosen, 'read': read}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
