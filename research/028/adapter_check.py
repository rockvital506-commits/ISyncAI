#!/usr/bin/env python3
"""И-027: независимая проверка адаптера GitHub Copilot / VS Code.

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
ap.add_argument('--adapter', default='copilot')
ARGS = ap.parse_args()
TREE = pathlib.Path(ARGS.tree).absolute()
spec = importlib.util.spec_from_file_location('kit_contract', TREE / 'kit/tools/contract.py')
c = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = c
spec.loader.exec_module(c)
VERSION = c.parse((TREE / 'kit/base/manifest.json').read_bytes())['base_version']
PIN = c.digest((TREE / 'kit/base/manifest.json').read_bytes())

LAYOUTS = {
    'copilot-repo-wide': {'.github/copilot-instructions.md': b'# synthetic copilot instructions\n'},
    'copilot-path-specific': {'.github/instructions/python.instructions.md':
                              b'---\napplyTo: "**/*.py"\n---\n- synthetic path rule\n'},
    'copilot-agents-dir': {'.github/agents/planner.agent.md': b'# synthetic agent\n'},
    'copilot-skills-dir': {'.github/skills/sample/SKILL.md': b'# synthetic skill\n'},
    'vscode-settings': {'.vscode/settings.json': b'{"synthetic":true}\n'},
    'claude-fallback-root': {'CLAUDE.md': b'# synthetic claude\n'},
    'gemini-fallback-root': {'GEMINI.md': b'# synthetic gemini\n'},
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
    card = call('adapter', 'A', {'name': ARGS.adapter})
    after = tree_state(root)
    add('карточка адаптера Copilot',
        'вход AGENTS.md, рекомендованный средой .github/copilot-instructions.md, '
        'entry_shared false, старшинство 3 из 5, пробелы покрытия, ничего не пишет',
        {k: card[k] for k in ('entry', 'entry_recommended', 'entry_shared', 'discovery_proven', 'writes')},
        card['entry'] == 'AGENTS.md' and card['entry_recommended'] == '.github/copilot-instructions.md'
        and card['entry_shared'] is False and card['priority']['tier'] == 'repository'
        and card['priority']['rank'] == 3 and card['priority']['of'] == 5
        and [x['rank'] for x in card['priority']['order']] == [1, 2, 3, 4, 5]
        and card['priority']['order'][3]['ours'] is True
        and 'Copilot Chat on github.com' in card['coverage']['coverage_gap']
        and 'inline suggestions' in card['coverage']['coverage_gap']
        and card['discovery_proven'] is False and card['writes'] is False and before == after)

    # A2. второй вход не создаётся
    root = project('A2')
    refusals = {}
    for requested in ('.github/copilot-instructions.md', 'CLAUDE.md', 'GEMINI.md',
                      '.github/instructions/any.instructions.md'):
        try:
            c.dispatch(lab, 'A2', 'plan', dict(op='connect', entry_path=requested))
            refusals[requested] = 'принято'
        except c.Refusal as exc:
            refusals[requested] = exc.code
    approved('A2', dict(op='connect', entry_path='AGENTS.md'))
    add('второй вход запрещён кодом second_entry',
        'любой путь, кроме AGENTS.md, отклонён; с AGENTS.md вход создан, .github/ не появился',
        dict(refusals=refusals, github_dir_exists=(root / '.github').exists(),
             entry_exists=(root / 'AGENTS.md').exists()),
        all(code == 'second_entry' for code in refusals.values())
        and not (root / '.github').exists() and (root / 'AGENTS.md').exists())

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
        def covered(rel):
            if rel in paths:
                return True
            node = pathlib.PurePosixPath(rel).parent
            while node.as_posix() not in ('.', ''):
                if node.as_posix() in paths:
                    return True
                node = node.parent
            return False
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
    call('adapter', 'E', {'name': ARGS.adapter})
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
    card = call('adapter', 'E', {'name': ARGS.adapter})
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
    out = dict(iteration='И-028', line=ARGS.line, version=VERSION, counts=dict(sorted(counts.items())),
               rows=rows, ok=all(row['status'] == 'pass' for row in rows))
    (HERE / f'adapter-{ARGS.line}.json').write_text(
        json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    for row in rows:
        print(f"  {row['status']:5} {row['case']}")
    print(json.dumps(out['counts'], ensure_ascii=False), 'ok:', out['ok'])
    return 0 if out['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
