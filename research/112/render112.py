"""И-112: отчёт и страница из принятой трассы, без секретов и билетов."""
from html import escape

from render import check_rows, counts_line, md_table

STAGES = {'bootstrap': '1. Старт', 'phrase': '2. Фраза и dry-run', 'confirmation': '3. Согласие и запись'}


def report(spec, red, result, data):
    runs, metrics = result['runs'], data['metrics']
    probe = spec['probe_instrumentation']
    cmd = 'python3 ' + ' '.join(spec['command'])
    lines = [
        f"# И‑112 — {spec['title']}",
        f"`{spec['branch']}` · {spec['phase']} · {spec['priority']}",
        '## П0–П2. Замысел и исходный контроль',
        f"Перед изменениями: `{spec['baseline']}` (`{spec['baseline_strategy']}`), повтор печати [И‑111](../111/REPLAY.json) совпал. "
        '[DESIGN.md](DESIGN.md) фиксирует согласованные границы: новый явный вход, существующий компилятор/порт, '
        'отдельное согласие, только пустые v2-фикстуры в положительном сценарии, без установщика.',
        f"[RED.json](RED.json): rc {red['rc']}, {counts_line(red['result']['counts'])}. Причина общая — отсутствовали `entry.txt`, `START.md`, `bootstrap.py`; "
        'порядок проверок нового входа ещё нельзя было выполнить. Прямой старый путь с той же фразой показал точный дифф, но не изменил файлов. '
        'Исходный контроль повторён из `git archive` базового коммита.',
        f"[CASES.json](CASES.json): SHA‑256 `{spec['casebook_sha256']}`. [test_bootstrap.py](test_bootstrap.py): `{spec['test_sha256']}`. "
        f"Первый вариант измерителя `{probe['initial_probe_sha256']}` дал B01 `fail` из-за события каталога. {probe['correction']}",
        '## П3–П5. Выполнение и приёмка',
        f"Команда пробы: `{cmd}`. Для двух прогонов, отчёта и печати: `python3 -B research/112/run.py`. "
        f"ОС `{result['host_os']}`, Python `{result['python']}`. П4 — новая копия ровно {len(spec['target_inputs'])} входов, "
        'без Git, 0.1.36 и ISAI. В каждом процессе — отдельные временные деревья реестров. Согласие тестовое, не полномочие живого владельца.',
        md_table(('Процесс', 'Обязательные случаи', 'rc', 'basis'), (
            ('П3 · checkout', counts_line(runs['checkout']['counts']), runs['checkout']['rc'], '[CHECKOUT.json](CHECKOUT.json)'),
            ('П4 · чистая копия', counts_line(runs['cleanroom']['counts']), runs['cleanroom']['rc'], '[CLEANROOM.json](CLEANROOM.json)'))),
        f"[ACCEPTANCE.json](ACCEPTANCE.json): **{result['outcome']}** (П5 на фикстурах). {counts_line(result['counts'])} по воротам и отложенным группам.",
        md_table(('Ворота', 'Статус', 'basis', 'criterion'), check_rows(result)),
        '## П6. Наблюдения',
    ]
    if metrics is None:
        lines.append('Приёмка отклонена; печать и страница не обновляются.')
    else:
        start, phrase, apply = data['witness']['steps']
        entry = data['witness']['stored']['document']['registry']['entries'][0]
        lines.extend([
            f"**{metrics['steps']} шага в B01.** Фраза ниже полностью задаёт реквизиты в узкой грамматике; произвольный запрос может потребовать уточнений.",
            '> ' + phrase['reply']['card']['request'],
            f"Старт и dry-run не меняли дерево. По отдельному согласию заменён ровно один файл `{apply['changed'][0]}`. "
            f"L1 {phrase['reply']['diff']['revision']['from']}→{apply['reply']['status']['profile_revision']}, L2 остался на {apply['reply']['status']['project_revision']}. "
            f"Сохранены `{entry['id']}`, `{entry['kind']}/{entry['state']}`, `parent: null` и одно решение `create`. L0 и соседний реестр прежние побайтно. "
            'На всех остальных обязательных случаях не было попыток записи Kit; внешний дрейф L2 в C04 внесла сама проба.',
            '### Прочитанные входы (B01)',
            md_table(('Шаг', 'Путь', 'Байт', 'SHA‑256 прочитанного'), (
                (STAGES[step['step']], f"`{r['file']}`", r['bytes'], f"`{r['sha256']}`")
                for step in (start, phrase, apply) for r in step['reads'])),
            f"У `START.md` осталось непрочитано {metrics['unread_start_tail_bytes']} байт, включая §1. В префиксе измерено только §0 с маркером конца. "
            'Отдельные документы контракта в дереве были, но не открывались. На втором шаге события `compile` и `verify-card` стоят **до** `read` реестров. '
            'Третий шаг повторно читает L1/L0/L2 для проверки свежести; это не загрузка всего контракта перед компиляцией. '
            'В таблице только данные/документы в целевых фазах; импорты Python и подготовка фикстуры не включены.',
            '[BOOTSTRAP.json](BOOTSTRAP.json) — полная трасса B01, фраза, точный дифф без билета, физически прочитанная запись и итоговые исходы контролей.',
            '### Границы, которые сохранены',
            md_table(('Факт', 'basis', 'criterion'), (
                ('Короткий вход не выполняет и не чинит данные.', 'S01–S09, P11–P12',
                 'Внешний указатель, пропуск файла, алиасы, битый §0 и превышение лимита различаются; частичный v2 или схема 1 не принимаются за чистую установку.'),
                ('Режим, адрес и состояние не додумываются.', 'P01–P05, P13',
                 'Сомнительный запрос даёт вопросы, временный — non_registry. Нет подстановки профиля или draft; L0 не становится целью.'),
                ('Ни обхода A1–A4, ни молчаливого победителя.', 'P05–P10',
                 'Пересечение корней, запись L0, конфликт, неназванный/чужой родитель или выход из scope остаются разными исходами без записи.'),
                ('Показанный дифф не является согласием.', 'B01; C01–C05',
                 'Отсутствие/подмена билета, подмена диффа, дрейф при прежней ревизии и смена фразы не пишут. Только B01 подтверждён точным билетом.')
            )),
            '### Контроли',
            md_table(('ID', 'basis', 'criterion', 'Наблюдалось'), ((c['id'], c['basis'], c['criterion'], ' → '.join(c['outcomes'])) for c in data['controls'])),
        ])
    lines.extend([
        '### Не выполнялось',
        md_table(('Что', 'Почему'), ((r['what'], r['why']) for r in result['not_run'])),
        '## П7–П9. Печать и синхронизация',
        '[SEAL.json](SEAL.json) фиксирует состав, байты и SHA‑256; [REPLAY.json](REPLAY.json) — результат повтора. '
        '`python3 -B research/112/run.py --verify-seal` проверяет архив, отчёт и страницу без записи. Сама страница и данные о печати не входят в ZIP.',
        '[Стратегия](../STRATEGY.md) и [сверка №22](../strategy/SYNC-LOG.md): A1–A4, P0, порядок, вехи и критерии сохранены. '
        'Владелец отдельно разрешил commit/push И‑112. '
        f"Завершение П9 проверяется по наличию коммита И‑112 в истории `origin/{spec['branch']}`, не по локальному ZIP. "
        'Печать И‑111 относится к `c5fec24`.',
    ])
    return '\n\n'.join(lines) + '\n'


def page(spec, result, data, seal, replay):
    def e(value):
        return escape(str(value))

    runs, metrics = result['runs'], data['metrics']
    ok = result['outcome'] == 'accepted' and replay['outcome'] == 'ok'
    skip = ''.join(f'<li><b>{e(r["what"])}</b> {e(r["why"])}</li>' for r in result['not_run'])
    step_cards = details = ''
    if metrics is not None:
        first, second, third = data['witness']['steps']
        step_cards = f'''<h2>Три шага в чистой копии</h2>
<ol class="grid paths">
<li><b>Старт</b><span><code>entry.txt</code> и только §0</span><small>{e(sum(r['bytes'] for r in first['reads']))} байта · без чтения реестров</small></li>
<li><b>Фраза и dry-run</b><span>Компиляция → три реестра → дифф</span><small>Нет записи или автоматического согласия</small></li>
<li><b>Согласие</b><span>Точный билет → <code>contract/draft</code></span><small>Одна замена · L1: 0 → 1 · L2: 0 → 0</small></li>
</ol>
<blockquote>{e(second['reply']['card']['request'])}</blockquote>'''
        reads = ''.join(f'<tr><td>{e(STAGES[s["step"]])}</td><td><code>{e(r["file"])}</code></td><td>{e(r["bytes"])}</td></tr>'
                        for s in (first, second, third) for r in s['reads'])
        controls = ''.join(f'<tr><td>{e(c["id"])}</td><td>{e(c["criterion"])}</td><td><code>{e(" → ".join(c["outcomes"]))}</code></td></tr>'
                           for c in data['controls'])
        details = f'''<h2>Какие данные действительно читались</h2>
<p>Хвост <code>START.md</code> после §0 ({e(metrics['unread_start_tail_bytes'])} байт) и документы полного контракта не открывались при старте.
Открытие реестров наблюдалось только после компиляции фразы и после согласия. Импорты Python и подготовка стенда не входят в трассу.</p>
<table><thead><tr><th>Шаг</th><th>Файл</th><th>Байт</th></tr></thead><tbody>{reads}</tbody></table>
<p><a href="BOOTSTRAP.json">Полная трасса с SHA‑256</a> · <a href="REPORT.md">Отчёт и критерии</a></p>
<details><summary>Точный дифф без билета</summary><pre>{e(second['reply']['diff']['unified'])}</pre></details>
<details><summary>Обязательные контроли</summary><br><table><thead><tr><th>ID</th><th>Критерий</th><th>Наблюдалось</th></tr></thead><tbody>{controls}</tbody></table></details>'''
    return f'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>И‑112 · Первый черновик</title><style>
:root {{color-scheme:light;--paper:#f9fbfa;--white:#fff;--ink:#142725;--fade:#52645f;--line:#cfdcd7;--hi:#135c4a;--mint:#e9f3ef}}
* {{box-sizing:border-box}} body {{margin:0;background:var(--paper);color:var(--ink);font:1rem/1.58 system-ui,sans-serif}}
header {{background:var(--mint);border-bottom:1px solid var(--line)}} header>div,main {{max-width:65rem;margin:auto;padding:1.5rem max(1rem,3vw)}}
h1 {{font-size:clamp(2.15rem,5.4vw,4.1rem);line-height:1.03;letter-spacing:-.04em;margin:.18em 0 .3em;max-width:17ch;text-wrap:balance}}
h2 {{line-height:1.2;margin:1.7em 0 .5em}} .meta,small {{color:var(--fade)}} .verdict {{color:{'#145541' if ok else '#8b2727'};font-weight:750}}
a {{color:var(--hi);text-underline-offset:.17em}} .grid {{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:.8rem}}
article,details,.paths li {{background:var(--white);border:1px solid var(--line);border-radius:.6rem;padding:.85rem 1rem}}
.paths {{counter-reset:phase;list-style:none;padding:0}} .paths li::before {{counter-increment:phase;content:"0" counter(phase);color:var(--hi);font:700 1.25rem/1 monospace}}
.paths li b,.paths li span,.paths li small,article strong {{display:block}} table {{width:100%;border-collapse:collapse;background:var(--white)}} th,td {{text-align:left;vertical-align:top;border-bottom:1px solid var(--line);padding:.5rem .7rem}}
blockquote {{margin:1rem 0;border-left:3px solid var(--hi);padding:.4rem .9rem;background:var(--white)}} details {{margin:.75rem 0}}
summary {{cursor:pointer;font-weight:650}} pre,code {{overflow-wrap:anywhere}} pre {{white-space:pre-wrap;background:var(--mint);padding:1rem}}
</style></head><body><header><div>
<p class="meta">И‑112 · {e(spec['phase'])} · {e(spec['priority'])}</p>
<h1>{e(spec['title'])}</h1><p class="verdict">{'Проверки П5 приняты на фикстурах' if ok else 'Проверки не приняты'}</p>
<p>Старт не читает весь контракт и не пишет. Сохраняется только согласованный черновик.</p>
</div></header><main>
<div class="grid"><article><a href="CHECKOUT.json">П3 · checkout</a><strong>{e(counts_line(runs['checkout']['counts']))}</strong></article>
<article><a href="CLEANROOM.json">П4 · чистая копия</a><strong>{e(counts_line(runs['cleanroom']['counts']))}</strong></article>
<article><a href="ACCEPTANCE.json">П5 · приёмка</a><strong>{e(counts_line(result['counts']))}</strong></article></div>
{step_cards}
{details}
<h2>Что не проверялось</h2><ul>{skip}</ul>
<h2>Печать и повтор</h2><p><a href="{e(seal['file'])}">Скачать ZIP</a> · {e(seal['members'])} файлов · {e(seal['bytes'])} байт · <a href="REPLAY.json">повтор: {e(replay['outcome'])}</a></p>
<p>SHA‑256 <code>{e(seal['sha256'])}</code></p>
<p><a href="DESIGN.md">Замысел</a> · <a href="RED.json">Исходный контроль</a> · <a href="../STRATEGY.md">Стратегия</a></p>
<p class="meta">Сверка №22 записана. П9 проверяется по коммиту И‑112 в <code>origin/{e(spec["branch"])}</code>.</p>
</main></body></html>
'''
