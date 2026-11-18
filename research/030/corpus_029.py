#!/usr/bin/env python3
"""И-029: замороженный корпус пар «наблюдатель против условий».

Корпус не зависит от версии продукта: он состоит из наблюдений и метки «должны ли они склеиться».
Восемь базовых наблюдений, на каждое — десять пар:

  склейка (метка True):
    obs-extension        — другое расширение;
    obs-editor           — другой редактор, версии редактора и расширения;
    obs-profile          — другой профиль;
    obs-form             — другое расширение и другая форма текста (регистр, пунктуация, словоформа);
  не склейка (метка False):
    con-os               — другая операционная система;
    con-mode             — другой режим;
    con-model            — другая модель;
    con-permissions      — другие права;
    obs-plus-fact        — другое расширение и другой факт (изменено число);
    obs-plus-condition   — другое расширение и другие условия.

Итого 8 × 10 = 80 пар: 32 должны склеиться, 48 — нет.

Запуск: python3 corpus_029.py --freeze   (записать pairs-029-corpus.json и его отпечаток)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib

HERE = pathlib.Path(__file__).absolute().parent
OUT = HERE / 'pairs-029-corpus.json'

ENV = dict(os='linux', editor='vscode', editor_version='1.105', extension='kilo.kilo-code',
           extension_version='5.0', mode='agent', model='synthetic-a', profile='default',
           permissions='read-write')

BASE = [
    ('Тесты сборки', 3, 'Тесты проходят.', 'Падает TypeError в test_build.', 'tests.log, строка 17',
     'Оценка по журналу, не запуск.', 'Читался журнал тестов, команда не запускалась.'),
    ('Запуск утилиты', 3, 'Код возврата 0.', 'Код возврата 2, отказ path.', 'run.log, строка 1',
     'Один запуск в изолированном каталоге.', 'Утилита запускалась с относительным путём.'),
    ('Проверка схемы', 1, 'Схема 1 принимается.', 'Отказ schema: неизвестное поле version.', 'schema.json, строка 3',
     'Только разбор файла, миграция не выполнялась.', 'Файл схемы читался как данные.'),
    ('Сборка образа', 2, 'Образ собран.', 'Сборка прервана: timeout после 600 секунд.', 'build.log, строка 812',
     'Журнал сборки, без повторного запуска.', 'Читался журнал сборки образа.'),
    ('Проверка зависимостей', 2, 'Все зависимости разрешаются.', 'ImportError: нет модуля yaml.', 'pip.log, строка 4',
     'Только текст ошибки, сеть не использовалась.', 'Прочитан вывод установки пакетов.'),
    ('Линтер', 1, 'Замечаний нет.', 'Найдено 3 предупреждения в kit/tools.', 'lint.log, строка 9',
     'Один прогон линтера, правила не менялись.', 'Линтер запускался по каталогу kit.'),
    ('Права файла', 2, 'Файл доступен на чтение.', 'Отказ EACCES при записи.', 'trace.log, строка 44',
     'Права менялись вручную до прогона.', 'Проверялась запись в защищённый каталог.'),
    ('Обновление', 3, 'Обновление проходит.', 'Отказ pending: незавершённая операция.', 'update.log, строка 5',
     'Оценка по журналу, обновление не повторялось.', 'Читался журнал обновления.'),
]


def observation(index: int, **changes) -> dict:
    case, level, expected, actual, evidence, limits, conditions = BASE[index]
    env = dict(ENV)
    data = changes.pop('environment', {})
    env.update(data)
    o = dict(case=case, level=level, conditions=conditions, expected=expected, actual=actual,
             status='pass', evidence=evidence, limits=limits, environment=env)
    o.update(changes)
    return o


def form_only(text: str) -> str:
    """Та же запись другой формой: регистр, пунктуация, словоформа."""
    return text.upper().replace('.', ' ').replace(',', ' ').replace('  ', ' ').strip()


def swap_number(text: str, delta: int = 424242) -> str:
    digits = ''.join(ch if ch.isdigit() else ' ' for ch in text).split()
    if not digits:
        return text + ' ' + str(delta)
    old = digits[0]
    return text.replace(old, str(int(old) + delta), 1)


def pairs() -> list[dict]:
    rows = []
    for index in range(len(BASE)):
        base = observation(index)
        rows += [
            dict(index=index, kind='obs-extension', label=True,
                 left=base, right=observation(index, environment={'extension': 'github.copilot'})),
            dict(index=index, kind='obs-editor', label=True,
                 left=base, right=observation(index, environment={
                     'editor': 'cursor', 'editor_version': '2.7', 'extension_version': '1.2'})),
            dict(index=index, kind='obs-profile', label=True,
                 left=base, right=observation(index, environment={'profile': 'ci'})),
            dict(index=index, kind='obs-form', label=True,
                 left=base, right=observation(index, environment={'extension': 'github.copilot'},
                                              actual=form_only(base['actual']),
                                              conditions=form_only(base['conditions']))),
            dict(index=index, kind='con-os', label=False,
                 left=base, right=observation(index, environment={'os': 'windows'})),
            dict(index=index, kind='con-mode', label=False,
                 left=base, right=observation(index, environment={'mode': 'chat'})),
            dict(index=index, kind='con-model', label=False,
                 left=base, right=observation(index, environment={'model': 'synthetic-b'})),
            dict(index=index, kind='con-permissions', label=False,
                 left=base, right=observation(index, environment={'permissions': 'read-only'})),
            dict(index=index, kind='obs-plus-fact', label=False,
                 left=base, right=observation(index, environment={'extension': 'github.copilot'},
                                              actual=swap_number(base['actual']))),
            dict(index=index, kind='obs-plus-condition', label=False,
                 left=base, right=observation(index, environment={'extension': 'github.copilot',
                                                                  'os': 'windows'})),
        ]
    return rows


def main() -> int:
    rows = pairs()
    payload = dict(format='observation-pairs', iteration='И-030', at='2026-11-18',
                   environment_keys=list(ENV), pairs=rows)
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + '\n'
    if OUT.exists():
        OUT.unlink()
    OUT.write_text(text, encoding='utf-8')
    merges = sum(1 for r in rows if r['label'])
    print(json.dumps(dict(pairs=len(rows), merges=merges, separates=len(rows) - merges,
                          sha256=hashlib.sha256(text.encode('utf-8')).hexdigest()), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
