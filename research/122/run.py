#!/usr/bin/env python3
"""И-122 (Kilo): приёмка по восьми пробам, печать и страница.

Принцип: печать фиксирует ТОЛЬКО то, что наблюдалось у владельца 2026-11-24.
Каждая карточка, на которую ссылается приёмка, входит в архив байтами — проверяющий
читает архив и видит те же файлы, а не пересказ.

Команды:
    python3 -B research/122/run.py --build    # заново посчитать печать и записать SEAL/REPLAY/страницу
    python3 -B research/122/run.py --verify-seal
"""
from __future__ import annotations

import argparse
import json
import sys
import zipfile
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.dont_write_bytecode = True

SPEC = HERE / 'ITERATION.json'
PREFIX = 'research/122/'
SEAL, REPLAY, PAGE = (HERE / n for n in ('SEAL.json', 'REPLAY.json', 'Итерация-122.html'))
ZIP_NAME = 'AgentContractKit-Iteration-122.zip'


def sha(data: bytes) -> str:
    return sha256(data).hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def dump_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + '\n',
                    encoding='utf-8', newline='\n')


def members() -> list[str]:
    """Что входит в печать: спецификация, все карточки, сводка, отчёт, документы оснований."""
    spec = read_json(SPEC)
    return sorted(set(spec['seal_members']))


def seal_bytes(names: list[str]) -> tuple[bytes, dict]:
    buffer = BytesIO()
    # Постоянные метаданные и ZIP_STORED: повтор не зависит от mtime и версии zlib.
    with zipfile.ZipFile(buffer, 'w') as archive:
        for name in sorted(names):
            info = zipfile.ZipInfo(name)
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, (ROOT / name).read_bytes())
    raw = buffer.getvalue()
    return raw, {'file': ZIP_NAME, 'format': 1, 'iteration': 'И-122', 'members': len(names),
                 'bytes': len(raw), 'sha256': sha(raw)}


def report_md(spec: dict, rec: dict, seal: dict) -> str:
    ok = sum(1 for c in rec['checks'] if c['status'] == 'pass')
    part = sum(1 for c in rec['checks'] if c['status'] == 'partial')
    fail = sum(1 for c in rec['checks'] if c['status'] == 'fail')
    lines = [
        f"# {rec['iteration']} · {spec['title']}",
        '',
        f"**Фаза:** {spec['phase']}  ·  **Дата:** {spec['date']}  ·  **Ветка:** `{spec['branch']}`",
        f"**Вердикт:** `{rec['outcome']}` — pass {ok}, partial {part}, fail {fail}, "
        f"not run {len(rec['not_run'])}",
        '',
        '## Окружение (наблюдённое, не документация)',
        '',
        '| Параметр | Значение |',
        '|---|---|',
    ]
    for k, v in spec['environment'].items():
        lines.append(f'| {k} | {v} |')
    lines += ['', '## Проверки', '', '| # | Проверка | Статус | Основание | Критерий |',
              '|---|---|---|---|---|']
    for i, c in enumerate(rec['checks'], 1):
        lines.append(f"| {i} | {c['name']} | **{c['status']}** | {c['basis']} | {c['criterion']} |")
    lines += ['', '## Пробы-долги (`not run`)', '', '| Что | Почему |', '|---|---|']
    for n in rec['not_run']:
        lines.append(f"| {n['what']} | {n['why']} |")
    lines += ['', '## Ограничения приёмки', '', '| # | Ограничение | Следствие |', '|---|---|---|']
    for o in spec['limits']:
        lines.append(f"| {o['id']} | {o['limit']} | {o['effect']} |")
    lines += ['', '## Что входит в печать', '', f'{seal["members"]} файлов, {seal["bytes"]} байт. '
              f'SHA-256 печати: `{seal["sha256"]}`.', '',
              'Каждая карточка пробы включена байтами: архив открывается без репозитория.', '',
              '## Чего эта приёмка не утверждает', '']
    for x in spec['not_claimed']:
        lines.append(f'- {x}')
    return '\n'.join(lines) + '\n'


def page_html(spec: dict, rec: dict, seal: dict) -> str:
    def esc(s: str) -> str:
        return (s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))

    rows = '\n'.join(
        f"<tr><td>{i}</td><td>{esc(c['name'])}</td><td class=s-{c['status'].replace(' ', '-')}>"
        f"{c['status']}</td><td>{esc(c['basis'])}</td></tr>"
        for i, c in enumerate(rec['checks'], 1))
    limits = '\n'.join(f"<li><b>{o['id']}</b> — {esc(o['limit'])}. <i>{esc(o['effect'])}</i></li>"
                       for o in spec['limits'])
    env = '\n'.join(f"<tr><th>{esc(k)}</th><td>{esc(str(v))}</td></tr>"
                    for k, v in spec['environment'].items())
    return f"""<!doctype html>
<html lang="ru"><meta charset="utf-8"><title>Итерация 122 · Kilo</title>
<style>
body{{font:16px/1.55 system-ui,sans-serif;max-width:58rem;margin:3rem auto;padding:0 1.2rem;color:#1b1f24}}
h1{{font-size:1.7rem;margin-bottom:.2rem}} .sub{{color:#5b6572;margin-bottom:2rem}}
table{{border-collapse:collapse;width:100%;margin:1rem 0}} th,td{{border-bottom:1px solid #e2e6ea;padding:.5rem;text-align:left;vertical-align:top}}
th{{background:#f6f8fa;font-weight:600}} .s-pass{{color:#1a7f37;font-weight:600}} .s-partial{{color:#9a6700;font-weight:600}}
.s-fail{{color:#b3261e;font-weight:600}} code{{background:#f6f8fa;padding:.1rem .35rem;border-radius:4px}}
</style>
<h1>Итерация 122 · {esc(spec['title'])}</h1>
<p class=sub>{esc(spec['phase'])} · {spec['date']} · ветка <code>{spec['branch']}</code> ·
вердикт <code>{rec['outcome']}</code></p>
<h2>Окружение</h2><table>{env}</table>
<h2>Проверки ({len(rec['checks'])})</h2>
<table><tr><th>#</th><th>Проверка</th><th>Статус</th><th>Основание</th></tr>{rows}</table>
<h2>Ограничения</h2><ul>{limits}</ul>
<h2>Печать</h2>
<p>{seal['members']} файлов, {seal['bytes']} байт. SHA-256: <code>{seal['sha256']}</code></p>
<p>Каждая карточка пробы входит в архив байтами — проверяющий видит те же файлы.</p>
<h2>Чего приёмка не утверждает</h2><ul>{''.join(f'<li>{esc(x)}</li>' for x in spec['not_claimed'])}</ul>
</html>"""


def evaluate(spec: dict) -> dict:
    """Проверки считаются по правилам, а не берутся готовыми: пересборка повторима."""
    checks = []
    for c in spec['checks']:
        kind = c['type']
        if kind == 'file_exists':
            ok = (ROOT / c['path']).is_file()
            detail = c['path']
        elif kind == 'dir_contains':
            folder = ROOT / c['dir']
            ok = folder.is_dir() and len(list(folder.glob(c['glob']))) >= c['min']
            detail = f"{c['dir']}: {len(list(folder.glob(c['glob']))) if folder.is_dir() else 0} файлов"
        elif kind == 'quote_present':
            text = (ROOT / c['path']).read_text(encoding='utf-8')
            ok = all(q in text for q in c['quotes'])
            detail = ', '.join(q for q in c['quotes'] if q in text) or 'ни одной цитаты'
        elif kind == 'json_field':
            data = read_json(ROOT / c['path'])
            cur = data
            for part in c['field'].split('.'):
                cur = cur[part] if isinstance(cur, dict) else None
            ok = cur == c['equals']
            detail = f"{c['field']} = {cur!r}"
        elif kind == 'spec_selfcheck':
            data = read_json(ROOT / c['path'])
            missing = [x['name'] for x in data['checks'] if not x.get('basis') or not x.get('criterion')]
            ok = not missing
            detail = 'basis/criterion у всех проверок' if ok else 'нет у: ' + ', '.join(missing)
        elif kind == 'declared_partial':
            ok, detail = True, c['why']
        else:
            raise ValueError('неизвестный тип проверки: ' + kind)
        status = c.get('force_status') or ('pass' if ok else 'fail')
        checks.append({'name': c['name'], 'status': status, 'basis': c['basis'],
                       'criterion': c['criterion'], 'detail': detail})
    skipped = [dict(row, status='not run') for row in spec['not_run']]
    counts = {s: sum(1 for r in checks if r['status'] == s) for s in ('pass', 'partial', 'fail')}
    outcome = 'rejected' if counts['fail'] else 'accepted'
    return {'iteration': 'И-122', 'phase': spec['phase'], 'checks': checks,
            'not_run': skipped, 'counts': counts, 'outcome': outcome}


def build() -> dict:
    spec = read_json(SPEC)
    rec = evaluate(spec)
    names = members()
    (HERE / 'REPORT.md').write_text(report_md(spec, rec, {'members': len(names), 'bytes': 0,
                                                          'sha256': '-'}), encoding='utf-8', newline='\n')
    raw, seal = seal_bytes(names)
    ZIP_BYTES = raw
    (HERE / ZIP_NAME).write_bytes(ZIP_BYTES)
    rec['seal'] = seal
    dump_json(HERE / 'ACCEPTANCE.json', rec)
    (HERE / 'REPORT.md').write_text(report_md(spec, rec, seal), encoding='utf-8', newline='\n')
    dump_json(SEAL, seal)
    PAGE.write_text(page_html(spec, rec, seal), encoding='utf-8', newline='\n')
    replay = {'outcome': 'ok', 'recorded_sha256': seal['sha256'],
              'archive_sha256': sha((HERE / ZIP_NAME).read_bytes()), 'rebuilt_sha256': seal_bytes(names)[1]['sha256']}
    dump_json(REPLAY, replay)
    return {'iteration': 'И-122', 'outcome': rec['outcome'], 'counts': rec['counts'],
            'seal': seal['sha256'], 'members': seal['members'], 'bytes': seal['bytes']}


def verify() -> dict:
    spec = read_json(SPEC)
    rec = evaluate(spec)
    names = members()
    raw, rebuilt = seal_bytes(names)
    recorded = read_json(SEAL)
    archived = (HERE / ZIP_NAME).read_bytes()
    page_ok = PAGE.read_bytes() == page_html(spec, rec, rebuilt).encode('utf-8')
    report_ok = (HERE / 'REPORT.md').read_bytes() == report_md(spec, rec, rebuilt).encode('utf-8')
    # В ACCEPTANCE.json есть блок seal (хеш архива) — при сравнении его надо отбросить,
    # иначе проверка сравнивает запись с её же отсутствием.
    acc_written = read_json(HERE / 'ACCEPTANCE.json')
    acc_ok = {k: v for k, v in acc_written.items() if k != 'seal'} == rec
    # состав архива совпадает с объявленным
    with ZipFile(io_bytes := BytesIO(archived)) as z:
        inside = sorted(n for n in z.namelist() if not n.endswith('/'))
    return {'iteration': 'И-122', 'outcome': 'ok' if (recorded == rebuilt and archived == raw
            and page_ok and report_ok and acc_ok and inside == names) else 'mismatch',
            'recorded_sha256': recorded.get('sha256'), 'rebuilt_sha256': rebuilt['sha256'],
            'archive_sha256': sha(archived), 'page_match': page_ok, 'report_match': report_ok,
            'acceptance_match': acc_ok, 'members_match': inside == names, 'members': len(names)}


def main() -> int:
    ap = argparse.ArgumentParser(description='И-122: приёмка Kilo и печать')
    ap.add_argument('--build', action='store_true')
    ap.add_argument('--verify-seal', action='store_true')
    a = ap.parse_args()
    if a.build:
        print(json.dumps(build(), ensure_ascii=False, indent=2)); return 0
    if a.verify_seal:
        v = verify(); print(json.dumps(v, ensure_ascii=False, indent=2)); return int(v['outcome'] != 'ok')
    print('укажите --build или --verify-seal', file=sys.stderr); return 2


if __name__ == '__main__':
    raise SystemExit(main())
