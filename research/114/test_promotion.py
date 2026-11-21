#!/usr/bin/env python3
"""Замороженный оракул И-114: реальный временный файл, без тел записей и билетов в результатах."""
from collections import Counter
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import platform
import re
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
from kit.base import registry_journal, registry_policy, registry_store, schema_v2

MODULE = 'kit/base/promotion.py'
PROFILE_ROOT = 'profiles/staged'
PROFILE_FILE = PROFILE_ROOT + '/registry.json'
STAGE_NAME = 'registry.json'
SOURCE_ID = 'L2-fixture-subject-114'
SOURCE_TITLE = 'ORIGINAL_TITLE_ONLY_114'
BODY_MARKER = 'SOURCE_MATERIAL_ONLY_114'
LITERAL = 'SYNTHETIC_ONLY_114_NOT_A_KEY'
PRIVATE_EXISTING = 'OTHER_ENTRY_ONLY_114'
TICKET_PATTERN = re.compile('[a-f0-9]{64}')
REFUSALS = {
    ('promote_unverified', 'target'), ('promote_unverified', 'confirmation'), ('promote_unverified', 'plan'),
    ('project_specific', 'proposal'), ('promote_conflict', 'entry'), ('promote_conflict', 'entries'),
    ('parent', 'proposal'), ('invalid_entry', 'source'), ('invalid_entry', 'proposal'),
    ('invalid_context', 'context'), ('invalid_profile', 'staged_profile'), ('write_failed', 'stage'),
}
MARKERS = {
    ('text', 'machine', 'known_machine'), ('text', 'path', 'posix_local'),
    ('text', 'project_name', 'known_project'), ('text', 'secret', 'credential_assignment'),
    ('scope', 'path', 'project_prefix'), ('title', 'project_name', 'known_project'),
    ('basis', 'path', 'posix_local'), ('value', 'secret', 'credential_value'),
}


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def digest(raw):
    return sha256(raw).hexdigest()


def entry_hash(row):
    return digest(canonical(row))


def row(id_, kind, authority, *, parent=None, scope='.', state='active', text='Синтетическое условие стенда.'):
    return {'id': id_, 'kind': kind, 'parent': parent, 'scope': scope, 'state': state, 'authority': authority,
            'title': 'Контрольная запись', 'text': text, 'basis': 'Фикстура И‑114', 'criterion': 'Сверить форму.'}


def doc(area, root, entries, *, revision=3, version='0.2.0-dev.114'):
    value = {'area': area, 'schema_version': 2, 'roots': [root], 'entries': entries}
    return dict(value, release_version=version) if area == 'L0' else dict(value, revision=revision)


def source_entry(kind):
    return dict(row(SOURCE_ID, kind, 'project_owner', scope='tenant-fixture/docs',
                    parent=None if kind == 'contract' else 'C-source',
                    text=f'Сверь основание: cedar-fixture host-fixture /home/fixture-only/check; api_key={LITERAL}; {BODY_MARKER}'),
                title=SOURCE_TITLE)


def source_doc(entry):
    return doc('L2', '.agent-contract', [row('C-source', 'contract', 'project_owner', scope='tenant-fixture'), entry], revision=8)


def editable(kind, driver):
    proposal = {'id': 'L1-new-draft-114', 'parent': None if kind == 'contract' else 'C-lab',
                'scope': 'docs/main', 'title': 'Сверка основания', 'text': 'Проверь основание, затем укажи результат.',
                'basis': 'Явная переносимая редакция', 'criterion': 'Основание и результат различимы.'}
    if driver in ('same_value', 'disjoint_value', 'key_conflict'):
        proposal.update(key='format.mode', value='checked' if driver == 'same_value' else 'separate')
        if driver == 'disjoint_value':
            proposal['scope'] = 'docs/alternate'
    if driver == 'variable':
        proposal['criterion'] = 'Сверь ссылку token=<API_KEY> без чтения значения.'
    return proposal


def profile_fixture(proposal, kind, driver):
    anchor = row('C-lab', 'contract', 'profile_owner', scope='docs')
    existing = [anchor]
    if driver in ('same_value', 'disjoint_value', 'key_conflict', 'parent_kind'):
        existing.append(dict(row('R-existing', 'rule', 'profile_owner', parent='C-lab', scope='docs/main',
                                 text=PRIVATE_EXISTING), key='format.mode', value='checked'))
    if driver == 'occupied':
        existing.append(dict(proposal, kind=kind, state='draft', authority='profile_owner'))
    root = 'profiles/working' if driver == 'bad_root' else PROFILE_ROOT
    registry = doc('L1', root, existing)
    fingerprints = {e['id']: entry_hash(e) for e in existing}
    raw, decisions = registry, []
    if driver in ('known_history', 'bad_history'):
        old = row('R-known', 'rule', 'profile_owner', parent='C-lab', scope='docs/main', state='draft')
        registry = dict(registry, entries=[*existing, old], revision=4)
        d = entry_hash(old)
        raw = {'profile_format': 1, 'registry': registry,
               'journal': {'base_revision': 3, 'decisions': [{'operation': 'create', 'entry_id': old['id'],
                                                              'profile_revision': 4,
                                                              'entry_sha256': '0' * 64 if driver == 'bad_history' else d}]}}
        decisions = [{'operation': 'create', 'entry_id': old['id'], 'profile_revision': 4,
                      'before_sha256': None, 'after_sha256': d}]
    elif driver == 'retired':
        entry_id = proposal['id']
        d = entry_hash(dict(proposal, kind=kind, state='revoked', authority='profile_owner'))
        registry = dict(registry, revision=4)
        fingerprints[entry_id] = d
        decisions = [{'operation': 'delete', 'entry_id': entry_id, 'profile_revision': 4, 'before_sha256': d, 'after_sha256': None}]
        raw = {'registry_format': 2, 'registry': registry,
               'journal': {'base_revision': 3, 'base_entries': fingerprints, 'decisions': decisions}}
    return canonical(raw) + b'\n', registry, fingerprints, decisions


def expected_file(candidate, registry, fingerprints, decisions):
    updated = dict(registry, entries=[*registry['entries'], candidate], revision=registry['revision'] + 1)
    decision = {'operation': 'create', 'entry_id': candidate['id'], 'profile_revision': updated['revision'],
                'before_sha256': None, 'after_sha256': entry_hash(candidate)}
    packed = {'registry_format': 2, 'registry': updated,
              'journal': {'base_revision': 3, 'base_entries': fingerprints, 'decisions': [*decisions, decision]}}
    return canonical(packed) + b'\n', packed, decision


def payload_file(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if type(data) is bytes else canonical(data) + b'\n')


def workspace(base, name, project):
    l0 = doc('L0', 'kit', [row(f'C-system-{name}', 'contract', 'system_release')], version=f'0.2.0-dev.{name}')
    l1 = doc('L1', PROFILE_ROOT, [row(f'C-existing-{name}', 'contract', 'profile_owner')])
    schema_v2.validate_catalog({'L0': l0, 'L1': l1, 'L2': project})
    for path, value in (('kit/base/registry.json', l0), (PROFILE_FILE, l1), ('.agent-contract/project/registry.json', project)):
        payload_file(base / path, value)
    payload_file(base / 'fixture.txt', f'Independent synthetic project {name}\n'.encode('ascii'))
    return registry_store.Layout(base, PROFILE_ROOT)


def file_tree(directory, *, except_path=None):
    return {p.relative_to(directory).as_posix(): (p.stat().st_ino, p.stat().st_mtime_ns, p.read_bytes())
            for p in sorted(directory.rglob('*')) if p.is_file() and p != except_path}


class Monitor:
    """До допуска не разрешает I/O; далее отдельный учёт создания и уборки временного файла."""
    def __init__(self):
        self.phase = None
        sys.addaudithook(self.history)

    def reset(self, scratch):
        self.scratch = scratch
        self.created = set()
        self.cleaning = None
        self.write_attempts = self.violations = self.allocations = 0
        self.quiet = True

    def deny(self):
        self.violations += 1
        raise AssertionError('unexpected_io')

    def history(self, event, args):
        phase = self.phase
        if phase is None:
            return
        if event == 'tempfile.mkdtemp':
            path = Path(os.fsdecode(args[0]))
            if phase == 'stage' and path.parent == self.scratch and path.name.startswith('ack-promote-'):
                self.created.add(path)
                self.allocations += 1
                return
            self.deny()
        if event == 'open':
            path, _, flags = args
            if type(path) in (str, bytes):
                path = Path(os.fsdecode(path))
            writing = flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            if phase == 'stage' and isinstance(path, Path) and path.parent in self.created and path.name == STAGE_NAME:
                if writing and flags & os.O_EXCL and flags & os.O_CREAT:
                    self.write_attempts += 1
                    if self.fail_open:
                        raise PermissionError('synthetic open refusal')
                    return
            if phase in ('exit', 'stage') and not writing and self.cleaning is not None and path == self.cleaning:
                return  # CPython rmtree открывает свой каталог без флага записи.
            self.deny()
        if event == 'os.mkdir' and phase == 'stage' and Path(os.fsdecode(args[0])) in self.created:
            return
        if event == 'shutil.rmtree' and phase in ('stage', 'exit'):
            path = Path(os.fsdecode(args[0]))
            if path in self.created:
                self.cleaning = path
                return
            self.deny()
        if self.cleaning is not None and event in ('os.scandir', 'os.listdir', 'os.rmdir', 'os.remove'):
            used = args[0]
            if event in ('os.scandir', 'os.listdir') and (type(used) is int or Path(os.fsdecode(used)) == self.cleaning):
                return
            if event == 'os.rmdir' and Path(os.fsdecode(used)) == self.cleaning:
                return
            if event == 'os.remove' and (Path(os.fsdecode(used)) == self.cleaning / STAGE_NAME or
                                         (os.fsdecode(used) == STAGE_NAME and type(args[1]) is int and args[1] >= 0)):
                return
            self.deny()
        if event.startswith(('os.', 'tempfile.', 'shutil.', 'socket.', 'subprocess.', 'urllib.')):
            self.deny()

    def call(self, thunk, *, phase='plan', fail_open=False):
        self.phase = phase
        self.cleaning = None
        self.fail_open = fail_open
        out, err = io.StringIO(), io.StringIO()
        try:
            with redirect_stdout(out), redirect_stderr(err):
                return thunk()
        finally:
            self.phase = None
            self.quiet = self.quiet and not out.getvalue() and not err.getvalue()


def response_code(error, findings):
    assert (error.code, error.where) in REFUSALS
    diagnostic = error.diagnostic()
    expected = {'code': error.code, 'where': error.where}
    if error.code == 'project_specific':
        details = diagnostic['details']
        assert type(details) is dict and details.keys() == {'findings'} and type(details['findings']) is list
        for f in details['findings']:
            assert type(f) is dict and f.keys() == {'field', 'category', 'code'}
            assert all(type(v) is str for v in f.values()) and (f['field'], f['category'], f['code']) in MARKERS
            findings.append(dict(f))
        expected['details'] = details
    assert canonical(expected) == canonical(diagnostic)
    return error.code + ':' + error.where


def observe(PromotionSession, book, c, guard):
    driver, kind = c['driver'], c['kind']
    source = source_entry(kind)
    clean = editable(kind, driver)
    context = deepcopy(book['context'])
    profile_bytes, profile, fingerprints, decisions = profile_fixture(clean, kind, driver)
    candidate = dict(clean, kind=kind, authority='profile_owner', state='draft')
    raw, packed, decision = expected_file(candidate, profile, fingerprints, decisions)
    revision = {'from': profile['revision'], 'to': profile['revision'] + 1}
    expected_plan = {'promotion_format': 1, 'operation': 'promote', 'target': 'stand', 'outcome': 'planned',
                     'candidate': candidate, 'candidate_sha256': entry_hash(candidate),
                     'diff': {'file': STAGE_NAME, 'revision': revision, 'before_sha256': digest(profile_bytes),
                              'after_sha256': digest(raw), 'decision': decision}}
    banned = (SOURCE_ID, SOURCE_TITLE, BODY_MARKER, LITERAL, PRIVATE_EXISTING, 'cedar-fixture', 'host-fixture', '/home/fixture-only')
    for value in banned:
        assert value.encode('ascii') not in canonical(expected_plan)
    session = PromotionSession()
    steps, findings = [], []
    actual_rev = None
    other_reads = 0
    unchanged = True
    with tempfile.TemporaryDirectory(prefix='ack-promotion-probe-') as tmp:
        lab = Path(tmp).resolve()
        src, live, other, scratch = (lab / key for key in ('source', 'working', 'other', 'scratch'))
        workspace(src, 'source', source_doc(source))
        workspace(live, 'working', doc('L2', '.agent-contract', [row('C-working', 'contract', 'project_owner')], revision=9))
        other_layout = workspace(other, 'other', doc('L2', '.agent-contract', [row('C-other', 'contract', 'project_owner')], revision=2))
        out_path = other / PROFILE_FILE
        scratch.mkdir()
        before = (file_tree(src), file_tree(live), file_tree(other, except_path=out_path))
        original_other_profile = out_path.read_bytes()
        guard.reset(scratch)
        previous_tmp = tempfile.tempdir
        tempfile.tempdir = str(scratch)

        def plan_with(src_entry, proposal, ctx, *, target='stand', verify=True):
            nonlocal unchanged
            inputs = canonical([src_entry, proposal, ctx])
            try:
                plan = guard.call(lambda: session.promote(src_entry, proposal=proposal, context=ctx,
                                                          staged_profile=profile_bytes, target=target))
            except registry_policy.StoreError as error:
                steps.append(response_code(error, findings))
                return None
            finally:
                unchanged = unchanged and inputs == canonical([src_entry, proposal, ctx])
            assert type(plan) is dict and type(plan.get('ticket')) is str and TICKET_PATTERN.fullmatch(plan['ticket'])
            if verify:
                assert canonical({k: v for k, v in plan.items() if k != 'ticket'}) == canonical(expected_plan)
            else:
                assert plan['outcome'] == 'planned'
            steps.append('planned')
            return plan

        def stage_with(owner, plan, ticket, *, fail_open=False):
            nonlocal actual_rev, other_reads, unchanged
            before_plan = canonical(plan)
            try:
                cm = guard.call(lambda: owner.stage(plan, confirmed_ticket=ticket))
                path = guard.call(cm.__enter__, phase='stage', fail_open=fail_open)
            except registry_policy.StoreError as error:
                steps.append(response_code(error, findings))
                return
            finally:
                unchanged = unchanged and before_plan == canonical(plan)
            try:
                assert isinstance(path, Path) and path.name == STAGE_NAME and path.parent in guard.created
                assert sorted(p.relative_to(path.parent).as_posix() for p in path.parent.rglob('*')) == [STAGE_NAME]
                assert path.read_bytes() == raw
                assert all(value.encode('ascii') not in raw for value in (SOURCE_ID, SOURCE_TITLE, BODY_MARKER, LITERAL, ticket))
                # Запись в другом проекте делает только проба: переносит точные байты контейнера.
                out_path.write_bytes(path.read_bytes())
                got = registry_store.read_registry(other_layout, target='L1')
                journal = registry_store.profile_history(other_layout)
                assert canonical(got) == canonical(packed['registry']) and canonical(journal) == canonical(packed['journal'])
                assert candidate['id'] not in {entry['id'] for entry in registry_policy.active_entries(got)}
                assert entry_hash(got['entries'][-1]) == plan['candidate_sha256'] == journal['decisions'][-1]['after_sha256']
                actual_rev = {'from': profile['revision'], 'to': got['revision']}
                other_reads += 1
                steps.append('staged')
            finally:
                guard.call(lambda: cm.__exit__(None, None, None), phase='exit')

        try:
            dirty = dict(clean, text=source['text'])
            if driver == 'repair':
                assert plan_with(source, dirty, context) is None
            edits = {'scope_marker': {'scope': 'tenant-fixture/docs'}, 'name_marker': {'title': 'CEDAR-FIXTURE: осмотр'},
                     'basis_marker': {'basis': 'Проверка /home/fixture-only/check'}, 'value_marker': {'key': 'api_key', 'value': LITERAL},
                     'parent_missing': {'parent': 'C-missing'}, 'parent_kind': {'parent': 'R-existing'},
                     'scope_outside': {'scope': 'docs-extra'}, 'bad_proposal': {'state': 'active'}}
            proposal = dict(clean, **edits.get(driver, {}))
            supplied = dict(source, authority='profile_owner') if driver == 'bad_source' else source
            ctx = dict(context, project_paths={'tenant-fixture': True}) if driver == 'bad_context' else context
            plan = plan_with(supplied, proposal, ctx, target='live' if driver == 'live' else 'stand')
            if plan is not None:
                ticket = plan['ticket']
                if driver == 'stable':
                    second = plan_with(dict(source, text='Другая исходная формулировка ' + BODY_MARKER),
                                       dict(reversed(list(clean.items()))), dict(reversed(list(context.items()))))
                    assert second is not None and second['ticket'] != ticket
                    stage_with(session, second, second['ticket'])
                elif driver == 'superseded':
                    second = plan_with(source, dict(clean, text='Другая явно поданная переносимая редакция.'), context, verify=False)
                    assert second is not None and second['ticket'] != ticket
                    stage_with(session, plan, ticket)
                elif driver == 'rejected_supersedes':
                    assert plan_with(source, dirty, context) is None
                    stage_with(session, plan, ticket)
                elif driver in ('edit_plan', 'edit_path', 'edit_digest'):
                    if driver == 'edit_plan':
                        plan['candidate']['text'] = 'Подмена текста без нового согласия.'
                    if driver == 'edit_path':
                        plan['diff']['file'] = str(live / PROFILE_FILE)
                    if driver == 'edit_digest':
                        plan['candidate_sha256'] = '0' * 64
                    stage_with(session, plan, ticket)
                elif driver == 'foreign_session':
                    stage_with(PromotionSession(), plan, ticket)
                elif driver == 'write_denied':
                    stage_with(session, plan, ticket, fail_open=True)
                    stage_with(session, plan, ticket)
                else:
                    supplied_ticket = None if driver == 'no_ticket' else 'f' * 64 if driver == 'wrong_ticket' else ticket
                    stage_with(session, plan, supplied_ticket)
                    if driver == 'replay':
                        stage_with(session, plan, ticket)
        finally:
            tempfile.tempdir = previous_tmp
        preserved = (before == (file_tree(src), file_tree(live), file_tree(other, except_path=out_path))
                     and out_path.read_bytes() == (raw if other_reads else original_other_profile))
        return {'steps': steps, 'findings': findings, 'write_attempts': guard.write_attempts,
                'revision': actual_rev, 'allocations': guard.allocations, 'io_violations': guard.violations,
                'other_validated': other_reads, 'stage_empty': not any(scratch.iterdir()), 'inputs_unchanged': unchanged,
                'protected_trees_unchanged': preserved, 'quiet': guard.quiet}


def expected_observation(c):
    e = c['expected']
    return dict(e, allocations=e['write_attempts'], io_violations=0, other_validated=int(e['revision'] is not None),
                stage_empty=True, inputs_unchanged=True, protected_trees_unchanged=True, quiet=True)


def control():
    origin = source_doc(source_entry('protocol'))
    profile_bytes, _, _, _ = profile_fixture(editable('protocol', 'ordinary'), 'protocol', 'ordinary')
    profile, _ = registry_journal.unpack_registry(schema_v2.parse_json(profile_bytes), area='L1')
    schema_v2.validate_catalog({'L0': doc('L0', 'kit', []), 'L1': profile, 'L2': origin})
    try:
        registry_policy.check_operation('promote', target='L1')
    except registry_policy.StoreError as error:
        assert error.code == 'unknown_operation' and 'promote' not in registry_policy.operation_matrix()
    else:
        raise AssertionError('working_port_acquired_promote')
    return {'source_v2': True, 'staged_profile_v2': True, 'working_port': 'unknown_operation'}


def main():
    book = json.loads((HERE / 'CASES.json').read_bytes())
    base_control, rows = control(), []
    if not (ROOT / MODULE).is_file():
        rows = [{'id': c['id'], 'status': 'fail', 'reason': 'promotion_missing'} for c in book['cases']]
    else:
        from kit.base.promotion import PromotionSession
        guard = Monitor()
        for c in book['cases']:
            try:
                observation = observe(PromotionSession, book, c, guard)
                if canonical(observation) != canonical(expected_observation(c)):
                    rows.append({'id': c['id'], 'status': 'fail', 'reason': 'observation_mismatch'})
                else:
                    rows.append({'id': c['id'], 'status': 'pass', 'observation': observation})
            except (AssertionError, AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError):
                rows.append({'id': c['id'], 'status': 'fail', 'reason': 'probe_rejected'})
    counts = Counter(r['status'] for r in rows)
    tally = {k: counts[k] for k in ('pass', 'fail', 'not run')}
    result = {'format': 1, 'os': platform.system(), 'python': platform.python_version(),
              'control': base_control, 'rows': rows, 'counts': tally}
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return int(tally['fail'] != 0 or tally['not run'] != 0)


if __name__ == '__main__':
    raise SystemExit(main())
