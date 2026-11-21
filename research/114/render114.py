"""Страница и отчёт из итоговых наблюдений, без тел исходника, чужих записей и билетов."""
from html import escape

from render import check_rows, counts_line, md_table


def rev(row):
    return f"{row['revision']['from']} → {row['revision']['to']}" if row['revision'] else '—'


def report(spec, red, result, data):
    runs, metrics = result['runs'], data['metrics']
    lines = [
        '# И‑114 — Переносимый черновик только в стенде',
        f"`{spec['branch']}` · {spec['phase']} · {spec['priority']}",
        '## П0–П2. Замысел и исходный контроль',
        f"[Замысел и границы согласия](DESIGN.md) · стратегия `{spec['baseline_strategy']}` · HEAD `{spec['baseline']}`. "
        '[Печать И‑113](../113/REPLAY.json) сверена до изменения стратегии. '
        'Гипотеза: явная новая редакция может пройти независимую проверку и стать черновиком без доступа в действующий профиль.',
        f"[RED.json](RED.json): rc {red['rc']}, {counts_line(red['result']['counts'])}. Базовые формы L2 и L1 валидны; "
        '`promote` ещё отсутствует, рабочий порт возвращает `unknown_operation`. Повтор до кода выполнен из `git archive` базового коммита.',
        f"SHA‑256 [CASES.json](CASES.json) `{spec['casebook_sha256']}`; [test_promotion.py](test_promotion.py) `{spec['test_sha256']}`.",
        '## П3–П5. Проверки и приёмка',
        f"Команда: `python3 {' '.join(spec['command'])}` · {result['os']}, Python {result['python']}. "
        f"Чистая копия — ровно {len(spec['target_inputs'])} заявленных входов. Исходная, контрольная рабочая и принимающая раскладки в каждом случае — новые синтетические каталоги.",
        md_table(('Процесс', 'Обязательные', 'rc', 'basis'), (
            ('П3 · checkout', counts_line(runs['checkout']['counts']), runs['checkout']['rc'], '[CHECKOUT.json](CHECKOUT.json)'),
            ('П4 · чистая копия', counts_line(runs['cleanroom']['counts']), runs['cleanroom']['rc'], '[CLEANROOM.json](CLEANROOM.json)'))),
        f"[ACCEPTANCE.json](ACCEPTANCE.json): **{result['outcome']}** · {counts_line(result['counts'])} по воротам и группам вне объёма.",
        md_table(('Ворота', 'Статус', 'basis', 'criterion'), check_rows(result)),
        '## П6. Находки и пределы',
    ]
    if metrics is None:
        lines.append('Приёмка отклонена; итоговую печать и страницу не обновлять.')
    else:
        first = next(r for r in data['rows'] if r['id'] == 'P01')
        lines.extend([
            f"На прогон {metrics['staged']} завершённых стендовых файлов из {metrics['write_attempts']} попыток создания, "
            'одна попытка — предусмотренный отказ открытия. Все допущенные файлы проверены чтением в другом проекте. '
            'Незапланированных I/O по аудиту не было; защищённые копии и входы прежние.',
            md_table(('Что установлено', 'basis', 'criterion / предел'), (
                ('P01: четыре признака → явное исправление → черновик.', 'P01; test_promotion.py: expected_file, stage_with',
                 f"Поменялась только редакция, не исходник. Ревизия {rev(first)}, одно create; SHA‑256 кандидата `{first['candidate_sha256']}` совпал с журналом."),
                ('Черновик структурно валиден в другом проекте.', 'P01–P07, R09; registry_store.read_registry / profile_history',
                 'Другая L0/L2-раскладка, точные байты L1, пять видов. Черновик не попал в действующие записи; это ещё не имитация развёртывания.'),
                ('Нет пути записи в рабочий профиль.', 'R01–R10; V12; Monitor',
                 'Рабочая цель и попытки обойти билет отказали. Изменение плана не даёт запись; один отказ создания убран без выдачи файла.'),
                ('Известный формальный конфликт не решается сам.', 'V01–V06; P03/P04/P07',
                 'ID, пересечение области и несовместимая пара в L1 стенда не приводят к перезаписи. A4 сохранён, история не выдумывается.'),
                ('Отсутствие маркеров не разрешает перенос.', 'S01–S04; P05; R02',
                 'Проверяем явно предложенные поля. Ссылка на переменную не равна литералу. Смысл, реальные сведения и авторизация за рамками.'),
            )),
            '[PROMOTION.json](PROMOTION.json) — шаги, коды, счётчики и подтверждённые отпечатки синтетических черновиков, без исходных значений.',
            '### Обязательные случаи',
            md_table(('ID', 'basis', 'criterion', 'Наблюдалось', 'Ревизия'),
                     ((r['id'], r['basis'], r['criterion'], ' → '.join(r['steps']), rev(r)) for r in data['rows'])),
        ])
    lines.extend([
        '### Что не выполнялось',
        md_table(('Что', 'Почему'), ((row['what'], row['why']) for row in result['not_run'])),
        '## П7–П9. Печать, повтор и сверка',
        '`python3 -B research/114/run.py` генерирует результаты. `python3 -B research/114/run.py --verify-seal` сверяет '
        '[ZIP / SHA‑256](SEAL.json), [записанный повтор](REPLAY.json), отчёт и страницу без записи. Страница и метаданные печати не входят в ZIP.',
        '[Стратегия v1.16](../STRATEGY.md), [сверка №24](../strategy/SYNC-LOG.md): A1–A4, P0, порядок, критерии, вехи и пригодность прежние. '
        'Владелец отдельно разрешил commit/push И‑114. '
        f"Завершение П9 проверяется по наличию коммита И‑114 в истории `origin/{spec['branch']}`, а не по локальному ZIP. "
        'Ф3 открыта; И‑115/116 не начаты.',
    ])
    return '\n\n'.join(lines) + '\n'


def page(spec, result, data, seal, replay):
    def e(value):
        return escape(str(value))

    m, runs = data['metrics'], result['runs']
    ok = result['outcome'] == 'accepted' and replay['outcome'] == 'ok'
    cards = rows = sample = ''
    if m is not None:
        cards = ''.join(f'<article><span>{e(label)}</span><strong>{e(m[key])}</strong></article>' for key, label in (
            ('staged', 'Готовых файлов на прогон'), ('write_attempts', 'Попыток создания'),
            ('cross_project_readbacks', 'Чтений в другом проекте'), ('io_violations', 'Незапланированных I/O')))
        rows = ''.join(f'<tr><td>{e(r["id"])}</td><td>{e(r["criterion"])}</td>'
                       f'<td><code>{e(" → ".join(r["steps"]))}</code></td><td>{e(rev(r))}</td></tr>' for r in data['rows'])
        first = next(r for r in data['rows'] if r['id'] == 'P01')
        sample = ('<aside><b>P01 · Исправленная редакция</b><p>Четыре категории привязок → ручное исправление → '
                  f'<code>protocol/draft</code> и одна запись журнала ({e(rev(first))}). Читаются в другом тестовом проекте.</p>'
                  f'<p>SHA‑256 черновика<br><code>{e(first["candidate_sha256"])}</code></p></aside>')
    skipped = ''.join(f'<li><b>{e(r["what"])}</b> {e(r["why"])}</li>' for r in result['not_run'])
    return f'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>И‑114 · Черновик в стенде</title><style>
:root {{color-scheme:light;--paper:#faf9f6;--ink:#222c30;--muted:#475b60;--line:#ccd9d8;--brand:#125451;--tint:#e1efeb}}
* {{box-sizing:border-box}} body {{margin:0;background:var(--paper);color:var(--ink);font:1rem/1.55 system-ui,sans-serif}}
header {{background:var(--tint);border-bottom:1px solid var(--line)}} header div,main {{max-width:70rem;margin:auto;padding:1.6rem max(1rem,3vw)}}
h1 {{max-width:19ch;text-wrap:balance;font-size:clamp(2.4rem,6vw,4.9rem);line-height:1;letter-spacing:-.055em;margin:.2em 0}}
h2 {{margin-top:1.6em;line-height:1.15;text-wrap:balance}} a {{color:var(--brand);text-underline-offset:.16em}}
.meta {{color:var(--muted)}} .verdict {{color:{'#125451' if ok else '#972d2d'};font-weight:700}}
.grid {{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(12.5rem,100%),1fr));gap:.7rem}} article,aside,details {{background:#fff;border:1px solid var(--line);border-radius:.5rem;padding:.9rem 1.1rem}}
article strong {{display:block;font-size:1.25rem;margin-top:.25rem}} aside {{margin-top:1rem;border-left:.28rem solid var(--brand)}} aside p {{margin:.35rem 0}}
summary {{cursor:pointer;font-weight:650}} .table {{overflow:auto}} table {{border-collapse:collapse;width:100%;margin-top:.6rem}} td,th {{text-align:left;vertical-align:top;padding:.5rem;border-bottom:1px solid var(--line)}} code {{overflow-wrap:anywhere}} li {{margin:.35rem 0}}
</style></head><body><header><div>
<p class="meta">И‑114 · {e(spec['phase'])} · {e(spec['priority'])}</p><h1>{e(spec['title'])}</h1>
<p class="verdict">{'Проверки П5 приняты на синтетических данных' if ok else 'Проверки не приняты'}</p>
<p>Явная редакция L2 → проверка → новый <code>draft</code> и журнал только во временном каталоге.</p>
</div></header><main>
<div class="grid"><article><a href="CHECKOUT.json">П3 · checkout</a><strong>{e(counts_line(runs['checkout']['counts']))}</strong></article>
<article><a href="CLEANROOM.json">П4 · чистая копия</a><strong>{e(counts_line(runs['cleanroom']['counts']))}</strong></article>
<article><a href="ACCEPTANCE.json">П5 · ворота</a><strong>{e(counts_line(result['counts']))}</strong></article></div>
<h2>Что доказал стенд</h2><div class="grid">{cards}</div>{sample}
<p>Kit не переписывает смысл и не открывает рабочий профиль. Наличие файла и SHA‑256 не означают развёртывание, активацию или разрешение переноса.</p>
<p><a href="../../kit/base/PROMOTION.md">Контракт стенда</a> · <a href="PROMOTION.json">Наблюдения JSON</a></p>
<details><summary>Все обязательные случаи</summary><div class="table"><table><thead><tr><th scope="col">ID</th><th scope="col">Критерий</th><th scope="col">Шаги</th><th scope="col">Ревизия</th></tr></thead><tbody>{rows}</tbody></table></div></details>
<h2>Что не проверялось</h2><ul>{skipped}</ul>
<h2>Печать и повтор</h2><p><a href="{e(seal['file'])}">ZIP</a> · {e(seal['members'])} файлов · {e(seal['bytes'])} байт · <a href="REPLAY.json">повтор: {e(replay['outcome'])}</a></p>
<p>SHA‑256 <code>{e(seal['sha256'])}</code></p>
<p><a href="REPORT.md">Отчёт</a> · <a href="DESIGN.md">Замысел</a> · <a href="../STRATEGY.md">Стратегия</a></p>
<p class="meta">Сверка №24 записана. П9 проверяется по коммиту И‑114 в <code>origin/{e(spec["branch"])}</code>. Ф3 открыта; И‑115/116 не начаты.</p>
</main></body></html>
'''
