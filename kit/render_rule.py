#!/usr/bin/env python3
"""Получить производный Markdown из действующей записи. Ничего не устанавливает и не пишет."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

# Позволяет запускать и как модуль, и как файл из любого каталога.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kit.base import registry_policy, schema_v2
from kit.base.profile_journal import canonical_bytes


class RenderError(ValueError):
    pass


def render(catalog, *, area, entry_id):
    """Строгое преобразование полного каталога в UTF-8 bytes, без побочных действий."""
    if type(catalog) is not dict or set(catalog) != {'L0', 'L1', 'L2'}:
        raise RenderError('нужны все три явно переданные области')
    if area not in ('L1', 'L2') or type(entry_id) is not str:
        raise RenderError('выберите L1 или L2 и ID записи')
    try:
        schema_v2.validate_catalog(catalog)
    except schema_v2.SchemaError as exc:
        raise RenderError(f'невалидный каталог: {exc.stage}:{exc.code}') from exc
    if registry_policy.find_conflicts(catalog):
        raise RenderError('структурный конфликт: сначала требуется решение')
    document = catalog[area]
    entries = {row['id']: row for row in document['entries']}
    row = entries.get(entry_id)
    if row is None:
        raise RenderError('запись не найдена в выбранной области')
    if row['kind'] == 'contract' or row['state'] != 'active':
        raise RenderError('нужна действующая дочерняя запись')
    parent = entries[row['parent']]
    if parent['state'] != 'active':
        raise RenderError('контракт записи не активен')
    if row['scope'] != '.':
        raise RenderError('узкий scope не поддержан: нельзя расширять действие')
    title, text = row['title'], row['text']
    if any(ord(c) < 32 or ord(c) == 127 for c in title):
        raise RenderError('заголовок содержит управляющий символ')
    if any((ord(c) < 32 and c not in '\n\t') or ord(c) == 127 for c in text):
        raise RenderError('текст содержит неподдерживаемый управляющий символ')
    if len(title.encode('utf-8')) > 512 or len(text.encode('utf-8')) > 16384:
        raise RenderError('запись превышает лимит материала')
    fingerprint = hashlib.sha256(canonical_bytes(row)).hexdigest()
    # ID уже проверен схемой как ASCII-токен; строка служебных метаданных не строится из тела.
    header = f'<!-- Kit: area={area} id={row["id"]} revision={document["revision"]} entry_sha256={fingerprint} -->\n'
    return (header + '# ' + title + '\n\n' + text + '\n').encode('utf-8')


def main():
    try:
        raw = sys.stdin.buffer.read(3_145_729)
        if len(raw) > 3_145_728:
            raise RenderError('слишком большой вход')
        payload = schema_v2.parse_json(raw)
        if type(payload) is not dict or set(payload) != {'catalog', 'area', 'entry_id'}:
            raise RenderError('ожидаются catalog, area, entry_id')
        result = render(payload['catalog'], area=payload['area'], entry_id=payload['entry_id'])
    except (RenderError, schema_v2.SchemaError, UnicodeError, RecursionError) as exc:
        print('render_failed: ' + str(exc), file=sys.stderr)
        return 1
    sys.stdout.buffer.write(result)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
