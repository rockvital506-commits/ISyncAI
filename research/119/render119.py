"""Отчёт и страница И-119: раздельные свидетельства целостности, подписи и решения."""
from html import escape

from render import check_rows, counts_line, md_table


def outcome(row):
    if row['error'] is not None:
        e = row['error']
        return f"{e['code']} · {e['where']} / {e['details']['reason']}"
    r = row['result']
    return f"{r['signature_status']} · {r['policy_decision']} / {r['reason']}"


def report(spec, red, verdict, info):
    m, runs = info['metrics'], verdict['runs']
    lines = [
        '# И‑119 — Подпись и исключение не заменяют целостность',
        f"`{spec['branch']}` · {spec['phase']} · {spec['priority']}",
        '## П0–П2. Сверка, замысел и RED',
        f"[Границы](DESIGN.md) · v1.20 · `{spec['baseline']}`. Согласованный fetch совпал, "
        '[печать И‑118](../118/REPLAY.json) прошла без записи. Рабочий порт не менялся.',
        f"[RED](RED.json): rc {red['rc']}, {counts_line(red['result']['counts'])}; чистый снимок Git дал те же строки. "
        'До реализации контроль проверил публичный вектор Ed25519 RFC 8032 §7.1, две настоящие учебные подписи, четыре отрицательных сравнения, '
        'целостность обоих ZIP и отсутствие рабочих операций.',
        f"{spec['expected_control']['openssl']} · [корпус](CASES.json) `{spec['casebook_sha256']}` · "
        f"[оракул](test_bundle_trust.py) `{spec['test_sha256']}`. В корпусе только открытые входы. "
        'Одноразовый учебный закрытый ключ создан при подготовке, остался в памяти и каналах процессов и не нужен для повтора.',
        '## П3–П5. Два независимых прогона',
        f"`python3 {' '.join(spec['command'])}` · {verdict['os']}, Python {verdict['python']}. В чистой копии только {len(spec['target_inputs'])} входов.",
        md_table(('Процесс', 'Проверки', 'rc', 'basis'), (
            ('П3 · рабочая копия', counts_line(runs['checkout']['counts']), runs['checkout']['rc'], '[CHECKOUT.json](CHECKOUT.json)'),
            ('П4 · чистая копия', counts_line(runs['cleanroom']['counts']), runs['cleanroom']['rc'], '[CLEANROOM.json](CLEANROOM.json)'))),
        f"[ACCEPTANCE.json](ACCEPTANCE.json): **{verdict['outcome']}** · {counts_line(verdict['counts'])} по воротам и отложенным группам.",
        md_table(('Ворота', 'Статус', 'basis', 'criterion'), check_rows(verdict)),
        '## П6. Наблюдения и предел вывода',
    ]
    if not m:
        lines.append('Приёмка отклонена; новая печать и страница не создаются.')
    else:
        source = info['references']['source']; alt = info['references']['alternate']
        lines.extend([
            f"На прогон: {m['assessed']} оценок политики ({m['by_decision']['blocked']} блокировок, два `optional`, два `exception` и два `satisfied`), "
            f"{m['refused']} отказа до решения (2 `digest_mismatch`, 3 `bundle_incomplete`, 18 `bundle_trust_invalid`). "
            f"Из {m['verifier_calls']} вызовов явно переданного проверяющего шесть — реальный OpenSSL, два — контроль сбоя/не-булева ответа. "
            f"В самом модуле {m['effect_attempts']} попыток I/O; входы и вывод не изменялись.",
            md_table(('Свидетельство', 'Ревизия L1', 'Digest манифеста', 'SHA‑256 ZIP'), (
                ('[И‑117/P01](../117/Synthetic-Bundle-117.zip)', source['revision'], f"`{source['manifest_digest']}`", f"`{source['archive_sha256']}`"),
                ('И‑118/P03 · вариант с пересчитанным манифестом', alt['revision'], f"`{alt['manifest_digest']}`", f"`{alt['archive_sha256']}`"),
                ('[Исследовательская печать](SEAL.json)', '—', '—', 'Отдельный SHA‑256, см. SEAL.json и HTML'),
            )),
            f"Отпечаток учебного **открытого ключа**, не пакета: `{info['public_key_id']}`.",
            md_table(('Факт', 'basis', 'criterion / предел'), (
                ('Целостность первая.', 'I01–I05; И‑118', 'Подмена и неполнота отвергаются до проверки; даже совпавшее исключение их не отменяет.'),
                ('`unsigned` — состояние, не ошибка SHA‑256.', 'U01/U02/U09', 'Одни и те же целостные байты получают разное решение только по явно выбранной политике; для личного сценария решение не навязывается.'),
                ('Исключение узкое и временное.', 'U03–U11; N10–N18', 'Только для unsigned, одного SHA‑256 ZIP, разрешённого approver и now < expiry. Ровно в expiry уже отказ.'),
                ('Подпись привязана к точному ZIP и выбранному ключу.', 'S01/S02/S04–S06/S17', 'Два отдельно подписанных ZIP приняты; перенести подпись между ними нельзя даже при совпавшей revision и согласованных внутренних хешах.'),
                ('Сбой проверки не выдаёт доверия.', 'S03/S07–S16', 'Ключ вне списка, неверная запись, недоступный проверяющий и не-булев ответ блокируются отдельно. Нет понижения до unsigned.'),
            )),
            '### Корпус',
            md_table(('ID', 'basis', 'criterion', 'Наблюдалось'), ((r['id'], r['basis'], r['criterion'], outcome(r)) for r in info['rows'])),
        ])
    lines.extend([
        '### Отдельно: not run',
        md_table(('Что', 'Почему'), ((r['what'], r['why']) for r in verdict['not_run'])),
        '## П7–П9. Печать и сверка',
        '`python3 -B research/119/run.py` воспроизводит исследование на согласованном стенде: нужен доступный OpenSSL с Ed25519, а не закрытый ключ. '
        '`python3 -B research/119/run.py --verify-seal` только сверяет сохранённые данные, [печать](SEAL.json), [повтор](REPLAY.json), отчёт и HTML без записи. '
        'Страница и записи о печати не входят в её состав.',
        '[Стратегия v1.21](../STRATEGY.md) · [сверка №29](../strategy/SYNC-LOG.md). A1–A4, P0, порядок, вехи, критерии и пригодность прежние. '
        f"Commit/push только 20 путей И‑119 разрешены отдельно ([основание](DESIGN.md)). П9 подтверждается по SHA в `origin/{spec['branch']}` "
        'и побайтным повтором из снимка коммита на открытых данных. И‑120 не начата; Ф4 открыта, М2 остаётся стендовой.',
    ])
    return '\n\n'.join(lines) + '\n'


def page(spec, verdict, info, seal, rep):
    def e(v):
        return escape(str(v))

    ref, m = info['references'], info['metrics']; accept = verdict['outcome'] == 'accepted' and rep['outcome'] == 'ok'
    checks = ''.join(f'<tr><th scope="row">{e(r["id"])}</th><td>{e(r["criterion"])}</td><td><code>{e(outcome(r))}</code></td></tr>'
                     for r in info['rows'])
    omitted = ''.join(f'<li><b>{e(r["what"])}</b> {e(r["why"])}</li>' for r in verdict['not_run'])
    return f'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>И‑119 · Подпись и временное исключение</title><style>
:root {{color-scheme:light;--bg:#f8f7f3;--panel:#fff;--ink:#1f2b38;--muted:#506372;--edge:#d4dede;--accent:#185767;--warn:#7c2b40}}
* {{box-sizing:border-box}} body {{margin:0;background:var(--bg);color:var(--ink);font:1rem/1.56 system-ui,sans-serif}}
header {{background:#e1edf0;border-bottom:1px solid var(--edge)}} .wrap,main {{max-width:71rem;margin:auto;padding:1.75rem max(1rem,4vw)}}
h1 {{font-size:clamp(2.2rem,6vw,4.65rem);letter-spacing:-.05em;line-height:1.04;max-width:20ch;margin:.32em 0;text-wrap:balance}}
h2 {{margin:1.4em 0 .55em;line-height:1.2}} h3,p {{margin:.4em 0}} a {{color:var(--accent);text-underline-offset:.16em}}
.meta {{color:var(--muted)}} .status {{font-weight:740;color:{'#185767' if accept else '#7c2b40'}}}
.grid {{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(16rem,100%),1fr));gap:.8rem}}
.card,details,aside {{padding:1rem 1.15rem;border:1px solid var(--edge);border-radius:.7rem;background:var(--panel)}}
.card strong {{display:block;font-size:1.12rem;margin-top:.3rem}} aside {{border-left:.25rem solid var(--accent);margin-top:1rem}}
summary {{cursor:pointer;font-weight:700}} .scroll {{overflow:auto}} table {{border-collapse:collapse;width:100%;margin-top:.55rem}}
th,td {{text-align:left;vertical-align:top;padding:.58rem;border-bottom:1px solid var(--edge)}} code {{overflow-wrap:anywhere}} li {{margin:.42em 0}}
</style></head><body><header><div class="wrap"><p class="meta">И‑119 · {e(spec['phase'])} · {e(spec['priority'])}</p>
<h1>{e(spec['title'])}</h1><p class="status">{'П5 принята на синтетических данных' if accept else 'Приёмка не пройдена'}</p>
<p>Отсутствие подписи — не повреждение. Действительное исключение не исправляет пакет и не делает его подписанным.</p></div></header>
<main><div class="grid">
<div class="card"><a href="CHECKOUT.json">Рабочая копия</a><strong>{e(counts_line(verdict['runs']['checkout']['counts']))}</strong></div>
<div class="card"><a href="CLEANROOM.json">Чистая копия</a><strong>{e(counts_line(verdict['runs']['cleanroom']['counts']))}</strong></div>
<div class="card"><a href="ACCEPTANCE.json">Ворота приёмки</a><strong>{e(counts_line(verdict['counts']))}</strong></div></div>
<h2>Что различила проверка</h2><div class="grid">
<section class="card"><h3>Подпись</h3><p>Две настоящие подписи Ed25519 проверены OpenSSL. Перенос подписи к ZIP с пересчитанным манифестом не проходит.</p></section>
<section class="card"><h3>Исключение</h3><p>Только для <code>unsigned</code>, одного SHA‑256 ZIP и разрешённого <code>approver</code>. Ровно в <code>expiry</code> уже не действует.</p></section>
<section class="card"><h3>Целостность</h3><p>{e(m['by_error']['digest_mismatch'])} подмены остановлены до решений. Пакет с неверными байтами не может воспользоваться исключением.</p></section>
</div><aside><b>Решение относится только к переданной политике.</b> Это не установка, не рабочий перенос и не доказательство защищённости источника ключей или часов.</aside>
<h2>Отпечатки и повтор</h2><div class="grid"><div class="card">
<h3><a href="../117/Synthetic-Bundle-117.zip">Исходный ZIP И‑117</a></h3><p>SHA‑256 ZIP<br><code>{e(ref['source']['archive_sha256'])}</code></p>
<p>Digest манифеста<br><code>{e(ref['source']['manifest_digest'])}</code></p><p>Ревизия L1: {e(ref['source']['revision'])}</p></div>
<div class="card"><h3><a href="{e(seal['file'])}">Печать исследования</a></h3>
<p>{e(seal['members'])} члена · {e(seal['bytes'])} байт · <a href="REPLAY.json">повтор: {e(rep['outcome'])}</a></p>
<p>SHA‑256 печати<br><code>{e(seal['sha256'])}</code></p><p>Содержит только открытые данные; закрытый ключ не нужен.</p></div></div>
<h2>Корпус и ограничения</h2><details><summary>{e(m['cases'])} обязательный случай</summary><div class="scroll"><table>
<thead><tr><th scope="col">ID</th><th scope="col">Критерий</th><th scope="col">Наблюдалось</th></tr></thead><tbody>{checks}</tbody></table></div></details>
<ul>{omitted}</ul><p><a href="REPORT.md">Отчёт</a> · <a href="TRUST.json">Доказательства</a> · <a href="../../kit/base/BUNDLE-TRUST.md">Контракт</a> · <a href="../STRATEGY.md">Стратегия</a></p>
<p class="meta">Сверка №29. П9 подтверждается по коммиту И‑119 в <code>origin/{e(spec["branch"])}</code> и повтором на открытых данных. И‑120 не начата.</p></main></body></html>
'''
