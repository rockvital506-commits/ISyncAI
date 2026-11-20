#!/usr/bin/env python3
"""И-030: замороженный корпус «точка и идентификатор».

Двенадцать пар: шесть должны склеиться (различие только в завершающей точке) и шесть — нет
(изменён идентификатор или версия, различие внутри имени). Метки записаны из решения Б до прогона.

Запуск: python3 corpus_030.py --freeze
"""
from __future__ import annotations

import hashlib
import json
import pathlib

HERE = pathlib.Path(__file__).absolute().parent
OUT = HERE / 'pairs-030-corpus.json'

ENV = dict(os='linux', editor='vscode', editor_version='1.105', extension='kilo.kilo-code',
           extension_version='5.0', mode='agent', model='synthetic-a', profile='default',
           permissions='read-write')


def observation(actual: str, case: str = 'сборка модуля') -> dict:
    return dict(case=case, level=1, conditions='Синтетический проект, одна и та же проверка',
                expected='Проверка проходит.', actual=actual, status='pass',
                evidence='tests.log, строка 12', limits='Только синтетические данные.',
                environment=dict(ENV))


PAIRS = [
    ('dot-identifier', True, 'Падает TypeError в test_build.', 'Падает TypeError в test_build'),
    ('dot-dotted-name', True, 'Разбор файла a.b.', 'Разбор файла a.b'),
    ('dot-exception', True, 'Пойман TypeError.', 'Пойман TypeError'),
    ('dot-version', True, 'Принята версия v1.0.', 'Принята версия v1.0'),
    ('dot-file', True, 'Модуль test_build.py не найден.', 'Модуль test_build.py не найден'),
    ('dot-two-sentences', True, 'Сборка прошла. Отчёт в build.log.', 'Сборка прошла. Отчёт в build.log'),
    ('name-with-extension', False, 'Модуль test_build.py не найден.', 'Модуль test_build не найден'),
    ('name-version', False, 'Принята версия v1.1.', 'Принята версия v1.0'),
    ('name-changed', False, 'Падает TypeError в test_build.', 'Падает AssertionError в test_io.'),
    ('name-dotted-longer', False, 'Разбор файла a.b.c.', 'Разбор файла a.b'),
    ('number-changed', False, 'Код возврата 2.', 'Код возврата 3'),
    ('dot-vs-underscore', False, 'Разбор файла a.b.', 'Разбор файла a_b'),
]


def main() -> int:
    rows = [dict(kind=kind, label=label, left=observation(left), right=observation(right))
            for kind, label, left, right in PAIRS]
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
