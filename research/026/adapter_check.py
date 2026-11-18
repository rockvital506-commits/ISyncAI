#!/usr/bin/env python3
"""И-026: независимая проверка адаптера Kilo.

Не повторяет регрессии комплекта: строит синтетические проекты в раскладке Kilo, гоняет команды
`adapter`, `inventory`, `connect` через настоящий продукт 0.1.6 и смотрит на файлы.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import pathlib
import shutil
import sys
import tempfile

HERE = pathlib.Path(__file__).absolute().parent
ap = argparse.ArgumentParser()
ap.add_argument('--tree', required=True)
ap.add_argument('--line', default='base')
ARGS = ap.parse_args()
TREE = pathlib.Path(ARGS.tree).absolute()
spec = importlib.util.spec_from_file_location('kit_contract', TREE / 'kit/tools/contract.py')
c = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = c
spec.loader.exec_module(c)
VERSION = c.parse((TREE / 'kit/base/manifest.json').read_bytes())['base_version']
PIN = c.digest((TREE / 'kit/base/manifest.json').read_bytes())

LAYOUTS = {
    'kilo-project-config': {'.kilo/kilo.jsonc': b'{"instructions":["rules/a.md"]}\n'},
    'kilo-rules-current': {'.kilo/rules/rules.md': b'- synthetic current rule\n'},
    'kilo-rules-compat': {'.kilocode/rules/legacy.md': b'- synthetic compat rule\n'},
    'kilo-rules-legacy-file': {'.kilocoderules': b'- synthetic legacy file\n'},
    'kilo-entry-fallback': {'AGENT.md': b'- synthetic fallback entry\n'},
    'kilo-root-config': {'kilo.jsonc': b'{"synthetic":true}\n'},
}


def tree_state(root: pathlib.Path) -> dict:
    state = {}
    for path in sorted(root.rglob('*')):
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            state[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return state


def main():
    lab = pathlib.Path(tempfile.mkdtemp(prefix='i026-'))
    shutil.copytree(TREE / 'releases', lab / 'releases')
    rows = []

    def add(case, expected, actual, ok, notes=''):
        rows.append(dict(case=case, expected=expected, actual=actual, status='pass' if ok else 'fail',
                         notes=notes))

    def call(command, project, payload=None):
        return c.dispatch(lab, project, command, {} if payload is None else payload)

    def approved(project, request):
        view = c.dispatch(lab, project, 'plan', request)
        return c.dispatch(lab, project, 'apply', {'request': request, 'ticket': view['ticket']})

    def project(name):
        root = lab / name
        root.mkdir()
        approved(name, dict(op='install', package=f'releases/{VERSION}', pin=PIN))
        return root

    # A. карточка среды
    root = project('A')
    before = tree_state(root)
    card = call('adapter', 'A', {'name': 'kilo'})
    after = tree_state(root)
    add('карточка адаптера Kilo', 'вход, запасное имя, старшинство 3 из 4, источники, ничего не пишет',
        {k: card[k] for k in ('entry', 'entry_fallback', 'sources', 'discovery_proven', 'writes')},
        card['entry'] == 'AGENTS.md' and card['entry_fallback'] == 'AGENT.md' and card['priority']['rank'] == 3
        and card['priority']['of'] == 4 and [x['rank'] for x in card['priority']['order']] == [1, 2, 3, 4]
        and card['discovery_proven'] is False and card['writes'] is False and before == after)

    # B. неизвестная среда
    try:
        call('adapter', 'A', {'name': 'synthetic-unknown'})
        add('неизвестная среда', 'отказ adapter_unknown', 'принято', False)
    except c.Refusal as exc:
        add('неизвестная среда', 'отказ adapter_unknown', exc.code, exc.code == 'adapter_unknown')

    # C. обнаружение каждой раскладки Kilo и подтверждение до создания входа
    for index, (name, files) in enumerate(sorted(LAYOUTS.items()), 1):
        root = project(f'C{index}')
        for rel, data in files.items():
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        before = tree_state(root)
        inventory = call('inventory', f'C{index}')
        paths = [item['path'] for item in inventory['native_paths']]
        expected_paths = [rel for rel in files]
        covered = lambda rel: rel in paths or any(str(pathlib.PurePosixPath(rel).parent).replace('.', '', 1) in p
                                                  or pathlib.PurePosixPath(rel).parent.as_posix() in p for p in paths)
        detected = all(covered(rel) for rel in expected_paths)
        kinds = {item['path']: item['kind'] for item in inventory['native_paths']}
        try:
            c.dispatch(lab, f'C{index}', 'plan', dict(op='connect'))
            refused = False
            detail = 'принято без подтверждения'
        except c.Refusal as exc:
            refused = exc.code == 'existing_sources'
            detail = exc.code
        ack = paths
        approved(f'C{index}', dict(op='connect', ack_existing=ack))
        after = tree_state(root)
        changed = {rel: (before.get(rel), after.get(rel)) for rel in set(before) | set(after)
                   if before.get(rel) != after.get(rel)}
        allowed = {k for k in changed if k == 'AGENTS.md' or k.startswith('.agent-contract/')}
        add(f'обнаружение и подтверждение: {name}',
            'источник виден без чтения, connect без подтверждения отклонён, файлы среды не изменены',
            dict(detected=detected, inventory_kind=[kinds.get(rel) for rel in expected_paths],
                 refused=detail, changed_outside_contract=sorted(set(changed) - allowed)),
            detected and refused and not (set(changed) - allowed),
            notes=f'подтверждено: {ack}')

    # D. порядок подтверждения — как в обнаружении, иначе отказ
    root = project('D')
    (root / '.kilo').mkdir()
    (root / '.kilo/kilo.jsonc').write_bytes(b'{"instructions":[]}\n')
    (root / '.kilocode/rules').mkdir(parents=True)
    (root / '.kilocode/rules/x.md').write_bytes(b'- synthetic\n')
    paths = [item['path'] for item in call('inventory', 'D')['native_paths']]
    order = [p for p in paths if p in ('.kilo/kilo.jsonc', '.kilocode/rules')]
    try:
        c.dispatch(lab, 'D', 'plan', dict(op='connect', ack_existing=list(reversed(order))))
        wrong = 'принято'
    except c.Refusal as exc:
        wrong = exc.code
    approved('D', dict(op='connect', ack_existing=order))
    add('порядок подтверждения', 'обратный порядок отклонён, прямой принят',
        dict(reversed_rejected=wrong, accepted=True), wrong == 'existing_sources')

    # E. адаптер не пишет в конфигурацию среды
    root = project('E')
    (root / '.kilo/rules').mkdir(parents=True)
    (root / '.kilo/rules/a.md').write_bytes(b'- synthetic\n')
    (root / '.kilo/kilo.jsonc').write_bytes(b'{"instructions":["rules/a.md"]}\n')
    (root / 'kilo.jsonc').write_bytes(b'{"synthetic":true}\n')
    (root / '.kilocoderules').write_bytes(b'- synthetic legacy\n')
    env_before = tree_state(root)
    env_paths = [item['path'] for item in call('inventory', 'E')['native_paths']]
    approved('E', dict(op='connect', ack_existing=env_paths))
    call('adapter', 'E', {'name': 'kilo'})
    call('status', 'E')
    call('inventory', 'E')
    approved('E', dict(op='record_check', observation=dict(
        case='kilo', level=2, conditions='Синтетический проект в раскладке Kilo', expected='Вход существует.',
        actual='Вход существует.', status='pass', evidence='AGENTS.md, строка 1', limits='Только наличие.',
        environment={k: 'synthetic' for k in c.ENV_KEYS.split()})))
    env_after = tree_state(root)
    changed = sorted(rel for rel in set(env_before) | set(env_after)
                     if env_before.get(rel) != env_after.get(rel) and not rel.startswith('.agent-contract/'))
    add('конфигурация среды не тронута',
        'изменяется только AGENTS.md; .kilo/**, .kilocode/**, kilo.jsonc, .kilocoderules — байт в байт',
        dict(changed=[rel for rel in changed if rel != 'AGENTS.md'],
             entry_created='AGENTS.md' in env_after),
        changed in ([], ['AGENTS.md']) and 'AGENTS.md' in env_after)

    # F. карточка не выдаёт обнаружение за проверку
    card = call('adapter', 'E', {'name': 'kilo'})
    add('обнаружение не заявлено как проверенное',
        'discovery_proven false, contents_read false, три непроверенных пункта',
        dict(discovery_proven=card['discovery_proven'], contents_read=card['contents_read'],
             not_proven=card['not_proven']),
        card['discovery_proven'] is False and card['contents_read'] is False
        and card['not_proven'] == ['auto-discovery', 'content_was_read', 'behaviour_with_model'])

    shutil.rmtree(lab, ignore_errors=True)
    counts = {}
    for row in rows:
        counts[row['status']] = counts.get(row['status'], 0) + 1
    out = dict(iteration='И-026', line=ARGS.line, version=VERSION, counts=dict(sorted(counts.items())),
               rows=rows, ok=all(row['status'] == 'pass' for row in rows))
    (HERE / f'adapter-{ARGS.line}.json').write_text(
        json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    for row in rows:
        print(f"  {row['status']:5} {row['case']}")
    print(json.dumps(out['counts'], ensure_ascii=False), 'ok:', out['ok'])
    return 0 if out['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
