"""Человекочитаемые свидетельства И-115: два проекта, отдельный контроль, никаких тел правил."""
from html import escape

from render import check_rows, counts_line, md_table

LABELS = {'cli': 'Фикстура CLI', 'docs': 'Фикстура документации'}


def verdict(row):
    return row['outcome'] if row['where'] is None else f"{row['outcome']} · {row['where']} / {row['reason']}"


def state_row(name, variant, r):
    return (LABELS[name], 'Контроль' if variant == 'control' else 'С кандидатом', r['profile_revision'],
            'да' if r['candidate_visible'] else 'нет', 'да' if r['text_verified'] else '—',
            'да' if r['candidate_active'] else 'нет', r['l2_rules'])


def report(spec, red, result, data):
    runs, m = result['runs'], data['metrics']
    lines = [
        '# И‑115 — Один черновик в двух новых проектах',
        f"`{spec['branch']}` · {spec['phase']} · {spec['priority']}",
        '## П0–П2. Сверка и оракул',
        f"[Границы согласия](DESIGN.md) · стратегия `{spec['baseline_strategy']}` · HEAD `{spec['baseline']}`. "
        '[Печать И‑114](../114/REPLAY.json) сверена до правок. Выбран точный кандидат P01, не заново написанный проектный протокол.',
        f"[RED.json](RED.json): rc {red['rc']}, {counts_line(red['result']['counts'])}. На исходном коммите `promote`/`stage` вернули P01, "
        'обе исходные раскладки приняли форму v2; `simulate` ещё отсутствует, рабочий порт возвращает `unknown_operation`. Проба совпала из `git archive`.',
        f"SHA‑256 [CASES.json](CASES.json) `{spec['casebook_sha256']}`; [test_simulation.py](test_simulation.py) `{spec['test_sha256']}`. "
        f"[Манифест](ITERATION.json) также закрепляет {len(spec['pinned_inputs'])} зависимостей по байтам.",
        '## П3–П5. Два прогона и приёмка',
        f"`python3 {' '.join(spec['command'])}` · {result['os']}, Python {result['python']}. "
        f"В чистой копии ровно {len(spec['target_inputs'])} объявленных входов; временные раскладки каждый раз создаются заново.",
        md_table(('Процесс', 'Обязательные', 'rc', 'basis'), (
            ('П3 · checkout', counts_line(runs['checkout']['counts']), runs['checkout']['rc'], '[CHECKOUT.json](CHECKOUT.json)'),
            ('П4 · чистая копия', counts_line(runs['cleanroom']['counts']), runs['cleanroom']['rc'], '[CLEANROOM.json](CLEANROOM.json)'))),
        f"[ACCEPTANCE.json](ACCEPTANCE.json): **{result['outcome']}** · {counts_line(result['counts'])} по воротам и отложенным группам.",
        md_table(('Ворота', 'Статус', 'basis', 'criterion'), check_rows(result)),
        '## П6. Наблюдения и ограничения',
    ]
    if m is None:
        lines.append('Приёмка отклонена; печать и страница не обновляются.')
    else:
        ref = data['reference']
        lines.extend([
            'В контрольной и установленной копии каждой пары одинаковы L0, L2, проектный файл и стартовый вход. Меняются только точные байты L1. '
            'Оба проекта прочитали тот же черновик по ID через настоящий короткий вход Kit, без `apply`, билета, исполнения или смены состояния.',
            md_table(('Проект', 'Вариант', 'Ревизия L1', 'В каталоге', 'Точный текст прочитан', 'В действующих', 'Правил L2'),
                     (state_row(p['fixture'], v, p[v]) for p in ref['projects'] for v in ('control', 'installed'))),
            md_table(('Связанный объект', 'SHA‑256', 'basis'), (
                ('Черновик И‑114 P01', f"`{ref['entry_sha256']}`", 'PROMOTION.json И‑114; test_simulation.py: load_prior'),
                ('Предшествующий профиль', f"`{ref['control_sha256']}`", 'И‑114 diff.before_sha256; CASES.json'),
                ('Профиль и журнал с черновиком', f"`{ref['profile_sha256']}`", 'И‑114 diff.after_sha256; проверены реальные файлы обеих копий'),
            )),
            f"На прогон: успешных проверок двух пар — {m['simulated']} (P01–P03), ожидаемых отказов — {m['refused']}. "
            f"Попыток создания — {m['write_attempts']}, вызовов входа — {m['bootstrap_calls']}, вызовов просмотра — {m['list_calls']}; "
            f"незапланированных обращений — {m['io_violations']}. Счётчики включают негативные пробы. Все временные деревья убраны.",
            md_table(('Факт', 'basis', 'criterion / предел'), (
                ('Короткий вход, не полное предварительное чтение.', 'P01/P03; BootstrapSession.inputs',
                 f"{ref['projects'][0]['installed']['entry_bytes']} байт точки входа, {ref['projects'][0]['installed']['section0_bytes']} байт §0. Другой хвост не меняет свидетельство входа; поздняя побайтная сверка не является чтением инструкций."),
                ('Разные L2, одинаковые байты кандидата.', 'P01–P03; checked_init; N13',
                 'Разные правила и файлы проекта; повтор одного L2 с другим форматированием отклонён. В обоих list активных черновика нет.'),
                ('Хеш записи не подменяет хеш профиля и его происхождение.', 'N04–N12; registry_journal',
                 'Подмена полного профиля, базы, ID, истории, активный объект и замена старого контракта не получают успеха.'),
                ('Две пары обязательны.', 'N18–N21; Monitor и observed_plan',
                 'Отказ чтения или создания во второй паре, либо изменённое наблюдение → simulation_failed без частичного выдаваемого результата.'),
            )),
            '[SIMULATION.json](SIMULATION.json) хранит результаты и отпечатки, не тела, билеты или абсолютные пути.',
            '### Корпус',
            md_table(('ID', 'basis', 'criterion', 'Наблюдалось'),
                     ((r['id'], r['basis'], r['criterion'], verdict(r)) for r in data['rows'])),
        ])
    lines.extend([
        '### Не выполнялось',
        md_table(('Что', 'Почему'), ((row['what'], row['why']) for row in result['not_run'])),
        '## П7–П9. Печать и сверка',
        '`python3 -B research/115/run.py` генерирует результаты. `python3 -B research/115/run.py --verify-seal` сверяет '
        '[архив и SHA‑256](SEAL.json), [повтор](REPLAY.json), отчёт и страницу без записи. Страница и данные о печати не входят в ZIP.',
        '[Стратегия v1.17](../STRATEGY.md), [сверка №25](../strategy/SYNC-LOG.md): A1–A4, P0, порядок, вехи, критерии и пригодность прежние. '
        f"Commit/push только И‑115 разрешены отдельно ([основание](DESIGN.md)); П9 подтверждается сверкой коммита с `origin/{spec['branch']}` "
        'и повтором печати из его снимка. Ф3 остаётся открытой, И‑116 не начата.',
    ])
    return '\n\n'.join(lines) + '\n'


def page(spec, result, data, seal, replay):
    def e(v):
        return escape(str(v))

    ref, m, runs = data['reference'], data['metrics'], result['runs']
    ok = result['outcome'] == 'accepted' and replay['outcome'] == 'ok'
    compare = cases = ''
    if m is not None:
        compare = '<div class="grid">' + ''.join(
            f'<article><p class="eyebrow">{e(x["asset"])}</p><h3>{e(LABELS[x["fixture"]])}</h3>'
            f'<b>Ревизия L1 {e(x["control"]["profile_revision"])} → {e(x["installed"]["profile_revision"])}</b>'
            f'<p>Контроль: черновика нет. С кандидатом: один и тот же черновик и точный текст найдены, в действующих — нет.</p>'
            f'<p>Правил L2: {e(x["installed"]["l2_rules"])}. После просмотра байты прежние.</p></article>' for x in ref['projects']) + '</div>'
        compare += f'<p>SHA‑256 черновика P01<br><code>{e(ref["entry_sha256"])}</code></p>'
        cases = ''.join(f'<tr><td>{e(r["id"])}</td><td>{e(r["criterion"])}</td><td><code>{e(verdict(r))}</code></td></tr>' for r in data['rows'])
    deferred = ''.join(f'<li><b>{e(row["what"])}</b> {e(row["why"])}</li>' for row in result['not_run'])
    return f'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>И‑115 · Имитация в двух проектах</title><style>
:root {{color-scheme:light;--paper:#faf9f4;--ink:#222e40;--muted:#4c5c70;--line:#d2dae5;--brand:#154b76;--tint:#e7eff7}}
* {{box-sizing:border-box}} body {{margin:0;background:var(--paper);color:var(--ink);font:1rem/1.55 system-ui,sans-serif}}
header {{background:var(--tint);border-bottom:1px solid var(--line)}} header div,main {{max-width:70rem;margin:auto;padding:1.6rem max(1rem,3vw)}}
h1 {{max-width:19ch;text-wrap:balance;font-size:clamp(2.4rem,6vw,4.9rem);line-height:1;letter-spacing:-.055em;margin:.2em 0}}
h2 {{margin-top:1.7em;line-height:1.15}} h3 {{margin:.1em 0 .5em}} a {{color:var(--brand);text-underline-offset:.16em}}
.meta,.eyebrow {{color:var(--muted)}} .eyebrow {{font-size:.85rem;margin:0 0 .2em;overflow-wrap:anywhere}}
.verdict {{color:{'#134b6d' if ok else '#952d2d'};font-weight:700}}
.grid {{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(15rem,100%),1fr));gap:.7rem}} article,details {{background:#fff;border:1px solid var(--line);border-radius:.5rem;padding:.95rem 1.1rem}}
article strong {{display:block;font-size:1.25rem;margin-top:.25rem}} summary {{cursor:pointer;font-weight:650}} .table {{overflow:auto}}
table {{border-collapse:collapse;width:100%;margin-top:.6rem}} td,th {{text-align:left;vertical-align:top;padding:.5rem;border-bottom:1px solid var(--line)}} code {{overflow-wrap:anywhere}} li {{margin:.4rem 0}}
</style></head><body><header><div>
<p class="meta">И‑115 · {e(spec['phase'])} · {e(spec['priority'])}</p><h1>{e(spec['title'])}</h1>
<p class="verdict">{'Проверки П5 приняты на синтетических данных' if ok else 'Проверки не приняты'}</p>
<p>Те же байты L1, две разные раскладки, контроль без кандидата. Чтение, не активация.</p>
</div></header><main>
<div class="grid"><article><a href="CHECKOUT.json">П3 · checkout</a><strong>{e(counts_line(runs['checkout']['counts']))}</strong></article>
<article><a href="CLEANROOM.json">П4 · чистая копия</a><strong>{e(counts_line(runs['cleanroom']['counts']))}</strong></article>
<article><a href="ACCEPTANCE.json">П5 · ворота</a><strong>{e(counts_line(result['counts']))}</strong></article></div>
<h2>Две пары свежих раскладок</h2>{compare}
<p><a href="../../kit/base/SIMULATION.md">Контракт имитации</a> · <a href="SIMULATION.json">Наблюдения JSON</a></p>
<details><summary>Все обязательные случаи</summary><div class="table"><table><thead><tr><th scope="col">ID</th><th scope="col">Критерий</th><th scope="col">Наблюдалось</th></tr></thead><tbody>{cases}</tbody></table></div></details>
<h2>Что не проверялось</h2><ul>{deferred}</ul>
<h2>Печать и повтор</h2><p><a href="{e(seal['file'])}">ZIP</a> · {e(seal['members'])} файлов · {e(seal['bytes'])} байт · <a href="REPLAY.json">повтор: {e(replay['outcome'])}</a></p>
<p>SHA‑256 <code>{e(seal['sha256'])}</code></p>
<p><a href="REPORT.md">Отчёт</a> · <a href="DESIGN.md">Замысел</a> · <a href="../STRATEGY.md">Стратегия</a></p>
<p class="meta">Сверка №25 записана. П9 подтверждается по коммиту И‑115 в <code>origin/{e(spec['branch'])}</code> и повтором из его снимка. Ф3 открыта; И‑116 не начата.</p>
</main></body></html>
'''
