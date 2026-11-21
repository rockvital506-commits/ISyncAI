"""Межслойный разбор A3 на байтах стенда. Никаких решений или доступа к файлам."""
from hashlib import sha256

from . import registry_journal, registry_policy, schema_v2
from .profile_journal import canonical_bytes, entry_digest
from .registry_policy import StoreError

REVIEW_FORMAT = 1
_MAX_BYTES, _MAX_ENTRIES = 1_048_576, 64
_AREAS = ('L0', 'L1', 'L2')
_ROOTS = {'L0': 'kit', 'L1': 'profiles/staged', 'L2': '.agent-contract'}
_FIELDS = ('id', 'kind', 'state', 'authority', 'parent', 'scope', 'value', 'text')


def _fail(where, reason):
    raise StoreError('conflict_review_failed', where, details={'reason': reason}) from None


def _digest(data):
    return sha256(data).hexdigest()


def _registry(raw, area, where):
    if type(raw) is not bytes or not 0 < len(raw) <= _MAX_BYTES:
        _fail(where, 'bytes')
    try:
        if area == 'L0':
            document = schema_v2.validate_json(raw, expected_area=area)
        else:
            document, _ = registry_journal.unpack_registry(schema_v2.parse_json(raw), area=area)
    except schema_v2.SchemaError as error:
        _fail(where, 'history' if error.stage == 'history' else 'registry')
    if document['roots'] != [_ROOTS[area]]:
        _fail(where, 'roots')
    if len(document['entries']) > _MAX_ENTRIES:
        _fail(where, 'entry_limit')
    return document


def _priorities(priorities, entries):
    if type(priorities) not in (tuple, list) or len(priorities) > _MAX_ENTRIES * len(_AREAS):
        _fail('priorities', 'shape')
    ranks = {}
    for field in priorities:
        if (type(field) is not dict or len(field) != 3 or any(type(k) is not str for k in field)
                or field.keys() != {'area', 'id', 'rank'}):
            _fail('priorities', 'shape')
        area, id_, rank = field['area'], field['id'], field['rank']
        if (type(area) is not str or area not in _AREAS or type(id_) is not str
                or schema_v2._ID.fullmatch(id_) is None or type(rank) is not int or not 0 <= rank <= 100):
            _fail('priorities', 'shape')
        ref = area, id_
        if ref in ranks:
            _fail('priorities', 'duplicate')
        if ref not in entries or entries[ref]['kind'] == 'contract':
            _fail('priorities', 'reference')
        ranks[ref] = rank
    declarations = [{'area': area, 'id': id_, 'rank': ranks[(area, id_)]} for area, id_ in sorted(ranks)]
    return ranks, _digest(canonical_bytes(declarations))


def _candidate(candidate_id, index):
    if candidate_id is None:
        return None
    if type(candidate_id) is not str or schema_v2._ID.fullmatch(candidate_id) is None:
        _fail('candidate', 'draft')
    entry = index.get(('L1', candidate_id))
    if entry is None or entry['kind'] == 'contract' or entry['state'] != 'draft':
        _fail('candidate', 'draft')
    if index[('L1', entry['parent'])]['state'] != 'active':
        _fail('candidate', 'inactive_parent')
    return {'area': 'L1', 'id': candidate_id, 'state': 'draft', 'entry_sha256': entry_digest(entry),
            'comparison': 'structural' if 'key' in entry else 'no_key'}


def _options(sides):
    options = [{'action': 'leave_unchanged', 'targets': []}]
    for action in ('revise', 'narrow_scope', 'suspend', 'clarify_conditions'):
        targets = [{'area': side['area'], 'id': side['id']} for side in sides
                   if side['area'] != 'L0' and (action != 'suspend' or side['state'] == 'active')]
        if targets:
            options.append({'action': action, 'targets': targets})
    return options


def _pairs(documents, index, ranks, candidate):
    # A3 сравнивает active. Отдельная локальная проекция включает ровно один
    # выбранный черновик; отчёт строится по исходным записям, не по проекции.
    projection = documents
    selected = None
    if candidate is not None and candidate['comparison'] == 'structural':
        selected = ('L1', candidate['id'])
        profile = documents['L1']
        projection = dict(documents, L1=dict(profile, entries=[
            dict(row, state='active') if row['id'] == selected[1] else row for row in profile['entries']]))
    result = []
    for pair in registry_policy.find_conflicts(projection):
        refs = [(row['area'], row['id']) for row in pair['entries']]
        areas = {r[0] for r in refs}
        if areas not in ({'L0', 'L1'}, {'L1', 'L2'}):
            continue
        sides = [{'area': ref[0], 'declared_rank': ranks.get(ref), **{f: index[ref][f] for f in _FIELDS}} for ref in refs]
        restrictions = ['owner_decision_required']
        if 'L0' in areas:
            restrictions.append('system_immutable')
            if any(r['area'] == 'L0' and r['kind'] == 'constraint' for r in sides):
                restrictions.append('system_constraint_not_overridable')
        result.append({'key': pair['key'], 'scope': pair['scope'],
                       'comparison': 'prospective' if selected in refs else 'active', 'entries': sides,
                       'restrictions': restrictions, 'options': _options(sides)})
    return result


def review_conflicts(*, system, profile, project, priorities=(), candidate_id=None, target='stand'):
    """Сравнить структурные пары L1↔L0/L2, сохраняя обе стороны и отсутствие решения."""
    if type(target) is not str or target != 'stand':
        _fail('target', 'stand_only')
    names = {'L0': ('system', system), 'L1': ('profile', profile), 'L2': ('project', project)}
    documents = {area: _registry(raw, area, where) for area, (where, raw) in names.items()}
    index = {(area, row['id']): row for area, doc in documents.items() for row in doc['entries']}
    ranks, rank_digest = _priorities(priorities, index)
    candidate = _candidate(candidate_id, index)
    conflicts = _pairs(documents, index, ranks, candidate)
    outcome = ('owner_decision_required' if conflicts else
               'unassessed_candidate' if candidate is not None and candidate['comparison'] == 'no_key' else
               'no_structural_conflict')
    return {'review_format': REVIEW_FORMAT, 'outcome': outcome, 'conflicts': conflicts, 'candidate': candidate,
            'write_allowed': False, 'inputs_sha256': {area: _digest(v[1]) for area, v in names.items()},
            'priorities_sha256': rank_digest}
