"""Внутреннее хранилище v2: раздельные корни и согласованные регистрации L1."""
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import tempfile

from . import profile_journal, registry_policy, schema_v2
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
    profile_bytes: bytes
    journal: dict


@dataclass(frozen=True)
class CreatePreview:
    """Снимок нативного плана и байтов для слоя карточек, без записи."""

    store_plan: dict
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

    files, documents, inputs_sha256 = {}, {}, {}
    for area, suffix in _SUFFIX.items():
        rel = roots[area] + '/' + suffix
        path, _ = _existing(workspace, rel, registry=True)
        try:
            raw = path.read_bytes()
        except OSError as error:
            raise StoreError('io_error', rel) from error
        try:
            if area == 'L1':
                document, journal = profile_journal.unpack_profile(schema_v2.parse_json(raw))
                profile_bytes = raw
            else:
                document = schema_v2.validate_json(raw, expected_area=area)
        except schema_v2.SchemaError as error:
            code = 'invalid_history' if error.stage == 'history' else 'invalid_registry'
            raise StoreError(code, rel, schema=error) from error
        if document['roots'] != [roots[area]]:
            raise StoreError('root_mismatch', rel)
        files[area], documents[area] = path, document
        inputs_sha256[area] = sha256(raw).hexdigest()
    return _Loaded(workspace, roots, files, documents, inputs_sha256, profile_bytes, journal)


def _status(current, profile):
    return {'schema_version': schema_v2.SCHEMA_VERSION, 'release_version': current.documents['L0']['release_version'],
            'profile_root': current.roots['L1'], 'profile_revision': profile['revision'],
            'project_revision': current.documents['L2']['revision']}


def status(layout):
    """Свежее чтение v2. Не создаёт и не исправляет отсутствующие данные."""
    current = _load(layout)
    return _status(current, current.documents['L1'])


def profile_history(layout):
    """Прочитать проверенный журнал регистраций выбранного профиля без записи."""
    return _load(layout).journal


def read_registry(layout, *, target):
    """Читать проверенный реестр области, не вычисляя действующий набор правил."""
    check_operation('read', target=target)
    return _load(layout).documents[target]


def report_conflicts(layout):
    """Показать структурные противоречия в реестрах, не решая их и не меняя файлы."""
    return registry_policy.find_conflicts(_load(layout).documents)


def _plan(current, entry):
    old = current.documents['L1']
    revision = old['revision']
    rel = current.files['L1'].relative_to(current.workspace).as_posix()
    entries = list(old['entries'])
    index = len(entries)
    if type(entry) is dict and type(entry.get('id')) is str:
        index = next((i for i, row in enumerate(entries) if row['id'] == entry['id']), index)
    previous = entries[index] if index < len(entries) else None
    # Для повтора с уже занятым ID проверяем новый объект в его прежнем месте,
    # иначе штатная проверка duplicate_id не даст различить no_change и новое тело.
    entries[index:index + 1] = [entry]
    candidate = dict(old, entries=entries, revision=revision + 1)
    try:
        schema_v2.validate_registry(candidate, expected_area='L1')
    except schema_v2.SchemaError as error:
        path = f'/entries/{index}'
        parent_error = (
            error.path == path + '/parent'
            or (error.stage == 'links' and error.code == 'scope_outside' and error.path == path + '/scope')
        )
        raise StoreError('parent' if parent_error else 'invalid_entry', rel, schema=error) from error
    if entry['kind'] != 'rule' or entry['state'] != 'draft':
        raise StoreError('unsupported_entry', 'L1')
    plan = {'operation': 'create', 'target': 'L1', 'registry': rel}
    if previous is not None:
        if _wire(previous) != _wire(entry):
            raise StoreError('entry_exists', rel)
        return dict(plan, revision={'from': revision, 'to': revision}, outcome='no_change', entry_id=entry['id']), None
    conflicts = registry_policy.find_conflicts(current.documents)
    if conflicts:
        raise StoreError('rule_conflict', 'entries', details={'conflicts': conflicts})
    plan.update(revision={'from': revision, 'to': candidate['revision']}, add=dict(entry))
    ticket_input = {'workspace': str(current.workspace), 'profile_sha256': current.inputs_sha256['L1'], 'plan': plan}
    plan['ticket'] = sha256(_wire(ticket_input)).hexdigest()
    return plan, candidate


def plan_create(layout, entry, *, target='L1'):
    """Показать добавление одной записи и переход ревизии без записи."""
    check_operation('create', target=target)
    plan, _ = _plan(_load(layout), entry)
    return plan


def _creation_bytes(candidate, journal):
    profile = profile_journal.with_creation(candidate, journal)
    return (json.dumps(profile, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')


def preview_create(layout, entry, *, target='L1'):
    """Сформировать точные будущие байты тем же путём, что и при записи."""
    check_operation('create', target=target)
    current = _load(layout)
    plan, candidate = _plan(current, entry)
    after = current.profile_bytes if candidate is None else _creation_bytes(candidate, current.journal)
    return CreatePreview(plan, current.inputs_sha256, current.profile_bytes, after)


def _replace(profile, raw, rel):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='wb', dir=profile.parent, prefix='.registry-', suffix='.tmp',
                                         delete=False) as staged:
            temporary = Path(staged.name)
            staged.write(raw)
        os.replace(temporary, profile)
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
    check_operation('create', target=plan.get('target'))
    if type(confirmed_ticket) is not str or plan.get('ticket') != confirmed_ticket:
        raise StoreError('confirmation_required', 'confirmed_ticket')
    current = _load(layout)
    steps = plan.get('revision')
    if (type(steps) is not dict or steps.keys() != {'from', 'to'} or type(steps['from']) is not int
            or type(steps['to']) is not int or steps['from'] < 0 or steps['to'] != steps['from'] + 1):
        raise StoreError('plan_mismatch', 'plan')
    if steps['from'] != current.documents['L1']['revision']:
        raise StoreError('stale_revision', 'revision/from')
    expected, candidate = _plan(current, plan.get('add'))
    if preview is not None:
        if type(preview) is not CreatePreview:
            raise StoreError('plan_mismatch', 'preview')
        for area, digest in sorted(current.inputs_sha256.items()):
            if digest != preview.inputs_sha256.get(area):
                raise StoreError('stale_plan', 'inputs/' + area)
    try:
        same = candidate is not None and _wire(plan) == _wire(expected)
    except (TypeError, ValueError, RecursionError):
        same = False
    if not same:
        raise StoreError('plan_mismatch', 'plan')
    raw = _creation_bytes(candidate, current.journal)
    if preview is not None and raw != preview.after:
        raise StoreError('plan_mismatch', 'diff')
    _replace(current.files['L1'], raw, expected['registry'])
    return _status(current, candidate)
