"""Человекочитаемые представления машинных артефактов П3–П8."""
from html import escape


def counts_line(counts):
    return ' / '.join(f"{counts[key]} {key}" for key in ('pass', 'fail', 'not run'))


def step_result(step):
    if step.get('error'):
        return step['error']
    if step.get('health'):
        return step['health']
    if 'ids' in step:
        return f"контрактов: {step['contracts']}; активных записей: {step['active']} ({', '.join(step['ids'])})"
    return 'успех' if step['rc'] == 0 else 'ошибка (нет кода в JSON)'


def baseline_rows(base):
    return [
        ('Выпуск', base['release']), ('ZIP: байт / членов', f"{base['zip']['bytes']} / {base['zip']['members']}"),
        ('SHA-256 выпуска', base['zip']['sha256']), ('Дерево: файлов', base['tree']['files']),
        ('Дерево: digest', base['tree']['tree_digest']),
        ('Команд / операций', f"{len(base['commands'])} / {len(base['ops'])}"),
        ('Digest baseline', base['digest']),
    ]


def check_rows(result):
    return [(c['check'], c['status'], c['basis'], c['criterion']) for c in result['checks']]


def md_table(headers, rows):
    def line(values):
        return '| ' + ' | '.join(str(value).replace('|', r'\|').replace('\n', ' ') for value in values) + ' |'
    return '\n'.join([line(headers), line(['---'] * len(headers)), *(line(row) for row in rows)])


def render_report(spec, ctx, result):
    base, room, suite = ctx['baseline'], ctx['cleanroom'], ctx['release_tests']
    plan = [
        ('Цель', spec['goal']), ('Гипотеза', spec['hypothesis']),
        ('Изменяемая поверхность', ', '.join(f'`{p}`' for p in spec['touches'])),
        ('Что НЕ трогаем', ', '.join(f'`{p}`' for p in spec['not_touched'])),
        ('Ожидаемые коды отказа', ', '.join(f'`{code}`' for code in spec['expected_codes'])),
        ('Критерий успеха', spec['success']), ('Критерий провала', spec['failure']), ('Откат', spec['rollback']),
    ]
    chunks = [
        f"# Итерация И-{spec['id']} — «{spec['title']}»",
        f"Ветка: `{spec['branch']}` · Дата: {spec['date']} · {spec['phase']} · {spec['priority']}",
        '## П0–П1. Сверка и замысел до прогона\n\nСм. [DESIGN.md](DESIGN.md) и [ITERATION.json](ITERATION.json).',
        md_table(('Пункт', 'Содержание'), plan),
        '## П2. Испытания\n\nЭталоны И‑101 и негативные сценарии заданы в `ITERATION.json` и `test_harness.py`. '
        f"Воспроизведение фикстур: `python3 -B research/{spec['id']}/test_harness.py`.",
        '## П3. Прогон в репозитории\n\n'
        f"Харнесс из рабочего дерева измеряет отслеживаемый архив `{spec['artifact_zip']}`. "
        'Машинные данные — `BASELINE.json`; выпуск не пересобирался и не менялся.',
        md_table(('Показатель', 'Значение'), baseline_rows(base)),
        '## П4. Прогон в чистой копии\n\nСвежая распаковка, пустой проект `A`, без калибровки.',
        md_table(('Шаг', 'rc', 'Результат'), [(s['step'], s['rc'], step_result(s)) for s in room['steps']]),
        f"Digest точек замера (`CLEANROOM.json`): `{room['checkpoints_digest']}`.",
        f"Отдельная распаковка: `kit/tests/test_contract.py` → **{counts_line(suite['totals'])}** "
        f"(rc {suite['rc']}, inconclusive: {suite['totals']['inconclusive']}). "
        'Это офлайн-регрессия выпуска, не проверка живой модели; её пропуски в `RELEASE-TESTS.json`.',
        '## П5. Приёмка\n\n'
        f"`ACCEPTANCE.json`: **{result['outcome']}**, {counts_line(result['counts'])}. "
        'Счётчики харнесса и набора выпуска ведутся отдельно.',
        md_table(('Проверка', 'Статус', 'basis', 'criterion'), check_rows(result)),
        '## П6. Находки',
        md_table(('#', 'Находка', 'basis', 'criterion', 'Следствие'),
                 [(f['id'], f['text'], f['basis'], f['criterion'], f['effect']) for f in spec['findings']]),
        '### Что не выполнялось (not run)',
        md_table(('Что', 'Почему'), [(row['what'], row['why']) for row in result['not_run']])
        if result['not_run'] else 'Все проверки в заданной области выполнены.',
        '## П7–П8. Печать и страница\n\n'
        'Размер и хеш — только в `SEAL.json` и на странице. `REPLAY.json` фиксирует сверку '
        'сохранённого ZIP и манифеста с повторной сборкой по итоговым файлам. '
        'Этот отчёт входит в печать и после неё не перезаписывается.',
        f"## Следующая итерация\n\n{spec['next']}",
    ]
    return '\n\n'.join(chunks) + '\n'


def render_page(spec, ctx, result, seal, replay):
    def e(value):
        return escape(str(value))

    def table(headers, rows):
        head = ''.join(f'<th scope="col">{e(h)}</th>' for h in headers)
        body = '\n'.join('<tr>' + ''.join(f'<td>{e(c)}</td>' for c in row) + '</tr>' for row in rows)
        return f'<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'

    base, room, suite = ctx['baseline'], ctx['cleanroom'], ctx['release_tests']
    passed = result['outcome'] == 'accepted' and replay['outcome'] == 'ok'
    release_skips = [(row['case'], row['test'], row['reason']) for row in suite['not_run']]
    return f"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>И-{e(spec['id'])} — {e(spec['title'])}</title>
<style>
body {{ font: 1rem/1.55 system-ui, sans-serif; margin: 2rem auto; max-width: 70rem; padding: 0 1rem; color: #162534; }}
h1 {{ margin-bottom: 0; }} h2 {{ margin: 1.8rem 0 .45rem; }}
.meta {{ color: #486074; }} .verdict {{ padding: .65rem .9rem; border-left: 4px solid; background: #eef5f9; }}
.ok {{ color: #135333; }} .bad {{ color: #8a2525; }}
table {{ width: 100%; border-collapse: collapse; font-size: .92rem; }}
th, td {{ border-bottom: 1px solid #dce5ed; padding: .42rem .5rem; text-align: left; vertical-align: top; overflow-wrap: anywhere; }}
th {{ background: #f1f5f9; }} code {{ overflow-wrap: anywhere; }}
</style></head><body>
<header><h1>И-{e(spec['id'])} — {e(spec['title'])}</h1>
<p class="meta">{e(spec['phase'])} · {e(spec['priority'])} · {e(spec['date'])}</p></header>
<main><p class="verdict {'ok' if passed else 'bad'}"><strong>{'Прогон принят' if passed else 'Прогон не принят'}</strong> ·
{e(counts_line(result['counts']))} · повтор печати: <code>{e(replay['outcome'])}</code></p>
<p>{e(spec['goal'])} <a href="REPORT.md">Полный отчёт</a>.</p>
<h2>Инвентарь выпуска</h2>{table(('Показатель', 'Значение'), baseline_rows(base))}
<h2>Чистая копия без калибровки</h2>
{table(('Шаг', 'rc', 'Результат'), [(s['step'], s['rc'], step_result(s)) for s in room['steps']])}
<p>Digest точек замера: <code>{e(room['checkpoints_digest'])}</code></p>
<h2>Приёмка харнесса</h2>{table(('Проверка', 'Статус', 'Основание', 'Критерий'), check_rows(result))}
<h2>Офлайн-тесты выпуска</h2><p>{e(counts_line(suite['totals']))} (rc {e(suite['rc'])}) · <a href="RELEASE-TESTS.json">Машинный результат</a>.</p>
{table(('Пропуск', 'Тест', 'Причина'), release_skips) if release_skips else ''}
<h2>Печать</h2><p><a href="{e(seal['file'])}">Скачать ZIP</a> · {e(seal['members'])} файлов · {e(seal['bytes'])} байт</p>
<p>SHA-256: <code>{e(seal['sha256'])}</code> · <a href="REPLAY.json">Протокол повтора</a></p>
<h2>Находки</h2>{table(('№', 'Факт', 'Основание', 'Изменение'), [(f['id'], f['text'], f['basis'], f['effect']) for f in spec['findings']])}
<h2>Что не выполнялось в этой итерации</h2>
{table(('Что', 'Почему'), [(row['what'], row['why']) for row in result['not_run']]) if result['not_run'] else '<p>Нет пропусков.</p>'}
<p class="meta">Дальше: {e(spec['next'])}</p></main>
</body></html>
"""
