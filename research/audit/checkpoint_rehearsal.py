#!/usr/bin/env python3
"""Абстрактная модель контрольной точки и прерывания, не политика и не обновление Kit."""
from dataclasses import dataclass
import re

DIGEST = re.compile(r'[0-9a-f]{64}')
MAX_SEQUENCE = 2**63 - 1


@dataclass(frozen=True)
class Release:
    # Условная последовательность и идентификатор. Не version и не реальная подпись.
    sequence: int
    digest: str

    def __post_init__(self):
        if (type(self.sequence) is not int or not 1 <= self.sequence <= MAX_SEQUENCE
                or type(self.digest) is not str or DIGEST.fullmatch(self.digest) is None):
            raise ValueError('release_invalid')


@dataclass(frozen=True)
class State:
    # Ни одна ячейка не считается защищённой самой этой моделью.
    checkpoint: Release | None
    active: Release | None

    def __post_init__(self):
        if (self.checkpoint is not None and type(self.checkpoint) is not Release
                or self.active is not None and type(self.active) is not Release):
            raise ValueError('state_invalid')


def observe(state):
    """Только классифицировать пару ячеек; совпадение не означает разрешение запуска."""
    if type(state) is not State:
        raise ValueError('state_invalid')
    checkpoint, active = state.checkpoint, state.active
    if checkpoint is None and active is None:
        relation = 'both_missing'
    elif checkpoint is None:
        relation = 'checkpoint_missing'
    elif active is None:
        relation = 'active_missing'
    elif checkpoint.sequence > active.sequence:
        relation = 'active_behind'
    elif checkpoint.sequence < active.sequence:
        relation = 'active_ahead'
    elif checkpoint.digest != active.digest:
        relation = 'same_sequence_conflict'
    else:
        relation = 'matches_checkpoint'
    return {'relation': relation, 'checkpoint_trust': 'assumed_not_verified',
            'signature': 'not_checked', 'authorization': 'not_checked',
            'data_preservation': 'not_checked', 'execution': 'not_implemented',
            'recovery': 'not_implemented'}


def simulate(old, new, *, order, completed_steps):
    """Два идеальных раздельных присваивания с разрывами между ними, только в памяти."""
    if type(old) is not Release or type(new) is not Release or new.sequence <= old.sequence:
        raise ValueError('transition_invalid')
    if order not in ('checkpoint_first', 'active_first') or type(order) is not str:
        raise ValueError('order_invalid')
    if type(completed_steps) is not int or not 0 <= completed_steps <= 2:
        raise ValueError('cut_invalid')
    checkpoint, active = old, old
    steps = ('checkpoint', 'active') if order == 'checkpoint_first' else ('active', 'checkpoint')
    for target in steps[:completed_steps]:
        if target == 'checkpoint':
            checkpoint = new
        else:
            active = new
    return State(checkpoint, active)
