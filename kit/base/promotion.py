"""Подготовка переноса одной явно отобранной записи: запись только в новый стенд."""
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from secrets import token_hex
from tempfile import TemporaryDirectory

from . import project_specificity, registry_journal, registry_policy, schema_v2
from .profile_journal import canonical_bytes, entry_digest
from .registry_policy import StoreError

PROMOTION_FORMAT = 1
_STAGE_ROOT = 'profiles/staged'  # Метаданные синтетического L1, не адрес записи.
_STAGE_NAME = 'registry.json'
_MAX_PROFILE_BYTES = 1_048_576
_EDITS = frozenset(('id', 'parent', 'scope', 'title', 'text', 'basis', 'criterion'))
_EDITS_WITH_PAIR = _EDITS | {'key', 'value'}


@dataclass(frozen=True)
class _Pending:
    ticket: str
    shown: bytes
    artifact: bytes


def _candidate(source, proposal, context):
    original = project_specificity.inspect_entry(source, context=context)
    if original['outcome'] == 'invalid_input':
        if original['code'] == 'invalid_context':
            raise StoreError('invalid_context', 'context')
        raise StoreError('invalid_entry', 'source')
    if type(proposal) is not dict or len(proposal) > len(_EDITS_WITH_PAIR) or any(type(k) is not str for k in proposal):
        raise StoreError('invalid_entry', 'proposal')
    fields = proposal.keys()
    if 'parent' not in fields and fields | {'parent'} in (_EDITS, _EDITS_WITH_PAIR):
        raise StoreError('parent', 'proposal')
    if fields not in (_EDITS, _EDITS_WITH_PAIR):
        raise StoreError('invalid_entry', 'proposal')
    # Переходят только вид и явно поданная редакция; ни тело, ни ID, ни состояние L2 не наследуются.
    entry = dict(proposal, kind=source['kind'], authority='profile_owner', state='draft')
    try:
        schema_v2._entry_shape(entry, 'L1', '')
    except schema_v2.SchemaError as error:
        raise StoreError('parent' if error.path == '/parent' else 'invalid_entry', 'proposal') from None
    # Детектор И-113 принимает форму L2. Меняем только метку в его локальной проекции.
    analysis = project_specificity.inspect_entry(dict(entry, authority='project_owner'), context=context)
    if analysis['outcome'] == 'invalid_input':
        raise StoreError('invalid_entry', 'proposal')
    if analysis['findings']:
        raise StoreError('project_specific', 'proposal', details={'findings': analysis['findings']})
    return entry


def _base(raw):
    if type(raw) is not bytes or len(raw) > _MAX_PROFILE_BYTES:
        raise StoreError('invalid_profile', 'staged_profile')
    try:
        registry, journal = registry_journal.unpack_registry(schema_v2.parse_json(raw), area='L1')
    except schema_v2.SchemaError:
        raise StoreError('invalid_profile', 'staged_profile') from None
    if registry['roots'] != [_STAGE_ROOT]:
        raise StoreError('invalid_profile', 'staged_profile')
    return registry, journal


def _pack(entry, registry, journal):
    if (any(e['id'] == entry['id'] for e in registry['entries'])
            or registry_journal.is_retired(journal, entry['id'])):
        raise StoreError('promote_conflict', 'entry')
    updated = dict(registry, entries=[*registry['entries'], entry], revision=registry['revision'] + 1)
    try:
        schema_v2.validate_registry(updated, expected_area='L1')
    except schema_v2.SchemaError as error:
        code = 'parent' if error.code in ('parent_missing', 'parent_kind', 'scope_outside') else 'invalid_entry'
        raise StoreError(code, 'proposal') from None
    # Черновик не действует. Это ранняя проверка одной структурной пары, не имитация активации.
    if entry['kind'] != 'contract' and 'key' in entry:
        for active in registry_policy.active_entries(registry):
            if (active['kind'] != 'contract' and active.get('key') == entry['key'] and active['value'] != entry['value']
                    and registry_policy._shared_scope(entry['scope'], active['scope']) is not None):
                raise StoreError('promote_conflict', 'entries')
    pack = registry_journal.with_change(updated, registry, journal, operation='create', before=None, after=entry)
    registry_journal.unpack_registry(pack, area='L1')
    return pack


class PromotionSession:
    """Одно ожидающее согласование черновика. Ни Layout, ни запись в рабочий профиль."""

    def __init__(self):
        self._pending = None

    def promote(self, source, *, proposal, context, staged_profile, target='stand'):
        """Проверить явную редакцию, показать точное добавление, ничего не записывая."""
        self._pending = None
        if type(target) is not str or target != 'stand':
            raise StoreError('promote_unverified', 'target')
        entry = _candidate(source, proposal, context)
        registry, journal = _base(staged_profile)
        pack = _pack(entry, registry, journal)
        raw = canonical_bytes(pack) + b'\n'
        diff = {'file': _STAGE_NAME, 'revision': {'from': registry['revision'], 'to': pack['registry']['revision']},
                'before_sha256': sha256(staged_profile).hexdigest(), 'after_sha256': sha256(raw).hexdigest(),
                'decision': pack['journal']['decisions'][-1]}
        ticket = token_hex(32)
        plan = {'promotion_format': PROMOTION_FORMAT, 'operation': 'promote', 'target': 'stand', 'outcome': 'planned',
                'candidate': entry, 'candidate_sha256': entry_digest(entry), 'diff': diff, 'ticket': ticket}
        self._pending = _Pending(ticket, canonical_bytes(plan), raw)
        return plan

    @contextmanager
    def stage(self, plan, *, confirmed_ticket=None):
        """По точному одноразовому согласию выдать временный файл, удаляемый при выходе."""
        pending = self._pending
        if (type(confirmed_ticket) is not str or pending is None or confirmed_ticket != pending.ticket
                or type(plan) is not dict or type(plan.get('ticket')) is not str or plan['ticket'] != confirmed_ticket):
            raise StoreError('promote_unverified', 'confirmation')
        try:
            same = canonical_bytes(plan) == pending.shown
        except (TypeError, ValueError, RecursionError):
            same = False
        if not same:
            raise StoreError('promote_unverified', 'plan')
        self._pending = None
        try:
            directory = TemporaryDirectory(prefix='ack-promote-')
        except OSError:
            raise StoreError('write_failed', 'stage') from None
        with directory as root:
            path = Path(root) / _STAGE_NAME
            try:
                with path.open('xb') as dest:
                    if dest.write(pending.artifact) != len(pending.artifact):
                        raise OSError('short_write')
            except OSError:
                raise StoreError('write_failed', 'stage') from None
            yield path
