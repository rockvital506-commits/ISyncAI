"""Переносимое намерение и диагностика переданных байтов; без ФС и без выполнения."""
from __future__ import annotations

import base64
import binascii
import hashlib
import json

from . import move_preview, schema_v2
from .registry_policy import StoreError

FORMAT = 1
MAX_INTENT = 16 * 1024 * 1024
_MAX_INPUT = move_preview.MAX_REGISTRY
_FIELDS = {'intent_format','source','target','entry_id','candidate','portability_context','before','after'}


def _encode(raw):
    return base64.b64encode(raw).decode('ascii')


def _decode(value):
    if type(value) is not str or len(value) > ((_MAX_INPUT + 2)//3)*4:
        raise ValueError('invalid bytes')
    raw = base64.b64decode(value, validate=True)
    if len(raw) > _MAX_INPUT or _encode(raw) != value:
        raise ValueError('invalid bytes')
    return raw


def _wire(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def _context(source, value):
    if source == 'L1' and value is not None:
        raise StoreError('invalid_context', 'portability_context')


def build(inputs, *, source, target, entry_id, candidate, portability_context):
    """Сформировать пакет и preview только из явных bytes. Не утверждает разрешение или согласие."""
    _context(source, portability_context)
    preview = move_preview.preview_move(inputs, source=source, target=target, entry_id=entry_id,
                                        candidate=candidate, portability_context=portability_context)
    after = {row['area']: row['after_utf8'].encode('utf-8') for row in preview['diffs']}
    if any(len(raw) > _MAX_INPUT for raw in after.values()):
        raise StoreError('move_intent_too_large', 'after')
    doc = {'intent_format':FORMAT, 'source':source, 'target':target, 'entry_id':entry_id,
           'candidate':preview['target_entry'], 'portability_context':portability_context,
           'before':{k:_encode(v) for k,v in inputs.items()}, 'after':{k:_encode(v) for k,v in after.items()}}
    try:
        raw = _wire(doc)
    except (TypeError, ValueError, UnicodeError, RecursionError) as error:
        raise StoreError('move_intent_invalid', 'intent') from error
    if len(raw) > MAX_INTENT:
        raise StoreError('move_intent_too_large', 'intent')
    return {'outcome':'intent_draft_only', 'intent_sha256':hashlib.sha256(raw).hexdigest(),
            'bytes':len(raw), 'preview':preview, 'authorization':'not_checked',
            'confirmation':'not_implemented', 'publication':'not_implemented',
            'apply':'not_implemented', 'recovery':'not_implemented'}, raw


def _verified(raw, pin):
    if type(raw) is not bytes or len(raw) > MAX_INTENT:
        raise StoreError('move_intent_invalid', 'intent')
    if (type(pin) is not str or len(pin) != 64 or any(c not in '0123456789abcdef' for c in pin)):
        raise StoreError('move_intent_pin_required', 'intent_pin')
    if hashlib.sha256(raw).hexdigest() != pin:
        raise StoreError('move_intent_pin_mismatch', 'intent_pin')
    try:
        doc = schema_v2.parse_json(raw)
        if (type(doc) is not dict or set(doc) != _FIELDS or type(doc['intent_format']) is not int
                or doc['intent_format'] != FORMAT or _wire(doc) != raw):
            raise ValueError('shape')
        source,target=doc['source'],doc['target']
        if type(source) is not str or type(target) is not str or (source,target) not in (('L1','L2'),('L2','L1')):
            raise ValueError('direction')
        if (type(doc['before']) is not dict or set(doc['before']) != {'L0','L1','L2'}
                or type(doc['after']) is not dict or set(doc['after']) != {source,target}):
            raise ValueError('areas')
        before = {k:_decode(v) for k,v in doc['before'].items()}
        after = {k:_decode(v) for k,v in doc['after'].items()}
        _context(source,doc['portability_context'])
        preview=move_preview.preview_move(before,source=source,target=target,entry_id=doc['entry_id'],
                                          candidate=doc['candidate'],portability_context=doc['portability_context'])
        calculated={row['area']:row['after_utf8'].encode('utf-8') for row in preview['diffs']}
        if calculated != after: raise ValueError('after mismatch')
        return doc, before, after
    except (schema_v2.SchemaError, StoreError, TypeError, ValueError, UnicodeError, RecursionError,
            KeyError, binascii.Error) as error:
        raise StoreError('move_intent_invalid', 'intent') from error


def assess(raw, *, intent_pin, observed):
    """Сравнить переданные bytes с закреплённым intent. Не читает marker, не восстанавливает."""
    doc,before,after = _verified(raw,intent_pin)
    if (type(observed) is not dict or set(observed) != {'L0','L1','L2'} or
            any(type(v) is not bytes or len(v) > _MAX_INPUT for v in observed.values())):
        raise StoreError('move_observation_invalid', 'observed')
    source,target=doc['source'],doc['target']
    if observed['L0'] != before['L0'] or any(observed[a] not in (before[a],after[a]) for a in (source,target)):
        state='foreign_or_changed'
    elif observed[source] == after[source] and observed[target] == before[target]:
        state='impossible_order'
    elif observed[target] == before[target]:
        state='before_both'
    elif observed[source] == before[source]:
        state='target_after_source_before'
    else:
        state='after_both'
    return {'outcome':'observation_only', 'state':state, 'source':source, 'target':target,
            'intent_sha256':intent_pin, 'observed_sha256':{k:hashlib.sha256(v).hexdigest() for k,v in observed.items()},
            'marker':'not_checked', 'authorization':'not_checked', 'origin':'not_verified',
            'durability':'not_checked', 'snapshot':'not_verified', 'recovery':'not_implemented'}
