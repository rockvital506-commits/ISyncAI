"""Страница и отчёт И-111 из принятых наблюдений без билетов."""
from html import escape

from render import check_rows, counts_line, md_table

MODES = {'permanent': 'Постоянное', 'temporary': 'Временное', 'proposal': 'Предложение',
         'hypothesis': 'Гипотеза', 'ambiguous': 'Неясный режим', 'boundary': 'Граница грамматики'}
OUTCOMES = {'planned': 'Дифф', 'listed': 'Просмотр', 'missing_params': 'Уточнение', 'non_registry': 'Вне реестра'}


def report(spec, cases, red, checkout, acceptance, data):
    runs = acceptance['runs']; metrics = data['metrics']
    lines = [
        '# И‑111 — Режим фразы: постоянное, временное, предложение, гипотеза',
        f"`{spec['branch']}` · {spec['phase']} · {spec['priority']} · {spec['date']}",
        '## П0–П2. Сверка и замысел',
        f"До начала: `{spec['baseline']}`. Повтор печати [И‑110](../110/REPLAY.json) совпал. "
        'И‑110 принимала явные действия, но ещё не отделяла подготовку текста от намерения записать его. '
        '[DESIGN.md](DESIGN.md) фиксирует границу карточки и хранилища, а не новую схему или полномочия.',
        f"[Корпус](CASES.json): {spec['case_counts']['nl']} фраз и {spec['case_counts']['control']} отдельных контролей. "
        f"[RED.json](RED.json) до правок: {counts_line(red['counts'])}, rc {red['rc']}; NL14 («Сделай черновик …» с полными реквизитами) "
        'раньше давал билет на дифф. Это преждевременный план, **не** наблюдавшаяся запись без согласия. '
        f"SHA‑256 корпуса `{spec['casebook_sha256']}`, SHA‑256 [пробы](test_intent.py) `{spec['test_sha256']}`.",
        '## П3–П5. Приёмка',
        '`python3 -B research/111/run.py` из корня. Целевая проба: `python3 -B -I -S -X utf8 research/111/test_intent.py`.',
        md_table(('Процесс', 'Обязательные случаи', 'rc', 'basis'), (
            ('П3 · checkout', counts_line(runs['checkout']['counts']), runs['checkout']['rc'], '[CHECKOUT.json](CHECKOUT.json)'),
            ('П4 · чистая копия', counts_line(runs['cleanroom']['counts']), runs['cleanroom']['rc'], '[CLEANROOM.json](CLEANROOM.json)'))),
        f"ОС: `{acceptance['host_os']}`. В чистом процессе только {len(spec['target_inputs'])} входов из [ITERATION.json](ITERATION.json), "
        'без Git, 0.1.36 или ISAI. Три реестра создаются во временных деревьях. Для каждого вызова сравниваются аудируемые события, '
        'вход порта, физические файлы, метки и замены. Положительные ответы на дифф тестовые, не согласие владельца живого профиля.',
        f"[ACCEPTANCE.json](ACCEPTANCE.json): **{acceptance['outcome']}**, {counts_line(acceptance['counts'])} по воротам и отложенным группам.",
        md_table(('Ворота', 'Статус', 'basis', 'criterion'), check_rows(acceptance)),
        '## П6. Что наблюдали',
    ]
    if metrics is None:
        lines.append('Приёмка отклонена: наблюдения не считаются принятым корпусом, печать не обновляется.')
    else:
        rows = {r['id']: r['observed'] for r in checkout['result']['rows']}
        stages = metrics['plan_outcomes']
        question = next(r for r in data['phrases'] if r['id'] == 'NL14')['card']['questions'][0]['text']
        lines += [
            f"**{len(metrics['false_write_cases'])} ложных записей на {metrics['phrases']} фразах.** "
            f"{stages['missing_params']} уточнений (из них {metrics['ambiguous_intent_questions']} — о режиме), "
            f"{stages['non_registry']} фраз вне реестра, {stages['planned']} диффа без подтверждения и {stages['listed']} просмотр. "
            f"Максимум {metrics['max_questions']} вопроса за один результат. Положительные контроли отдельно: {metrics['confirmed_replacements']} замены по точному билету.",
            f'> «{question}»',
            '[INTENTS.json](INTENTS.json) — действительные карточки, исходы сессии, контрольные применения, диффы без билетов.',
            md_table(('Факт', 'basis · ID в CHECKOUT/CLEANROOM', 'criterion / предел'), (
                ('Выбор режима предшествует диффу.', 'NL13–NL18; RED/NL14; C14',
                 'Отсутствующий/конкурирующий режим → вопрос о persistence. Перестановка альтернатив не меняет решения. '
                 'В полном missing[] до 9 пробелов, в выдаче не больше трёх вопросов.'),
                ('Три режима не обращаются к хранилищу.', 'NL05–NL12; C12–C13',
                 'temporary/proposal/hypothesis различимы; у non_registry нет операции, чтения порта, диффа, билета или записи. '
                 'Тело — данные, гипотеза не доказана, временное указание не исполнено.'),
                ('Уточнение не выдаёт ни состояние, ни право.', 'NL01–NL04; NL19–NL20; C01–C02; C10–C11',
                 'Постоянное не подставляет draft/active или родителя. Цитаты не создают меток. Просмотр читает, не пишет. '
                 'Два отдельных согласия изменили ровно свою область (L1 4→5, L2 7→8), вместе с решениями; L0 и соседний слой прежние.'),
                ('Новый выбор не наследует согласие.', 'C03–C09',
                 'Одинаковые реквизиты в заново сформулированной фразе → non_registry или новый dry-run. '
                 'Одно «Постоянное.» не восстанавливает запрос. Повтор прежнего билета, подмена карточки и перенос билета не пишут.'),
            )),
            'Две прежние формы И‑108 (`NL02 «Оформи»`, `N19 «Сделай»`) теперь спрашивают также о режиме: это '
            'преднамеренное усиление, не редакция их исторических ожиданий. Путь явных операций И‑110 не меняется.',
            '### 20 фраз и исходы',
            md_table(('ID', 'basis · категория', 'Фраза', 'criterion · наблюдённая развилка'), (
                (r['id'], MODES[r['category']], r['card']['request'],
                 r['plan'] + (' · ' + ', '.join(q['field'] for q in r['card']['questions']) if r['card']['questions'] else ''))
                for r in data['phrases'])),
            '### Отдельные контроли',
            md_table(('ID', 'basis', 'criterion · исход', 'Изменённый файл'), (
                (c['id'], c['basis'], rows[c['id']]['final'].get('error',{}).get('code', rows[c['id']]['final']['outcome']),
                 ', '.join(rows[c['id']]['changed']) or '—') for c in cases if c['group'] == 'control')),
        ]
    lines += [
        '### Не выполнялось', md_table(('Что', 'Почему'), ((x['what'], x['why']) for x in acceptance['not_run'])),
        '## П7–П9. Печать, страница и сверка',
        '[SEAL.json](SEAL.json) содержит размер и SHA‑256, [REPLAY.json](REPLAY.json) — результат чтения и повтора. '
        '`python3 -B research/111/run.py --verify-seal` сверяет архив и страницу без записи. '
        'Архив И‑110 прежний и проверяется из `7ba1c7e`.',
        '[Стратегия v1.13](../STRATEGY.md) · [сверка №21](../strategy/SYNC-LOG.md). A1–A4, P0, порядок и критерий Ф2 прежние. '
        'Ф2 остаётся открытой; это классификация намерения, не общий диалог или пригодность Kit.',
        '## Дальше', spec['next'],
    ]
    return '\n\n'.join(lines) + '\n'


def page(spec, acceptance, data, seal, replay):
    def e(x):
        return escape(str(x))

    ok = acceptance['outcome'] == 'accepted' and replay['outcome'] == 'ok'
    runs, metrics = acceptance['runs'], data['metrics']
    examples = details = guidance = ''
    if metrics is not None:
        for s in data['phrases']:
            card = s['card']
            questions = ''.join(f'<li>{e(r["text"])}</li>' for r in card['questions'])
            mode = card['params'].get('persistence')
            tag = f' · <code>{e(mode)}</code>' if mode else ''
            examples += (f'<details><summary>{e(s["id"])} · {e(MODES[s["category"]])} <span class="meta">{e(OUTCOMES[s["plan"]])}</span></summary>'
                         f'<p class="meta">{e(s["basis"])}{tag}</p><blockquote>{e(card["request"])}</blockquote>'
                         f'{"<ul>"+questions+"</ul>" if questions else ""}</details>')
        for i, plan in data['previews'].items():
            diff = plan['diff']
            details += (f'<details><summary>{e(i)} · {e(diff["file"])}</summary>'
                        f'<p>SHA‑256 после: <code>{e(diff["after_sha256"])}</code></p><pre>{e(diff["unified"])}</pre></details>')
        q = next(r['card']['questions'][0]['text'] for r in data['phrases'] if r['id'] == 'NL14')
        guidance = (f'<h2>Вопрос вместо догадки</h2><blockquote>{e(q)}</blockquote>'
                    f'<p>{metrics["ambiguous_intent_questions"]} неясных запросов дали вопрос о режиме. '
                    'Временное, предложение и гипотеза не дошли до загрузки реестров. '
                    'Выбор можно уточнить полной новой фразой; он не заменяет согласие на дифф.</p>')
    skipped = ''.join(f'<li><strong>{e(r["what"])}</strong> {e(r["why"])}</li>' for r in acceptance['not_run'])
    return f'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>И‑111 · Режим фразы</title><style>
:root {{color-scheme:light;--ink:#211c32;--muted:#574e67;--line:#ddd7e8;--wash:#f1edf7;--accent:#594287}}
* {{box-sizing:border-box}} body {{margin:0;background:#fdfcfe;color:var(--ink);font:1rem/1.55 system-ui,sans-serif}}
header {{background:var(--wash);border-bottom:1px solid var(--line)}} header>div,main {{max-width:64rem;margin:auto;padding:1.5rem max(1rem,3vw)}}
h1 {{font-size:clamp(2rem,4.5vw,3.4rem);line-height:1.08;text-wrap:balance;margin:.25em 0}} h2 {{margin:1.75rem 0 .6rem}}
.meta {{color:var(--muted)}} .verdict {{font-weight:700;color:{'#215a49' if ok else '#982f36'}}} a {{color:var(--accent);text-underline-offset:.18em}}
.cards {{display:grid;grid-template-columns:repeat(auto-fit,minmax(13rem,1fr));gap:.75rem}}
article,details {{background:white;padding:.75rem 1rem;border:1px solid var(--line);border-radius:.5rem}} article strong {{display:block}} details {{margin:.55rem 0}}
summary {{cursor:pointer;font-weight:650}} summary .meta {{display:inline-block;margin-left:.65rem;font-weight:450}}
blockquote {{margin:.6rem 0;border-left:.22rem solid var(--line);padding:0 .8rem}} pre {{padding:.85rem;background:var(--wash);white-space:pre-wrap}}
pre,code {{overflow-wrap:anywhere}} li {{margin:.35rem 0}}
</style></head><body><header><div>
<p class="meta">И‑111 · {e(spec['phase'])} · {e(spec['priority'])} · {e(spec['date'])}</p>
<h1>{e(spec['title'])}</h1><p class="verdict">{'Проверки приняты на фикстурах' if ok else 'Проверки не приняты'}</p>
<p>Неясный режим — уточнить. Незаносимое в реестр — не записывать. Явное изменение — показать дифф, затем получить отдельное согласие.</p>
</div></header><main>
<div class="cards"><article><a href="CHECKOUT.json">П3 · checkout</a><strong>{e(counts_line(runs['checkout']['counts']))}</strong></article>
<article><a href="CLEANROOM.json">П4 · чистая копия</a><strong>{e(counts_line(runs['cleanroom']['counts']))}</strong></article>
<article><a href="ACCEPTANCE.json">П5 · приёмка</a><strong>{e(counts_line(acceptance['counts']))}</strong></article></div>
{guidance}
<h2>Корпус</h2><p>Ложных записей: <strong>{len(metrics['false_write_cases']) if metrics else '—'}</strong> на {metrics['phrases'] if metrics else '—'} фразах. Отдельно проверены две согласованные записи L1/L2.</p>
{examples}
<h2>Диффы без билетов</h2><p><a href="INTENTS.json">Карточки и наблюдения</a> · <a href="../../kit/base/OPERATION-CARD.md">Грамматика</a></p>{details}
<h2>Не выполнялось</h2><ul>{skipped}</ul>
<h2>Печать и повтор</h2><p><a href="{e(seal['file'])}">ZIP с приёмкой</a> · {e(seal['members'])} файлов · {e(seal['bytes'])} байт ·
<a href="REPLAY.json">повтор: {e(replay['outcome'])}</a></p><p>SHA‑256 <code>{e(seal['sha256'])}</code></p>
<p><a href="REPORT.md">Отчёт и критерии</a> · <a href="DESIGN.md">Замысел</a> · <a href="../STRATEGY.md">Стратегия</a></p>
<p class="meta">{e(spec['next'])}</p></main></body></html>
'''
