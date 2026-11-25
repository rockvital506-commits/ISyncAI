"""Опытная подготовка двух контекстов по явному выбору; выдача агенту не реализована."""
from . import applicability, schema_v2
from .registry_policy import StoreError

# Локальная привязка к байтам кандидатного L0, не доверенный внешний источник.
SYSTEM_L0_SHA256 = '8249a721c0f775612313f3a9d8f33877793d04706c1f797c3fedd3924ca3f006'
_MAX_CHOICES = 4096


def _choices(value):
    if type(value) is not dict or value.keys() != {'include', 'exclude'}:
        raise StoreError('context_choices_invalid', 'choices')
    result = {}
    for choice in ('include', 'exclude'):
        rows = value[choice]
        if type(rows) is not list or len(rows) > _MAX_CHOICES:
            raise StoreError('context_choices_invalid', 'choices')
        for row in rows:
            if (type(row) is not dict or row.keys() != {'area','id'}
                    or type(row['area']) is not str or row['area'] not in ('L1','L2')
                    or type(row['id']) is not str or schema_v2._ID.fullmatch(row['id']) is None):
                raise StoreError('context_choices_invalid', 'choices')
            key = row['area'], row['id']
            if key in result:
                raise StoreError('context_choices_invalid', 'choices')
            result[key] = choice
    return result


def prepare(layout, *, mode, scope, choices):
    """Показать гипотетический контекст на ревью, не исполняя и не доставляя его агенту."""
    if type(mode) is not str or mode not in ('project','kit'):
        raise StoreError('context_mode_invalid', 'mode')
    decisions = _choices(choices)
    report = applicability.applicable(layout, scope=scope)
    if report['inputs_sha256']['L0'] != SYSTEM_L0_SHA256:
        raise StoreError('context_system_unbound', 'L0')
    if report['outcome'] != 'applicable':
        # Для показа обеих сторон существует явный applicable; здесь не выдаём контекст.
        raise StoreError('context_conflict', 'scope')
    entries = report['entries']
    by_ref = {(row['area'], row['entry']['id']):row for row in entries if row['area'] != 'L0'}
    if set(decisions) != set(by_ref):
        raise StoreError('context_choices_incomplete', 'choices')
    for ref,row in by_ref.items():
        entry = row['entry']
        if entry['kind'] in ('constraint','protocol') and decisions[ref] != 'include':
            raise StoreError('context_mandatory_excluded', 'choices')
        if decisions[ref] == 'include' and entry['parent'] is not None:
            if decisions.get((ref[0],entry['parent'])) != 'include':
                raise StoreError('context_parent_excluded', 'choices')
    opposite = 'SYS-KIT-MODE' if mode == 'project' else 'SYS-PROJECT-MODE'
    selected = [row for row in entries if (row['area'] == 'L0' and row['entry']['id'] != opposite)
                or (row['area'] != 'L0' and decisions[(row['area'],row['entry']['id'])] == 'include')]
    return {'context_format':1, 'outcome':'review_required', 'mode':mode, 'scope':scope,
            'inputs_sha256':report['inputs_sha256'], 'entries':selected,
            'excluded_count':sum(value == 'exclude' for value in decisions.values()),
            'safety_completeness':'not_checked', 'text_conflicts':'not_checked',
            'scope_completeness':'not_checked', 'minimality':'not_checked',
            'origin':'not_verified', 'authorization':'not_checked', 'delivery':'not_implemented',
            'agent_application':'not_checked'}
