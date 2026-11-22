"""И-120: выбор точного N-1 и журнал успешных переключений одного стенда."""
from hashlib import sha256
from os import replace
from pathlib import Path
import re
import stat
from tempfile import NamedTemporaryFile, TemporaryDirectory

from . import schema_v2
from .bundle_trust import assess_bundle_trust
from .profile_journal import canonical_bytes
from .registry_policy import StoreError

_MAX_BYTES, _MAX_EVENTS = 64 * 1024, 32
_HEX = re.compile('[0-9a-f]{64}')
_FIELDS = {'rollout_format', 'active_sha256', 'journal'}
_EVENT = {'seq', 'action', 'from_sha256', 'to_sha256', 'revision', 'manifest_digest', 'signature_status', 'policy_decision'}
_ACTIONS = ('rollout', 'rollback')
_ALLOWED = {('unsigned', 'optional'), ('unsigned', 'exception'), ('trusted_signature', 'satisfied')}
_REPARSE = getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0)


def _fail(code, where, reason):
    raise StoreError(code, where, details={'reason': reason}) from None


def _journal(reason):
    _fail('rollout_state_invalid', 'journal', reason)


def _hash(raw):
    return sha256(raw).hexdigest()


def _wire(state):
    return canonical_bytes(state) + b'\n'


def _sha(value):
    return type(value) is str and _HEX.fullmatch(value) is not None


def _same_receipt(a, b):
    return (a['revision'], a['manifest_digest']) == (b['revision'], b['manifest_digest'])


def _decode(raw):
    try:
        state = schema_v2.parse_json(raw)
    except schema_v2.SchemaError:
        _journal('json')
    if (type(state) is not dict or state.keys() != _FIELDS or type(state['rollout_format']) is not int
            or state['rollout_format'] != 1 or type(state['journal']) is not list
            or not (state['active_sha256'] is None or _sha(state['active_sha256']))):
        _journal('shape')
    events = state['journal']
    if len(events) > _MAX_EVENTS:
        _journal('limit')
    head, previous = None, None
    for i, row in enumerate(events, 1):
        if (type(row) is not dict or row.keys() != _EVENT or type(row['seq']) is not int
                or type(row['action']) is not str or row['action'] not in _ACTIONS
                or not (row['from_sha256'] is None or _sha(row['from_sha256'])) or not _sha(row['to_sha256'])
                or not _sha(row['manifest_digest']) or type(row['revision']) is not int or row['revision'] < 0
                or type(row['signature_status']) is not str or type(row['policy_decision']) is not str
                or (row['signature_status'], row['policy_decision']) not in _ALLOWED):
            _journal('shape')
        if row['seq'] != i or row['from_sha256'] != head or row['to_sha256'] == head:
            _journal('chain')
        if row['action'] == 'rollback':
            if i < 3 or previous['action'] != 'rollout' or row['to_sha256'] != previous['from_sha256']:
                _journal('chain')
            if not _same_receipt(row, events[i-3]):
                _journal('receipt')
        elif i == _MAX_EVENTS:
            _journal('limit')
        head, previous = row['to_sha256'], row
    if head != state['active_sha256']:
        _journal('chain')
    if raw != _wire(state):
        _journal('encoding')
    return state


def _proposal(state, archive, action, *, policy, now, signature, exceptions, verify_signature):
    seq = len(state['journal']) + 1; active = state['active_sha256']
    previous = None
    if action == 'rollback':
        history = state['journal']
        if len(history) < 2 or history[-1]['action'] != 'rollout':
            _fail('rollback_unavailable', 'journal', 'no_previous')
        previous = history[-2]
        if archive is None:
            _fail('rollback_unavailable', 'archive', 'missing')
    elif seq >= _MAX_EVENTS:
        _fail('rollout_limit', 'journal', 'capacity')

    trust = assess_bundle_trust(archive, policy=policy, now=now, signature=signature, exceptions=exceptions,
                                verify_signature=verify_signature)
    info = trust['integrity']; target = info['archive_sha256']
    if previous is not None:
        if target != previous['to_sha256']:
            _fail('rollback_unavailable', 'archive', 'not_previous')
        if not _same_receipt(info, previous):
            _journal('receipt')
    if (trust['signature_status'], trust['policy_decision']) not in _ALLOWED:
        _fail('rollout_blocked', 'trust', trust['reason'])
    if target == active:
        _fail('rollout_no_change', 'archive', 'already_active')
    event = {'seq': seq, 'action': action, 'from_sha256': active, 'to_sha256': target, 'revision': info['revision'],
             'manifest_digest': info['manifest_digest'], 'signature_status': trust['signature_status'],
             'policy_decision': trust['policy_decision']}
    next_raw = _wire(dict(state, active_sha256=target, journal=[*state['journal'], event]))
    if len(next_raw) > _MAX_BYTES:
        _fail('rollout_limit', 'journal', 'capacity')
    return event, next_raw


def _same_plan(value, expected):
    # Все значения плана — простые скаляры и один непрозрачный объект билета.
    return (type(value) is dict and len(value) == len(expected)
            and all(type(k) is str and k in expected and type(v) is type(expected[k]) and v == expected[k]
                    for k, v in value.items()))


def _identity(info):
    return info.st_dev, info.st_ino


class RolloutSession:
    """Владеет только новым временным стендом, без аргумента пути или рабочего режима."""

    def __init__(self, *, target='stand'):
        if type(target) is not str or target != 'stand':
            _fail('rollout_invalid', 'target', 'stand_only')
        self._temp = self._state_path = self._root_id = self._pending = None

    def __enter__(self):
        if self._temp is not None:
            _fail('rollout_invalid', 'session', 'active')
        temp = None
        try:
            temp = TemporaryDirectory(prefix='ack-i120-stand-')
            root = Path(temp.name).resolve(strict=True)
            identity = _identity(root.lstat())
            path = root/'rollout.json'
            raw = _wire({'rollout_format': 1, 'active_sha256': None, 'journal': []})
            with path.open('xb') as f:
                if f.write(raw) != len(raw):
                    raise OSError
        except (OSError, RuntimeError):
            if temp is not None:
                try:
                    temp.cleanup()
                except OSError:
                    pass
            _fail('rollout_write_failed', 'state', 'initialize')
        self._temp, self._state_path, self._root_id = temp, path, identity
        return self

    def __exit__(self, *_):
        temp = self._temp
        self._temp = self._state_path = self._root_id = self._pending = None
        if temp is not None:
            try:
                temp.cleanup()
            except OSError:
                _fail('rollout_write_failed', 'state', 'cleanup')

    def _read(self):
        path = self._state_path
        if path is None:
            _fail('rollout_invalid', 'session', 'inactive')
        try:
            parent = path.parent.lstat()
            if (not stat.S_ISDIR(parent.st_mode) or _identity(parent) != self._root_id
                    or getattr(parent, 'st_file_attributes', 0) & _REPARSE or path.parent.resolve(strict=True) != path.parent):
                _journal('file')
            info = path.lstat()
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or getattr(info, 'st_file_attributes', 0) & _REPARSE):
                _journal('file')
            if info.st_size > _MAX_BYTES:
                _journal('limit')
            with path.open('rb') as f:
                raw = f.read(_MAX_BYTES + 1)
            if len(raw) > _MAX_BYTES:
                _journal('limit')
        except FileNotFoundError:
            _journal('missing')
        except (OSError, RuntimeError):
            _journal('read')
        return raw

    def status(self):
        """Свежий журнал и SHA-256 его байтов. Не читает архивы и не выдаёт билет."""
        raw = self._read()
        return dict(_decode(raw), state_sha256=_hash(raw))

    def plan(self, archive, *, action, policy, now, signature=None, exceptions=(), verify_signature=None):
        self._pending = None
        if type(action) is not str or action not in _ACTIONS:
            _fail('rollout_invalid', 'operation', 'unknown')
        raw = self._read()
        event, after = _proposal(_decode(raw), archive, action, policy=policy, now=now, signature=signature,
                                 exceptions=exceptions, verify_signature=verify_signature)
        self._pending = {'plan_format': 1, 'outcome': 'planned', 'target': 'stand', 'state_sha256': _hash(raw),
                         'after_sha256': _hash(after), **event, 'ticket': object()}
        return self._pending.copy()

    def apply(self, plan, *, confirmed_ticket=None, archive, policy, now, signature=None, exceptions=(), verify_signature=None):
        pending, self._pending = self._pending, None
        if self._state_path is None:
            _fail('rollout_invalid', 'session', 'inactive')
        if pending is None or confirmed_ticket is not pending['ticket']:
            _fail('rollout_unconfirmed', 'plan', 'ticket')
        if not _same_plan(plan, pending):
            _fail('rollout_unconfirmed', 'plan', 'changed')
        before = self._read(); state = _decode(before)
        if _hash(before) != pending['state_sha256']:
            _fail('rollout_stale', 'journal', 'changed')
        event, after = _proposal(state, archive, pending['action'], policy=policy, now=now, signature=signature,
                                 exceptions=exceptions, verify_signature=verify_signature)
        if event['to_sha256'] != pending['to_sha256']:
            _fail('rollout_stale', 'archive', 'changed')
        if _hash(after) != pending['after_sha256']:
            _fail('rollout_stale', 'plan', 'assessment')
        result = {'outcome': 'applied', 'state_sha256': pending['after_sha256'], 'active_sha256': event['to_sha256'], 'event': event}
        self._replace_state(before, after)
        return result

    def _replace_state(self, before, after):
        path = self._state_path
        if self._read() != before:
            _fail('rollout_stale', 'journal', 'changed')
        temp_path = None
        try:
            with NamedTemporaryFile(mode='wb', dir=path.parent, prefix='pending-', delete=False) as f:
                temp_path = Path(f.name)
                if f.write(after) != len(after):
                    raise OSError
            if self._read() != before:
                _fail('rollout_stale', 'journal', 'changed')
            replace(temp_path, path)
            temp_path = None
        except OSError:
            _fail('rollout_write_failed', 'state', 'replace')
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    # Состояние не заменено; закрытие убирает собственный каталог стенда.
                    pass
