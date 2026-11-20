#!/usr/bin/env python3
"""И-052: стенд обкатки — уровень L4T: контур машины состояний по аудиту A-001.

Сценарий владельца тот же, что в И-032–И-033: архив внутри репозитория, абсолютный путь проекта,
чужой `AGENTS.md`, запись наблюдений, слияние состояния двух машин через git. Новое здесь — два
последних пункта матрицы: P5 (порядок первого обращения исполняется буквально: каждая команда шага
действительно запускается) и P6 (в поставке есть инструкция обкатки: `docs/` в Edition, раздел в
`START.md` обеих линий).

Запуск: python3 pilot.py --tree ../release-0.1.32/base/AgentContractLab --line base
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).absolute().parent
PACK_VERSION = '0.1.32'
ENV_LOCAL = dict(os='windows', editor='vscode', editor_version='1.146.0', extension='kilo.kilo-code',
                 extension_version='5.0.0', mode='agent', model='local-model', profile='default',
                 permissions='read-write')
ENV_KILO = ENV_LOCAL
ENV_COPILOT = dict(ENV_LOCAL, editor='vscode', editor_version='1.147.0', extension='github.copilot-chat',
                   extension_version='0.30.0', profile='default')
ENV_ARENA = dict(os='linux', editor='arena', editor_version='cloud', extension='arena-agent',
                 extension_version='1', mode='agent', model='cloud-model', profile='default',
                 permissions='read-write')

ITEMS: list[dict] = []


def item(pid, title, expected, status, detail, evidence=None):
    ITEMS.append(dict(id=pid, title=title, expected=expected, status=status, detail=detail,
                      evidence=evidence or {}))


def sha(path) -> str:
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def git(cwd, *args):
    proc = subprocess.run(['git', *args], cwd=str(cwd), capture_output=True, text=True)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def cli(lab, project, command, payload=None, expect_error=False):
    """Опубликованный запуск: файл, отдельный процесс, JSON на входе и выходе."""
    args = [sys.executable, '-I', '-B', str(lab / 'kit/tools/contract.py'), '--lab', str(lab),
            '--project', str(project), command]
    proc = subprocess.run(args, input=(json.dumps(payload).encode() if payload is not None else b''),
                          capture_output=True, cwd=str(lab))
    if not expect_error:
        assert proc.stderr == b'', proc.stderr.decode()[-600:]
    try:
        out = json.loads(proc.stdout.decode())
    except Exception:
        out = {'raw': proc.stdout.decode()[:400], 'stderr': proc.stderr.decode()[-400:]}
    return proc.returncode, out



def rights_view_paths(rights):
    return set(rights.get('write_paths', []))

def approved(lab, project, request):
    rc, plan = cli(lab, project, 'plan', request)
    assert rc == 0, plan
    if not plan['changes']:
        return 'no_change'
    rc, out = cli(lab, project, 'apply', dict(request=request, ticket=plan['ticket']))
    assert rc == 0, out
    return out['outcome']


def install(lab, project):
    pin = sha(lab / f'releases/{PACK_VERSION}/manifest.json')
    return approved(lab, project, dict(op='install', package=f'releases/{PACK_VERSION}', pin=pin))


def observation(actual, env, case='сборка модуля'):
    return dict(case=case, level=1, conditions='Синтетический проект, одна проверка',
                expected='Проверка проходит.', actual=actual, status='pass',
                evidence='tests.log, строка 12', limits='Только синтетические данные.',
                environment=dict(env))


def record(lab, project, obs):
    rc, plan = cli(lab, project, 'plan', dict(op='record_check', observation=dict(obs)))
    assert rc == 0, plan
    if not plan['changes']:
        return 'no_change', plan['notes']
    rc, out = cli(lab, project, 'apply',
                  dict(request=dict(op='record_check', observation=dict(obs)), ticket=plan['ticket']))
    assert rc == 0, out
    return out['outcome'], plan['notes']


def discovery(lab, project, environment):
    rc, out = cli(lab, project, 'discovery', dict(environment=environment))
    assert rc == 0, out
    return out


def imitator(tree, environment):
    """Вторая реализация обнаружения: отдельный процесс, свой порядок, без импорта комплекта."""
    proc = subprocess.run([sys.executable, '-B', str(HERE / 'stand_env.py'), '--tree', str(tree),
                           '--environment', environment], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-400:]
    return json.loads(proc.stdout)


def entry_card(lab, project, environment):
    rc, out = cli(lab, project, 'entry', dict(environment=environment))
    assert rc == 0, out
    return out


def reader(tree, environment, marker=''):
    proc = subprocess.run([sys.executable, '-B', str(HERE / 'stand_reader.py'), '--tree', str(tree),
                           '--environment', environment, '--marker', marker],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-400:]
    return json.loads(proc.stdout)


def records(project):
    path = pathlib.Path(project) / '.agent-contract/project/checks.json'
    return json.loads(path.read_text(encoding='utf-8'))['checks'] if path.is_file() else []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--tree', required=True)
    ap.add_argument('--line', default='base')
    args = ap.parse_args()
    source = pathlib.Path(args.tree).absolute()
    assert (source / 'kit/tools/contract.py').is_file(), source

    root = pathlib.Path(tempfile.mkdtemp(prefix='pilot033-'))
    repo = root / 'myproject'
    repo.mkdir()
    shutil.copytree(source, repo / 'AgentContractLab')     # шаг 5 владельца
    lab = repo / 'AgentContractLab'
    (repo / 'README.md').write_text('проект владельца\n', encoding='utf-8')
    (repo / 'demo.txt').write_text('синтетический вход\n', encoding='utf-8')

    # --- P1. Раскладка владельца: архив внутри репозитория, проект — абсолютным путём ----------
    outcome_install = install(lab, repo)
    outcome_connect = approved(lab, repo, dict(op='connect'))
    state_path = repo / '.agent-contract/project/state.json'
    item('P1', 'Архив распакован в корень репозитория, установка без ручной правки',
         'install и connect проходят из консоли в раскладке шага 5',
         'pass' if outcome_install == 'committed' and outcome_connect == 'committed'
         and state_path.is_file() else 'fail',
         'проект задаётся абсолютным путём; относительный путь по-прежнему не выходит из комплекта',
         dict(install=outcome_install, connect=outcome_connect, state=str(state_path.relative_to(repo))))

    # --- P2. Вход занят: в проекте уже есть свой AGENTS.md --------------------------------------
    repo2 = root / 'second'
    repo2.mkdir()
    (repo2 / 'AGENTS.md').write_text('# инструкции проекта\n', encoding='utf-8')
    (repo2 / 'demo.txt').write_text('синтетический вход\n', encoding='utf-8')
    install(lab, repo2)
    rc, plan = cli(lab, repo2, 'plan', dict(op='connect'))
    rc_brief, brief = cli(lab, repo2, 'brief')
    rc_status, status = cli(lab, repo2, 'status')
    foreign_files = (repo2 / 'AGENTS.md').read_bytes()
    recorded, _notes2 = record(lab, repo2, observation('Проверка проходит.', ENV_LOCAL))
    untouched = (repo2 / 'AGENTS.md').read_bytes() == foreign_files
    item('P2', 'Вход уже занят чужим AGENTS.md',
         'документированный ручной вход вместо тупика; чужой файл не тронут',
         'pass' if plan.get('error') == 'foreign_entry' and rc_brief == 0
         and brief.get('mode') == 'foreign' and brief.get('writes') is False
         and status.get('entry_mode') == 'foreign' and untouched and recorded == 'committed' else 'fail',
         'connect по-прежнему отказывает; brief отдаёт строку для своего файла и путь к START.md; '
         'запись проверок от адаптера не зависит',
         dict(connect_error=plan.get('error'), brief_mode=brief.get('mode'),
              brief_line=(brief.get('line') or '')[:60], entry_mode=status.get('entry_mode'),
              foreign_untouched=untouched, recorded=recorded))

    # --- P3. Одно событие, увиденное двумя участниками ------------------------------------------
    rc_card, card = cli(lab, repo, 'identity')
    first, _ = record(lab, repo, observation('Проверка проходит.', ENV_KILO))
    second, notes_second = record(lab, repo, observation('Проверка проходит.', ENV_COPILOT))
    after_two_observers = len(records(repo))
    third, _ = record(lab, repo, observation('Проверка проходит.', dict(ENV_LOCAL, model='other-model')))
    after_other_model = len(records(repo))
    rule_ok = (rc_card == 0 and card.get('decision') == 'Б' and card.get('writes') is False
               and 'model' in card.get('compared', []) and 'os' in card.get('compared', [])
               and 'extension' in card.get('ignored', []))
    item('P3', 'Одно событие, увиденное локально Kilo и Copilot',
         'одна запись на событие при разных наблюдателях и двух записях при другой модели',
         'pass' if first == 'committed' and second == 'no_change' and after_two_observers == 1
         and third == 'committed' and after_other_model == 2 and rule_ok else 'fail',
         'правило названо данными: сравниваются os, mode, model, permissions; редактор и расширение — '
         'происхождение записи и не сравниваются. Поэтому смена участника не создаёт второго факта, '
         'а другая платформа или модель — создаёт: это объявленное следствие решения Б, а не провал',
         dict(identity=card.get('meaning'), compared=card.get('compared'), ignored=card.get('ignored'),
              kilo=first, copilot=second, copilot_notes=notes_second,
              after_two_observers=after_two_observers, other_model=third,
              after_other_model=after_other_model, identity_rc=rc_card))

    # --- P4. Два писателя: конфликт общего checks.json разрешается внутри продукта ---------------
    git(repo, 'init', '-q')
    git(repo, 'config', 'user.email', 'pilot@local')
    git(repo, 'config', 'user.name', 'pilot')
    git(repo, 'add', '-A')
    git(repo, 'commit', '-q', '-m', 'контракт установлен и наблюдения записаны')
    git(root, 'init', '-q', '--bare', 'origin.git')
    git(repo, 'remote', 'add', 'origin', str(root / 'origin.git'))
    rc_push, out_push = git(repo, 'push', '-q', 'origin', 'HEAD:main')
    rc_clone, out_clone = git(root, 'clone', '-q', '-b', 'main', str(root / 'origin.git'), 'arena')
    assert rc_push == 0 and rc_clone == 0, (out_push, out_clone)
    arena = root / 'arena'
    git(arena, 'config', 'user.email', 'arena@cloud')
    git(arena, 'config', 'user.name', 'arena')
    rc_arena_status, arena_status = cli(lab, arena, 'status')
    cloud_outcome, _ = record(lab, arena, observation('Проверка проходит.', ENV_ARENA, case='сборка в облаке'))
    git(arena, 'add', '-A')
    git(arena, 'commit', '-q', '-m', 'наблюдение из облака')
    rc_push_b, out_push_b = git(arena, 'push', '-q', 'origin', 'HEAD:main')
    local_outcome, _ = record(lab, repo, observation('Проверка проходит.', ENV_LOCAL, case='сборка отчёта'))
    git(repo, 'add', '-A')
    git(repo, 'commit', '-q', '-m', 'наблюдение локально')
    local_before = len(records(repo))
    rc_pull, out_pull = git(repo, 'pull', '-q', '--no-rebase', 'origin', 'main')
    conflicted = rc_pull != 0
    incoming_path = '.agent-contract/project/checks.incoming.json'
    merge_outcome, merge_notes, merge_dup = 'not run', None, None
    if conflicted:
        rc_show, incoming = git(repo, 'show', ':3:.agent-contract/project/checks.json')
        (repo / incoming_path).write_text(incoming + '\n', encoding='utf-8')
        git(repo, 'checkout', '--ours', '--', '.agent-contract/project/checks.json')
        rc_plan, merge_plan = cli(lab, repo, 'plan', dict(op='merge', incoming=incoming_path))
        merge_notes = merge_plan.get('notes')
        if rc_plan == 0 and merge_plan.get('changes'):
            rc_apply, applied = cli(lab, repo, 'apply',
                                    dict(request=dict(op='merge', incoming=incoming_path),
                                         ticket=merge_plan['ticket']))
            merge_outcome = applied.get('outcome') if rc_apply == 0 else applied.get('error')
        else:
            merge_outcome = merge_plan.get('error') or 'no_change'
        git(repo, 'add', '-A')
        rc_commit, out_commit = git(repo, 'commit', '-q', '-m', 'слияние состояния через merge')
        rc_push_c, out_push_c = git(repo, 'push', '-q', 'origin', 'HEAD:main')
    merged_records = records(repo)
    repeat_outcome = approved(lab, repo, dict(op='merge', incoming=incoming_path)) if conflicted else 'not run'
    after_repeat = len(records(repo))
    cases = {item_['observation']['case'] for item_ in merged_records}
    both_sides = {'сборка в облаке', 'сборка отчёта'} <= cases
    rc_repo_status, repo_status = cli(lab, repo, 'status')
    rc_arena_pull, out_arena_pull = git(arena, 'pull', '-q', '--no-rebase', 'origin', 'main')
    in_arena = len(records(arena))
    item('P4', 'Состояние переживает git: слияние двух писателей',
         'конфликт общего checks.json разрешается операцией merge без потери записей',
         'pass' if conflicted and merge_outcome == 'committed' and both_sides
         and repeat_outcome == 'no_change' and after_repeat == len(merged_records)
         and rc_repo_status == 0 and rc_arena_pull == 0 and in_arena == len(merged_records) else 'fail',
         'порядок владельца: сохранить входящую версию (git show :3:), оставить локальную '
         '(git checkout --ours), затем plan/apply merge и commit. merge только добавляет: известные '
         'наблюдения отбрасываются, ничего не удаляется',
         dict(transfer_ok=rc_arena_status == 0, pull_rc=rc_pull, conflicted=conflicted,
              cloud_outcome=cloud_outcome, local_outcome=local_outcome, local_before=local_before,
              merge_outcome=merge_outcome, merge_notes=merge_notes, repeat=repeat_outcome,
              merged=len(merged_records), after_repeat=after_repeat, cases=sorted(cases),
              arena_records=in_arena, pushed=rc_push_b,
              pushed_after_merge=rc_push_c if conflicted else None,
              arena_pull_rc=rc_arena_pull, arena_health=arena_status.get('health')))

    # --- P5. Первый промпт: порядок шагов, исполнимый буквально --------------------------------
    start = (repo / '.agent-contract/base/START.md').read_text(encoding='utf-8')
    steps = [l for l in start.splitlines() if l[:1].isdigit() and '. **' in l]
    commands = [line.split('`')[1].split(' ')[0] for line in steps]
    merge_incoming = '.agent-contract/project/checks.incoming.json'
    (repo / merge_incoming).write_bytes(json.dumps({'schema_version': 1, 'checks': [
        {'at': '2026-01-02T00:00:00Z', 'revision': 1, 'base_version': PACK_VERSION,
         'adapter_version': None, 'observation': observation('Проверка проходит.', ENV_ARENA,
                                                             case='сборка в облаке')}]},
        ensure_ascii=False).encode())
    payloads = [{}, {}, {}, {}, dict(name='kilo'), {}, dict(op='connect'),
                dict(op='record_check', observation=observation('Проверка проходит.', ENV_LOCAL)),
                dict(op='merge', incoming=merge_incoming), {}]
    keywords = ['`status`', '`list`', '`updates`', '`identity`', '`adapter', '`brief`',
                '`plan {"op": "connect"}`', '`op: record_check`', '`op: merge`', '`restore`']
    runs = []
    if len(steps) == 10:
        for step, command, payload, keyword in zip(steps, commands, payloads, keywords):
            rc_step, out_step = cli(lab, repo, command, payload if payload else None)
            runs.append(dict(step=step[:28], command=command, rc=rc_step,
                             error=out_step.get('error'), named=keyword in step))
    else:
        runs = [dict(step='нет', command=None, rc=1, error='steps', named=False)]
    order_ok = (len(steps) == 10
                and commands == ['status', 'list', 'updates', 'identity', 'adapter', 'brief',
                                 'plan', 'plan', 'plan', 'updates']
                and all(r['rc'] == 0 and r['named'] for r in runs))
    rights_not_changed = 'Права и глобальные настройки среды комплект не меняет' in start
    discovery_named = 'Обнаружение — не проверка' in start
    item('P5', 'Первый промпт исполним буквально',
         'десять шагов по порядку, каждый назван командой, каждая команда проходит',
         'pass' if order_ok and rights_not_changed and discovery_named else 'fail',
         'шаги не перечисление требований, а порядок: команда каждого шага запущена в том же проекте '
         'и вернула 0; права и поведение моделей в порядок не входят намеренно',
         dict(steps=len(steps), commands=commands, runs=runs, rights_not_changed=rights_not_changed,
              discovery_named=discovery_named))

    # --- P6. Инструкция обкатки внутри архива ---------------------------------------------------
    # runs/ — след прогонов, а не поставка: иначе L1 не воспроизводится из архива (замечание 0.1.32).
    archive_files = [p.name for p in source.rglob('*') if p.is_file()
                     and not ({'runs', '__pycache__'} & set(p.relative_to(source).parts))]
    docs_dir = source / 'docs'
    docs_page = docs_dir / 'ПЕРВЫЙ-ЗАПУСК.md'
    docs_text = docs_page.read_text(encoding='utf-8') if docs_page.is_file() else ''
    docs_steps = [l for l in docs_text.splitlines() if l[:1].isdigit() and '. ' in l]
    if args.line == 'edition':
        found = (docs_page.is_file() and docs_steps == steps
                 and 'условно пригодный' in docs_text
                 and 'python3 -I -B kit/tests/test_contract.py' in docs_text)
        detail = ('Edition несёт docs/ПЕРВЫЙ-ЗАПУСК.md: тот же порядок, что в START.md, плюс как '
                  'прогнать обкатку и что означает «условно пригодный»')
    else:
        found = (not docs_dir.exists() and bool(steps)
                 and 'Порядок первого обращения' in start)
        detail = ('базовая линия без docs/ — объявленная разница линий: порядок лежит разделом '
                  'START.md, проверять его можно оттуда')
    item('P6', 'В поставке есть инструкция обкатки',
         'владелец находит порядок действий внутри архива',
         'pass' if found else 'fail',
         detail,
         dict(files=len(archive_files), line=args.line, docs=docs_dir.exists(),
              docs_page=docs_page.name if docs_page.is_file() else None,
              docs_steps=len(docs_steps), steps=len(steps),
              hints=[n for n in archive_files if any(w in n.lower() for w in ('обкат', 'docs', 'инстр'))]))

    # --- P7. Ни одного шага с ручной правкой поставки -------------------------------------------
    hand_steps = []
    if outcome_install != 'committed' or outcome_connect != 'committed':
        hand_steps.append('P1: раскладку или установку пришлось делать иначе')
    if brief.get('mode') != 'foreign':
        hand_steps.append('P2: вход пришлось искать вручную')
    if merge_outcome != 'committed':
        hand_steps.append('P4: слияние двух писателей пришлось делать вручную')
    item('P7', 'Ни один шаг не требует ручной правки поставки',
         'весь сценарий проходится консолью',
         'pass' if not hand_steps else 'fail',
         '; '.join(hand_steps) or 'все шаги прошли консолью: установка, вход, ручной вход, запись, '
                                  'слияние',
         dict(hand_steps=hand_steps))

    # --- P8. Повторяемость ----------------------------------------------------------------------
    before = len(records(repo))
    repeat = []
    for _ in range(2):
        rc_s, st = cli(lab, repo, 'status')
        repeat.append((rc_s, len(st.get('observations', []))))
    item('P8', 'Повторный прогон даёт тот же результат',
         'два одинаковых вызова не меняют состояние',
         'pass' if len(set(repeat)) == 1 and repeat[0][1] == before else 'fail',
         f'состояние до повтора: {before}; два вызова status: {repeat}',
         dict(repeat=repeat))

    # --- Уровни достоверности: 1, 2, 3, 5 -------------------------------------------------------
    layouts = []

    def make_layout(name, files):
        folder = root / f'layout-{name}'
        folder.mkdir()
        for rel_path, body in files.items():
            target = folder / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding='utf-8')
        layouts.append((name, folder, sorted(files)))

    make_layout('entry', {'AGENTS.md': '# вход проекта\n'})
    make_layout('copilot', {'.github/copilot-instructions.md': '# инструкции проекта\n'})
    make_layout('both', {'AGENTS.md': '# вход проекта\n',
                         '.github/copilot-instructions.md': '# инструкции проекта\n'})

    l1, l2 = True, True
    detail1, detail2 = [], []
    for name, folder, expected in layouts:
        seen = discovery(lab, folder, 'kilo')
        ok1 = set(expected) <= set(seen['found'])
        l1 = l1 and ok1
        detail1.append(dict(layout=name, found=seen['found'], expected=expected, ok=ok1))
        for environment in ('kilo', 'copilot'):
            ours = discovery(lab, folder, environment)
            other = imitator(folder, environment)
            ok2 = ours['chosen'] == other['chosen']
            l2 = l2 and ok2
            detail2.append(dict(layout=name, environment=environment, ours=ours['chosen'],
                                imitator=other['chosen'], ok=ok2))

    # L3: содержимое прочитано — комплектом и независимым читателем, с одним и тем же отпечатком.
    marker = cli(lab, repo, 'brief')[1]['line']
    own = entry_card(lab, repo, 'kilo')
    twin = reader(repo, 'kilo', marker)
    l3 = (own['owned'] and not own['foreign'] and own['read'] is not None
          and all(own['read'][k] == twin['read'][k] for k in ('path', 'bytes', 'sha256', 'lines'))
          and own['marker_found'] and twin['read']['marker_found']
          and own['points_to'] == '.agent-contract/base/START.md'
          and own['levels']['3_content_read_by_contract'] == 'pass'
          and own['levels']['3_content_read_by_model'] == 'not run'
          and not own['content_proven'] and not own['writes'])
    detail3 = dict(path=own['path'], read=own['read'], imitator=twin['read'],
                   marker_found=own['marker_found'], points_to=own['points_to'],
                   by_contract=own['levels']['3_content_read_by_contract'],
                   by_model=own['levels']['3_content_read_by_model'])

    # L3F: чужой вход не читается — проект установлен, но вход занят чужим файлом.
    stranger = repo2
    foreign_bytes = (stranger / 'AGENTS.md').read_bytes()
    foreign = entry_card(lab, stranger, 'kilo')
    l3f = (foreign['foreign'] and not foreign['owned'] and foreign['read'] is None
           and foreign['content'] == 'not read (foreign)'
           and foreign['levels']['3_content_read_by_contract'] == 'not run'
           and (stranger / 'AGENTS.md').read_bytes() == foreign_bytes)
    detail3f = dict(path=foreign['path'], content=foreign['content'], bytes=foreign['bytes'],
                    untouched=(stranger / 'AGENTS.md').read_bytes() == foreign_bytes)

    # L4C: изменение существующего правила внесено комплектом и восстановимо по журналу (И-052).
    editor = root / 'edit-case'
    editor.mkdir()
    (editor / 'demo.txt').write_text('синтетический вход\n', encoding='utf-8')
    install(lab, editor)
    approved(lab, editor, dict(op='connect'))
    approved(lab, editor, dict(op='create', kind='contract', title='контракт', scope='.',
                               text='контракт проекта', basis='fixture', criterion='observable',
                               reason='создание контракта'))
    approved(lab, editor, dict(op='create', kind='rule', contract='P-1', title='правило', scope='src',
                               text='исходный текст', basis='fixture', criterion='observable',
                               reason='создание правила'))

    def state_of(project):
        return json.loads((project / '.agent-contract/project/state.json').read_text(encoding='utf-8'))

    def entry_of(project, ident):
        return next(e for e in state_of(project)['entries'] if e['id'] == ident)

    first = entry_of(editor, 'P-2')
    approved(lab, editor, dict(op='edit', id='P-2', fields=dict(text='новый текст'),
                               reason='уточнение формулировки'))
    second = entry_of(editor, 'P-2')
    decision_last = cli(lab, editor, 'history')[1]['decisions'][-1]
    restored = {c['field']: c['before'] for c in decision_last.get('changes', [])}
    approved(lab, editor, dict(op='edit', id='P-2', fields=dict(text=restored.get('text')),
                               reason='возврат по журналу'))
    third = entry_of(editor, 'P-2')
    rc_bad, bad = cli(lab, editor, 'plan', dict(op='edit', id='P-2', fields=dict(scope='docs'),
                                               reason='перенос области'), expect_error=True)
    scope_refused = (rc_bad == 2 and bad.get('error') == 'scope'
                     and bad.get('details') == {'from': 'src', 'to': 'docs'})
    rc_kind, kind_bad = cli(lab, editor, 'plan', dict(op='edit', id='P-2', fields=dict(kind='contract'),
                                                      reason='нельзя'), expect_error=True)
    approved(lab, editor, dict(op='edit', id='P-2', fields=dict(scope='docs'), allow_scope=True,
                               reason='перенос области'))
    fourth = entry_of(editor, 'P-2')
    scope_decision = cli(lab, editor, 'history')[1]['decisions'][-1]
    l4c = (first['text'] == 'исходный текст' and second['text'] == 'новый текст'
           and second['revision'] == first['revision'] + 1
           and decision_last['changes'] == [{'field': 'text', 'before': 'исходный текст',
                                             'after': 'новый текст'}]
           and third['text'] == 'исходный текст' and restored.get('text') == 'исходный текст'
           and scope_refused and rc_kind == 2 and kind_bad.get('error') == 'fields'
           and fourth['scope'] == 'docs'
           and scope_decision['changes'] == [{'field': 'scope', 'before': 'src', 'after': 'docs'}])
    detail4c = dict(before=first['text'], after=second['text'], restored=third['text'],
                    revision=[first['revision'], second['revision']],
                    decision=decision_last.get('changes'), scope_refusal=bad.get('details'),
                    immutable=kind_bad.get('error'), scope=dict(before='src', after=fourth['scope']),
                    scope_decision=scope_decision.get('changes'))

    # L4Q: разовый запрос не сохраняется, не требует реестра и допустим в повторе (И-052).
    def tree_state(project):
        base = project / '.agent-contract'
        out = {}
        for path in sorted(base.rglob('*')):
            if path.is_file():
                out[path.relative_to(project).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
        return out

    before_ask = tree_state(editor)
    ask = cli(lab, editor, 'session', dict(kind='temporary', text='прогони сборку один раз', scope='src'))[1]
    proposal = cli(lab, editor, 'session', dict(kind='proposal', text='добавь проверку'))[1]
    after_ask = tree_state(editor)
    rc_rule, rule_bad = cli(lab, editor, 'session', dict(kind='rule', text='правило'), expect_error=True)
    rc_save, save_bad = cli(lab, editor, 'session', dict(kind='temporary', text='разово', save=True),
                            expect_error=True)
    series_ask = cli(lab, editor, 'repeat', dict(runs=2, requests=[
        dict(command='session', payload=dict(kind='hypothesis', text='что если'))]))[1]
    after_series = tree_state(editor)
    l4q = (ask.get('persisted') is False and ask.get('stored') is False and ask.get('writes') is False
           and ask.get('rule_created') is False and ask.get('active_rule_created') is False
           and ask.get('project_unchanged') is True and ask.get('applies') == 'этот запуск'
           and proposal.get('stored') is False and before_ask == after_ask
           and rc_rule == 2 and rule_bad.get('error') == 'not_a_request'
           and rc_save == 2 and save_bad.get('error') == 'not_saved'
           and save_bad.get('details', {}).get('as_rule', {}).get('op') == 'create'
           and series_ask.get('identical') is True and series_ask.get('project_unchanged') is True
           and before_ask == after_series)
    detail4q = dict(kind=ask.get('kind'), stored=ask.get('stored'), writes=ask.get('writes'),
                    applies=ask.get('applies'), files_before=len(before_ask), files_after=len(after_ask),
                    unchanged=before_ask == after_ask, rule_refusal=rule_bad.get('error'),
                    save_refusal=save_bad.get('error'),
                    save_points_to=save_bad.get('details', {}).get('as_rule', {}).get('op'),
                    series_identical=series_ask.get('identical'))

    # L4D: отмена сохраняет запись, удаление оставляет след (И-052).
    approved(lab, editor, dict(op='create', kind='rule', contract='P-1', title='временное правило',
                               scope='tmp', text='временный текст', basis='fixture',
                               criterion='observable', reason='создание'))
    third_id = 'P-3'
    approved(lab, editor, dict(op='transition', id=third_id, to='revoked', reason='отзыв'))
    kept = entry_of(editor, third_id)
    removed_before = cli(lab, editor, 'removed')[1]
    approved(lab, editor, dict(op='purge', id=third_id, reason='удаление', allow_delete=True))
    removed_after = cli(lab, editor, 'removed')[1]
    state_after = state_of(editor)
    status_after = cli(lab, editor, 'status')[1]
    trace = (removed_after.get('removed') or [{}])[0]
    l4d = (kept['state'] == 'revoked' and kept['text'] == 'временный текст'
           and removed_before.get('count') == 0
           and removed_after.get('count') == 1 and trace.get('id') == third_id
           and trace.get('kind') == 'rule' and trace.get('reason') == 'удаление'
           and 'text' not in trace and 'value' not in trace
           and third_id not in [e['id'] for e in state_after['entries']]
           and status_after.get('removed') == 1)
    detail4d = dict(revoked=kept['state'], text_kept=kept['text'], before=removed_before.get('count'),
                    after=removed_after.get('count'),
                    trace={k: v for k, v in trace.items() if k != 'at'},
                    in_entries=third_id in [e['id'] for e in state_after['entries']],
                    status_removed=status_after.get('removed'))

    # L4S: секрет не пишется в реестр и не печатается из старого реестра (И-052).
    secret_case = root / 'secret-case'
    secret_case.mkdir()
    (secret_case / 'demo.txt').write_text('синтетический вход\n', encoding='utf-8')
    install(lab, secret_case)
    approved(lab, secret_case, dict(op='connect'))
    approved(lab, secret_case, dict(op='create', kind='contract', title='контракт', scope='.',
                                    text='контракт проекта', basis='fixture', criterion='observable',
                                    state='active', reason='создание контракта'))
    token = 'ghp_' + 'A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8'
    rc_secret, secret_refusal = cli(lab, secret_case, 'plan',
                                    dict(op='create', kind='rule', contract='P-1', title='правило',
                                         scope='.', text='токен ' + token, basis='fixture',
                                         criterion='observable', reason='создание'), expect_error=True)
    stored = state_of(secret_case)
    legacy = json.loads(json.dumps(stored, ensure_ascii=False))
    legacy['entries'][0]['text'] = 'ключ ' + token
    (secret_case / '.agent-contract/project/state.json').write_text(
        json.dumps(legacy, ensure_ascii=False, sort_keys=True, indent=2) + '\n', encoding='utf-8')
    listing = cli(lab, secret_case, 'list')[1]
    dumped = json.dumps(listing, ensure_ascii=False)
    l4s = (rc_secret == 2 and secret_refusal.get('error') == 'secret'
           and secret_refusal.get('details', {}).get('field') == 'text'
           and secret_refusal.get('details', {}).get('kind') == 'github_token'
           and token not in json.dumps(secret_refusal, ensure_ascii=False)
           and token not in json.dumps(stored, ensure_ascii=False)
           and token not in dumped and '[скрыто]' in dumped and listing.get('redacted', 0) >= 1)
    detail4s = dict(refusal=secret_refusal.get('error'), field=secret_refusal.get('details', {}).get('field'),
                    kind=secret_refusal.get('details', {}).get('kind'),
                    value_not_echoed=token not in json.dumps(secret_refusal, ensure_ascii=False),
                    stored_clean=token not in json.dumps(stored, ensure_ascii=False),
                    printed=token in dumped, redacted=listing.get('redacted'))

    # L4O: правило меняет только владелец, передача владения — с согласия (И-052).
    owner_case = root / 'owner-case'
    owner_case.mkdir()
    (owner_case / 'demo.txt').write_text('синтетический вход\n', encoding='utf-8')
    install(lab, owner_case)
    approved(lab, owner_case, dict(op='connect'))
    approved(lab, owner_case, dict(op='create', kind='contract', title='контракт', scope='.',
                                   text='контракт проекта', basis='fixture', criterion='observable',
                                   state='active', reason='создание контракта'))
    approved(lab, owner_case, dict(op='create', kind='rule', contract='P-1', title='правило', scope='src',
                                   text='текст', basis='fixture', criterion='observable',
                                   owner='alice', reason='создание правила'))
    rc_no_actor, no_actor = cli(lab, owner_case, 'plan',
                                dict(op='edit', id='P-2', fields=dict(text='иначе'), reason='нельзя'),
                                expect_error=True)
    approved(lab, owner_case, dict(op='edit', id='P-2', fields=dict(text='новый текст'),
                                   actor='alice', reason='уточнение'))
    rc_transfer, transfer_bad = cli(lab, owner_case, 'plan',
                                    dict(op='edit', id='P-2', fields=dict(owner='bob'),
                                         actor='alice', reason='передача'), expect_error=True)
    approved(lab, owner_case, dict(op='edit', id='P-2', fields=dict(owner='bob'), actor='alice',
                                   allow_owner=True, reason='передача'))
    rc_old, old_bad = cli(lab, owner_case, 'plan',
                          dict(op='edit', id='P-2', fields=dict(text='снова'), actor='alice',
                               reason='нельзя'), expect_error=True)
    owner_entry = entry_of(owner_case, 'P-2')
    l4o = (rc_no_actor == 2 and no_actor.get('error') == 'not_owner'
           and no_actor.get('details', {}).get('owner') == 'alice'
           and owner_entry['text'] == 'новый текст' and owner_entry['owner'] == 'bob'
           and rc_transfer == 2 and transfer_bad.get('error') == 'owner'
           and transfer_bad.get('details') == {'from': 'alice', 'to': 'bob'}
           and rc_old == 2 and old_bad.get('error') == 'not_owner')
    detail4o = dict(no_actor=no_actor.get('error'), owner=no_actor.get('details', {}).get('owner'),
                    text_after=owner_entry['text'], transfer_refusal=transfer_bad.get('error'),
                    transfer_details=transfer_bad.get('details'), new_owner=owner_entry['owner'],
                    old_owner_refused=old_bad.get('error'))

    # L4V: версия — содержимое, повтор — не правка, срок проверки — данные записи (И-052).
    version_case = root / 'version-case'
    version_case.mkdir()
    (version_case / 'demo.txt').write_text('синтетический вход\n', encoding='utf-8')
    install(lab, version_case)
    approved(lab, version_case, dict(op='connect'))
    approved(lab, version_case, dict(op='create', kind='contract', title='контракт', scope='.',
                                     text='контракт проекта', basis='fixture', criterion='observable',
                                     state='active', reason='создание контракта'))
    approved(lab, version_case, dict(op='create', kind='rule', contract='P-1', title='правило', scope='src',
                                     text='текст', basis='fixture', criterion='observable',
                                     owner='alice', state='active', reason='создание правила'))
    _, repeat = cli(lab, version_case, 'plan', dict(op='edit', id='P-2', fields=dict(text='текст'),
                                                    actor='alice', reason='повтор'))
    after_repeat = entry_of(version_case, 'P-2')
    approved(lab, version_case, dict(op='edit', id='P-2', fields=dict(text='новый текст'),
                                     actor='alice', reason='уточнение'))
    edited = entry_of(version_case, 'P-2')
    _, due_before = cli(lab, version_case, 'due', {})
    approved(lab, version_case, dict(op='review', id='P-2', actor='alice', reason='просмотрено'))
    reviewed = entry_of(version_case, 'P-2')
    _, due_after = cli(lab, version_case, 'due', {})
    approved(lab, version_case, dict(op='transition', id='P-2', to='suspended', actor='alice',
                                     reason='пауза'))
    paused = entry_of(version_case, 'P-2')
    l4v = (repeat.get('same') == ['text'] and after_repeat['revision'] == 1
           and edited['revision'] == 2 and edited['text'] == 'новый текст'
           and due_before.get('count') == 1 and due_before['due'][0].get('never') is True
           and reviewed.get('review_by') and reviewed['review_by'] > reviewed['reviewed_at']
           and reviewed['revision'] == 2
           and due_after.get('count') == 0 and due_after.get('writes') is False
           and paused['state'] == 'suspended' and paused['revision'] == 2)
    detail4v = dict(same=repeat.get('same'), revision_after_repeat=after_repeat['revision'],
                    revision_after_edit=edited['revision'],
                    due_before=due_before.get('count'),
                    review_by_after_reviewed=bool(reviewed.get('review_by') and reviewed['review_by'] > reviewed['reviewed_at']),
                    review_days=reviewed.get('review_days'),
                    revision_after_review=reviewed['revision'],
                    due_after=due_after.get('count'), writes=due_after.get('writes'),
                    revision_after_transition=paused['revision'])

    # L4X: неизвестная схема — отказ с ответом, восстановление из журнала без потери (И-052).
    schema_case = root / 'schema-case'
    schema_case.mkdir()
    (schema_case / 'demo.txt').write_text('синтетический вход\n', encoding='utf-8')
    install(lab, schema_case)
    approved(lab, schema_case, dict(op='connect'))
    approved(lab, schema_case, dict(op='create', kind='contract', title='контракт', scope='.',
                                    text='контракт проекта', basis='fixture', criterion='observable',
                                    state='active', reason='создание контракта'))
    state_file = schema_case / '.agent-contract/project/state.json'
    good = state_file.read_bytes()
    approved(lab, schema_case, dict(op='edit', id='P-1', fields=dict(text='правка'), reason='правка'))
    _, ops = cli(lab, schema_case, 'operations')
    backup = None
    for op in ops['operations']:
        if op['status'] != 'committed':
            continue
        candidate = schema_case / '.agent-contract/local/ops' / op['tx'] / 'before/.agent-contract/project/state.json'
        if candidate.exists() and candidate.read_bytes() == good:
            backup = candidate
    state_file.write_bytes(good.replace(b'"schema_version": 1', b'"schema_version": 2', 1))
    broken = state_file.read_bytes()
    rc_status, refused = cli(lab, schema_case, 'status', None, expect_error=True)
    rc_migrate, migrate_refused = cli(lab, schema_case, 'plan', dict(op='migrate', reason='обновить'),
                                     expect_error=True)
    untouched = state_file.read_bytes() == broken
    restored = None
    if backup is not None:
        state_file.write_bytes(backup.read_bytes())
        restored = cli(lab, schema_case, 'status', None)[1]
    l4x = (rc_status == 2 and refused.get('error') == 'unknown_schema'
           and refused.get('details', {}).get('found') == 2
           and refused.get('details', {}).get('supported') == [1]
           and refused.get('details', {}).get('migrate') is False
           and rc_migrate == 2 and migrate_refused.get('error') == 'unknown_schema'
           and untouched and backup is not None
           and restored is not None and restored.get('health') == 'valid')
    detail4x = dict(status_refusal=refused.get('error'), found=refused.get('details', {}).get('found'),
                    supported=refused.get('details', {}).get('supported'),
                    migrate_refusal=migrate_refused.get('error'), data_untouched=untouched,
                    backup_found=backup is not None,
                    restored_health=(restored or {}).get('health'))

    # L4P: частичный сбой — половина записи и половина файла (И-052).
    child = '''
import sys, importlib.util, json, pathlib, os
s=importlib.util.spec_from_file_location('offline_child', sys.argv[1]); m=importlib.util.module_from_spec(s)
sys.modules[s.name]=m; s.loader.exec_module(m)
r,t=json.loads(sys.stdin.buffer.read())
m.apply(pathlib.Path(sys.argv[2]), sys.argv[3], r, t,
        _after_write=lambda n: os._exit(75) if n==int(sys.argv[4]) else None)
'''

    def broken(project, request, after):
        _, view = cli(lab, project, 'plan', request)
        proc = subprocess.run([sys.executable, '-I', '-B', '-c', child,
                               str(lab / 'kit/tools/contract.py'), str(lab), str(project), str(after)],
                              input=json.dumps([request, view['ticket']]).encode(), capture_output=True)
        return proc.returncode

    half = root / 'half-case'
    half.mkdir()
    (half / 'demo.txt').write_text('синтетический вход\n', encoding='utf-8')
    install(lab, half)
    rc_stop = broken(half, dict(op='connect'), 1)
    _, pending = cli(lab, half, 'pending')
    tx = pending['pending'][0]
    _, partial = cli(lab, half, 'status')
    detail = partial['pending_detail'][0]
    kinds = sorted(detail['files'].values())
    _, view = cli(lab, half, 'plan', dict(op='restore', tx=tx, allow_delete=True))
    rc_applied, restored = cli(lab, half, 'apply',
                               dict(request=dict(op='restore', tx=tx, allow_delete=True),
                                    ticket=view['ticket']))
    _, after_restore = cli(lab, half, 'status')

    bite = root / 'bite-case'
    bite.mkdir()
    (bite / 'demo.txt').write_text('синтетический вход\n', encoding='utf-8')
    install(lab, bite)
    rc_bite_stop = broken(bite, dict(op='connect'), 1)
    _, bite_pending = cli(lab, bite, 'pending')
    bite_tx = bite_pending['pending'][0]
    _, bite_status = cli(lab, bite, 'status')
    bite_detail = bite_status['pending_detail'][0]
    written = ['.agent-contract/project/state.json']
    target = bite / written[0]
    whole = target.read_bytes()
    target.write_bytes(whole[:max(1, len(whole) // 2)])
    cut = target.read_bytes()
    _, broken_status = cli(lab, bite, 'status')
    broken_detail = broken_status['pending_detail'][0]
    salvage = broken_detail['salvage'][written[0]]
    _, bite_view = cli(lab, bite, 'plan', dict(op='restore', tx=bite_tx, allow_delete=True))
    _, bite_partial = cli(lab, bite, 'apply',
                          dict(request=dict(op='restore', tx=bite_tx, allow_delete=True),
                               ticket=bite_view['ticket']))
    kept = target.read_bytes() == cut
    copy = bite / salvage['copy']
    target.write_bytes(copy.read_bytes())
    _, bite_final_view = cli(lab, bite, 'plan', dict(op='restore', tx=bite_tx, allow_delete=True))
    _, bite_done = cli(lab, bite, 'apply',
                       dict(request=dict(op='restore', tx=bite_tx, allow_delete=True),
                            ticket=bite_final_view['ticket']))
    l4p = (rc_stop == 75 and kinds == ['after', 'before'] and partial.get('health') == 'partial'
           and partial.get('writes') is False and detail.get('tx') == tx
           and restored.get('outcome') == 'restored' and after_restore.get('health') == 'valid'
           and rc_bite_stop == 75 and broken_detail['files'][written[0]] == 'foreign'
           and salvage['intact'] is True and bite_partial.get('outcome') == 'partial'
           and written[0] in bite_partial.get('unresolved', []) and kept
           and bite_done.get('outcome') == 'restored'
           and cli(lab, bite, 'status')[1].get('health') == 'valid')
    detail4p = dict(child_exit=rc_stop, half_classes=detail['files'], health=partial.get('health'),
                    writes=partial.get('writes'), restore=restored.get('outcome'),
                    bite_classes=broken_detail['files'], salvage_intact=salvage['intact'],
                    half_file_outcome=bite_partial.get('outcome'),
                    unresolved=bite_partial.get('unresolved'), file_kept=kept,
                    final=bite_done.get('outcome'))

    # L4M: метрики считают по машине состояний — действует только active под active (И-052).
    metrics_case = root / 'metrics-case'
    metrics_case.mkdir()
    (metrics_case / 'demo.txt').write_text('синтетический вход\n', encoding='utf-8')
    install(lab, metrics_case)
    approved(lab, metrics_case, dict(op='connect'))
    approved(lab, metrics_case, dict(op='create', kind='contract', title='контракт', scope='.',
                                     text='контракт проекта', basis='fixture', criterion='observable',
                                     state='active', reason='создание контракта'))
    approved(lab, metrics_case, dict(op='create', kind='rule', contract='P-1', title='правило', scope='src',
                                     text='действует', basis='fixture', criterion='observable',
                                     state='active', reason='создание правила'))
    approved(lab, metrics_case, dict(op='create', kind='rule', contract='P-1', title='черновик', scope='src',
                                     text='черновик', basis='fixture', criterion='observable',
                                     state='draft', reason='создание черновика'))
    _, before = cli(lab, metrics_case, 'metrics', {})
    approved(lab, metrics_case, dict(op='transition', id='P-1', to='suspended', reason='пауза'))
    _, during = cli(lab, metrics_case, 'metrics', {})
    _, empty = cli(lab, metrics_case, 'list', {})
    approved(lab, metrics_case, dict(op='transition', id='P-1', to='active', reason='вернуть'))
    _, after = cli(lab, metrics_case, 'metrics', {})
    _, active_now = cli(lab, metrics_case, 'list', {})
    l4m = (before.get('writes') is False and before['active']['count'] == 1
           and before['noise']['count'] == 1 and before['hidden']['count'] == 0
           and before['entries']['by_state'] == {'active': 2, 'draft': 1}
           and during['active']['count'] == 0 and during['hidden']['count'] == 1
           and during['hidden']['ids'] == ['P-2'] and empty.get('active') == []
           and after['active']['count'] == 1 and after['hidden']['count'] == 0
           and after['transitions']['by'] == {'active→suspended': 1, 'suspended→active': 1}
           and len(active_now.get('active', [])) == len([e for e in after and active_now['active']]))
    detail4m = dict(after_create=before['active']['count'], noise=before['noise']['count'],
                    states=before['entries']['by_state'], when_suspended=during['active']['count'],
                    hidden=during['hidden']['ids'], transitions=after['transitions']['by'],
                    writes=before.get('writes'), active_after=after['active']['count'])


    # L4T: контур машины состояний — все 32 пары (4 состояния × 4 цели × контракт/правило) и запреты входа (И-052).
    transitions = {'draft': ['active', 'revoked'], 'active': ['suspended', 'revoked'],
                   'suspended': ['active', 'revoked'], 'revoked': []}
    pairs, mismatches = 0, []

    def matrix_project(name, kind, state):
        project = root / f'matrix-{name}'
        project.mkdir()
        (project / 'demo.txt').write_text('синтетический вход\n', encoding='utf-8')
        install(lab, project)
        approved(lab, project, dict(op='connect'))
        approved(lab, project, dict(op='create', kind='contract', title='контракт', scope='.',
                                    text='контракт проекта', basis='fixture', criterion='observable',
                                    state='draft', reason='создание контракта'))
        if kind == 'contract':
            ident = 'P-1'
        else:
            approved(lab, project, dict(op='transition', id='P-1', to='active', reason='активация контракта'))
            approved(lab, project, dict(op='create', kind='rule', contract='P-1', title='правило', scope='src',
                                        text='действует', basis='fixture', criterion='observable',
                                        state='draft', reason='создание правила'))
            ident = 'P-2'
        way = {'draft': [], 'active': ['active'], 'suspended': ['active', 'suspended'],
               'revoked': ['active', 'revoked']}[state]
        for step in way:
            approved(lab, project, dict(op='transition', id=ident, to=step, reason='подготовка'))
        return project, ident

    for kind in ('contract', 'rule'):
        for state in ('draft', 'active', 'suspended', 'revoked'):
            for to in ('draft', 'active', 'suspended', 'revoked'):
                pairs += 1
                project, ident = matrix_project(f'{kind}-{state}-{to}', kind, state)
                allowed = to in transitions[state]
                rc, plan = cli(lab, project, 'plan', dict(op='transition', id=ident, to=to, reason='проверка'))
                applied = rc == 0 and bool(plan.get('changes'))
                if rc == 0 and plan.get('changes'):
                    rc2, out = cli(lab, project, 'apply', dict(request=dict(op='transition', id=ident, to=to,
                                                                           reason='проверка'),
                                                               ticket=plan['ticket']))
                    applied = rc2 == 0 and out.get('outcome') in ('applied', 'committed')
                    if applied and [e for e in json.loads((project / '.agent-contract/project/state.json')
                                                         .read_text(encoding='utf-8'))['entries']
                                    if e['id'] == ident][0]['state'] != to:
                        mismatches.append(f'{kind}:{state}->{to}: состояние не сменилось')
                elif rc != 0:
                    code = plan.get('error') if isinstance(plan.get('error'), str) else None
                    if code != 'transition':
                        mismatches.append(f'{kind}:{state}->{to}: отказ {code}, ожидался transition')
                if applied != allowed:
                    mismatches.append(f'{kind}:{state}->{to}: ожидалось {allowed}, получено {applied}')
                shutil.rmtree(project, ignore_errors=True)

    guard = root / 'guard-case'
    guard.mkdir()
    (guard / 'demo.txt').write_text('синтетический вход\n', encoding='utf-8')
    install(lab, guard)
    approved(lab, guard, dict(op='connect'))
    approved(lab, guard, dict(op='create', kind='contract', title='контракт', scope='.', text='контракт',
                              basis='fixture', criterion='observable', state='draft', reason='создание'))
    approved(lab, guard, dict(op='transition', id='P-1', to='active', reason='активация контракта'))
    approved(lab, guard, dict(op='create', kind='rule', contract='P-1', title='черновик', scope='.',
                              text='черновик', basis='fixture', criterion='observable', state='draft',
                              reason='создание'))
    approved(lab, guard, dict(op='create', kind='rule', contract='P-1', title='действует', scope='.',
                              text='действует', basis='fixture', criterion='observable', state='active',
                              reason='создание'))
    _, due_before = cli(lab, guard, 'due', {})
    approved(lab, guard, dict(op='transition', id='P-1', to='suspended', reason='пауза'))
    rc_active, refuse_active = cli(lab, guard, 'plan', dict(op='create', kind='rule', contract='P-1',
                                                           title='новое', scope='.', text='новое',
                                                           basis='fixture', criterion='observable',
                                                           state='active', reason='ввод'))
    rc_draft, plan_draft = cli(lab, guard, 'plan', dict(op='create', kind='rule', contract='P-1',
                                                        title='позже', scope='.', text='позже',
                                                        basis='fixture', criterion='observable',
                                                        state='draft', reason='ввод'))
    approved(lab, guard, dict(op='create', kind='rule', contract='P-1', title='позже', scope='.',
                              text='позже', basis='fixture', criterion='observable', state='draft',
                              reason='ввод'))
    rc_step, refuse_step = cli(lab, guard, 'plan', dict(op='transition', id='P-2', to='active',
                                                        reason='активация'))
    approved(lab, guard, dict(op='transition', id='P-1', to='active', reason='вернуть'))
    approved(lab, guard, dict(op='transition', id='P-2', to='active', reason='активация правила'))
    approved(lab, guard, dict(op='transition', id='P-4', to='active', reason='активация отложенного'))
    approved(lab, guard, dict(op='transition', id='P-3', to='revoked', reason='отмена правила'))
    approved(lab, guard, dict(op='transition', id='P-1', to='revoked', reason='отмена контракта'))
    rc_dead, refuse_dead = cli(lab, guard, 'plan', dict(op='create', kind='rule', contract='P-1',
                                                        title='после', scope='.', text='после',
                                                        basis='fixture', criterion='observable',
                                                        state='draft', reason='ввод'))
    _, guard_metrics = cli(lab, guard, 'metrics', {})

    def refusal(rc, out):
        return (out.get('error') if rc != 0 and isinstance(out.get('error'), str) else None)

    l4t = (not mismatches and pairs == 32
           and refusal(rc_active, refuse_active) == 'state'
           and refuse_active.get('details') == {'contract': 'P-1', 'parent_state': 'suspended'}
           and rc_draft == 0 and bool(plan_draft.get('changes'))
           and not (refuse_step.get('changes') or []) and refusal(rc_step, refuse_step) == 'state'
           and refusal(rc_dead, refuse_dead) == 'parent'
           and refuse_dead.get('details') == {'contract': 'P-1', 'state': 'revoked'}
           and sorted({row['state'] for row in due_before['due']}) == ['active', 'draft']
           and guard_metrics['hidden']['by_reason'] == {'parent_draft': 0, 'parent_revoked': 2,
                                                        'parent_suspended': 0, 'retired': 0}
           and guard_metrics['hidden']['ids'] == ['P-2', 'P-4']
           and guard_metrics.get('writes') is False)
    detail4t = dict(pairs=pairs, mismatches=mismatches[:8],
                    create_active=refusal(rc_active, refuse_active),
                    create_active_details=refuse_active.get('details'),
                    create_draft='ok' if rc_draft == 0 else refusal(rc_draft, plan_draft),
                    step_activation=refusal(rc_step, refuse_step),
                    create_dead=refusal(rc_dead, refuse_dead),
                    create_dead_details=refuse_dead.get('details'),
                    due_states=sorted({row['state'] for row in due_before['due']}),
                    hidden_reasons=guard_metrics['hidden']['by_reason'], hidden=guard_metrics['hidden']['ids'])


    # L4K: два сценария рядом — сравнение действующего набора, а не реестра (И-052).
    cmp_here = root / 'compare-here'
    cmp_there = root / 'compare-there'
    cmp_broken = root / 'compare-broken'
    for folder in (cmp_here, cmp_there, cmp_broken):
        folder.mkdir()
        (folder / 'demo.txt').write_text('синтетический вход\n', encoding='utf-8')
        install(lab, folder)
        approved(lab, folder, dict(op='connect'))
        approved(lab, folder, dict(op='create', kind='contract', title='контракт', scope='.',
                                   text='контракт проекта', basis='fixture', criterion='observable',
                                   state='active', reason='создание контракта'))
    approved(lab, cmp_here, dict(op='create', kind='rule', contract='P-1', title='срок', scope='.',
                                 text='срок 90', basis='fixture', criterion='observable', key='k.review',
                                 value='90', state='active', reason='создание'))
    approved(lab, cmp_here, dict(op='create', kind='rule', contract='P-1', title='общее', scope='.',
                                 text='общее правило', basis='fixture', criterion='observable',
                                 state='active', reason='создание'))
    approved(lab, cmp_here, dict(op='create', kind='rule', contract='P-1', title='только здесь', scope='.',
                                 text='только здесь', basis='fixture', criterion='observable', key='k.here',
                                 value='1', state='active', reason='создание'))
    approved(lab, cmp_here, dict(op='create', kind='rule', contract='P-1', title='черновик', scope='.',
                                 text='черновик', basis='fixture', criterion='observable', state='draft',
                                 reason='создание'))
    approved(lab, cmp_there, dict(op='create', kind='rule', contract='P-1', title='срок', scope='.',
                                  text='срок 30', basis='fixture', criterion='observable', key='k.review',
                                  value='30', state='active', reason='создание'))
    approved(lab, cmp_there, dict(op='create', kind='rule', contract='P-1', title='общее', scope='.',
                                  text='общее правило', basis='fixture', criterion='observable',
                                  state='active', reason='создание'))
    approved(lab, cmp_there, dict(op='create', kind='rule', contract='P-1', title='только там', scope='.',
                                  text='только там', basis='fixture', criterion='observable', key='k.there',
                                  value='2', state='active', reason='создание'))
    approved(lab, cmp_there, dict(op='create', kind='rule', contract='P-1', title='черновик', scope='.',
                                  text='черновик', basis='fixture', criterion='observable', state='draft',
                                  reason='создание'))
    state_file = cmp_here / '.agent-contract/project/state.json'
    before_cmp = sha(state_file)
    rc_cmp, view = cli(lab, cmp_here, 'metrics', dict(against=str(cmp_there)))
    after_cmp = sha(state_file)
    cmp = view.get('compare') or {}
    rc_self, self_view = cli(lab, cmp_here, 'metrics', dict(against=str(cmp_here)))
    base_drift = cmp_broken / '.agent-contract/base/START.md'
    base_drift.write_text(base_drift.read_text(encoding='utf-8') + '\nправка\n', encoding='utf-8')
    rc_broken, broken_view = cli(lab, cmp_here, 'metrics', dict(against=str(cmp_broken)))
    rc_missing, missing_view = cli(lab, cmp_here, 'metrics', dict(against=str(root / 'нет-такого')))
    detail4k = dict(pairs=len(cmp.get('active', {})), only_here=[r['title'] for r in cmp.get('active', {}).get('only_here', [])],
                    only_there=[r['title'] for r in cmp.get('active', {}).get('only_there', [])],
                    changed=cmp.get('active', {}).get('changed'),
                    same=cmp.get('active', {}).get('same', []),
                    cost=cmp.get('cost'), noise=cmp.get('noise'),
                    writes=view.get('writes'), unchanged=before_cmp == after_cmp,
                    self_delta=(self_view.get('compare') or {}).get('cost', {}).get('delta'),
                    broken=refusal(rc_broken, broken_view), missing=refusal(rc_missing, missing_view))
    l4k = (rc_cmp == 0 and view.get('writes') is False and before_cmp == after_cmp
           and [r['title'] for r in cmp['active']['only_here']] == ['только здесь']
           and [r['title'] for r in cmp['active']['only_there']] == ['только там']
           and cmp['active']['same'] == ['P-3']
           and cmp['active']['changed'] == [{'key': 'k.review', 'scope': '.', 'here': ['P-2'],
                                             'there': ['P-2'], 'values_here': ['90'],
                                             'values_there': ['30']}]
           and cmp['cost']['delta'] == cmp['cost']['bytes_here'] - cmp['cost']['bytes_there']
           and cmp['noise'] == {'here': 1, 'there': 1}
           and cmp['here']['ids'] == ['P-2', 'P-3', 'P-4']
           and self_view['compare']['cost']['delta'] == 0
           and self_view['compare']['active']['changed'] == []
           and refusal(rc_broken, broken_view) == 'compare'
           and broken_view.get('details', {}).get('reason') == 'drift'
           and refusal(rc_missing, missing_view) == 'compare'
           and missing_view.get('details', {}).get('reason') == 'root')


    # L4R: права названы данными, посторонняя запись останавливает изменения, но не чтение (И-052).
    rights_case = root / 'rights-case'
    rights_case.mkdir()
    (rights_case / 'demo.txt').write_text('синтетический вход\n', encoding='utf-8')
    install(lab, rights_case)
    approved(lab, rights_case, dict(op='connect'))
    approved(lab, rights_case, dict(op='create', kind='contract', title='контракт', scope='.',
                                    text='контракт проекта', basis='fixture', criterion='observable',
                                    state='active', reason='создание контракта'))
    approved(lab, rights_case, dict(op='create', kind='rule', contract='P-1', title='правило', scope='.',
                                    text='действует', basis='fixture', criterion='observable',
                                    state='active', reason='создание правила'))
    state_file = rights_case / '.agent-contract/project/state.json'
    before_rights = sha(state_file)
    rc_rights, rights_view = cli(lab, rights_case, 'rights', {})
    after_rights = sha(state_file)
    rc_series, series = cli(lab, rights_case, 'repeat', dict(runs=2, requests=[
        dict(command='metrics'), dict(command='due'), dict(command='rights')]))
    extra = rights_case / '.agent-contract/project/extra.json'
    extra.write_text('{"чужое": true}\n', encoding='utf-8')
    _, status_foreign = cli(lab, rights_case, 'status', {})
    rc_list, list_foreign = cli(lab, rights_case, 'list', {})
    rc_blocked, blocked = cli(lab, rights_case, 'plan', dict(op='create', kind='rule', contract='P-1',
                                                            title='новое', scope='.', text='новое',
                                                            basis='fixture', criterion='observable',
                                                            state='active', reason='ввод'))
    rc_restore, restore_view = cli(lab, rights_case, 'plan', dict(op='restore', tx='none', allow_delete=True))
    extra.unlink()
    rc_allowed, allowed = cli(lab, rights_case, 'plan', dict(op='create', kind='rule', contract='P-1',
                                                             title='новое', scope='.', text='новое',
                                                             basis='fixture', criterion='observable',
                                                             state='active', reason='ввод'))
    _, rights_after = cli(lab, rights_case, 'rights', {})
    detail4r = dict(writes=rights_view.get('writes'), write_paths=rights_view.get('write_paths'),
                    reads=rights_view.get('reads'), foreign=rights_view.get('foreign'),
                    unchanged=before_rights == after_rights,
                    series_identical=series.get('identical'),
                    series_commands=[r['command'] for r in series.get('requests', [])],
                    status_foreign=status_foreign.get('foreign'),
                    reading_works=rc_list == 0 and len(list_foreign.get('active', [])) == 1,
                    blocked=refusal(rc_blocked, blocked),
                    blocked_details=blocked.get('details'),
                    restore_plan_rc=rc_restore,
                    allowed_after_cleanup=rc_allowed == 0 and bool(allowed.get('changes')),
                    foreign_after=rights_after.get('foreign'))
    l4r = (rc_rights == 0 and rights_view.get('writes') is False and before_rights == after_rights
           and rights_view['foreign'] == [] and rights_view['blocks_writes'] is False
           and '.agent-contract/project/state.json' in rights_view['reads']
           and 'AGENTS.md' in rights_view['reads']
           and len(rights_view['write_paths']) == 9
           and 'AGENTS.md' in rights_view['write_paths']
           and rc_series == 0 and series.get('identical') is True and series.get('project_unchanged') is True
           and [r['command'] for r in series['requests']] == ['metrics', 'due', 'rights']
           and status_foreign.get('foreign') == ['.agent-contract/project/extra.json']
           and rc_list == 0 and len(list_foreign.get('active', [])) == 1
           and refusal(rc_blocked, blocked) == 'foreign'
           and blocked.get('details', {}).get('foreign') == ['.agent-contract/project/extra.json']
           and rc_restore in (0, 2)
           and rc_allowed == 0 and bool(allowed.get('changes'))
           and rights_after.get('foreign') == [])


    # L4F: чужая файловая система — измеренный регистр, длина имени, права файлов (И-052).
    fs_case = root / 'fs-case'
    fs_case.mkdir()
    (fs_case / 'demo.txt').write_text('синтетический вход\n', encoding='utf-8')
    install(lab, fs_case)
    approved(lab, fs_case, dict(op='connect'))
    approved(lab, fs_case, dict(op='create', kind='contract', title='контракт', scope='.',
                                text='контракт проекта', basis='fixture', criterion='observable',
                                state='active', reason='создание контракта'))
    before_sys = sha(fs_case / '.agent-contract/project/state.json')
    rc_sys, system_view = cli(lab, fs_case, 'system', {})
    after_sys = sha(fs_case / '.agent-contract/project/state.json')
    _, rights_files = cli(lab, fs_case, 'rights', {})
    decoy_case = root / 'fs-case-decoy'
    decoy_case.mkdir()
    (decoy_case / 'demo.txt').write_text('синтетический вход\n', encoding='utf-8')
    install(lab, decoy_case)
    (decoy_case / 'agents.md').write_text('чужое имя в другом регистре\n', encoding='utf-8')
    rc_case, case_refusal = cli(lab, decoy_case, 'plan', dict(op='connect'))
    (decoy_case / 'agents.md').unlink()
    rc_connect, _ = cli(lab, decoy_case, 'plan', dict(op='connect'))
    long_name = 'x' * 300 + '.json'
    rc_long, long_refusal = cli(lab, fs_case, 'plan',
                                dict(op='merge', incoming='.agent-contract/project/' + long_name))
    detail4f = dict(case_insensitive=system_view.get('case_insensitive'),
                    proven=system_view.get('proven'), declared=system_view.get('declared'),
                    probe=system_view.get('probe'), writes=system_view.get('writes'),
                    unchanged=before_sys == after_sys,
                    files=[(r['path'], r['mode'], r['world_writable']) for r in rights_files.get('files', [])],
                    case_refusal=refusal(rc_case, case_refusal),
                    case_details=case_refusal.get('details'),
                    connect_after_cleanup=rc_connect,
                    long_refusal=refusal(rc_long, long_refusal),
                    long_details={k: long_refusal.get('details', {}).get(k) for k in ('limit', 'bytes')})
    expected_case = True if os.name == 'nt' else False
    l4f = (rc_sys == 0 and system_view.get('writes') is False and before_sys == after_sys
           and system_view.get('case_insensitive') is expected_case
           and system_view.get('proven', {}).get('case_insensitive') is True
           and system_view.get('proven', {}).get('max_path') is False
           and system_view.get('declared', {}).get('name_bytes') == 255
           and system_view.get('probe', {}).get('name') == 'AGENTS.md'
           and rights_files.get('files') and all(r['path'] in rights_view_paths(rights_files) for r in rights_files['files'])
           and (os.name == 'nt' or all(r['world_writable'] is False for r in rights_files['files']))
           and refusal(rc_case, case_refusal) == 'case'
           and case_refusal.get('details', {}).get('conflicts') == [{'path': 'AGENTS.md', 'existing': 'agents.md'}]
           and rc_connect == 0
           and refusal(rc_long, long_refusal) == 'path'
           and long_refusal.get('details', {}).get('limit') == 255
           and long_refusal.get('details', {}).get('bytes') == 305)

    # L4L: живые модели — записанный ответ проверяется как данные (И-052, §14 ур. 4).
    model_case = root / 'model-case'
    model_case.mkdir()
    (model_case / 'demo.txt').write_text('синтетический вход\n', encoding='utf-8')
    install(lab, model_case)
    approved(lab, model_case, dict(op='connect'))
    approved(lab, model_case, dict(op='create', kind='contract', title='контракт', scope='.',
                                    text='контракт проекта', basis='fixture', criterion='observable',
                                    state='active', reason='создание контракта'))
    approved(lab, model_case, dict(op='create', kind='rule', contract='P-1', title='правило', scope='.',
                                    text='действует в проекте', basis='fixture', criterion='observable',
                                    state='active', reason='создание правила'))
    model_rule = cli(lab, model_case, 'list')[1].get('active', [])[0]
    rc_card_empty, card_empty = cli(lab, model_case, 'model')
    folder_model = model_case / '.agent-contract/local/model'
    folder_model.mkdir(parents=True)
    (folder_model / 'good.json').write_text(json.dumps(
        dict(model='kilo', at='2026-11-18T10:00:00Z', task='explain',
             claims=[dict(id=model_rule['id'], state='active', text=model_rule['text'])]),
        ensure_ascii=False), encoding='utf-8')
    (folder_model / 'bad.json').write_text(json.dumps(
        dict(model='copilot', at='2026-11-18T10:05:00Z', task='refuse',
             claims=[dict(id=model_rule['id'], state='suspended')]), ensure_ascii=False), encoding='utf-8')
    before_model = (sha(model_case / '.agent-contract/project/state.json'),
                    sha(model_case / '.agent-contract/project/checks.json'))
    rc_card, card = cli(lab, model_case, 'model')
    after_model = (sha(model_case / '.agent-contract/project/state.json'),
                   sha(model_case / '.agent-contract/project/checks.json'))
    rc_ok, ok_view = cli(lab, model_case, 'verify',
                         dict(model='kilo', at='2026-11-18T10:10:00Z', task='explain',
                              claims=[dict(id=model_rule['id'], state='active', text=model_rule['text'])]))
    rc_bad, bad_view = cli(lab, model_case, 'verify',
                           dict(model='kilo', task='choose',
                                claims=[dict(id=model_rule['id'], state='draft'),
                                        dict(id='P-999', state='active')]))
    rc_shape, shape_refusal = cli(lab, model_case, 'verify', dict(model='kilo'))
    model_inputs = cli(lab, model_case, 'rights')[1].get('inputs', {})
    series_model = cli(lab, model_case, 'repeat',
                       dict(runs=2, requests=[dict(command='model'),
                                              dict(command='verify',
                                                   payload=dict(model='kilo', task='explain',
                                                                claims=[dict(id=model_rule['id'])]))]))[1]
    (folder_model / 'bad.json').unlink()
    card_clean = cli(lab, model_case, 'model')[1]
    detail4l = dict(live=card.get('live'), count=card.get('count'),
                    recorded=[(r.get('path'), r.get('verdict')) for r in card.get('recorded', [])],
                    levels=card.get('levels'), proven=card.get('proven'),
                    unchanged=before_model == after_model,
                    empty_levels=card_empty.get('levels'), empty_count=card_empty.get('count'),
                    verify_pass=ok_view.get('counts'), verify_pass_verdict=ok_view.get('verdict'),
                    verify_fail=[c.get('why') for c in bad_view.get('claims', [])],
                    verify_fail_verdict=bad_view.get('verdict'),
                    shape_refusal=refusal(rc_shape, shape_refusal),
                    inputs=sorted(model_inputs), repeat=series_model.get('identical'),
                    repeat_unchanged=series_model.get('project_unchanged'),
                    clean_level=card_clean.get('levels', {}).get('4_behavior_checked'))
    l4l = (rc_card_empty == 0 and card_empty.get('levels', {}).get('4_behavior_checked') == 'not run'
           and card_empty.get('live') is False and card_empty.get('writes') is False
           and rc_card == 0 and card.get('live') is False and card.get('writes') is False
           and card.get('count') == 2
           and [r.get('verdict') for r in card.get('recorded', [])] == ['fail', 'pass']
           and card.get('levels', {}).get('4_behavior_checked') == 'fail'
           and card.get('levels', {}).get('5_behavior_repeatable') == 'not run'
           and card.get('proven', {}).get('live_call') is False
           and card.get('proven', {}).get('answer_graded') is True
           and before_model == after_model
           and rc_ok == 0 and ok_view.get('verdict') == 'pass' and ok_view.get('live') is False
           and ok_view.get('counts') == {'pass': 1, 'fail': 0}
           and ok_view.get('writes') is False
           and rc_bad == 0 and bad_view.get('verdict') == 'fail'
           and [c.get('why') for c in bad_view.get('claims', [])] == ['state_mismatch', 'unknown_rule']
           and refusal(rc_shape, shape_refusal) == 'answer'
           and '.agent-contract/local/model/*.json' in model_inputs
           and series_model.get('identical') is True and series_model.get('project_unchanged') is True
           and card_clean.get('levels', {}).get('4_behavior_checked') == 'pass')
    # L6: развёртывание в корень — архив распакован внутрь проекта (И-052, §3 переносимость).
    deploy = root / 'deploy-root'
    deploy.mkdir()
    (deploy / 'demo.txt').write_text('синтетический вход\n', encoding='utf-8')
    shutil.copytree(lab, deploy / 'AgentContractLab')
    deploy_lab = deploy / 'AgentContractLab'
    before_deploy = sorted(p.name for p in deploy.iterdir())
    rc_lay, layout_deploy = cli(deploy_lab, deploy, 'layout')
    after_deploy = sorted(p.name for p in deploy.iterdir())
    pin_deploy = sha(deploy_lab / f'releases/{PACK_VERSION}/manifest.json')
    rc_ins, _ = cli(deploy_lab, deploy, 'plan', dict(op='install', package=f'releases/{PACK_VERSION}',
                                                    pin=pin_deploy))
    approved(lab=deploy_lab, project=deploy,
             request=dict(op='install', package=f'releases/{PACK_VERSION}', pin=pin_deploy))
    approved(lab=deploy_lab, project=deploy, request=dict(op='connect'))
    approved(lab=deploy_lab, project=deploy,
             request=dict(op='create', kind='contract', title='контракт', scope='.',
                          text='контракт проекта', basis='fixture', criterion='observable',
                          state='active', reason='создание контракта'))
    rc_dep_status, deploy_status = cli(deploy_lab, deploy, 'status')
    rc_upd, updates_deploy = cli(deploy_lab, deploy, 'updates')
    rc_plan_upd, plan_upd = cli(deploy_lab, deploy, 'plan',
                                dict(op='update', package=f'releases/{PACK_VERSION}', pin=pin_deploy))
    rc_upd_apply, upd_apply = cli(deploy_lab, deploy, 'apply',
                                  dict(request=dict(op='update', package=f'releases/{PACK_VERSION}',
                                                    pin=pin_deploy),
                                       ticket=plan_upd.get('ticket')))
    rc_ops, ops_deploy = cli(deploy_lab, deploy, 'operations')
    created = [o for o in ops_deploy.get('operations', []) if o.get('op') == 'create']
    last_tx = created[-1]['tx'] if created else None
    undo_req = dict(op='undo', tx=last_tx) if last_tx else None
    undo_rc, undo_view = (0, {})
    if undo_req is not None:
        rc_uplan, uplan = cli(deploy_lab, deploy, 'plan', undo_req)
        if rc_uplan == 0 and uplan.get('changes'):
            undo_rc, undo_view = cli(deploy_lab, deploy, 'apply',
                                     dict(request=undo_req, ticket=uplan.get('ticket')))
        else:
            undo_rc, undo_view = rc_uplan, uplan
    series_deploy = cli(deploy_lab, deploy, 'repeat', dict(runs=2, requests=[dict(command='layout'),
                                                                           dict(command='status')]))[1]
    added_deploy = sorted(set(p.name for p in deploy.iterdir()) - set(before_deploy))
    detail6 = dict(relation=layout_deploy.get('relation'), lab_relative=layout_deploy.get('lab_relative'),
                   warnings=layout_deploy.get('warnings'), writes=layout_deploy.get('writes'),
                   installed_before=layout_deploy.get('installed'), unchanged=before_deploy == after_deploy,
                   install_plan_rc=rc_ins, status=(deploy_status.get('health'), deploy_status.get('entry_mode')),
                   updates=updates_deploy.get('installed_version'), update_plan_changes=len(plan_upd.get('changes') or []),
                   update_outcome=upd_apply.get('outcome'), operations=len(ops_deploy.get('operations') or []),
                   undo=undo_view.get('outcome'), added=added_deploy,
                   repeat=series_deploy.get('identical'), repeat_unchanged=series_deploy.get('project_unchanged'))
    l6 = (rc_lay == 0 and layout_deploy.get('relation') == 'lab_inside_project'
          and layout_deploy.get('lab_relative') == 'AgentContractLab'
          and layout_deploy.get('writes') is False and before_deploy == after_deploy
          and layout_deploy.get('installed') is False and bool(layout_deploy.get('warnings'))
          and rc_ins == 0
          and rc_dep_status == 0 and deploy_status.get('health') == 'valid'
          and deploy_status.get('entry_mode') == 'owned'
          and rc_upd == 0 and updates_deploy.get('installed_version') == PACK_VERSION
          and rc_plan_upd == 0 and not (plan_upd.get('changes') or [])
          and rc_upd_apply == 0 and upd_apply.get('outcome') == 'no_change'
          and rc_ops == 0 and bool(ops_deploy.get('operations'))
          and undo_rc == 0
          and {'AGENTS.md', '.agent-contract'} <= set(added_deploy)
          and series_deploy.get('identical') is True
          and series_deploy.get('project_unchanged') is True)

    # L5: серия чтений и серия установок в чистых каталогах.
    series = cli(lab, repo, 'repeat', dict(runs=3, requests=[
        dict(command='status'), dict(command='identity'),
        dict(command='discovery', payload=dict(environment='kilo')),
        dict(command='entry', payload=dict(environment='kilo'))]))[1]
    l5a = (series.get('identical') is True and series.get('project_unchanged') is True
           and series.get('behavior_proven') is False and series.get('writes') is False
           and len(series.get('requests', [])) == 4
           and all(row['identical'] for row in series['requests']))

    fresh, fingerprints = [], []
    for index in range(3):
        project = root / f'series-{index}'
        project.mkdir()
        (project / 'demo.txt').write_text('синтетический вход\n', encoding='utf-8')
        install(lab, project)
        approved(lab, project, dict(op='connect'))
        record(lab, project, observation('Проверка проходит.', ENV_LOCAL))
        checks = json.loads((project / '.agent-contract/project/checks.json').read_text(encoding='utf-8'))
        for entry_ in checks['checks']:
            entry_['at'] = '<время>'
        status = cli(lab, project, 'status')[1]
        fresh.append(status.get('project_revision'))
        fingerprints.append((json.dumps(checks, sort_keys=True, ensure_ascii=False),
                             status.get('health'), status.get('entry')))
    l5b = len(set(fingerprints)) == 1 and len(set(fresh)) == 1

    item('L1', 'Уровень 1: файл есть и назван',
         'объявленные входы перечислены, наличие измерено',
         'pass' if l1 else 'fail',
         'наличие файлов — единственное, что измерено в этом пункте; содержимое не нужно',
         dict(layouts=detail1))
    item('L2', 'Уровень 2: обнаружение по документированному порядку',
         'две независимые реализации называют один и тот же вход на трёх раскладках',
         'pass' if l2 else 'fail',
         'имитатор среды дублирует порядок старшинства отдельным процессом; совпадение значит, что '
         'порядок в карточках исполним и однозначен',
         dict(cases=detail2))
    item('L3', 'Уровень 3: содержимое прочитано и опознано',
         'комплект и независимый читатель дают один отпечаток, размер и число строк; строка-указатель найдена',
         'pass' if l3 else 'fail',
         'прочитал комплект и имитатор читателя; что содержимое прочитала модель — отдельный уровень '
         'и он not run',
         detail3)
    item('L3F', 'Уровень 3: чужой вход не читается',
         'посторонний AGENTS.md не читается и остаётся байт в байт',
         'pass' if l3f else 'fail',
         'содержимое чужого файла не запрашивается: известен только размер с диска',
         detail3f)
    item('L3M', 'Уровень 3: модель прочитала содержимое',
         'модель получила текст входа и действовала по нему',
         'not run',
         'модели не вызываются: комплект не выдаёт своё чтение за чтение моделью',
         dict(content_proven=own['content_proven'], reason='нет живой среды в песочнице'))
    item('L4C', 'Уровень 4: изменение внесено и восстановимо по журналу',
         'правка меняет запись, решение хранит «до/после», обратная правка возвращает текст; смена области без согласия отклонена',
         'pass' if l4c else 'fail',
         'измерено комплектом: правка текста, возврат по журналу, отказ scope и согласие allow_scope; '
         'выполнение требования моделью — отдельный уровень и он not run',
         detail4c)
    item('L4', 'Уровень 4: модель выполнила требование',
         'модель соблюдает правило после изменения',
         'not run',
         'модели не вызываются: измерено, что изменение внесено и записано, а не что правило исполнено',
         dict(reason='нет живой среды в песочнице'))
    item('L4Q', 'Уровень 4: разовый запрос не сохраняется',
         'запрос исполняется один раз: проект не изменился, сохранение отклонено, правило оформляется отдельно',
         'pass' if l4q else 'fail',
         'измерено комплектом: отпечатки .agent-contract до и после совпали, kind rule — not_a_request, '
         'save — not_saved с направлением к create, серия через repeat ничего не изменила',
         detail4q)
    item('L4D', 'Уровень 4: отмена сохраняет запись, удаление оставляет след',
         'отменённая запись остаётся целиком, удалённая исчезает из реестра, но след остаётся без содержимого',
         'pass' if l4d else 'fail',
         'измерено комплектом: revoked сохранил текст, purge убрал запись из entries, removed показал '
         'след без text/value, status назвал число следов',
         detail4d)
    item('L4S', 'Уровень 4: секрет не записывается и не печатается',
         'запись токена отклонена без пересказа значения, старый реестр читается с меткой [скрыто]',
         'pass' if l4s else 'fail',
         'измерено комплектом: отказ secret с полем и видом образца, токена нет ни в деталях, ни в state; '
         'подложенный в state токен заменён меткой, ответ нёс redacted',
         detail4s)
    item('L4O', 'Уровень 4: правило меняет только владелец',
         'правка без владельца отклонена, владелец правит, передача требует согласия, прежний владелец теряет право',
         'pass' if l4o else 'fail',
         'измерено комплектом: not_owner без actor и с чужим actor, owner при передаче без allow_owner, '
         'после передачи прежний владелец получает not_owner',
         detail4o)
    item('L4V', 'Уровень 4: версия — содержимое, срок проверки — данные',
         'повтор правки не двигает версию, смена состояния её не двигает, review переносит срок и убирает правило из due',
         'pass' if l4v else 'fail',
         'измерено комплектом: same в плане, revision 1 → 2 → 2, due 1 → 0, review_by позже reviewed_at',
         detail4v)
    item('L4X', 'Уровень 4: неизвестная схема — отказ и возврат без потери',
         'отказ unknown_schema с found/supported/migrate, migrate не угадывает, данные целы, файл before возвращает проект',
         'pass' if l4x else 'fail',
         'измерено комплектом: status и migrate отклонены кодом unknown_schema, state байт в байт, файл before из журнала вернул проект',
         detail4x)
    item('L4P', 'Уровень 4: частичный сбой виден до восстановления',
         'обрыв процесса даёт pending, статус называет классы файлов, восстановление возвращает restored, половина файла не перезаписывается',
         'pass' if l4p else 'fail',
         'измерено комплектом: дочерний процесс завершился кодом 75, status отдал pending_detail с before/after, restore вернул restored; усечённый файл остался foreign, копия before цела и вернула проект',
         detail4p)
    item('L4M', 'Уровень 4: метрики считают по машине состояний',
         'draft не действует, suspended-контракт скрывает активное правило, метрики совпадают с набором list',
         'pass' if l4m else 'fail',
         'измерено комплектом: active 1 → 0 → 1, hidden [P-2] при suspended, transitions по истории, writes false',
         detail4m)
    item('L4T', 'Уровень 4: контур машины состояний — все пары и запреты входа',
         'все 32 пары переходов совпадают с объявленной машиной; активная запись под неактивным контрактом и запись под отменённым отклонены; due называет состояние; hidden делит причину',
         'pass' if l4t else 'fail',
         'измерено комплектом: 32 пары (4 состояния × 4 цели × контракт/правило) применены и сверены с состоянием в state.json; '
         'create active под suspended — state, переход в active под suspended — state, create под revoked — parent; '
         'hidden.by_reason называет parent_revoked, due.state присутствует',
         detail4t)
    item('L4K', 'Уровень 4: два сценария рядом',
         'сравнивается действующий набор обеих сторон: same, changed, only_here, only_there, стоимость и разница байтов; нечитаемый второй сценарий отклонён',
         'pass' if l4k else 'fail',
         'измерено комплектом: key+scope дают changed (90 против 30), свободное правило — same, «только здесь» и '
         '«только там» названы поимённо, delta = bytes_here − bytes_there, черновики остались шумом; '
         'второй сценарий с дрейфом и несуществующий путь отклонены кодом compare с причиной; чтение не пишет',
         detail4k)
    item('L4R', 'Уровень 4: права названы данными',
         'reads и write_paths объявлены; посторонняя запись в служебном каталоге останавливает изменения, но не чтение; repeat принимает metrics, due и rights',
         'pass' if l4r else 'fail',
         'измерено комплектом: rights называет 8 путей записи и читает вход; посторонний файл виден в status и rights, '
         'list продолжает работать, plan отказывает кодом foreign с перечнем; после удаления файла работа продолжается; '
         'repeat на трёх чтениях совпал и ничего не изменил',
         detail4r)
    item('L4F', 'Уровень 4: чужая файловая система',
         'регистр измерен, лимиты объявлены; имя в другом регистре останавливает запись кодом case; длинный компонент — кодом path; права файлов измерены',
         'pass' if l4f else 'fail',
         'измерено комплектом: system называет case_insensitive и proven, rights.files — режим и доступ другим; '
         'AGENTS.md против agents.md даёт отказ case с парой путей, после удаления connect проходит; '
         'имя из 305 байт отклонено кодом path с limit 255',
         detail4f)
    item('L4L', 'Уровень 4: живые модели',
         'ответ модели проверяется как данные: правило, состояние, текст; комплект модель не вызывает (live false)',
         'pass' if l4l else 'fail',
         'измерено комплектом: model оценил две записи (good pass, bad fail) и назвал уровни 4_behavior_checked и '
         '5_behavior_repeatable; verify дал pass на верное утверждение и state_mismatch/unknown_rule на неверные, '
         'пустой ответ отклонён кодом answer; чтения не изменили проект; repeat на model и verify совпал. '
         'Чего нет: вызова модели и проверки рассуждения — это not run',
         detail4l)
    item('L6', 'Уровень 6: развёртывание в корень',
         'архив распакован внутрь проекта: лаборатория названа, установка и обновление работают, проектные файлы не тронуты',
         'pass' if l6 else 'fail',
         'измерено комплектом: layout называет lab_inside_project и путь лаборатории внутри проекта, сам ничего не пишет; '
         'install/connect/create дают status valid с entry_mode owned; update той же версии отвечает no_change; '
         'в корне появились только .agent-contract и AGENTS.md; undo последней операции проходит; repeat на layout и status совпал. '
         'Чего нет: восстановление после частичного сбоя в этой раскладке отдельно не имитировалось — оно измерено в L4P',
         detail6)
    item('L5a', 'Уровень 5: серия чтений даёт тот же ответ',
         'четыре команды по три прогона совпадают, проект не изменился',
         'pass' if l5a else 'fail',
         'повторяется ответ комплекта, а не поведение расширения: behaviour_proven false',
         dict(series=series.get('requests'), identical=series.get('identical'),
              project_unchanged=series.get('project_unchanged')))
    item('L5b', 'Уровень 5: серия установок в чистых каталогах',
         'три независимых проекта после install/connect/record совпадают без времени',
         'pass' if l5b else 'fail',
         'сравнивались checks.json без поля at и отчёт status: ревизия, здоровье, режим входа',
         dict(revisions=fresh, unique=len(set(fingerprints))))
    item('L5M', 'Уровень 5: модель повторяет поведение',
         'модель в двух прогонах действует одинаково',
         'not run',
         'модели не вызываются: измерен повтор ответа комплекта, не поведение',
         dict(behavior_proven=False, reason='нет живой среды в песочнице'))
    item('LIVE', 'Живая среда: VS Code с Kilo и Copilot',
         'расширение действительно находит и читает вход',
         'not run',
         'здесь расширения не запускаются, модели не вызываются: уровень 2 в смысле «среда нашла '
         'сама» остаётся not run, а команда discovery честно отвечает discovery_proven: false',
         dict(declared='discovery_proven: false', reason='нет живой среды в песочнице'))

    counts = {}
    for entry in ITEMS:
        counts[entry['status']] = counts.get(entry['status'], 0) + 1
    out = dict(iteration='И-052', line=args.line, at='2026-11-18', pack_version=PACK_VERSION,
               counts=dict(sorted(counts.items())), items=ITEMS,
               scope='условная обкатка доступными средствами: процессы, копии поставки, git',
               limits='живые расширения VS Code, модели, права и настоящий Windows не проверялись; '
                      'environment объявляется вызывающим, а не измеряется')
    (HERE / f'PILOT-{args.line}.json').write_text(
        json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    for entry in ITEMS:
        print(f"  {entry['status']:5} {entry['id']}  {entry['title']}")
    print(json.dumps(out['counts'], ensure_ascii=False))
    shutil.rmtree(root, ignore_errors=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
