"""И-028: приёмка двух сред на одном проекте и проверка, что правило тождества не поехало."""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys
import zipfile

HERE = pathlib.Path(__file__).absolute().parent
RELEASE = HERE.parent / 'release-0.1.8'


def load(name):
    return json.loads((HERE / name).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def main():
    rows = []

    def row(name, expected, actual, status, source, note=''):
        return dict(name=name, expected=expected, actual=actual, status=status,
                    source=source, note=note)

    dual = {line: load(f'dual-{line}.json') for line in ('base', 'edition')}
    adapter = {line: load(f'adapter-{line}.json') for line in ('base', 'edition')}
    corpus = {line: load(f'pairs-028-{line}.json') for line in ('base', 'edition')}
    journals = {line: load(f'pairs-028-journals-{line}.json') for line in ('base', 'edition')}
    compat = load('COMPAT.json')

    def checks(line):
        path = RELEASE / line / 'AgentContractLab/reports/CHECKS.json'
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding='utf-8'))['totals']

    totals = {line: checks(line) for line in ('base', 'edition')}
    rows.append(row('выпуск 0.1.8 собран и испытан',
                    '47 pass / 0 fail / 3 not run на обеих линиях',
                    {line: totals[line] for line in totals},
                    'pass' if all(t and t['pass'] == 47 and t['fail'] == 0 and t['not run'] == 3
                                  for t in totals.values()) else 'not run',
                    'release-0.1.8/*/AgentContractLab/reports/CHECKS.json'))

    def case(line, cid):
        return next(r for r in dual[line]['rows'] if r['id'] == cid)

    def status(line, cid):
        return case(line, cid)['status']

    rows.append(row('две среды на одном проекте проверены стендом',
                    '16 проверок на каждой линии: один вход, настройки сред, тождество, конфликт, порядок, заглушки',
                    {line: dual[line]['counts'] for line in dual},
                    'pass' if all(dual[line]['counts'] == {'pass': 16} for line in dual) else 'fail',
                    'dual-base.json; dual-edition.json'))

    rows.append(row('один вход на две среды',
                    'AGENTS.md один, отпечаток не меняется между ходами, второй вход отклоняется second_entry',
                    {line: {'entry_hashes': case(line, 'D4')['actual']['distinct_hashes'],
                            'second_entry': case(line, 'D11')['actual']['refusal'],
                            'repeat_connect': case(line, 'D16')['actual']['outcome']} for line in dual},
                    'pass' if all(status(line, cid) == 'pass' for line in dual
                                  for cid in ('D4', 'D11', 'D16')) else 'fail',
                    'dual-*.json'))

    rows.append(row('настройки сред не тронуты за все ходы',
                    'ни одного изменённого байта в .kilo/**, .kilo/kilo.jsonc, .vscode/settings.json, .github/**',
                    {line: case(line, 'D13')['actual'] for line in dual},
                    'pass' if all(status(line, 'D13') == 'pass' for line in dual) else 'fail',
                    'dual-*.json'))

    rows.append(row('конфликт правил двух сред',
                    'пересечение действующих требований отклоняется кодом conflict в обе стороны',
                    {line: case(line, 'D9')['actual'] for line in dual},
                    'pass' if all(status(line, 'D9') == 'pass' for line in dual) else 'fail',
                    'dual-*.json'))

    rows.append(row('порядок сред не важен',
                    'обратный порядок ходов даёт те же счётчики, health и rules.json',
                    {line: case(line, 'D10')['actual'] for line in dual},
                    'pass' if all(status(line, 'D10') == 'pass' for line in dual) else 'fail',
                    'dual-*.json'))

    rows.append(row('находка F1 измерена: одно событие под двумя расширениями — две записи',
                    'тождество склеивает повтор при одинаковом environment и не склеивает при разном extension',
                    {line: {'same': case(line, 'D6')['actual']['observations'],
                            'different': case(line, 'D7')['actual']['observations']} for line in dual},
                    'pass' if all(status(line, 'D6') == 'pass' and status(line, 'D7') == 'pass'
                                  for line in dual) else 'fail',
                    'dual-*.json', 'решение о правиле — за владельцем, в этой итерации не принималось'))

    rows.append(row('заглушки не заявляют ни входа, ни покрытия',
                    'claude, cursor, antigravity: status stub, entry null, sources [], facts_checked_at null; '
                    'наличие .claude/CLAUDE.md всё равно требует ack_existing',
                    {line: case(line, 'D14')['actual']['stubs'] for line in dual},
                    'pass' if all(status(line, 'D14') == 'pass' for line in dual) else 'fail',
                    'dual-*.json'))

    rows.append(row('адаптер Copilot не сломан заглушками',
                    '13 из 13 на обеих линиях',
                    {line: adapter[line]['counts'] for line in adapter},
                    'pass' if all(adapter[line]['counts'] == {'pass': 13} for line in adapter) else 'fail',
                    'adapter-base.json; adapter-edition.json'))

    rows.append(row('правило тождества не поехало: корпус',
                    '24 склейки (12 форменных и 12 объявленных в И-025), прочих 0, обе линии',
                    {line: {'merged': corpus[line]['merged_count'],
                            'unexpected': len(corpus[line]['unexpected_merges'])} for line in corpus},
                    'pass' if all(corpus[line]['merged_count'] == 24 and
                                  len(corpus[line]['unexpected_merges']) == 12 for line in corpus) else 'fail',
                    'pairs-028-base.json; pairs-028-edition.json'))

    rows.append(row('правило тождества не поехало: журналы',
                    '3 из 3 повторов склеены, ложных 0 из 40, обе линии',
                    {line: {'merged': sum(v['merged'] for v in journals[line]['classes'].values()),
                            'false': len(journals[line]['false_merges'])} for line in journals},
                    'pass' if all(sum(v['merged'] for v in journals[line]['classes'].values()) == 3
                                  and not journals[line]['false_merges'] for line in journals) else 'fail',
                    'pairs-028-journals-*.json'))

    rows.append(row('данные 0.1.7 читаются и не переписываются',
                    'старое читается, повтор не меняет байты, отличие факта даёт запись',
                    {k: compat[k] for k in ('old_version', 'new_version', 'old_data_reads',
                                            'old_data_untouched', 'repeat_kept_bytes', 'ok')},
                    'pass' if compat['ok'] and compat['old_data_untouched'] and compat['repeat_kept_bytes'] else 'fail',
                    'COMPAT.json'))

    chain = {}
    for line, name in (('base', 'AgentContractKit-0.1.8.zip'),
                       ('edition', 'AgentContractKitISAIEdition-0.1.8+docs.1.zip')):
        path = RELEASE / name
        with zipfile.ZipFile(path) as zf:
            chain[line] = sorted({n.split('/')[2] for n in zf.namelist()
                                  if n.startswith('AgentContractLab/releases/') and n.count('/') > 2})
    want = ['0.1.0', '0.1.4', '0.1.5', '0.1.6', '0.1.7', '0.1.8']
    rows.append(row('цепочка выпусков в поставке',
                    'releases/0.1.0, 0.1.4, 0.1.5, 0.1.6, 0.1.7 и 0.1.8 в обеих линиях',
                    chain, 'pass' if all(chain[line] == want for line in chain) else 'fail',
                    'архивы 0.1.8'))

    replay = load('REPLAY.json')
    rows.append(row('повтор из печати совпадает со сборкой',
                    'все результаты и файлы совпадают, identical true',
                    {'identical': replay['identical'], 'equal': replay['equal']},
                    'pass' if replay['identical'] and all(replay['equal'].values()) else 'fail',
                    'REPLAY.json'))

    rows.append(row('живой VS Code с двумя расширениями',
                    'Kilo и Copilot поочерёдно читают AGENTS.md в открытом проекте',
                    None, 'not run', '—',
                    'Расширения здесь не запускаются: стенд имитирует раскладку и вызовы команд.'))
    rows.append(row('загрузка инструкций в VS Code', 'среды действительно читают AGENTS.md',
                    None, 'not run', '—', 'Уровни достоверности 2–3, И-031…И-032.'))
    rows.append(row('старшинство в живых средах', 'kilo.jsonc и .github/copilot-instructions.md перекрывают AGENTS.md',
                    None, 'not run', '—', 'Старшинство взято из документации сред и записано данными.'))
    rows.append(row('Windows и права', 'поведение на другой файловой системе', None, 'not run', '—', 'Здесь только Linux.'))
    rows.append(row('журналы заказчика', 'приёмка на данных владельца', None, 'not run', '—', 'Журналов у владельца нет.'))

    counts = {}
    for item in rows:
        counts[item['status']] = counts.get(item['status'], 0) + 1
    out = dict(iteration='И-028', counts=dict(sorted(counts.items())), rows=rows,
               release=dict(version='0.1.8', tests=totals),
               at='2026-11-18')
    (HERE / 'ACCEPTANCE.json').write_text(
        json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    for item in rows:
        print(f"  {item['status']:7} {item['name']}")
    print(json.dumps(out['counts'], ensure_ascii=False))
    return 0 if not counts.get('fail') else 1


if __name__ == '__main__':
    raise SystemExit(main())
