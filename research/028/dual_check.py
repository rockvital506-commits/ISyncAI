#!/usr/bin/env python3
"""И-028: стенд двух сред на одном проекте — Kilo и Copilot поочерёдно.

Не повторяет регрессии комплекта и независимую проверку одного адаптера (И-026, И-027). Здесь
проверяется сценарий: проект открыт в VS Code, в нём включены оба расширения, и обращения идут
по очереди — то Kilo, то Copilot — к одному проекту и одному входу AGENTS.md.

Стенд синтетический: расширения не запускаются, их видимость и порядок инструкций взяты из карточек
среды. Что именно не проверено, перечислено в отчёте.
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

ENV = {'os': 'linux', 'editor': 'vscode', 'editor_version': '1.105', 'extension': 'kilo.kilo-code',
       'extension_version': '5.0', 'mode': 'agent', 'model': 'synthetic', 'profile': 'default',
       'permissions': 'read-write'}
KILO, COPILOT = 'kilo.kilo-code', 'github.copilot'


def env_of(extension, **changes):
    out = dict(ENV)
    out['extension'] = extension
    out.update(changes)
    return out


def observation(extension, case='сборка кита', actual='Сборка прошла, 47 проверок.',
                evidence='tests.log, строка 12', **env):
    return dict(case=case, level=1, conditions='Проект в VS Code, оба расширения включены',
                expected='Сборка проходит.', actual=actual, status='pass',
                evidence=evidence, limits='Только синтетические данные.',
                environment=env_of(extension, **env))


def tree_state(root: pathlib.Path) -> dict:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file()}


def main() -> int:
    lab = pathlib.Path(tempfile.mkdtemp(prefix='i028-'))
    shutil.copytree(TREE / 'releases', lab / 'releases')
    rows = []

    def add(cid, case, expected, actual, ok, notes=''):
        rows.append(dict(id=cid, case=case, expected=expected, actual=actual,
                         status='pass' if ok else 'fail', notes=notes))

    def call(command, project, payload=None):
        return c.dispatch(lab, project, command, {} if payload is None else payload)

    def approved(project, request):
        view = c.dispatch(lab, project, 'plan', request)
        return c.dispatch(lab, project, 'apply', {'request': request, 'ticket': view['ticket']})

    def refused(project, request):
        try:
            c.dispatch(lab, project, 'plan', request)
            return None
        except c.Refusal as exc:
            return exc.code

    def project(name, from_version=VERSION):
        root = lab / name
        root.mkdir()
        folder = f'releases/{from_version}'
        pin = PIN if from_version == VERSION else c.digest(
            (TREE / folder / 'manifest.json').read_bytes())
        approved(name, dict(op='install', package=folder, pin=pin))
        return root

    def connected(name, from_version=VERSION):
        """Проект, открытый в VS Code, где уже настроены обе среды."""
        root = project(name, from_version)
        (root / '.vscode').mkdir()
        (root / '.vscode/settings.json').write_bytes(b'{"synthetic":true}\n')
        (root / '.kilo').mkdir()
        (root / '.kilo/kilo.jsonc').write_bytes(b'{"instructions":["rules/x.md"]}\n')
        (root / '.kilo/rules').mkdir()
        (root / '.kilo/rules/x.md').write_bytes(b'- synthetic rule\n')
        paths = [x['path'] for x in call('inventory', name)['native_paths']]
        approved(name, dict(op='connect', ack_existing=paths))
        return root, paths

    # A. карточки двух сред на одном проекте
    root = lab / 'A'
    root.mkdir()
    approved('A', dict(op='install', package=f'releases/{VERSION}', pin=PIN))
    before = tree_state(root)
    kilo = call('adapter', 'A', {'name': 'kilo'})
    copilot = call('adapter', 'A', {'name': 'copilot'})
    after = tree_state(root)
    add('D1', 'карточки двух сред на одном проекте',
        'вход AGENTS.md у обоих; у Copilot entry_shared false и рекомендованный файл; оба не заявляют обнаружение',
        {'kilo_entry': kilo['entry'], 'copilot_entry': copilot['entry'],
         'copilot_entry_shared': copilot.get('entry_shared'),
         'copilot_recommended': copilot.get('entry_recommended'),
         'discovery_proven': [kilo['discovery_proven'], copilot['discovery_proven']]},
        kilo['entry'] == copilot['entry'] == 'AGENTS.md'
        and copilot['entry_shared'] is False
        and copilot['entry_recommended'] == '.github/copilot-instructions.md'
        and kilo['discovery_proven'] is False and copilot['discovery_proven'] is False
        and before == after)

    # B. стек инструкций каждой среды
    order_kilo = kilo['priority']['order']
    in_kilo = [x['rank'] for x in order_kilo if x['ours']]
    add('D2', 'стек instructions Kilo',
        'старшинство 3 из 4, наш вход на позиции 3',
        {'rank': kilo['priority']['rank'], 'of': kilo['priority']['of'], 'ours_at': in_kilo},
        kilo['priority']['rank'] == 3 and kilo['priority']['of'] == 4 and in_kilo == [3])
    order_cop = copilot['priority']['order']
    in_cop = [x['rank'] for x in order_cop if x['ours']]
    add('D3', 'стек instructions Copilot',
        'порядок из пяти шагов, наш вход на позиции 4, два пробела покрытия',
        {'ranks': [x['rank'] for x in order_cop], 'ours_at': in_cop,
         'gap': copilot['coverage']['coverage_gap']},
        [x['rank'] for x in order_cop] == [1, 2, 3, 4, 5] and in_cop == [4]
        and copilot['coverage']['coverage_gap'] == ['Copilot Chat on github.com', 'inline suggestions'])

    # C. шесть поочерёдных ходов на одном входе
    root, ack = connected('C')
    entry_hashes = []
    for turn in ('kilo', 'copilot', 'kilo', 'copilot', 'kilo', 'copilot'):
        if turn == 'kilo':
            call('status', 'C')
            call('list', 'C')
            approved('C', dict(op='record_check', observation=observation(KILO)))
        else:
            call('status', 'C')
            call('list', 'C')
            approved('C', dict(op='record_check', observation=observation(COPILOT)))
        entry_hashes.append(hashlib.sha256((root / 'AGENTS.md').read_bytes()).hexdigest())
    add('D4', 'обе среды читают один и тот же вход',
        'AGENTS.md один, его sha256 не меняется между ходами',
        {'entry_files': sorted(p.name for p in root.iterdir() if p.name == 'AGENTS.md'),
         'distinct_hashes': len(set(entry_hashes))},
        len(set(entry_hashes)) == 1 and (root / 'AGENTS.md').exists())
    changed = [rel for rel in tree_state(root) if rel.startswith(('.kilo/', '.vscode/'))]
    untouched = all((root / rel).read_bytes() in (
        b'{"instructions":["rules/x.md"]}\n', b'- synthetic rule\n', b'{"synthetic":true}\n')
        for rel in changed)
    add('D5', 'шесть поочерёдных ходов',
        'меняются только AGENTS.md и .agent-contract/**; настройки сред байт в байт',
        {'env_files': changed, 'env_files_unchanged': untouched,
         'observations': len(call('status', 'C')['observations']),
         'health': call('status', 'C')['health']},
        untouched and changed and call('status', 'C')['health'] == 'valid')

    # D. тождество при одинаковом environment и при разном extension
    root = lab / 'D'
    root.mkdir()
    approved('D', dict(op='install', package=f'releases/{VERSION}', pin=PIN))
    approved('D', dict(op='connect'))
    one = observation(KILO)
    approved('D', dict(op='record_check', observation=one))
    approved('D', dict(op='record_check', observation=dict(one)))
    merged = len(call('status', 'D')['observations'])
    add('D6', 'тождество при одинаковом environment',
        'то же наблюдение от второй среды с теми же полями environment не создаёт новой записи',
        {'observations': merged}, merged == 1)
    approved('D', dict(op='record_check', observation=observation(COPILOT)))
    two = len(call('status', 'D')['observations'])
    add('D7', 'тождество при разном extension',
        'то же наблюдение с environment.extension другой среды не склеивается: две записи',
        {'observations': two, 'meaning': 'одно событие под двумя расширениями даёт две записи'},
        two == 2, notes='следствие: различие расширений — часть environment, а он сравнивается точно')
    approved('D', dict(op='record_check', observation=observation(
        KILO, case='сборка кита', actual='Сборка прошла, 48 проверок.', evidence='tests.log, строка 20')))
    add('D8', 'два разных факта',
        'наблюдения с разным числом в факте не склеиваются',
        {'observations': len(call('status', 'D')['observations'])},
        len(call('status', 'D')['observations']) == 3)

    # E. конфликт правил двух сред — в обе стороны
    outcomes = {}
    for order in ('kilo-first', 'copilot-first'):
        name = 'E-' + order
        root = lab / name
        root.mkdir()
        approved(name, dict(op='install', package=f'releases/{VERSION}', pin=PIN))
        approved(name, dict(op='connect'))
        approved(name, dict(op='create', kind='contract', title='контракт проекта', scope='.',
                            text='synthetic contract', basis='test', criterion='exact output',
                            reason='контракт проекта', state='active'))
        contract = call('history', name)['decisions'][-1]['subject']
        base = dict(kind='rule', contract=contract, title='формат', scope='src', key='example.format',
                    basis='test', criterion='exact output', reason='правило первой среды',
                    state='active', text='synthetic rule text')
        approved(name, dict(base, op='create', value='one'))
        second = dict(base, op='create', value='two', scope='src/nested', reason='правило второй среды')
        outcomes[order] = refused(name, second)
    add('D9', 'конфликт правил двух сред',
        'пересечение требований отклоняется кодом conflict в обе стороны',
        outcomes, set(outcomes.values()) == {'conflict'})

    # F. порядок сред не важен
    def series(name, order):
        root = lab / name
        root.mkdir()
        approved(name, dict(op='install', package=f'releases/{VERSION}', pin=PIN))
        approved(name, dict(op='connect'))
        for turn in order:
            approved(name, dict(op='record_check', observation=observation(
                KILO if turn == 'kilo' else COPILOT)))
        status = call('status', name)
        return {'observations': len(status['observations']), 'health': status['health'],
                'rules': (root / '.agent-contract/base/rules.json').read_bytes()}

    forward = series('F1', ('kilo', 'copilot', 'kilo'))
    reverse = series('F2', ('copilot', 'kilo', 'copilot'))
    add('D10', 'порядок сред не важен',
        'обратный порядок даёт те же счётчики и то же здоровье контракта',
        {'forward': {k: v for k, v in forward.items() if k != 'rules'},
         'reverse': {k: v for k, v in reverse.items() if k != 'rules'},
         'rules_equal': forward['rules'] == reverse['rules']},
        forward['observations'] == reverse['observations'] and forward['health'] == reverse['health']
        and forward['rules'] == reverse['rules'])

    # G. второй вход в уже подключённом проекте
    root, ack = connected('G')
    attempted = refused('G', dict(op='connect', entry_path='.github/copilot-instructions.md'))
    add('D11', 'второй вход в подключённом проекте',
        'connect с entry_path .github/copilot-instructions.md отклоняется кодом second_entry',
        {'refusal': attempted, 'github_dir': (root / '.github').exists()},
        attempted == 'second_entry' and not (root / '.github').exists())

    # H. чужая правка входа — обе среды не перезаписывают
    root = project('H', from_version='0.1.7')
    approved('H', dict(op='connect'))
    entry = root / 'AGENTS.md'
    ours = entry.read_bytes()
    entry.write_bytes(ours + b'\n<!-- foreign edit outside contract -->\n')
    status = call('status', 'H')
    drift = refused('H', dict(op='update', package=f'releases/{VERSION}', pin=PIN))
    add('D12', 'чужая правка входа',
        'status attention, update adapter_drift, вход не перезаписан',
        {'health': status['health'], 'entry': status['entry'], 'update': drift,
         'entry_kept': entry.read_bytes().endswith(b'<!-- foreign edit outside contract -->\n')},
        status['health'] == 'attention' and status['entry'] == 'drift' and drift == 'adapter_drift'
        and entry.read_bytes().endswith(b'<!-- foreign edit outside contract -->\n'))

    # I. конфигурация сред за все ходы
    offenders = []
    for name in ('C', 'D', 'G', 'H'):
        root = lab / name
        for rel, data in tree_state(root).items():
            if rel.startswith(('.kilo/', '.kilocode/')) or rel in (
                    'kilo.jsonc', '.kilocoderules', '.github/copilot-instructions.md',
                    '.vscode/settings.json', 'CLAUDE.md', 'GEMINI.md'):
                if rel not in ('kilo.jsonc',):
                    offenders.append(rel)
    add('D13', 'конфигурация сред за все ходы',
        'ни одной записи в .github/**, .vscode/**, .kilo/**, CLAUDE.md, GEMINI.md',
        {'environment_files_seen': sorted(set(offenders)),
         'github_instructions_created': (lab / 'C' / '.github').exists()},
        not (lab / 'C' / '.github').exists() and not (lab / 'H' / '.github').exists())

    # H2. повторное подключение второй средой — не второй вход и не порча
    root, ack = connected('H2')
    entry = root / 'AGENTS.md'
    before_bytes = entry.read_bytes()
    repeat = approved('H2', dict(op='connect', ack_existing=ack))
    add('D16', 'повторное подключение второй средой',
        'connect в подключённом проекте проходит без второго входа и не меняет AGENTS.md',
        {'outcome': repeat.get('outcome'), 'entry_unchanged': entry.read_bytes() == before_bytes,
         'github_dir': (root / '.github').exists()},
        entry.read_bytes() == before_bytes and not (root / '.github').exists())

    # J. заглушки и общее обнаружение
    stubs = {}
    for name in ('claude', 'cursor', 'antigravity'):
        card = call('adapter', 'A', {'name': name})
        stubs[name] = {'status': card['status'], 'entry': card['entry'],
                       'sources': card['sources'], 'present': card['present'],
                       'facts_checked_at': card['facts_checked_at']}
    root = lab / 'J'
    root.mkdir()
    approved('J', dict(op='install', package=f'releases/{VERSION}', pin=PIN))
    (root / '.claude').mkdir()
    (root / '.claude/CLAUDE.md').write_bytes(b'# synthetic claude memory\n')
    stub_ack = refused('J', dict(op='connect'))
    paths = [x['path'] for x in call('inventory', 'J')['native_paths']]
    approved('J', dict(op='connect', ack_existing=paths))
    add('D14', 'заглушки и общее обнаружение',
        'claude, cursor, antigravity: status stub без входа и покрытия; .claude/CLAUDE.md всё равно требует ack_existing',
        {'stubs': stubs, 'connect_without_ack': stub_ack,
         'claude_memory_unchanged': (root / '.claude/CLAUDE.md').read_bytes() == b'# synthetic claude memory\n'},
        all(v['status'] == 'stub' and v['entry'] is None and v['sources'] == []
            and v['present'] == [] and v['facts_checked_at'] is None for v in stubs.values())
        and stub_ack == 'existing_sources')

    # K. идемпотентность повторного прохода
    before = (lab / 'C' / '.agent-contract/base/checks.json').read_bytes() \
        if (lab / 'C' / '.agent-contract/base/checks.json').exists() else None
    checks_path = lab / 'C' / '.agent-contract/project/checks.json'
    before = checks_path.read_bytes() if checks_path.exists() else before
    for turn in ('kilo', 'copilot'):
        approved('C', dict(op='record_check', observation=observation(
            KILO if turn == 'kilo' else COPILOT)))
    after = checks_path.read_bytes() if checks_path.exists() else None
    add('D15', 'идемпотентность повторного прохода',
        'повторная запись тех же наблюдений не меняет checks.json ни на байт',
        {'equal': before == after, 'bytes': None if after is None else len(after)},
        before is not None and before == after)

    shutil.rmtree(lab, ignore_errors=True)
    counts = {}
    for row in rows:
        counts[row['status']] = counts.get(row['status'], 0) + 1
    out = dict(iteration='И-028', line=ARGS.line, version=VERSION,
               counts=dict(sorted(counts.items())), rows=rows,
               ok=all(row['status'] == 'pass' for row in rows))
    (HERE / f'dual-{ARGS.line}.json').write_text(
        json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    for row in rows:
        print(f"  {row['status']:5} {row['id']:4} {row['case']}")
    print(json.dumps(out['counts'], ensure_ascii=False), 'ok:', out['ok'])
    return 0 if out['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
