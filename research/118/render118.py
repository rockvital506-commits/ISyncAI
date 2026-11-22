"""Отчёт и статическая страница И-118: проверка байтов, не доверие к источнику."""
from html import escape

from render import check_rows, counts_line, md_table


def outcome(row):
    if row['error'] is None:
        return f"verified · revision {row['verified']['revision']}"
    error = row['error']
    return f"{error['code']} · {error['where']} / {error['details']['reason']}"


def report(spec, red, verdict, info):
    runs, m = verdict['runs'], info['metrics']
    lines = [
        '# И‑118 — Полученный пакет сверяется в обе стороны',
        f"`{spec['branch']}` · {spec['phase']} · {spec['priority']}",
        '## П0–П2. Сверка, границы, RED',
        f"[Границы](DESIGN.md) · стратегия `{spec['baseline_strategy']}` · HEAD `{spec['baseline']}`. "
        'Согласованный fetch подтвердил И‑117; 301 рабочий файл был побайтно равен опубликованному снимку, '
        'локальный HEAD выровнен без перезаписи рабочих файлов. [Печать И‑117](../117/REPLAY.json) прошла без записи.',
        f"[RED.json](RED.json): rc {red['rc']}, {counts_line(red['result']['counts'])}; вывод архивной базы совпал. "
        'Контроль до продукта принял оба голых v2 и два штатных формата истории; рабочий порт вернул `unknown_operation` для обеих операций.',
        f"[Корпус](CASES.json) `{spec['casebook_sha256']}` · [оракул](test_bundle_verify.py) `{spec['test_sha256']}`. "
        'Векторы ZIP и ответы закреплены до реализации. Генератор не вызывает сборщик или проверяющий модуль.',
        '## П3–П5. Два независимых прогона',
        f"`python3 {' '.join(spec['command'])}` · {verdict['os']}, Python {verdict['python']}. В чистой копии только {len(spec['target_inputs'])} объявленных входов.",
        md_table(('Процесс', 'Проверки', 'rc', 'basis'), ((
            'П3 · рабочая копия', counts_line(runs['checkout']['counts']), runs['checkout']['rc'], '[CHECKOUT.json](CHECKOUT.json)'), (
            'П4 · чистая копия', counts_line(runs['cleanroom']['counts']), runs['cleanroom']['rc'], '[CLEANROOM.json](CLEANROOM.json)'))),
        f"[ACCEPTANCE.json](ACCEPTANCE.json): **{verdict['outcome']}** · {counts_line(verdict['counts'])} по воротам и отложенным группам.",
        md_table(('Ворота', 'Статус', 'basis', 'criterion'), check_rows(verdict)),
        '## П6. Что доказано',
    ]
    if m is None:
        lines.append('Приёмка отклонена. Новая печать и страница не создаются.')
    else:
        ref, other = info['reference'], info['independent_rehash']
        lines.extend([
            f"На прогон: {m['verified']} успехов, {m['refused']} ожидаемых отказов "
            f"(`bundle_incomplete`: {m['by_code']['bundle_incomplete']}; `digest_mismatch`: {m['by_code']['digest_mismatch']}). "
            f"{m['no_archive_open']} отказов до открытия ZIP, {m['no_member_read']} — до чтения любого члена. "
            f"{m['archive_attempts']} открытий буфера, {m['member_reads']} попыток чтения, {m['effect_attempts']} попыток I/O или записи ZIP. "
            'Входы неизменны, вывод и частичные результаты отсутствуют.',
            md_table(('Вход', 'Ревизия L1', 'Digest манифеста', 'SHA‑256 ZIP'), (
                ('[И‑117/P01](../117/Synthetic-Bundle-117.zip)', ref['revision'], f"`{ref['manifest_digest']}`", f"`{ref['archive_sha256']}`"),
                ('P03 · синтетические байты с заново пересчитанным манифестом', other['revision'], f"`{other['manifest_digest']}`", f"`{other['archive_sha256']}`"),
                ('[Печать И‑118](SEAL.json), не пакет формата И‑117', '—', '—', 'См. SEAL.json и HTML'),
            )),
            md_table(('Находка', 'basis', 'criterion / предел'), (
                ('Одно изменение обнаруживается даже при правильном CRC ZIP.', 'T01–T16; N20, N33–N35', 'Все 16 подмен одного байта с прежним манифестом → digest_mismatch. Сбой CRC — bundle_incomplete; размер, digest и хеш файла сверяются отдельно.'),
                ('Обе стороны должны перечислить один и тот же полный набор.', 'A01–A16/M01–M16/B01–B16; N09–N14', '48 одиночных пропусков отклонены. Равенство неполных списков, лишняя строка и повтор имени не принимаются.'),
                ('Недопустимый контейнер не читается как набор файлов.', 'N01–N08/N15–N19/N21–N23/N44–N46; P06', 'Ограничения проверяются до чтения; правильная граница 1/4 МиБ проходит.'),
                ('Согласованные хеши не проверяют пригодность реестра.', 'P02/P04/P05; N36–N42; контроль', 'Пустой голый L1 валиден; чужой корень, новая ложная ревизия, неверный A4 и целая локальная история отвергаются.'),
                ('Внутренняя целостность не доказывает источник.', 'P01/P03; T01–T16', 'Замена с пересчётом связей проходит при тех же корнях и revision; не подпись, pin, отсутствие секретов или разрешение на установку.'),
            )),
            '### Обязательные строки',
            md_table(('ID', 'basis', 'criterion', 'Наблюдалось', 'Чтений'), ((r['id'], r['basis'], r['criterion'], outcome(r), r['reads']) for r in info['rows'])),
        ])
    lines.extend([
        '### Отдельно: not run',
        md_table(('Что', 'Почему'), ((r['what'], r['why']) for r in verdict['not_run'])),
        '## П7–П9. Печать, страница и сверка',
        '`python3 -B research/118/run.py` воспроизводит исследование. `python3 -B research/118/run.py --verify-seal` сверяет '
        '[печать](SEAL.json), [повтор](REPLAY.json), результаты, отчёт и HTML без записи. Исходный пример входит в печать как закреплённые байты. '
        'HTML и записи о самой печати не входят в её состав.',
        '[Стратегия v1.20](../STRATEGY.md) · [сверка №28](../strategy/SYNC-LOG.md). A1–A4, P0, порядок, вехи, критерии и пригодность прежние. '
        f"Commit/push только 20 путей И‑118 разрешены отдельно ([основание](DESIGN.md)). П9 подтверждается совпадением SHA "
        f"с `origin/{spec['branch']}` и побайтным повтором из снимка коммита. "
        'М2 учитывается только в стендовом объёме по этому подтверждению; рабочего переноса и установки не было. И‑119 не начата, Ф4 открыта.',
    ])
    return '\n\n'.join(lines) + '\n'


def page(spec, verdict, info, seal, replay):
    def e(value):
        return escape(str(value))

    ref, m = info['reference'], info['metrics']
    good = verdict['outcome'] == 'accepted' and replay['outcome'] == 'ok'
    tests = ''.join(f'<tr><th scope="row">{e(r["id"])}</th><td>{e(r["criterion"])}</td><td><code>{e(outcome(r))}</code></td><td>{e(r["reads"])}</td></tr>'
                    for r in info['rows'])
    limits = ''.join(f'<li><b>{e(r["what"])}</b> {e(r["why"])}</li>' for r in verdict['not_run'])
    return f'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>И‑118 · Целостность пакета</title><style>
:root {{color-scheme:light;--canvas:#f7f6f2;--paper:#fff;--ink:#1b2b38;--sub:#4b606b;--edge:#cfdbde;--link:#07586c;--teal:#075b61}}
* {{box-sizing:border-box}} body {{margin:0;background:var(--canvas);color:var(--ink);font:1rem/1.57 system-ui,sans-serif}}
header {{background:#e0eef0;border-bottom:1px solid var(--edge)}} main,.wrap {{max-width:72rem;margin:auto;padding:1.75rem max(1rem,4vw)}}
h1 {{font-size:clamp(2.25rem,6vw,4.7rem);letter-spacing:-.052em;line-height:1.03;max-width:19ch;margin:.32em 0;text-wrap:balance}}
h2 {{font-size:clamp(1.3rem,3vw,1.8rem);margin:1.45em 0 .55em;line-height:1.2}} h3,p {{margin:.45em 0}} .meta {{color:var(--sub)}}
a {{color:var(--link);text-underline-offset:.16em}} .status {{font-weight:750;color:{'#075b61' if good else '#9a173b'}}}
.grid {{display:grid;gap:.8rem;grid-template-columns:repeat(auto-fit,minmax(min(16.5rem,100%),1fr))}}
.card,details,aside {{border:1px solid var(--edge);border-radius:.75rem;background:var(--paper);padding:1rem 1.15rem}}
.card strong {{display:block;margin-top:.28rem;font-size:1.12rem}} aside {{border-left:.25rem solid var(--teal);margin-top:1rem}}
summary {{cursor:pointer;font-weight:710}} .scroll {{overflow:auto}} table {{width:100%;border-collapse:collapse;margin-top:.55rem}}
th,td {{text-align:left;vertical-align:top;padding:.6rem;border-bottom:1px solid var(--edge)}} code {{overflow-wrap:anywhere}} li {{margin:.42rem 0}}
</style></head><body><header><div class="wrap"><p class="meta">И‑118 · {e(spec['phase'])} · {e(spec['priority'])}</p>
<h1>{e(spec['title'])}</h1><p class="status">{'П5 принята на синтетических пакетах' if good else 'Приёмка не пройдена'}</p>
<p>16 изменений одного байта обнаружены при корректном CRC. 48 проб пропуска подтверждают, что сверка идёт в обе стороны.</p></div></header>
<main><div class="grid">
<div class="card"><a href="CHECKOUT.json">Рабочая копия</a><strong>{e(counts_line(verdict['runs']['checkout']['counts']))}</strong></div>
<div class="card"><a href="CLEANROOM.json">Чистая копия</a><strong>{e(counts_line(verdict['runs']['cleanroom']['counts']))}</strong></div>
<div class="card"><a href="ACCEPTANCE.json">Ворота приёмки</a><strong>{e(counts_line(verdict['counts']))}</strong></div></div>
<h2>Проверенный пакет и печать исследования</h2><div class="grid">
<section class="card"><h3><a href="../117/Synthetic-Bundle-117.zip">Эталон И‑117/P01</a></h3>
<p>{e(info['source']['bytes'])} байт · 17 членов · revision {e(ref['revision'])}</p><p>Digest манифеста<br><code>{e(ref['manifest_digest'])}</code></p>
<p>SHA‑256 входного ZIP<br><code>{e(ref['archive_sha256'])}</code></p></section>
<section class="card"><h3><a href="{e(seal['file'])}">Печать И‑118</a></h3>
<p>{e(seal['members'])} члена · {e(seal['bytes'])} байт. Включает эталон, входы, тесты и отчёт; не является пакетом формата И‑117.</p>
<p>SHA‑256 печати<br><code>{e(seal['sha256'])}</code></p><p><a href="REPLAY.json">Повтор: {e(replay['outcome'])}</a></p></section></div>
<aside><strong>Целостность не равна подлинности.</strong> В P03 другой файл с пересчитанным манифестом прошёл проверку. Эта функция не определяет, кто его выпустил и можно ли его устанавливать.</aside>
<h2>Наблюдения и границы</h2><p>{e(m['verified'])} успехов · {e(m['refused'])} ожидаемых отказов · {e(m['no_member_read'])} отказов до первого чтения члена.</p>
<details><summary>{e(m['cases'])} обязательных случаев</summary><div class="scroll"><table>
<thead><tr><th scope="col">ID</th><th scope="col">Критерий</th><th scope="col">Наблюдалось</th><th scope="col">Чтений</th></tr></thead><tbody>{tests}</tbody></table></div></details>
<ul>{limits}</ul><p><a href="REPORT.md">Отчёт</a> · <a href="VERIFICATION.json">Доказательства</a> · <a href="../../kit/base/BUNDLE-VERIFY.md">Контракт</a> · <a href="../STRATEGY.md">Стратегия</a></p>
<p class="meta">Сверка №28. П9 подтверждается по коммиту И‑118 в <code>origin/{e(spec["branch"])}</code> и повтором. М2 — только на стенде. И‑119 не начата.</p></main></body></html>
'''
