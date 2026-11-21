"""И-109: человекочитаемые представления принятого диффа и результатов."""
from html import escape
from render import check_rows, counts_line, md_table


def diagnostic(obs):
    if obs['ok']:
        return f"`{obs['outcome']}`"
    error = obs['error']
    schema = error.get('schema')
    return (f"`{error['code']}` · `{error['where']}`" +
            (f" · `{schema['stage']}:{schema['code']}` на `{schema['path']}`" if schema else ''))


def report(spec, cases, checkout, acceptance, plan):
    runs, metrics = acceptance['runs'], plan['metrics']
    lines = [
        '# И‑109 — Дифф до записи: план и отдельный билет',
        f"`{spec['branch']}` · {spec['phase']} · {spec['priority']} · {spec['date']}",
        '## П0–П2. Сверка и замысел',
        f"До начала: `{spec['baseline']}`. [И‑108](../108/ACCEPTANCE.json) приняла карточки, но не давала им права записи. "
        '[Замысел](DESIGN.md) требует проверить точный дифф, отдельное подтверждение и все прочитанные байты до '
        'единственной замены. [Контракт сессии](../../kit/base/OPERATION-PLAN.md) не расширяет матрицу действий И‑107.',
        f"[CASES.json](CASES.json) — {spec['case_counts']['positive']} положительных и {spec['case_counts']['negative']} отрицательных случаев. "
        f"SHA‑256 ожиданий `{spec['casebook_sha256']}`, SHA‑256 [пробы](test_plan.py) `{spec['test_sha256']}`. "
        'До изменений Kit прогон ожидаемо остановился на отсутствии `operation_plan`. '
        'Ожидаемые байты L1 и диагностики не считываются из ответов продукта.',
        '## П3–П5. Два целевых процесса',
        'Из корня: `python3 -B research/109/run.py`. Команда пробы: `python3 -B -I -S -X utf8 research/109/test_plan.py`.',
        md_table(('Процесс', 'Обязательные случаи', 'rc', 'Основание'), (
            ('П3 · checkout', counts_line(runs['checkout']['counts']), runs['checkout']['rc'], '[CHECKOUT.json](CHECKOUT.json)'),
            ('П4 · чистая копия', counts_line(runs['cleanroom']['counts']), runs['cleanroom']['rc'], '[CLEANROOM.json](CLEANROOM.json)'))),
        f"ОС: `{acceptance['host_os']}`. В П4 только {len(spec['target_inputs'])} входов из [ITERATION.json](ITERATION.json). "
        'Каждый случай — отдельное временное рабочее дерево, три физических файла реестров и один писатель. '
        'Преднамеренный дрейф состояния и первая успешная запись перед проверкой повтора создаются до наблюдаемого вызова. '
        'Отказы в нём не засчитывают изменения подготовки. Билеты не сохраняются, согласие только тестовое.',
        f"[ACCEPTANCE.json](ACCEPTANCE.json): **{acceptance['outcome']}** ({counts_line(acceptance['counts'])}; "
        'счётчик ворот и отложенных групп, не число операций).',
        md_table(('Ворота', 'Статус', 'basis', 'criterion'), check_rows(acceptance)),
        '## П6. Наблюдения',
    ]
    if metrics is None:
        lines.append('Приёмка отклонена: не выдаём частичный замер за дифф и не публикуем новую печать.')
    else:
        p = plan['preview']; diff = p['diff']; revisions = diff['revision']
        rows = {r['id']: r['observed'] for r in checkout['result']['rows']}
        positive = rows['P02-confirmed']
        lines += [
            f"**Записей без подтверждения: {metrics['writes_without_confirmation']}** в обязательных случаях. "
            f"{metrics['refused_before_write']} отказов до попытки записи. В одном отдельном испытании была разрешённая подготовка, "
            'но замена отказала (`write_failed`); файл остался прежним и временный файл удалён. '
            'Аудируемые события, фактические замены, байты и метки файлов проверяются раздельно.',
            f"[PLAN.json](PLAN.json) — наблюдавшийся dry-run без живого билета. Показан только `{diff['file']}`, "
            f"ревизия {revisions['from']} → {revisions['to']}. Дифф включает черновое правило, контейнер и локальное решение. "
            'Снимок сжатого исходного JSON без последней LF корректно представлен и не был переписан.',
            md_table(('Реквизит плана', 'Наблюдение'), (
                ('Вход L0', f"`{p['inputs_sha256']['L0']}`"), ('Вход L1 / SHA‑256 до', f"`{diff['before_sha256']}`"),
                ('Вход L2', f"`{p['inputs_sha256']['L2']}`"), ('Будущий L1 / SHA‑256 после', f"`{diff['after_sha256']}`"))),
            f"**Принятый `apply` (`P02-confirmed`).** Подготовленный файл побайтно равен показанному результату, "
            f"итоговый `profile_revision: {positive['profile_revision']}`, `project_revision: {positive['project_revision']}`, "
            f"ID `{positive['entry_id']}`, решений в журнале: {positive['decisions']}. "
            'Замена была одна, L0 и L2 не изменились; `P05-unread-note` отдельно показывает границу прочитанных входов.',
            md_table(('Факт или опровержение', 'basis', 'criterion / предел'), (
                ('План и уточнение не являются подтверждением.', 'P01; P03; P04; N01–N05; N14; N29',
                 'Dry-run ничего не пишет; no_change и missing_params без билета. Отсутствующий, булев, неверный или '
                 'самостоятельно подставленный билет не меняет файлы.'),
                ('Билет принадлежит выдаче, а не строке или экземпляру словаря.', 'N06–N12; N13; P02',
                 'Повтор, чужая сессия, заменённый план, подмена диффа, файла, карточки и типа отклонены. '
                 'Точный JSON можно передать отдельно; это не аутентификация владельца.'),
                ('Актуальность шире одной ревизии или SemVer.', 'N21–N25; P05',
                 'Сверены L0/L1/L2; дрейф даёт stale_plan или stale_revision, конфликт показывает обе записи. '
                 'Посторонняя непрочитанная заметка не инвалидирует план.'),
                ('Карточка не переопределяет границы порта, а сбой не журналируется.', 'N15–N20; N26–N28; P02',
                 'L0 неизменяем, перечень операций прежний, контракт проверяется локально. '
                 'Повтор отказа Linux не доказывает отказоустойчивость при сбое питания или гонках.'),
            )),
            '### Все случаи',
            md_table(('ID', 'basis', 'Наблюдение', 'Изменённые файлы'), (
                (case['id'], case['basis'], diagnostic(rows[case['id']]), ', '.join(rows[case['id']]['changed']) or '—')
                for case in cases)),
        ]
    lines += [
        '### Не выполнялось', md_table(('Работа', 'Почему'), ((r['what'], r['why']) for r in acceptance['not_run'])),
        '## П7–П9. Печать, страница, сверка',
        '[SEAL.json](SEAL.json) фиксирует ZIP с принятыми наблюдениями, примером плана, отчётом и приёмкой. '
        '[REPLAY.json](REPLAY.json) фиксирует сверку с повторной сборкой. `python3 -B research/109/run.py --verify-seal` '
        'проверяет печать и страницу без перезаписи. Размер и SHA‑256 — из сборки, это не подпись.',
        '[Стратегия v1.11](../STRATEGY.md) и [сверка №19](../strategy/SYNC-LOG.md) сохраняют A1–A4, P0, '
        '40 итераций и порядок фаз. Ф2 не закрыта. Историческая печать И‑108 проверяется из `1e6add9` после изменения ориентира.',
        '## Дальше', spec['next'],
    ]
    return '\n\n'.join(lines) + '\n'


def page(spec, acceptance, plan, seal, replay):
    def e(value):
        return escape(str(value))

    ok = acceptance['outcome'] == 'accepted' and replay['outcome'] == 'ok'
    verdict = 'Проверки приняты' if ok else 'Проверки не приняты'
    runs = acceptance['runs']; preview = plan['preview']; metrics = plan['metrics']
    measured = ''
    if preview:
        d = preview['diff']; rev = d['revision']
        measured = (f'<h2>Фраза и дифф одного файла</h2><blockquote>{e(preview["card"]["request"])}</blockquote>'
                    f'<dl><dt>Цель</dt><dd><code>{e(d["file"])}</code></dd>'
                    f'<dt>Ревизия L1</dt><dd>{e(rev["from"])} → {e(rev["to"])}</dd>'
                    f'<dt>SHA‑256 после</dt><dd><code>{e(d["after_sha256"])}</code></dd></dl>'
                    f'<details><summary>Показать точный дифф</summary><pre>{e(d["unified"])}</pre></details>'
                    '<p><a href="PLAN.json">Наблюдавшийся план без билета</a> · '
                    '<a href="../../kit/base/OPERATION-PLAN.md">Контракт сессии</a></p>'
                    f'<h2>Без отдельного подтверждения — без записи</h2>'
                    f'<p>Записей без подтверждения: <strong>{e(metrics["writes_without_confirmation"])}</strong>. '
                    f'Отказов до попытки записи: {e(metrics["refused_before_write"])}. '
                    'Отдельный отказ <code>os.replace</code> не оставил записи, решения или временного файла.</p>')
    skipped = ''.join(f'<li><strong>{e(r["what"])}</strong> {e(r["why"])}</li>' for r in acceptance['not_run'])
    return f'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>И‑109 · План и билет</title><style>
:root {{color-scheme:light;--ink:#222b36;--muted:#52616f;--line:#dce5ec;--wash:#eef4f9;--accent:#204b71}}
* {{box-sizing:border-box}} body {{margin:0;background:#fcfdff;color:var(--ink);font:1rem/1.55 system-ui,sans-serif}}
header {{background:var(--wash);border-bottom:1px solid var(--line)}} header>div,main {{max-width:64rem;margin:auto;padding:1.4rem max(1rem,3vw)}}
h1 {{font-size:clamp(2.05rem,4vw,3.3rem);line-height:1.08;text-wrap:balance;margin:.4em 0}} h2 {{margin-top:1.7em}}
a {{color:var(--accent);text-underline-offset:.19em}} .meta {{color:var(--muted)}} .status {{font-weight:bold;color:{'#1b5e48' if ok else '#963637'}}}
.cards {{display:grid;grid-template-columns:repeat(auto-fit,minmax(13rem,1fr));gap:.65rem}} article {{padding:.8rem 1rem;background:white;border:1px solid var(--line);border-radius:.5rem}} article strong {{display:block}}
blockquote {{margin:.65rem 0;border-left:.24rem solid #91afc6;padding:.2rem .8rem}} dl {{display:grid;grid-template-columns:max-content 1fr;gap:.35rem 1rem}} dt {{font-weight:650}} dd {{margin:0}}
summary {{cursor:pointer;font-weight:bold}} pre {{background:var(--wash);border-radius:.45rem;padding:.75rem;white-space:pre-wrap;overflow-wrap:anywhere}} code {{overflow-wrap:anywhere}}
</style></head><body><header><div><p class="meta">И‑109 · {e(spec['phase'])} · {e(spec['priority'])}</p>
<h1>{e(spec['title'])}</h1><p class="status">{verdict}</p>
<p>Сначала карточка и точный dry-run. Затем отдельное подтверждение и сверка актуальности. При успехе — один файл чернового профиля L1.</p></div></header>
<main><div class="cards">
<article><a href="CHECKOUT.json">П3 · checkout</a><strong>{e(counts_line(runs['checkout']['counts']))}</strong></article>
<article><a href="CLEANROOM.json">П4 · чистая копия</a><strong>{e(counts_line(runs['cleanroom']['counts']))}</strong></article>
<article><a href="ACCEPTANCE.json">П5 · приёмка</a><strong>{e(counts_line(acceptance['counts']))}</strong></article></div>
{measured}
<h2>Не выполнялось</h2><ul>{skipped}</ul>
<h2>Печать и повтор</h2><p><a href="{e(seal['file'])}">Архив с приёмкой</a> · {e(seal['members'])} файлов · {e(seal['bytes'])} байт ·
<a href="REPLAY.json">повтор: {e(replay['outcome'])}</a></p><p>SHA‑256 <code>{e(seal['sha256'])}</code></p>
<p><a href="REPORT.md">Отчёт и критерии</a> · <a href="DESIGN.md">Замысел</a> · <a href="../STRATEGY.md">Стратегия</a></p>
<p class="meta">{e(spec['next'])}</p></main></body></html>
'''
