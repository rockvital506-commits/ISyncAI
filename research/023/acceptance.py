#!/usr/bin/env python3
"""И-023: приёмка. Считает только то, что лежит в артефактах; ничего не додумывает.

Статусы: pass — ожидание выполнено, fail — нет, not run — проверка невозможна здесь (и это сказано).
"""
from __future__ import annotations

import json
import pathlib

HERE = pathlib.Path(__file__).absolute().parent


def load(name):
    return json.loads((HERE / name).read_text(encoding='utf-8'))


def row(case, expected, actual, status, evidence, limits=''):
    return dict(case=case, expected=expected, actual=actual, status=status, evidence=evidence, limits=limits)


def main():
    provenance = load('journals/provenance.json')
    observed = load('observations.json')
    verify = load('VERIFY.json')
    base = load('pairs-023-base.json')
    edition = load('pairs-023-edition.json')
    diagnosis = load('DIAGNOSIS.json')
    rows = []

    journals = verify['checks'][0]
    rows.append(row('журналы с происхождением',
                    '8 журналов, у каждого команда, код возврата, время и отпечаток',
                    journals, 'pass' if journals['journals'] == 8 and not verify['problems'] else 'fail',
                    'VERIFY.json'))

    authored = verify['checks'][1]
    rows.append(row('журнал, написанный рукой, вне приёмки',
                    'контрольный журнал распознан и не попал в приёмку',
                    authored, 'pass' if authored['detected'] and authored['authored_journals'] == 0 else 'fail',
                    'VERIFY.json'))

    facts = verify['checks'][2]
    rows.append(row('наблюдения собраны из настоящих журналов',
                    'не меньше 40 наблюдений, каждый факт подтверждается указанной строкой',
                    facts, 'pass' if verify['ok'] and facts['verified'] == facts['observations'] >= 40 else 'fail',
                    'observations.json'))

    negatives = base['classes']['hard-negative']['pairs'] + base['classes']['random-negative']['pairs']
    rows.append(row('ложных склеек нет, база',
                    'на 40 парах «другое событие» (20 самых похожих, 20 выбранных отпечатком) — 0 склеек',
                    dict(pairs=negatives, false_merges=len(base['false_merges'])),
                    'pass' if not base['false_merges'] and negatives == 40 else 'fail',
                    'pairs-023-base.json'))

    rows.append(row('ложных склеек нет, Edition',
                    'то же на линии Edition',
                    dict(pairs=negatives, false_merges=len(edition['false_merges'])),
                    'pass' if not edition['false_merges'] and negatives == 40 else 'fail',
                    'pairs-023-edition.json'))

    repeats = base['classes']['repeat-form']
    rows.append(row('повтор настоящего события склеивается',
                    'две записи одного и того же падения из двух прогонов дают no_change',
                    dict(pairs=repeats['pairs'], merged=repeats['merged'], refused=repeats['refused']),
                    'pass' if repeats['merged'] == repeats['pairs'] and repeats['pairs'] >= 2 else 'fail',
                    'pairs-023-base.json; причина — DIAGNOSIS.json'))

    volatile = base['classes']['repeat-volatile']
    rows.append(row('повтор с изменчивым числом не склеивается',
                    'две итоговые строки с разной длительностью не склеиваются (записано как факт)',
                    dict(pairs=volatile['pairs'], merged=volatile['merged']),
                    'pass' if volatile['merged'] == 0 and volatile['pairs'] == 1 else 'fail',
                    'pairs-023-base.json'))

    rows.append(row('склейка не переписывает файл наблюдений',
                    'при no_change checks.json остаётся байт в байт',
                    dict(merges_kept=base['merges_kept'], merges=base['classes']['repeat-form']['merged']),
                    'not run',
                    'pairs-023-base.json',
                    'Склеек на настоящих журналах не было ни одной, поэтому свойство не проверялось. '
                    'На корпусе И-024 оно проверено (12 склеек, байты не менялись).'))

    rows.append(row('запись нового наблюдения сохраняет прежние',
                    'все прежние записи остаются в checks.json после новой записи',
                    dict(pairs=base['pairs'], preserved=base['preserved']),
                    'pass' if base['preserved'] and edition['preserved'] else 'fail',
                    'pairs-023-base.json; pairs-023-edition.json'))

    rows.append(row('обе линии ведут себя одинаково',
                    'классы пар совпадают на base и Edition',
                    {k: [base['classes'][k]['merged'], edition['classes'][k]['merged']]
                     for k in base['classes']},
                    'pass' if {k: base['classes'][k]['merged'] for k in base['classes']}
                    == {k: edition['classes'][k]['merged'] for k in edition['classes']} else 'fail',
                    'pairs-023-base.json; pairs-023-edition.json'))

    rows.append(row('причина отказа названа, а не угадана',
                    'диагностика показывает, какое поле мешает склейке, и какой вариант её включает',
                    [dict(pair=f"{p['left']} / {p['right']}",
                          variants=[(v['variant'], v['outcome']) for v in p['counterfactual']])
                     for p in diagnosis['pairs']],
                    'pass' if all(any(v['outcome'] == 'no_change' for v in p['counterfactual'])
                                  for p in diagnosis['pairs']) else 'fail',
                    'DIAGNOSIS.json',
                    'Контрфактические варианты — диагностика, не приёмка: продукт не менялся.'))

    rows.append(row('журналы заказчика', 'настоящие журналы вашей машины и ваших проектов',
                    None, 'not run', '—', 'Журналов нет; заменены журналами настоящих инструментов здесь.'))
    rows.append(row('Windows и права', 'запуск и запись под Windows, ограниченные права',
                    None, 'not run', '—', 'Стенд Linux, права обычные.'))
    rows.append(row('живые модели', 'поведение с подключённой моделью',
                    None, 'not run', '—', 'Модель не подключалась, режим офлайн.'))

    counts = {}
    for r in rows:
        counts[r['status']] = counts.get(r['status'], 0) + 1
    out = dict(iteration='И-023', counts=dict(sorted(counts.items())), rows=rows,
               sources=dict(journals=provenance['journals'], authored=provenance['authored']['id'],
                            observations=observed['observations'], pairs=base['pairs'],
                            release=base['version'], release_pin=base['release_pin']))
    (HERE / 'ACCEPTANCE.json').write_text(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True)
                                          + '\n', encoding='utf-8')
    print(json.dumps(out['counts'], ensure_ascii=False))
    for r in rows:
        print(f"  {r['status']:7} {r['case']}")


if __name__ == '__main__':
    main()
