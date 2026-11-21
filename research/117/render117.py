"""Человекочитаемая приёмка И-117: образец продукта не равен печати исследования."""
from html import escape

from render import check_rows, counts_line, md_table


def outcome(row):
    if row['error']:
        e = row['error']
        return f"{e['code']} · {e['where']} / {e['details']['reason']}"
    return f"bundled · {row['package']['archive_members']} членов"


def report(spec, red, verdict, data):
    runs, m = verdict['runs'], data['metrics']
    lines = [
        '# И‑117 — Неполный пакет не собирается',
        f"`{spec['branch']}` · {spec['phase']} · {spec['priority']}",
        '## П0–П2. Сверка, замысел, контроль',
        f"[Границы согласия](DESIGN.md) · стратегия `{spec['baseline_strategy']}` · HEAD `{spec['baseline']}`. "
        '[Печать И‑116](../116/REPLAY.json) подтверждена до правок. Сборка полного среза отличается от проверки уже полученного пакета; рабочий порт не менялся.',
        f"[RED.json](RED.json): rc {red['rc']}, {counts_line(red['result']['counts'])}; вывод из базового `git archive` совпал. "
        'Положительный контроль отдельно принял обе формы голого v2 и два валидных контейнера истории. Сборщик ещё отсутствовал; порт вернул `unknown_operation` для обеих операций.',
        f"[Манифест эксперимента](ITERATION.json) закрепляет {len(spec['pinned_inputs'])} материалов. SHA‑256 [корпуса](CASES.json) "
        f"`{spec['casebook_sha256']}`, [оракула](test_bundle.py) `{spec['test_sha256']}`.",
        'Первый прогон с продуктом: 45/1/0, P05. Порядок ключей изменился при сохранении корпуса после расчёта эталона. '
        'Восстановлен исходный порядок полей фикстуры, не критерий, вектор, продукт или код теста; базовый RED повторён. '
        'Исходные отпечатки и причина: `RED.json.fixture_correction`.',
        '## П3–П5. Два прогона и приёмка',
        f"`python3 {' '.join(spec['command'])}` · {verdict['os']}, Python {verdict['python']}. В чистой копии только {len(spec['target_inputs'])} объявленных входов.",
        md_table(('Процесс', 'Обязательные строки', 'rc', 'basis'), (
            ('П3 · рабочая копия', counts_line(runs['checkout']['counts']), runs['checkout']['rc'], '[CHECKOUT.json](CHECKOUT.json)'),
            ('П4 · чистая копия', counts_line(runs['cleanroom']['counts']), runs['cleanroom']['rc'], '[CLEANROOM.json](CLEANROOM.json)'))),
        f"[ACCEPTANCE.json](ACCEPTANCE.json): **{verdict['outcome']}** · {counts_line(verdict['counts'])} по воротам и отложенным группам.",
        md_table(('Ворота', 'Статус', 'basis', 'criterion'), check_rows(verdict)),
        '## П6. Что собрано и что отвергнуто',
    ]
    if m is None:
        lines.append('Приёмка отклонена; пример, печать и страница не обновляются.')
    else:
        ref = data['reference']; mf = ref['manifest']
        lines.extend([
            f"[{spec['sample']}]({spec['sample']}) — пример продукта P01, **не** дистрибутив и не ZIP исследования. "
            f"`revision` = {mf['revision']}, `roots` = `{', '.join(mf['roots'])}`, {len(mf['files'])} файлов и `manifest.json`.",
            md_table(('Величина', 'Значение', 'basis'), (
                ('Digest манифеста', f"`{mf['digest']}`", 'P01; JSON полей revision/roots/files, без digest и LF'),
                ('SHA‑256 ZIP продукта', f"`{ref['archive_sha256']}`", f"P01; {ref['archive_bytes']} точных байт, {ref['archive_members']} членов"),
                ('SHA‑256 печати исследования', '[SEAL.json](SEAL.json)', 'Другой архив: входы, отчёт, оракул и готовый пример'),
            )),
            md_table(('Файл P01', 'Байт', 'SHA‑256'), ((f"`{f['path']}`", f['size'], f"`{f['sha256']}`") for f in mf['files'])),
            f"На прогон: {m['bundled']} успехов и {m['refused']} отказов; {m['missing_members_tested']} одиночных пропусков. "
            f"{m['refused_before_build']} отказов до создания ZIP; сбой восьмой записи N21 не дал и частичного результата. "
            f"Всего {m['archive_attempts']} попыток создать буфер ZIP, {m['member_attempts']} попыток записать член, {m['effect_attempts']} попыток файлового/сетевого I/O. Входы прежние.",
            md_table(('Факт', 'basis', 'criterion / предел'), (
                ('Полноту нельзя вывести из списка, присланного самим вызывающим.', 'M01–M16; N04–N07/N23/N24', 'Пропуск любого из 16 даёт отказ, лишнее имя или привязка к L2 не упаковываются; разрешённый пустой профиль проходит.'),
                ('Порядок передачи не меняет результат, но исходные байты имеют значение.', 'P02/P04/P05/P06', 'Перестановка даёт тот же ZIP; другое тело или форматирование при revision 7 меняет digest; revision 8 берётся из L1.'),
                ('Валидный журнал остаётся локальным.', 'N17/N18; положительный контроль; PROFILE-JOURNAL.md', 'Оба целых контейнера 1 и 2 отвергаются без скрытого извлечения. В образце голый v2; P01 И‑114–И‑116 не включён.'),
                ('Не выполняется код из пакета и не ставится Kit.', 'test_bundle.py: Monitor и inspect_known_archive', 'Читатель сверяет только известный синтетический результат, а не произвольный полученный архив или источник доверия.'),
            )),
            '### Корпус',
            md_table(('ID', 'basis', 'criterion', 'Наблюдалось'), ((r['id'], r['basis'], r['criterion'], outcome(r)) for r in data['rows'])),
        ])
    lines.extend([
        '### Не выполнялось',
        md_table(('Что', 'Почему'), ((r['what'], r['why']) for r in verdict['not_run'])),
        '## П7–П9. Печать, повтор, сверка',
        '`python3 -B research/117/run.py` воспроизводит комплект. `python3 -B research/117/run.py --verify-seal` сверяет '
        '[печать](SEAL.json), точный пример, [запись повтора](REPLAY.json), отчёт и страницу без записи. Страница и записи о печати не являются членами исследовательского ZIP.',
        '[Стратегия v1.19](../STRATEGY.md) · [сверка №27](../strategy/SYNC-LOG.md). A1–A4, P0, критерии, порядок, вехи и пригодность прежние. '
        f"Commit/push только 21 пути И‑117 разрешены отдельно ([основание](DESIGN.md)). После сверки с `origin/{spec['branch']}` "
        'локальный HEAD выровнен без изменения рабочих файлов. П9 подтверждается совпадением SHA и повтором из снимка коммита. И‑118 не начата; Ф4 открыта.',
    ])
    return '\n\n'.join(lines) + '\n'


def page(spec, verdict, data, seal, replay):
    def e(value):
        return escape(str(value))
    runs, m, ref = verdict['runs'], data['metrics'], data['reference']
    mf = ref['manifest']
    good = verdict['outcome'] == 'accepted' and replay['outcome'] == 'ok'
    files = ''.join(f'<tr><th scope="row"><code>{e(r["path"])}</code></th><td>{e(r["size"])}</td><td><code>{e(r["sha256"])}</code></td></tr>'
                    for r in mf['files'])
    cases = ''.join(f'<tr><th scope="row">{e(r["id"])}</th><td>{e(r["criterion"])}</td><td><code>{e(outcome(r))}</code></td></tr>'
                    for r in data['rows'])
    limits = ''.join(f'<li><b>{e(r["what"])}</b> {e(r["why"])}</li>' for r in verdict['not_run'])
    return f'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>И‑117 · Полный синтетический пакет</title><style>
:root {{color-scheme:light;--page:#f6f5f1;--surface:white;--ink:#172738;--muted:#516475;--accent:#055b72;--line:#d4dfe2}}
* {{box-sizing:border-box}} body {{margin:0;background:var(--page);color:var(--ink);font:1rem/1.55 system-ui,sans-serif}}
header {{background:#e0eef0;border-bottom:1px solid var(--line)}} .wrap,main {{max-width:71rem;margin:auto;padding:1.65rem max(1rem,3.8vw)}}
h1 {{font-size:clamp(2.4rem,7vw,5rem);line-height:1;letter-spacing:-.055em;max-width:17ch;margin:.3em 0;text-wrap:balance}}
h2 {{margin:1.6em 0 .55em;line-height:1.2}} h3,p {{margin:.45em 0}} a {{color:var(--accent);text-underline-offset:.17em}}
.meta {{color:var(--muted)}} .verdict {{font-weight:740;color:{'#0b5c63' if good else '#992235'}}}
.grid {{display:grid;gap:.75rem;grid-template-columns:repeat(auto-fit,minmax(min(16rem,100%),1fr))}}
.card,details {{background:var(--surface);border:1px solid var(--line);border-radius:.7rem;padding:1rem 1.15rem}}
.card strong {{display:block;margin-top:.25em;font-size:1.18rem}} .scroll {{overflow:auto}} summary {{cursor:pointer;font-weight:670}}
table {{border-collapse:collapse;width:100%;margin-top:.6rem}} td,th {{border-bottom:1px solid var(--line);padding:.6rem;text-align:left;vertical-align:top}} code {{overflow-wrap:anywhere}} li {{margin:.4em 0}}
</style></head><body><header><div class="wrap"><p class="meta">И‑117 · {e(spec['phase'])} · {e(spec['priority'])}</p>
<h1>{e(spec['title'])}</h1><p class="verdict">{'П5 принята на синтетических данных' if good else 'Приёмка не пройдена'}</p>
<p>{e(m['missing_members_tested'])} одиночных пропусков закрыли сборку до ZIP; поздний сбой не выдал промежуточные байты.</p></div></header>
<main><div class="grid">
<div class="card"><a href="CHECKOUT.json">Рабочая копия</a><strong>{e(counts_line(runs['checkout']['counts']))}</strong></div>
<div class="card"><a href="CLEANROOM.json">Чистая копия</a><strong>{e(counts_line(runs['cleanroom']['counts']))}</strong></div>
<div class="card"><a href="ACCEPTANCE.json">Ворота приёмки</a><strong>{e(counts_line(verdict['counts']))}</strong></div></div>
<h2>Два разных ZIP</h2><div class="grid">
<article class="card"><h3><a href="{e(spec['sample'])}">Синтетический продукт P01</a></h3>
<p>Ревизия {e(mf['revision'])} · {e(ref['archive_members'])} членов · {e(ref['archive_bytes'])} байт. Код из пакета не исполнялся.</p>
<p>Digest манифеста<br><code>{e(mf['digest'])}</code></p><p>SHA‑256 ZIP продукта<br><code>{e(ref['archive_sha256'])}</code></p></article>
<article class="card"><h3><a href="{e(seal['file'])}">Печать исследования</a></h3>
<p>{e(seal['members'])} членов · {e(seal['bytes'])} байт. Оракул, отчёт и точный пример.</p>
<p>SHA‑256 печати<br><code>{e(seal['sha256'])}</code></p><p><a href="REPLAY.json">Повтор: {e(replay['outcome'])}</a></p></article></div>
<h2>Полезные файлы примера</h2><p>Корни: <code>{e(', '.join(mf['roots']))}</code>. Манифест не включает себя.</p>
<details><summary>{e(len(mf['files']))} имён, размеров и отпечатков</summary><div class="scroll"><table>
<thead><tr><th scope="col">Имя</th><th scope="col">Байт</th><th scope="col">SHA‑256</th></tr></thead><tbody>{files}</tbody></table></div></details>
<h2>Проверки и пределы</h2><details><summary>{e(m['cases'])} случаев, включая отказы</summary><div class="scroll"><table>
<thead><tr><th scope="col">ID</th><th scope="col">Критерий</th><th scope="col">Наблюдалось</th></tr></thead><tbody>{cases}</tbody></table></div></details>
<ul>{limits}</ul><p><a href="REPORT.md">Отчёт</a> · <a href="BUNDLE.json">Машинные результаты</a> · <a href="../../kit/base/BUNDLE.md">Формат</a> · <a href="../STRATEGY.md">Стратегия</a></p>
<p class="meta">Сверка №27. П9 подтверждается по коммиту И‑117 в <code>origin/{e(spec["branch"])}</code> и повтором из его снимка. И‑118 не начата.</p></main></body></html>
'''
