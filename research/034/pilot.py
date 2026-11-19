#!/usr/bin/env python3
"""И-034: стенд обкатки — первый запуск порядком шагов и документы в поставке.

Сценарий владельца тот же, что в И-032–И-033: архив внутри репозитория, абсолютный путь проекта,
чужой `AGENTS.md`, запись наблюдений, слияние состояния двух машин через git. Новое здесь — два
последних пункта матрицы: P5 (порядок первого обращения исполняется буквально: каждая команда шага
действительно запускается) и P6 (в поставке есть инструкция обкатки: `docs/` в Edition, раздел в
`START.md` обеих линий).

Запуск: python3 pilot.py --tree ../release-0.1.14/base/AgentContractLab --line base
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).absolute().parent
PACK_VERSION = '0.1.14'
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
    archive_files = [p.name for p in source.rglob('*') if p.is_file()]
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

    counts = {}
    for entry in ITEMS:
        counts[entry['status']] = counts.get(entry['status'], 0) + 1
    out = dict(iteration='И-034', line=args.line, at='2026-11-18', pack_version=PACK_VERSION,
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
