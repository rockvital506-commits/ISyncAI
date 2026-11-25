#!/usr/bin/env python3
"""Абстрактные атомарные шаги, только в памяти; не реализация хранилища Kit."""
from dataclasses import dataclass

AREAS = ('L0', 'L1', 'L2')


@dataclass(frozen=True)
class Cell:
    content: bytes
    epoch: int

    def __post_init__(self):
        if type(self.content) is not bytes or type(self.epoch) is not int or self.epoch < 0:
            raise ValueError('invalid_cell')


@dataclass(frozen=True)
class State:
    cells: tuple

    def __post_init__(self):
        if type(self.cells) is not tuple or len(self.cells) != len(AREAS) or any(type(c) is not Cell for c in self.cells):
            raise ValueError('invalid_state')

    def get(self, area):
        if area not in AREAS: raise ValueError('invalid_area')
        return self.cells[AREAS.index(area)]


@dataclass(frozen=True)
class Plan:
    inputs: State
    target: str
    after: bytes

    def __post_init__(self):
        if type(self.inputs) is not State or self.target not in ('L1', 'L2') or type(self.after) is not bytes:
            raise ValueError('invalid_plan')


def matches(state, plan, *, epochs):
    """Сравнение трёх абстрактных значений, а не хеш, проверка путей или прав."""
    if type(state) is not State or type(plan) is not Plan or type(epochs) is not bool:
        raise ValueError('invalid_comparison')
    if epochs:
        return state == plan.inputs
    return all(a.content == b.content for a, b in zip(state.cells, plan.inputs.cells))


def write_unconditionally(state, area, content):
    """Один идеальный шаг, увеличение локального счётчика — предпосылка модели."""
    if type(state) is not State or area not in AREAS or type(content) is not bytes:
        raise ValueError('invalid_write')
    i = AREAS.index(area); current = state.cells[i]
    cells = list(state.cells); cells[i] = Cell(content, current.epoch + 1)
    return State(tuple(cells))


def compare_and_write(state, plan, *, epochs):
    """Идеализированная транзакция: сравнить ВСЕ ячейки и записать цель за один шаг.

    Возвращает (новое состояние, 'applied'/'stale'). Такая транзакция не реализована в Kit.
    """
    if not matches(state, plan, epochs=epochs):
        return state, 'stale'
    return write_unconditionally(state, plan.target, plan.after), 'applied'
