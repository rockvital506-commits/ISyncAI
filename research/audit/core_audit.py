#!/usr/bin/env python3
"""A-002: живой аудит ядра Kit против документов v2.

Зачем. Тесты итераций 105/107/108/109 — замороженные акты приёмки внутри печатей.
Они проверяли поведение своего времени и с тех пор разошлись с кодом намеренно
(см. research/audit/A-002-DIAGNOSIS.md). Править их нельзя: сломается ответ на
вопрос «чем проверяли И-NNN». Живой регрессии у ядра не было.

Этот файл — живая проверка: он сверяет ТЕКУЩИЙ код с документами (kit/base/*.md),
а не со снимками. Плюс «каталог дрейфа»: 20 известных расхождений закреплены
поимённо, чтобы любое НОВОЕ расхождение или молчаливое «исправление» было видно.

Ничего не пишет вне временного каталога, не трогает Git, не ходит в сеть.

Запуск:
    python3 -B research/audit/core_audit.py            # человеку
    python3 -B research/audit/core_audit.py --json     # машинно
Код возврата: 0 — всё сошлось; 1 — есть расхождения.
"""
from __future__ import annotations

import json
import sys
import tempfile
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from kit.base import registry_store as store                      # noqa: E402
from kit.base.operation_card import compile_prompt                # noqa: E402
from kit.base.operation_plan import PlanSession                   # noqa: E402

RELEASE = '0.2.0-audit'


# ---------------------------------------------------------------- каталог дрейфа

#: Известные расхождения замороженных тестов с текущим кодом.
#: Ключ — итерация; значение — ПОЛНЫЙ список ID, которые сейчас расходятся.
#: Любое отличие в обе стороны считается изменением и требует правки каталога
#: вместе с документом, объясняющим почему.
KNOWN_DRIFT = {
    105: ['P02-create', 'N12-no-parent'],
    107: ['M-create-L2', 'M-list-L1', 'M-list-L2', 'M-edit-L1', 'M-edit-L2',
          'M-suspend-L1', 'M-suspend-L2', 'M-resume-L1', 'M-resume-L2',
          'M-revoke-L1', 'M-revoke-L2', 'M-delete-L1', 'M-delete-L2'],
    108: ['NL02', 'N19'],
    109: ['N16-project', 'N17-list', 'N28-kind'],
}


# ---------------------------------------------------------------- рабочее дерево

def entry(ident, kind, authority, parent, scope, *, state='active', text='текст'):
    return {'id': ident, 'kind': kind, 'authority': authority, 'state': state,
            'parent': parent, 'scope': scope, 'title': 'Заголовок ' + ident,
            'text': text, 'basis': 'Аудит A-002', 'criterion': 'Есть отчёт'}


def make_workspace(root, *, parent_scope='docs', parent_state='active', bare_l1=False):
    """Три раздельных корня L0/L1/L2. Родитель C-1 для дочерних записей."""
    root = Path(root).resolve()
    for rel in ('kit/base', 'profiles/pilot', '.agent-contract/project'):
        (root / rel).mkdir(parents=True)
    l0 = {'schema_version': 2, 'area': 'L0', 'roots': ['kit'], 'release_version': RELEASE,
          'entries': [entry('S-1', 'contract', 'system_release', None, '.')]}
    l1_doc = {'schema_version': 2, 'area': 'L1', 'roots': ['profiles/pilot'], 'revision': 0,
              'entries': [entry('C-1', 'contract', 'profile_owner', None, parent_scope,
                                state=parent_state)]}
    l2 = {'schema_version': 2, 'area': 'L2', 'roots': ['.agent-contract'], 'revision': 0,
          'entries': [entry('P-1', 'contract', 'project_owner', None, '.')]}
    write(root / 'kit/base/registry.json', l0)
    write(root / 'profiles/pilot/registry.json', l1_doc)
    write(root / '.agent-contract/project/registry.json', l2)
    return store.Layout(root, 'profiles/pilot')


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, sort_keys=True) + '\n',
                          encoding='utf-8', newline='\n')


def tree_digest(root):
    """Хеши всех файлов дерева: доказательство «ничего не изменилось»."""
    root = Path(root)
    return {p.relative_to(root).as_posix(): sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file()}


CARD = ('Создай черновик {word} {ident} в профиле Pilot, постоянное, '
        'по контракту C-1, область «{scope}», название «Проверка», '
        'основание «Нужно», критерий «Есть отчёт»: {text}')

#: Русское слово вида — так фраза компилируется в нужный kind без подмены полей.
WORD = {'rule': 'правила', 'constraint': 'ограничения', 'protocol': 'протокола',
        'preference': 'предпочтения'}


def card(ident='Q-1', scope='docs', kind='protocol', text='Сверяй свидетельства.'):
    """Карточка из фразы. Подменять params нельзя: _checked_card её перекомпилирует."""
    return compile_prompt(CARD.format(word=WORD[kind], ident=ident, scope=scope, text=text))


# ---------------------------------------------------------------- проверки

def check_matrix():
    """OPERATION-MATRIX.md: таблица 8×3 совпадает с исполняемой матрицей."""
    documented = {
        'read':    {'L0': 'available', 'L1': 'available', 'L2': 'available'},
        'create':  {'L0': 'forbidden', 'L1': 'available', 'L2': 'available'},
        'list':    {'L0': 'planned',   'L1': 'available', 'L2': 'available'},
        'edit':    {'L0': 'forbidden', 'L1': 'available', 'L2': 'available'},
        'suspend': {'L0': 'forbidden', 'L1': 'available', 'L2': 'available'},
        'resume':  {'L0': 'forbidden', 'L1': 'available', 'L2': 'available'},
        'revoke':  {'L0': 'forbidden', 'L1': 'available', 'L2': 'available'},
        'delete':  {'L0': 'forbidden', 'L1': 'available', 'L2': 'available'},
    }
    live = store.operation_matrix()
    bad = [f'{op}/{area}: документ={want}, код={live[op][area]["state"]}'
           for op, areas in documented.items()
           for area, want in areas.items() if live[op][area]['state'] != want]
    return {'name': 'матрица 8×3 против OPERATION-MATRIX.md',
            'cells': sum(len(v) for v in documented.values()), 'mismatches': bad}


def check_schema_scope():
    """SCHEMA-V2.md: scope записи вложен в scope родителя по компонентам."""
    out = []
    for scope, must_pass in (('docs/guide', True), ('docs2/guide', False)):
        with tempfile.TemporaryDirectory() as tmp:
            layout = make_workspace(tmp)
            session = PlanSession(layout, profile_id='Pilot')
            try:
                plan = session.plan(card(scope=scope))
                got, detail = True, plan['outcome']
            except store.StoreError as error:
                got, detail = False, error.diagnostic()['code']
        if got != must_pass:
            out.append(f'scope={scope}: документ={"принять" if must_pass else "отклонить"}, '
                       f'код={"принял" if got else "отклонил"} ({detail})')
    return {'name': 'вложенность scope против SCHEMA-V2.md', 'cases': 2, 'mismatches': out}


def check_schema_parent():
    """SCHEMA-V2.md: parent — ID существующего contract; null только у contract."""
    out = []
    # родитель не contract → отказ
    with tempfile.TemporaryDirectory() as tmp:
        layout = make_workspace(tmp)
        path = Path(layout.workspace) / 'profiles/pilot/registry.json'
        doc = json.loads(path.read_text(encoding='utf-8'))
        doc['entries'][0].update(kind='rule', parent=None)
        write(path, doc)
        session = PlanSession(layout, profile_id='Pilot')
        try:
            session.plan(card())
            out.append('родитель kind=rule: документ требует contract, код принял')
        except store.StoreError:
            pass
    # отсутствующий родитель → отказ (родителя нет в дереве)
    with tempfile.TemporaryDirectory() as tmp:
        layout = make_workspace(tmp)
        path = Path(layout.workspace) / 'profiles/pilot/registry.json'
        doc = json.loads(path.read_text(encoding='utf-8'))
        doc['entries'] = []
        write(path, doc)
        session = PlanSession(layout, profile_id='Pilot')
        try:
            got = session.plan(card())
            out.append(f'отсутствующий родитель: код выдал {got["outcome"]} вместо отказа')
        except store.StoreError as error:
            if error.diagnostic()['code'] not in ('parent', 'invalid_entry'):
                out.append(f'отсутствующий родитель: неожиданный код {error.diagnostic()["code"]}')
    return {'name': 'родитель записи против SCHEMA-V2.md', 'cases': 2, 'mismatches': out}


def check_plan_outcomes():
    """OPERATION-PLAN.md: исходы и их состав (нет билета без planned)."""
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        layout = make_workspace(tmp)
        session = PlanSession(layout, profile_id='Pilot')

        # missing_params: нет текста
        c = compile_prompt('Создай протокол Q-9 в профиле Pilot.')
        plan = session.plan(c)
        if plan['outcome'] != 'missing_params' or 'ticket' in plan or 'diff' in plan:
            out.append(f'missing_params: получено {plan["outcome"]}, ключи {sorted(plan)}')

        # listed: без диффа и билета
        plan = session.plan(compile_prompt('Покажи протоколы в профиле Pilot.'))
        if plan['outcome'] != 'listed' or 'ticket' in plan or 'diff' in plan:
            out.append(f'listed: получено {plan["outcome"]}, ключи {sorted(plan)}')

        # planned: дифф + билет
        plan = session.plan(card())
        if plan['outcome'] != 'planned' or 'ticket' not in plan or 'diff' not in plan:
            out.append(f'planned: получено {plan["outcome"]}, ключи {sorted(plan)}')
        else:
            steps = plan['diff'].get('revision')
            if steps != {'from': 0, 'to': 1}:
                out.append(f'planned: ревизия {steps} вместо 0→1')

        # no_change: тот же текст и адрес → пустой дифф, нет билета
        session.apply(json.loads(json.dumps(plan)), confirmed_ticket=plan['ticket'])
        again = session.plan(card())
        if again['outcome'] != 'no_change' or 'ticket' in again:
            out.append(f'no_change: получено {again["outcome"]}, ключи {sorted(again)}')
    return {'name': 'исходы плана против OPERATION-PLAN.md', 'cases': 4, 'mismatches': out}


def check_l1_format():
    """REGISTRY-JOURNAL.md: запись ЛЮБОГО вида даёт контейнер с журналом."""
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        layout = make_workspace(tmp)
        path = Path(layout.workspace) / 'profiles/pilot/registry.json'
        bare = json.loads(path.read_text(encoding='utf-8'))
        if 'entries' not in bare:
            out.append('голый v2 не читается как реестр')

        session = PlanSession(layout, profile_id='Pilot')
        plan = session.plan(card())
        session.apply(json.loads(json.dumps(plan)), confirmed_ticket=plan['ticket'])
        doc = json.loads(path.read_text(encoding='utf-8'))
        if 'registry_format' not in doc or 'journal' not in doc:
            out.append(f'после записи формат файла: {sorted(doc)} — нет контейнера журнала')
        else:
            rows = doc['registry']['entries']
            added = [r for r in rows if r['id'] == 'Q-1']
            if not added:
                out.append('после записи нет Q-1 в реестре')
            elif added[0]['kind'] != 'protocol':
                out.append(f'вид записан как {added[0]["kind"]}, ждали protocol')
            decisions = doc['journal'].get('decisions') or []
            if len(decisions) != 1:
                out.append(f'решений в журнале {len(decisions)}, ждали 1')
    return {'name': 'формат файла L1 против REGISTRY-JOURNAL.md', 'cases': 3, 'mismatches': out}


def check_kinds_and_layers():
    """И-110 DESIGN: create принимает любой из 5 видов; L2 доступен через карточку."""
    out = []
    kinds = ('rule', 'constraint', 'protocol', 'preference')
    for kind in kinds:
        with tempfile.TemporaryDirectory() as tmp:
            layout = make_workspace(tmp)
            session = PlanSession(layout, profile_id='Pilot')
            try:
                plan = session.plan(card(ident='Q-' + kind[:3], kind=kind))
            except store.StoreError as error:
                out.append(f'вид {kind}: отказ {error.diagnostic()["code"]} — документ разрешает')
                continue
            if plan['outcome'] != 'planned':
                out.append(f'вид {kind}: {plan["outcome"]} вместо planned')
    # L2 через карточку
    with tempfile.TemporaryDirectory() as tmp:
        layout = make_workspace(tmp)
        session = PlanSession(layout, profile_id='Pilot')
        c = compile_prompt('Создай черновик правила Q-2 в проекте, постоянное, '
                           'по контракту P-1, область «docs», название «Пр», '
                           'основание «Нужно», критерий «Есть»: Текст правила.')
        try:
            plan = session.plan(c)
            if plan['outcome'] != 'planned' or plan['diff']['file'] != '.agent-contract/project/registry.json':
                out.append(f'L2: {plan["outcome"]}, файл {plan.get("diff", {}).get("file")}')
        except store.StoreError as error:
            out.append(f'L2: отказ {error.diagnostic()["code"]} — документ разрешает')
    return {'name': 'виды и слои против И-110 DESIGN', 'cases': 5, 'mismatches': out}


def check_tickets():
    """OPERATION-PLAN.md: без билета, с чужим и с изменённым планом записи нет."""
    out = []
    scenarios = (
        ('без билета', lambda s, p: s.apply(p, confirmed_ticket=None)),
        ('чужой билет', lambda s, p: s.apply(p, confirmed_ticket='0' * 64)),
        ('билет без плана', lambda s, p: s.apply(None, confirmed_ticket=p['ticket'])),
        ('изменённый план', lambda s, p: s.apply({**p, 'diff': {}}, confirmed_ticket=p['ticket'])),
    )
    for name, act in scenarios:
        with tempfile.TemporaryDirectory() as tmp:
            layout = make_workspace(tmp)
            session = PlanSession(layout, profile_id='Pilot')
            before = tree_digest(tmp)
            plan = session.plan(card())
            try:
                act(session, json.loads(json.dumps(plan)))
                out.append(f'{name}: запись прошла без отказа')
            except store.StoreError:
                pass
            if tree_digest(tmp) != before:
                out.append(f'{name}: дерево изменилось при отказе')
    # повтор того же билета после успеха
    with tempfile.TemporaryDirectory() as tmp:
        layout = make_workspace(tmp)
        session = PlanSession(layout, profile_id='Pilot')
        plan = session.plan(card())
        payload = json.loads(json.dumps(plan))
        session.apply(payload, confirmed_ticket=plan['ticket'])
        after_first = tree_digest(tmp)
        try:
            session.apply(payload, confirmed_ticket=plan['ticket'])
            out.append('повтор билета: запись прошла второй раз')
        except store.StoreError:
            pass
        if tree_digest(tmp) != after_first:
            out.append('повтор билета: дерево изменилось')
    return {'name': 'дисциплина билета против OPERATION-PLAN.md', 'cases': 5, 'mismatches': out}


def check_l0_immutable():
    """OPERATION-MATRIX.md: мутации L0 запрещены при любой формулировке."""
    out = []
    for phrase in ('Создай черновик правила Q-3 в L0, постоянное, по контракту S-1, '
                   'область «docs», название «П», основание «Н», критерий «Е»: текст.',
                   'Покажи правила в L0.'):
        with tempfile.TemporaryDirectory() as tmp:
            layout = make_workspace(tmp)
            session = PlanSession(layout, profile_id='Pilot')
            before = tree_digest(tmp)
            try:
                got = session.plan(compile_prompt(phrase))
                # OPERATION-MATRIX.md строка 17: у мутаций L0 — system_immutable
                # (карточка отвергает сразу), у list — planned даёт operation_unavailable.
                # Любой исход, кроме этих двух, означал бы, что L0 стал изменяемым.
                if got['outcome'] != 'rejected':
                    out.append(f'L0: исход {got["outcome"]} вместо rejected')
            except store.StoreError as error:
                code = error.diagnostic()['code']
                if code not in ('system_immutable', 'operation_unavailable'):
                    out.append(f'L0: код {code} вместо system_immutable/operation_unavailable')
            if tree_digest(tmp) != before:
                out.append('L0: дерево изменилось')
    return {'name': 'неизменность L0 против OPERATION-MATRIX.md', 'cases': 2, 'mismatches': out}


def check_code():
    """STORAGE-V2.md: steady-коды ошибок различимы."""
    out = []
    seen = {}
    # parent_missing: родителя нет в дереве
    with tempfile.TemporaryDirectory() as tmp:
        layout = make_workspace(tmp)
        path = Path(layout.workspace) / 'profiles/pilot/registry.json'
        doc = json.loads(path.read_text(encoding='utf-8'))
        doc['entries'] = []
        write(path, doc)
        session = PlanSession(layout, profile_id='Pilot')
        try:
            session.plan(card())
        except store.StoreError as error:
            seen['parent'] = error.diagnostic()['code']
    # scope_outside: scope вне родителя
    with tempfile.TemporaryDirectory() as tmp:
        layout = make_workspace(tmp, parent_scope='docs')
        session = PlanSession(layout, profile_id='Pilot')
        try:
            session.plan(card(scope='other/guide'))
        except store.StoreError as error:
            seen['scope_outside'] = error.diagnostic()['code']
    # system_immutable: L0 — карточка отвергает сама, с этим кодом
    with tempfile.TemporaryDirectory() as tmp:
        layout = make_workspace(tmp)
        session = PlanSession(layout, profile_id='Pilot')
        got = compile_prompt('Создай черновик правила Q-4 в L0, постоянное, '
                             'по контракту S-1, область «docs», название «П», '
                             'основание «Н», критерий «Е»: текст.')
        seen['system_immutable'] = got.get('code') if got['outcome'] == 'rejected' else got['outcome']
    if seen.get('parent') not in ('parent', 'invalid_entry'):
        out.append(f'отсутствующий родитель дал {seen.get("parent")!r}')
    if seen.get('scope_outside') != 'parent':
        out.append(f'scope вне родителя дал {seen.get("scope_outside")!r}, ждали parent (A4)')
    if seen.get('system_immutable') != 'system_immutable':
        out.append(f'L0 дал {seen.get("system_immutable")!r}')
    return {'name': 'коды ошибок против OPERATION-MATRIX.md A4', 'cases': 3, 'mismatches': out}


def check_known_drift():
    """Каталог дрейфа: ровно 20 известных расхождений, ни больше ни меньше."""
    import importlib.util

    out, rows = [], {}
    for iteration, name in ((105, 'test_layout'), (107, 'test_policy'),
                            (108, 'test_cards'), (109, 'test_plan')):
        path = ROOT / f'research/{iteration}/{name}.py'
        spec = importlib.util.spec_from_file_location(f'drift{iteration}', path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[f'drift{iteration}'] = module
        try:
            spec.loader.exec_module(module)
        except Exception as error:                     # noqa: BLE001
            out.append(f'И-{iteration}: модуль не загрузился — {type(error).__name__}')
            continue
        cases = json.loads((ROOT / f'research/{iteration}/CASES.json')
                           .read_text(encoding='utf-8'))['cases']
        rows[iteration] = {c['id']: c for c in cases}
        drifted = drift_of(module, cases, iteration)
        known = KNOWN_DRIFT[iteration]
        new = sorted(set(drifted) - set(known))
        healed = sorted(set(known) - set(drifted))
        if new:
            out.append(f'И-{iteration}: НОВЫЕ расхождения {new}')
        if healed:
            out.append(f'И-{iteration}: перестали расходиться {healed} — обновите каталог')
    return {'name': 'каталог дрейфа 105/107/108/109',
            'cases': sum(len(v) for v in rows.values()), 'mismatches': out}


def drift_of(module, cases, iteration):
    """ID случаев, которые сейчас дают не тот результат, что записан в замороженном корпусе."""
    import platform
    import subprocess

    if iteration in (105, 108):
        # Эти тесты строят evidence внутри main() и печатают его; берём оттуда.
        name = 'test_layout' if iteration == 105 else 'test_cards'
        run = subprocess.run([sys.executable, '-B', str(ROOT / f'research/{iteration}/{name}.py')],
                             capture_output=True, text=True)
        evidence = json.loads(run.stdout)
        return [r['id'] for r in module.case_checks(cases, evidence) if r['status'] != 'pass']

    if iteration == 109:
        # Падает на N17 внутри общего прогона, поэтому по одному случаю.
        audit = module.Audit()
        drifted = []
        for case in cases:
            try:
                row = module.observe(store, PlanSession, compile_prompt, audit, case)
                actual = row['observed']
            except Exception:                          # noqa: BLE001
                drifted.append(case['id'])
                continue
            if json.dumps(actual, sort_keys=True, ensure_ascii=False) != \
                    json.dumps(case['expected'], sort_keys=True, ensure_ascii=False):
                drifted.append(case['id'])
        return drifted

    evidence = {'os': platform.system(), 'rows': []}
    for case in cases:
        try:
            if iteration == 105:
                evidence['rows'].append(module.observe(store, case))
            else:
                evidence['rows'].append(module.observe(store, case))
        except Exception:                              # noqa: BLE001
            evidence['rows'].append({'id': case['id'], 'observed': {'<исключение>': True}})
    if iteration == 108:
        for row in evidence['rows']:
            if 'observed' not in row:
                row['observed'] = {'empty': {'card': {}}, 'seeded': {'card': {}}}
    return [r['id'] for r in module.case_checks(cases, evidence) if r['status'] != 'pass']


CHECKS = (check_matrix, check_schema_scope, check_schema_parent, check_plan_outcomes,
          check_l1_format, check_kinds_and_layers, check_tickets, check_l0_immutable,
          check_code, check_known_drift)


def main():
    report, failures = {'audit': 'A-002', 'release': RELEASE, 'checks': []}, 0
    for check in CHECKS:
        try:
            result = check()
        except Exception as error:                     # noqa: BLE001
            result = {'name': check.__name__, 'cases': 0,
                      'mismatches': [f'исключение: {type(error).__name__}: {error}']}
        result.setdefault('cases', 0)
        result.setdefault('mismatches', [])
        result['status'] = 'pass' if not result['mismatches'] else 'fail'
        failures += bool(result['mismatches'])
        report['checks'].append(result)
    report['status'] = 'pass' if not failures else 'fail'
    report['summary'] = {'checks': len(report['checks']), 'failed': failures,
                         'cases': sum(c['cases'] for c in report['checks']),
                         'mismatches': sum(len(c['mismatches']) for c in report['checks'])}
    if '--json' in sys.argv:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f'Аудит ядра Kit ({report["release"]})')
        for check in report['checks']:
            mark = 'OK  ' if check['status'] == 'pass' else 'ОШИБ'
            print(f'  {mark} {check["name"]} · случаев {check["cases"]}')
            for line in check['mismatches']:
                print(f'        — {line}')
        s = report['summary']
        print(f'\nИтог: {s["checks"]} проверок, случаев {s["cases"]}, '
              f'расхождений {s["mismatches"]}, статус {report["status"]}')
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
