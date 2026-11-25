#!/usr/bin/env python3
"""A-002: живой аудит ядра Kit против документов v2.

Зачем. Тесты итераций 105/107/108/109 — замороженные акты приёмки внутри печатей.
Они проверяли поведение своего времени и с тех пор разошлись с кодом намеренно
(см. research/audit/A-002-DIAGNOSIS.md). Править их нельзя: сломается ответ на
вопрос «чем проверяли И-NNN». Проверенные расхождения объяснены последующими изменениями; это не доказывает отсутствие других дефектов.

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

import copy
import json
import re
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
    for rel in ('kit/base', 'profiles/pilot', '.domain-agent-kit/project'):
        (root / rel).mkdir(parents=True)
    l0 = {'schema_version': 2, 'area': 'L0', 'roots': ['kit'], 'release_version': RELEASE,
          'entries': [entry('S-1', 'contract', 'system_release', None, '.')]}
    l1_doc = {'schema_version': 2, 'area': 'L1', 'roots': ['profiles/pilot'], 'revision': 0,
              'entries': [entry('C-1', 'contract', 'profile_owner', None, parent_scope,
                                state=parent_state)]}
    l2 = {'schema_version': 2, 'area': 'L2', 'roots': ['.domain-agent-kit'], 'revision': 0,
          'entries': [entry('P-1', 'contract', 'project_owner', None, '.')]}
    write(root / 'kit/base/registry.json', l0)
    write(root / 'profiles/pilot/registry.json', l1_doc)
    write(root / '.domain-agent-kit/project/registry.json', l2)
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

MATRIX_REFERENCE = {
    'read':    ('available', 'available', 'available'),
    'create':  ('forbidden', 'available', 'available'),
    'list':    ('planned',   'available', 'available'),
    'edit':    ('forbidden', 'available', 'available'),
    'activate': ('forbidden', 'available', 'available'),
    'suspend': ('forbidden', 'available', 'available'),
    'resume':  ('forbidden', 'available', 'available'),
    'revoke':  ('forbidden', 'available', 'available'),
    'delete':  ('forbidden', 'available', 'available'),
}
MATRIX_CODES = {'available': None, 'planned': 'operation_unavailable',
                'forbidden': 'system_immutable'}


def parse_matrix(text):
    """Строго читаем единственную таблицу L0/L1/L2, отказываемся от неполных данных."""
    lines = text.splitlines()
    header = '| Операция | L0 | L1 | L2 |'
    if lines.count(header) != 1:
        raise ValueError('не найдена единственная таблица операций')
    start = lines.index(header) + 2
    rows = {}
    for line in lines[start:]:
        if not line.startswith('|'):
            break
        cells = [x.strip() for x in line.strip().strip('|').split('|')]
        if len(cells) != 4:
            raise ValueError('неверная строка таблицы')
        match = re.match(r'^`([a-z]+)`', cells[0])
        if not match or match.group(1) in rows:
            raise ValueError('неверная или повторная операция')
        states = tuple(x.strip('`') for x in cells[1:])
        if any(x not in MATRIX_CODES for x in states):
            raise ValueError('неизвестное состояние')
        rows[match.group(1)] = states
    if set(rows) != set(MATRIX_REFERENCE):
        raise ValueError('неполная или расширенная таблица операций')
    # Документ также должен сохранять отображение состояний в диагностические коды.
    mapping = '`available` имеет `code: null`, `planned` — `operation_unavailable`, `forbidden` — `system_immutable`'
    if mapping not in text:
        raise ValueError('описание кодов состояний изменилось или отсутствует')
    return rows


def compare_matrix(text, live):
    documented = parse_matrix(text)
    out = []
    if set(live) != set(MATRIX_REFERENCE):
        out.append('код: операции матрицы не совпадают с эталоном')
    for op, reference in MATRIX_REFERENCE.items():
        for pos, area in enumerate(('L0', 'L1', 'L2')):
            state = documented[op][pos]
            if state != reference[pos]:
                out.append(f'{op}/{area}: документ={state}, эталон={reference[pos]}')
            actual = live.get(op, {}).get(area)
            want = {'state': state, 'code': MATRIX_CODES[state]}
            if actual != want:
                out.append(f'{op}/{area}: документ={want}, код={actual}')
        if set(live.get(op, {})) != {'L0', 'L1', 'L2'}:
            out.append(f'{op}: неполный или расширенный набор областей')
    return out


def check_matrix():
    text = (ROOT / 'kit/base/OPERATION-MATRIX.md').read_text(encoding='utf-8')
    return {'name': 'матрица 9×3 против OPERATION-MATRIX.md', 'cases': 27,
            'mismatches': compare_matrix(text, store.operation_matrix())}


def check_schema_scope():
    """SCHEMA-V2.md: scope записи вложен в scope родителя по компонентам."""
    out = []
    for scope, must_pass in (('docs/guide', True), ('docs2/guide', False)):
        with tempfile.TemporaryDirectory() as tmp:
            layout = make_workspace(tmp)
            session = PlanSession(layout, profile_id='Pilot')
            try:
                plan = session.plan(card(scope=scope))
                got, detail = plan.get('outcome') == 'planned', plan.get('outcome')
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
            if error.diagnostic()['code'] != 'parent':
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
    """Четыре дочерних вида в L1 и правило в L2 через карточку."""
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
            if plan['outcome'] != 'planned' or plan['diff']['file'] != '.domain-agent-kit/project/registry.json':
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
    """Два отдельных сценария L0, не утверждение обо всех формулировках."""
    out = []
    scenarios = (
        ('Создай черновик правила Q-3 в L0, постоянное, по контракту S-1, '
         'область «docs», название «П», основание «Н», критерий «Е»: текст.', 'system_immutable'),
        ('Покажи правила в L0.', 'operation_unavailable'),
    )
    for phrase, expected_code in scenarios:
        with tempfile.TemporaryDirectory() as tmp:
            layout = make_workspace(tmp)
            session = PlanSession(layout, profile_id='Pilot')
            before = tree_digest(tmp)
            try:
                got = session.plan(compile_prompt(phrase))
                out.append(f'L0: получен исход {got.get("outcome")} вместо отказа {expected_code}')
            except store.StoreError as error:
                code = error.diagnostic()['code']
                if code != expected_code:
                    out.append(f'L0: код {code} вместо {expected_code}')
            if tree_digest(tmp) != before:
                out.append('L0: дерево изменилось')
    return {'name': 'два сценария L0 против OPERATION-MATRIX.md', 'cases': 2, 'mismatches': out}


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
    if seen.get('parent') != 'parent':
        out.append(f'отсутствующий родитель дал {seen.get("parent")!r}')
    if seen.get('scope_outside') != 'parent':
        out.append(f'scope вне родителя дал {seen.get("scope_outside")!r}, ждали parent (A4)')
    if seen.get('system_immutable') != 'system_immutable':
        out.append(f'L0 дал {seen.get("system_immutable")!r}')
    return {'name': 'коды ошибок против OPERATION-MATRIX.md A4', 'cases': 3, 'mismatches': out}


def current_cases(iteration, cases):
    """Ожидаемое поведение сегодня: точечные замены к историческим ожиданиям."""
    cases = copy.deepcopy(cases)
    by_id = {case['id']: case for case in cases}
    if len(by_id) != len(cases) or not set(KNOWN_DRIFT[iteration]) <= set(by_id):
        raise ValueError('повторные или отсутствующие ID случаев')
    if iteration == 105:
        by_id['P02-create']['expected']['exact_append'] = False
        by_id['N12-no-parent']['expected']['error']['code'] = 'parent'
    elif iteration == 107:
        # Старый тест create/L2 вызывает нативный create L1 после проверки допуска L2.
        by_id['M-create-L2']['expected'] = copy.deepcopy(by_id['M-create-L1']['expected'])
        for ident in KNOWN_DRIFT[107]:
            if ident == 'M-create-L2':
                continue
            by_id[ident]['expected'] = {'ok': True, 'changed': [], 'l0_l2_unchanged': True,
                                         'registry_untouched': True,
                                         'route': {'state': 'available', 'code': None}}
    elif iteration == 108:
        for ident in KNOWN_DRIFT[108]:
            expected = by_id[ident]['expected']
            expected['missing'].insert(0, {'field': 'persistence', 'reason': 'absent'})
            expected['questions'].insert(0, {'field': 'persistence', 'text':
                'Как трактовать запрос: как постоянное изменение реестра, временное указание, предложение или гипотезу?'})
            expected.update(code='missing_params', outcome='missing_params')
    elif iteration == 109:
        for ident, start in (('N16-project', 7), ('N28-kind', 4)):
            by_id[ident]['expected'] = {'ok': True, 'outcome': 'planned', 'dry_run': True,
                'valid_ticket': True, 'exact_preview': False, 'revision': {'from': start, 'to': start + 1},
                'changed': [], 'profile_untouched': True, 'l0_l2_unchanged': True,
                'write_event': False, 'replacements': 0, 'staged_matches_preview': False}
    return cases


def subprocess_evidence(path):
    import subprocess
    run = subprocess.run([sys.executable, '-B', str(path)], capture_output=True, text=True, timeout=120)
    if run.returncode not in (0, 1):
        raise ValueError(f'тест завершился с кодом {run.returncode}: {run.stderr[-500:]}')
    try:
        data = json.loads(run.stdout)
    except (ValueError, TypeError) as error:
        raise ValueError(f'нет корректного JSON теста, код {run.returncode}: {run.stderr[-500:]}') from error
    if type(data) is not dict or type(data.get('rows')) is not list or run.stderr:
        raise ValueError(f'неполный результат теста или stderr: {run.stderr[-500:]}')
    return data


def compare_evidence(module, cases, evidence):
    """Запускаем исторический проверяющий код поверх актуального эталона, включая digest."""
    return [f'{row["id"]}: {row.get("issue", "fail")}'
            for row in module.case_checks(cases, evidence) if row['status'] != 'pass']


def known_exception(ident, error):
    return ident == 'N17-list' and type(error) is KeyError and error.args == ('diff',)


def translated_paths(value):
    """Переадресация синтетических фикстур в памяти; исходный корпус не меняется."""
    if isinstance(value, str):
        return value.replace('.agent-contract', '.domain-agent-kit')
    if isinstance(value, list):
        return [translated_paths(x) for x in value]
    if isinstance(value, dict):
        return {key: translated_paths(item) for key, item in value.items()}
    return value


def load_path_adapted_test(iteration, path):
    """Только исторический код репозитория; в памяти меняются строковые литералы пути.

    Это адаптированный тест текущего пути, не повтор исходного запечатанного испытания.
    """
    import ast
    import importlib.util
    class ReplacePath(ast.NodeTransformer):
        def visit_Constant(self, node):
            if isinstance(node.value, str):
                node.value = translated_paths(node.value)
            return node
    spec = importlib.util.spec_from_file_location(f'drift{iteration}', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    tree = ReplacePath().visit(ast.parse(path.read_text(encoding='utf-8'), filename=str(path)))
    exec(compile(tree, str(path), 'exec'), module.__dict__)
    return module


def check_known_drift():
    """130 случаев с точечными ожиданиями; пути 105/107/109 адаптированы в памяти."""
    import importlib.util
    import platform
    out, count = [], 0
    for iteration, name in ((105, 'test_layout'), (107, 'test_policy'),
                            (108, 'test_cards'), (109, 'test_plan')):
        path = ROOT / f'research/{iteration}/{name}.py'
        try:
            if iteration in (105, 107, 109):
                module = load_path_adapted_test(iteration, path)
            else:
                spec = importlib.util.spec_from_file_location(f'drift{iteration}', path)
                module = importlib.util.module_from_spec(spec)
                sys.modules[f'drift{iteration}'] = module
                spec.loader.exec_module(module)
            cases = json.loads((ROOT / f'research/{iteration}/CASES.json').read_text(encoding='utf-8'))['cases']
            if iteration in (105, 107, 109):
                cases = translated_paths(cases)
            expected = current_cases(iteration, cases)
            count += len(cases)
            exception_ids = set()
            if iteration == 108:
                evidence = subprocess_evidence(path)
            elif iteration == 105:
                evidence = {'os': platform.system(), 'rows': [module.observe(store, case['id']) for case in cases]}
            elif iteration == 107:
                evidence = {'os': platform.system(), 'rows': [module.observe(store, case) for case in cases]}
            else:
                rows = []
                audit = module.Audit()
                for case in cases:
                    try:
                        row = module.observe(store, PlanSession, compile_prompt, audit, case)
                    except Exception as error:
                        # Только точная историческая ошибка и только у N17 допустимы.
                        if known_exception(case['id'], error):
                            exception_ids.add(case['id'])
                            continue
                        out.append(f'И-109 {case["id"]}: неожиданное исключение {type(error).__name__}: {error}')
                        continue
                    if case['id'] == 'N17-list':
                        out.append('И-109 N17-list: ожидаемое KeyError diff не возникло')
                        continue
                    rows.append(row)
                expected = [c for c in expected if c['id'] != 'N17-list']
                evidence = {'os': platform.system(), 'rows': rows}
            out.extend(f'И-{iteration} {issue}' for issue in compare_evidence(module, expected, evidence))
            historical = [c for c in cases if c['id'] not in exception_ids]
            observed_drift = {row['id'] for row in module.case_checks(historical, evidence)
                              if row['status'] != 'pass'} | exception_ids
            if observed_drift != set(KNOWN_DRIFT[iteration]):
                out.append(f'И-{iteration}: изменился состав исторических расхождений: '
                           f'новые={sorted(observed_drift - set(KNOWN_DRIFT[iteration]))}, '
                           f'исчезли={sorted(set(KNOWN_DRIFT[iteration]) - observed_drift)}')
        except Exception as error:
            out.append(f'И-{iteration}: сбой аудита {type(error).__name__}: {error}')
    return {'name': 'текущие ожидания случаев 105/107/108/109 (пути 105/107/109 адаптированы в памяти)',
            'cases': count, 'mismatches': out}


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
