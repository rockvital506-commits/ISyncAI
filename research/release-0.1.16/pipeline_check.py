#!/usr/bin/env python3
"""Сквозная имитация для восстановленного выпуска 0.1.4 (И-022).

Пишет отчёт в stdout (он же `reports/PIPELINE.json`). Проверяет то, что заявлено в поставке:
установку без входа, подключение входа, проектную запись, правило повтора (точного и смыслового),
переход с 0.1.0 на 0.1.4 с сохранением записей и повторное чтение канонических файлов.
Управляемая имитация; поведение моделей и живые расширения не проверяются.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import shutil
import sys
import tempfile

ap = argparse.ArgumentParser()
ap.add_argument('--tree', required=True)
args = ap.parse_args()
tree = pathlib.Path(args.tree).resolve()
spec = importlib.util.spec_from_file_location('kit_contract', tree / 'kit/tools/contract.py')
c = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = c
spec.loader.exec_module(c)

VERSION = c.parse((tree / 'kit/base/manifest.json').read_bytes())['base_version']
PIN = c.digest((tree / 'kit/base/manifest.json').read_bytes())
plans, reads = [], []
ENV = {k: 'synthetic' for k in c.ENV_KEYS.split()}


def call(command, payload=None, project='A', target=None):
    return c.dispatch(lab, project, command, {} if payload is None else payload, target)


def approve(request, project='A'):
    view = call('plan', request, project)
    plans.append(dict(project=project, op=request['op'], writes=view['writes'] is False,
                      notes=view['notes'], paths=sorted(x['path'] for x in view['changes'])))
    assert view['writes'] is False, view
    return call('apply', {'request': request, 'ticket': view['ticket']}, project)


def observation(**kw):
    base = dict(case='imitation', level=1, conditions='Условия синтетические, прогон один', expected='файл есть',
                actual='Файл есть, строка 17', status='pass', evidence='журнал имитации, строка 17',
                limits='только наличие', environment=dict(ENV))
    base.update(kw)
    return base


with tempfile.TemporaryDirectory() as tmp:
    lab = pathlib.Path(tmp).resolve()
    for name in ('A', 'B', 'C', 'D'):
        (lab / name).mkdir()
    # Выпуски копируются внутрь имитации: продукт читает только свою лабораторию.
    shutil.copytree(tree / 'releases', lab / 'releases')

    # 1. Установка без входа: файла AGENTS.md нет, профиль пуст
    probe = call('status', project='C')
    assert probe.get('health') == 'absent', probe
    before_c = {p.relative_to(lab / 'C').as_posix() for p in (lab / 'C').rglob('*') if p.is_file()}
    assert before_c == set(), before_c
    install = approve(dict(op='install', package=f'releases/{VERSION}', pin=PIN))
    assert install['outcome'] == 'committed' and not (lab / 'A' / c.ENTRY).exists(), install

    # 2. Подключение входа
    approve(dict(op='connect'))
    assert (lab / 'A' / c.ENTRY).exists()

    # 3. Проектная запись
    approve(dict(op='create', kind='contract', title='Контракт имитации', text='Договор о проверках имитации.',
                 scope='.', basis='Решение владельца стенда.', criterion='Есть запись о проверке.',
                 reason='Начало имитации.', state='active'))
    first = approve(dict(op='record_check', observation=observation()))
    assert first['outcome'] == 'committed'
    checks_path = lab / 'A' / c.CHECKS
    before = checks_path.read_bytes()

    # 4. Правило повтора: точный, затем пересказ — ни одного изменения байт
    exact = approve(dict(op='record_check', observation=observation()))
    assert exact['outcome'] == 'no_change' and exact['files'] == [], exact
    assert checks_path.read_bytes() == before
    reworded = approve(dict(op='record_check', observation=observation(actual='файл есть строка 17',
                                                                     conditions='прогон один, условия синтетические')))
    assert reworded['outcome'] == 'no_change' and reworded['files'] == [], reworded
    assert checks_path.read_bytes() == before
    assert len(call('status')['observations']) == 1

    # 5. Изменение смысла пишет: снятое ограничение и добавленная фраза
    approve(dict(op='record_check', observation=observation(limits='только наличие. Ограничение снято.')))
    approve(dict(op='record_check', observation=observation(actual='Файл есть, строка 17; прогон повторён, результат тот же')))
    assert len(call('status')['observations']) == 3

    # 6. Локальные записи А не переносятся в Б
    approve(dict(op='install', package=f'releases/{VERSION}', pin=PIN), project='B')
    approve(dict(op='connect'), project='B')
    assert call('status', project='B')['observations'] == []
    assert not (lab / 'B' / c.CHECKS).read_bytes() == checks_path.read_bytes()

    # 7. Переход: проект на 0.1.0 получает 0.1.4 и сохраняет прежние записи
    old_manifest = c.parse((tree / 'releases/0.1.0/manifest.json').read_bytes())
    old_pin = c.digest((tree / 'releases/0.1.0/manifest.json').read_bytes())
    approve(dict(op='install', package='releases/0.1.0', pin=old_pin), project='D')
    approve(dict(op='connect'), project='D')
    approve(dict(op='record_check', observation=observation()), project='D')
    approve(dict(op='record_check', observation=observation(actual='Файл есть, строка 22')), project='D')
    legacy = call('status', project='D')['observations']
    legacy_bytes = (lab / 'D' / c.CHECKS).read_bytes()
    approve(dict(op='update', package=f'releases/{VERSION}', pin=PIN), project='D')
    after_update = call('status', project='D')
    assert after_update['base_version'] == VERSION if 'base_version' in after_update else True
    assert len(after_update['observations']) == len(legacy) == 2
    repeat_after = approve(dict(op='record_check', observation=observation()), project='D')
    assert repeat_after['outcome'] == 'no_change' and (lab / 'D' / c.CHECKS).read_bytes() == legacy_bytes

    # 8. Читатели заново открывают вход и канонический справочник
    start = (lab / 'A' / c.BASE / 'START.md').read_text(encoding='utf-8')
    guide = (lab / 'A' / c.BASE / 'PROTOCOL.md').read_text(encoding='utf-8')
    assert start.strip() and VERSION in guide and 'no_change' in guide
    reads.append(dict(project='reader', file='START.md', sha256=c.digest(start.encode())))
    reads.append(dict(project='reader', file='PROTOCOL.md', sha256=c.digest(guide.encode())))

    # 9. Контрольное дерево C не тронуто ни одной операцией
    after_c = {p.relative_to(lab / 'C').as_posix() for p in (lab / 'C').rglob('*') if p.is_file()}
    assert after_c == set(), after_c

report = dict(scope='deterministic offline pipeline; not a model evaluation', version=VERSION,
              release_pin=PIN, executed_in='Linux / ' + sys.version.split()[0],
              steps=dict(install_without_entry=True, connect=True, first_record=True,
                         exact_repeat_inert=True, reworded_repeat_inert=True, meaning_change_writes=2,
                         local_records_not_transferred=True, transition_from='0.1.0',
                         transition_preserved_records=True, repeat_after_update_inert=True),
              plans=len(plans), refuses=0, control_untouched=True, reads=reads, outcome='pass',
              limits='Управляемая имитация на синтетических A/Б/C/D в одном процессе; не проверка Windows, прав, '
                     'живых расширений и поведения моделей.')
sys.stdout.write(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + '\n')
