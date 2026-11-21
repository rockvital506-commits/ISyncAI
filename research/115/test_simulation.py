#!/usr/bin/env python3
"""Оракул И-115: реальный P01, четыре новые раскладки, наблюдение за входом и просмотром."""
from collections import Counter
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import platform
import sys
import tempfile
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT), str(ROOT / 'research/114')]
from kit.base import bootstrap, operation_card, registry_policy, schema_v2
from kit.base.promotion import PromotionSession
import test_promotion as prev

MODULE = 'kit/base/simulation.py'
BOOK = 'research/115/CASES.json'
FIXTURES = {'cli': 'src/tool/usage.txt', 'docs': 'docs/site/index.md'}
VARIANTS = ('control', 'installed')
ENTRY_PATH, START_PATH = 'kit/base/entry.txt', 'kit/base/START.md'
SYS_PATH, PROJ_PATH = 'kit/base/registry.json', '.agent-contract/project/registry.json'
PROFILE_PATH = 'profiles/staged/registry.json'
SECTION_END = b'<!-- /bootstrap-0 -->\n'
ENTRY_BYTES, SECTION_BYTES = 20, 2363
canonical, digest = prev.canonical, prev.digest


def load_prior(book):
    ref = book['origin']
    assert ref['iteration'] == '114' and ref['case'] == 'P01'
    prior = ROOT / 'research/114'
    c = json.loads((prior / 'CASES.json').read_bytes())
    case = next(r for r in c['cases'] if r['id'] == ref['case'])
    assert case['driver'] == 'repair' and case['kind'] == 'protocol'
    source = prev.source_entry('protocol')
    proposal = prev.editable('protocol', 'repair')
    before, registry, anchor, history = prev.profile_fixture(proposal, 'protocol', 'repair')
    entry = dict(proposal, kind='protocol', state='draft', authority='profile_owner')
    expected, _, _ = prev.expected_file(entry, registry, anchor, history)
    session = PromotionSession()
    try:
        session.promote(source, proposal=dict(proposal, text=source['text']), context=c['context'], staged_profile=before)
    except registry_policy.StoreError as error:
        assert error.code == 'project_specific' and error.diagnostic()['details']['findings'] == case['expected']['findings']
    else:
        raise AssertionError('expected_original_refusal')
    plan = session.promote(source, proposal=proposal, context=c['context'], staged_profile=before)
    with session.stage(plan, confirmed_ticket=plan['ticket']) as path:
        packed = path.read_bytes()
    assert not path.exists() and packed == expected
    witnesses = {'entry_id': entry['id'], 'entry_sha256': prev.entry_hash(entry),
                 'control_sha256': digest(before), 'profile_sha256': digest(packed)}
    stored = next(r for r in json.loads((prior / 'PROMOTION.json').read_bytes())['rows'] if r['id'] == ref['case'])
    assert witnesses == ref['witness'] and witnesses['entry_sha256'] == plan['candidate_sha256'] == stored['candidate_sha256']
    assert plan['diff']['before_sha256'] == witnesses['control_sha256'] and plan['diff']['after_sha256'] == witnesses['profile_sha256']
    assert plan['diff']['revision'] == stored['revision'] == {'from': 3, 'to': 4}
    return packed, before


def wires(book, profiles):
    packed, before = profiles
    seeds = book['fixtures']
    startup = {'entry': (ROOT / ENTRY_PATH).read_bytes(), 'start': (ROOT / START_PATH).read_bytes()}
    assert len(startup['entry']) == ENTRY_BYTES and startup['start'].index(SECTION_END) + len(SECTION_END) == SECTION_BYTES
    projects = {k: {'registry': canonical(v['registry']) + b'\n', 'asset': v['asset'].encode('utf-8')}
                for k, v in seeds['projects'].items()}
    return {'candidate_profile': packed, 'control_profile': before, 'witness': deepcopy(book['origin']['witness']),
            'startup': startup, 'system': canonical(seeds['system']) + b'\n', 'projects': projects, 'target': 'stand'}


def control(book, profiles):
    data = wires(book, profiles)
    for k in FIXTURES:
        schema_v2.validate_catalog({'L0': book['fixtures']['system'], 'L1': json.loads(profiles[1]),
                                    'L2': book['fixtures']['projects'][k]['registry']})
    assert data['projects']['cli'] != data['projects']['docs']
    try:
        registry_policy.check_operation('simulate', target='L1')
    except registry_policy.StoreError as error:
        assert error.code == 'unknown_operation' and 'simulate' not in registry_policy.operation_matrix()
    else:
        raise AssertionError('working_port_acquired_simulate')
    for phrase in ('Покажи протоколы в профиле staged.', 'Покажи действующие протоколы в профиле staged.',
                   'Покажи только текст протокола «L1-new-draft-114» в профиле staged.', 'Покажи правила в L2.'):
        c = operation_card.compile_prompt(phrase)
        assert c['outcome'] == 'complete' and c['operation'] == 'list'
    return {'promotion_case': 'P01', 'promotion_exact': True, 'fixtures_valid': 2, 'working_port': 'unknown_operation',
            'entry_sha256': data['witness']['entry_sha256'], 'profile_sha256': data['witness']['profile_sha256'],
            'control_sha256': data['witness']['control_sha256']}


def change(data, driver):
    w, projects = data['witness'], data['projects']
    if driver == 'live':
        data['target'] = 'live'
    elif driver == 'reordered':
        data['projects'] = dict(reversed(list(projects.items())))
        data['witness'] = dict(reversed(list(w.items())))
    elif driver == 'different_tail':
        data['startup']['start'] = data['startup']['start'][:SECTION_BYTES] + b'\nSIM_TAIL_ONLY_115: not an instruction.\n'
    elif driver == 'no_id':
        w.pop('entry_id')
    elif driver == 'bad_digest_type':
        w['entry_sha256'] = True
    elif driver == 'changed_profile_bytes':
        data['candidate_profile'] += b'\n'
    elif driver == 'changed_control_bytes':
        data['control_profile'] += b'\n'
    elif driver == 'different_entry_digest':
        w['entry_sha256'] = '0' * 64
    elif driver == 'foreign_id':
        w['entry_id'] = 'R-absent-in-pack'
    elif driver in ('broken_history', 'different_parent_body', 'different_order', 'active_draft', 'foreign_profile_root'):
        box = json.loads(data['candidate_profile'])
        rows, journal = box['registry']['entries'], box['journal']
        parent, candidate = rows
        if driver == 'broken_history':
            journal['decisions'][-1]['after_sha256'] = '0' * 64
        elif driver == 'different_parent_body':
            parent['title'] = 'Незаметная замена прежнего контракта'
            journal['base_entries'][parent['id']] = prev.entry_hash(parent)
        elif driver == 'different_order':
            rows.reverse()
        elif driver == 'active_draft':
            candidate['state'] = 'active'
            w['entry_sha256'] = journal['decisions'][-1]['after_sha256'] = prev.entry_hash(candidate)
        else:
            box['registry']['roots'] = ['profiles/working']
        data['candidate_profile'] = canonical(box) + b'\n'
        w['profile_sha256'] = digest(data['candidate_profile'])
    elif driver == 'duplicate_projects':
        projects['docs']['registry'] = json.dumps(json.loads(projects['cli']['registry']), indent=2).encode('ascii')
    elif driver == 'one_project':
        projects.pop('docs')
    elif driver in ('overlapping_root', 'orphan_in_docs'):
        doc = json.loads(projects['docs']['registry'])
        if driver == 'overlapping_root':
            doc['roots'] = ['kit']
        else:
            doc['entries'][-1]['parent'] = 'C-no-such-parent'
        projects['docs']['registry'] = canonical(doc) + b'\n'
    elif driver == 'wrong_system':
        data['system'] = projects['cli']['registry']
    elif driver == 'bad_start':
        data['startup']['start'] = '## 1. Не секция входа\n'.encode('utf-8')
    elif driver == 'bad_asset':
        projects['docs']['asset'] = 'this-is-not-a-filename-to-open.txt'


def files(data, fixture, variant):
    return {ENTRY_PATH: data['startup']['entry'], START_PATH: data['startup']['start'], SYS_PATH: data['system'],
            PROFILE_PATH: data['candidate_profile' if variant == 'installed' else 'control_profile'],
            PROJ_PATH: data['projects'][fixture]['registry'], FIXTURES[fixture]: data['projects'][fixture]['asset']}


def expected_result(book):
    result = {'simulation_format': 1, 'outcome': 'simulated', 'projects': []}
    for k in ('entry_sha256', 'control_sha256', 'profile_sha256'):
        result[k] = book['origin']['witness'][k]
    for fixture, path in FIXTURES.items():
        count = sum(r['kind'] == 'rule' for r in book['fixtures']['projects'][fixture]['registry']['entries'])
        common = {'candidate_active': False, 'l2_rules': count, 'entry_bytes': ENTRY_BYTES,
                  'section0_bytes': SECTION_BYTES, 'unchanged': True}
        result['projects'].append({'fixture': fixture, 'asset': path,
                                   'control': dict(common, profile_revision=3, candidate_visible=False, text_verified=False),
                                   'installed': dict(common, profile_revision=4, candidate_visible=True, text_verified=True)})
    return result


ALL_FILES = {Path(fixture) / variant / name for fixture, asset in FIXTURES.items() for variant in VARIANTS
             for name in (ENTRY_PATH, START_PATH, SYS_PATH, PROFILE_PATH, PROJ_PATH, asset)}
ALL_DIRS = {directory for f in ALL_FILES for directory in f.parents}


class Monitor:
    """Перехват до доступа: ни одного открытия вне выделенной пробы, без вызова сети и процессов."""
    def __init__(self):
        self.active = False
        sys.addaudithook(self.event)

    def begin(self, scratch, driver):
        self.scratch, self.driver = scratch, driver
        self.root = None
        self.writes = []
        self.allocations = self.violations = 0
        self.cleaning = self.inspecting = False

    def reject(self):
        self.violations += 1
        raise AssertionError('out_of_bounds_io')

    def local(self, arg):
        if self.root is None or type(arg) not in (str, bytes):
            return None
        p = Path(os.fsdecode(arg))
        return p.relative_to(self.root) if p.is_relative_to(self.root) else None

    def event(self, event, args):
        if not self.active:
            return
        if event == 'tempfile.mkdtemp':
            p = Path(os.fsdecode(args[0]))
            if self.root is None and p.parent == self.scratch and p.name.startswith('ack-simulate-'):
                self.root = p
                self.allocations += 1
                return
            self.reject()
        if event == 'open':
            p, _, flags = args
            rel = self.local(p)
            writing = flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            if writing:
                if not (rel in ALL_FILES and rel not in self.writes and flags & os.O_EXCL and flags & os.O_CREAT and not self.cleaning):
                    self.reject()
                self.writes.append(rel)
                if self.driver == 'write_denied' and rel == Path('docs/control') / ENTRY_PATH:
                    raise PermissionError('synthetic create refusal')
                return
            if rel in ALL_FILES and rel in self.writes:
                if self.driver == 'read_denied' and rel == Path('docs/installed') / START_PATH and not self.inspecting:
                    raise PermissionError('synthetic read refusal')
                return
            if self.cleaning and (rel in ALL_DIRS or (type(p) is str and p in {d.name for d in ALL_DIRS})):
                return
            self.reject()
        if event == 'shutil.rmtree' and self.local(args[0]) == Path('.'):
            self.cleaning = True
            return
        if event == 'os.mkdir' and self.local(args[0]) in ALL_DIRS and not self.cleaning:
            return
        if event in ('os.scandir', 'os.listdir') and (self.local(args[0]) in ALL_DIRS or (self.cleaning and type(args[0]) is int)):
            return
        if self.cleaning and event in ('os.remove', 'os.rmdir'):
            allowed = ALL_DIRS if event == 'os.rmdir' else ALL_FILES
            p, fd = args[:2]
            if self.local(p) in allowed or (type(p) is str and p in {a.name for a in allowed} and type(fd) is int and fd >= 0):
                return
            self.reject()
        if event.startswith(('os.', 'tempfile.', 'shutil.', 'socket.', 'subprocess.', 'urllib.')):
            self.reject()


def observe(simulate, book, case, profiles, guard):
    driver, want = case['driver'], case['expected']
    data = wires(book, profiles)
    change(data, driver)
    original = deepcopy(data)
    boot_calls, list_calls = [], []
    out, err = io.StringIO(), io.StringIO()
    result = None
    code = 'simulated'
    where = reason = None
    with tempfile.TemporaryDirectory(prefix='ack-simulation-probe-') as tmp:
        root = Path(tmp).resolve()
        source, working, scratch = (root / p for p in ('source', 'working', 'scratch'))
        prev.workspace(source, 'source', prev.source_doc(prev.source_entry('protocol')))
        prev.workspace(working, 'working', prev.doc('L2', '.agent-contract', [prev.row('C-working', 'contract', 'project_owner')]))
        protected = prev.file_tree(source), prev.file_tree(working)
        scratch.mkdir()
        guard.begin(scratch, driver)
        old_tmp, tempfile.tempdir = tempfile.tempdir, str(scratch)
        old_init, old_plan = bootstrap.BootstrapSession.__init__, bootstrap.BootstrapSession.plan

        def checked_init(self, layout, *, profile_id):
            workspace = layout.workspace
            assert isinstance(workspace, Path) and guard.root is not None and workspace.is_relative_to(guard.root)
            rel = workspace.relative_to(guard.root)
            assert len(rel.parts) == 2
            fixture, variant = rel.parts
            assert profile_id == 'staged' and layout.profile_root == 'profiles/staged'
            assert (fixture, variant) == next((k, v) for k in FIXTURES for v in VARIANTS if (k, v) not in boot_calls)
            boot_calls.append((fixture, variant))
            wanted = files(data, fixture, variant)
            guard.inspecting = True
            try:
                assert {p.relative_to(workspace).as_posix(): p.read_bytes() for p in workspace.rglob('*') if p.is_file()} == wanted
                assert not any(p.is_symlink() for p in workspace.rglob('*'))
            finally:
                guard.inspecting = False
            old_init(self, layout, profile_id=profile_id)

        def observed_plan(self, request):
            fixture, variant = self._layout.workspace.relative_to(guard.root).parts
            pos = sum((x, y) == (fixture, variant) for x, y in list_calls)
            expected = [
                {'kind': 'protocol', 'target': 'L1', 'profile': 'staged'},
                {'state': 'active', 'kind': 'protocol', 'target': 'L1', 'profile': 'staged'},
                {'kind': 'rule', 'target': 'L2'},
            ]
            if variant == 'installed':
                expected.append({'view': 'text', 'kind': 'protocol', 'entry_id': book['origin']['witness']['entry_id'],
                                 'target': 'L1', 'profile': 'staged'})
            assert pos < len(expected)
            card = operation_card.compile_prompt(request)
            assert card['operation'] == 'list' and card['outcome'] == 'complete' and card['params'] == expected[pos]
            list_calls.append((fixture, variant))
            seen = old_plan(self, request)
            assert seen['outcome'] == 'listed' and seen['dry_run'] is True and 'diff' not in seen and 'ticket' not in seen
            if driver == 'listing_drift' and (fixture, variant, pos) == ('docs', 'installed', 3):
                seen['result']['entries'][0]['text'] = 'UNEXPECTED_BODY_NOT_FOR_REPORT_115'
            return seen

        try:
            with patch.object(bootstrap.BootstrapSession, '__init__', checked_init), patch.object(bootstrap.BootstrapSession, 'plan', observed_plan):
                with redirect_stdout(out), redirect_stderr(err):
                    guard.active = True
                    try:
                        result = simulate(**data)
                    except registry_policy.StoreError as error:
                        code, where = error.code, error.where
                        reason = error.diagnostic().get('details', {}).get('reason')
                        assert {'code': want['outcome'], 'where': want['where'], 'details': {'reason': want['reason']}} == error.diagnostic()
                    finally:
                        guard.active = False
        finally:
            tempfile.tempdir = old_tmp
        if result is not None:
            assert canonical(result) == canonical(expected_result(book))
        assert guard.violations == 0
        return {'outcome': code, 'where': where, 'reason': reason, 'result': result,
                'write_attempts': len(guard.writes), 'bootstrap_calls': len(boot_calls), 'list_calls': len(list_calls),
                'allocations': guard.allocations, 'io_violations': guard.violations, 'cleaned': not any(scratch.iterdir()),
                'protected_unchanged': protected == (prev.file_tree(source), prev.file_tree(working)),
                'inputs_unchanged': data == original, 'quiet': not out.getvalue() and not err.getvalue()}


def expected_observation(book, case):
    want = case['expected']
    return dict(want, result=expected_result(book) if want['outcome'] == 'simulated' else None,
                io_violations=0, cleaned=True, protected_unchanged=True, inputs_unchanged=True, quiet=True)


def main():
    book = json.loads((ROOT / BOOK).read_bytes())
    profiles = load_prior(book)
    ctrl = control(book, profiles)
    rows = []
    if not (ROOT / MODULE).is_file():
        rows = [{'id': c['id'], 'status': 'fail', 'reason': 'simulation_missing'} for c in book['cases']]
    else:
        from kit.base.simulation import simulate
        guard = Monitor()
        for c in book['cases']:
            try:
                observation = observe(simulate, book, c, profiles, guard)
                if canonical(observation) == canonical(expected_observation(book, c)):
                    rows.append({'id': c['id'], 'status': 'pass', 'observation': observation})
                else:
                    rows.append({'id': c['id'], 'status': 'fail', 'reason': 'observation_mismatch'})
            except (AssertionError, AttributeError, KeyError, OSError, RuntimeError, StopIteration, TypeError, ValueError):
                rows.append({'id': c['id'], 'status': 'fail', 'reason': 'probe_rejected'})
    counts = Counter(r['status'] for r in rows)
    tally = {k: counts[k] for k in ('pass', 'fail', 'not run')}
    result = {'format': 1, 'os': platform.system(), 'python': platform.python_version(),
              'control': ctrl, 'rows': rows, 'counts': tally}
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return int(tally['fail'] != 0 or tally['not run'] != 0)


if __name__ == '__main__':
    raise SystemExit(main())
