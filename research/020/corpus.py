"""Восстановленный корпус пар наблюдений (И-024), взамен утраченного вместе с `dist/`.

Строение то же, что в И-020: 12 базовых случаев; на каждый — три пересказа «того же события»
и шесть пар «другое событие»; плюс четыре перекрёстные пары. Всего 12*3 + 12*6 + 4 = 112 пар:
36 повторов и 76 разных событий.

Пересказы:
  вар1 — добавлена фраза «Прогон повторён, результат тот же.»;
  вар2 — добавлено уточнение в скобках к свидетельству;
  вар3 — только форма записи: регистр, пунктуация, словоформа, порядок слов.

«Другое событие»: изменён идентификатор, изменён номер, изменён файл свидетельства, снято
ограничение, смягчено свидетельство, сужено условие. Перекрёстные: статус, среда, ожидаемый
результат, дело.

Все наблюдения синтетические. Корпус не зависит ни от одной версии продукта.
"""
from __future__ import annotations

import copy

ENV = dict(os='linux', editor='none', editor_version='n/a', extension='none', extension_version='n/a',
           mode='offline', model='none', profile='none', permissions='read-only')

# (case, level, expected, actual, evidence, limits, conditions)
BASE = [
    ('Тесты сборки', 3, 'Тесты проходят.', 'Падает TypeError в test_build.', 'tests.log, строка 17',
     'Оценка по журналу, не запуск.', 'Читался журнал тестов, команда не запускалась.'),
    ('Тесты сборки', 3, 'Тесты проходят.', 'Падает AssertionError в test_build.', 'tests.log, строка 22',
     'Оценка по журналу, не запуск.', 'Читался журнал тестов, команда не запускалась.'),
    ('Проверка зависимостей', 2, 'Все зависимости разрешаются.', 'ImportError: нет модуля yaml.', 'pip.log, строка 4',
     'Только текст ошибки, сеть не использовалась.', 'Прочитан вывод установки пакетов.'),
    ('Запуск утилиты', 3, 'Код возврата 0.', 'Код возврата 2, отказ path.', 'run.log, строка 1',
     'Один запуск в изолированном каталоге.', 'Утилита запускалась с относительным путём.'),
    ('Сборка образа', 2, 'Образ собран.', 'Сборка прервана: timeout после 600 секунд.', 'build.log, строка 812',
     'Журнал сборки, без повторного запуска.', 'Читался журнал сборки образа.'),
    ('Проверка схемы', 1, 'Схема 1 принимается.', 'Отказ schema: неизвестное поле version.', 'schema.json, строка 3',
     'Только разбор файла, миграция не выполнялась.', 'Файл схемы читался как данные.'),
    ('Тесты сборки', 3, 'Тесты проходят.', 'Падает UnicodeDecodeError в test_io.', 'tests.log, строка 31',
     'Оценка по журналу, не запуск.', 'Читался журнал тестов, команда не запускалась.'),
    ('Запуск утилиты', 3, 'Код возврата 0.', 'Код возврата 1, отказ field: evidence пуст.', 'run.log, строка 7',
     'Один запуск в изолированном каталоге.', 'Утилита запускалась через CLI.'),
    ('Проверка зависимостей', 2, 'Все зависимости разрешаются.', 'PermissionError при чтении /opt/lib.',
     'pip.log, строка 9', 'Только текст ошибки, права не менялись.', 'Прочитан вывод установки пакетов.'),
    ('Сверка версий', 2, 'Версии совпадают.', 'Версия адаптера 2 не равна версии 1.', 'versions.log, строка 5',
     'Сверка по файлу, установка не выполнялась.', 'Читался файл версий.'),
    ('Проверка ссылок', 2, 'Все ссылки разрешаются.', 'Битая ссылка: missing.md.', 'links.txt, строка 12',
     'Только разбор текста, файлы не открывались.', 'Читался список ссылок.'),
    ('Чтение справочника', 1, 'Справочник читается.', 'Кодировка не UTF-8 при чтении PROTOCOL.md.',
     'start.log, строка 2', 'Только чтение, правка не выполнялась.', 'Читался файл справочника.'),
]

# Замены для пар «другое событие». Значение — (поле, что заменить, на что заменить).
IDENT = [('actual', 'TypeError', 'ValueError'), ('actual', 'AssertionError', 'RuntimeError'),
         ('actual', 'ImportError', 'ModuleNotFoundError'), ('actual', 'path', 'scope'),
         ('actual', 'timeout', 'deadline'), ('actual', 'schema', 'format'),
         ('actual', 'UnicodeDecodeError', 'UnicodeEncodeError'), ('actual', 'field', 'column'),
         ('actual', '/opt/lib', '/opt/bin'), ('actual', 'адаптера', 'протокола'),
         ('actual', 'missing.md', 'missing.txt'), ('actual', 'PROTOCOL.md', 'START.md')]
FILE_POOL = ('tests.log', 'pip.log', 'run.log', 'build.log', 'schema.json', 'versions.log', 'links.txt', 'start.log')
# Словоформы для пересказа вар3: (что заменить, на что заменить); основа не меняется.
INFLECT = [('строка', 'строки'), ('строка', 'строки'), ('пакетов', 'пакеты'), ('запуск', 'запуске'),
           ('сборки', 'сборка'), ('файла', 'файле'), ('строка', 'строки'), ('запуск', 'запуске'),
           ('пакетов', 'пакеты'), ('файл', 'файла'), ('ссылка', 'ссылки'), ('справочник', 'справочнике')]


def observation(index: int, **changes) -> dict:
    case, level, expected, actual, evidence, limits, conditions = BASE[index]
    out = dict(case=case, level=level, expected=expected, actual=actual, evidence=evidence,
               limits=limits, conditions=conditions, environment=copy.deepcopy(ENV))
    out.update(changes)
    return out


def _first_number(text: str) -> str:
    digits = ''
    for ch in text:
        if ch.isdigit():
            digits += ch
        elif digits:
            break
    return digits


def _replace_number(text: str, new: str) -> str:
    old = _first_number(text)
    return text.replace(old, new, 1) if old else text + ' ' + new


def _form_only(text: str) -> str:
    """Только форма записи: нижний регистр, знаки препинания в пробелы; идентификаторы целы."""
    keep = '_/-.'
    out = ''.join(ch.lower() if ch.isalnum() or ch.isspace() or ch in keep else ' ' for ch in text)
    return ' '.join(out.split())


def variant(index: int, number: int) -> dict:
    base = observation(index)
    if number == 1:
        return dict(base, actual=base['actual'] + ' Прогон повторён, результат тот же.')
    if number == 2:
        return dict(base, evidence=base['evidence'] + ' (журнал перечитан, файл не менялся)')
    if number == 3:
        old, new = INFLECT[index]
        out = dict(base)
        for key in ('actual', 'evidence', 'limits', 'conditions'):
            out[key] = _form_only(base[key]).replace(new, old, 1)
        out['conditions'] = ' '.join(out['conditions'].split()[::-1])
        return out
    raise ValueError(number)


def _new_number(index: int) -> str:
    digits = _first_number(observation(index)['actual']) or '17'
    return str(int(digits) + 7)


def _new_file(index: int) -> str:
    current = observation(index)['evidence'].split(',')[0].strip()
    return next(name for name in FILE_POOL if name != current)


def negatives(index: int) -> dict:
    ident_field, ident_old, ident_new = IDENT[index]
    base = observation(index)
    return {
        'изменён идентификатор': dict(base, **{ident_field: base[ident_field].replace(ident_old, ident_new, 1)}),
        'изменён номер': dict(base, actual=_replace_number(base['actual'], _new_number(index))),
        'изменён файл свидетельства': dict(base, evidence=_new_file(index) + base['evidence'][base['evidence'].find(','):]),
        'снято ограничение': dict(base, limits=base['limits'] + ' Ограничение снято.'),
        'смягчено свидетельство': dict(base, evidence=base['evidence'] + ' (по памяти, файл не открывался)'),
        'сужено условие': dict(base, conditions=base['conditions'] + ' Только при повторном прогоне.'),
    }


def pairs() -> list[tuple[bool, str, dict, dict]]:
    rows = []
    for i in range(len(BASE)):
        for n in (1, 2, 3):
            rows.append((True, f'E{i + 1:02d}-вар{n}', observation(i), variant(i, n)))
        for name, other in negatives(i).items():
            rows.append((False, f'E{i + 1:02d}-{name}', observation(i), other))
    cross = [
        (False, 'перекрёстно: другой статус', dict(observation(0), status='pass'), dict(observation(0), status='fail')),
        (False, 'перекрёстно: другая среда', observation(1), dict(observation(1), environment=dict(ENV, os='windows'))),
        (False, 'перекрёстно: другой ожидаемый результат', observation(2), dict(observation(2), expected='Есть предупреждение.')),
        (False, 'перекрёстно: другое дело', observation(3), dict(observation(3), case='Запуск проверки')),
    ]
    rows.extend(cross)
    return rows


if __name__ == '__main__':
    rows = pairs()
    repeats = sum(1 for r in rows if r[0])
    print(f'пар: {len(rows)}, повторов: {repeats}, разных событий: {len(rows) - repeats}, случаев: {len(BASE)}')
