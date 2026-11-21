"""Одна карточка → read-only дифф → отдельное подтверждение → существующий порт записи."""
from dataclasses import dataclass
from difflib import diff_bytes, unified_diff
from hashlib import sha256
from io import BytesIO
import json
from secrets import token_hex

from . import registry_store
from .operation_card import compile_prompt
from .profile_journal import canonical_bytes
from .registry_policy import StoreError, check_operation

PLAN_FORMAT = 1


@dataclass(frozen=True)
class _Pending:
    ticket: str
    shown: bytes
    preview: registry_store.CreatePreview


def _same_json(got, expected):
    # Строгие типы нужны и для bool/int, и для изменённых контейнеров после передачи вызывающему коду.
    if type(got) is not type(expected):
        return False
    if type(expected) is dict:
        return (all(type(k) is str for k in got) and got.keys() == expected.keys()
                and all(_same_json(got[k], v) for k, v in expected.items()))
    if type(expected) is list:
        return len(got) == len(expected) and all(_same_json(a, b) for a, b in zip(got, expected))
    return got == expected


def _checked_card(card):
    if type(card) is not dict or type(card.get('request')) is not str:
        raise StoreError('card_mismatch', 'card')
    try:
        expected = compile_prompt(card['request'])
    except (TypeError, ValueError) as error:
        raise StoreError('card_mismatch', 'card') from error
    if not _same_json(card, expected):
        raise StoreError('card_mismatch', 'card')
    return expected


def _diff(preview):
    native = preview.store_plan
    rel = native['registry']
    before, after = preview.before, preview.after
    lines = diff_bytes(unified_diff, list(BytesIO(before)), list(BytesIO(after)),
                       fromfile=('a/' + rel).encode('utf-8'), tofile=('b/' + rel).encode('utf-8'))
    display = b''.join(line if line.endswith(b'\n') else line + b'\n\\ No newline at end of file\n' for line in lines)
    return {'file': rel, 'revision': dict(native['revision']), 'before_sha256': sha256(before).hexdigest(),
            'after_sha256': sha256(after).hexdigest(), 'unified': display.decode('utf-8')}


class PlanSession:
    """Один ожидающий план в памяти. Не идентификация пользователя и не разрешение ОС."""

    def __init__(self, layout, *, profile_id):
        if type(profile_id) is not str or not profile_id:
            raise ValueError('profile_id: ожидается ID доверенной привязки')
        self._layout = layout
        self._profile_id = profile_id
        self._pending = None

    def plan(self, card):
        """Показать точный дифф без записи. Любая новая попытка отзывает старый билет."""
        self._pending = None
        card = _checked_card(card)
        result = {'plan_format': PLAN_FORMAT, 'dry_run': True, 'card': card}
        if card['outcome'] == 'missing_params':
            return dict(result, outcome='missing_params')
        if card['outcome'] == 'rejected':
            code = card['code']
            raise StoreError(code, 'L0' if code == 'system_immutable' else 'card/params/contract')
        operation, params = card['operation'], card['params']
        target = params['target']
        check_operation(operation, target=target)
        # Даже расширение матрицы не подключает новый исполнитель автоматически.
        if (operation, target) != ('create', 'L1'):
            raise StoreError('operation_unavailable', 'operation')
        if params['profile'] != self._profile_id:
            raise StoreError('profile_mismatch', 'card/params/profile')
        entry = {k: params[k] for k in ('kind', 'state', 'scope', 'title', 'text', 'basis', 'criterion')}
        entry.update(id=params['entry_id'], parent=params.get('contract'), authority='profile_owner')
        preview = registry_store.preview_create(self._layout, entry, target=target)
        result.update(diff=_diff(preview), inputs_sha256=dict(preview.inputs_sha256))
        if preview.store_plan.get('outcome') == 'no_change':
            return dict(result, outcome='no_change')
        ticket = token_hex(32)
        result.update(outcome='planned', ticket=ticket)
        self._pending = _Pending(ticket, canonical_bytes(result), preview)
        return result

    def apply(self, plan, *, confirmed_ticket=None):
        """Писать только по отдельно переданному билету именно этого выданного плана."""
        if type(confirmed_ticket) is not str or not confirmed_ticket:
            raise StoreError('confirmation_required', 'confirmed_ticket')
        if type(plan) is not dict:
            raise StoreError('plan_mismatch', 'plan')
        if type(plan.get('ticket')) is not str or plan['ticket'] != confirmed_ticket:
            raise StoreError('confirmation_required', 'confirmed_ticket')
        pending = self._pending
        if pending is None or pending.ticket != confirmed_ticket:
            raise StoreError('ticket_unknown', 'ticket')
        if not _same_json(plan, json.loads(pending.shown)):
            raise StoreError('plan_mismatch', 'plan')
        # После проверки расходуется одна попытка. Ни сбой, ни дрейф не создают новую выдачу автоматически.
        self._pending = None
        preview = pending.preview
        native = preview.store_plan
        status = registry_store.apply_create(self._layout, native, confirmed_ticket=native['ticket'], preview=preview)
        return {'outcome': 'applied', 'status': status}
