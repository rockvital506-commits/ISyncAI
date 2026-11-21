"""Отчёт и страница из принятой разметки; значения входов не выводятся."""
from html import escape

from render import check_rows, counts_line, md_table

LABELS = {'no_markers': 'Нет известных признаков', 'project_specific': 'Проектная привязка',
          'possible_secret': 'Возможный секрет', 'invalid_input': 'Неверный вход'}


def observed(row):
    return row.get('code') or '; '.join(f"{f['field']} · {f['category']}:{f['code']}" for f in row['findings']) or '—'


def report(spec, red, result, data):
    runs, m = result['runs'], data['metrics']
    lines = [
        '# И‑113 — Таксономия и признаки проектной специфики',
        f"`{spec['branch']}` · {spec['phase']} · {spec['priority']}",
        '## П0–П2. Замысел и исходный контроль',
        f"Основание: стратегия `{spec['baseline_strategy']}`, Ф3 и R9; HEAD `{spec['baseline']}`. [И‑112](../112/REPLAY.json) сверена до правок. "
        '[DESIGN.md](DESIGN.md) фиксирует выбор одного объекта L2 и явно переданных подсказок вместо сканирования, автоматического переписывания или переноса.',
        f"[RED.json](RED.json): rc {red['rc']}, {counts_line(red['result']['counts'])}. Общая причина — нет детектора. "
        'S01 проходит исходную валидацию формы v2; считать это проверкой буквального секрета было бы подменой проверки. '
        'Исходный контроль совпал в checkout и копии из `git archive` базового коммита. Входы тестов синтетические.',
        f"SHA‑256 [CASES.json](CASES.json) `{spec['casebook_sha256']}`; [test_specificity.py](test_specificity.py) `{spec['test_sha256']}`.",
        '## П3–П5. Два прогона и приёмка',
        f"Целевая команда: `python3 {' '.join(spec['command'])}`; стенд: {result['os']}, Python {result['python']}. "
        'Чистая копия — только шесть заявленных входов; без существующих реестров, `.git`, исходного проекта, донора и ISAI.',
        md_table(('Процесс', 'Обязательные случаи', 'rc', 'basis'), (
            ('П3 · checkout', counts_line(runs['checkout']['counts']), runs['checkout']['rc'], '[CHECKOUT.json](CHECKOUT.json)'),
            ('П4 · чистая копия', counts_line(runs['cleanroom']['counts']), runs['cleanroom']['rc'], '[CLEANROOM.json](CLEANROOM.json)'))),
        f"[ACCEPTANCE.json](ACCEPTANCE.json): **{result['outcome']}** (П5). {counts_line(result['counts'])} по воротам и отложенным группам.",
        md_table(('Ворота', 'Статус', 'basis', 'criterion'), check_rows(result)),
        '## П6. Наблюдения и ограничения',
    ]
    if m is None:
        lines.append('Приёмка отклонена; разметка не считается подтверждённой, печать не обновляется.')
    else:
        out = m['outcomes']
        lines.extend([
            f"{m['valid_entries']} валидных записей размечены верно (порог — не менее 8), ещё {out['invalid_input']} контролей неверного входа. "
            f"Из валидных: {out['project_specific']} проектных привязок, {out['possible_secret']} возможных секретов и {out['no_markers']} случаев без известных маркеров. "
            f"На процесс {m['calls']} вызовов с повтором в переставленном контексте, {m['io_events']} аудируемых попыток доступа. "
            'Входы не изменились, логов и значений совпадений нет. Это наблюдение о вызовах пробы, а не гарантия безопасности произвольного кода.',
            md_table(('Подтвердилось', 'basis', 'criterion / предел'), (
                ('Вид не решает вопрос о переносимости.', 'F01–F05, D01–D10; PROJECT-SPECIFICITY.md',
                 'Пять видов v2. Отдельно смысл, применимость, ID/parent, состояние и исходный контекст. Никакой автоматической перепривязки.'),
                ('Пути и имена различаются.', 'D01–D10, F03, N01–N04',
                 'Локальные формы пути и явные префиксы; нормализация имён с границей, не подстрочный поиск. URL и неизвестное имя не объявлены машинным путём.'),
                ('Буквальное значение не равно ссылке на переменную.', 'S01–S07, F04, N03',
                 'Срабатывания на присвоение, пару ключ/значение, заголовок PEM и Bearer. Вывод — только принадлежность поля и код; не подтверждение настоящего ключа.'),
                ('Неверная форма не выдаётся за чистую запись.', 'E01–E09',
                 'Отказы по части записи и контексту без эха; общего анализа PII и скрытых секретов здесь нет.'),
            )),
            '[CLASSIFICATION.json](CLASSIFICATION.json) — наблюдённая классификация всех случаев, без текстов, подсказок и совпавших значений.',
            '### Корпус: результат и критерий',
            md_table(('ID', 'basis', 'criterion', 'Исход', 'Поле и код'),
                     ((r['id'], r['basis'], r['criterion'], r['outcome'], observed(r)) for r in data['rows'])),
        ])
    lines.extend([
        '### Не выполнялось',
        md_table(('Что', 'Почему'), ((r['what'], r['why']) for r in result['not_run'])),
        '## П7–П9. Печать, повтор и сверка',
        '`python3 -B research/113/run.py` генерирует результаты. `python3 -B research/113/run.py --verify-seal` проверяет '
        '[архив/манифест](SEAL.json), [повтор](REPLAY.json), отчёт и страницу без записи. Страница и метаданные самой печати не входят в ZIP.',
        '[Стратегия v1.15](../STRATEGY.md), [сверка №23](../strategy/SYNC-LOG.md): подтверждён узкий детектор, не перенос. '
        'A1–A4, P0, порядок и пригодность не менялись. Владелец отдельно разрешил commit/push И‑113. '
        f"Завершение П9 проверяется по наличию коммита И‑113 в истории `origin/{spec['branch']}`, а не по локальному ZIP. "
        'Ф3 остаётся открытой; И‑114 не начата.',
    ])
    return '\n\n'.join(lines) + '\n'


def page(spec, result, data, seal, replay):
    def e(v):
        return escape(str(v))

    m = data['metrics']
    runs = result['runs']
    ok = result['outcome'] == 'accepted' and replay['outcome'] == 'ok'
    outcomes = rows = ''
    if m is not None:
        outcomes = ''.join(f'<article><span>{e(label)}</span><strong>{e(m["outcomes"].get(k, 0))}</strong></article>'
                           for k, label in LABELS.items())
        rows = ''.join(f'<tr><td>{e(r["id"])}</td><td>{e(r["criterion"])}</td><td><code>{e(r["outcome"])}</code>'
                       f'<br>{e(observed(r))}</td></tr>' for r in data['rows'])
    skipped = ''.join(f'<li><b>{e(r["what"])}</b> {e(r["why"])}</li>' for r in result['not_run'])
    return f'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>И‑113 · Проектная специфика</title><style>
:root {{color-scheme:light;--bg:#fbfaf8;--ink:#202825;--muted:#50615a;--line:#d3ded8;--accent:#0b6351;--tint:#e5f3ed}}
* {{box-sizing:border-box}} body {{margin:0;background:var(--bg);color:var(--ink);font:1rem/1.55 system-ui,sans-serif}}
header {{background:var(--tint);border-bottom:1px solid var(--line)}} header>div,main {{max-width:66rem;margin:auto;padding:1.5rem max(1rem,3vw)}}
h1 {{font-size:clamp(2.4rem,6vw,4.6rem);line-height:1.01;letter-spacing:-.05em;margin:.2em 0;max-width:18ch;text-wrap:balance}}
h2 {{margin:1.7em 0 .55em;line-height:1.15}} a {{color:var(--accent);text-underline-offset:.17em}}
.meta {{color:var(--muted)}} .verdict {{color:{'#145541' if ok else '#972d2d'};font-weight:700}}
.grid {{display:grid;grid-template-columns:repeat(auto-fit,minmax(12rem,1fr));gap:.65rem}} article,details {{background:#fff;border:1px solid var(--line);border-radius:.6rem;padding:.8rem 1rem}}
article strong {{display:block;font-size:1.35rem}} table {{width:100%;border-collapse:collapse;margin-top:.75rem}} th,td {{padding:.5rem .65rem;text-align:left;vertical-align:top;border-bottom:1px solid var(--line)}}
summary {{cursor:pointer;font-weight:650}} code {{overflow-wrap:anywhere}} li {{margin:.35rem 0}}
</style></head><body><header><div>
<p class="meta">И‑113 · {e(spec['phase'])} · {e(spec['priority'])}</p><h1>{e(spec['title'])}</h1>
<p class="verdict">{'Проверки П5 приняты на синтетических данных' if ok else 'Проверки не приняты'}</p>
<p>Одна запись L2, четыре категории признаков. Никакого сканирования проекта или записи в L1.</p></div></header><main>
<div class="grid"><article><a href="CHECKOUT.json">П3 · checkout</a><strong>{e(counts_line(runs['checkout']['counts']))}</strong></article>
<article><a href="CLEANROOM.json">П4 · чистая копия</a><strong>{e(counts_line(runs['cleanroom']['counts']))}</strong></article>
<article><a href="ACCEPTANCE.json">П5 · ворота</a><strong>{e(counts_line(result['counts']))}</strong></article></div>
<h2>Что показал корпус</h2><div class="grid">{outcomes}</div>
<p>«Нет известных признаков» не означает «можно переносить». Детектор возвращает только поле и код, без найденных значений.</p>
<p><a href="../../kit/base/PROJECT-SPECIFICITY.md">Таксономия и интерфейс</a> · <a href="CLASSIFICATION.json">Разметка JSON</a></p>
<details><summary>Обязательные случаи и результаты</summary><table><thead><tr><th>ID</th><th>Критерий</th><th>Наблюдалось</th></tr></thead><tbody>{rows}</tbody></table></details>
<h2>Что не проверялось</h2><ul>{skipped}</ul>
<h2>Печать и повтор</h2><p><a href="{e(seal['file'])}">ZIP</a> · {e(seal['members'])} файлов · {e(seal['bytes'])} байт · <a href="REPLAY.json">повтор: {e(replay['outcome'])}</a></p>
<p>SHA‑256 <code>{e(seal['sha256'])}</code></p>
<p><a href="REPORT.md">Отчёт</a> · <a href="DESIGN.md">Замысел</a> · <a href="../STRATEGY.md">Стратегия</a></p>
<p class="meta">Сверка №23 записана. П9 проверяется по коммиту И‑113 в <code>origin/{e(spec["branch"])}</code>. Ф3 остаётся открытой; И‑114 не начата.</p>
</main></body></html>
'''
