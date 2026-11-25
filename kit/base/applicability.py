"""Только чтение: структурно применимые сущности к одному явно заданному scope."""
from copy import deepcopy
from . import registry_policy, registry_store, schema_v2
from .registry_policy import StoreError


def _covers(scope, selected):
    return scope == '.' or scope == selected or selected.startswith(scope + '/')


def applicable(layout, *, scope):
    """Не выбирает scope задачи и не проверяет её смысл, права и фактическое применение."""
    try:
        schema_v2._portable_path(scope, '', allow_dot=True)
    except (schema_v2.SchemaError, TypeError, ValueError) as error:
        raise StoreError('scope_invalid', 'scope') from error
    current = registry_store._load(layout)
    conflicts = [c for c in registry_policy.find_conflicts(current.documents) if _covers(c['scope'], scope)]
    common = {'applicability_format':1, 'scope':scope, 'inputs_sha256':dict(current.inputs_sha256),
              'coverage':'selected_scope_only', 'text_conflicts':'not_checked',
              'authorization':'not_checked', 'agent_application':'not_checked'}
    if conflicts:
        return dict(common, outcome='structural_conflict', conflicts=deepcopy(conflicts), entries=[])
    rows = []
    for area in ('L0','L1','L2'):
        doc = current.documents[area]
        for entry in sorted(registry_policy.active_entries(doc), key=lambda item:item['id']):
            if _covers(entry['scope'], scope):
                rows.append({'area':area, 'source_sha256':current.inputs_sha256[area],
                             'source_version':doc['release_version'] if area=='L0' else doc['revision'],
                             'entry':deepcopy(entry)})
    unstructured = sum(1 for row in rows if row['entry']['kind'] != 'contract' and 'key' not in row['entry'])
    return dict(common, outcome='applicable', entries=rows, conflicts=[], unstructured_active_entries=unstructured)
