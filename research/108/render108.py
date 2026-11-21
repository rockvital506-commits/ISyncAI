"""Отчёт и страница И-108 из наблюдений, не из запланированной формы результата."""
from html import escape
import json
from render import check_rows, counts_line, md_table

_LABELS = {'complete': 'Полная карточка', 'missing_params': 'Уточнение', 'rejected': 'Запрет'}


def missing_line(card):
    return ', '.join(f"{row['field']} ({row['reason']})" for row in card['missing']) or '—'


def report(spec, cases, checkout, acceptance, cards):
    runs, metrics = acceptance['runs'], cards['metrics']
    lines = [
        '# И‑108 — Карточка операции и недостающие параметры',
        f"`{spec['branch']}` · {spec['phase']} · {spec['priority']} · {spec['date']}",
        '## П0–П2. Сверка, замысел, корпус',
        f"До начала: `{spec['baseline']}`. [И‑107](../107/ACCEPTANCE.json) проверила допуск операции к области, но не переход от фразы. "
        '[Замысел](DESIGN.md) отделяет компиляцию карточки от связи с реестрами, плана и записи. '
        '[Контракт карточки](../../kit/base/OPERATION-CARD.md) фиксирует формат, вход и границы языка.',
        f"[CASES.json](CASES.json) содержит {spec['case_counts']['nl']} основных формулировок и "
        f"{spec['case_counts']['control']} обязательных контролей. SHA‑256 корпуса `{spec['casebook_sha256']}`, "
        f"SHA‑256 [пробы](test_cards.py) `{spec['test_sha256']}`. До реализации — ожидаемый отказ импорта `operation_card`. "
        'Эталоны не извлекаются из парсера.',
        '## П3–П5. Два процесса и приёмка',
        'Воспроизведение из корня: `python3 -B research/108/run.py`. '
        'Команда пробы в обоих процессах: `python3 -B -I -S -X utf8 research/108/test_cards.py`.',
        md_table(('Процесс', 'Основные NL', 'Контроли', 'Все обязательные случаи', 'rc'), (
            (label, counts_line(runs[k]['groups']['nl']), counts_line(runs[k]['groups']['control']),
             counts_line(runs[k]['counts']), runs[k]['rc']) for k, label in
            (('checkout', '[П3 · checkout](CHECKOUT.json)'), ('cleanroom', '[П4 · чистая копия](CLEANROOM.json)')))),
        f"ОС: `{acceptance['host_os']}`. П4 запускается из {len(spec['target_inputs'])} входов, без Git, 0.1.36 и ISAI. "
        'Каждую фразу компилируем в двух временных рабочих деревьях: пустом и с валидными v2, одним профилем `Pilot` и '
        'одним локальным контрактом `C-1` на область. Сравниваем карточки, аудируемые события I/O и снимки до/после. '
        'Аудит Python и метки файлов на Linux — наблюдение, не ограничение процессов ОС или доказательство bootstrap.',
        f"[ACCEPTANCE.json](ACCEPTANCE.json): **{acceptance['outcome']}** ({counts_line(acceptance['counts'])}; "
        'ворота и группы работ вне объёма, не число фраз).',
        md_table(('Ворота', 'Статус', 'basis', 'criterion'), check_rows(acceptance)),
        '## П6. Что показал корпус',
    ]
    if metrics is None:
        lines.append('Приёмка отклонена: не публикуем неполный набор как принятые карточки, не собираем новую печать.')
    else:
        outcomes = metrics['nl_outcomes']
        lines += [
            f"**{metrics['nl_phrases']} формулировок → {metrics['nl_cards']} карточек; {metrics['nl_silent_guesses']} молчаливых догадок** "
            f"в замороженном основном корпусе. Из них {outcomes['complete']} полных, {outcomes['missing_params']} с уточнениями и "
            f"{outcomes['rejected']} с явным запретом. `complete` не означает «операция доступна» или «получено согласие».",
            f"В каждом процессе {metrics['compilations_per_run']} компиляции в двух стендах на случай, "
            f"аудируемых I/O-событий: {metrics['audited_io_events_per_run']}; максимум вопросов: {metrics['max_questions']}. "
            'Молчаливая догадка — присвоение неназванной операции или реквизита, не совпадающего с независимым эталоном. '
            'Приёмка строже: сверены также пропуски, коды, типы, текст и вопросы.',
            md_table(('Факт или опровержение', 'basis', 'criterion / граница'), (
                ('Наличие одного профиля/родителя не означает выбор владельца.', 'NL03; NL04; NL05; N02; N06; N07; N19',
                 'Пустой и населённый стенды дают одинаковые карточки. Для всех дочерних видов нужен явный contract. '
                 'NL03 хранит восемь пробелов, выдаёт первые три вопроса; проверка существования ссылки впереди.'),
                ('Посмотреть ≠ создать или активировать.', 'NL06; NL07; N14; N15',
                 'list не требует родителя, при точном просмотре нужен ID; state active — фильтр. Тело реестра не читается.'),
                ('Отсутствие реквизитов ≠ отказ; заполненность ≠ исполнение.', 'NL02; NL10; N05; N17',
                 'L0 получает system_immutable без вопросов, родитель у нового контракта даёт parent. '
                 'Полная карточка для L2 не открывает путь записи.'),
                ('Управляющий ввод отделён от литералов, условий и цитат.', 'NL01; NL11; NL12; N03; N04; N09–N13; N18',
                 'Явные значения тела сохранены. Из префикса ID не выбирается область. «Постоянное» не даёт draft/active. '
                 'Неизвестная конструкция остаётся уточнением, а не домыслом.'),
            )),
            'Во вспомогательной сверке обнаружилось, что «в L1 или в профиле Pilot» могло выбрать профиль; '
            'исправлена обработка альтернатив. Явный запрос родителя для контракта теперь отвергается и при нескольких вариантах. '
            'Это коррекции исполнения; П2 не переписан.',
            '### 12 исходных формулировок',
            '[CARDS.json](CARDS.json) — полные карточки из прогона (включая `params` и тексты вопросов).',
            md_table(('ID', 'Фраза', 'Операция', 'Исход', 'Что уточнить'), (
                (row['id'], c['request'], c['operation'] or '—', c['code'] or c['outcome'], missing_line(c))
                for row in cards['cards'] for c in (row['card'],))),
        ]
        probes = {r['id']: r['observed']['empty']['card'] for r in checkout['result']['rows']}
        lines += ['### Контрольные входы', md_table(('ID', 'basis', 'Результат', 'Что уточнить'), (
            (r['id'], r['basis'], c['code'] or c['outcome'], missing_line(c))
            for r in cases if r['group'] == 'control' for c in (probes[r['id']],)))]
    lines += [
        '### Отдельно: не выполнялось',
        md_table(('Работа', 'Почему'), ((r['what'], r['why']) for r in acceptance['not_run'])),
        '## П7–П9. Печать, страница и сверка',
        '[Печать](SEAL.json) содержит финальные наблюдения, карточки, приёмку и отчёт. [Повтор](REPLAY.json) '
        'сверяет сохранённый архив с пересборкой; `python3 -B research/108/run.py --verify-seal` проверяет '
        'архив, результат повтора и страницу без записи. Размер и SHA‑256 берутся из сборки, не являются подписью.',
        '[Стратегия v1.10](../STRATEGY.md) и [сверка №18](../strategy/SYNC-LOG.md) фиксируют предел: '
        'фраза → явные реквизиты и уточнения, без исполнения. A1–A4, P0, 40 итераций и порядок фаз сохранены; Ф2 не закрыта. '
        'Печать И‑107 после изменения ориентира воспроизводится из `39c83e3`.',
        '## Дальше', spec['next'],
    ]
    return '\n\n'.join(lines) + '\n'


def page(spec, acceptance, data, seal, replay):
    def e(value):
        return escape(str(value))

    runs = acceptance['runs']
    ok = acceptance['outcome'] == 'accepted' and replay['outcome'] == 'ok'
    verdict = 'Проверки приняты' if ok else 'Проверки не приняты'
    metrics = data['metrics'] or {}
    kinds = metrics.get('nl_outcomes', {})
    cards = []
    for row in data['cards']:
        c = row['card']
        label = _LABELS[c['outcome']]
        summary = f"{row['id']} · {label}" + (f" · {c['operation']}" if c['operation'] else '')
        questions = '<ul>' + ''.join(f'<li>{e(r["text"])}</li>' for r in c['questions']) + '</ul>' if c['questions'] else ''
        raw = {k: c[k] for k in ('operation', 'params', 'missing', 'code')}
        cards.append(f'<details{" open" if row["id"] == "NL03" else ""}><summary>{e(summary)}</summary>'
                     f'<blockquote>{e(c["request"])}</blockquote>{questions}'
                     f'<pre>{e(json.dumps(raw, ensure_ascii=False, sort_keys=True, indent=2))}</pre></details>')
    skipped = ''.join(f'<li><strong>{e(r["what"])}</strong> {e(r["why"])}</li>' for r in acceptance['not_run'])
    return f'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>И‑108 · Карточка операции</title><style>
:root {{color-scheme:light;--ink:#223031;--sub:#4e6262;--rule:#d9e5e3;--wash:#eaf5f2;--accent:#17665a}}
* {{box-sizing:border-box}} body {{margin:0;color:var(--ink);background:#fbfdfc;font:1rem/1.55 system-ui,sans-serif}}
header {{background:var(--wash);border-bottom:1px solid var(--rule)}} header>div,main {{max-width:63rem;margin:auto;padding:1.4rem max(1rem,3vw)}}
h1 {{font-size:clamp(2.1rem,5vw,3.4rem);line-height:1.05;margin:.35em 0;text-wrap:balance}} h2 {{margin-top:1.75em}}
a {{color:var(--accent);text-underline-offset:.18em}} .meta {{color:var(--sub)}} .status {{font-weight:700;color:{'#185b46' if ok else '#8b3b39'}}}
.cards {{display:grid;grid-template-columns:repeat(auto-fit,minmax(13rem,1fr));gap:.65rem}} article {{background:white;border:1px solid var(--rule);border-radius:.55rem;padding:.8rem 1rem}} article strong {{display:block}}
details {{background:white;border:1px solid var(--rule);border-radius:.55rem;padding:.65rem .9rem;margin:.5rem 0}} summary {{cursor:pointer;font-weight:650}} summary:focus-visible {{outline:2px solid var(--accent);outline-offset:.25rem}}
blockquote {{margin:.7em 0;border-left:.24rem solid #8cb8af;padding:.2em .8em}} pre {{background:#f1f6f5;border-radius:.35rem;padding:.7rem;white-space:pre-wrap;overflow-wrap:anywhere}} code {{overflow-wrap:anywhere}}
</style></head><body><header><div><p class="meta">И‑108 · {e(spec['phase'])} · {e(spec['priority'])}</p>
<h1>{e(spec['title'])}</h1><p class="status">{verdict}</p>
<p>Карточка отделяет сказанное явно от того, что нужно уточнить. Она не является планом, билетом или записью в реестр.</p></div></header>
<main><div class="cards">
<article><a href="CHECKOUT.json">П3 · checkout</a><strong>{e(counts_line(runs['checkout']['counts']))}</strong></article>
<article><a href="CLEANROOM.json">П4 · чистая копия</a><strong>{e(counts_line(runs['cleanroom']['counts']))}</strong></article>
<article><a href="ACCEPTANCE.json">П5 · приёмка</a><strong>{e(counts_line(acceptance['counts']))}</strong></article></div>
<h2>{e(metrics.get('nl_phrases', '—'))} фраз → {e(metrics.get('nl_cards', '—'))} карточек</h2>
<p>{e(kinds.get('complete', 0))} полных, {e(kinds.get('missing_params', 0))} с уточнениями, {e(kinds.get('rejected', 0))} с запретом.
Молчаливых догадок в корпусе: <strong>{e(metrics.get('nl_silent_guesses', '—'))}</strong>. Не более {e(metrics.get('max_questions', '—'))} вопросов за раз; полный список остаётся в <code>missing</code>.</p>
<p><a href="CARDS.json">Все карточки в JSON</a> · <a href="../../kit/base/OPERATION-CARD.md">Формат и пределы входа</a></p>
{''.join(cards)}
<h2>Не выполнялось</h2><ul>{skipped}</ul>
<h2>Печать и повтор</h2><p><a href="{e(seal['file'])}">Архив с приёмкой</a> · {e(seal['members'])} файлов · {e(seal['bytes'])} байт ·
<a href="REPLAY.json">повтор: {e(replay['outcome'])}</a></p><p>SHA‑256 <code>{e(seal['sha256'])}</code></p>
<p><a href="REPORT.md">Отчёт и основания</a> · <a href="DESIGN.md">Замысел</a> · <a href="../STRATEGY.md">Стратегия</a></p>
<p class="meta">{e(spec['next'])}</p></main></body></html>
'''
