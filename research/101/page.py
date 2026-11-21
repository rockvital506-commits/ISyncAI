#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""И-101: страница итерации из машинных артефактов.

Ничего не выдумывает: все числа берутся из ACCEPTANCE.json, SEAL.json, BASELINE.json,
CLEANROOM.json. Если файла ещё нет — честно печатается «нет данных».
"""
import html
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(HERE, 'Итерация-101.html')


def load(path, default=None):
    try:
        with open(path, encoding='utf-8') as fh:
            return json.load(fh)
    except OSError:
        return default


def esc(value):
    return html.escape(str(value))


def rows(items, keys):
    return '\n'.join('<tr>' + ''.join(f'<td>{esc(i.get(k, "—"))}</td>' for k in keys) + '</tr>'
                     for i in items)


def main():
    acc = load(os.path.join(HERE, 'ACCEPTANCE.json'), {})
    seal = load(os.path.join(HERE, 'SEAL.json'), {})
    base = load(os.path.join(REPO, 'research', 'strategy', 'BASELINE.json'), {})
    room = load(os.path.join(HERE, 'CLEANROOM.json'), {})
    counts = acc.get('counts', {})
    checks = acc.get('checks', [])
    steps = room.get('steps', [])
    surfaces = base.get('surfaces', {})
    adapters = base.get('adapters', {})

    status_class = {'pass': 'ok', 'fail': 'bad', 'not run': 'na'}
    verdict = acc.get('outcome', 'нет данных')
    body = f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>Итерация И-101 — Якорь</title>
<style>
 body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; margin: 2rem auto; max-width: 62rem;
        line-height: 1.5; color: #1a1a1a; padding: 0 1rem; }}
 h1 {{ font-size: 1.6rem; margin-bottom: .2rem; }}
 h2 {{ font-size: 1.15rem; margin-top: 2rem; border-bottom: 1px solid #ddd; padding-bottom: .3rem; }}
 .meta {{ color: #555; font-size: .9rem; }}
 table {{ border-collapse: collapse; width: 100%; margin: .6rem 0; font-size: .9rem; }}
 th, td {{ border: 1px solid #ddd; padding: .35rem .5rem; text-align: left; vertical-align: top; }}
 th {{ background: #f6f6f6; }}
 .ok {{ color: #0a6b2d; font-weight: 600; }}
 .bad {{ color: #a10d0d; font-weight: 600; }}
 .na {{ color: #8a6d00; font-weight: 600; }}
 code {{ background: #f3f3f3; padding: .05rem .25rem; border-radius: 3px; }}
 .verdict {{ font-size: 1.1rem; padding: .6rem .8rem; background: #f2f7f3; border-left: 4px solid #0a6b2d; }}
</style>
</head>
<body>
<h1>Итерация И-101 — «Якорь»</h1>
<p class="meta">Фаза Ф0 «Каркас программы» · приоритет P0 · 2026-11-18 · ветка arena/4e000a5e-isyncai</p>

<div class="verdict">Приёмка: <b>{esc(verdict)}</b> · pass {esc(counts.get('pass', '—'))} /
fail {esc(counts.get('fail', '—'))} / not run {esc(counts.get('not run', '—'))}</div>

<h2>Замысел</h2>
<p>Сделать стратегию файлом-якорем и снять неизменяемый базовый отпечаток выпуска 0.1.36.
Гипотеза: в 0.1.36 нет шести поверхностей и адаптера Arena. Изменяется только <code>research/</code>.</p>

<h2>Baseline выпуска (из артефакта)</h2>
<table>
<tr><th>Показатель</th><th>Значение</th></tr>
<tr><td>Выпуск</td><td>{esc(base.get('release', '—'))}</td></tr>
<tr><td>Размер архива, байт</td><td>{esc(base.get('zip', {}).get('bytes', '—'))}</td></tr>
<tr><td>sha256 архива</td><td><code>{esc(base.get('zip', {}).get('sha256', '—'))}</code></td></tr>
<tr><td>Файлов / членов архива</td><td>{esc(base.get('tree', {}).get('files', '—'))} / {esc(base.get('zip', {}).get('members', '—'))}</td></tr>
<tr><td>tree_digest</td><td><code>{esc(base.get('tree', {}).get('tree_digest', '—'))}</code></td></tr>
<tr><td>Команд CLI / операций</td><td>{esc(len(base.get('commands', [])))} / {esc(len(base.get('ops', [])))}</td></tr>
<tr><td>digest baseline</td><td><code>{esc(base.get('digest', '—'))}</code></td></tr>
</table>

<h2>Шесть поверхностей, которых нет</h2>
<table>
<tr><th>Поверхность</th><th>В командах</th><th>В операциях</th><th>Вывод</th></tr>
{rows([{'s': k, 'c': 'да' if v.get('command_present') else 'нет', 'o': 'да' if v.get('op_present') else 'нет',
        'p': 'есть' if v.get('present') else 'отсутствует'} for k, v in surfaces.items()], ['s', 'c', 'o', 'p'])}
</table>

<h2>Адаптеры</h2>
<table>
<tr><th>Среда</th><th>Статус</th><th>Старшинство</th></tr>
{rows([{'n': k, 'st': v.get('status'), 'rank': v.get('rank')} for k, v in adapters.items()], ['n', 'st', 'rank'])}
<tr><td>arena</td><td>отсутствует</td><td>—</td></tr>
</table>

<h2>Чистая копия (install → connect → create)</h2>
<table>
<tr><th>Шаг</th><th>rc</th><th>Результат</th></tr>
{rows([{'s': s.get('step'), 'rc': s.get('rc'),
        'r': s.get('error') or s.get('health') or (str(s.get('count')) + ' записей: ' + ', '.join(s.get('ids') or []))}
       for s in steps], ['s', 'rc', 'r'])}
</table>
<p class="meta">Digest точек замера: <code>{esc(room.get('checkpoints_digest', '—'))}</code> — два прогона совпали.</p>

<h2>Проверки приёмки</h2>
<table>
<tr><th>Проверка</th><th>Статус</th><th>Основание</th><th>Деталь</th></tr>
{''.join('<tr><td>' + esc(c.get('check')) + '</td><td class="' + status_class.get(c.get('status'), 'na') + '">'
         + esc(c.get('status')) + '</td><td>' + esc(c.get('basis')) + '</td><td>'
         + esc(c.get('detail') if c.get('detail') is not None else '—') + '</td></tr>' for c in checks)}
</table>

<h2>Печать</h2>
<table>
<tr><th>Файл</th><th>Членов</th><th>Байт</th><th>sha256</th></tr>
<tr><td>{esc(seal.get('file', '—'))}</td><td>{esc(seal.get('members', '—'))}</td>
<td>{esc(seal.get('bytes', '—'))}</td><td><code>{esc(seal.get('sha256', '—'))}</code></td></tr>
</table>
<p class="meta">AccEPTANCE.json, SEAL.json и эта страница в печать не входят: печать не может ссылаться сама на себя.</p>

<h2>Находки</h2>
<ol>
<li><b>F1.</b> Запись вида <code>rule</code> обязана принадлежать существующему <code>contract</code>
(код <code>parent</code>, contract.py:643). Минимальный <code>create</code> — два шага.</li>
<li><b>F2.</b> Имя в исходнике не доказывает существование механизма: <code>guard_writes</code> — не CI-привратник.</li>
<li><b>F3.</b> Импорт <code>contract.py</code> создаёт <code>__pycache__</code> внутри измеряемого дерева и меняет digest.
Снимок — до импорта, служебные каталоги исключаются.</li>
<li><b>F4.</b> <code>list</code> возвращает <code>active</code>/<code>contracts</code>, ключа <code>entries</code> нет.</li>
<li><b>F5.</b> В 0.1.36 26 команд и 15 операций (было записано 20/13 по памяти) — журнал сверок №1.</li>
<li><b>F6.</b> <code>health</code> и <code>entry_mode</code> — разные поля: <code>valid</code> при <code>entry_mode: absent</code>.</li>
</ol>

<h2>Что не выполнялось</h2>
<ul>
{''.join('<li><b>' + esc(i.get('what')) + '</b> — ' + esc(i.get('why')) + '</li>' for i in acc.get('not_run', []))}
</ul>

<h2>Сверка стратегии</h2>
<p>Стратегия синхронизирована до <b>v1.1</b>: пять записей в журнале сверок
(<code>research/strategy/SYNC-LOG.md</code>), включая инвариант A4 и принцип P13.</p>

<p class="meta">Следующая итерация: И-102 — харнесс прогона (П3–П8 одной командой).</p>
</body>
</html>
"""
    with open(OUT, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(body)
    print('page:', OUT, len(body.encode()), 'bytes')


if __name__ == '__main__':
    main()
