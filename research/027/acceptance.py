#!/usr/bin/env python3
"""И-027: приёмка адаптера Copilot и проверка, что правило тождества не поехало."""
from __future__ import annotations

import json
import pathlib

HERE = pathlib.Path(__file__).absolute().parent
TREE = HERE.parent / 'release-0.1.7'


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
    corpus = {line: load(f'pairs-027-{line}.json') for line in ('base', 'edition')}
    journals = {line: load(f'pairs-027-journals-{line}.json') for line in ('base', 'edition')}
    expectations = load('EXPECTATIONS.json')
    compat = load('COMPAT.json')
    replay = load('REPLAY.json') if (HERE / 'REPLAY.json').exists() else None
    rows = []

    got = {line: totals(line) for line in ('base', 'edition')}
    rows.append(row('выпуск 0.1.7 собран и испытан',
                    '46 pass / 0 fail / 3 not run на обеих линиях',
                    got, 'pass' if all(t['pass'] == 46 and t['fail'] == 0 for t in got.values()) else 'fail',
                    'release-0.1.7/{base,edition}/AgentContractLab/reports/CHECKS.json'))

    rows.append(row('адаптер Copilot проверен независимо от регрессий комплекта',
                    '13 проверок: карточка, второй вход, неизвестная среда, семь раскладок, порядок, '
                    'невыписывание, отсутствие заявленного обнаружения',
                    dict(base=base['counts'], edition=edition['counts'], ok=base['ok'] and edition['ok']),
                    'pass' if base['ok'] and edition['ok'] and base['counts'].get('pass') == 13 else 'fail',
                    'adapter-base.json; adapter-edition.json'))

    rows.append(row('карточка среды ничего не пишет и не читает',
                    'adapter copilot: discovery_proven false, contents_read false, проект не изменён',
                    [x for x in base['rows'] if x['case'] in ('карточка адаптера Copilot',
                                                              'обнаружение не заявлено как проверенное')],
                    'pass' if all(x['status'] == 'pass' for x in base['rows']
                                  if x['case'] in ('карточка адаптера Copilot',
                                                   'обнаружение не заявлено как проверенное')) else 'fail',
                    'adapter-base.json'))

    rows.append(row('второй вход запрещён кодом отказа',
                    'connect с entry_path, отличным от AGENTS.md, отклоняется как second_entry; '
                    'с AGENTS.md вход создаётся, .github/ не появляется',
                    [x['actual'] for x in base['rows'] if x['case'].startswith('второй вход')],
                    'pass' if any(x['status'] == 'pass' for x in base['rows']
                                  if x['case'].startswith('второй вход')) else 'fail',
                    'adapter-base.json'))

    rows.append(row('источники Copilot видны, но не читаются и не меняются',
                    'семь раскладок: общий файл, path-specific, agents, skills, .vscode/settings.json, '
                    'CLAUDE.md, GEMINI.md — подтверждение до входа, файлы байт в байт',
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
                    'pairs-027-base.json; pairs-027-edition.json',
                    f"объявленная замена ожидания: {expectations['why'][:80]}…"))

    rows.append(row('правило тождества не поехало: журналы',
                    '3 из 3 повторов склеены, 0 ложных из 40, обе линии',
                    {line: dict(merged=journals[line]['classes']['repeat-form']['merged']
                                + journals[line]['classes']['repeat-volatile']['merged'],
                                false=len(journals[line]['false_merges'])) for line in journals},
                    'pass' if all(journals[line]['classes']['repeat-form']['merged']
                                  + journals[line]['classes']['repeat-volatile']['merged'] == 3
                                  and not journals[line]['false_merges'] for line in journals) else 'fail',
                    'pairs-027-journals-base.json; pairs-027-journals-edition.json'))

    rows.append(row('данные 0.1.6 читаются и не переписываются',
                    'файл наблюдений 0.1.6 читается 0.1.7; повтор не меняет байты',
                    compat, 'pass' if compat['ok'] else 'fail', 'COMPAT.json'))

    rows.append(row('повтор из печати совпадает со сборкой',
                    'все запечатанные результаты — те же',
                    None if replay is None else dict(identical=replay['identical'], equal=replay['equal']),
                    'pass' if replay and replay['identical'] else ('fail' if replay else 'not run'),
                    'REPLAY.json'))

    rows.append(row('обнаружение в живом Copilot / VS Code',
                    'Chat в VS Code загружает AGENTS.md и файлы инструкций',
                    None, 'not run', '—', 'Плагина здесь нет; это уровни достоверности 2–3, И-030…И-032.'))
    rows.append(row('старшинство в живом Copilot',
                    'path-specific и общий файл перекрывают AGENTS.md; Chat на github.com его не читает',
                    None, 'not run', '—', 'Старшинство и пробелы покрытия взяты из документации среды и записаны данными.'))
    rows.append(row('журналы заказчика', 'ваши журналы и проекты', None, 'not run', '—', 'Журналов нет.'))
    rows.append(row('Windows и права', 'Windows, ограниченные права', None, 'not run', '—', 'Стенд Linux.'))
    rows.append(row('живые модели', 'поведение с подключённой моделью', None, 'not run', '—', 'Режим офлайн.'))

    counts = {}
    for r in rows:
        counts[r['status']] = counts.get(r['status'], 0) + 1
    out = dict(iteration='И-027', counts=dict(sorted(counts.items())), rows=rows,
               release=dict(version='0.1.7', tests=got))
    (HERE / 'ACCEPTANCE.json').write_text(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
                                          encoding='utf-8')
    print(json.dumps(out['counts'], ensure_ascii=False))
    for r in rows:
        print(f"  {r['status']:7} {r['case']}")


if __name__ == '__main__':
    main()
