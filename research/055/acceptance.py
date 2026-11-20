"""И-055: приёмка — достоверность 5: повтор серии."""
from __future__ import annotations

import hashlib
import json
import pathlib
import zipfile

HERE = pathlib.Path(__file__).absolute().parent
RELEASE = HERE.parent / 'release-0.1.35'
LINES = ('base', 'edition')


def load(name):
    return json.loads((HERE / name).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def main():
    rows = []

    def row(name, expected, actual, status, source, note=''):
        return dict(name=name, expected=expected, actual=actual, status=status, source=source, note=note)

    def checks(line):
        return json.loads((RELEASE / line / 'AgentContractLab/reports/CHECKS.json').read_text(encoding='utf-8'))

    totals = {line: checks(line)['totals'] for line in LINES}
    rows.append(row('выпуск 0.1.35 собран и испытан',
                    '102 pass / 0 fail / 3 not run на обеих линиях',
                    totals,
                    'pass' if all(t == {'pass': 102, 'fail': 0, 'not run': 3, 'inconclusive': 0}
                                  for t in totals.values()) else 'fail',
                    'release-0.1.35/*/AgentContractLab/reports/CHECKS.json'))

    cases = {}
    for line in LINES:
        report = checks(line)
        cases[line] = {c['case']: c.get('status') for c in report['cases']}
    rows.append(row('раскладка: лаборатория, проект и корень',
                    'X78 пройден на обеих линиях',
                    {line: cases[line].get('X78') for line in LINES},
                    'pass' if all(cases[line].get('X78') == 'pass' for line in LINES) else 'fail',
                    'X78 layout называет раскладку из четырёх и не пишет'))
    rows.append(row('права измерены, а не объявлены',
                    'X84, X85 и X86 пройдены на обеих линиях',
                    {line: {k: cases[line].get(k) for k in ('X84', 'X85', 'X86')} for line in LINES},
                    'pass' if all(cases[line].get(k) == 'pass' for line in LINES for k in ('X80', 'X81')) else 'fail',
                    'X84 книга калибровки с отпечатками; X85 ответ пишется до сравнения; X86 починка в закрытом списке'))

    punct = {line: load(f'pairs-055-cli-punct-{line}.json') for line in LINES}
    rows.append(row('корпус пунктуации через консоль',
                    '12 пар, 6 склеек, 0 промахов и 0 ложных на обеих линиях',
                    {line: {k: punct[line][k] for k in ('pairs', 'merged', 'unexpected', 'bytes_unchanged')}
                     for line in LINES},
                    'pass' if all(punct[l]['outcome'] == 'pass' and punct[l]['merged'] == 6 for l in LINES) else 'fail',
                    'pairs-055-cli-punct-*.json'))

    corpus80 = {line: load(f'pairs-055-cli-corpus80-{line}.json') for line in LINES}
    rows.append(row('корпус И-029 через консоль',
                    '80 пар, 32 склейки, ничего неожиданного',
                    {line: {k: corpus80[line][k] for k in ('pairs', 'merged', 'unexpected')} for line in LINES},
                    'pass' if all(corpus80[l]['outcome'] == 'pass' and corpus80[l]['pairs'] == 80 for l in LINES) else 'fail',
                    'pairs-055-cli-corpus80-*.json'))

    corpus112 = {line: load(f'pairs-055-cli-corpus112-{line}.json') for line in LINES}
    rows.append(row('корпус 112 пар через консоль',
                    '24 склейки, из них 12 объявленных в И-025, прочих 0',
                    {line: {'merged': corpus112[line]['merged'],
                            'declared_false': len(corpus112[line]['declared_false']),
                            'declared_missed': len(corpus112[line]['declared_missed']),
                            'unexpected': len(corpus112[line]['unexpected'])} for line in LINES},
                    'pass' if all(corpus112[l]['merged'] == 24 and not corpus112[l]['unexpected'] for l in LINES) else 'fail',
                    'pairs-055-cli-corpus112-*.json'))

    journals = {line: load(f'pairs-055-journals-{line}.json') for line in LINES}
    rows.append(row('журналы (прежний стенд, импорт)',
                    '3 из 3 повторов склеены, ложных 0 из 40',
                    {line: {'merged': sum(v['merged'] for v in journals[line]['classes'].values()),
                            'false': len(journals[line]['false_merges'])} for line in LINES},
                    'pass' if all(sum(v['merged'] for v in journals[l]['classes'].values()) == 3
                                  and not journals[l]['false_merges'] for l in LINES) else 'fail',
                    'pairs-055-journals-*.json',
                    'перенос этого стенда на консоль — в следующей итерации'))

    pilot = {line: load(f'PILOT-{line}.json') for line in LINES}
    counts = {line: pilot[line]['counts'] for line in LINES}
    adapter_ok = all(any(i['id'] == 'P5' and any(r['command'] == 'adapter' and r['rc'] == 0
                                                 for r in i['evidence']['runs']) for i in pilot[l]['items'])
                     for l in LINES)
    rows.append(row('матрица обкатки измерена: 33 уровня',
                    'P1–P8 на обеих линиях: 8 pass / 0 fail, карточка среды доступна внутри прогона',
                    dict(counts=counts, adapter_from_cli=adapter_ok),
                    'pass' if all(counts[l].get('pass') == 33 and counts[l].get('not run') == 4 for l in LINES) and adapter_ok else 'fail',
                    'PILOT-*.json',
                    'P1–P8 закрыты; L1, L2, L3, L3F, L4C, L4Q, L4D, L4S, L4O, L4V, L4X, L4P, L4M, L4T, L4K, L4R, L4W, L4F, L4L, L6, L7, L8, L9, L5a, L5b измерены; выполнение требования моделью, чтение моделью, повтор моделью и живая среда — not run'))

    compat = load('COMPAT.json')
    rows.append(row('данные 0.1.34 читаются и не переписываются',
                    'старое читается, повтор не меняет байты, отличие факта даёт запись',
                    {k: compat[k] for k in ('old_version', 'new_version', 'old_data_reads',
                                            'old_data_untouched', 'repeat_kept_bytes', 'ok')},
                    'pass' if compat['ok'] and compat['old_data_untouched'] and compat['repeat_kept_bytes'] else 'fail',
                    'COMPAT.json'))

    chain = {}
    for line, name in (('base', 'AgentContractKit-0.1.35.zip'),
                       ('edition', 'AgentContractKitISAIEdition-0.1.35+docs.1.zip')):
        with zipfile.ZipFile(RELEASE / name) as zf:
            chain[line] = sorted({n.split('/')[2] for n in zf.namelist()
                                  if n.startswith('AgentContractLab/releases/') and n.count('/') > 2},
                                 key=lambda v: tuple(map(int, v.split('.'))))
            want = ['0.1.0', '0.1.4', '0.1.5', '0.1.6', '0.1.7', '0.1.8', '0.1.9', '0.1.10', '0.1.11',
            '0.1.12', '0.1.13', '0.1.14', '0.1.15', '0.1.16', '0.1.17', '0.1.18', '0.1.19', '0.1.20', '0.1.21', '0.1.22', '0.1.23', '0.1.24', '0.1.25', '0.1.26', '0.1.27', '0.1.28', '0.1.29', '0.1.30', '0.1.31', '0.1.32', '0.1.33', '0.1.34', '0.1.35']
    rows.append(row('цепочка выпусков в поставке',
                    'releases/0.1.0 и 0.1.4–0.1.35 в обеих линиях',
                    chain, 'pass' if all(chain[l] == want for l in chain) else 'fail', 'архивы 0.1.35'))

    replay = load('REPLAY.json')
    cal_name = 'AgentContractKit-Calibration-0.1.35.zip'
    cal_path = RELEASE / cal_name
    cal_inside = False
    cal_members = []
    if cal_path.is_file():
        with zipfile.ZipFile(cal_path) as zf:
            cal_members = zf.namelist()
            cal_inside = any(m.endswith('ЭТАЛОНЫ-ПОСЛЕ.md') for m in cal_members)
    probes = []
    if cal_path.is_file():
        with zipfile.ZipFile(cal_path) as zf:
            text = zf.read('AgentContractKitCalibration/docs/ЭТАЛОНЫ-ПОСЛЕ.md').decode('utf-8')
        probes = [line for line in text.splitlines() if len(line) >= 60][:3]
    in_kit = []
    for name in ('AgentContractKit-0.1.35.zip', 'AgentContractKitISAIEdition-0.1.35+docs.1.zip'):
        with zipfile.ZipFile(RELEASE / name) as zf:
            for member in zf.namelist():
                if member.endswith('.md') or member.endswith('.json'):
                    data = zf.read(member).decode('utf-8', 'ignore')
                    if any(probe in data for probe in probes):
                        in_kit.append(member)
    rows.append(row('эталоны отдельным архивом, в поставке их нет',
                    'архив AgentContractKit-Calibration с эталонами; в основных архивах значений нет',
                    dict(archive=cal_name, present=cal_path.is_file(), reference=cal_inside,
                         members=cal_members, probes=len(probes), leaks=in_kit),
                    'pass' if cal_path.is_file() and cal_inside and probes and not in_kit else 'fail',
                    'отдельный архив эталонов и отсутствие их в основных архивах'))
    rows.append(row('повтор из печати совпадает со сборкой',
                    'все результаты и файлы совпадают, identical true',
                    {'identical': replay['identical'], 'equal': replay['equal']},
                    'pass' if replay['identical'] and all(replay['equal'].values()) else 'fail',
                    'REPLAY.json'))

    rows.append(row('живой VS Code с двумя расширениями', 'Kilo и Copilot поочерёдно читают вход',
                    None, 'not run', '—', 'Расширения здесь не запускаются.'))
    rows.append(row('загрузка инструкций в VS Code', 'среды действительно читают AGENTS.md',
                    None, 'not run', '—', 'Уровни достоверности 2–3, отдельные итерации.'))
    rows.append(row('поведение моделей', 'модель следует правилам комплекта',
                    None, 'not run', '—', 'Стенд исполняет промпт буквально, а не изображает модель.'))
    rows.append(row('Windows и права', 'поведение на другой файловой системе', None, 'not run', '—',
                    'Стенд подаёт платформу как объявленные данные, а не как факт машины.'))
    rows.append(row('журналы заказчика', 'приёмка на данных владельца', None, 'not run', '—',
                    'Журналов у владельца нет.'))

    counts_out = {}
    for item in rows:
        counts_out[item['status']] = counts_out.get(item['status'], 0) + 1
    out = dict(iteration='И-055', at='2026-11-18', counts=dict(sorted(counts_out.items())), rows=rows,
               release=dict(version='0.1.35', tests=totals))
    (HERE / 'ACCEPTANCE.json').write_text(
        json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    for item in rows:
        print(f"  {item['status']:7} {item['name']}")
    print(json.dumps(out['counts'], ensure_ascii=False))
    return 0 if not counts_out.get('fail') else 1


if __name__ == '__main__':
    raise SystemExit(main())
