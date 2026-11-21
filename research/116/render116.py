"""Отчёт и статическая страница И-116: пары, декларации, ограничения и пределы."""
from html import escape

from render import check_rows, counts_line, md_table

LIMITS = {'owner_decision_required': 'Решение принадлежит владельцу',
          'system_immutable': 'L0 неизменяем при эксплуатации',
          'system_constraint_not_overridable': 'Системное ограничение нельзя отменить'}
MODES = {'active': 'Действующие записи', 'prospective': 'Потенциальное при рассмотрении черновика'}


def value(x):
    return 'не объявлен' if x is None else str(x)


def primary(data):
    return ((r['id'], p) for r in data['rows'][:6] for p in r['report']['conflicts'])


def outcome(row):
    if row['error'] is not None:
        err = row['error']
        return f"{err['code']} · {err['where']} / {err['details']['reason']}"
    got = row['report']
    return f"{got['outcome']} · пар: {len(got['conflicts'])}"


def cell(side):
    return (f"{side['area']}/{side['id']} ({side['kind']}/{side['state']}), scope {side['scope']}, "
            f"value `{side['value']}`, ранг: {value(side['declared_rank'])}. «{side['text']}»")


def report(spec, red, verdict, data):
    runs, metrics = verdict['runs'], data['metrics']
    lines = [
        '# И‑116 — Конфликт виден, решение за владельцем',
        f"`{spec['branch']}` · {spec['phase']} · {spec['priority']}",
        '## П0–П2. Сверка и RED',
        f"[Замысел и границы](DESIGN.md) · `{spec['baseline_strategy']}` · базовый `{spec['baseline']}`. "
        '[Предыдущая печать](../115/REPLAY.json) подтверждена до правок. Порт A3 уже видит активные пары, но не показывает ранги и не оценивает выбранный черновик.',
        f"[RED.json](RED.json): rc {red['rc']}, {counts_line(red['result']['counts'])}, тот же вывод из `git archive` базы. "
        'Старый A3 вернул X07, контроль равных значений не дал пары; A2 вернул `system_immutable`. Воспроизведены байты P01, отсутствовал новый интерфейс.',
        f"SHA‑256 [корпуса](CASES.json) `{spec['casebook_sha256']}` · [оракула](test_conflict_review.py) `{spec['test_sha256']}`. "
        f"[Манифест](ITERATION.json) закрепляет ещё {len(spec['pinned_inputs'])} источников.",
        '## П3–П5. Два прогона и приёмка',
        f"Запуск: `python3 {' '.join(spec['command'])}` · {verdict['os']}, Python {verdict['python']}. «Чистая копия» — отдельный каталог из {len(spec['target_inputs'])} объявленных входов.",
        md_table(('Процесс', 'Обязательные строки', 'rc', 'basis'), (
            ('П3 · рабочая копия', counts_line(runs['checkout']['counts']), runs['checkout']['rc'], '[CHECKOUT.json](CHECKOUT.json)'),
            ('П4 · чистая копия', counts_line(runs['cleanroom']['counts']), runs['cleanroom']['rc'], '[CLEANROOM.json](CLEANROOM.json)'))),
        f"[ACCEPTANCE.json](ACCEPTANCE.json): **{verdict['outcome']}** · {counts_line(verdict['counts'])} по воротам и отложенным группам.",
        md_table(('Ворота', 'Статус', 'basis', 'criterion'), check_rows(verdict)),
        '## П6. Обе стороны и ограничения',
    ]
    if metrics is None:
        lines.append('Приёмка отклонена. Печать и страница не обновляются.')
    else:
        pairs = tuple(primary(data))
        w = data['control']['p01_exact']
        lines.extend([
            f"{metrics['primary_cases']} конфликтных сценариев дали {metrics['primary_pairs']} пар, одна из них потенциальная. "
            'Отпечатки и объявленные ранги — сведения для просмотра, не порядок исполнения. Даже при rank 90 против 10 в C01 системное ограничение не отменено.',
            md_table(('Случай', 'Ключ / общее scope', 'Первая сторона', 'Вторая сторона', 'Тип и ограничения'), (
                (n, f"{p['key']} / {p['scope']}", cell(p['entries'][0]), cell(p['entries'][1]),
                 MODES[p['comparison']] + ' · ' + '; '.join(LIMITS[x] for x in p['restrictions'])) for n, p in pairs)),
            '### Наблюдения и их пределы',
            md_table(('Факт', 'basis', 'criterion'), (
                ('Не было автоматического выбора или разрешения.','C01–C06; K06; `write_allowed`','Обе записи и исходные формулировки на месте; L0 не является целью предложения, ранги не меняют порядок.'),
                ('Действующее отличается от потенциального.','C06; K04; K10','Без явного выбора черновик не сравнивается; выбранный помечен draft. Неоценённый черновик не скрывает действующие пары.'),
                ('Точный P01 формально не оценён для обоих проектов.','K07/K08; CASES.json; И‑114 и И‑115','Входы L2 разные, байты профиля совпали, `key/value` у P01 нет. Не считать отсутствие пары свидетельством безопасности или готовности к переносу.'),
                ('Поведение при неверных входах и эффекты.','N01–N17; Monitor','17 отказов без частичных результатов и эха, 0 попыток I/O при вызовах, все входы прежние.'),
            )),
            f"Профиль P01: SHA‑256 `{w['profile_sha256']}`; запись `{w['id']}`: `{w['entry_sha256']}`. "
            '[CONFLICTS.json](CONFLICTS.json) содержит только объявленные синтетические формулировки и точные результаты, а не реальные профили, билеты или вывод инструментов.',
            '[Порядок решения](../../kit/base/CONFLICT-REVIEW.md#как-продолжить-после-конфликта-или-расхождения-копий): показать варианты владельцу, не трогать L0, '
            'после решения нужен новый актуальный дифф и отдельное согласие. Расхождение копий L1 проверяется по общей базе, обеим сторонам и ID, не автообъединением историй.',
            '### Корпус',
            md_table(('ID', 'basis', 'criterion', 'Наблюдалось'), ((r['id'], r['basis'], r['criterion'], outcome(r)) for r in data['rows'])),
        ])
    lines.extend([
        '### Не выполнялось',
        md_table(('Что', 'Почему'), ((n['what'], n['why']) for n in verdict['not_run'])),
        '## П7–П9. Печать и сверка',
        '`python3 -B research/116/run.py` воспроизводит результаты. `python3 -B research/116/run.py --verify-seal` проверяет '
        '[архив](SEAL.json), [запись повтора](REPLAY.json), отчёт и страницу без записи. Страница, архив, SEAL и REPLAY не являются членами ZIP.',
        '[Стратегия v1.18](../STRATEGY.md) · [сверка №26](../strategy/SYNC-LOG.md). A1–A4, P0, критерии, порядок, вехи и пригодность прежние. '
        f"Commit/push только И‑116 разрешены отдельно ([основание](DESIGN.md)); П9 подтверждается сверкой коммита с `origin/{spec['branch']}` "
        'и повтором из снимка. Стендовые критерии Ф3 выполнены, рабочий перенос и активация не подтверждены. И‑117 не начата.',
    ])
    return '\n\n'.join(lines) + '\n'


def pair_card(case_id, pair):
    e = escape
    def side_card(r):
        return (f'<div class="side"><h4>{e(r["area"])}/{e(r["id"])}</h4><p class="meta">{e(r["kind"])}/{e(r["state"])}'
                f' · scope <code>{e(r["scope"])}</code></p><p>{e(r["text"])}</p>'
                f'<p>Значение: <code>{e(r["value"])}</code> · ранг: <b>{e(value(r["declared_rank"]))}</b></p></div>')
    limits = ' · '.join(LIMITS[x] for x in pair['restrictions'])
    return (f'<article class="pair"><p class="meta">{e(case_id)} · {e(MODES[pair["comparison"]])}</p>'
            f'<h3><code>{e(pair["key"])}</code> <small>↔ <code>{e(pair["scope"])}</code></small></h3>'
            f'<div class="sides">{"".join(side_card(r) for r in pair["entries"])}</div><p class="limit">{e(limits)}</p></article>')


def page(spec, verdict, observed, seal, replay):
    e = escape
    runs = verdict['runs']
    ok = verdict['outcome'] == 'accepted' and replay['outcome'] == 'ok'
    cards = ''.join(pair_card(n, p) for n, p in primary(observed))
    case_rows = ''.join(f'<tr><th scope="row">{e(r["id"])}</th><td>{e(r["criterion"])}</td><td><code>{e(outcome(r))}</code></td></tr>'
                        for r in observed['rows'])
    deferred = ''.join(f'<li><b>{e(r["what"])}</b> {e(r["why"])}</li>' for r in verdict['not_run'])
    w = observed['control']['p01_exact']
    return f'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>И‑116 · Конфликты без автоматического решения</title><style>
:root {{color-scheme:light;--bg:#f6f7f4;--surface:white;--ink:#182432;--muted:#4e5e67;--line:#d5dfdc;--accent:#126052;--warn:#754521}}
* {{box-sizing:border-box}} body {{margin:0;background:var(--bg);font:1rem/1.55 system-ui,sans-serif;color:var(--ink)}}
header {{background:#e4efe9;border-bottom:1px solid var(--line)}} .wrap,main {{max-width:72rem;margin:auto;padding:1.5rem max(1rem,4vw)}}
h1 {{font-size:clamp(2.65rem,7vw,5rem);line-height:.98;margin:.3em 0 .36em;max-width:17ch;letter-spacing:-.055em;text-wrap:balance}}
h2 {{line-height:1.15;margin:1.65em 0 .55em}} h3,h4 {{margin:.15em 0 .45em;line-height:1.2}} p {{margin:.5em 0}}
a {{color:var(--accent);text-underline-offset:.18em}} .meta,small {{color:var(--muted)}} .status {{color:{'#126052' if ok else '#921f2a'};font-weight:750}}
.metrics,.sides {{display:grid;gap:.75rem;grid-template-columns:repeat(auto-fit,minmax(min(13rem,100%),1fr))}}
.metric,.pair,.note,details {{background:var(--surface);border:1px solid var(--line);border-radius:.75rem;padding:1rem 1.15rem}}
.metric strong {{display:block;margin-top:.3em;font-size:1.12rem}} .pair {{margin:.75rem 0}} .side {{background:#f5f8f6;padding:.8rem .9rem;border-radius:.55rem}}
.limit {{color:var(--warn);font-weight:600}} code {{overflow-wrap:anywhere}} summary {{cursor:pointer;font-weight:650}} .scroll {{overflow:auto}}
table {{border-collapse:collapse;width:100%}} th,td {{border-bottom:1px solid var(--line);padding:.6rem;text-align:left;vertical-align:top}} li {{margin:.4em 0}}
</style></head><body>
<header><div class="wrap"><p class="meta">И‑116 · {e(spec['phase'])} · {e(spec['priority'])}</p>
<h1>{e(spec['title'])}</h1><p class="status">{'Приёмка П5 пройдена на синтетических данных' if ok else 'Приёмка не пройдена'}</p>
<p>Шесть случаев, семь пар. Объявленные ранги видны, но ничего не выбирают и не меняют.</p></div></header>
<main><div class="metrics">
<div class="metric"><a href="CHECKOUT.json">Рабочая копия</a><strong>{e(counts_line(runs['checkout']['counts']))}</strong></div>
<div class="metric"><a href="CLEANROOM.json">Чистая копия</a><strong>{e(counts_line(runs['cleanroom']['counts']))}</strong></div>
<div class="metric"><a href="ACCEPTANCE.json">Ворота и пределы</a><strong>{e(counts_line(verdict['counts']))}</strong></div></div>
<h2>Что видит владелец</h2><p>Первая и вторая стороны показаны в порядке областей, не старшинства. Число ранга — входная декларация, не разрешение.</p>{cards}
<h2>Точный P01 из И‑115</h2>
<div class="note"><b>CLI и документация: не оценён.</b><p>У того же черновика <code>{e(w['id'])}</code> нет key/value. Это не результат проверки смысла текста и не допуск к рабочему переносу.</p>
<p>SHA‑256 профиля <code>{e(w['profile_sha256'])}</code></p></div>
<h2>Проверки и ограничения</h2><details><summary>33 обязательных случая</summary><div class="scroll"><table>
<thead><tr><th scope="col">ID</th><th scope="col">Критерий</th><th scope="col">Наблюдалось</th></tr></thead><tbody>{case_rows}</tbody></table></div></details>
<ul>{deferred}</ul><h2>Печать и повтор</h2>
<p><a href="{e(seal['file'])}">ZIP</a> · {e(str(seal['members']))} членов · {e(str(seal['bytes']))} байт · <a href="REPLAY.json">повтор: {e(replay['outcome'])}</a></p>
<p>SHA‑256 <code>{e(seal['sha256'])}</code></p>
<p><a href="REPORT.md">Отчёт</a> · <a href="CONFLICTS.json">Пары и варианты JSON</a> · <a href="../../kit/base/CONFLICT-REVIEW.md">Контракт и порядок решения</a> · <a href="../STRATEGY.md">Стратегия</a></p>
<p class="meta">Сверка №26. П9 подтверждается по коммиту И‑116 в <code>origin/{e(spec["branch"])}</code> и повтором из его снимка. Рабочий профиль не менялся.</p></main></body></html>
'''
