"""Карточка: просмотр либо точный дифф и согласованная запись L1/L2."""
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

PLAN_FORMAT = 4
REPLACEMENT_NOTICE = (
    'Замена файла может изменить ACL и другие метаданные. На POSIX перед заменой '
    'сравниваются mode, UID и GID цели и временного файла; несовпадение вызывает отказ. '
    'Сохранность ACL и защита от гонок не проверяются; на других ОС метаданные не проверяются.'
)


@dataclass(frozen=True)
class _Pending:
    ticket: str
    shown: bytes
    preview: registry_store._ActionPreview


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
    rel = preview.registry
    before, after = preview.before, preview.after
    lines = diff_bytes(unified_diff, list(BytesIO(before)), list(BytesIO(after)),
                       fromfile=('a/' + rel).encode('utf-8'), tofile=('b/' + rel).encode('utf-8'))
    display = b''.join(line if line.endswith(b'\n') else line + b'\n\\ No newline at end of file\n' for line in lines)
    return {'file': rel, 'revision': {'from': preview.from_revision, 'to': preview.to_revision},
            'before_sha256': sha256(before).hexdigest(), 'after_sha256': sha256(after).hexdigest(),
            'unified': display.decode('utf-8')}


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
        if card['outcome'] in ('missing_params', 'non_registry'):
            return dict(result, outcome=card['outcome'])
        if card['outcome'] == 'rejected':
            code = card['code']
            raise StoreError(code, 'L0' if code == 'system_immutable' else 'card/params/contract')
        operation, params = card['operation'], card['params']
        target = params['target']
        check_operation(operation, target=target)
        if target == 'L1' and params['profile'] != self._profile_id:
            raise StoreError('profile_mismatch', 'card/params/profile')
        if operation == 'list':
            return dict(result, outcome='listed', result=registry_store._list_entries(self._layout, params))
        preview = registry_store._preview_action(self._layout, operation, params)
        result.update(diff=_diff(preview), inputs_sha256=dict(preview.inputs_sha256))
        if preview.from_revision == preview.to_revision:
            return dict(result, outcome='no_change')
        ticket = token_hex(32)
        modes = ({'status': 'captured_posix_mode_bits', 'inputs': dict(preview.input_modes)}
                 if preview.input_modes is not None else {'status': 'not_checked', 'inputs': None})
        result.update(outcome='planned', ticket=ticket, replacement_notice=REPLACEMENT_NOTICE,
                      input_mode_bits=modes)
        self._pending = _Pending(ticket, canonical_bytes(result), preview)
        return result

    def apply(self, plan, *, confirmed_ticket=None, allow_delete=False):
        """Писать только по отдельному билету на этот план; для удаления нужно также allow_delete."""
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
        status = registry_store._apply_action(self._layout, pending.preview, allow_delete=allow_delete)
        return {'outcome': 'applied', 'status': status}
