"""Чтение матрицы И-121: отчёт и самостоятельная статическая страница."""
from html import escape

from render import check_rows, counts_line, md_table

_ORDER = ('arena','kilo','copilot','claude','cursor','antigravity')
_STAGES = (('presence','Наличие в пробе'),('detected','Обнаружение'),('read','Чтение'),('applied','Применение'),('repeat','Повторяемость'))
_GAP = {'entry':'Вход и версия', 'priority':'Старшинство', 'copy_boundary':'Граница копии/PR', 'foreign_entry':'Чужой вход',
        'single_registry':'Один реестр', 'read_apply_repeat':'Чтение и применение', 'context_budget':'Контекст', 'scope':'Причина отсрочки'}


def report(spec, book, red, verdict, doc):
    runs = verdict['runs']; m = verdict['summary']; ctl = spec['expected_control']
    lines = [
        '# И‑121 — Матрица входов и пробелов',
        f"`{spec['branch']}` · {spec['phase']} · {spec['priority']}",
        '## П0–П2. Границы и RED',
        f"[Замысел](DESIGN.md) · v1.22 · `{spec['baseline']}`. Fetch совпал; [печать И‑120](../120/REPLAY.json) проверена без записи. Только локальные входы, без подключения клиентов.",
        f"[RED](RED.json): rc {red['rc']}, {counts_line(red['result']['counts'])}; результат побайтно совпал с базовым снимком. "
        f"[Корпус](CASES.json) `{spec['casebook_sha256']}` и [оракул](test_surfaces.py) `{spec['test_sha256']}` закреплены до матрицы и валидатора.",
        '## П3–П5. Два офлайн-прогона',
        f"`python3 {' '.join(spec['command'])}` · {verdict['os']}, Python {verdict['python']}. В чистой копии только {len(spec['target_inputs'])} входов.",
        md_table(('Процесс','Случаи','rc','basis'), (
            ('П3 · рабочая копия',counts_line(runs['checkout']['counts']),runs['checkout']['rc'],'[CHECKOUT.json](CHECKOUT.json)'),
            ('П4 · чистая копия',counts_line(runs['cleanroom']['counts']),runs['cleanroom']['rc'],'[CLEANROOM.json](CLEANROOM.json)'))),
        f"[ACCEPTANCE.json](ACCEPTANCE.json): **{verdict['outcome']}** · {counts_line(verdict['counts'])} по воротам и отложенным группам.",
        md_table(('Ворота','Статус','basis','criterion'),check_rows(verdict)),
        '## П6. Матрица и предел вывода',
    ]
    if not m:
        lines.append('Приёмка отклонена; новая печать и страница не создаются.')
    else:
        env = doc['environments']
        lines.extend([
            f"[SURFACES.json](SURFACES.json): {m['by_status']['candidate']} кандидата, {m['by_status']['stub']} заглушки, {m['entry_candidates']} кандидатов входа. "
            f"{m['client_runs']} клиентских запусков; {m['by_coverage']['not run']} стадий `not run`, {m['by_coverage']['out_of_scope']} вне области. "
            'Реальные версия и режим не наблюдались. Windows 11 / VS Code 1.146 — план, не измерение. '
            'Ручной кандидат для целевых сред: первый согласованный запрос с явным `kit/base/entry.txt → kit/base/START.md §0`; не обещание автообнаружения.',
            md_table(('Среда','status','Вход-кандидат','Старшинство / что не трогаем'), (
                (env[k]['target']['surface'],f"`{env[k]['status']}`",', '.join(f'`{n}`' for n in env[k]['entry']['paths']) or env[k]['stub_reason'],
                 ('Победитель не установлен. ' if env[k]['status']=='candidate' else 'Вне пробы. ')+', '.join(env[k]['unchanged'])) for k in _ORDER)),
            md_table(('Проверка / вывод','basis','criterion'), (
                ('Copilot, 0.1.36: инвентарь 3/5, текст отчёта 3/4.',
                 '[Инвентарь](../strategy/BASELINE.json) из печати И‑101; [повтор](../102/BASELINE.json); [отчёт](../101/REPORT.md)',
                 'Обе записи неизменны. Для исторического значения используем структурную запись; причина разночтения не установлена. Nearest wins у цели — гипотеза.'),
                ('Arena отсутствовала у донора, сейчас кандидат.', '[И‑101: шаг 7](../101/CLEANROOM.json); Ф5',
                 '`adapter_unknown`, rc2 — только ответ 0.1.36, не проба обнаружения текущим клиентом.'),
                (f"Окно 25–30% — цель Kit; 4096 B — предел локального §0, в B01 прочитано {ctl['start_section_observed_bytes']} B §0.",
                 'P8; [И‑112 B01/S05](../112/BOOTSTRAP.json)', 'Ни одна величина не клиентский кап. Токены, усечение и фактическую долю проверить в И‑126.'),
                ('Наличие ≠ обнаружение ≠ чтение ≠ применение ≠ повторяемость.',
                 'SURFACES.json:coverage/metrics; S11–S17; [сверка P12](../strategy/pre-104/ARCHITECTURE-REVIEW.md)',
                 'Ни одна ячейка не принята. 0 запусков; read_rate / apply_rate / false_positive остаются null. Разбиение И‑125 согласовать отдельно.'),
            )),
            '### Пробелы и следующий способ проверки',
            md_table(('Среда / пробел','Шаг','basis','criterion'), (
                (f"{env[k]['target']['surface']} / {_GAP[n]}",g['next'] or 'вне Ф5',g['basis'],g['criterion']) for k in _ORDER for n,g in env[k]['gaps'].items())),
            '### Обязательный корпус',
            md_table(('ID','basis','criterion','Ожидалось и совпало'), (
                (r['id'],r['basis'],r['criterion'],r['error']['code'] if 'error' in r else 'матрица принята') for r in book['cases'])),
        ])
    lines.extend([
        '### Не выполнялось (not run)',
        md_table(('Что','Почему'),((r['what'],r['why']) for r in verdict['not_run'])),
        '## П7–П9. Печать и сверка',
        '`python3 -B research/121/run.py` повторяет проверку в двух копиях; `--verify-seal` только сверяет [печать](SEAL.json), [повтор](REPLAY.json), отчёт и страницу без записи. '
        'Якорные строки стратегии закреплены до кода, полная стратегия входит в печать. Страница и записи о самой печати находятся снаружи.',
        '[Стратегия v1.23](../STRATEGY.md) · [сверка №31](../strategy/SYNC-LOG.md). A1–A4, P0, план, вехи, критерии и пригодность прежние. '
        f"Публикация ровно 19 путей разрешена отдельно ([основание](DESIGN.md)); П9 подтверждается по SHA в `origin/{spec['branch']}` "
        'и побайтным повтором из снимка коммита. Ф5 открыта. И‑122 не начата.',
    ])
    return '\n\n'.join(lines)+'\n'


def page(spec, verdict, doc, seal, replay):
    def e(v): return escape(str(v))

    env, m = doc['environments'], verdict['summary']
    state = 'П5 принята: только матрица' if verdict['outcome']=='accepted' and replay['outcome']=='ok' else 'Приёмка не пройдена'
    cards = []
    for name in _ORDER:
        r = env[name]; stub = r['status']=='stub'
        kind = 'Заглушка' if stub else 'Кандидат'
        paths = ' · '.join(f'<code>{e(n)}</code>' for n in r['entry']['paths'])
        approach = e(r['stub_reason']) if stub else paths
        gaps = ''.join(f'<li><b>{e(_GAP[n])} · {e(g["next"] or "вне Ф5")}</b><br>{e(g["criterion"])}</li>' for n,g in r['gaps'].items())
        cards.append(f'<article class="card"><p class="badge {"stub" if stub else "candidate"}">{e(kind)} · <code>{e(r["status"])}</code></p>'
                     f'<h3>{e(r["target"]["surface"])}</h3><p>{approach}</p>'
                     f'<p class="muted"><b>Не трогаем:</b> {e(", ".join(r["unchanged"]))}.</p>'
                     f'<details><summary>Пробелы и критерии</summary><ul>{gaps}</ul></details></article>')
    head = ''.join(f'<th scope="col">{e(name)}</th>' for _,name in _STAGES)
    body = ''.join(f'<tr><th scope="row">{e(env[k]["target"]["surface"])}</th>'
                   + ''.join(f'<td>{"вне области" if env[k]["coverage"][col]=="out_of_scope" else "not run"}</td>' for col,_ in _STAGES) + '</tr>' for k in _ORDER)
    omitted = ''.join(f'<li><b>{e(r["what"])}</b> {e(r["why"])}</li>' for r in verdict['not_run'])
    return f'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>И‑121 · Матрица входов и пробелов</title><style>
:root {{color-scheme:light;--bg:#f6f7f3;--ink:#1c2a37;--muted:#465d68;--rule:#d6e0db;--accent:#135b51}}
* {{box-sizing:border-box}} body {{margin:0;background:var(--bg);color:var(--ink);font:1rem/1.58 system-ui,sans-serif}}
header {{background:#e0efea;border-bottom:1px solid var(--rule)}} .wrap,main {{max-width:72rem;margin:auto;padding:1.6rem max(1rem,4vw)}}
h1 {{font-size:clamp(2.2rem,6vw,4.5rem);letter-spacing:-.055em;line-height:1.04;max-width:19ch;margin:.37em 0}}
h2 {{margin:1.5em 0 .55em;line-height:1.2}} h3,p {{margin:.38em 0}} a {{color:var(--accent);text-underline-offset:.17em}}
.muted {{color:var(--muted)}} .status {{color:var(--accent);font-weight:750}} .grid {{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(18rem,100%),1fr));gap:.8rem}}
.card,aside {{background:#fff;border:1px solid var(--rule);border-radius:.72rem;padding:1rem 1.12rem;min-width:0}} aside {{border-left:.26rem solid var(--accent);margin:1rem 0}}
.badge {{padding:.08rem .48rem;border-radius:.3rem;display:inline-block;background:#dbefe7;color:#164d41;font-size:.92rem}}
.badge.stub {{background:#e9ebef;color:#374655}} details {{margin:.65em 0 0}} summary {{cursor:pointer;font-weight:650}}
.scroll {{overflow:auto}} table {{border-collapse:collapse;width:100%;min-width:36rem}} th,td {{text-align:left;padding:.58rem;border-bottom:1px solid var(--rule)}}
code {{overflow-wrap:anywhere}} li {{margin:.4em 0}}
</style></head><body><header><div class="wrap"><p class="muted">И‑121 · {e(spec['phase'])} · {e(spec['priority'])}</p>
<h1>Матрица входов и пробелов</h1><p class="status">{e(state)}</p>
<p>Три кандидата, три заглушки. Ни один клиент не запускался; наличие файла не означает, что клиент его прочитал или применил.</p></div></header>
<main><div class="grid">
<div class="card"><a href="CHECKOUT.json">Рабочая копия</a><p><b>{e(counts_line(verdict['runs']['checkout']['counts']))}</b></p></div>
<div class="card"><a href="CLEANROOM.json">Чистая копия</a><p><b>{e(counts_line(verdict['runs']['cleanroom']['counts']))}</b></p></div>
<div class="card"><a href="ACCEPTANCE.json">Приёмка</a><p><b>{e(counts_line(verdict['counts']))}</b></p></div></div>
<h2>Шесть сред</h2><div class="grid">{''.join(cards)}</div>
<aside><b>Две исторические записи о Copilot.</b> В отчёте И‑101 — 3/4, в структурном инвентаре из печати и повторе И‑102 — 3/5. Использовано 3/5 только для донора 0.1.36; оба источника сохранены. Текущее старшинство неизвестно.</aside>
<h2>Что не измерено</h2><p><b>25–30%</b> — бюджет Kit, <b>4096 B</b> — предел локального §0. Капы клиента и усечение не измерялись. Доли чтения, применения и ложных срабатываний — <code>null</code>, не 0%.</p>
<div class="scroll"><table><thead><tr><th scope="col">Среда</th>{head}</tr></thead><tbody>{body}</tbody></table></div>
<p class="muted">{e(m['by_coverage']['not run'])} стадий ожидают проб. {e(m['by_coverage']['out_of_scope'])} стадий заглушек вне области.</p>
<h2>Печать и документы</h2><div class="card"><a href="{e(seal['file'])}">Печать исследования</a>
<p>{e(seal['members'])} файлов · {e(seal['bytes'])} байт · <a href="REPLAY.json">повтор: {e(replay['outcome'])}</a></p><p>SHA‑256<br><code>{e(seal['sha256'])}</code></p></div>
<ul>{omitted}</ul><p><a href="SURFACES.json">Матрица JSON</a> · <a href="REPORT.md">Отчёт с основаниями</a> · <a href="../STRATEGY.md">Стратегия</a></p>
<p class="muted">Сверка №31. П9 сверяется по SHA в <code>origin/{e(spec["branch"])}</code> и побайтным повтором из снимка коммита. Ф5 открыта, И‑122 не начата.</p></main></body></html>
'''
