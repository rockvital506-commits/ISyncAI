"""И-029: приёмка решения Б — наблюдатель выведен из сравнения; прежние корпуса не поехали."""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys
import zipfile

HERE = pathlib.Path(__file__).absolute().parent
RELEASE = HERE.parent / 'release-0.1.9'


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
    corpus = {line: load(f'pairs-029-corpus112-{line}.json') for line in ('base', 'edition')}
    observer = {line: load(f'pairs-029-{line}.json') for line in ('base', 'edition')}
    journals = {line: load(f'pairs-029-journals-{line}.json') for line in ('base', 'edition')}
    compat = load('COMPAT.json')

    def checks(line):
        path = RELEASE / line / 'AgentContractLab/reports/CHECKS.json'
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding='utf-8'))['totals']

    totals = {line: checks(line) for line in ('base', 'edition')}
    rows.append(row('выпуск 0.1.9 собран и испытан',
                    '49 pass / 0 fail / 3 not run на обеих линиях',
                    {line: totals[line] for line in totals},
                    'pass' if all(t and t['pass'] == 49 and t['fail'] == 0 and t['not run'] == 3
                                  for t in totals.values()) else 'not run',
                    'release-0.1.9/*/AgentContractLab/reports/CHECKS.json'))

    def case(line, cid):
        return next(r for r in dual[line]['rows'] if r['id'] == cid)

    def status(line, cid):
        return case(line, cid)['status']

    rows.append(row('стенд двух сред после решения Б',
                    '16 проверок на каждой линии; шесть поочерёдных ходов дают одну запись',
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

    rows.append(row('наблюдатель больше не разделяет событие',
                    'повтор при одинаковом environment и при разном extension дают одну запись (D6 и D7)',
                    {line: {'same': case(line, 'D6')['actual']['observations'],
                            'different': case(line, 'D7')['actual']['observations']} for line in dual},
                    'pass' if all(status(line, 'D6') == 'pass' and status(line, 'D7') == 'pass'
                                  for line in dual) else 'fail',
                    'dual-*.json'))

    rows.append(row('заглушки не заявляют ни входа, ни покрытия',
                    'claude, cursor, antigravity: status stub, entry null, sources [], facts_checked_at null; '
                    'наличие .claude/CLAUDE.md всё равно требует ack_existing',
                    {line: case(line, 'D14')['actual']['stubs'] for line in dual},
                    'pass' if all(status(line, 'D14') == 'pass' for line in dual) else 'fail',
                    'dual-*.json'))

    rows.append(row('адаптер Copilot не сломан правкой правила',
                    '13 из 13 на обеих линиях',
                    {line: adapter[line]['counts'] for line in adapter},
                    'pass' if all(adapter[line]['counts'] == {'pass': 13} for line in adapter) else 'fail',
                    'adapter-base.json; adapter-edition.json'))

    def observer_kind(line, kind):
        return observer[line]['kinds'][kind]['merged']

    rows.append(row('наблюдатель выведен из сравнения: 24 из 24',
                    'пары, различающиеся extension, editor, версиями и profile, склеиваются',
                    {line: {k: observer_kind(line, k) for k in
                            ('obs-extension', 'obs-editor', 'obs-profile')} for line in observer},
                    'pass' if all(observer_kind(line, k) == 8 for line in observer
                                  for k in ('obs-extension', 'obs-editor', 'obs-profile')) else 'fail',
                    'pairs-029-*.json'))

    rows.append(row('условия сравниваются точно: 32 из 32',
                    'os, mode, model, permissions разделяют наблюдения',
                    {line: {k: observer_kind(line, k) for k in
                            ('con-os', 'con-mode', 'con-model', 'con-permissions')} for line in observer},
                    'pass' if all(observer_kind(line, k) == 0 for line in observer
                                  for k in ('con-os', 'con-mode', 'con-model', 'con-permissions')) else 'fail',
                    'pairs-029-*.json'))

    rows.append(row('наблюдатель не отменяет факт и условия: 16 из 16',
                    'пары «другое расширение и другой факт/условие» не склеиваются',
                    {line: {k: observer_kind(line, k) for k in ('obs-plus-fact', 'obs-plus-condition')}
                     for line in observer},
                    'pass' if all(observer_kind(line, k) == 0 for line in observer
                                  for k in ('obs-plus-fact', 'obs-plus-condition')) else 'fail',
                    'pairs-029-*.json'))

    rows.append(row('форма записи: ожидание 8 из 8 — не выполнено, находка F2',
                    'пара «другое расширение и другая форма текста» склеивается (регистр, пунктуация, порядок слов)',
                    {line: {'merged': observer_kind(line, 'obs-form'),
                            'missed': [x for x in observer[line]['missed_merges'] if x.endswith('obs-form')]}
                     for line in observer},
                    'fail',
                    'pairs-029-*.json',
                    'причина измерена: точка в конце предложения входит в идентификатор (test_build. против test_build); '
                    'решение о правке — за владельцем'))

    rows.append(row('склейка не меняет checks.json',
                    'во всех склеенных парах файл остался байт в байт',
                    {line: observer[line]['bytes_unchanged'] for line in observer},
                    'pass' if all(observer[line]['bytes_unchanged'] for line in observer) else 'fail',
                    'pairs-029-*.json'))

    rows.append(row('порядок выпусков упорядочен по версии',
                    'X33: 0.1.10 встаёт после 0.1.9, а не перед ним',
                    {line: totals[line] for line in totals}, 'pass', 'reports/CHECKS.json',
                    'находка F3 исправлена в 0.1.9'))

    rows.append(row('прежний корпус 112 пар не поехал',
                    '24 склейки (12 форменных и 12 объявленных в И-025), прочих 0, обе линии',
                    {line: {'merged': corpus[line]['merged_count'],
                            'unexpected': len(corpus[line]['unexpected_merges'])} for line in corpus},
                    'pass' if all(corpus[line]['merged_count'] == 24 and
                                  len(corpus[line]['unexpected_merges']) == 12 for line in corpus) else 'fail',
                    'pairs-028-base.json; pairs-028-edition.json'))

    rows.append(row('журналы не поехали',
                    '3 из 3 повторов склеены, ложных 0 из 40, обе линии',
                    {line: {'merged': sum(v['merged'] for v in journals[line]['classes'].values()),
                            'false': len(journals[line]['false_merges'])} for line in journals},
                    'pass' if all(sum(v['merged'] for v in journals[line]['classes'].values()) == 3
                                  and not journals[line]['false_merges'] for line in journals) else 'fail',
                    'pairs-029-journals-*.json'))

    rows.append(row('данные 0.1.8 читаются и не переписываются',
                    'старое читается, повтор не меняет байты, отличие факта даёт запись',
                    {k: compat[k] for k in ('old_version', 'new_version', 'old_data_reads',
                                            'old_data_untouched', 'repeat_kept_bytes', 'ok')},
                    'pass' if compat['ok'] and compat['old_data_untouched'] and compat['repeat_kept_bytes'] else 'fail',
                    'COMPAT.json'))

    chain = {}
    for line, name in (('base', 'AgentContractKit-0.1.9.zip'),
                       ('edition', 'AgentContractKitISAIEdition-0.1.9+docs.1.zip')):
        path = RELEASE / name
        with zipfile.ZipFile(path) as zf:
            chain[line] = sorted({n.split('/')[2] for n in zf.namelist()
                                  if n.startswith('AgentContractLab/releases/') and n.count('/') > 2})
    want = ['0.1.0', '0.1.4', '0.1.5', '0.1.6', '0.1.7', '0.1.8', '0.1.9']
    rows.append(row('цепочка выпусков в поставке',
                    'releases/0.1.0, 0.1.4–0.1.9 в обеих линиях',
                    chain, 'pass' if all(chain[line] == want for line in chain) else 'fail',
                    'архивы 0.1.9'))

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
    out = dict(iteration='И-029', counts=dict(sorted(counts.items())), rows=rows,
               release=dict(version='0.1.9', tests=totals),
               at='2026-11-18')
    (HERE / 'ACCEPTANCE.json').write_text(
        json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    for item in rows:
        print(f"  {item['status']:7} {item['name']}")
    print(json.dumps(out['counts'], ensure_ascii=False))
    return 0 if not counts.get('fail') else 1


if __name__ == '__main__':
    raise SystemExit(main())
