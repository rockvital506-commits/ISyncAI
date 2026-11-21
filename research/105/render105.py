"""П6/П8: отчёт и обзор из одних результатов приёмки."""
from html import escape
from render import counts_line, md_table


def transition(mutation):
    pair = mutation['observed']
    return [(label, pair['before'][key], pair['after'][key]) for key, label in (
        ('profile_revision', 'L1 · profile_revision'), ('project_revision', 'L2 · project_revision'),
        ('release_version', 'L0 · release_version'))]


def report(spec, cases, checkout, result):
    checks, runs, mutation = result['checks'], result['runs'], result['mutation']
    lines = [
        '# И‑105 — Раздельные корни и первая запись в L1',
        f"`{spec['branch']}` · {spec['phase']} · {spec['priority']} · {spec['date']}",
        '## П0–П2. Замысел до реализации',
        f"Сверка от `{spec['baseline']}`: [И‑104](../104/ACCEPTANCE.json) дала форму, а не хранилище. "
        'По [замыслу](DESIGN.md) один порт работает с тремя физическими деревьями и пишет только выбранный L1. '
        '[Хранилище](../../kit/base/STORAGE-V2.md) использует v2 без изменения схемы, без донора и без публичного интерфейса.',
        f"[Список П2](CASES.json): {spec['case_counts']['positive']} положительных и {spec['case_counts']['negative']} "
        f"отрицательных случаев, SHA‑256 `{spec['casebook_sha256']}`. [Проба](test_layout.py) написана до хранилища; "
        'до реализации модуль не импортировался. Ожидания не менялись при исправлении порядка диагностики жёсткой ссылки.',
        '## П3–П5. Прогоны и приёмка',
        md_table(('Прогон', 'Случаи', 'Артефакт'), (
            ('П3 · код из checkout', counts_line(runs['checkout']['counts']), 'CHECKOUT.json'),
            ('П4 · код из отдельного дерева', counts_line(runs['cleanroom']['counts']), 'CLEANROOM.json'))),
        f"Среда: `{result['host_os']}`. П3 и П4 создают свои рабочие каталоги с реальными файлами: "
        'ни один рабочий реестр не используется. Во втором процессе (`-B -I -S -X utf8`) только шесть входных файлов: '
        'без ZIP донора, ISAI, Git и исследовательского харнесса. Испытание `os.replace` включает живую запись '
        'и отдельно контролируемый отказ замены. Это не пилот выделенным тест-агентом.',
        'Нативный 0.1.36 **не запускался**; [стенд И‑103](../103/VERSION-EVIDENCE.json) и [контроль И‑104](../104/DONOR-CONTROL.json) '
        'служат сравнением, а не испытаниями И‑105. Наличие счётчика на стенде ещё не означает рабочее хранилище.',
        f"[ACCEPTANCE.json](ACCEPTANCE.json): **{result['outcome']}**, {counts_line(result['counts'])}. "
        'Это сводка критериев и невыполненных работ, не сумма случаев двух прогонов.',
        md_table(('Ворота', 'Статус', 'basis', 'criterion'),
                 ((r['check'], r['status'], r['basis'], r['criterion']) for r in checks)),
        '## П6. Наблюдения',
    ]
    if mutation is not None:
        before, after = mutation['digest']['before'], mutation['digest']['after']
        lines.extend([
            '### Один фактический переход P02-create',
            md_table(('Из `status`', 'До', 'После повторного чтения'), transition(mutation)),
            'Сохранён `T-2` (`rule` / `draft`) под `T-1`. План не менял файлов. '
            f"Изменён только `{mutation['observed']['changed'][0]}`; повторно прочитанный документ точно равен старому с "
            'одной добавленной записью и `revision + 1`. Идентичность файла изменилась, что соответствует замене.',
            md_table(('SHA‑256 · basis: CHECKOUT.json / CLEANROOM.json', 'До', 'После'),
                     ((name, f'`{before[k]}`', f'`{after[k]}`') for k, name in (
                         ('L0', 'Дерево L0'), ('L0_manifest', 'Тестовый манифест L0'),
                         ('L1', 'Дерево профиля'), ('L2', 'Дерево L2')))),
            'Критерий дерева: те же относительные имена и типы, для каждого файла те же байты. Хеш манифеста '
            'измерен отдельно; он не означает подтверждение pin, подписи или публикации `0.2.0-dev.105`.',
            '### Что уточнили пробы',
            md_table(('Факт', 'basis', 'criterion и граница'), (
                ('Разные строки для каталогов недостаточны.', 'P01, P03, N01–N02, N07–N09',
                 'Три реальные директории с разными идентичностями; вложенность, символьные ссылки и жёсткая ссылка отклонены. '
                 'Оставлен явный альтернативный непересекающийся профиль. ACL и гонки не доказаны.'),
                ('Декларации не подменяют привязку.', 'N03–N06, N12–N13',
                 'Чужая цель, несовпавшие корни, чужой/отсутствующий реестр и невалидная будущая запись не пишут.'),
                ('Показ диффа не авторизует запись.', 'P02, N10–N11',
                 'Нужно отдельное подтверждение актуального плана. В испытании оно сценарное; не выдаёт прав в среде.'),
                ('Неуспешная замена не сохранила половину перехода.', 'N14',
                 'Отказ инъецирован непосредственно в os.replace; временный файл убран, снимок байтов целиком прежний.'),
            )),
            '### Все обязательные случаи',
        ])
        seen = {row['id']: row['observed'] for row in checkout['result']['rows']}
        lines.append(md_table(('ID', 'basis', 'Наблюдение'), (
            (case['id'], case['basis'], 'принят' if (obs := seen[case['id']])['ok'] else
             f"`{obs['error']['code']}` · `{obs['error']['where']}`" +
             (f" · `{s['stage']}:{s['code']}` на `{s['path']}`" if (s := obs['error'].get('schema')) else ''))
            for case in cases)))
    else:
        lines.append('Результат не принят; утверждения о фактическом переходе не сделаны.')
    lines.extend([
        '### Не выполнялось', md_table(('Что', 'Почему'), ((r['what'], r['why']) for r in result['not_run'])),
        '## П7–П9. Печать и сверка',
        '[Печать](SEAL.json) включает конечный отчёт и приёмку. [Повтор](REPLAY.json) проверяет сохранённые архив, '
        'манифест и входы без записи; страница построена из приёмки и метаданных печати и в неё не входит.',
        'Воспроизведение: из снимка этой итерации `python3 -B research/105/run.py`, затем '
        '`python3 -B research/105/run.py --verify-seal`. Изменение входов требует новой печати.',
        'Сверка — [в стратегии](../STRATEGY.md) и [журнале, запись 15](../strategy/SYNC-LOG.md). '
        'P0, A1–A4 и порядок фаз не менялись; Ф1 не закрыта.',
        '## Дальше', spec['next'],
    ])
    return '\n\n'.join(lines) + '\n'


def page(spec, result, seal, replay):
    def e(value):
        return escape(str(value))

    def table(headings, rows):
        head = ''.join(f'<th scope="col">{e(h)}</th>' for h in headings)
        body = ''.join('<tr>' + ''.join(f'<td>{e(v)}</td>' for v in row) + '</tr>' for row in rows)
        return f'<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'

    ok = result['outcome'] == 'accepted' and replay['outcome'] == 'ok'
    runs = result['runs']
    mutation = result['mutation']
    observed = '' if mutation is None else (
        '<h2>Одна запись L1</h2>' + table(('Поле', 'До', 'После'), transition(mutation))
        + f"<p>Только <code>{e(mutation['observed']['changed'][0])}</code> изменился; "
          'байты и состав деревьев L0 и L2 прежние. T-2 сохранён как тестовый черновик.</p>')
    return f'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>И-105 · Раздельные корни</title><style>
:root {{color-scheme:light;--bg:#fbfcfe;--muted:#415873;--line:#d9e4ef;--accent:#28528a;--ink:#152439}}
* {{box-sizing:border-box}} body {{margin:0;font:1rem/1.55 system-ui,sans-serif;background:var(--bg);color:var(--ink)}}
header {{background:#ecf4fe;border-bottom:1px solid var(--line)}} header>div,main {{max-width:66rem;margin:auto;padding:1.4rem max(1rem,3vw)}}
h1 {{font-size:clamp(1.9rem,4vw,3rem);line-height:1.12;margin:.4rem 0}} h2 {{margin-top:1.8rem}} a {{color:var(--accent)}}
.meta {{color:var(--muted)}} .verdict {{font-weight:700;color:{'#195844' if ok else '#9c3232'}}}
.cards {{display:grid;grid-template-columns:repeat(auto-fit,minmax(13rem,1fr));gap:.75rem;margin:1rem 0}}
article {{background:white;border:1px solid var(--line);border-radius:.65rem;padding:.8rem 1rem}} article b {{display:block}}
table {{border-collapse:collapse;width:100%}} th,td {{padding:.48rem .6rem;border-bottom:1px solid var(--line);text-align:left;vertical-align:top;overflow-wrap:anywhere}}
th {{background:#eff5fd}} code {{overflow-wrap:anywhere}}
</style></head><body><header><div><p class="meta">И-105 · {e(spec['phase'])} · {e(spec['priority'])}</p>
<h1>{e(spec['title'])}</h1><p class="verdict">{'Прогон принят' if ok else 'Прогон не принят'}</p>
<p>Реальные файлы L0, L1 и L2 на отдельной тестовой площадке. Без работы с пользовательскими реестрами.</p></div></header>
<main><div class="cards">
<article><b><a href="CHECKOUT.json">П3 · checkout</a></b>{e(counts_line(runs['checkout']['counts']))}</article>
<article><b><a href="CLEANROOM.json">П4 · без доноров</a></b>{e(counts_line(runs['cleanroom']['counts']))}</article>
<article><b><a href="ACCEPTANCE.json">П5 · приёмка</a></b>{e(counts_line(result['counts']))}</article></div>
{observed}
<h2>Границы доказательства</h2>{table(('Не выполнялось', 'Почему'), [(r['what'], r['why']) for r in result['not_run']])}
<h2>Печать и повтор</h2><p><a href="{e(seal['file'])}">ZIP итерации</a> · {e(seal['members'])} файлов · {e(seal['bytes'])} байт ·
<a href="REPLAY.json">повтор: {e(replay['outcome'])}</a></p><p>SHA‑256 <code>{e(seal['sha256'])}</code></p>
<p><a href="REPORT.md">Отчёт с диагностикой</a> · <a href="DESIGN.md">Замысел</a> · <a href="../../kit/base/STORAGE-V2.md">Описание хранилища</a></p>
<p class="meta">{e(spec['next'])}</p></main></body></html>
'''
