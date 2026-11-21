"""Представления И-107: матрица и основания из фактических результатов П3–П5."""
from html import escape
from render import check_rows, counts_line, md_table

_AREAS = ('L0', 'L1', 'L2')
_LABELS = {'available': 'Доступно', 'planned': 'Не реализовано', 'forbidden': 'Запрещено'}
_INVARIANTS = (
    ('A1', 'profile_root_conflict', 'A1-equal, A1-system-nested, A1-project-nested',
     'Совпадение и вложенность корней отвергнуты, исходные файлы без изменений.'),
    ('A2', 'system_immutable', 'Шесть мутаций M-…-L0; A2-claim-L0, A2-apply-L0, N-claim-L1',
     'Мутации L0 запрещены; объявление authority и билет от другой цели не меняют маршрут.'),
    ('A3', 'rule_conflict', 'P-A3-report, P-A3-same-area, A3-plan, A3-apply-drift; контроли P-A3-*',
     'Обе записи на каждое пересечение с разными значениями; при конфликте новая запись не сохраняется.'),
    ('A4', 'parent', 'A4-no-field, A4-null, A4-dangling, A4-wrong-kind, A4-foreign, A4-scope, A4-contract-parent',
     'Причина входа или связи сохранена в schema.stage/code/path. Внешний ID и ложный префикс не подходят.'),
)


def matrix_rows(data):
    matrix = data['matrix'] or {}
    principal = ('read', 'create', 'list')
    order = [*(op for op in principal if op in matrix), *sorted(matrix.keys() - set(principal))]
    return ((op, [matrix[op][area] for area in _AREAS]) for op in order)


def cell_label(op, area, row):
    if row['code']:
        return row['code']
    return 'available: rule / draft' if (op, area) == ('create', 'L1') else row['state']


def report(spec, cases, checkout, accepted, data):
    runs = accepted['runs']
    lines = [
        '# И‑107 — Допуск операций и коды A1–A4',
        f"`{spec['branch']}` · {spec['phase']} · {spec['priority']} · {spec['date']}",
        '## П0–П2. Сверка и замысел',
        f"До начала: `{spec['baseline']}`. [И‑106](../106/ACCEPTANCE.json) приняла десять регистраций L1 с журналом. "
        'В И‑107 проверяем разницу между инвариантом и отсутствием обработчика, не расширяя набор мутаций. '
        '[Замысел](DESIGN.md) фиксирует ожидаемые коды, путь согласованной записи и предел проверки A3. '
        '[Контракт порта](../../kit/base/OPERATION-MATRIX.md) описывает его внутренние вызовы.',
        f"[CASES.json](CASES.json): {spec['case_counts']['positive']} положительных и {spec['case_counts']['negative']} отрицательных случаев, "
        f"SHA‑256 `{spec['casebook_sha256']}`. SHA‑256 [пробы](test_policy.py) `{spec['test_sha256']}`. "
        'Эталоны не считываются из кода допуска. До реализации проба остановилась на отсутствии `check_operation`.',
        '## П3–П5. Измерение и приёмка',
        'Из корня снимка: `python3 -B research/107/run.py`. Целевой процесс: `python3 -B -I -S -X utf8 research/107/test_policy.py`.',
        md_table(('Среда', 'Обязательные случаи', 'rc', 'Наблюдения'), (
            ('П3 · checkout', counts_line(runs['checkout']['counts']), runs['checkout']['rc'], '[CHECKOUT.json](CHECKOUT.json)'),
            ('П4 · чистая копия', counts_line(runs['cleanroom']['counts']), runs['cleanroom']['rc'], '[CLEANROOM.json](CLEANROOM.json)'))),
        f"ОС: `{accepted['host_os']}`. В каждом процессе отдельные физические фикстуры. "
        f"В П4 только {len(spec['target_inputs'])} входов из [ITERATION.json](ITERATION.json), без Git, 0.1.36 и ISAI. "
        'Не используются рабочие профили или данные `R-2`.',
        f"[ACCEPTANCE.json](ACCEPTANCE.json): **{accepted['outcome']}** ({counts_line(accepted['counts'])}; это ворота и группы отложенных работ).",
        md_table(('Ворота', 'Статус', 'basis', 'criterion'), check_rows(accepted)),
        '## П6. Наблюдения',
    ]
    if data['matrix'] is not None:
        counts = data['cells']
        lines += [
            f"[Машинная матрица](MATRIX.json) из `operation_matrix()`: **{counts['available']} доступны**, "
            f"**{counts['planned']} ещё не реализованы**, **{counts['forbidden']} запрещены**. "
            'Проверены реальные внутренние чтения, маршрут `create` при плане и применении и общий ответ на каждую ячейку. '
            'Для `planned` не засчитан обработчик. Диагностические `status` / `profile_history` / `report_conflicts` не имеют цели записи.',
            md_table(('Операция', *_AREAS), ((f'`{op}`', *(f'`{cell_label(op, a, c)}`' for a, c in zip(_AREAS, cells)))
                                              for op, cells in matrix_rows(data))),
            md_table(('Инвариант', 'Код', 'basis · ID в двух прогонах', 'criterion'),
                     ((i, f'`{code}`', basis, criterion) for i, code, basis, criterion in _INVARIANTS)),
        ]
        observations = {r['id']: r['observed'] for r in checkout['result']['rows']}
        positive = observations['M-create-L1']
        before, after = positive['profile_revision']
        first, last = positive['project_revision']
        example = observations['P-A3-report']['conflicts'][0]
        lines += [
            f"**Положительный путь (`M-create-L1`, `P-A3-draft-write`).** Меняется только `{positive['changed'][0]}`. "
            f"Ревизия L1 {before} → {after} и одно согласованное решение; L2 {first} → {last}. "
            'У L0 прежние SemVer и хеши дерева и тестового манифеста. Остальные случаи не оставляют изменённых путей или замены файла профиля.',
            f"**Пример A3 (`P-A3-report`).** Ключ `{example['key']}`, пересечение `{example['scope']}`. "
            'В этом случае обнаружены две пары; ниже первая. Строки не обозначают старшинство.',
            md_table(('Область', 'ID', 'scope', 'Значение', 'Формулировка'),
                     ((e['area'], e['id'], e['scope'], e['value'], e['text']) for e in example['entries'])),
            '### Находки и предел',
            md_table(('Факт или опровержение', 'basis', 'criterion / следствие'), (
                ('Нет записи L2 сейчас ≠ L2 неизменяем по модели.', 'M-create-L2; N-apply-L2; M-create-L0; A2-apply-L0',
                 'operation_unavailable различим с system_immutable; L2 не получает обработчик только от известного имени.'),
                ('Корректный JSON не гарантирует допустимый дифф.', 'N-claim-L1; A4-foreign; A4-scope',
                 'Чужое полномочие и неверная связь дают разные причины, сохраняющие путь проверки v2.'),
                ('Актуальный L1 не гарантирует, что не появилось противоречие в другой области.', 'A3-apply-drift; P-A3-draft-write',
                 'После плана поменялась только входная фикстура L2; apply не меняет ни одного файла. '
                 'Черновик без действующего конфликта сохраняется; не доказаны активация, смысловое сравнение и И‑116.'),
            )),
            '### Диагностики вне ячеек',
            md_table(('ID', 'basis', 'Результат'), ((c['id'], c['basis'], observation(observations[c['id']]))
                                                       for c in cases if 'cell' not in c)),
        ]
    else:
        lines.append('Приёмка отклонена; по неполному результату матрица не публикуется и новая печать не создаётся.')
    lines += [
        '### Не выполнялось', md_table(('Что', 'Почему'), ((r['what'], r['why']) for r in accepted['not_run'])),
        '## П7–П9. Печать, страница и сверка',
        '[SEAL.json](SEAL.json) фиксирует архив с финальными приёмкой, матрицей и отчётом. [REPLAY.json](REPLAY.json) '
        'фиксирует совпадение с повторной сборкой. `python3 -B research/107/run.py --verify-seal` проверяет архив, запись повтора '
        'и страницу без перезаписи. Печать — проверка байтов, не подпись или свидетельство предоставленных прав.',
        '[Стратегия v1.9](../STRATEGY.md) и [сверка №17](../strategy/SYNC-LOG.md) ограничивают результат моделью и внутренним портом Ф1. '
        'A1–A4, P0, порядок фаз и определение пригодности не изменены. X07/X08 не приняты этой итерацией. '
        'Исторические печати И‑105 и И‑106 сверяются из снимков `8e03563` и `23b320b`: теперь A4 в порте даёт '
        '`parent` вместо общего `invalid_entry`, а прежние ожидания не переписываются.',
        '## Дальше', spec['next'],
    ]
    return '\n\n'.join(lines) + '\n'


def observation(row):
    if not row['ok']:
        error = row['error']
        text = f"`{error['code']}` · `{error['where']}`"
        if inner := error.get('schema'):
            text += f" · `{inner['stage']}:{inner['code']}` на `{inner['path']}`"
        if details := error.get('details'):
            text += f" · пар: {len(details['conflicts'])}"
        return text
    if 'entry_id' in row:
        return f"сохранён `rule/draft` `{row['entry_id']}`, ревизия 0 → 1"
    return f"пар: {len(row['conflicts'])}; чтение без записи"


def page(spec, accepted, data, seal, replay):
    def e(text):
        return escape(str(text))

    def table(headers, body):
        head = ''.join(f'<th scope="col">{e(h)}</th>' for h in headers)
        return f'<div class="scroll"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'

    def text_rows(rows):
        return ''.join('<tr>' + ''.join(f'<td>{e(v)}</td>' for v in row) + '</tr>' for row in rows)

    def cell(op, area, row):
        state = row['state']
        return f'<td><strong class="{e(state)}">{e(_LABELS[state])}</strong><br><code>{e(cell_label(op, area, row))}</code></td>'

    body = ''.join(f'<tr><th scope="row"><code>{e(op)}</code></th>' +
                   ''.join(cell(op, a, r) for a, r in zip(_AREAS, cells)) + '</tr>' for op, cells in matrix_rows(data))
    runs = accepted['runs']
    ok = accepted['outcome'] == 'accepted' and replay['outcome'] == 'ok'
    cards = ('<div class="cards">' + ''.join(f'<article><a href="{href}">{e(title)}</a><strong>{e(counts_line(counts))}</strong></article>'
            for href, title, counts in (('CHECKOUT.json', 'П3 · checkout', runs['checkout']['counts']),
                                        ('CLEANROOM.json', 'П4 · чистая копия', runs['cleanroom']['counts']),
                                        ('ACCEPTANCE.json', 'П5 · приёмка', accepted['counts']))) + '</div>')
    badge = 'pass' if ok else 'fail'
    verdict = 'Проверки приняты' if ok else 'Проверки не приняты'
    return f'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>И‑107 · Операции и области</title><style>
:root {{color-scheme:light;--ink:#202a31;--muted:#515f68;--line:#dce4e8;--accent:#174f76;--wash:#eff5f7}}
* {{box-sizing:border-box}} body {{margin:0;color:var(--ink);background:#fbfcfc;font:1rem/1.55 system-ui,sans-serif}}
header {{background:var(--wash);border-bottom:1px solid var(--line)}} header>div,main {{max-width:68rem;margin:auto;padding:1.5rem max(1rem,3vw)}}
h1 {{font-size:clamp(2rem,4vw,3.3rem);line-height:1.12;margin:.4em 0}} h2 {{margin-top:1.8em}} h1,h2 {{text-wrap:balance}}
a {{color:var(--accent);text-underline-offset:.17em}} .meta {{color:var(--muted)}} .badge {{display:inline-block;font-weight:700;border:1px solid currentColor;border-radius:2em;padding:.22em .8em}}
.pass,.available {{color:#1a624d}} .fail,.forbidden {{color:#8c3b3c}} .planned {{color:#79510e}}
.cards {{display:grid;grid-template-columns:repeat(auto-fit,minmax(13rem,1fr));gap:.65rem}}
article {{padding:.9rem 1.05rem;background:#fff;border:1px solid var(--line);border-radius:.55rem}} article strong {{display:block;margin-top:.35rem}}
.scroll {{overflow-x:auto}} table {{width:100%;border-collapse:collapse;background:#fff}} th,td {{padding:.65rem;text-align:left;vertical-align:top;border-bottom:1px solid var(--line)}}
thead th {{background:var(--wash)}} code {{font-size:.92em;overflow-wrap:anywhere}} .scroll td {{min-width:8rem}}
</style></head><body><header><div><p class="meta">И‑107 · {e(spec['phase'])} · {e(spec['priority'])}</p>
<h1>{e(spec['title'])}</h1><span class="badge {badge}">{verdict}</span>
<p>Внутренний порт v2: чтение трёх областей и одна поддержанная мутация — создание чернового правила L1. Запрет и отсутствие реализации различаются.</p></div></header>
<main>{cards}
<h2>Операция × область</h2>{table(('Операция', *_AREAS), body)}
<p><a href="MATRIX.json">Машинная матрица</a> · <a href="../../kit/base/OPERATION-MATRIX.md">Контракт допуска</a></p>
<h2>Четыре причины отказа</h2>{table(('Инвариант', 'Код', 'Проверено'), text_rows((i, code, criterion) for i, code, _, criterion in _INVARIANTS))}
<p>Противоречия показаны парами, без эффективного набора, выбора победителя или разрешения. A3 здесь — только явный ключ, разные значения и пересечение scope.</p>
<h2>Не выполнялось</h2>{table(('Работа', 'Почему'), text_rows((r['what'], r['why']) for r in accepted['not_run']))}
<h2>Печать и повтор</h2><p><a href="{e(seal['file'])}">Архив с приёмкой</a> · {e(seal['members'])} файлов · {e(seal['bytes'])} байт ·
<a href="REPLAY.json">повтор: {e(replay['outcome'])}</a></p><p>SHA‑256 <code>{e(seal['sha256'])}</code></p>
<p><a href="REPORT.md">Отчёт и основания</a> · <a href="DESIGN.md">Замысел</a> · <a href="../STRATEGY.md">Стратегия</a></p>
<p class="meta">{e(spec['next'])}</p></main></body></html>
'''
