"""Исследовательская модель D08 в памяти: не файловый протокол и не выполнение переноса."""
from __future__ import annotations

import copy
import hashlib
import json

from kit.base import move_preview


def _hash(raw): return hashlib.sha256(raw).hexdigest()


class ModelError(ValueError):
    pass


def prepare(inputs, *, source, target, entry_id, candidate, portability_context=None):
    """Полный preview плюс модельный пакет, без чтения/записи ФС или разрешения."""
    preview = move_preview.preview_move(inputs, source=source, target=target, entry_id=entry_id,
                                        candidate=candidate, portability_context=portability_context)
    after = {row['area']: row['after_utf8'].encode('utf-8') for row in preview['diffs']}
    intent = {'format':1, 'source':source, 'target':target, 'before':copy.deepcopy(inputs),
              'after':after, 'preview':preview, 'portability_context':copy.deepcopy(portability_context)}
    return copy.deepcopy(preview), intent


def _validate(intent):
    """Связать before/after с полным preview; самоподписанный хеш не доказывает авторства."""
    try:
        if type(intent) is not dict or set(intent) != {'format','source','target','before','after','preview','portability_context'}:
            raise ModelError('intent_invalid')
        if type(intent['format']) is not int or intent['format'] != 1: raise ModelError('intent_invalid')
        source, target, before, after, preview = (intent[k] for k in ('source','target','before','after','preview'))
        if (source,target) not in (('L1','L2'),('L2','L1')) or type(before) is not dict or set(before) != {'L0','L1','L2'}:
            raise ModelError('intent_invalid')
        if type(after) is not dict or set(after) != {source,target} or any(type(v) is not bytes for v in [*before.values(),*after.values()]):
            raise ModelError('intent_invalid')
        if (type(preview) is not dict or preview['source'] != source or preview['target'] != target
                or preview['inputs_sha256'] != {k:_hash(v) for k,v in before.items()}):
            raise ModelError('intent_invalid')
        rows=preview['diffs']
        if (type(rows) is not list or len(rows)!=2 or {r['area'] for r in rows} != {source,target}):
            raise ModelError('intent_invalid')
        for row in rows:
            area=row['area']
            if (row['before_sha256'] != _hash(before[area]) or row['after_sha256'] != _hash(after[area])
                    or row['after_utf8'].encode('utf-8') != after[area]):
                raise ModelError('intent_invalid')
        regenerated = move_preview.preview_move(before, source=source, target=target,
                      entry_id=preview['source_entry']['id'], candidate=preview['target_entry'],
                      portability_context=intent['portability_context'])
        if regenerated != preview: raise ModelError('intent_invalid')
    except (KeyError,TypeError,ValueError,AttributeError,UnicodeError,RecursionError,
            move_preview.StoreError) as error:
        if isinstance(error,ModelError): raise
        raise ModelError('intent_invalid') from error


def start(state, preview, intent, *, confirmed):
    """Модель одного атомарного устойчивого сохранения intent, не системный вызов."""
    _validate(intent)
    if confirmed is not True: raise ModelError('confirmation_required')
    if state['intent'] is not None: raise ModelError('pending_intent')
    if preview != intent['preview']: raise ModelError('preview_mismatch')
    if state['registries'] != intent['before']: raise ModelError('stale_inputs')
    state['intent'] = copy.deepcopy(intent)


def advance(state):
    """Один идеализированный атомарный шаг или идемпотентный готовый результат.

    Заранее сверяем обе области и L0; только целевую сторону меняем первой. Предполагается,
    что в течение всего вызова не может вмешаться ни один читатель/писатель.
    """
    intent=state['intent']
    if intent is None: raise ModelError('intent_missing')
    _validate(intent)
    source,target,before,after=(intent[k] for k in ('source','target','before','after'))
    current=state['registries']
    if type(current) is not dict or set(current) != {'L0','L1','L2'} or current['L0'] != before['L0']:
        raise ModelError('foreign_state')
    src,dst=current[source],current[target]
    if src not in (before[source],after[source]) or dst not in (before[target],after[target]):
        raise ModelError('foreign_state')
    if src == after[source] and dst == before[target]: raise ModelError('impossible_order')
    if dst == before[target]:
        current[target]=after[target]; return 'target_written'
    if src == before[source]:
        current[source]=after[source]; return 'source_deleted'
    return 'complete_intent_retained'
