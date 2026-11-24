"""Внутреннее хранилище v2: раздельные корни и согласованные манипуляции L1/L2."""
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import tempfile

from . import profile_journal, registry_journal, registry_policy, schema_v2
from .profile_journal import canonical_bytes as _wire
from .registry_policy import StoreError, check_operation, operation_matrix


@dataclass(frozen=True)
class Layout:
    """Доверенный контекст вызывающего кода, а не адреса из реестра или фразы."""

    workspace: Path
    profile_root: str


# Проверяемая цель L1 первая: алиас её файла диагностируется на выбранном профиле.
_SUFFIX = {'L1': 'registry.json', 'L0': 'base/registry.json', 'L2': 'project/registry.json'}
_REPARSE = getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0)


@dataclass(frozen=True)
class _Loaded:
    workspace: Path
    roots: dict
    files: dict
    documents: dict
    inputs_sha256: dict
    raw: dict
    journals: dict


@dataclass(frozen=True)
class CreatePreview:
    """Снимок нативного плана и байтов для слоя карточек, без записи."""

    store_plan: dict
    inputs_sha256: dict
    before: bytes
    after: bytes


@dataclass(frozen=True)
class _Change:
    candidate: dict
    prior: dict | None
    replacement: dict | None


@dataclass(frozen=True)
class _ActionPreview:
    operation: str
    params: dict
    registry: str
    from_revision: int
    to_revision: int
    inputs_sha256: dict
    before: bytes
    after: bytes


def _declared_roots(layout):
    roots = {'L0': 'kit', 'L1': layout.profile_root, 'L2': '.agent-contract'}
    # Пустые оболочки только для общей лексической политики формы; это не инициализация.
    candidates = {area: {'schema_version': schema_v2.SCHEMA_VERSION, 'area': area, 'roots': [root], 'entries': [],
                         **({'release_version': '0.0.0'} if area == 'L0' else {'revision': 0})}
                  for area, root in roots.items()}
    try:
        schema_v2.validate_catalog(candidates)
    except schema_v2.SchemaError as error:
        if error.code == 'roots_overlap':
            raise StoreError('profile_root_conflict', layout.profile_root) from error
        raise StoreError('invalid_layout', 'profile_root', schema=error) from error
    return roots


def _workspace(path):
    try:
        base = Path(path)
        if base.is_absolute():
            base = base.resolve(strict=True)
            if base.is_dir():
                return base
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise StoreError('invalid_layout', 'workspace') from error
    raise StoreError('invalid_layout', 'workspace')


def _existing(workspace, rel, *, registry=False):
    # rel уже проверен схемой либо составлен с фиксированным суффиксом.
    current = workspace
    parts = rel.split('/')
    for i, part in enumerate(parts):
        current = current / part
        where = '/'.join(parts[:i + 1])
        try:
            info = current.lstat()
        except FileNotFoundError as error:
            raise StoreError('missing_path', where) from error
        except OSError as error:
            raise StoreError('io_error', where) from error
        ordinary = (stat.S_ISREG(info.st_mode) and info.st_nlink == 1 if registry and i == len(parts) - 1
                    else stat.S_ISDIR(info.st_mode))
        if not ordinary or getattr(info, 'st_file_attributes', 0) & _REPARSE:
            raise StoreError('unsafe_path', where)
    return current, info


def _load(layout):
    roots = _declared_roots(layout)
    workspace = _workspace(layout.workspace)
    identities = set()
    for area, name in roots.items():
        _, info = _existing(workspace, name)
        identity = (info.st_dev, info.st_ino)
        if identity in identities:
            raise StoreError('profile_root_conflict', roots['L1'])
        identities.add(identity)

    files, documents, inputs_sha256, raw_by_area, journals = {}, {}, {}, {}, {}
    for area, suffix in _SUFFIX.items():
        rel = roots[area] + '/' + suffix
        path, _ = _existing(workspace, rel, registry=True)
        try:
            raw = path.read_bytes()
        except OSError as error:
            raise StoreError('io_error', rel) from error
        try:
            if area == 'L0':
                document = schema_v2.validate_json(raw, expected_area=area)
            else:
                document, journals[area] = registry_journal.unpack_registry(schema_v2.parse_json(raw), area=area)
        except schema_v2.SchemaError as error:
            code = 'invalid_history' if error.stage == 'history' else 'invalid_registry'
            raise StoreError(code, rel, schema=error) from error
        if document['roots'] != [roots[area]]:
            raise StoreError('root_mismatch', rel)
        files[area], documents[area] = path, document
        inputs_sha256[area] = sha256(raw).hexdigest()
        raw_by_area[area] = raw
    return _Loaded(workspace, roots, files, documents, inputs_sha256, raw_by_area, journals)


def _status(current, *, target=None, revision=None):
    values = {area: revision if area == target else current.documents[area]['revision'] for area in ('L1', 'L2')}
    return {'schema_version': schema_v2.SCHEMA_VERSION, 'release_version': current.documents['L0']['release_version'],
            'profile_root': current.roots['L1'], 'profile_revision': values['L1'], 'project_revision': values['L2']}


def status(layout):
    """Свежее чтение v2. Не создаёт и не исправляет отсутствующие данные."""
    return _status(_load(layout))


def registry_history(layout, *, target):
    """Прочитать локальный журнал L1/L2 в его проверенной форме, без записи."""
    check_operation('read', target=target)
    if target == 'L0':
        raise StoreError('operation_unavailable', 'operation')
    return _load(layout).journals[target]


def profile_history(layout):
    """Прочитать проверенный журнал выбранного профиля без записи."""
    return registry_history(layout, target='L1')


def read_registry(layout, *, target):
    """Читать проверенный реестр области, не вычисляя действующий набор правил."""
    check_operation('read', target=target)
    return _load(layout).documents[target]


def report_conflicts(layout):
    """Показать структурные противоречия в реестрах, не решая их и не меняя файлы."""
    return registry_policy.find_conflicts(_load(layout).documents)


def _rel(current, target):
    return current.files[target].relative_to(current.workspace).as_posix()


def _validated_candidate(current, target, entries, index):
    old = current.documents[target]
    candidate = dict(old, entries=entries, revision=old['revision'] + 1)
    try:
        schema_v2.validate_registry(candidate, expected_area=target)
    except schema_v2.SchemaError as error:
        path = f'/entries/{index}'
        parent_error = (error.path == path + '/parent'
                        or (error.stage == 'links' and error.code == 'scope_outside' and error.path == path + '/scope'))
        raise StoreError('parent' if parent_error else 'invalid_entry', _rel(current, target), schema=error) from error
    return candidate


def _check_conflicts(documents):
    conflicts = registry_policy.find_conflicts(documents)
    if conflicts:
        raise StoreError('rule_conflict', 'entries', details={'conflicts': conflicts})


def _change(current, target, candidate, prior, replacement):
    _check_conflicts(current.documents)
    _check_conflicts({**current.documents, target: candidate})
    return _Change(candidate, prior, replacement)


def _propose_create(current, target, entry, *, rule_only=False):
    entries = list(current.documents[target]['entries'])
    index = len(entries)
    if type(entry) is dict and type(entry.get('id')) is str:
        index = next((i for i, row in enumerate(entries) if row['id'] == entry['id']), index)
    prior = entries[index] if index < len(entries) else None
    # Сначала проверяем и возможный повтор, не превращая его в duplicate_id.
    entries[index:index + 1] = [entry]
    candidate = _validated_candidate(current, target, entries, index)
    if entry['state'] != 'draft' or (rule_only and entry['kind'] != 'rule'):
        raise StoreError('unsupported_entry', target)
    if prior is not None:
        if _wire(prior) != _wire(entry):
            raise StoreError('entry_exists', _rel(current, target))
        return None
    if registry_journal.is_retired(current.journals[target], entry['id']):
        raise StoreError('entry_retired', _rel(current, target))
    return _change(current, target, candidate, prior, entry)


_TRANSITIONS = {'activate': ({'draft'}, 'active'), 'suspend': ({'active'}, 'suspended'), 'resume': ({'suspended'}, 'active'),
                'revoke': ({'draft', 'active', 'suspended'}, 'revoked')}


def _locate(entries, params, rel):
    for i, row in enumerate(entries):
        if row['id'] == params['entry_id']:
            if params.get('kind', row['kind']) != row['kind']:
                raise StoreError('entry_kind_mismatch', rel)
            return i, row
    raise StoreError('entry_not_found', rel)


def _propose_existing(current, operation, target, params):
    entries = list(current.documents[target]['entries'])
    rel = _rel(current, target)
    index, prior = _locate(entries, params, rel)
    state = prior['state']

    def invalid_transition():
        return StoreError('invalid_transition', rel, details={'entry_id': prior['id'], 'operation': operation,
                                                              'state': state})

    if operation == 'edit':
        if state == 'revoked':
            raise invalid_transition()
        if prior['text'] == params['text']:
            return None
        replacement = dict(prior, text=params['text'])
    elif operation == 'delete':
        if state != 'revoked':
            raise invalid_transition()
        children = sorted(row['id'] for row in entries if row['parent'] == prior['id'])
        if children:
            raise StoreError('parent', rel, details={'reason': 'contract_has_children', 'children': children})
        replacement = None
    else:
        allowed, new_state = _TRANSITIONS[operation]
        if state == new_state:
            # Активный дочерний флаг не делает запись действующей под неактивным контрактом.
            if operation == 'activate' and prior['parent'] is not None:
                parent = next(row for row in entries if row['id'] == prior['parent'])
                if parent['state'] != 'active':
                    raise StoreError('parent', rel, details={'reason': 'parent_inactive', 'contract': parent['id']})
            return None
        if state not in allowed:
            raise invalid_transition()
        if operation in ('activate', 'resume') and prior['parent'] is not None:
            parent = next(row for row in entries if row['id'] == prior['parent'])
            if parent['state'] != 'active':
                raise StoreError('parent', rel, details={'reason': 'parent_inactive', 'contract': parent['id']})
        replacement = dict(prior, state=new_state)
    entries[index:index + 1] = [] if replacement is None else [replacement]
    candidate = _validated_candidate(current, target, entries, index)
    return _change(current, target, candidate, prior, replacement)


def _mutation_bytes(current, operation, target, change):
    journal = current.journals[target]
    if target == 'L1' and operation == 'create' and change.replacement['kind'] == 'rule' and 'base_entries' not in journal:
        packed = profile_journal.with_creation(change.candidate, journal)
    else:
        packed = registry_journal.with_change(change.candidate, current.documents[target], journal,
                                              operation=operation, before=change.prior, after=change.replacement)
    return (json.dumps(packed, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')


def _list_entries(layout, params):
    target = params['target']
    current = _load(layout)
    document = current.documents[target]
    rows = document['entries']
    if 'entry_id' in params:
        _, row = _locate(rows, params, _rel(current, target))
        rows = [row]
    state = params.get('state')
    if state == 'active':
        active = {row['id'] for row in registry_policy.active_entries(document)}
        rows = [row for row in rows if row['id'] in active]
    elif state is not None:
        rows = [row for row in rows if row['state'] == state]
    if 'kind' in params:
        rows = [row for row in rows if row['kind'] == params['kind']]
    fields = ('id', 'text') if params.get('view') == 'text' else ('id', 'kind', 'state', 'parent', 'scope', 'title')
    return {'target': target, 'revision': document['revision'],
            'entries': [{key: row[key] for key in fields} for row in rows]}


def _prepare_action(current, operation, params):
    target = params['target']
    if operation == 'create':
        entry = {k: params[k] for k in ('kind', 'state', 'scope', 'title', 'text', 'basis', 'criterion')}
        # Метка из проверенного маршрута, не свидетельство полномочий.
        entry.update(id=params['entry_id'], parent=params.get('contract'),
                     authority={'L1': 'profile_owner', 'L2': 'project_owner'}[target])
        change = _propose_create(current, target, entry)
    else:
        change = _propose_existing(current, operation, target, params)
    revision, before = current.documents[target]['revision'], current.raw[target]
    after = before if change is None else _mutation_bytes(current, operation, target, change)
    return _ActionPreview(operation, dict(params), _rel(current, target), revision,
                          revision if change is None else change.candidate['revision'], current.inputs_sha256, before, after)


def _preview_action(layout, operation, params):
    """Внутренний путь из проверенной карточки, без выдачи полномочий или записи."""
    return _prepare_action(_load(layout), operation, params)


def _check_inputs(current, preview):
    for area, digest in sorted(current.inputs_sha256.items()):
        if digest != preview.inputs_sha256.get(area):
            raise StoreError('stale_plan', 'inputs/' + area)


def _apply_action(layout, preview, *, allow_delete=False):
    """Только после проверки отдельного билета в PlanSession."""
    operation, params = preview.operation, preview.params
    target = params['target']
    check_operation(operation, target=target)
    if operation == 'delete' and allow_delete is not True:
        raise StoreError('delete_confirmation_required', 'allow_delete')
    current = _load(layout)
    if current.documents[target]['revision'] != preview.from_revision:
        raise StoreError('stale_revision', 'revision/from')
    prepared = _prepare_action(current, operation, params)
    _check_inputs(current, preview)
    if (prepared.registry != preview.registry or prepared.to_revision != preview.to_revision
            or prepared.to_revision != prepared.from_revision + 1
            or prepared.before != preview.before or prepared.after != preview.after):
        raise StoreError('plan_mismatch', 'diff')
    _replace(current.files[target], prepared.after, prepared.registry)
    return _status(current, target=target, revision=prepared.to_revision)


def _native_create(target):
    check_operation('create', target=target)
    if target != 'L1':
        # Нативный интерфейс И-105–109 остаётся L1-only. L2 только через карточку.
        raise StoreError('operation_unavailable', 'operation')


def _plan(current, entry):
    revision = current.documents['L1']['revision']
    change = _propose_create(current, 'L1', entry, rule_only=True)
    plan = {'operation': 'create', 'target': 'L1', 'registry': _rel(current, 'L1')}
    if change is None:
        return dict(plan, revision={'from': revision, 'to': revision}, outcome='no_change', entry_id=entry['id']), None
    plan.update(revision={'from': revision, 'to': change.candidate['revision']}, add=dict(entry))
    ticket_input = {'workspace': str(current.workspace), 'profile_sha256': current.inputs_sha256['L1'], 'plan': plan}
    plan['ticket'] = sha256(_wire(ticket_input)).hexdigest()
    return plan, change


def plan_create(layout, entry, *, target='L1'):
    """Совместимый нативный план для одного чернового правила L1."""
    _native_create(target)
    plan, _ = _plan(_load(layout), entry)
    return plan


def preview_create(layout, entry, *, target='L1'):
    """Нативный снимок будущих байтов чернового правила L1, без записи."""
    _native_create(target)
    current = _load(layout)
    plan, change = _plan(current, entry)
    before = current.raw['L1']
    after = before if change is None else _mutation_bytes(current, 'create', 'L1', change)
    return CreatePreview(plan, current.inputs_sha256, before, after)


def _replace(registry, raw, rel):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='wb', dir=registry.parent, prefix='.registry-', suffix='.tmp',
                                         delete=False) as staged:
            temporary = Path(staged.name)
            staged.write(raw)
        os.replace(temporary, registry)
    except OSError as error:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError as cleanup:
                raise StoreError('cleanup_failed', rel) from cleanup
        raise StoreError('write_failed', rel) from error


def apply_create(layout, plan, *, confirmed_ticket, preview=None):
    """Записать только актуальный план создания L1; вызов не удостоверяет владельца."""
    if type(plan) is not dict:
        raise StoreError('plan_mismatch', 'plan')
    _native_create(plan.get('target'))
    if type(confirmed_ticket) is not str or plan.get('ticket') != confirmed_ticket:
        raise StoreError('confirmation_required', 'confirmed_ticket')
    current = _load(layout)
    steps = plan.get('revision')
    if (type(steps) is not dict or steps.keys() != {'from', 'to'} or type(steps['from']) is not int
            or type(steps['to']) is not int or steps['from'] < 0 or steps['to'] != steps['from'] + 1):
        raise StoreError('plan_mismatch', 'plan')
    if steps['from'] != current.documents['L1']['revision']:
        raise StoreError('stale_revision', 'revision/from')
    expected, change = _plan(current, plan.get('add'))
    if preview is not None:
        if type(preview) is not CreatePreview:
            raise StoreError('plan_mismatch', 'preview')
        _check_inputs(current, preview)
    try:
        same = change is not None and _wire(plan) == _wire(expected)
    except (TypeError, ValueError, RecursionError):
        same = False
    if not same:
        raise StoreError('plan_mismatch', 'plan')
    raw = _mutation_bytes(current, 'create', 'L1', change)
    if preview is not None and raw != preview.after:
        raise StoreError('plan_mismatch', 'diff')
    _replace(current.files['L1'], raw, expected['registry'])
    return _status(current, target='L1', revision=change.candidate['revision'])
