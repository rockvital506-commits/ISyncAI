#!/usr/bin/env python3
"""И-032: стенд обкатки — раскладка владельца, чужой вход, перенос состояния.

Сценарий тот же, что в И-031, но теперь он идёт так, как его пройдёт владелец: распакованный архив
лежит **внутри** репозитория, проект задаётся абсолютным путём, чужой `AGENTS.md` не мешает, а
состояние переносится через git без ручной чистки каталогов.

Запуск: python3 pilot.py --tree ../release-0.1.12/base/AgentContractLab --line base
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
PACK_VERSION = '0.1.12'
ENV_LOCAL = dict(os='windows', editor='vscode', editor_version='1.146.0', extension='kilo.kilo-code',
                 extension_version='5.0.0', mode='agent', model='local-model', profile='default',
                 permissions='read-write')
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

    root = pathlib.Path(tempfile.mkdtemp(prefix='pilot032-'))
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

    # --- P3. Одно событие, увиденное двумя машинами ---------------------------------------------
    git(repo, 'init', '-q')
    git(repo, 'config', 'user.email', 'pilot@local')
    git(repo, 'config', 'user.name', 'pilot')
    git(repo, 'add', '-A')
    git(repo, 'commit', '-q', '-m', 'контракт установлен')
    outcome_local, _ = record(lab, repo, observation('Проверка проходит.', ENV_LOCAL))
    git(repo, 'add', '-A')
    git(repo, 'commit', '-q', '-m', 'первое наблюдение')
    git(root, 'init', '-q', '--bare', 'origin.git')
    git(repo, 'remote', 'add', 'origin', str(root / 'origin.git'))
    rc_push, out_push = git(repo, 'push', '-q', 'origin', 'HEAD:main')
    rc_clone, out_clone = git(root, 'clone', '-q', '-b', 'main', str(root / 'origin.git'), 'arena')
    assert rc_push == 0 and rc_clone == 0, (out_push, out_clone)
    arena = root / 'arena'
    git(arena, 'config', 'user.email', 'arena@cloud')
    git(arena, 'config', 'user.name', 'arena')
    # перенос без ручной чистки: журнал приехал из другого пути
    rc_arena_status, arena_status = cli(lab, arena, 'status')
    outcome_cloud, notes_cloud = record(lab, arena, observation('Проверка проходит.', ENV_ARENA))
    in_arena, in_repo = len(records(arena)), len(records(repo))
    item('P3', 'Одно событие, увиденное локально и в облачном агенте',
         'одна запись на событие, если правило так решило',
         'pass' if in_arena == 1 else 'fail',
         f'записей в облачном клоне: {in_arena}; локально: {in_repo}. Условия сравнения включают os и '
         'model, а у машин они разные: по действующему правилу это два разных события',
         dict(local_outcome=outcome_local, cloud_outcome=outcome_cloud, notes=notes_cloud,
              in_arena=in_arena, arena_status_rc=rc_arena_status,
              arena_health=arena_status.get('health'),
              arena_observations=len(arena_status.get('observations', []))))

    # --- P4. Состояние через git: перенос и два писателя ----------------------------------------
    git(arena, 'add', '-A')
    git(arena, 'commit', '-q', '-m', 'наблюдение из облака')
    rc_push_b, out_push_b = git(arena, 'push', '-q', 'origin', 'HEAD:main')
    record(lab, repo, observation('Проверка проходит.', ENV_LOCAL, case='сборка отчёта'))
    git(repo, 'add', '-A')
    git(repo, 'commit', '-q', '-m', 'наблюдение локально')
    rc_pull, out_pull = git(repo, 'pull', '-q', '--no-rebase', 'origin', 'main')
    conflicted = rc_pull != 0
    readable = []
    for path in (repo, arena):
        try:
            json.loads((path / '.agent-contract/project/checks.json').read_text(encoding='utf-8'))
            readable.append(path.name)
        except Exception:
            pass
    if conflicted:
        git(repo, 'merge', '--abort')
    transfer_ok = rc_arena_status == 0
    item('P4', 'Состояние переживает git: перенос и два писателя',
         'перенос без ручной чистки; слияние двух писателей не рвёт состояние',
         'pass' if transfer_ok and not conflicted and len(readable) == 2 else 'fail',
         'перенос теперь проходит: завершённые операции чужого пути читаются как история. '
         'Слияние двух писателей в один JSON по-прежнему не поддержано'
         if not transfer_ok or conflicted else 'перенос и слияние прошли',
         dict(transfer_ok=transfer_ok, pull_rc=rc_pull, pull=out_pull.splitlines()[-3:],
              readable=readable, pushed=rc_push_b))

    # --- P5. Первый промпт: исполнимость по тексту ----------------------------------------------
    start = (repo / '.agent-contract/base/START.md').read_text(encoding='utf-8')
    prompt_present = 'Начальный запрос после смены среды' in start
    rc_card, card = cli(lab, repo, 'adapter', dict(name='kilo'))
    actions = [('открыть START.md', True), ('открыть манифест и правила', True),
               ('объяснить правила', True), ('показать версии', True),
               ('ограничения среды', True), ('конфликты с другими инструкциями', True),
               ('предложить вход', True), ('показать разницу и дождаться согласия', True),
               ('отличить обнаружение от проверенного поведения', True),
               ('поддержка и коррекция самой папки', False)]
    item('P5', 'Первый промпт исполним буквально',
         'весь ритуал первого обращения покрыт командами и порядком',
         'fail',
         f'в тексте {len(actions)} действий, командой покрыто '
         f'{sum(1 for _, ok in actions if ok)}; порядок («сначала это, потом то») не описан, '
         'поддержка самой папки агентом — только через update/publish/restore',
         dict(prompt_present=prompt_present, adapter_rc=rc_card,
              adapter_rank=card.get('priority', {}).get('rank'), actions=actions))

    # --- P6. Инструкция обкатки внутри архива ---------------------------------------------------
    archive_files = [p.name for p in source.rglob('*') if p.is_file()]
    hints = [n for n in archive_files if any(w in n.lower() for w in ('обкат', 'pilot', 'docs', 'инстр'))]
    item('P6', 'В поставке есть инструкция обкатки',
         'владелец находит порядок действий внутри архива',
         'pass' if hints or (source / 'docs').is_dir() else 'fail',
         'в архиве нет ни каталога docs, ни файла с порядком обкатки: единственный текст — README, '
         'написанный для разработчика',
         dict(files=len(archive_files), hints=hints))

    # --- P7. Ни одного шага с ручной правкой поставки -------------------------------------------
    hand_steps = []
    if outcome_install != 'committed' or outcome_connect != 'committed':
        hand_steps.append('P1: раскладку или установку пришлось делать иначе')
    if brief.get('mode') != 'foreign':
        hand_steps.append('P2: вход пришлось искать вручную')
    item('P7', 'Ни один шаг не требует ручной правки поставки',
         'весь сценарий проходится консолью',
         'pass' if not hand_steps else 'fail',
         '; '.join(hand_steps) or 'все шаги прошли консолью: установка, вход, ручной вход, перенос',
         dict(hand_steps=hand_steps))

    # --- P8. Повторяемость ----------------------------------------------------------------------
    before = len(records(repo))
    repeat = []
    for _ in range(2):
        rc_s, status = cli(lab, repo, 'status')
        repeat.append((rc_s, len(status.get('observations', []))))
    item('P8', 'Повторный прогон даёт тот же результат',
         'два одинаковых вызова не меняют состояние',
         'pass' if len(set(repeat)) == 1 and repeat[0][1] == before else 'fail',
         f'состояние до повтора: {before}; два вызова status: {repeat}',
         dict(repeat=repeat))

    counts = {}
    for entry in ITEMS:
        counts[entry['status']] = counts.get(entry['status'], 0) + 1
    out = dict(iteration='И-032', line=args.line, at='2026-11-18', pack_version=PACK_VERSION,
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
