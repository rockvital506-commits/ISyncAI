"""Допуск однообластных операций и структурные противоречия в проверенных данных v2."""
from itertools import combinations


class StoreError(ValueError):
    def __init__(self, code, where, *, schema=None, details=None):
        self.code, self.where, self.schema, self.details = code, where, schema, details
        super().__init__(f'{code} at {where}')

    def diagnostic(self):
        result = {'code': self.code, 'where': self.where}
        if self.schema is not None:
            result['schema'] = {'stage': self.schema.stage, 'code': self.schema.code, 'path': self.schema.path}
        if self.details is not None:
            result['details'] = self.details
        return result


_AREAS = ('L0', 'L1', 'L2')
# operation: (мутация по модели, области с реализованным путём в порте).
# «Регистрация» называется create. Внутреннее read не подменяет пользовательский list.
_MUTABLE = ('L1', 'L2')
_OPERATIONS = {
    'read': (False, _AREAS),
    'create': (True, _MUTABLE),
    'list': (False, _MUTABLE),
    'edit': (True, _MUTABLE),
    'activate': (True, _MUTABLE),
    'suspend': (True, _MUTABLE),
    'resume': (True, _MUTABLE),
    'revoke': (True, _MUTABLE),
    'delete': (True, _MUTABLE),
}


def _cell(operation, target):
    mutates, implemented = _OPERATIONS[operation]
    if mutates and target == 'L0':
        return {'state': 'forbidden', 'code': 'system_immutable'}
    if target not in implemented:
        return {'state': 'planned', 'code': 'operation_unavailable'}
    return {'state': 'available', 'code': None}


def operation_matrix():
    """Снимок политики порта, не проверка полномочий или состояния файлов."""
    return {op: {area: _cell(op, area) for area in _AREAS} for op in _OPERATIONS}


def check_operation(operation, *, target):
    """Допустить реализованную пару или вернуть код её ограничения. Не пишет."""
    if type(operation) is not str or operation not in _OPERATIONS:
        raise StoreError('unknown_operation', 'operation')
    if type(target) is not str or target not in _AREAS:
        raise StoreError('unknown_area', 'target')
    cell = _cell(operation, target)
    if cell['state'] == 'forbidden':
        raise StoreError(cell['code'], target)
    if cell['state'] == 'planned':
        raise StoreError(cell['code'], 'operation')
    return cell


def _shared_scope(left, right):
    a = () if left == '.' else tuple(left.split('/'))
    b = () if right == '.' else tuple(right.split('/'))
    if a[:len(b)] == b:
        return left
    if b[:len(a)] == a:
        return right
    return None


def active_entries(document):
    """Фильтр одного реестра, не объединение политик и не исполнение текста."""
    entries = document['entries']
    parents = {row['id'] for row in entries if row['kind'] == 'contract' and row['state'] == 'active'}
    return [row for row in entries if row['state'] == 'active'
            and (row['kind'] == 'contract' or row['parent'] in parents)]


def find_conflicts(documents):
    """Пары противоречий в проверенных реестрах; никаких эффективных записей или решений."""
    by_key = {}
    for area in _AREAS:
        for row in sorted(active_entries(documents[area]), key=lambda item: item['id']):
            if row['kind'] != 'contract' and 'key' in row:
                description = {'area': area, **{field: row[field] for field in ('id', 'scope', 'value', 'text')}}
                by_key.setdefault(row['key'], []).append(description)

    conflicts = []
    for key, entries in sorted(by_key.items()):
        for left, right in combinations(entries, 2):
            if left['value'] == right['value']:
                continue
            scope = _shared_scope(left['scope'], right['scope'])
            if scope is not None:
                conflicts.append({'key': key, 'scope': scope, 'entries': [left, right]})
    return conflicts
