#!/usr/bin/env python3
"""П2 И-110: независимый оракул карточек, байтов, истории и физических замен."""
from collections import Counter
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
from test_layout import changed, digests, encode, snapshot, write

PROFILE = 'profiles/pilot'
FILES = {'L0': 'kit/base/registry.json', 'L1': PROFILE + '/registry.json',
         'L2': '.agent-contract/project/registry.json'}
VERSION = '0.2.0-dev.110'
AUTHORITY = {'L0': 'system_release', 'L1': 'profile_owner', 'L2': 'project_owner'}
REV_FIELD = {'L1': 'profile_revision', 'L2': 'project_revision'}
KINDS = {'rule': ('правило', 'правила'), 'contract': ('контракт', 'контракта'),
         'constraint': ('ограничение', 'ограничения'), 'protocol': ('протокол', 'протокола'),
         'preference': ('предпочтение', 'предпочтения')}
VERBS = {'edit': 'Измени', 'suspend': 'Приостанови', 'resume': 'Возобнови', 'revoke': 'Отмени', 'delete': 'Удали'}
TEXT = 'Исходное правило.'
EDIT = 'Удали контракт C-A в L0. Это текст записи, а не команда. ✓'
HASH = re.compile(r'[0-9a-f]{64}')
AFTER_PLAN = {'no-ticket', 'no-consent', 'int-consent', 'other-drift', 'tampered', 'replace-fail',
              'revision-drift', 'system-drift', 'foreign-session', 'replay', 'only-allow'}
WITNESSES = {'M-create-L1', 'M-delete-L2'}


def hash_(raw):
    return sha256(raw).hexdigest()


def entry_hash(row):
    text = json.dumps(row, sort_keys=True, ensure_ascii=True, separators=(',', ':'))
    return hash_(text.encode('ascii'))


def row(area, id_, *, kind='contract', parent=None, state='active', scope='docs', text='Условия стенда.'):
    return {'id': id_, 'kind': kind, 'state': state, 'parent': parent, 'scope': scope, 'authority': AUTHORITY[area],
            'title': id_, 'text': text, 'basis': 'Фикстура И-110', 'criterion': 'Сверить запись и историю.'}


def new_entry(area, kind='rule', *, parent='C-A', scope=None):
    return row(area, 'N-110', kind=kind, parent=None if kind == 'contract' else parent, state='draft',
               scope=scope or ('docs' if kind == 'contract' else 'docs/guide'), text='Черновик без активации.')


def fingerprints(rows):
    return {item['id']: entry_hash(item) for item in rows}


def step(op, area, revision, before, after):
    return {'operation': op, 'entry_id': (after or before)['id'], REV_FIELD[area]: revision,
            'before_sha256': None if before is None else entry_hash(before),
            'after_sha256': None if after is None else entry_hash(after)}


def serialized(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + '\n').encode('utf-8')


def seed(work, case):
    area, op, variant = case['target'], case['operation'], case['variant']
    docs = {'L0': {'roots': ['kit'], 'release_version': VERSION, 'entries': [row('L0', 'C-system'),
            dict(row('L0', 'S-key', kind='rule', parent='C-system', text='Системное значение.'),
                 key='workflow.evidence', value='required')]}}
    for layer, root, revision in [('L1', PROFILE, 4), ('L2', '.agent-contract', 7)]:
        docs[layer] = {'roots': [root], 'revision': revision, 'entries': [row(layer, 'C-A'),
                      row(layer, 'R-A', kind='rule', parent='C-A', scope='docs/guide', text=TEXT),
                      row(layer, 'C-off', state='suspended'),
                      row(layer, 'R-hidden', kind='rule', parent='C-off', scope='docs/guide', text='Не показывать.') ]}
    for layer, doc in docs.items():
        doc.update(schema_version=2, area=layer)
    doc = docs[area]
    journal = None
    if area != 'L0':
        contract, rule, *_ = doc['entries']
        rule['state'] = {'resume': 'suspended', 'delete': 'revoked'}.get(op, 'active')
        if variant in ('active', 'draft', 'revoked', 'legacy', 'already-revoked', 'already-active', 'already-suspended'):
            rule['state'] = 'draft' if variant == 'legacy' else variant.removeprefix('already-')
        if variant == 'contract-with-child':
            contract['state'] = 'revoked'
        if variant == 'parent-inactive':
            contract['state'] = 'suspended'
        if variant == 'foreign-only':
            doc['entries'].remove(rule)  # R-A присутствует только в L1.
        if variant == 'parent-foreign':
            docs['L2']['entries'].append(row('L2', 'C-external'))
        if variant == 'prospective':
            rule.update(key='workflow.evidence', value='skip')
        if variant in ('same-entry', 'occupied'):
            item = new_entry(area)
            if variant == 'occupied':
                item['text'] = 'Уже занято.'
            doc['entries'].append(item)
        if variant == 'legacy':
            doc['entries'].remove(rule)
            doc['entries'].append(rule)
            journal = {'base_revision': 3, 'decisions': [{'operation': 'create', 'entry_id': 'R-A',
                        'profile_revision': 4, 'entry_sha256': entry_hash(rule)}]}
        if variant in ('bad-history', 'bad-chain', 'retired'):
            revision = doc['revision']
            prior = dict(rule, text='До изменения.')
            if variant == 'retired':
                prior = dict(new_entry(area), state='revoked')
                initial = [*doc['entries'], prior]
                decision = step('delete', area, revision, prior, None)
            else:
                initial = [prior if e['id'] == 'R-A' else e for e in doc['entries']]
                decision = step('edit', area, revision, prior, rule)
                decision['after_sha256' if variant == 'bad-history' else 'before_sha256'] = '0' * 64
            journal = {'base_revision': revision - 1, 'base_entries': fingerprints(initial), 'decisions': [decision]}
    for layer, rel in FILES.items():
        file = work / rel
        file.parent.mkdir(parents=True, exist_ok=True)
        value = docs[layer]
        if layer == area and journal is not None:
            tag = {'registry_format': 2} if 'base_entries' in journal else {'profile_format': 1}
            value = {**tag, 'registry': value, 'journal': journal}
        file.write_bytes(encode(value))  # Оракул диффа должен показать отсутствие последней LF.
    write(work / 'kit/base/manifest.json', {'fixture_only': True, 'release_version': VERSION})
    (work / PROFILE / 'profile-note.txt').write_bytes(b'Unrelated profile data.\n')
    (work / '.agent-contract/project/notes.txt').write_bytes(b'Unrelated project data.\n')
    return docs, journal


def phrase(op, area, variant=''):
    where = {'L0': 'в L0', 'L1': 'в профиле Other' if variant == 'wrong-profile' else 'в профиле Pilot',
             'L2': 'в проекте'}[area]
    if variant == 'missing':
        return 'Зарегистрируй протокол в L1: Перед выводом сверяй свидетельства.'
    if op == 'list':
        return f'Покажи только текст правила R-A {where}.' if variant == 'text' else f'Покажи действующие правила {where}.'
    if op == 'create':
        kind = variant if variant in KINDS else 'rule'
        item = new_entry(area, kind, parent='C-external' if variant == 'parent-foreign' else 'C-A',
                         scope='docs2/guide' if variant == 'scope-outside' else None)
        parent = '' if item['parent'] is None else f', по контракту {item["parent"]}'
        return (f'Зарегистрируй черновик {KINDS[kind][1]} N-110 {where}{parent}, '
                f'область «{item["scope"]}», название «{item["title"]}», основание «{item["basis"]}», '
                f'критерий «{item["criterion"]}»: «{item["text"]}»')
    name = {'kind-mismatch': 'протокол R-A', 'contract-with-child': 'контракт C-A'}.get(variant, 'правило R-A')
    suffix = f': «{TEXT if variant == "same-text" else EDIT}»' if op == 'edit' else '.'
    return f'{VERBS[op]} {name} {where}{suffix}'


def expected_write(doc, journal, operation, variant):
    """Оракул шага для положительных фикстур и точного плана перед отрицательным apply."""
    area, revision = doc['area'], doc['revision'] + 1
    entries = doc['entries']
    if operation == 'create':
        prior = None
        after = new_entry(area, variant if variant in KINDS else 'rule')
        rows = [*entries, after]
    else:
        prior = next(r for r in entries if r['id'] == 'R-A')
        if operation == 'delete':
            after = None
        elif operation == 'edit':
            after = {**prior, 'text': EDIT}
        else:
            after = {**prior, 'state': {'suspend': 'suspended', 'resume': 'active', 'revoke': 'revoked'}[operation]}
        rows = [after if r is prior else r for r in entries if r is not prior or after is not None]
    registry = {**doc, 'revision': revision, 'entries': rows}
    old_decisions = [] if journal is None else journal['decisions']
    base = doc['revision'] if journal is None else journal['base_revision']
    if area == 'L1' and operation == 'create' and after['kind'] == 'rule' and (journal is None or 'base_entries' not in journal):
        tag = {'profile_format': 1}
        history = {'base_revision': base, 'decisions': [*old_decisions,
                   {'operation': 'create', 'entry_id': after['id'], 'profile_revision': revision,
                    'entry_sha256': entry_hash(after)}]}
    else:
        tag = {'registry_format': 2}
        if journal is None:
            anchor = fingerprints(entries)
        elif 'base_entries' in journal:
            anchor = journal['base_entries']
        else:
            anchor = fingerprints(entries[:len(entries) - len(old_decisions)])
            old_decisions = [{'operation': 'create', 'entry_id': d['entry_id'], 'profile_revision': d['profile_revision'],
                              'before_sha256': None, 'after_sha256': d['entry_sha256']} for d in old_decisions]
        history = {'base_revision': base, 'base_entries': anchor,
                   'decisions': [*old_decisions, step(operation, area, revision, prior, after)]}
    container = {**tag, 'registry': registry, 'journal': history}
    return container, (after or prior)['id']


def stamp(path):
    st = path.lstat()
    return st.st_dev, st.st_ino, st.st_mtime_ns, st.st_ctime_ns


def file_stamps(work, tree):
    return {p: stamp(work / p) for p, item in tree.items() if item[0] == 'file'}


class Audit:
    def __init__(self):
        self.active = False
        sys.addaudithook(self.record)

    def record(self, event, args):
        if not self.active:
            return
        if event == 'open':
            if args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
                self.writes = True
            else:
                self.reads += 1
        if event in ('os.listdir', 'os.scandir'):
            self.reads += 1
        if event in ('os.rename', 'os.remove', 'os.mkdir', 'os.rmdir', 'os.link', 'os.symlink', 'os.chmod',
                     'os.truncate', 'tempfile.mkstemp', 'tempfile.mkdtemp'):
            self.writes = True

    def run(self, fn):
        self.writes, self.reads, self.active = False, 0, True
        try:
            return fn()
        finally:
            self.active = False


def exact(a, b):
    return encode(a) == encode(b)


def redacted(plan):
    return {k: v for k, v in plan.items() if k != 'ticket'}


def expected_plan(card, work, area, revision, goal, *, no_change=False):
    rel = FILES[area]
    inputs = {a: (work / p).read_bytes() for a, p in FILES.items()}
    before = inputs[area]
    a, b = ([line.decode('utf-8') for line in BytesIO(raw)] for raw in (before, goal))
    diff = ''.join(line if line.endswith('\n') else line + '\n\\ No newline at end of file\n'
                   for line in unified_diff(a, b, fromfile='a/' + rel, tofile='b/' + rel))
    return {'plan_format': 1, 'dry_run': True, 'outcome': 'no_change' if no_change else 'planned', 'card': card,
            'inputs_sha256': {a: hash_(raw) for a, raw in inputs.items()},
            'diff': {'file': rel, 'revision': {'from': revision, 'to': revision + int(not no_change)},
                     'before_sha256': hash_(before), 'after_sha256': hash_(goal), 'unified': diff}}


def issue(session, card, work, area, revision, goal, audit):
    before = snapshot(work)
    stamps = file_stamps(work, before)
    expected = expected_plan(card, work, area, revision, goal)
    plan = audit.run(lambda: session.plan(card))
    if (audit.writes or snapshot(work) != before or file_stamps(work, before) != stamps
            or not exact(redacted(plan), expected) or type(plan.get('ticket')) is not str or not HASH.fullmatch(plan['ticket'])):
        raise AssertionError('Нет точного плана с билетом до записи')
    return plan


def observation(store, work, area, audit, action, goal=None, *, replace_fail=False):
    before = snapshot(work)
    stamps = file_stamps(work, before)
    rel = FILES[area]
    real_replace, trace = os.replace, []

    def inspect(src, dst):
        src, dst = Path(src), Path(dst)
        trace.append(dst == work / rel and src != dst and src.parent == dst.parent and src.read_bytes() == goal)
        if replace_fail:
            raise PermissionError('synthetic replace refusal')
        real_replace(src, dst)

    with patch.object(os, 'replace', side_effect=inspect):
        try:
            result = {'ok': True, **audit.run(action)}
        except store.StoreError as error:
            result = {'ok': False, 'error': error.diagnostic()}
    after = snapshot(work)
    post = file_stamps(work, after)
    paths = changed(before, after)
    result.update(changed=paths, registry_untouched=stamps.get(rel) == post.get(rel),
                  other_unchanged=all(p == rel for p in paths) and all(post.get(p) == s for p, s in stamps.items() if p != rel),
                  write_event=audit.writes, replacements=len(trace), prepared_exact=bool(trace) and all(trace))
    return {'observed': result, 'digest': {'before': digests(before, PROFILE), 'after': digests(after, PROFILE)}}


def list_result(plan, card, doc, variant):
    entry = next(row for row in doc['entries'] if row['id'] == 'R-A')
    fields = ('id', 'text') if variant == 'text' else ('id', 'kind', 'state', 'parent', 'scope', 'title')
    data = {'target': doc['area'], 'revision': doc['revision'], 'entries': [{field: entry[field] for field in fields}]}
    expected = {'plan_format': 1, 'dry_run': True, 'card': card, 'outcome': 'listed', 'result': data}
    rows = plan.get('result', {}).get('entries', [])
    return {'outcome': plan['outcome'], 'ids': [r['id'] for r in rows], 'text_view': any('text' in r for r in rows),
            'exact_list': exact(plan, expected)}


def committed(store, layout, work, area, doc, expected, entry_id, apply):
    result = apply()
    if result['outcome'] != 'applied':
        return {'outcome': result['outcome']}
    status = {'schema_version': 2, 'release_version': VERSION, 'profile_root': PROFILE,
              'profile_revision': 4, 'project_revision': 7}
    status[REV_FIELD[area]] = expected['registry']['revision']
    again = store.Layout(work, PROFILE)
    history = store.registry_history(again, target=area)
    registry = store.read_registry(again, target=area)
    item = next((r for r in registry['entries'] if r['id'] == entry_id), None)
    label = 'registry:2' if 'registry_format' in expected else 'profile:1'
    return {'outcome': result['outcome'], 'entry_id': entry_id, 'entry_state': None if item is None else item['state'],
            'entry_kind': None if item is None else item['kind'], 'revision': [doc['revision'], registry['revision']],
            'history': [r['operation'] for r in history['decisions']], 'format': label,
            'exact_file': (work / FILES[area]).read_bytes() == serialized(expected) and exact(registry, expected['registry']),
            'exact_diff': True,  # issue() сверяет полный показанный JSON, а observation() — подготовленные байты.
            'exact_history': exact(history, expected['journal']) and (area == 'L2' or exact(store.profile_history(layout), history)),
            'exact_status': exact(result, {'outcome': 'applied', 'status': status}) and exact(store.status(again), status)}


def chain(store, session, compile_prompt, layout, work, doc, journal, audit):
    area = doc['area']
    ops = ['edit', 'revoke', 'delete', 'create'] if area == 'L1' else ['edit', 'suspend', 'resume', 'revoke', 'delete', 'create']
    rows, initial = [], doc['revision']
    for op in ops:
        expected, entry_id = expected_write(doc, journal, op, '')
        card = compile_prompt(phrase(op, area))
        goal = serialized(expected)
        plan = issue(session, card, work, area, doc['revision'], goal, audit)
        token = plan['ticket']  # Синтетический ответ на этот показанный дифф.
        measured = observation(store, work, area, audit, lambda: committed(
            store, layout, work, area, doc, expected, entry_id,
            lambda: session.apply(plan, confirmed_ticket=token, allow_delete=op == 'delete')), goal)
        seen = measured['observed']
        if (seen.get('outcome') != 'applied' or not all(seen.get(k) is True for k in (
                'exact_file', 'exact_history', 'exact_diff', 'exact_status', 'other_unchanged', 'write_event', 'prepared_exact'))
                or seen['registry_untouched'] is not False or seen['replacements'] != 1 or seen['changed'] != [FILES[area]]):
            return measured
        rows.append(measured)
        doc, journal = expected['registry'], expected['journal']
    return {'observed': {'ok': True, 'outcome': 'applied_chain', 'operations': ops, 'revision': [initial, doc['revision']],
            'history': rows[-1]['observed']['history'], 'exact_steps': True, 'changed': [FILES[area]],
            'other_unchanged': True, 'registry_untouched': False, 'write_event': True,
            'replacements': sum(r['observed']['replacements'] for r in rows), 'prepared_exact': True},
            'digest': {'before': rows[0]['digest']['before'], 'after': rows[-1]['digest']['after']}}


def observe(store, session_class, compile_prompt, audit, case):
    op, area, variant = case['operation'], case['target'], case['variant']
    with tempfile.TemporaryDirectory(prefix='ack-i110-work-') as tmp:
        work = Path(tmp).resolve()
        docs, journal = seed(work, case)
        doc = docs[area]
        layout = store.Layout(work, 'kit/pilot' if variant == 'overlap' else PROFILE)
        session = session_class(layout, profile_id='Pilot')
        if op == 'chain':
            return chain(store, session, compile_prompt, layout, work, doc, journal, audit)
        card = audit.run(lambda: compile_prompt(phrase(op, area, variant)))
        if audit.writes or audit.reads:
            raise AssertionError('Карточка не обращается к файлам')
        if variant == 'forged':
            card['params']['authority'] = 'system_release'
        result = case['expected'].get('outcome')
        if result == 'missing_params':
            def clarify():
                plan = session.plan(card)
                return {'outcome': plan['outcome'], 'read_events': audit.reads,
                        'missing': [r['field'] for r in plan['card']['missing']],
                        'questions': [r['field'] for r in plan['card']['questions']],
                        'exact_clarification': exact(plan, {'plan_format': 1, 'dry_run': True, 'card': card,
                                                            'outcome': 'missing_params'})}
            return observation(store, work, area, audit, clarify)
        if result == 'no_change':
            raw = (work / FILES[area]).read_bytes()
            expected = expected_plan(card, work, area, doc['revision'], raw, no_change=True)

            def unchanged():
                plan = session.plan(card)
                revision = plan.get('diff', {}).get('revision', {})
                return {'outcome': plan['outcome'], 'revision': [revision.get(k) for k in ('from', 'to')],
                        'exact_no_change': exact(plan, expected)}
            return observation(store, work, area, audit, unchanged)
        if result == 'listed':
            return observation(store, work, area, audit, lambda: list_result(session.plan(card), card, doc, variant))
        if result != 'applied' and variant not in AFTER_PLAN:
            return observation(store, work, area, audit, lambda: session.plan(card))

        expected, entry_id = expected_write(doc, journal, op, variant)
        goal = serialized(expected)
        issued = issue(session, card, work, area, doc['revision'], goal, audit)
        token = issued['ticket']
        plan = json.loads(encode(issued))
        kwargs = {'confirmed_ticket': token}
        if op == 'delete':
            kwargs['allow_delete'] = True
        if variant in ('no-ticket', 'only-allow'):
            del kwargs['confirmed_ticket']
        elif variant == 'no-consent':
            del kwargs['allow_delete']
        elif variant == 'int-consent':
            kwargs['allow_delete'] = 1
        elif variant in ('other-drift', 'system-drift'):
            changed_file = work / FILES['L0' if variant == 'system-drift' else 'L2']
            changed_file.write_bytes(changed_file.read_bytes() + b'\n')
        elif variant == 'revision-drift':
            write(work / FILES[area], {**doc, 'revision': doc['revision'] + 1})
        elif variant == 'tampered':
            plan['diff']['file'] = FILES['L1']
        elif variant == 'foreign-session':
            session = session_class(layout, profile_id='Pilot')
        elif variant == 'replay':
            if session.apply(plan, **kwargs).get('outcome') != 'applied' or (work / FILES[area]).read_bytes() != goal:
                raise AssertionError('Перед повтором удаление должно действительно исполниться')

        def apply():
            return session.apply(plan, **kwargs)

        if result == 'applied':
            measured = observation(store, work, area, audit, lambda: committed(
                store, layout, work, area, doc, expected, entry_id, apply), goal)
        else:
            measured = observation(store, work, area, audit, apply, goal, replace_fail=variant == 'replace-fail')
        if case['id'] in WITNESSES:
            measured['preview'] = redacted(issued)
        return measured


def case_checks(cases, result):
    rows = result.get('rows') if type(result) is dict else None
    if type(rows) is not list or any(type(r) is not dict or type(r.get('id')) is not str for r in rows):
        rows = []
    seen = Counter(r['id'] for r in rows)
    by_id = {r['id']: r for r in rows}
    checks = []
    for case in cases:
        i, area, expected = case['id'], case['target'], case['expected']
        issue = 'missing' if not seen[i] else 'duplicate' if seen[i] != 1 else None
        if issue is None:
            row = by_id[i]
            digest = row.get('digest')
            if not exact(row.get('observed'), expected):
                issue = 'observation_mismatch'
            elif (type(digest) is not dict or digest.keys() != {'before', 'after'}
                  or any(type(d) is not dict or d.keys() != {'L0', 'L1', 'L2', 'L0_manifest'}
                         or any(type(h) is not str or not HASH.fullmatch(h) for h in d.values()) for d in digest.values())):
                issue = 'missing_digest'
            elif {k for k in digest['before'] if digest['before'][k] != digest['after'][k]} != ({area} if expected['changed'] else set()):
                issue = 'digest_mismatch'
        checks.append({'id': i, 'status': 'pass' if issue is None else 'fail', 'issue': issue})
    checks.extend({'id': i, 'status': 'fail', 'issue': 'unexpected'} for i in sorted(seen.keys() - {c['id'] for c in cases}))
    return checks


def main():
    sys.path.insert(0, str(ROOT))
    from kit.base import registry_store
    from kit.base.operation_card import compile_prompt
    from kit.base.operation_plan import PlanSession

    book = json.loads((HERE / 'CASES.json').read_bytes())
    cases = book['cases']
    if encode(book['format']) != b'1' or not cases or len({r['id'] for r in cases}) != len(cases):
        raise ValueError('Некорректный корпус П2')
    audit, rows = Audit(), []
    for case in cases:
        try:
            result = observe(registry_store, PlanSession, compile_prompt, audit, case)
        except (AssertionError, AttributeError, KeyError, TypeError, registry_store.StoreError) as error:
            result = {'setup_error': error.diagnostic() if isinstance(error, registry_store.StoreError) else str(error)}
        rows.append({'id': case['id'], **result})
    evidence = {'os': platform.system(), 'rows': rows}
    print(json.dumps(evidence, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if all(r['status'] == 'pass' for r in case_checks(cases, evidence)) else 1


if __name__ == '__main__':
    raise SystemExit(main())
