"""Отчёт и статическая страница И-120: откат указателя, журнал и независимое чтение."""
from html import escape

from render import check_rows, counts_line, md_table


def detail(row):
    if row['error'] is not None:
        e = row['error']
        return f"{row['at']}: {e['code']} · {e['where']} / {e['details']['reason']}"
    if row['result'] is None:
        return 'planned · без записи'
    e = row['result']['event']
    return f"{e['action']} · #{e['seq']} · {e['signature_status']}/{e['policy_decision']}"


def report(spec, red, verdict, info):
    m, runs = info['metrics'], verdict['runs']
    lines = [
        '# И‑120 — Откат к точному N‑1 и журнал переключений',
        f"`{spec['branch']}` · {spec['phase']} · {spec['priority']}",
        '## П0–П2. Сверка, замысел и RED',
        f"[Замысел](DESIGN.md) · v1.21 · `{spec['baseline']}`. Согласованный fetch совпал; "
        '[печать И‑119](../119/REPLAY.json) проверена без записи. Рабочий порт не изменён.',
        f"[RED](RED.json): rc {red['rc']}, {counts_line(red['result']['counts'])}. Базовый Git-снимок дал те же байты вывода. "
        'Контроль до реализации уже читает три различных синтетических L1 штатным читателем; неуспех относится к отсутствующей операции И‑120.',
        f"[Корпус](CASES.json) `{spec['casebook_sha256']}` · [оракул](test_bundle_rollback.py) `{spec['test_sha256']}`. "
        'B и C собраны независимо из точного синтетического A; ни код из ZIP, ни закрытые ключи для повтора не нужны.',
        '## П3–П5. Два полных прогона',
        f"`python3 {' '.join(spec['command'])}` · {verdict['os']}, Python {verdict['python']}. В чистой копии только {len(spec['target_inputs'])} входов.",
        md_table(('Процесс', 'Случаи', 'rc', 'basis'), (
            ('П3 · рабочая копия', counts_line(runs['checkout']['counts']), runs['checkout']['rc'], '[CHECKOUT.json](CHECKOUT.json)'),
            ('П4 · чистая копия', counts_line(runs['cleanroom']['counts']), runs['cleanroom']['rc'], '[CLEANROOM.json](CLEANROOM.json)'))),
        f"[ACCEPTANCE.json](ACCEPTANCE.json): **{verdict['outcome']}** · {counts_line(verdict['counts'])} по воротам и отложенным группам.",
        md_table(('Ворота', 'Статус', 'basis', 'criterion'), check_rows(verdict)),
        '## П6. Что наблюдалось',
    ]
    if not m:
        lines.append('Приёмка отклонена; новая печать и страница не создаются.')
    else:
        refs = info['reader_control']; p01 = next(r for r in info['rows'] if r['id'] == 'P01')['readback']
        lines.extend([
            f"В измеряемой части прогона (без подготовки начальных журналов): **{m['applied']}** переключений "
            f"({m['by_action']['rollout']} вперёд, {m['by_action']['rollback']} назад), {m['preview_only']} план без записи, "
            f"{m['refused']} отказа. У {m['unchanged_refusals']} отказов нет изменения состояния. Из {m['replace_attempts']} попыток "
            f"замены завершились {m['successful_replaces']}; W01 остановлен до смены файла.",
            md_table(('Снимок', 'revision L1', 'SHA‑256 ZIP', 'SHA‑256 L1'),
                     ((n, r['profile_revision'], f"`{r['archive_sha256']}`", f"`{r['profile_sha256']}`") for n, r in refs.items())),
            f"**Точное восстановление B (P01/P02).** `read_registry` и `status` на свежей копии получили L1 `{p01['restored']['profile_sha256']}`, "
            f"тот же отпечаток текста, что до перехода на C (`{p01['restored']['rule_text_sha256']}`). "
            'В P02 чтение текущего C сначала отказало `digest_mismatch`, однако предыстория и проверяемые байты B сохранились. '
            f"L0 (`{p01['restored']['system_sha256']}`) и L2 (`{p01['restored']['project_sha256']}`) побайтно прежние. "
            'Это работоспособность чтения сохранённого состояния на стенде, не выполнение его правил.',
            md_table(('Факт', 'basis', 'criterion / предел'), (
                ('История, а не revision, выбирает N‑1.', 'P01/P02, R01–R07',
                 'Самосогласованный ZIP B_rebuilt и более старый A оставляют B единственным кандидатом. После отката нет автоматического второго шага.'),
                ('Старый допуск не заменяет проверку.', 'P03, T01–T10, R08/R09',
                 'И‑118 прежде политики; ровно в expiry или при недоступной проверке подписи нет перехода, в том числе после полученного плана.'),
                ('Указатель и журнал — одна замена.', 'P04/P07, J01–J10, W01',
                 'Во время попытки замены старый файл цел, новый записан рядом. Успех сохраняет весь префикс. Сбой до замены не выдаёт частичного успеха.'),
                ('Согласие точно и одноразово.', 'P06, C01–C08, T04',
                 'Старый билет не срабатывает даже при том же активном SHA и изменившейся цепочке. Билет не аутентификация владельца.'),
            )),
            '### Корпус',
            md_table(('ID', 'basis', 'criterion', 'Наблюдалось'), ((r['id'], r['basis'], r['criterion'], detail(r)) for r in info['rows'])),
        ])
    lines.extend([
        '### Отдельно: not run',
        md_table(('Что', 'Почему'), ((r['what'], r['why']) for r in verdict['not_run'])),
        '## П7–П9. Печать и сверка',
        '`python3 -B research/120/run.py` воспроизводит исследование (Python stdlib, без сети, новых ключей и OpenSSL). '
        '`python3 -B research/120/run.py --verify-seal` сверяет [печать](SEAL.json), [повтор](REPLAY.json), отчёт и HTML без записи. '
        'Страница и записи о самой печати не входят в её состав. Исследовательская печать не является одним из пакетов A/B/C.',
        '[Стратегия v1.22](../STRATEGY.md) · [сверка №30](../strategy/SYNC-LOG.md). A1–A4, P0, порядок, вехи, критерии и пригодность прежние. '
        f"Публикация ровно 20 путей разрешена отдельно ([основание](DESIGN.md)); П9 подтверждается по SHA в `origin/{spec['branch']}` "
        'и побайтным повтором из снимка коммита. Печати И‑117–И‑119 сверены из их опубликованных снимков. '
        'По §6 Ф4 закрывается после подтверждения П9 только в измеренном стендовом объёме; рабочий откат и пригодность не приняты. Д7 не решён; И‑121 не начата.',
    ])
    return '\n\n'.join(lines) + '\n'


def page(spec, verdict, info, seal, rep):
    def e(v):
        return escape(str(v))

    m = info['metrics']; ok = verdict['outcome'] == 'accepted' and rep['outcome'] == 'ok'
    witness = next(r for r in info['rows'] if r['id'] == 'P01')['readback']
    trace = ''.join(f'<tr><th scope="row">{e(label)}</th><td><code>{e(fact["archive_sha256"])}</code></td>'
                    f'<td><code>{e(fact["profile_sha256"])}</code></td></tr>'
                    for label, fact in (('Прежнее B', witness['previous']), ('Текущее C', witness['current']), ('Восстановленное B', witness['restored'])))
    checks = ''.join(f'<tr><th scope="row">{e(r["id"])}</th><td>{e(r["criterion"])}</td><td><code>{e(detail(r))}</code></td></tr>'
                     for r in info['rows'])
    omitted = ''.join(f'<li><b>{e(r["what"])}</b> {e(r["why"])}</li>' for r in verdict['not_run'])
    return f'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>И‑120 · Точный откат на стенде</title><style>
:root {{color-scheme:light;--bg:#f8f7f3;--panel:#fff;--ink:#1f2b38;--muted:#506372;--edge:#d4dede;--accent:#185767;--warn:#7c2b40}}
* {{box-sizing:border-box}} body {{margin:0;background:var(--bg);color:var(--ink);font:1rem/1.55 system-ui,sans-serif}}
header {{background:#e4efed;border-bottom:1px solid var(--edge)}} .wrap,main {{max-width:71rem;margin:auto;padding:1.75rem max(1rem,4vw)}}
h1 {{font-size:clamp(2.2rem,6vw,4.3rem);letter-spacing:-.045em;line-height:1.04;max-width:19ch;margin:.35em 0}}
h2 {{margin:1.4em 0 .55em;line-height:1.2}} h3,p {{margin:.42em 0}} a {{color:var(--accent);text-underline-offset:.16em}}
.meta {{color:var(--muted)}} .status {{font-weight:750;color:{'#185767' if ok else '#7c2b40'}}}
.grid {{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(16rem,100%),1fr));gap:.85rem}}
.card,details,aside {{padding:1rem 1.15rem;border:1px solid var(--edge);border-radius:.7rem;background:var(--panel);min-width:0}}
.card strong {{display:block;font-size:1.28rem;margin-top:.3rem}} aside {{border-left:.24rem solid var(--accent);margin-top:1rem}}
summary {{cursor:pointer;font-weight:700}} .scroll {{overflow:auto}} table {{border-collapse:collapse;width:100%;margin-top:.55rem}}
th,td {{text-align:left;vertical-align:top;padding:.62rem;border-bottom:1px solid var(--edge)}} code {{overflow-wrap:anywhere}} li {{margin:.44em 0}}
</style></head><body><header><div class="wrap"><p class="meta">И‑120 · {e(spec['phase'])} · {e(spec['priority'])}</p>
<h1>Откат на точный N‑1</h1><p class="status">{'П5 принята на синтетических данных' if ok else 'Приёмка не пройдена'}</p>
<p>Один файл связывает активный SHA‑256 ZIP и историю переключений. Результат подтверждён штатным чтением v2, а не только сменой указателя.</p></div></header>
<main><div class="grid">
<div class="card"><a href="CHECKOUT.json">Рабочая копия</a><strong>{e(counts_line(verdict['runs']['checkout']['counts']))}</strong></div>
<div class="card"><a href="CLEANROOM.json">Чистая копия</a><strong>{e(counts_line(verdict['runs']['cleanroom']['counts']))}</strong></div>
<div class="card"><a href="ACCEPTANCE.json">Приёмка</a><strong>{e(counts_line(verdict['counts']))}</strong></div></div>
<h2>Что вернулось после отката</h2><p>A → B → C → <b>B</b>. Ревизия L1 во всех трёх ZIP — {e(witness['restored']['profile_revision'])}; байты C отличаются. Во второй пробе C стал нечитаемым, а после возврата B читатель снова дал точный прежний результат. L0 и L2 не изменились.</p>
<div class="scroll"><table><thead><tr><th scope="col">Снимок</th><th scope="col">SHA‑256 ZIP</th><th scope="col">SHA‑256 L1</th></tr></thead><tbody>{trace}</tbody></table></div>
<h2>Что блокирует переход</h2><div class="grid">
<section class="card"><h3>Не тот пакет</h3><p>Согласованная пересборка с той же <code>revision</code> не подменяет N‑1. Более старый A не выбирается вместо B.</p></section>
<section class="card"><h3>Нет текущего допуска</h3><p>Исключение ровно в <code>expiry</code> уже не действует. Это проверяется заново при применении согласованного плана.</p></section>
<section class="card"><h3>Запись не завершена</h3><p>{e(m['unchanged_refusals'])} отказа без изменения состояния. При искусственном сбое перед заменой и указатель, и журнал остались прежними.</p></section>
</div><aside><b>Граница — собственный временный стенд.</b> Не проверены рабочий откат, исполнение правил, конкурентная запись, питание и происхождение доверенных входов.</aside>
<h2>Печать и повтор</h2><div class="card"><a href="{e(seal['file'])}">Печать исследования</a><p>{e(seal['members'])} членов · {e(seal['bytes'])} байт · <a href="REPLAY.json">повтор: {e(rep['outcome'])}</a></p>
<p>SHA‑256 печати<br><code>{e(seal['sha256'])}</code></p><p>Печать исследования — не переносимый ZIP и не установщик.</p></div>
<h2>Корпус и пределы</h2><details><summary>{e(m['cases'])} обязательных случаев</summary><div class="scroll"><table>
<thead><tr><th scope="col">ID</th><th scope="col">Критерий</th><th scope="col">Наблюдалось</th></tr></thead><tbody>{checks}</tbody></table></div></details>
<ul>{omitted}</ul><p><a href="REPORT.md">Отчёт</a> · <a href="ROLLOUT.json">Наблюдения</a> · <a href="../../kit/base/BUNDLE-ROLLBACK.md">Контракт</a> · <a href="../STRATEGY.md">Стратегия</a></p>
<p class="meta">Сверка №30. П9 подтверждается по коммиту И‑120 в <code>origin/{e(spec["branch"])}</code> и побайтному повтору. Закрытие Ф4 — только в стендовом объёме; И‑121 не начата.</p></main></body></html>
'''
