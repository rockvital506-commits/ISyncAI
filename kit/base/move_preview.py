"""Гипотетический план перемещения в памяти; не пишет и не выполняет перенос."""
import copy
from difflib import diff_bytes, unified_diff
from hashlib import sha256
from io import BytesIO
import json

from . import project_specificity, registry_journal, registry_policy, schema_v2
from .registry_policy import StoreError

MAX_REGISTRY = 2_097_152
MAX_CANDIDATE = 65_536


def _parse(inputs):
    if type(inputs) is not dict or inputs.keys() != {'L0', 'L1', 'L2'}:
        raise StoreError('invalid_inputs', 'inputs')
    documents, journals = {}, {}
    for area in ('L0', 'L1', 'L2'):
        raw = inputs[area]
        if type(raw) is not bytes or len(raw) > MAX_REGISTRY:
            raise StoreError('invalid_inputs', area)
        try:
            parsed = schema_v2.parse_json(raw)
            if area == 'L0':
                schema_v2.validate_registry(parsed, expected_area=area)
                documents[area] = parsed
            else:
                documents[area], journals[area] = registry_journal.unpack_registry(parsed, area=area)
        except (schema_v2.SchemaError, TypeError, ValueError, RecursionError) as error:
            raise StoreError('invalid_registry', area) from error
    try:
        schema_v2.validate_catalog(documents)
    except (schema_v2.SchemaError, TypeError, ValueError, RecursionError) as error:
        raise StoreError('invalid_catalog', 'inputs') from error
    return documents, journals


def _pack(before, journal, new_entries, *, operation, old_entry, new_entry):
    after = dict(before, entries=new_entries, revision=before['revision'] + 1)
    try:
        schema_v2.validate_registry(after, expected_area=before['area'])
        result = registry_journal.with_change(after, before, journal, operation=operation,
                                               before=old_entry, after=new_entry)
        registry_journal.unpack_registry(result, area=before['area'])
        raw = (json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf-8')
    except (schema_v2.SchemaError, TypeError, ValueError, KeyError, RecursionError) as error:
        raise StoreError('invalid_result', before['area']) from error
    return after, result, raw


def _diff(area, before, after, prior_revision, decision):
    display = b''.join(line if line.endswith(b'\n') else line + b'\n\\ No newline at end of file\n'
                       for line in diff_bytes(unified_diff, list(BytesIO(before)), list(BytesIO(after)),
                                              fromfile=('a/'+area).encode(), tofile=('b/'+area).encode()))
    return {'area': area, 'revision': {'from': prior_revision, 'to': prior_revision+1},
            'before_sha256': sha256(before).hexdigest(), 'after_sha256': sha256(after).hexdigest(),
            'unified': display.decode('utf-8'), 'after_utf8': after.decode('utf-8'),
            'hypothetical_decision': decision}


def preview_move(inputs, *, source, target, entry_id, candidate, portability_context=None):
    """Только данные: показать обе стороны и явную редакцию, без записи/билета/применения.

    inputs содержит точные байты L0/L1/L2. candidate — полная явно выбранная запись целевой
    области, не сгенерированная автоматически. План не может быть передан в apply.
    """
    if (type(source) is not str or type(target) is not str
            or (source, target) not in (('L1', 'L2'), ('L2', 'L1'))):
        raise StoreError('move_direction_invalid', 'direction')
    if type(entry_id) is not str or schema_v2._ID.fullmatch(entry_id) is None:
        raise StoreError('entry_id_invalid', 'entry_id')
    docs, journals = _parse(inputs)
    if registry_policy.find_conflicts(docs):
        raise StoreError('rule_conflict', 'inputs')
    original = next((e for e in docs[source]['entries'] if e['id'] == entry_id), None)
    if original is None:
        raise StoreError('entry_not_found', source)
    children = sorted(e['id'] for e in docs[source]['entries'] if e['parent'] == entry_id)
    if children:
        raise StoreError('source_has_children', source, details={'children': children})
    if type(candidate) is not dict:
        raise StoreError('invalid_entry', target)
    try:
        schema_v2._entry_shape(candidate, target, '')
        if sum(len(value.encode('utf-8')) for value in candidate.values() if type(value) is str) > MAX_CANDIDATE:
            raise StoreError('invalid_entry', target)
    except StoreError:
        raise
    except (schema_v2.SchemaError, TypeError, ValueError, RecursionError) as error:
        raise StoreError('invalid_entry', target) from error
    candidate = copy.deepcopy(candidate)
    if original['kind'] != candidate['kind']:
        raise StoreError('kind_change_forbidden', target)
    if (any(e['id'] == candidate['id'] for e in docs[target]['entries'])
            or registry_journal.is_retired(journals[target], candidate['id'])):
        raise StoreError('target_id_unavailable', target)
    if source == 'L2':
        inspection = project_specificity.inspect_entry(dict(candidate, authority='project_owner'),
                                                        context=portability_context)
        if inspection['outcome'] == 'invalid_input':
            raise StoreError(inspection['code'], 'portability_context')
        if inspection['findings']:
            raise StoreError('project_specific', target, details={'findings': inspection['findings']})
    else:
        inspection = None
    source_entries = [e for e in docs[source]['entries'] if e['id'] != entry_id]
    source_doc, source_pack, source_bytes = _pack(docs[source], journals[source], source_entries,
                                                  operation='delete', old_entry=original, new_entry=None)
    target_entries = [*docs[target]['entries'], candidate]
    target_doc, target_pack, target_bytes = _pack(docs[target], journals[target], target_entries,
                                                  operation='create', old_entry=None, new_entry=candidate)
    future = dict(docs, **{source: source_doc, target: target_doc})
    if registry_policy.find_conflicts(future):
        raise StoreError('rule_conflict', 'proposed_result')
    diffs = [_diff(source, inputs[source], source_bytes, docs[source]['revision'],
                   source_pack['journal']['decisions'][-1]),
             _diff(target, inputs[target], target_bytes, docs[target]['revision'],
                   target_pack['journal']['decisions'][-1])]
    def parent_of(document, entry):
        return next((copy.deepcopy(row) for row in document['entries'] if row['id'] == entry['parent']), None)
    effectiveness = {'source_before': any(row['id'] == original['id'] for row in registry_policy.active_entries(docs[source])),
                     'target_after': any(row['id'] == candidate['id'] for row in registry_policy.active_entries(target_doc))}
    return {'move_preview_format': 1, 'outcome': 'hypothetical_only', 'source': source, 'target': target,
            'inputs_sha256': {area: sha256(inputs[area]).hexdigest() for area in ('L0','L1','L2')},
            'source_entry': copy.deepcopy(original), 'target_entry': copy.deepcopy(candidate),
            'source_parent': parent_of(docs[source], original), 'target_parent': parent_of(target_doc, candidate),
            'structural_effectiveness': effectiveness,
            'changes': {field: {'before': original.get(field), 'after': candidate.get(field)}
                        for field in sorted(set(original)|set(candidate)) if original.get(field) != candidate.get(field)},
            'portability': inspection if inspection is not None else {'status':'not_applicable'},
            'diffs': diffs, 'source_removed_in_hypothesis': True, 'transaction_history': 'not_implemented',
            'text_conflicts': 'not_checked', 'authorization': 'not_checked', 'confirmation': 'not_implemented',
            'apply': 'not_implemented', 'recovery': 'not_implemented'}


def preview_workspace(layout, *, source, target, entry_id, candidate, portability_context):
    """Согласованный штатный снимок для preview; запись и выдача билета отсутствуют."""
    if source == 'L1' and portability_context is not None:
        raise StoreError('invalid_context', 'portability_context')
    from . import registry_store
    current = registry_store._load(layout)
    return preview_move(current.raw, source=source, target=target, entry_id=entry_id,
                        candidate=candidate, portability_context=portability_context)
