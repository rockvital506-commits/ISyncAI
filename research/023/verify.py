#!/usr/bin/env python3
"""И-023: независимая проверка журналов и наблюдений.

Ничего не берёт из observations.json, кроме самих наблюдений: журналы читаются заново с диска,
отпечатки сверяются с provenance.json, факт ищется в указанной строке дословно.
"""
from __future__ import annotations

import hashlib
import json
import pathlib

HERE = pathlib.Path(__file__).absolute().parent
JOURNALS = HERE / 'journals'

# независимая таблица рамок: только префикс/суффикс, без правил разбора
FRAMES = {
    'pytest-summary': ('Итог прогона: ', '.'),
    'pytest-failed': ('Падает тест ', '.'),
    'pip-error': ('Ошибка pip: ', ''),
    'build-error': ('Ошибка сборки: ', ''),
    'npm-deprecated': ('', ' объявлен устаревшим.'),
    'npm-error': ('Ошибка npm: ', ''),
    'npm-vuln-total': ('Уязвимостей: ', ''),
}
ENV_KEYS = 'os editor editor_version extension extension_version mode model profile permissions'.split()


def main():
    provenance = json.loads((JOURNALS / 'provenance.json').read_text(encoding='utf-8'))
    obs = json.loads((HERE / 'observations.json').read_text(encoding='utf-8'))
    problems, checks = [], []

    # 1. происхождение журналов
    listed = {j['id'] for j in provenance['journals']}
    for journal in provenance['journals']:
        path = JOURNALS / journal['log']
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != journal['log_sha256']:
            problems.append(f"отпечаток {journal['id']} не совпадает с файлом")
        for field in ('command', 'exit_code', 'started', 'finished'):
            if field not in journal:
                problems.append(f"у {journal['id']} нет поля {field}")
    checks.append(dict(check='журналы с происхождением', journals=len(listed),
                       authored_in_journals=len(listed & {'authored-control'})))

    # 2. контроль, написанный рукой
    authored = provenance['authored']
    authored_path = JOURNALS / authored['log']
    authored_ok = (authored_path.exists()
                   and hashlib.sha256(authored_path.read_bytes()).hexdigest() == authored['log_sha256']
                   and authored['id'] not in listed)
    if not authored_ok:
        problems.append('контрольный журнал не распознан как написанный рукой')
    checks.append(dict(check='написанный рукой журнал вне приёмки', detected=authored_ok,
                       authored_journals=0 if authored_ok else 1))

    # 3. каждый факт — в указанной строке
    lines_cache = {}
    verified = 0
    for row in obs['rows']:
        path = JOURNALS / f"{row['journal']}.log"
        if row['journal'] not in lines_cache:
            lines_cache[row['journal']] = path.read_text(encoding='utf-8').splitlines()
        lines = lines_cache[row['journal']]
        if not 1 <= row['line'] <= len(lines):
            problems.append(f"{row['id']}: строка вне файла")
            continue
        source = lines[row['line'] - 1].strip()
        if row['facts'] not in source:
            problems.append(f"{row['id']}: факт не найден в строке {row['line']}")
        prefix, suffix = FRAMES[row['case']]
        if not (row['actual'].startswith(prefix) and row['actual'].endswith(suffix)
                and row['actual'] == f"{prefix}{row['facts']}{suffix}"):
            problems.append(f"{row['id']}: рамка не совпадает с фактом")
        if row['evidence'] != f"{row['journal']}.log, строка {row['line']}":
            problems.append(f"{row['id']}: улика не соответствует номеру строки")
        if list(row['environment']) and sorted(row['environment']) != sorted(ENV_KEYS):
            problems.append(f"{row['id']}: неполное окружение")
        if row['level'] not in (1, 2, 3) or not row['expected']:
            problems.append(f"{row['id']}: уровень или ожидание вне допустимого")
        verified += 1

    checks.append(dict(check='факты подтверждены строками журналов', verified=verified,
                       observations=len(obs['rows']),
                       cases=sorted({r['case'] for r in obs['rows']})))
    result = dict(iteration='И-023', problems=problems, checks=checks,
                  ok=not problems and verified == len(obs['rows']) and len(obs['rows']) >= 40)
    (HERE / 'VERIFY.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
                                      + '\n', encoding='utf-8')
    print(json.dumps(result['checks'], ensure_ascii=False, indent=1))
    print('проблем:', len(problems), 'ok:', result['ok'])
    for p in problems[:10]:
        print(' !', p)


if __name__ == '__main__':
    main()
