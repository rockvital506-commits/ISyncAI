#!/usr/bin/env python3
"""И-031: стенд условной обкатки.

Проходит сценарий владельца целиком теми средствами, которые есть у исследователя: отдельные
процессы, копии поставки, два «компьютера» в виде каталогов и git. Всё, что должно делаться руками
владельца, делается через опубликованную консольную команду — импорт не используется.

Получается матрица P1–P8. В И-031 она измеряет стартовую точку: часть пунктов обязана провалиться,
и это записывается честно, а не закрашивается.

Запуск: python3 pilot.py --tree ../release-0.1.11/base/AgentContractLab --line base
"""
from __future__ import annotations

import argparse
import hashlib
import os
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).absolute().parent
PACK_VERSION = '0.1.11'
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
            '--project', project, command]
    proc = subprocess.run(args, input=(json.dumps(payload).encode() if payload is not None else b''),
                          capture_output=True, cwd=str(lab))
    if not expect_error:
        assert proc.stderr == b'', proc.stderr.decode()[-600:]
    try:
        out = json.loads(proc.stdout.decode())
    except Exception:
        out = {'raw': proc.stdout.decode()[:400], 'stderr': proc.stderr.decode()[-400:]}
    return proc.returncode, out


def install_project(lab, project):
    pin = sha(lab / f'releases/{PACK_VERSION}/manifest.json')
    request = dict(op='install', package=f'releases/{PACK_VERSION}', pin=pin)
    rc, plan = cli(lab, project, 'plan', request)
    assert rc == 0, plan
    rc, applied = cli(lab, project, 'apply', dict(request=request, ticket=plan['ticket']))
    assert rc == 0 and applied.get('outcome') == 'committed', applied
    return applied


def connect_project(lab, project):
    rc, plan = cli(lab, project, 'plan', dict(op='connect'))
    assert rc == 0, plan
    rc, applied = cli(lab, project, 'apply', dict(request=dict(op='connect'), ticket=plan['ticket']))
    assert rc == 0 and applied.get('outcome') == 'committed', applied
    return applied


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
    rc, applied = cli(lab, project, 'apply',
                      dict(request=dict(op='record_check', observation=dict(obs)), ticket=plan['ticket']))
    assert rc == 0, applied
    return applied['outcome'], plan['notes']


def records(lab, project):
    path = lab / project / '.agent-contract/project/checks.json'
    return json.loads(path.read_text(encoding='utf-8'))['checks'] if path.is_file() else []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--tree', required=True)
    ap.add_argument('--line', default='base')
    args = ap.parse_args()
    source = pathlib.Path(args.tree).absolute()
    assert (source / 'kit/tools/contract.py').is_file(), source

    root = pathlib.Path(tempfile.mkdtemp(prefix='pilot-'))
    lab = root / 'AgentContractLab'
    shutil.copytree(source, lab)

    # --- P1. Раскладка владельца: архив распакован в корень репозитория -------------------------
    repo_root = root / 'myproject'
    (repo_root / '.git').mkdir(parents=True)
    (repo_root / 'README.md').write_text('проект владельца\n', encoding='utf-8')
    shutil.copytree(source, repo_root / 'AgentContractLab')
    rc, out = cli(repo_root / 'AgentContractLab', '.', 'inventory')
    inside = (repo_root / 'AgentContractLab/kit/tools/contract.py').is_file()
    parent_lab = repo_root / 'AgentContractLab'
    rc2, out2 = 0, {}
    if rc != 0:
        # второй заход: лаборатория — родительский каталог, проект — репозиторий рядом
        rc2, out2 = cli(lab, '.', 'inventory')
    item('P1', 'Архив распакован в корень репозитория, установка без ручной правки',
         'install и connect проходят из консоли в раскладке шага 5',
         'fail' if rc != 0 and rc2 != 0 else 'pass',
         'проект обязан быть подкаталогом корня комплекта; проект «.», «..» и путь снаружи отклоняются',
         dict(archive_inside_repo=inside, project_dot=out, parent_layout=out2))

    # Рабочая раскладка для остальных шагов — та, которую продукт допускает.
    for name in ('repo', 'repo2'):
        (lab / name).mkdir()
    for name in ('repo', 'repo2'):
        (lab / name / 'demo.txt').write_text('синтетический вход\n', encoding='utf-8')
    install_project(lab, 'repo')
    connect_project(lab, 'repo')

    # --- P2. Вход занят: в репозитории уже есть AGENTS.md ---------------------------------------
    (lab / 'repo2/AGENTS.md').write_text('# инструкции проекта\n', encoding='utf-8')
    install_project(lab, 'repo2')
    rc, plan = cli(lab, 'repo2', 'plan', dict(op='connect'))
    manual_path = (lab / 'repo2/.agent-contract/base/START.md').is_file()
    rc_read, out_read = cli(lab, 'repo2', 'status')
    item('P2', 'Вход уже занят чужим AGENTS.md',
         'документированный путь вместо тупика',
         'fail',
         'connect отказывает foreign_entry; «ручное чтение START.md» файлом доступно, но командой или '
         'процедурой не оформлено',
         dict(plan_error=plan.get('error'), message=plan.get('message'),
              start_present=manual_path, status_rc=rc_read, status_keys=sorted(out_read)[:8]))

    # --- P3. Одно событие, увиденное двумя машинами ---------------------------------------------
    git(lab / 'repo', 'init', '-q')
    git(lab / 'repo', 'config', 'user.email', 'pilot@local')
    git(lab / 'repo', 'config', 'user.name', 'pilot')
    git(lab / 'repo', 'add', '-A')
    git(lab / 'repo', 'commit', '-q', '-m', 'контракт установлен')
    outcome, notes = record(lab, 'repo', observation('Проверка проходит.', ENV_LOCAL))
    git(lab / 'repo', 'add', '-A')
    git(lab / 'repo', 'commit', '-q', '-m', 'первое наблюдение')
    git(lab, 'init', '-q', '--bare', 'origin.git')
    git(lab / 'repo', 'remote', 'add', 'origin', str(lab / 'origin.git'))
    rc_push, out_push = git(lab / 'repo', 'push', '-q', 'origin', 'HEAD:main')
    # ящик пуст, пока в него не пришёл хотя бы один коммит: ветка по умолчанию — main
    rc_clone, out_clone = git(lab, 'clone', '-q', '-b', 'main', str(lab / 'origin.git'), 'arena')
    assert rc_push == 0 and rc_clone == 0, (out_push, out_clone)
    git(lab / 'arena', 'config', 'user.email', 'arena@cloud')
    git(lab / 'arena', 'config', 'user.name', 'arena')
    rc_b, out_b = cli(lab, 'arena', 'plan', dict(op='record_check',
                                                observation=observation('Проверка проходит.', ENV_ARENA)),
                      expect_error=True)
    journal_error = out_b.get('error')
    # рабочий обход: журнал операций несёт абсолютный путь и в копию не переносится
    shutil.rmtree(lab / 'arena/.agent-contract/local', ignore_errors=True)
    outcome_b, notes_b = record(lab, 'arena', observation('Проверка проходит.', ENV_ARENA))
    in_arena = len(records(lab, 'arena'))
    in_repo = len(records(lab, 'repo'))
    item('P3', 'Одно событие, увиденное локально и в облачном агенте',
         'одна запись на событие, если правило так решило',
         'pass' if in_arena == 1 else 'fail',
         f'записей в облачном клоне: {in_arena}; локально: {in_repo}. Условия сравнения включают os и '
         'model, а у машин они разные: по действующему правилу это два разных события',
         dict(local_outcome=outcome, cloud_outcome=outcome_b, notes=notes_b, in_arena=in_arena,
              journal_error_on_clone=journal_error))

    # --- P4. Состояние через git: два писателя и перенос журнала --------------------------------
    git(lab / 'arena', 'add', '-A')
    git(lab / 'arena', 'commit', '-q', '-m', 'наблюдение из облака')
    rc_push_b, out_push_b = git(lab / 'arena', 'push', '-q', 'origin', 'HEAD:main')
    record(lab, 'repo', observation('Проверка проходит.', ENV_LOCAL, case='сборка отчёта'))
    git(lab / 'repo', 'add', '-A')
    git(lab / 'repo', 'commit', '-q', '-m', 'наблюдение локально')
    rc_pull, out_pull = git(lab / 'repo', 'pull', '-q', '--no-rebase', 'origin', 'main')
    conflicted = rc_pull != 0
    state_intacts = []
    for name in ('repo', 'arena'):
        try:
            json.loads((lab / name / '.agent-contract/project/checks.json').read_text(encoding='utf-8'))
            state_intacts.append(name)
        except Exception:
            pass
    if conflicted:
        git(lab / 'repo', 'merge', '--abort')
    item('P4', 'Состояние переживает git: перенос и два писателя',
         'clone/push/pull и слияние не рвут состояние; процедура описана',
         'pass' if not conflicted and journal_error is None and len(state_intacts) == 2 else 'fail',
         'журнал операций содержит абсолютный путь проекта и после клонирования не принимается '
         '(обход — удалить `.agent-contract/local`); при двух писателях слияние общий JSON не '
         'поддержано; какая часть `.agent-contract` переносится, в поставке не сказано',
         dict(push_rc=rc_push_b, pull_rc=rc_pull, pull=out_pull.splitlines()[-3:],
              journal_error=journal_error, readable=state_intacts))

    # --- P5. Первый промпт: исполнимость по тексту ----------------------------------------------
    start = (lab / 'repo/.agent-contract/base/START.md').read_text(encoding='utf-8')
    prompt_present = 'Начальный запрос после смены среды' in start
    actions = [('открыть START.md', True), ('открыть манифест и правила', True),
               ('объяснить правила', True), ('показать версии', True),
               ('ограничения среды', True), ('конфликты с другими инструкциями', True),
               ('предложить вход', True), ('показать разницу и дождаться согласия', True),
               ('отличить обнаружение от проверенного поведения', True),
               ('поддержка и коррекция самой папки', False)]
    rc_card, card = cli(lab, 'repo', 'adapter', dict(name='kilo'))
    item('P5', 'Первый промпт исполним буквально',
         'весь ритуал первого обращения покрыт командами и порядком',
         'fail',
         f'в тексте {len(actions)} действий, командой покрыто '
         f'{sum(1 for _, ok in actions if ok)}; порядок («сначала это, потом то») не описан, '
         'поддержка самой папки агентом — только через update/publish/restore',
         dict(prompt_present=prompt_present, adapter_rc=rc_card,
              adapter_rank=card.get('priority', {}).get('rank'), actions=actions))

    # --- P6. Инструкция обкатки внутри архива ---------------------------------------------------
    archive_names = [p.name for p in source.rglob('*') if p.is_file()]
    hints = [n for n in archive_names if any(w in n.lower() for w in ('обкат', 'pilot', 'docs', 'инстр'))]
    docs_dir = (source / 'docs').is_dir()
    item('P6', 'В поставке есть инструкция обкатки',
         'владелец находит порядок действий внутри архива',
         'pass' if hints or docs_dir else 'fail',
         'в архиве нет ни каталога docs, ни файла с порядком обкатки: единственный текст — README, '
         'написанный для разработчика',
         dict(files=len(archive_names), hints=hints, docs_dir=docs_dir))

    # --- P7. Ни одного шага с ручной правкой поставки -------------------------------------------
    hand_steps = []
    if rc != 0:
        hand_steps.append('P1: раскладку пришлось заменить на «архив сверху, проект внутри»')
    if plan.get('error') == 'foreign_entry':
        hand_steps.append('P2: вход пришлось искать вручную (другой проект или чтение START.md)')
    item('P7', 'Ни один шаг не требует правки поставки руками',
         'весь сценарий проходится консолью',
         'pass' if not hand_steps else 'fail',
         '; '.join(hand_steps) or 'все шаги прошли консолью',
         dict(hand_steps=hand_steps))

    # --- P8. Повторяемость ----------------------------------------------------------------------
    before = len(records(lab, 'repo'))
    repeat = []
    for _ in range(2):
        rc_s, status = cli(lab, 'repo', 'status')
        repeat.append((rc_s, len(status.get('observations', []))))
    item('P8', 'Повторный прогон даёт тот же результат',
         'два одинаковых вызова не меняют состояние',
         'pass' if len(set(repeat)) == 1 and repeat[0][1] == before else 'fail',
         f'состояние до повтора: {before}; два вызова status: {repeat}',
         dict(repeat=repeat))

    counts = {}
    for entry in ITEMS:
        counts[entry['status']] = counts.get(entry['status'], 0) + 1
    out = dict(iteration='И-031', line=args.line, at='2026-11-18', pack_version=PACK_VERSION,
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
