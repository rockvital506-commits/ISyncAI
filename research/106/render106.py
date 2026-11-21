"""Отчёт и страница И-106 из одной приёмки и наблюдений."""
from html import escape
from render import counts_line, md_table


def report(spec, cases, checkout, accepted):
    runs, series = accepted['runs'], accepted['series']
    lines = [
        '# И‑106 — Десять регистраций L1 и журнал решений',
        f"`{spec['branch']}` · {spec['phase']} · {spec['priority']} · {spec['date']}",
        '## П0–П2. Сверка, замысел и испытания',
        f"До начала: `{spec['baseline']}`. [И‑105](../105/ACCEPTANCE.json) дала одну реальную запись; "
        '[замысел](DESIGN.md) требует десяти отдельных подтверждений и непрерывного журнала без изменения L0. '
        '[Хранилище](../../kit/base/STORAGE-V2.md) пишет один файл; [контракт журнала](../../kit/base/PROFILE-JOURNAL.md) '
        'разделяет формат контейнера, внутренний реестр v2 и номер принятого решения.',
        f"[Замороженные ожидания](CASES.json): {spec['case_counts']['positive']} положительных и {spec['case_counts']['negative']} отрицательных "
        f"случаев; SHA‑256 `{spec['casebook_sha256']}`. [Проба](test_history.py) до реализации остановилась из-за отсутствия `profile_history`.",
        '## П3–П5. Два целевых прогона',
        md_table(('Процесс', 'Случаи', 'Машинный результат'), (
            ('П3 · код из checkout', counts_line(runs['checkout']['counts']), 'CHECKOUT.json'),
            ('П4 · чистая копия', counts_line(runs['cleanroom']['counts']), 'CLEANROOM.json'))),
        f"Среда: `{accepted['host_os']}`. Каждый процесс создаёт своё временное рабочее дерево с тремя физическими корнями. "
        'П4 (`-B -I -S -X utf8`) запускается только из девяти перечисленных входов без Git, ISAI и ZIP 0.1.36. '
        'Измерения и SHA‑256 входов совпали при принятом результате. Это не обкатка независимым агентом или живой установщик.',
        'Донорский [стенд И‑103](../103/VERSION-EVIDENCE.json) — отдельное историческое свидетельство: '
        'его последовательная запись двух файлов не является транзакцией рабочего Kit. '
        '0.1.36 нативно не запускали и не засчитывали в целевые случаи.',
        f"[ACCEPTANCE.json](ACCEPTANCE.json): **{accepted['outcome']}**, {counts_line(accepted['counts'])}. "
        'Это число ворот и отложенных работ, не сумма результатов П3 и П4.',
        md_table(('Проверка', 'Статус', 'basis', 'criterion'),
                 ((r['check'], r['status'], r['basis'], r['criterion']) for r in accepted['checks'])),
        '## П6. Наблюдения',
    ]
    if series is not None:
        source = checkout['result']
        fixed = series['fixed_digests']
        steps = ' → '.join(str(n) for n in series['revisions'])
        lines.extend([
            f"**{steps}** — ревизии L1, прочитанные после каждой принятой регистрации. История содержит {series['decisions']} "
            f"решений, SHA‑256 файла L1 различался на всех {series['distinct_l1_file_hashes']} точках. "
            f"На всех точках `release_version` L0 — `{series['release_version']}`, `project_revision` L2 — `{series['project_revision']}`. "
            'Стартовый SemVer синтетический; выпуска или настоящего pin не создавали.',
            md_table(('Неизменная область на всех точках', 'SHA‑256 из П3/П4'), (
                ('L0 · типы, относительные имена и байты', f"`{fixed['L0']}`"),
                ('Тестовый манифест L0 · байты', f"`{fixed['L0_manifest']}`"),
                ('L2 · типы, относительные имена и байты', f"`{fixed['L2']}`"))),
            '### Сохранённые решения',
            '`last_profile` в [CHECKOUT.json](CHECKOUT.json) снят напрямую с файла, не из ответа `apply_create`. '
            'Фикстурные Q-01…Q-10 — неактивные `rule`/`draft` под Q-0. Ни `R-2`, ни пользовательский профиль не затронуты.',
            md_table(('profile_revision', 'entry_id', 'entry_sha256 в журнале'), (
                (r['profile_revision'], r['entry_id'], f"`{r['entry_sha256']}`")
                for r in source['last_profile']['journal']['decisions'])),
            '### Находки',
            md_table(('Что установлено', 'basis', 'criterion и предел'), (
                ('Ревизия, запись и решение согласованы на каждом шаге.', 'P01–P10; N05',
                 'Ровно один подготовленный к замене файл с полным новым состоянием. При отказе тот же файл, байты и журнал; не испытание сбоя питания.'),
                ('Два свежих запроса той же записи дают no_change, старый план — нет.', 'P11; N01–N04; X03',
                 'У no_change нет билета; старое согласие не действует. Равной ревизии недостаточно при дрейфе байтов.'),
                ('Нельзя восстановить историю из одного числа.', 'P12; N06–N08',
                 'Голый v2 с revision 4 читается с пустой историей от 4; неполная или несогласованная история в контейнере отклоняется.'),
            )),
            '### Результаты обязательных случаев',
        ])
        observations = {r['id']: r['observed'] for r in source['rows']}

        def result_line(i):
            obs = observations[i]
            if obs['ok']:
                return 'два `no_change` без записи' if i == 'P11-no-change' else f"прочитана ревизия `{obs['status']['profile_revision']}`"
            error = obs['error']
            inner = error.get('schema')
            return (f"`{error['code']}` · `{error['where']}`" +
                    (f" · `{inner['stage']}:{inner['code']}` на `{inner['path']}`" if inner else ''))

        lines.append(md_table(('ID', 'basis', 'Исход'), ((c['id'], c['basis'], result_line(c['id'])) for c in cases)))
    else:
        lines.append('Результат не принят; вывод о выполнении десяти регистраций не сделан.')
    lines += [
        '### Не выполнялось', md_table(('Что', 'Почему'), ((r['what'], r['why']) for r in accepted['not_run'])),
        '## П7–П9. Печать, страница и сверка',
        '[Печать](SEAL.json) содержит принятые наблюдения и конечные отчёт/приёмку; [повтор](REPLAY.json) '
        'сравнивает сохранённые байты без перезаписи. Страница строится отдельно из того же результата. '
        'Из корня снимка: `python3 -B research/106/run.py`; сверка без записи: `python3 -B research/106/run.py --verify-seal`.',
        '[Стратегия v1.8](../STRATEGY.md) и [запись 16 журнала](../strategy/SYNC-LOG.md) фиксируют границу доказанного. '
        'A1–A4, P0 и порядок фаз сохранены; Ф1 остаётся открытой.',
        '## Дальше', spec['next'],
    ]
    return '\n\n'.join(lines) + '\n'


def page(spec, accepted, seal, replay):
    def e(value):
        return escape(str(value))

    def table(headers, rows):
        head = ''.join(f'<th scope="col">{e(h)}</th>' for h in headers)
        body = ''.join('<tr>' + ''.join(f'<td>{e(cell)}</td>' for cell in row) + '</tr>' for row in rows)
        return f'<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'

    ok = accepted['outcome'] == 'accepted' and replay['outcome'] == 'ok'
    series, runs = accepted['series'], accepted['runs']
    measured = '' if series is None else (
        '<h2>Одна история L1</h2><p><strong>' + e(' → '.join(str(n) for n in series['revisions'])) + '</strong></p>'
        + table(('Показатель', 'Измерено'), (('Принятые решения', series['decisions']),
              ('Разные хеши файла L1', series['distinct_l1_file_hashes']),
              ('SemVer L0 · неизменен', series['release_version']),
              ('Ревизия L2 · неизменна', series['project_revision'])))
        + '<p>Байты L0 и L2 сохранились на каждой точке. Два <code>no_change</code> не переписали профиль; старые планы отклонены.</p>')
    return f'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>И-106 · Журнал и ревизии L1</title><style>
:root {{color-scheme:light;--paper:#fcfbf8;--ink:#252422;--muted:#5d6268;--line:#dddcd6;--accent:#285278}}
* {{box-sizing:border-box}} body {{margin:0;background:var(--paper);color:var(--ink);font:1rem/1.55 system-ui,sans-serif}}
header {{background:#edf3f5;border-bottom:1px solid var(--line)}} header>div,main {{max-width:65rem;margin:auto;padding:1.3rem max(1rem,3vw)}}
h1 {{font-size:clamp(2rem,4vw,3rem);line-height:1.12;margin:.35em 0}} h2 {{margin-top:1.9rem}} a {{color:var(--accent)}}
.meta {{color:var(--muted)}} .verdict {{font-weight:700;color:{'#0e5948' if ok else '#963837'}}}
.cards {{display:grid;grid-template-columns:repeat(auto-fit,minmax(12rem,1fr));gap:.7rem}} article {{background:white;padding:1rem;border:1px solid var(--line);border-radius:.6rem}} article strong {{display:block}}
table {{width:100%;border-collapse:collapse}} th,td {{padding:.55rem;text-align:left;vertical-align:top;border-bottom:1px solid var(--line);overflow-wrap:anywhere}} th {{background:#edf3f5}} code {{overflow-wrap:anywhere}}
</style></head><body><header><div><p class="meta">И-106 · {e(spec['phase'])} · {e(spec['priority'])}</p>
<h1>{e(spec['title'])}</h1><p class="verdict">{'Прогон принят' if ok else 'Прогон не принят'}</p>
<p>Локальный журнал принятых регистраций. Только тестовые профили; без активации, переноса и миграции.</p></div></header>
<main><div class="cards"><article><strong><a href="CHECKOUT.json">П3 · checkout</a></strong>{e(counts_line(runs['checkout']['counts']))}</article>
<article><strong><a href="CLEANROOM.json">П4 · без доноров</a></strong>{e(counts_line(runs['cleanroom']['counts']))}</article>
<article><strong><a href="ACCEPTANCE.json">П5 · приёмка</a></strong>{e(counts_line(accepted['counts']))}</article></div>
{measured}
<h2>Не выполнялось</h2>{table(('Работа', 'Почему'), [(r['what'], r['why']) for r in accepted['not_run']])}
<h2>Печать и повтор</h2><p><a href="{e(seal['file'])}">Архив итерации</a> · {e(seal['members'])} файлов · {e(seal['bytes'])} байт ·
<a href="REPLAY.json">повтор: {e(replay['outcome'])}</a></p><p>SHA‑256 <code>{e(seal['sha256'])}</code></p>
<p><a href="REPORT.md">Отчёт и десять решений</a> · <a href="DESIGN.md">Замысел</a> · <a href="../../kit/base/PROFILE-JOURNAL.md">Контракт журнала</a></p>
<p class="meta">{e(spec['next'])}</p></main></body></html>
'''
