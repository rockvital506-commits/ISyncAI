#!/usr/bin/env python3
"""И-023: извлечение наблюдений из настоящих журналов по правилам, зафиксированным в DESIGN.md.

Правило = (имя случая, регулярное выражение строки, рамка фразы). Содержание наблюдения — дословная
часть строки; рамка только обрамляет её. Номер строки в журнале становится уликой.
"""
from __future__ import annotations

import json
import pathlib
import re

HERE = pathlib.Path(__file__).absolute().parent
JOURNALS = HERE / 'journals'

RULES = [
    # case, pattern, prefix, suffix, expected, level
    ('pytest-summary', re.compile(r'^(?:\d+ [a-z]+(?:, )?)+.* in \d+\.\d+s(?: \(.*\))?$'),
     'Итог прогона: ', '.', 'Тесты проходят.', 3),
    ('pytest-failed', re.compile(r'^FAILED (\S+)$'), 'Падает тест ', '.', 'Тесты проходят.', 3),
    ('pip-error', re.compile(r'^ERROR: (.+)$'), 'Ошибка pip: ', '', 'Установка проходит.', 3),
    ('build-error', re.compile(r'^\s*(\S+:\d+:\d+: (?:fatal )?error: .+)$'), 'Ошибка сборки: ',
     '', 'Сборка проходит.', 3),
    ('npm-deprecated', re.compile(r'^npm warn deprecated (\S+): (.+)$'), '', ' объявлен устаревшим.',
     'Зависимости актуальны.', 2),
    ('npm-error', re.compile(r'^npm error (\S.*)$'), 'Ошибка npm: ', '', 'Команда npm проходит.', 3),
    ('npm-vuln-total', re.compile(r'^(\d+ vulnerabilities? \(.*\))$'), 'Уязвимостей: ', '',
     'Уязвимостей нет.', 3),
]


def classify(line: str):
    for case, pattern, prefix, suffix, expected, level in RULES:
        m = pattern.match(line)
        if m:
            if case == 'npm-deprecated':
                facts = f'{m.group(1)}: {m.group(2)}'
            else:
                facts = m.group(1) if m.groups() else m.group(0).strip()
            return case, f'{prefix}{facts}{suffix}', facts, expected, level
    return None


def environment(host) -> dict:
    return dict(os=host['os_name'].lower(), editor='none', editor_version='n/a', extension='none',
                extension_version='n/a', mode='offline', model='none', profile='none',
                permissions='read-only')


def main():
    provenance = json.loads((JOURNALS / 'provenance.json').read_text(encoding='utf-8'))
    env = environment(provenance['host'])
    observations = []
    for journal in provenance['journals']:
        lines = (JOURNALS / journal['log']).read_text(encoding='utf-8').splitlines()
        for number, line in enumerate(lines, 1):
            got = classify(line)
            if not got:
                continue
            case, actual, facts, expected, level = got
            observations.append(dict(
                id=f"{journal['id']}#L{number}", journal=journal['id'], line=number, case=case,
                level=level, expected=expected, actual=actual, facts=facts,
                evidence=f"{journal['log']}, строка {number}",
                limits='Оценка по журналу, не запуск.',
                conditions=f"Читался вывод команды `{' '.join(journal['command'])}`; "
                           f"код возврата {journal['exit_code']}.",
                environment=dict(env)))
    by_case = {}
    for o in observations:
        by_case[o['case']] = by_case.get(o['case'], 0) + 1
    out = dict(iteration='И-023', journals=len(provenance['journals']), observations=len(observations),
               by_case=dict(sorted(by_case.items())),
               by_journal={j['id']: sum(1 for o in observations if o['journal'] == j['id'])
                           for j in provenance['journals']},
               rows=observations)
    (HERE / 'observations.json').write_text(
        json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps({k: out[k] for k in ('journals', 'observations', 'by_case', 'by_journal')},
                     ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
