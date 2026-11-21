#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""И-101: машинная приёмка. Пишет ACCEPTANCE.json в research/101/.

Правило: проверка без фактического прогона получает статус `not run`, а не `pass`.
Проверка, зависящая от печати, читает SEAL.json — поэтому печать выполняется до приёмки.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
ZIP = os.path.join(REPO, 'research', 'release-0.1.36', 'AgentContractKit-0.1.36.zip')
SURFACES = ('promote', 'simulate', 'bundle', 'bundle_verify', 'guard', 'prompt')


def read(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read()


def check(name, ok, basis, detail=None):
    return {'check': name, 'status': 'pass' if ok else 'fail', 'basis': basis, 'detail': detail}


def run_script(script, *args):
    out = subprocess.run([sys.executable, os.path.join(HERE, script), *args],
                         capture_output=True, cwd=REPO)
    return out.returncode, out.stdout


def deterministic_inventory():
    """Два независимых прогона инвентаря обязаны дать идентичные байты."""
    emitted = []
    for _ in range(2):
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as fh:
            path = fh.name
        rc, _ = run_script('inventory.py', '--zip', ZIP, '--out', path)
        if rc != 0:
            return False, 'прогон инвентаря завершился ошибкой'
        emitted.append(open(path, 'rb').read())
        os.unlink(path)
    return emitted[0] == emitted[1], hashlib.sha256(emitted[0]).hexdigest()[:16]


def deterministic_cleanroom():
    digests = []
    for _ in range(2):
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as fh:
            path = fh.name
        rc, _ = run_script('cleanroom.py', '--zip', ZIP, '--out', path)
        if rc != 0:
            return False, None
        digests.append(json.load(open(path))['checkpoints_digest'])
        os.unlink(path)
    return digests[0] == digests[1], digests[0]


def main():
    base = json.load(open(os.path.join(REPO, 'research', 'strategy', 'BASELINE.json')))
    room = json.load(open(os.path.join(HERE, 'CLEANROOM.json')))
    strategy = read(os.path.join(REPO, 'research', 'STRATEGY.md'))
    journal = read(os.path.join(REPO, 'research', 'strategy', 'SYNC-LOG.md'))
    report = read(os.path.join(HERE, 'REPORT.md'))
    steps = {s['step']: s for s in room['steps']}

    checks = []
    checks.append(check('strategy_file', 'Версия: **v1.1**' in strategy,
                        'research/STRATEGY.md: заголовок версии'))
    checks.append(check('sync_journal', journal.count('\n| ') >= 6,
                        'research/strategy/SYNC-LOG.md: строки журнала', journal.count('\n| ')))
    checks.append(check('report_basis', 'basis' in report and 'not run' in report,
                        'research/101/REPORT.md: разделы basis и not run'))
    checks.append(check('baseline_release', base['release'] == '0.1.36',
                        'BASELINE.json: release', base['release']))
    checks.append(check('baseline_files_match_zip',
                        base['tree']['files'] == base['zip']['members'] == 220,
                        'BASELINE.json: tree.files == zip.members', base['zip']['members']))
    ok, digest = deterministic_inventory()
    checks.append(check('baseline_deterministic', ok, 'два прогона inventory.py', digest))
    absent = [s for s in SURFACES if base['surfaces'][s]['present']]
    checks.append(check('six_surfaces_absent', not absent,
                        'BASELINE.json: surfaces[*].present', absent))
    checks.append(check('adapters_baseline',
                        base['adapters']['kilo']['status'] == 'documented'
                        and base['adapters']['copilot']['status'] == 'documented'
                        and 'arena' in base['absent_adapters']
                        and len(base['stub_adapters']) == 3,
                        'BASELINE.json: adapters',
                        {'absent': base['absent_adapters'], 'stub': base['stub_adapters']}))
    checks.append(check('cleanroom_install', steps['2-install']['rc'] == 0,
                        'CLEANROOM.json: шаг 2', steps['2-install']))
    checks.append(check('cleanroom_connect', steps['4-connect']['rc'] == 0,
                        'CLEANROOM.json: шаг 4', steps['4-connect']))
    checks.append(check('cleanroom_create',
                        steps['5a-create-contract']['rc'] == 0 and steps['5b-create-rule']['rc'] == 0,
                        'CLEANROOM.json: шаги 5a, 5b'))
    checks.append(check('cleanroom_list',
                        steps['6-list']['contracts'] == 1 and steps['6-list']['active'] == 1,
                        'CLEANROOM.json: шаг 6', steps['6-list']))
    checks.append(check('cleanroom_arena_refused',
                        steps['7-adapter-arena']['error'] == 'adapter_unknown',
                        'CLEANROOM.json: шаг 7', steps['7-adapter-arena']))
    ok2, room_digest = deterministic_cleanroom()
    checks.append(check('cleanroom_deterministic', ok2, 'два прогона cleanroom.py', room_digest))
    checks.append(check('page_exists', os.path.exists(os.path.join(HERE, 'Итерация-101.html')),
                        'файл страницы итерации'))

    seal_path = os.path.join(HERE, 'SEAL.json')
    if os.path.exists(seal_path):
        seal = json.load(open(seal_path))
        checks.append(check('seal_recorded', seal.get('bytes', 0) > 0 and len(seal.get('sha256', '')) == 64,
                            'SEAL.json', {'bytes': seal.get('bytes'), 'sha256': seal.get('sha256')}))
    else:
        checks.append({'check': 'seal_recorded', 'status': 'not run',
                       'basis': 'SEAL.json отсутствует на момент приёмки', 'detail': None})

    not_run = [
        {'what': 'поведение моделей в Arena / Kilo / Copilot', 'why': 'отдельные сессии и N повторов — И-125'},
        {'what': 'чтение AGENTS.md в Arena', 'why': 'публичной спецификации нет — И-124/И-125'},
        {'what': 'локальный запуск в VS Code 1.146 (Windows 11)', 'why': 'среды нет в песочнице — И-134'},
        {'what': 'полный набор тестов выпуска kit/tests', 'why': 'не входит в тест итерации; переносится в И-102'},
    ]
    counts = {'pass': sum(1 for c in checks if c['status'] == 'pass'),
              'fail': sum(1 for c in checks if c['status'] == 'fail'),
              'not run': sum(1 for c in checks if c['status'] == 'not run')}
    result = {'iteration': 'И-101', 'phase': 'Ф0', 'checks': checks, 'counts': counts,
              'not_run': not_run, 'outcome': 'accepted' if counts['fail'] == 0 else 'rejected'}
    text = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2)
    with open(os.path.join(HERE, 'ACCEPTANCE.json'), 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(text + '\n')
    print(text)
    return 0 if counts['fail'] == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
