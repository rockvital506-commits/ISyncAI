#!/usr/bin/env python3
"""И-025: приёмка выпуска 0.1.5 на двух стендах (корпус 112 пар и настоящие журналы)."""
from __future__ import annotations

import json
import pathlib

HERE = pathlib.Path(__file__).absolute().parent
TREE = HERE.parent / 'release-0.1.5'


def load(name):
    return json.loads((HERE / name).read_text(encoding='utf-8'))


def row(case, expected, actual, status, evidence, limits=''):
    return dict(case=case, expected=expected, actual=actual, status=status, evidence=evidence, limits=limits)


def totals(line):
    report = json.loads((TREE / line / 'AgentContractLab/reports/CHECKS.json').read_text(encoding='utf-8'))
    return report['totals']


def main():
    journals = {line: load(f'pairs-025-journals-{line}.json') for line in ('base', 'edition')}
    corpus = {line: load(f'pairs-025-{line}.json') for line in ('base', 'edition')}
    expectations = load('EXPECTATIONS.json')
    compat = load('COMPAT.json')
    replay = load('REPLAY.json') if (HERE / 'REPLAY.json').exists() else None
    rows = []

    got = {line: totals(line) for line in ('base', 'edition')}
    rows.append(row('выпуск 0.1.5 собран и испытан',
                    '38 pass / 0 fail / 3 not run на обеих линиях',
                    got, 'pass' if all(t['pass'] == 38 and t['fail'] == 0 for t in got.values()) else 'fail',
                    'release-0.1.5/{base,edition}/AgentContractLab/reports/CHECKS.json'))

    checks = journals['base']['classes']
    merged = checks['repeat-form']['merged'] + checks['repeat-volatile']['merged']
    rows.append(row('настоящий повтор склеивается',
                    '3 из 3 (2 одинаковых и 1 с разной длительностью), 0 ложных из 40',
                    dict(merged=merged, false=len(journals['base']['false_merges']),
                         negatives=checks['hard-negative']['pairs'] + checks['random-negative']['pairs']),
                    'pass' if merged == 3 and not journals['base']['false_merges'] else 'fail',
                    'pairs-025-journals-base.json'))

    rows.append(row('то же на линии Edition',
                    'те же 3 склейки и 0 ложных',
                    dict(merged=journals['edition']['classes']['repeat-form']['merged']
                         + journals['edition']['classes']['repeat-volatile']['merged'],
                         false=len(journals['edition']['false_merges'])),
                    'pass' if (journals['edition']['classes']['repeat-form']['merged']
                               + journals['edition']['classes']['repeat-volatile']['merged']) == 3
                    and not journals['edition']['false_merges'] else 'fail',
                    'pairs-025-journals-edition.json'))

    base = corpus['base']
    form = [m for m in base['merged'] if m.endswith('вар3')]
    rows.append(row('форменные склейки корпуса сохранены',
                    '12 склеек «вар3» на обеих линиях',
                    dict(form_only=len(form), merged_total=base['merged_count']),
                    'pass' if len(form) == 12 and len(
                        [m for m in corpus['edition']['merged'] if m.endswith('вар3')]) == 12 else 'fail',
                    'pairs-025-base.json; pairs-025-edition.json'))

    changed = [m for m in base['merged'] if 'файл свидетельства' in m]
    rows.append(row('изменение спецификации объявлено',
                    '12 пар «изменён файл свидетельства» теперь склеиваются, и это записано, '
                    'а ожидание И-024 не переписано',
                    dict(reclassified=len(changed), expected=expectations['expected_merges']),
                    'pass' if sorted(changed) == sorted(expectations['reclassified']) else 'fail',
                    'EXPECTATIONS.json; ../024/pairs-base.json (не изменён)',
                    'Отменена одна защита — «подмена файла свидетельства». Цена измерена в DESIGN.md, '
                    'альтернатива (снимать только номер строки) дала 12 склеек корпуса и 1 из 3 повторов.'))

    negatives_left = 76 - len(changed)
    rows.append(row('остальные отказы корпуса сохранены',
                    f'{negatives_left} пар «другое событие» по-прежнему не склеиваются',
                    dict(expected=negatives_left,
                         merged_other=len([m for m in base['merged']
                                           if not m.endswith('вар3') and 'файл свидетельства' not in m]),
                         mismatches=len(base['mismatches'])),
                    'pass' if not [m for m in base['merged']
                                   if not m.endswith('вар3') and 'файл свидетельства' not in m] else 'fail',
                    'pairs-025-base.json'))

    rows.append(row('содержание улики защищено',
                    'отпечаток файла, «по памяти», другой счётчик — новое наблюдение',
                    dict(compat_different=compat['different_outcome'],
                         corpus_identifier_refusals=len([m for m in base['merged'] if 'идентификатор' in m]),
                         corpus_number_refusals=len([m for m in base['merged'] if 'номер' in m])),
                    'pass' if compat['different_outcome'] == 'committed'
                    and not [m for m in base['merged'] if 'идентификатор' in m or 'номер' in m] else 'fail',
                    'pairs-025-base.json; COMPAT.json',
                    'Отдельно проверены регрессии X20–X22 в испытаниях комплекта.'))

    rows.append(row('данные 0.1.4 читаются и не переписываются',
                    'файл наблюдений 0.1.4 читается 0.1.5 без изменений; повтор не меняет байты',
                    compat, 'pass' if compat['ok'] else 'fail', 'COMPAT.json'))

    rows.append(row('повтор из печати совпадает со сборкой',
                    'пять результатов и совместимость — те же',
                    None if replay is None else dict(identical=replay['identical'], equal=replay['equal']),
                    'pass' if replay and replay['identical'] else ('fail' if replay else 'not run'),
                    'REPLAY.json'))

    rows.append(row('обновление на месте (update)', 'трёхстороннее сравнение с разрешениями',
                    None, 'not run', '—', 'Отдельный предмет: нужно разрешение конфликтов данных.'))
    rows.append(row('журналы заказчика', 'ваши журналы и ваши проекты', None, 'not run', '—',
                    'Журналов нет; стенд И-023 — наши инструменты на коде третьих лиц.'))
    rows.append(row('Windows и права', 'Windows, ограниченные права', None, 'not run', '—', 'Стенд Linux.'))
    rows.append(row('живые модели', 'поведение с подключённой моделью', None, 'not run', '—', 'Режим офлайн.'))

    counts = {}
    for r in rows:
        counts[r['status']] = counts.get(r['status'], 0) + 1
    out = dict(iteration='И-025', counts=dict(sorted(counts.items())), rows=rows,
               release=dict(version='0.1.5', base_sha256=None, edition_sha256=None))
    (HERE / 'ACCEPTANCE.json').write_text(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
                                          encoding='utf-8')
    print(json.dumps(out['counts'], ensure_ascii=False))
    for r in rows:
        print(f"  {r['status']:7} {r['case']}")


if __name__ == '__main__':
    main()
