"""И-030: приёмка решения Б по F2 — завершающая точка не входит в идентификатор."""
from __future__ import annotations

import hashlib
import json
import pathlib
import zipfile

HERE = pathlib.Path(__file__).absolute().parent
RELEASE = HERE.parent / 'release-0.1.10'


def load(name):
    return json.loads((HERE / name).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def main():
    rows = []

    def row(name, expected, actual, status, source, note=''):
        return dict(name=name, expected=expected, actual=actual, status=status, source=source, note=note)

    lines = ('base', 'edition')
    punct = {line: load(f'pairs-030-{line}.json') for line in lines}
    corpus80 = {line: load(f'pairs-030-corpus80-{line}.json') for line in lines}
    corpus112 = {line: load(f'pairs-030-corpus112-{line}.json') for line in lines}
    journals = {line: load(f'pairs-030-journals-{line}.json') for line in lines}
    dual = {line: load(f'dual-{line}.json') for line in lines}
    adapter = {line: load(f'adapter-{line}.json') for line in lines}
    compat = load('COMPAT.json')

    def totals(line):
        path = RELEASE / line / 'AgentContractLab/reports/CHECKS.json'
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding='utf-8'))['totals']

    tests = {line: totals(line) for line in lines}
    rows.append(row('выпуск 0.1.10 собран и испытан',
                    '50 pass / 0 fail / 3 not run на обеих линиях',
                    tests,
                    'pass' if all(t and t['pass'] == 50 and t['fail'] == 0 and t['not run'] == 3
                                  for t in tests.values()) else 'not run',
                    'release-0.1.10/*/AgentContractLab/reports/CHECKS.json',
                    'находка F4: при первой сборке блоки правок не применились из-за строкового сравнения версий'))

    def merged(line, kind):
        return punct[line]['kinds'][kind]['merged']

    dots = ('dot-identifier', 'dot-dotted-name', 'dot-exception', 'dot-version', 'dot-file', 'dot-two-sentences')
    names = ('name-with-extension', 'name-version', 'name-changed', 'name-dotted-longer',
             'number-changed', 'dot-vs-underscore')
    rows.append(row('завершающая точка не разделяет событие: 6 из 6',
                    'test_build., a.b., TypeError., v1.0., test_build.py. и две фразы склеиваются',
                    {line: {k: merged(line, k) for k in dots} for line in lines},
                    'pass' if all(merged(line, k) == 1 for line in lines for k in dots) else 'fail',
                    'pairs-030-*.json'))
    rows.append(row('точка внутри имени значима: 6 из 6',
                    'test_build.py против test_build, v1.1 против v1.0, a.b.c против a.b, a_b против a.b — разделены',
                    {line: {k: merged(line, k) for k in names} for line in lines},
                    'pass' if all(merged(line, k) == 0 for line in lines for k in names) else 'fail',
                    'pairs-030-*.json'))

    rows.append(row('корпус И-029: 80 из 80',
                    'форма записи стала склеиваться (8 из 8 против 3 из 8), остальные виды не изменились',
                    {line: {'missed': len(corpus80[line]['missed_merges']),
                            'false': len(corpus80[line]['false_merges']),
                            'form': corpus80[line]['kinds']['obs-form']['merged']} for line in lines},
                    'pass' if all(not corpus80[line]['missed_merges'] and not corpus80[line]['false_merges']
                                  and corpus80[line]['kinds']['obs-form']['merged'] == 8 for line in lines) else 'fail',
                    'pairs-030-corpus80-*.json'))

    rows.append(row('прежний корпус 112 пар не поехал',
                    '24 склейки, из них 12 объявленных в И-025, прочих 0',
                    {line: {'merged': corpus112[line]['merged_count'],
                            'unexpected': len(corpus112[line]['unexpected_merges'])} for line in lines},
                    'pass' if all(corpus112[line]['merged_count'] == 24 for line in lines) else 'fail',
                    'pairs-030-corpus112-*.json'))

    rows.append(row('журналы не поехали',
                    '3 из 3 повторов склеены, ложных 0 из 40',
                    {line: {'merged': sum(v['merged'] for v in journals[line]['classes'].values()),
                            'false': len(journals[line]['false_merges'])} for line in lines},
                    'pass' if all(sum(v['merged'] for v in journals[line]['classes'].values()) == 3
                                  and not journals[line]['false_merges'] for line in lines) else 'fail',
                    'pairs-030-journals-*.json'))

    rows.append(row('склейка не меняет checks.json',
                    'во всех склеенных парах корпусов файл остался байт в байт',
                    {line: punct[line]['bytes_unchanged'] for line in lines},
                    'pass' if all(punct[line]['bytes_unchanged'] for line in lines) else 'fail',
                    'pairs-030-*.json'))

    rows.append(row('стенд двух сред',
                    '16 проверок на каждой линии, шесть поочерёдных ходов дают одну запись',
                    {line: dual[line]['counts'] for line in lines},
                    'pass' if all(dual[line]['counts'] == {'pass': 16} for line in lines) else 'fail',
                    'dual-*.json'))

    rows.append(row('адаптер Copilot не сломан правкой правила',
                    '13 из 13 на обеих линиях',
                    {line: adapter[line]['counts'] for line in lines},
                    'pass' if all(adapter[line]['counts'] == {'pass': 13} for line in lines) else 'fail',
                    'adapter-*.json'))

    rows.append(row('данные 0.1.9 читаются и не переписываются',
                    'старое читается, повтор не меняет байты, отличие факта даёт запись',
                    {k: compat[k] for k in ('old_version', 'new_version', 'old_data_reads',
                                            'old_data_untouched', 'repeat_kept_bytes', 'ok')},
                    'pass' if compat['ok'] and compat['old_data_untouched'] and compat['repeat_kept_bytes'] else 'fail',
                    'COMPAT.json'))

    chain = {}
    for line, name in (('base', 'AgentContractKit-0.1.10.zip'),
                       ('edition', 'AgentContractKitISAIEdition-0.1.10+docs.1.zip')):
        with zipfile.ZipFile(RELEASE / name) as zf:
            chain[line] = sorted({n.split('/')[2] for n in zf.namelist()
                                  if n.startswith('AgentContractLab/releases/') and n.count('/') > 2})
    want = ['0.1.0', '0.1.4', '0.1.5', '0.1.6', '0.1.7', '0.1.8', '0.1.9', '0.1.10']
    def by_version(names):
        return sorted(names, key=lambda v: tuple(map(int, v.split('.'))))
    rows.append(row('цепочка выпусков в поставке',
                    'releases/0.1.0 и 0.1.4–0.1.10 в обеих линиях',
                    {line: by_version(chain[line]) for line in chain},
                    'pass' if all(sorted(chain[line]) == sorted(want) for line in chain) else 'fail',
                    'архивы 0.1.10'))

    replay = load('REPLAY.json')
    rows.append(row('повтор из печати совпадает со сборкой',
                    'все результаты и файлы совпадают, identical true',
                    {'identical': replay['identical'], 'equal': replay['equal']},
                    'pass' if replay['identical'] and all(replay['equal'].values()) else 'fail',
                    'REPLAY.json'))

    rows.append(row('живой VS Code с двумя расширениями',
                    'Kilo и Copilot поочерёдно читают AGENTS.md в открытом проекте',
                    None, 'not run', '—', 'Расширения здесь не запускаются.'))
    rows.append(row('загрузка инструкций в VS Code', 'среды действительно читают AGENTS.md',
                    None, 'not run', '—', 'Уровни достоверности 2–3, И‑031…И‑032.'))
    rows.append(row('старшинство в живых средах', 'kilo.jsonc и .github/copilot-instructions.md перекрывают AGENTS.md',
                    None, 'not run', '—', 'Старшинство взято из документации сред и записано данными.'))
    rows.append(row('Windows и права', 'поведение на другой файловой системе', None, 'not run', '—', 'Здесь только Linux.'))
    rows.append(row('журналы заказчика', 'приёмка на данных владельца', None, 'not run', '—', 'Журналов у владельца нет.'))

    counts = {}
    for item in rows:
        counts[item['status']] = counts.get(item['status'], 0) + 1
    out = dict(iteration='И-030', counts=dict(sorted(counts.items())), rows=rows,
               release=dict(version='0.1.10', tests=tests), at='2026-11-18')
    (HERE / 'ACCEPTANCE.json').write_text(
        json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    for item in rows:
        print(f"  {item['status']:7} {item['name']}")
    print(json.dumps(out['counts'], ensure_ascii=False))
    return 0 if not counts.get('fail') else 1


if __name__ == '__main__':
    raise SystemExit(main())
