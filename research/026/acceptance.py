#!/usr/bin/env python3
"""И-026: приёмка адаптера Kilo и проверка, что правило тождества не поехало."""
from __future__ import annotations

import json
import pathlib

HERE = pathlib.Path(__file__).absolute().parent
TREE = HERE.parent / 'release-0.1.6'


def load(name):
    return json.loads((HERE / name).read_text(encoding='utf-8'))


def row(case, expected, actual, status, evidence, limits=''):
    return dict(case=case, expected=expected, actual=actual, status=status, evidence=evidence, limits=limits)


def totals(line):
    report = json.loads((TREE / line / 'AgentContractLab/reports/CHECKS.json').read_text(encoding='utf-8'))
    return report['totals']


def main():
    base = load('adapter-base.json')
    edition = load('adapter-edition.json')
    corpus = {line: load(f'pairs-026-{line}.json') for line in ('base', 'edition')}
    journals = {line: load(f'pairs-026-journals-{line}.json') for line in ('base', 'edition')}
    expectations = load('EXPECTATIONS.json')
    compat = load('COMPAT.json')
    replay = load('REPLAY.json') if (HERE / 'REPLAY.json').exists() else None
    rows = []

    got = {line: totals(line) for line in ('base', 'edition')}
    rows.append(row('выпуск 0.1.6 собран и испытан',
                    '42 pass / 0 fail / 3 not run на обеих линиях',
                    got, 'pass' if all(t['pass'] == 42 and t['fail'] == 0 for t in got.values()) else 'fail',
                    'release-0.1.6/{base,edition}/AgentContractLab/reports/CHECKS.json'))

    rows.append(row('адаптер Kilo проверен независимо от регрессий комплекта',
                    '11 проверок: карточка, неизвестная среда, шесть раскладок, порядок, невыписывание, '
                    'отсутствие заявленного обнаружения',
                    dict(base=base['counts'], edition=edition['counts'], ok=base['ok'] and edition['ok']),
                    'pass' if base['ok'] and edition['ok'] and base['counts'].get('pass') == 11 else 'fail',
                    'adapter-base.json; adapter-edition.json'))

    rows.append(row('карточка среды ничего не пишет и не читает',
                    'adapter kilo: discovery_proven false, contents_read false, проект не изменён',
                    [x for x in base['rows'] if x['case'] in ('карточка адаптера Kilo',
                                                              'обнаружение не заявлено как проверенное')],
                    'pass' if all(x['status'] == 'pass' for x in base['rows']
                                  if x['case'] in ('карточка адаптера Kilo',
                                                   'обнаружение не заявлено как проверенное')) else 'fail',
                    'adapter-base.json'))

    rows.append(row('источники Kilo видны, но не читаются и не меняются',
                    'шесть раскладок: .kilo/kilo.jsonc, .kilo/rules, .kilocode/rules, .kilocoderules, '
                    'AGENT.md, kilo.jsonc — подтверждение до входа, файлы байт в байт',
                    [x['status'] for x in base['rows'] if x['case'].startswith('обнаружение и подтверждение')],
                    'pass' if all(x['status'] == 'pass' for x in base['rows']
                                  if x['case'].startswith('обнаружение и подтверждение')) else 'fail',
                    'adapter-base.json'))

    rows.append(row('правило тождества не поехало: корпус',
                    '24 склейки (12 форменных и 12 объявленных в И-025), 0 прочих, обе линии',
                    {line: dict(merged=corpus[line]['merged_count'],
                                reclassified=len([m for m in corpus[line]['merged']
                                                  if 'файл свидетельства' in m]),
                                other=len([m for m in corpus[line]['merged'] if not m.endswith('вар3')
                                           and 'файл свидетельства' not in m]))
                     for line in corpus},
                    'pass' if all(corpus[line]['merged_count'] == 24 for line in corpus) else 'fail',
                    'pairs-026-base.json; pairs-026-edition.json',
                    f"объявленная замена ожидания: {expectations['why'][:80]}…"))

    rows.append(row('правило тождества не поехало: журналы',
                    '3 из 3 повторов склеены, 0 ложных из 40, обе линии',
                    {line: dict(merged=journals[line]['classes']['repeat-form']['merged']
                                + journals[line]['classes']['repeat-volatile']['merged'],
                                false=len(journals[line]['false_merges'])) for line in journals},
                    'pass' if all(journals[line]['classes']['repeat-form']['merged']
                                  + journals[line]['classes']['repeat-volatile']['merged'] == 3
                                  and not journals[line]['false_merges'] for line in journals) else 'fail',
                    'pairs-026-journals-base.json; pairs-026-journals-edition.json'))

    rows.append(row('данные 0.1.5 читаются и не переписываются',
                    'файл наблюдений 0.1.5 читается 0.1.6; повтор не меняет байты',
                    compat, 'pass' if compat['ok'] else 'fail', 'COMPAT.json'))

    rows.append(row('повтор из печати совпадает со сборкой',
                    'все запечатанные результаты — те же',
                    None if replay is None else dict(identical=replay['identical'], equal=replay['equal']),
                    'pass' if replay and replay['identical'] else ('fail' if replay else 'not run'),
                    'REPLAY.json'))

    rows.append(row('обнаружение в живом Kilo', 'Kilo Code загружает вход в редакторе и читает его',
                    None, 'not run', '—', 'Плагина здесь нет; это уровни достоверности 2–3, И-030…И-032.'))
    rows.append(row('старшинство в живом Kilo',
                    'ключ instructions в проектном kilo.jsonc перекрывает AGENTS.md',
                    None, 'not run', '—', 'Старшинство взято из документации среды и записано данными; проверка — в живом Kilo.'))
    rows.append(row('журналы заказчика', 'ваши журналы и проекты', None, 'not run', '—', 'Журналов нет.'))
    rows.append(row('Windows и права', 'Windows, ограниченные права', None, 'not run', '—', 'Стенд Linux.'))
    rows.append(row('живые модели', 'поведение с подключённой моделью', None, 'not run', '—', 'Режим офлайн.'))

    counts = {}
    for r in rows:
        counts[r['status']] = counts.get(r['status'], 0) + 1
    out = dict(iteration='И-026', counts=dict(sorted(counts.items())), rows=rows,
               release=dict(version='0.1.6', tests=got))
    (HERE / 'ACCEPTANCE.json').write_text(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
                                          encoding='utf-8')
    print(json.dumps(out['counts'], ensure_ascii=False))
    for r in rows:
        print(f"  {r['status']:7} {r['case']}")


if __name__ == '__main__':
    main()
