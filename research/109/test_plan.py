#!/usr/bin/env python3
"""П2: проверка карточки/билета и единственной замены на физических фикстурах."""
from difflib import unified_diff
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import platform
import re
import sys
import tempfile
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'research/105'))
from test_layout import case_checks, changed, digests, encode, snapshot, under, write

PROFILE = 'profiles/pilot'
FILES = {'L0': 'kit/base/registry.json', 'L1': PROFILE + '/registry.json',
         'L2': '.agent-contract/project/registry.json'}
VERSION = '0.2.0-dev.109'
NEW = {'id': 'Q-109', 'kind': 'rule', 'authority': 'profile_owner', 'state': 'draft', 'parent': 'C-1',
       'scope': 'docs/guide', 'title': 'След диффа', 'text': 'Сохранить факты: без автоактивации. 🔎',
       'basis': 'Нужна проверка', 'criterion': 'Есть строка отчёта'}
TICKET = re.compile(r'[a-f0-9]{64}')
PLAN_ONLY = {'P01-dry-run', 'P03-no-change', 'P04-missing', 'N13-forged-card', 'N15-system',
             'N16-project', 'N17-list', 'N18-profile', 'N19-parent', 'N20-scope', 'N27-root-overlap', 'N28-kind'}


def entry(id_, owner, *, kind='contract', parent=None, scope='docs', text='Условия стенда.'):
    return {'id': id_, 'kind': kind, 'authority': owner, 'state': 'active', 'parent': parent,
            'scope': scope, 'title': id_, 'text': text, 'basis': 'Фикстура И-109', 'criterion': 'Сверить байты состояния.'}


def serialized_after(doc):
    registry = {**doc, 'revision': doc['revision'] + 1, 'entries': [*doc['entries'], NEW]}
    decision = {'operation': 'create', 'entry_id': NEW['id'], 'profile_revision': registry['revision'],
                'entry_sha256': sha256(json.dumps(NEW, sort_keys=True, ensure_ascii=True,
                                                  separators=(',', ':')).encode('ascii')).hexdigest()}
    container = {'profile_format': 1, 'registry': registry,
                 'journal': {'base_revision': doc['revision'], 'decisions': [decision]}}
    return (json.dumps(container, sort_keys=True, indent=2, ensure_ascii=False) + '\n').encode('utf-8')


def seed(work, i):
    docs = {
        'L0': {'roots': ['kit'], 'release_version': VERSION, 'entries': []},
        'L1': {'roots': [PROFILE], 'revision': 4, 'entries': [entry('C-1', 'profile_owner'),
               dict(entry('P-1', 'profile_owner', kind='rule', parent='C-1', text='Нужны свидетельства.'),
                    key='workflow.evidence', value='required')]},
        'L2': {'roots': ['.agent-contract'], 'revision': 7, 'entries': [entry('C-ext', 'project_owner', scope='.')]},
    }
    for area, file in FILES.items():
        docs[area].update(schema_version=2, area=area)
        write(work / file, docs[area])
    goal = serialized_after(docs['L1'])
    if i in ('P03-no-change', 'N14-no-change-apply'):
        (work / FILES['L1']).write_bytes(goal)
    if i == 'P01-dry-run':
        (work / FILES['L1']).write_bytes(encode(docs['L1']))  # Источник без последней LF.
    write(work / 'kit/base/manifest.json', {'fixture_only': True, 'release_version': VERSION})
    (work / 'notes.txt').write_bytes(b'Not read by the planner.\n')
    return goal


def phrase(*, profile='Pilot', area='L1', parent='C-1', scope='docs/guide', kind='правила'):
    where = f'в профиле {profile}' if area == 'L1' else 'в проекте'
    return (f'Создай черновик {kind} Q-109 {where}, по контракту {parent}, область «{scope}», '
            f'название «{NEW["title"]}», основание «{NEW["basis"]}», критерий «{NEW["criterion"]}»: «{NEW["text"]}»')


def card_input(compile_prompt, i):
    variants = {'N16-project': {'area': 'L2', 'parent': 'C-ext'}, 'N18-profile': {'profile': 'Other'},
                'N19-parent': {'parent': 'C-ext'}, 'N20-scope': {'scope': 'docs2/guide'},
                'N28-kind': {'kind': 'протокола'}}
    phrases = {'P04-missing': 'Зарегистрируй протокол в L1: Перед выводом сверяй свидетельства.',
               'N15-system': 'Создай черновик правила Q-109 в L0.', 'N17-list': 'Покажи действующие правила в проекте.'}
    card = compile_prompt(phrases.get(i, phrase(**variants.get(i, {}))))
    if i == 'N13-forged-card':
        card['params']['text'] = 'Подмена при прежней фразе.'
    return card


def hash_(raw):
    return sha256(raw).hexdigest()


def stamp(path):
    info = path.lstat()
    return info.st_dev, info.st_ino, info.st_mtime_ns, info.st_ctime_ns


class Audit:
    def __init__(self):
        self.active = False
        self.writes = False
        sys.addaudithook(self.record)

    def record(self, event, args):
        if not self.active:
            return
        if event == 'open' and args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            self.writes = True
        if event in ('os.rename', 'os.remove', 'os.mkdir', 'os.rmdir', 'os.link', 'os.symlink', 'os.chmod', 'os.truncate',
                     'tempfile.mkstemp', 'tempfile.mkdtemp'):
            self.writes = True

    def run(self, action):
        self.writes = False
        self.active = True
        try:
            return action()
        finally:
            self.active = False


def expected_preview(work, card, goal, *, no_change=False):
    file = FILES['L1']
    raw = (work / file).read_bytes()
    old, new = (5, 5) if no_change else (4, 5)
    # Независимо считаем ожидаемый контейнер и дифф по строкам, а не берём байты из порта.
    before, after = ([line.decode('utf-8') for line in BytesIO(x)] for x in (raw, goal))
    patch_text = ''.join(line if line.endswith('\n') else line + '\n\\ No newline at end of file\n'
                         for line in unified_diff(before, after, fromfile='a/' + file, tofile='b/' + file))
    return {'plan_format': 1, 'outcome': 'no_change' if no_change else 'planned', 'dry_run': True,
            'card': card, 'inputs_sha256': {a: hash_((work / rel).read_bytes()) for a, rel in FILES.items()},
            'diff': {'file': file, 'revision': {'from': old, 'to': new}, 'before_sha256': hash_(raw),
                     'after_sha256': hash_(goal), 'unified': patch_text}}


def ticket_ok(plan):
    t = plan.get('ticket')
    return type(t) is str and TICKET.fullmatch(t) is not None


def without_ticket(plan):
    return {k: v for k, v in plan.items() if k != 'ticket'}


def exact_preview(plan, expected):
    return (('ticket' in plan) == (expected['outcome'] == 'planned') and encode(without_ticket(plan)) == encode(expected))


def quiet_plan(session, card, work, goal, audit, *, no_change=False):
    saved, file_stamp = snapshot(work), stamp(work / FILES['L1'])
    expected = expected_preview(work, card, goal, no_change=no_change)
    plan = audit.run(lambda: session.plan(card))
    if (audit.writes or saved != snapshot(work) or file_stamp != stamp(work / FILES['L1'])
            or not exact_preview(plan, expected) or ticket_ok(plan) == no_change):
        raise AssertionError('Предварительный план не может менять файлы или расходиться с точным диффом П2')
    return plan


def plan_action(session, card, work, goal, i, witness):
    plan = session.plan(card)
    if i == 'P04-missing':
        return {'outcome': plan['outcome'], 'dry_run': plan['dry_run'],
                'missing': [row['field'] for row in plan['card']['missing']],
                'questions': [row['field'] for row in plan['card']['questions']],
                'exact_clarification': encode(plan) == encode({'plan_format': 1, 'outcome': 'missing_params',
                                                              'dry_run': True, 'card': card})}
    if i == 'P01-dry-run':
        witness['preview'] = without_ticket(plan)
    return {'outcome': plan['outcome'], 'dry_run': plan['dry_run'], 'valid_ticket': ticket_ok(plan),
            'exact_preview': exact_preview(plan, expected_preview(work, card, goal, no_change=i == 'P03-no-change')),
            'revision': plan['diff']['revision']}


def apply_action(session, card, work, goal, audit, i, layout, new_session):
    if i == 'N29-null-plan':
        return lambda: session.apply(None, confirmed_ticket='0' * 64)
    issued = quiet_plan(session, card, work, goal, audit, no_change=i == 'N14-no-change-apply')
    # Отдельный аргумент имитирует ответ тестового владельца, не даёт полномочий.
    token = issued.get('ticket')
    plan = json.loads(encode(issued))
    kwargs = {'confirmed_ticket': token}
    if i == 'N01-no-confirmation':
        kwargs = {}
    elif i == 'N02-false-confirmation':
        kwargs['confirmed_ticket'] = False
    elif i in ('N03-wrong-confirmation', 'N05-fabricated-ticket', 'N14-no-change-apply'):
        different = '0' * 64 if token != '0' * 64 else '1' * 64
        kwargs['confirmed_ticket'] = different
        if i == 'N05-fabricated-ticket':
            plan['ticket'] = different
    elif i == 'N04-ticket-removed':
        del plan['ticket']
    elif i == 'N06-foreign-session':
        session = new_session(layout, profile_id='Pilot')
    elif i == 'N07-replay':
        # Подготовка состояния до замера повтора: прежнее подтверждение уже принято.
        result = session.apply(plan, **kwargs)
        if result['outcome'] != 'applied' or (work / FILES['L1']).read_bytes() != goal:
            raise AssertionError('Сначала нужно действительно использовать билет')
    elif i == 'N08-superseded':
        newer = quiet_plan(session, card, work, goal, audit)
        if newer['ticket'] == token:
            raise AssertionError('Новый дифф должен получить новое ожидание согласия')
    elif i == 'N09-diff-edited':
        issued['diff']['unified'] += '\nПодмена показанного диффа.\n'
        plan = issued  # Мутация именно объекта, выданного вызывающему коду.
    elif i == 'N10-card-edited':
        plan['card']['request'] += ' Подмена.'
    elif i == 'N11-path-edited':
        plan['diff']['file'] = FILES['L0']
    elif i == 'N12-boolean-format':
        plan['plan_format'] = True  # Python считает True == 1; JSON не считает.
    elif i == 'P05-unread-note':
        (work / 'notes.txt').write_bytes(b'Changed between preview and approval; not an input.\n')
    elif i in ('N22-stale-L1', 'N24-stale-L0'):
        path = work / FILES[i[-2:]]
        path.write_bytes(path.read_bytes() + b'\n')
    elif i in ('N21-stale-revision', 'N23-stale-L2', 'N25-conflict'):
        path = work / FILES['L1' if i == 'N21-stale-revision' else 'L2']
        doc = json.loads(path.read_bytes())
        doc['revision'] += 1
        if i == 'N25-conflict':
            doc['entries'].append(dict(entry('Q-other', 'project_owner', kind='rule', parent='C-ext',
                                             scope='docs/guide', text='Свидетельства пропустить.'),
                                       key='workflow.evidence', value='skip'))
        write(path, doc)
    return lambda: session.apply(plan, **kwargs)


def apply_result(action, store, work, layout, goal):
    result = action()
    if result['outcome'] != 'applied':
        return {'outcome': result['outcome']}
    saved = (work / FILES['L1']).read_bytes()
    profile = json.loads(saved)
    seen = store.status(layout)
    journal = store.profile_history(layout)
    return {'outcome': result['outcome'], 'profile_revision': seen['profile_revision'], 'project_revision': seen['project_revision'],
            'entry_id': profile['registry']['entries'][-1]['id'], 'decisions': len(journal['decisions']),
            'exact_saved_bytes': saved == goal, 'exact_status': encode(result) == encode({'outcome': 'applied', 'status': seen})
            and seen['release_version'] == VERSION, 'journal_verified': encode(journal) == encode(json.loads(goal)['journal'])}


def observe(store, session_class, compiler, audit, case):
    i = case['id']
    with tempfile.TemporaryDirectory(prefix='ack-i109-work-') as tmp:
        work = Path(tmp).resolve()
        goal = seed(work, i)
        layout = store.Layout(work, 'kit/pilot' if i == 'N27-root-overlap' else PROFILE)
        session = session_class(layout, profile_id='Pilot')
        card = card_input(compiler, i)
        witness = {}
        if i in PLAN_ONLY:
            def action():
                return plan_action(session, card, work, goal, i, witness)
        else:
            apply = apply_action(session, card, work, goal, audit, i, layout, session_class)

            def action():
                return apply_result(apply, store, work, layout, goal)

        before = snapshot(work)
        profile = work / FILES['L1']
        profile_stamp = stamp(profile)
        fixed = ('kit', '.agent-contract')
        protected = {rel: stamp(work / rel) for root in fixed for rel, obj in under(before, root).items() if obj[0] == 'file'}
        real_replace = os.replace
        trace = []

        def inspect(src, dst):
            src, dst = Path(src), Path(dst)
            trace.append(dst == profile and src != dst and src.parent == dst.parent and src.read_bytes() == goal)
            if i == 'N26-replace-failed':
                raise PermissionError('synthetic replace refusal')
            real_replace(src, dst)

        with patch.object(store.os, 'replace', side_effect=inspect):
            try:
                actual = {'ok': True, **audit.run(action)}
            except store.StoreError as error:
                actual = {'ok': False, 'error': error.diagnostic()}
        after = snapshot(work)
        actual.update(changed=changed(before, after), profile_untouched=stamp(profile) == profile_stamp,
                      l0_l2_unchanged=all(under(before, root) == under(after, root) for root in fixed)
                      and all(stamp(work / rel) == old for rel, old in protected.items()),
                      write_event=audit.writes, replacements=len(trace), staged_matches_preview=bool(trace) and all(trace))
        return {'id': i, 'observed': actual, 'digest': {'before': digests(before, PROFILE), 'after': digests(after, PROFILE)},
                **witness}


def main():
    sys.path.insert(0, str(ROOT))
    from kit.base import registry_store
    from kit.base.operation_card import compile_prompt
    from kit.base.operation_plan import PlanSession

    book = json.loads((HERE / 'CASES.json').read_bytes())
    cases = book['cases']
    if encode(book['format']) != b'1' or not cases or len({r['id'] for r in cases}) != len(cases):
        raise ValueError('Некорректный корпус П2')
    audit = Audit()
    evidence = {'os': platform.system(), 'rows': [observe(registry_store, PlanSession, compile_prompt, audit, c) for c in cases]}
    print(json.dumps(evidence, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if all(r['status'] == 'pass' for r in case_checks(cases, evidence)) else 1


if __name__ == '__main__':
    raise SystemExit(main())
