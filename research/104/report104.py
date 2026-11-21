"""П6 и П8: отчёт и страница из одних наблюдений, без повторного счёта вручную."""
from html import escape
from render import counts_line, md_table


def findings():
    return [
        ('F1', 'Известное, но чужое authority не согласуется с областью, а область загрузки задаётся извне.',
         'N03-context, N04-known-wrong', 'shape:area_mismatch и shape:authority_area; входы прежние.',
         'Допустимая декларация не выдаёт прав; в И-105 читатель передаёт expected_area, И-107 проверяет операцию.'),
        ('F2', 'Ссылка на настоящий контракт вне данного документа — не существующая локальная связь; префикса пути недостаточно.',
         'N08-foreign, V03-scope-self, N07-sibling', 'Внешняя ссылка и docs2/guide отвергнуты, точный scope принят.',
         'Раздельный формат не ищет родителя в других слоях. Для старых ссылок И-131 нужен явный разбор.'),
        ('F3', 'Строгое чтение и проверка типов нужны независимо от прав и связей.',
         'N19-duplicate-json, N05-bool, N05-decimal, N16-floating-tag',
         'Дубликат отклонён; логические и вещественные значения не приняты за целочисленный счётчик.',
         'Адаптер разбирает через validate_json и не заменяет отсутствующее поле догадкой.'),
        ('F4', 'Лексическое совпадение или вложенность roots обнаруживаются, даже когда физического дерева нет.',
         'N14-declared-equal, N14-declared-nested, V05-other-root',
         'Совпадающие/вложенные отвергнуты; похожее имя kit-extra принято.',
         'Не считать это проверкой реальной раскладки, прав, ссылок и регистрозависимости ФС.'),
        ('F5', 'Подготовительный корпус полезен и без рабочего профиля; отрицания проверяются по наблюдаемым ответам.',
         'V01–V02, CHECKOUT.json, CLEANROOM.json, test_acceptance.py',
         'Все обязательные ID в двух процессах; черновик не изменился; ложные пропуски шлюз отклонил.',
         'Не активировать протокол и не считать сохранение/исполнение доказанным. Следующий шаг — реальная раскладка.'),
    ]


def report(spec, result, casebook, checkout, clean, donor):
    cases = result['target_cases']
    rows = checkout['result']['rows'] if result['outcome'] == 'accepted' else []
    observed = {row['id']: row['observed'] for row in rows}
    lines = [
        '# И‑104 — Самостоятельная схема v2',
        f"`{spec['branch']}` · {spec['phase']} · {spec['priority']} · {spec['date']}",
        '## П0–П2. Замысел и пределы',
        f"Исходная сверка: {spec['strategy_before']}. [Замысел](DESIGN.md) и [обязательные испытания](CASES.json) "
        'записаны до валидатора. Подготовительная проверка в этот момент прошла пять тестов шлюза, '
        'целевая проба закономерно не импортировала ещё не написанный `schema_v2`.',
        f"[Исполнимый контракт](../../kit/base/schema_v2.py) и [формат](../../kit/base/SCHEMA-V2.md). "
        f"Обязательных случаев на прогон: **{cases['required_per_run']}** ({cases['positive']} положительных, "
        f"{cases['negative']} отрицательных). SHA‑256 списка П2: `{spec['casebook_sha256']}`.",
        '## П3–П4. Два целевых прогона и отдельный донорский контроль',
        md_table(('Прогон', 'Результат', 'Свидетельство'), (
            ('П3 · checkout', f"{counts_line(cases['checkout'])}; rc {checkout['rc']}", 'CHECKOUT.json'),
            ('П4 · чистая копия', f"{counts_line(cases['cleanroom'])}; rc {clean['rc']}", 'CLEANROOM.json'),
            ('Донор 0.1.36', 'совпал со старым эталоном' if donor['matches_saved_evidence'] else 'не совпал',
             'DONOR-CONTROL.json; не целевые тесты'),
        )),
        'Целевой процесс запускается с `-B -I -S`. В чистую копию входят только пять файлов '
        'из `target_inputs`, **без ZIP 0.1.36, ISAI и исследовательского харнесса**. '
        'Сравнены SHA‑256 входов, список файлов и фактические результаты. Это независимый повтор процесса, '
        'а не независимый тест-агент и не гарантия прав среды.',
        'Контроль донора отдельно запускает `check_preparation.py`: сверяет его архив и проверяет `install → connect → create` '
        'черновика в L2 без калибровки, отказ для неизвестного родителя и неизменность L0 **донора**. '
        'Это не `compat --old` и не повтор полного набора 0.1.36.',
        '## П5. Приёмка',
        f"[ACCEPTANCE.json](ACCEPTANCE.json): **{result['outcome']}**, {counts_line(result['counts'])}. "
        'Здесь считаются ворота приёмки и вынесенные работы, а не сумма двух целевых прогонов.',
        md_table(('Проверка', 'Статус', 'basis', 'criterion'),
                 [(row['check'], row['status'], row['basis'], row['criterion']) for row in result['checks']]),
        '## П6. Находки',
    ]
    if rows:
        lines.append(md_table(('ID', 'Наблюдение', 'basis', 'criterion', 'Следствие'), findings()))
        lines.append('### Обязательные случаи (результаты совпали в обеих копиях)')
        lines.append(md_table(('ID', 'Покрытие исходного требования', 'Наблюдение'), (
            (row['id'], row['covers'], 'принят' if observed[row['id']]['ok'] else
             f"отказ `{observed[row['id']]['stage']}:{observed[row['id']]['code']}` "
             f"на `{observed[row['id']]['path'] or '<root>'}`") for row in casebook['cases'])))
    else:
        lines.append('Целевой результат не принят; выводы о прохождении случаев не делаются.')
    lines += ['### Не выполнялось', md_table(('Что', 'Где проверяется'), [(row['what'], row['why']) for row in result['not_run']]),
              '## П7–П9. Печать, страница и сверка',
              '[Печать](SEAL.json) включает замысел, код, входы и принятый отчёт с приёмкой. '
              '[Повтор](REPLAY.json) сравнивает сохранённые байты без их замены. Страница производная и не входит в печать. '
              'Сверка: [стратегия v1.6](../STRATEGY.md) и [журнал](../strategy/SYNC-LOG.md), запись 14. '
              'Состав P0, A1–A4 и граф фаз не изменены.',
              'Воспроизведение из корня снимка Git этой итерации: `python3 -B research/104/run.py`; '
              'проверка уже сохранённой печати и страницы без записи: `python3 -B research/104/run.py --verify-seal`.',
              '## Дальше', spec['next']]
    return '\n\n'.join(lines) + '\n'


def page(spec, result, donor, seal, replay):
    def html(value):
        return escape(str(value))

    def table(headers, rows):
        head = ''.join(f'<th scope="col">{html(h)}</th>' for h in headers)
        body = '\n'.join('<tr>' + ''.join(f'<td>{html(cell)}</td>' for cell in row) + '</tr>' for row in rows)
        return f'<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'

    ok = result['outcome'] == 'accepted' and replay['outcome'] == 'ok'
    cases = result['target_cases']
    donor_status = 'совпал с эталоном' if donor['matches_saved_evidence'] else 'не совпал с эталоном'
    return f'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>И-104 · Схема v2</title><style>
:root {{color-scheme:light;--ink:#162020;--muted:#486064;--line:#d7e1de;--fine:#edf5f2;--accent:#0e6555;}}
* {{box-sizing:border-box}} body {{margin:0;background:#fbfdfc;color:var(--ink);font:1rem/1.55 system-ui,sans-serif}}
header {{border-bottom:1px solid var(--line);background:var(--fine)}} header>div,main {{max-width:67rem;margin:auto;padding:1.5rem max(1rem,3vw)}}
h1 {{margin:.25rem 0;font-size:clamp(2rem,4vw,3rem);line-height:1.13}} h2 {{margin-top:2rem}} .meta {{color:var(--muted)}}
a {{color:var(--accent)}} .verdict {{font-weight:700;color:{'#0e6555' if ok else '#952b2b'}}}
.cards {{display:grid;grid-template-columns:repeat(auto-fit,minmax(12rem,1fr));gap:.7rem;margin:1rem 0}}
article {{padding:1rem;background:#fff;border:1px solid var(--line);border-radius:.5rem}} article strong {{display:block}}
table {{border-collapse:collapse;width:100%;font-size:.95rem}} th,td {{padding:.55rem;text-align:left;border-bottom:1px solid var(--line);vertical-align:top;overflow-wrap:anywhere}} th {{background:var(--fine)}} code {{overflow-wrap:anywhere}}
</style></head><body><header><div><p class="meta">И-104 · {html(spec['phase'])} · {html(spec['priority'])}</p>
<h1>Самостоятельная схема v2</h1><p class="verdict">{'Прогон принят' if ok else 'Прогон не принят'}</p>
<p>Контракт данных и связи L0/L1/L2. Без установки, мутации профиля или активации правил.</p></div></header>
<main><div class="cards">
<article><a href="CHECKOUT.json"><strong>П3 · checkout</strong></a>{html(counts_line(cases['checkout']))}</article>
<article><a href="CLEANROOM.json"><strong>П4 · без доноров</strong></a>{html(counts_line(cases['cleanroom']))}</article>
<article><a href="DONOR-CONTROL.json"><strong>Контроль 0.1.36</strong></a>{html(donor_status)} · отдельно</article></div>
<p>На каждый целевой прогон: {html(cases['required_per_run'])} обязательных случаев,
{html(cases['positive'])} положительных и {html(cases['negative'])} отрицательных. R-2 проверяется как черновик.</p>
<h2>Ворота приёмки</h2><p>{html(counts_line(result['counts']))} · <a href="ACCEPTANCE.json">Машинная приёмка</a></p>
{table(('Проверка', 'Статус', 'Критерий'), [(r['check'], r['status'], r['criterion']) for r in result['checks']])}
<h2>Не выполнялось</h2>{table(('Что', 'Почему'), [(r['what'], r['why']) for r in result['not_run']])}
<h2>Печать и повтор</h2><p><a href="{html(seal['file'])}">Архив итерации</a> · {html(seal['members'])} файлов · {html(seal['bytes'])} байт ·
<a href="REPLAY.json">повтор: {html(replay['outcome'])}</a></p><p>SHA‑256 <code>{html(seal['sha256'])}</code></p>
<p><a href="REPORT.md">Отчёт с находками</a> · <a href="DESIGN.md">Замысел</a> · <a href="../../kit/base/SCHEMA-V2.md">Спецификация</a></p>
<p class="meta">{html(spec['next'])}</p></main></body></html>
'''
