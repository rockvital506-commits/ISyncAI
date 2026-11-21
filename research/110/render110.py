"""Отчёт и страница И-110 из принятых наблюдений, без временных адресов и билетов."""
from html import escape

from render import check_rows, counts_line, md_table

OP_NAMES = {'create': 'Регистрация', 'list': 'Просмотр', 'edit': 'Правка текста', 'suspend': 'Приостановка',
            'resume': 'Возобновление', 'revoke': 'Отмена', 'delete': 'Удаление'}


def describe(obs):
    if obs['ok']:
        return f"`{obs['outcome']}`"
    error = obs['error']
    schema = error.get('schema')
    return f"`{error['code']}` · `{error['where']}`" + (f" · `{schema['code']}`" if schema else '')


def matrix_rows(data):
    def display(cell):
        if cell['outcome'] == 'listed':
            return 'прочитан каталог, 0 замен'
        before, after = cell['revision']
        return f"{before} → {after} · {cell['state'] or 'запись удалена'}"
    return [(f'{name} · {op}', display(data['matrix'][op]['L1']), display(data['matrix'][op]['L2']))
            for op, name in OP_NAMES.items()]


def report(spec, cases, red, checkout, acceptance, data):
    runs = acceptance['runs']; metrics = data['metrics']
    lines = [
        '# И‑110 — Семь действий в L1 и L2: точный дифф и история',
        f"`{spec['branch']}` · {spec['phase']} · {spec['priority']} · {spec['date']}",
        '## П0–П2. Сверка и замысел',
        f"До начала: `{spec['baseline']}`. [И‑109](../109/ACCEPTANCE.json) доказала план для чернового правила L1. "
        '[DESIGN.md](DESIGN.md) расширяет исполнение до 7×2 и описывает журнал, в котором редактирование или purge '
        'не ломают раннее решение `create`. A1–A4, порядок фаз и критерий стратегии не изменились.',
        f"[П2](CASES.json): {spec['case_counts']['positive']} положительных и {spec['case_counts']['negative']} отрицательных случаев. "
        f"До правок Kit [RED.json](RED.json): {counts_line(red['counts'])}, rc {red['rc']}. "
        f"SHA‑256 корпуса `{spec['casebook_sha256']}`, SHA‑256 [пробы](test_actions.py) `{spec['test_sha256']}`. "
        'Ожидаемые диагностики, дифф и будущие файлы построены по фикстурам, а не по ответам Kit.',
        '## П3–П5. Два целевых процесса',
        '`python3 -B research/110/run.py` из корня. Проба: `python3 -B -I -S -X utf8 research/110/test_actions.py`.',
        md_table(('Процесс', 'Обязательные случаи', 'rc', 'basis'), (
            ('П3 · checkout', counts_line(runs['checkout']['counts']), runs['checkout']['rc'], '[CHECKOUT.json](CHECKOUT.json)'),
            ('П4 · чистая копия', counts_line(runs['cleanroom']['counts']), runs['cleanroom']['rc'], '[CLEANROOM.json](CLEANROOM.json)'))),
        f"ОС: `{acceptance['host_os']}`. П4 содержит только {len(spec['target_inputs'])} входов из [ITERATION.json](ITERATION.json). "
        'В обоих процессах используются временные рабочие деревья с тремя файлами реестров, один писатель, синтетическое согласие. '
        'Сравниваются байты, состав дерева, метки обычных файлов, вызовы замены и аудируемые попытки записи. '
        'Преднамеренный дрейф, установка фикстуры и первая запись перед тестом повтора не входят в замер отказа.',
        f"[ACCEPTANCE.json](ACCEPTANCE.json): **{acceptance['outcome']}**, {counts_line(acceptance['counts'])}. "
        'Это счётчик ворот и отложенных групп, не число случаев.',
        md_table(('Ворота', 'Статус', 'basis', 'criterion'), check_rows(acceptance)),
        '## П6. Что подтверждено',
    ]
    if metrics is None:
        lines.append('Измерение отклонено: приёмка ячеек и новая печать не публикуются.')
    else:
        rows = {r['id']: r['observed'] for r in checkout['result']['rows']}
        lines += [
            '**7 действий × 2 области.** Каждой ячейке соответствует обязательный случай `M-<действие>-<область>` '
            'и исполненный вызов через карточку. [ACTIONS.json](ACTIONS.json) — наблюдавшаяся матрица, два диффа без билетов и две цепочки.',
            md_table(('Действие', 'L1', 'L2'), matrix_rows(data)),
            f"Записей без подтверждения: **{metrics['writes_without_confirmation']}**. "
            f"В измеренных вызовах — {metrics['successful_replacements']} успешных замен, {metrics['read_only_lists']} чтения `list`, "
            f"{metrics['no_change']} точных повторов, {metrics['refused_before_write']} отказа до попытки записи и "
            f"{metrics['failed_replacements']} отказ замены без изменения реестра и истории. "
            'Положительные случаи цепочек включают несколько отдельных согласований; один шаг всегда равен одной замене.',
            md_table(('Факт', 'basis (ID в CHECKOUT/CLEANROOM)', 'criterion / предел'), (
                ('Фраза и просмотр не пишут.', 'M-list-L1/L2; P-text-L1/L2; P-missing; P-repeat-*; M-edit-L1/L2',
                 'Каталог не содержит тел, явный ID допускает просмотр одного текста. Родитель в приостановке исключает активного ребёнка из фильтра. '
                 'Уточнение — до чтения, 3 вопроса при 8 пропусках. Глагол в теле правки остаётся текстом.'),
                ('Отмена не удаляет запись. Purge — самостоятельное согласие.', 'M-revoke-L1/L2; M-delete-L1/L2; N03–N06; N28–N29',
                 'Отмена сохраняет текст. Запись удаляется из текущего файла только из revoked, по билету и точному allow_delete=True; '
                 'дети не удаляются каскадом. История содержит ID и отпечатки, не прежнее тело; Git/копии не стираются.'),
                ('Журнал и реестр меняются вместе; прежние решения не исчезают.', 'P-legacy-edit; P-chain-L1/L2; N21–N23; N30',
                 'Известный create формата 1 сохранён, неизвестная история голого v2 не выдумана. L1 4→8, L2 7→13 в разных деревьях. '
                 'Итог и цепочка проверены независимо. Повреждённая история и заново предъявленный удалённый ID отклонены.'),
                ('Допуски и свежесть проверяются независимо от реквизитов.', 'N01–N02; N11–N20; N25–N27; N31–N33',
                 'Перечитаны L0/L1/L2, SHA и ревизия цели. Соседний ID/родитель не разрешается, L0 не меняется. '
                 'При конфликте будущего resume видны обе стороны. Согласие не удостоверяет владельца и не выдаёт прав ОС.'),
            )),
            '### Все обязательные случаи',
            md_table(('ID', 'basis · фикстура', 'Наблюдение', 'criterion · изменённые файлы'), (
                (case['id'], case['basis'], describe(rows[case['id']]), ', '.join(rows[case['id']]['changed']) or '—') for case in cases)),
        ]
    lines += [
        '### Не выполнялось', md_table(('Что', 'Почему'), ((x['what'], x['why']) for x in acceptance['not_run'])),
        '## П7–П9. Печать, страница и сверка',
        '[SEAL.json](SEAL.json) — размер и SHA‑256 сборки, не подпись. [REPLAY.json](REPLAY.json) — сравнение с сохранённым ZIP. '
        '`python3 -B research/110/run.py --verify-seal` проверяет их и страницу без перезаписи. '
        'Старые печати не обновляются вслед за изменением Kit; И‑109 проверяется на `57d7021`.',
        '[Стратегия v1.12](../STRATEGY.md) · [сверка №20](../strategy/SYNC-LOG.md). Ф2 остаётся открытой. '
        'Исполненные операции над реестром не доказывают соблюдение правил моделью или пригодность Kit в живой среде.',
        '## Дальше', spec['next'],
    ]
    return '\n\n'.join(lines) + '\n'


def page(spec, acceptance, data, seal, replay):
    def e(x):
        return escape(str(x))

    def table(headers, rows):
        head = ''.join(f'<th scope="col">{e(h)}</th>' for h in headers)
        body = ''.join('<tr>' + ''.join(f'<td>{e(c)}</td>' for c in row) + '</tr>' for row in rows)
        return f'<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'

    ok = acceptance['outcome'] == 'accepted' and replay['outcome'] == 'ok'
    verdict = 'Проверки приняты на фикстурах' if ok else 'Проверки не приняты'
    runs = acceptance['runs']; metrics = data['metrics']
    details = ''
    if metrics is not None:
        for i, plan in data['previews'].items():
            d = plan['diff']; r = d['revision']
            details += (f'<details><summary>{e(i)} · {r["from"]} → {r["to"]}</summary>'
                        f'<blockquote>{e(plan["card"]["request"])}</blockquote><p><code>{e(d["file"])}</code><br>'
                        f'SHA‑256 после: <code>{e(d["after_sha256"])}</code></p><pre>{e(d["unified"])}</pre></details>')
    skipped = ''.join(f'<li><strong>{e(r["what"])}</strong> {e(r["why"])}</li>' for r in acceptance['not_run'])
    return f'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>И‑110 · Манипуляции в L1 и L2</title><style>
:root {{color-scheme:light;--ink:#14233a;--muted:#4a5b70;--line:#d7e2e9;--wash:#edf5f7;--accent:#165b60}}
* {{box-sizing:border-box}} body {{margin:0;background:#fcfdfe;color:var(--ink);font:1rem/1.56 system-ui,sans-serif}}
header {{background:var(--wash);border-bottom:1px solid var(--line)}} header>div,main {{max-width:65rem;margin:auto;padding:1.5rem max(1rem,3vw)}}
h1 {{font-size:clamp(2rem,4.5vw,3.45rem);line-height:1.1;text-wrap:balance;margin:.25em 0}} h2 {{margin:1.75rem 0 .6rem}}
.meta {{color:var(--muted)}} .verdict {{font-weight:720;color:{'#15574b' if ok else '#982f36'}}} a {{color:var(--accent);text-underline-offset:.18em}}
.cards {{display:grid;grid-template-columns:repeat(auto-fit,minmax(13rem,1fr));gap:.75rem}}
article,details {{background:white;padding:.8rem 1rem;border:1px solid var(--line);border-radius:.45rem}} article strong {{display:block}} details {{margin:.6rem 0}}
table {{width:100%;border-collapse:collapse;text-align:left}} td,th {{padding:.45rem .65rem;border-bottom:1px solid var(--line);vertical-align:top}} th {{background:var(--wash)}}
summary {{cursor:pointer;font-weight:650}} blockquote {{margin:.7rem 0;border-left:3px solid var(--line);padding:0 .7rem}}
pre {{padding:.85rem;background:var(--wash);white-space:pre-wrap}} pre,code {{overflow-wrap:anywhere}} li {{margin:.4rem 0}}
</style></head><body><header><div>
<p class="meta">И‑110 · {e(spec['phase'])} · {e(spec['priority'])} · {e(spec['date'])}</p>
<h1>{e(spec['title'])}</h1><p class="verdict">{verdict}</p>
<p>Просмотр — без записи. Мутация — только после отдельного подтверждения точного диффа. Изменение, ревизия и решение сохраняются вместе.</p>
</div></header><main>
<div class="cards"><article><a href="CHECKOUT.json">П3 · checkout</a><strong>{e(counts_line(runs['checkout']['counts']))}</strong></article>
<article><a href="CLEANROOM.json">П4 · чистая копия</a><strong>{e(counts_line(runs['cleanroom']['counts']))}</strong></article>
<article><a href="ACCEPTANCE.json">П5 · приёмка</a><strong>{e(counts_line(acceptance['counts']))}</strong></article></div>
<h2>Матрица исполненных действий</h2>{table(('Действие', 'L1 · профиль', 'L2 · проект'), matrix_rows(data)) if metrics else ''}
<p>Записей без подтверждения: <strong>{e(metrics['writes_without_confirmation']) if metrics else '—'}</strong>. L0 неизменён.</p>
<h2>Отмена и физическое удаление</h2><p>Отмена оставляет запись и текст. Удаление после отмены требует своего согласия помимо билета на дифф.
Затронут только текущий реестр, а не Git и не резервные копии. Локальный журнал сохраняет ID и отпечатки решений.</p>
<h2>Два точных диффа</h2><p>Синтетические примеры без билетов · <a href="ACTIONS.json">наблюдения и цепочки</a>.</p>{details}
<h2>Не выполнялось</h2><ul>{skipped}</ul>
<h2>Печать и повтор</h2><p><a href="{e(seal['file'])}">ZIP с приёмкой</a> · {e(seal['members'])} файлов · {e(seal['bytes'])} байт ·
<a href="REPLAY.json">повтор: {e(replay['outcome'])}</a></p><p>SHA‑256 <code>{e(seal['sha256'])}</code></p>
<p><a href="REPORT.md">Отчёт и критерии</a> · <a href="DESIGN.md">Замысел</a> · <a href="../STRATEGY.md">Стратегия</a></p>
<p class="meta">{e(spec['next'])}</p></main></body></html>
'''
