#!/usr/bin/env python3
"""Замороженный оракул И-116: точные пары, декларации, ограничения и отсутствие I/O."""
from collections import Counter
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from hashlib import sha256
import io
import json
from pathlib import Path
import platform
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT), str(ROOT / 'research/114')]
from kit.base import registry_policy, schema_v2, registry_journal
import test_promotion as prior

BOOK = 'research/116/CASES.json'
MODULE = 'kit/base/conflict_review.py'
AREAS = ('L0', 'L1', 'L2')
ROOTS = {'L0': 'kit', 'L1': 'profiles/staged', 'L2': '.agent-contract'}
AUTHORITY = {'L0': 'system_release', 'L1': 'profile_owner', 'L2': 'project_owner'}
CONTRACT = {'L0': 'S-1', 'L1': 'R-1', 'L2': 'P-1'}
FIELDS = {'L0': 'system', 'L1': 'profile', 'L2': 'project'}
EVIDENCE = 'workflow.phase.evidence'
LINKS = 'test.links'
DISPLAY = ('id', 'kind', 'state', 'authority', 'parent', 'scope', 'value', 'text')
BAD = 'SYNTHETIC_DO_NOT_ECHO_116'


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def hash_bytes(data):
    return sha256(data).hexdigest()


def encoded(value):
    return canonical(value) + b'\n'


def get(path):
    return json.loads((ROOT / path).read_bytes())


def context(book):
    examples = get('research/strategy/pre-104/SCHEMA-CASES.json')
    required = {r['id']: r for r in examples['cases'] if r['id'] in ('X07', 'X08')}
    assert set(required) == {'X07', 'X08'} and all(e['from_iteration'] == 'И-116' for e in required.values())
    s2 = next(s for s in examples['samples']['L0']['entries'] if s['alias'] == 'S-2')
    assert (s2['kind'], s2['scope'], s2['key'], s2['value']) == ('constraint', '.', EVIDENCE, 'required')
    proposal = prior.editable('protocol', 'repair')
    entry = dict(proposal, kind='protocol', state='draft', authority='profile_owner')
    before, base, anchor, decisions = prior.profile_fixture(proposal, 'protocol', 'repair')
    packed, expected, decision = prior.expected_file(entry, base, anchor, decisions)
    w = {'id': entry['id'], 'entry_sha256': hash_bytes(canonical(entry)), 'control_sha256': hash_bytes(before),
         'profile_sha256': hash_bytes(packed)}
    assert w == book['prior'] and 'key' not in entry and 'value' not in entry
    assert (base['revision'], expected['registry']['revision'], decision['operation']) == (3, 4, 'create')
    registry, journal = registry_journal.unpack_registry(schema_v2.parse_json(packed), area='L1')
    assert registry == expected['registry'] and journal == expected['journal'] and journal['decisions'] == [decision]
    pub = next(r for r in get('research/114/PROMOTION.json')['rows'] if r['id'] == 'P01')
    assert pub['candidate_sha256'] == w['entry_sha256'] and pub['revision'] == {'from': 3, 'to': 4}
    p115 = get('research/115/CASES.json')
    witness = dict(p115['origin']['witness']); witness['id'] = witness.pop('entry_id')
    assert witness == w
    summary = get('research/115/SIMULATION.json')['reference']
    assert all(summary[k] == w[k] for k in w if k.endswith('_sha256'))
    assert [row['fixture'] for row in summary['projects']] == ['cli', 'docs']
    assert all(row['installed']['text_verified'] is True and row['installed']['candidate_active'] is False for row in summary['projects'])
    projects = {n: row['registry'] for n, row in p115['fixtures']['projects'].items()}
    assert projects.keys() == {'cli', 'docs'} and projects['cli'] != projects['docs']
    return {'s2_text': s2['text'], 'exact_raw': packed, 'exact_registry': registry,
            'exact_system': p115['fixtures']['system'], 'exact_projects': projects}


def row(area, id_, *, kind='rule', scope='.', value=None, key=EVIDENCE, state='active', parent=None, text=None):
    r = {'id': id_, 'kind': kind, 'scope': scope, 'state': state, 'authority': AUTHORITY[area],
         'parent': None if kind == 'contract' else parent or CONTRACT[area], 'title': f'Фикстура {id_}',
         'text': text or f'Синтетическое условие {area}/{id_}: {value if value is not None else "без пары"}.',
         'basis': 'Фикстура И‑116', 'criterion': 'Сверить формулировку и область.'}
    if value is not None:
        r.update(key=key, value=value)
    return r


def registry(area):
    counter = {'release_version': '0.2.0-dev.116'} if area == 'L0' else {'revision': 4 if area == 'L1' else 12}
    return {'schema_version': 2, 'area': area, 'roots': [ROOTS[area]],
            'entries': [row(area, CONTRACT[area], kind='contract')], **counter}


def rank(area, id_, n):
    return {'area': area, 'id': id_, 'rank': n}


def fixture(name, ctx):
    docs = {a: registry(a) for a in AREAS}
    def add(area, id_, **kwargs):
        entry = row(area, id_, **kwargs)
        docs[area]['entries'].append(entry)
        return entry

    decl, candidate, source = [], None, None
    if name in ('x07', 'equal', 'older_history', 'joint', 'reordered', 'unkeyed_and_active', 'inactive', 'other_pairs'):
        add('L0', 'S-2', kind='constraint', value='required', text=ctx['s2_text'])
        v = 'required' if name == 'equal' else 'skip'
        r = add('L1', 'R-2', kind='protocol', value=v,
                text='Зафиксировать свидетельство фазы.' if v == 'required' else 'Допускается пропустить свидетельство фазы.')
        decl = [rank('L0', 'S-2', 10), rank('L1', 'R-2', 90)]
        if name in ('joint', 'reordered', 'unkeyed_and_active'):
            add('L2', 'P-evidence', scope='docs/guide', value='local-only')
            decl = [rank('L1', 'R-2', 85), rank('L2', 'P-evidence', 0)]
        if name == 'reordered':
            for doc in docs.values():
                doc['entries'].reverse()
            decl.reverse()
        if name == 'unkeyed_and_active':
            add('L1', 'draft-no-key', kind='protocol', state='draft', scope='docs/guide')
            candidate = 'draft-no-key'
        if name == 'inactive':
            r['state'] = 'draft'
            for state in ('suspended', 'revoked'):
                add('L1', 'R-' + state, value='skip', state=state)
            add('L1', 'R-paused-parent', kind='contract', state='suspended')
            add('L1', 'R-under-paused', value='skip', parent='R-paused-parent')
        if name == 'other_pairs':
            decl = []
            r.update(key='other.key', value='one')
            add('L1', 'R-same-layer', key='other.key', value='two')
            add('L2', 'P-evidence', scope='docs/guide', value='skip')
        if name == 'older_history':
            recent = add('L1', 'old-created', key='other.key', value='note', state='draft')
            source = encoded({'profile_format': 1, 'registry': docs['L1'],
                              'journal': {'base_revision': 3, 'decisions': [{'operation': 'create', 'entry_id': recent['id'],
                                          'profile_revision': 4, 'entry_sha256': hash_bytes(canonical(recent))}]}})
    elif name == 'system_rule':
        add('L0', 'shared', scope='docs', key='report.format', value='full')
        add('L1', 'shared', kind='preference', scope='docs/guide', key='report.format', value='short')
    elif name in ('x08', 'reverse_rank', 'explicit_draft', 'implicit_draft', 'siblings'):
        state = 'draft' if name in ('explicit_draft', 'implicit_draft') else 'active'
        add('L1', 'R-links', scope='docs/guide' if name == 'siblings' else 'docs', value='manual', key=LINKS, state=state)
        add('L2', 'P-links', kind='constraint', scope='docs/guidebook' if name == 'siblings' else 'docs/guide',
            value='automated', key=LINKS)
        first, second = (40, 40) if name == 'x08' else (7, 100)
        decl = [rank('L1', 'R-links', first), rank('L2', 'P-links', second)]
        if name == 'explicit_draft':
            candidate = 'R-links'
    elif name in ('prior_cli', 'prior_docs'):
        docs = {'L0': ctx['exact_system'], 'L1': ctx['exact_registry'], 'L2': ctx['exact_projects'][name[6:]]}
        source, candidate = ctx['exact_raw'], 'L1-new-draft-114'
    else:
        raise AssertionError('fixture_name')
    wires = {FIELDS[a]: encoded(docs[a]) for a in AREAS}
    if source is not None:
        wires['profile'] = source
    return dict(wires, priorities=decl, candidate_id=candidate, target='stand'), docs


def inject(w, name):
    if name is None:
        return
    if name == 'live':
        w['target'] = 'live'
    elif name == 'path':
        w['profile'] = Path('not-a-registry-' + BAD)
    elif name == 'oversize':
        w['system'] = b' ' * (1_048_576 + 1)
    elif name == 'duplicate_json':
        w['project'] = ('{"schema_version":2,"schema_version":1,"body":"' + BAD + '"}').encode('ascii')
    elif name in ('in_record_rank', 'wrong_root', 'missing_parent', 'inactive_parent', 'broken_history'):
        doc = json.loads(w['profile'])
        if name == 'in_record_rank':
            doc['entries'][1]['priority'] = BAD
        elif name == 'wrong_root':
            doc['roots'] = ['kit/staged']
        elif name == 'missing_parent':
            doc['entries'][1]['parent'] = BAD
        elif name == 'inactive_parent':
            doc['entries'][0]['state'] = 'suspended'
        else:
            doc['journal']['decisions'][-1]['after_sha256'] = '0' * 64
        w['profile'] = encoded(doc)
    elif name in ('bool_rank', 'double_rank', 'foreign_ref', 'extra_priority_field', 'rank_range'):
        d = w['priorities']
        if name == 'bool_rank':
            d[0]['rank'] = True
        elif name == 'double_rank':
            d.append(dict(d[0]))
        elif name == 'foreign_ref':
            d[0]['area'] = 'L2'
        elif name == 'rank_range':
            d[0]['rank'] = 101
        else:
            d[0]['body'] = BAD
    elif name in ('active_candidate', 'missing_id'):
        w['candidate_id'] = 'R-2' if name == 'active_candidate' else BAD
    elif name == 'entries_limit':
        doc = json.loads(w['system'])
        doc['entries'].extend(row('L0', f'S-fill-{i}', kind='contract') for i in range(63))
        assert len(doc['entries']) == 65
        w['system'] = encoded(doc)
    else:
        raise AssertionError('inject_name')


def declared_options(sides):
    actual = [(r['area'], r['id'], r['state']) for r in sides if r['area'] != 'L0']
    suggestion = [{'action': 'leave_unchanged', 'targets': []}]
    for action in ('revise', 'narrow_scope', 'suspend', 'clarify_conditions'):
        targets = [{'area': a, 'id': id_} for a, id_, s in actual if action != 'suspend' or s == 'active']
        if targets:
            suggestion.append({'action': action, 'targets': targets})
    return suggestion


def expected_observation(case, ctx):
    if 'error' in case:
        where, reason = case['error']
        report = None
        diagnostic = {'code': 'conflict_review_failed', 'where': where, 'details': {'reason': reason}}
    else:
        w, docs = fixture(case['fixture'], ctx)
        sides_by_ref = {a + '/' + r['id']: (a, r) for a, d in docs.items() for r in d['entries']}
        observed = []
        for key, overlap, phase, lref, rref, l0_constraint, lrank, rrank in case['pairs']:
            sides = []
            for ref, expected_rank in ((lref, lrank), (rref, rrank)):
                area, data = sides_by_ref[ref]
                assert data['key'] == key
                sides.append({'area': area, 'declared_rank': expected_rank, **{f: data[f] for f in DISPLAY}})
            restrictions = ['owner_decision_required']
            if 'L0' in [r['area'] for r in sides]:
                restrictions.append('system_immutable')
            if l0_constraint:
                restrictions.append('system_constraint_not_overridable')
            observed.append({'key': key, 'scope': overlap, 'comparison': phase, 'entries': sides,
                             'restrictions': restrictions, 'options': declared_options(sides)})
        candidate = None
        if 'candidate' in case:
            a, row = sides_by_ref['L1/' + w['candidate_id']]
            candidate = {'area': a, 'id': row['id'], 'state': 'draft', 'entry_sha256': hash_bytes(canonical(row)),
                         'comparison': case['candidate']}
        report = {'review_format': 1, 'outcome': case['outcome'], 'conflicts': observed, 'candidate': candidate,
                  'write_allowed': False, 'inputs_sha256': {a: hash_bytes(w[FIELDS[a]]) for a in AREAS},
                  'priorities_sha256': hash_bytes(canonical(sorted(w['priorities'], key=lambda r: (r['area'], r['id']))))}
        diagnostic = None
    return {'report': report, 'error': diagnostic, 'inputs_unchanged': True, 'effects': [], 'quiet': True}


def control(book, ctx):
    positive = fixture('x07', ctx)[1]
    equal = fixture('equal', ctx)[1]
    joint = fixture('joint', ctx)[1]
    for docs in (positive, equal, joint, fixture('prior_cli', ctx)[1], fixture('prior_docs', ctx)[1]):
        schema_v2.validate_catalog(docs)
    old = registry_policy.find_conflicts(positive)
    assert old == [{'key': EVIDENCE, 'scope': '.', 'entries': [
        {k: row[k] for k in ('id', 'scope', 'value', 'text')} | {'area': a}
        for a, row in (('L0', positive['L0']['entries'][1]), ('L1', positive['L1']['entries'][1]))]}]
    assert registry_policy.find_conflicts(equal) == []
    assert len(registry_policy.find_conflicts(joint)) == 3  # включает L0↔L2, новый просмотр — нет
    results = []
    for op, expected in (('edit', 'system_immutable'), ('review_conflicts', 'unknown_operation')):
        try:
            registry_policy.check_operation(op, target='L0')
        except registry_policy.StoreError as e:
            assert e.code == expected
            results.append(e.code)
        else:
            raise AssertionError('port_control')
    assert 'review_conflicts' not in registry_policy.operation_matrix()
    return {'legacy_x07_pairs': 1, 'legacy_equal_pairs': 0, 'legacy_joint_pairs': 3,
            'system_mutation': results[0], 'working_port': results[1],
            'p01_exact': book['prior'], 'p01_projects': ['cli', 'docs']}


class Monitor:
    def __init__(self):
        self.enabled = False
        self.events = []
        sys.addaudithook(self.record)

    def record(self, event, _args):
        if self.enabled and (event == 'open' or event.startswith(('os.', 'socket.', 'subprocess.', 'ctypes.', 'shutil.'))):
            self.events.append(event)
            raise RuntimeError('unexpected_effect')

    def call(self, function, wires):
        self.events = []
        old = deepcopy(wires)
        so, se = io.StringIO(), io.StringIO()
        report = error = None
        with redirect_stdout(so), redirect_stderr(se):
            self.enabled = True
            try:
                report = function(**wires)
            except registry_policy.StoreError as e:
                error = e.diagnostic()
            finally:
                self.enabled = False
        return {'report': report, 'error': error, 'inputs_unchanged': old == wires,
                'effects': list(self.events), 'quiet': not (so.getvalue() or se.getvalue())}


def main():
    book = get(BOOK)
    assert book['format'] == 1 and len({c['id'] for c in book['cases']}) == len(book['cases'])
    ctx = context(book)
    c = control(book, ctx)
    implementation = (ROOT / MODULE).is_file()
    if implementation:
        from kit.base.conflict_review import review_conflicts
        monitor = Monitor()
    rows = []
    for case in book['cases']:
        base = {'id': case['id']}
        if not implementation:
            rows.append(dict(base, status='fail', reason='conflict_review_missing'))
            continue
        try:
            wires, _ = fixture(case['fixture'], ctx)
            inject(wires, case.get('inject'))
            observed = monitor.call(review_conflicts, wires)
            matches = canonical(observed) == canonical(expected_observation(case, ctx))
        except Exception as error:
            rows.append(dict(base, status='fail', reason=type(error).__name__))
        else:
            rows.append(dict(base, status='pass', observation=observed) if matches else dict(base, status='fail', reason='oracle_mismatch'))
    count = Counter(r['status'] for r in rows)
    data = {'format': 1, 'control': c, 'counts': {k: count[k] for k in ('pass', 'fail', 'not run')},
            'os': platform.system(), 'python': platform.python_version(), 'rows': rows}
    print(json.dumps(data, ensure_ascii=False, sort_keys=True))
    return int(bool(count['fail'] or count['not run']))


if __name__ == '__main__':
    raise SystemExit(main())
