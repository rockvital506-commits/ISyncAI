"""Гипотетические шаги для проверенных bytes; никакой файловой записи или recovery."""
from __future__ import annotations

from . import move_intent


def plan(raw, *, intent_pin, observed):
    """Показать обязательные барьеры и следующий гипотетический шаг, не разрешая его."""
    result = move_intent.assess(raw, intent_pin=intent_pin, observed=observed)
    state, source, target = result['state'], result['source'], result['target']
    if state == 'before_both':
        next_step = 'target_replace'
        barriers = ['verify_and_sync_marker_and_parent']
        area = target
    elif state == 'target_after_source_before':
        next_step = 'source_replace'
        barriers = ['verify_and_sync_marker_and_parent', 'verify_and_sync_target_and_parent']
        area = source
    elif state == 'after_both':
        next_step = 'no_registry_replace'
        barriers = ['verify_and_sync_marker_and_parent', 'verify_and_sync_target_and_parent',
                    'verify_and_sync_source_and_parent']
        area = None
    else:
        next_step, barriers, area = 'stop', [], None
    return {'outcome': 'hypothetical_only', 'state': state, 'source': source, 'target': target,
            'intent_sha256': intent_pin, 'observed_sha256': result['observed_sha256'],
            'next_step': next_step, 'area': area, 'required_prior_barriers': barriers,
            'marker': 'not_checked_or_removed', 'snapshot': 'not_verified',
            'origin': 'not_verified', 'authorization': 'not_checked',
            'confirmation': 'not_implemented', 'execution': 'not_implemented',
            'recovery': 'not_implemented', 'durability': 'not_checked'}
