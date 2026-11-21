"""Имитация развёртывания точного черновика: две пары временных раскладок, только просмотр."""
from hashlib import sha256
from pathlib import Path
import re
import stat
from tempfile import TemporaryDirectory

from . import bootstrap, registry_journal, registry_policy, registry_store, schema_v2
from .profile_journal import canonical_bytes, entry_digest
from .registry_policy import StoreError

SIMULATION_FORMAT = 1
_PROFILE_ROOT, _PROFILE_ID = 'profiles/staged', 'staged'
_ENTRY, _START = 'kit/base/entry.txt', 'kit/base/START.md'
_L0, _L2 = 'kit/base/registry.json', '.agent-contract/project/registry.json'
_ASSET = {'cli': 'src/tool/usage.txt', 'docs': 'docs/site/index.md'}
_WITNESS = {'entry_id', 'entry_sha256', 'control_sha256', 'profile_sha256'}
_HASH = re.compile('[a-f0-9]{64}')
_MAX_REGISTRY, _MAX_ASSET = 1_048_576, 65_536
_CATALOG_FIELDS = ('id', 'kind', 'state', 'parent', 'scope', 'title')


def _fail(where, reason):
    raise StoreError('simulation_failed', where, details={'reason': reason}) from None


def _keys(value, fields):
    return (type(value) is dict and len(value) == len(fields)
            and all(type(k) is str for k in value) and value.keys() == fields)


def _blob(raw, limit):
    return type(raw) is bytes and 0 < len(raw) <= limit


def _sha(raw):
    return sha256(raw).hexdigest()


def _profiles(candidate_profile, control_profile, witness):
    if (not _keys(witness, _WITNESS) or type(witness['entry_id']) is not str
            or schema_v2._ID.fullmatch(witness['entry_id']) is None
            or any(type(witness[k]) is not str or _HASH.fullmatch(witness[k]) is None for k in _WITNESS - {'entry_id'})):
        _fail('witness', 'shape')
    if not (_blob(candidate_profile, _MAX_REGISTRY) and _blob(control_profile, _MAX_REGISTRY)):
        _fail('profiles', 'shape')
    if _sha(candidate_profile) != witness['profile_sha256']:
        _fail('profiles', 'profile_digest')
    if _sha(control_profile) != witness['control_sha256']:
        _fail('profiles', 'control_digest')
    try:
        raw = schema_v2.parse_json(candidate_profile)
        if type(raw) is not dict or raw.get('registry_format') != registry_journal.REGISTRY_FORMAT:
            _fail('profiles', 'profile_shape')
        installed, _ = registry_journal.unpack_registry(raw, area='L1')
        control, history = registry_journal.unpack_registry(schema_v2.parse_json(control_profile), area='L1')
    except schema_v2.SchemaError:
        _fail('profiles', 'profile_shape')
    if any(profile['roots'] != [_PROFILE_ROOT] for profile in (control, installed)):
        _fail('profiles', 'roots')
    entry_id = witness['entry_id']
    entry = next((row for row in installed['entries'] if row['id'] == entry_id), None)
    if entry is None or entry['kind'] != 'protocol' or entry['state'] != 'draft':
        _fail('profiles', 'identity')
    if entry_digest(entry) != witness['entry_sha256']:
        _fail('profiles', 'entry_digest')
    if any(row['id'] == entry_id for row in control['entries']) or registry_journal.is_retired(history, entry_id):
        _fail('profiles', 'lineage')
    appended = dict(control, entries=[*control['entries'], entry], revision=control['revision'] + 1)
    expected = registry_journal.with_change(appended, control, history, operation='create', before=None, after=entry)
    if canonical_bytes(expected) + b'\n' != candidate_profile:
        _fail('profiles', 'lineage')
    return control, installed, entry


def _validate_projects(startup, system, projects, installed):
    if not _keys(startup, {'entry', 'start'}) or any(not _blob(raw, _MAX_ASSET) for raw in startup.values()):
        _fail('startup', 'shape')
    if not _blob(system, _MAX_REGISTRY):
        _fail('system', 'shape')
    try:
        l0 = schema_v2.validate_json(system, expected_area='L0')
    except schema_v2.SchemaError:
        _fail('system', 'registry')
    if l0['roots'] != ['kit']:
        _fail('system', 'roots')
    if not _keys(projects, _ASSET.keys()):
        _fail('projects', 'shape')
    docs = {}
    for name in _ASSET:
        where, fixture = 'project/' + name, projects[name]
        if (not _keys(fixture, {'registry', 'asset'}) or not _blob(fixture['registry'], _MAX_REGISTRY)
                or not _blob(fixture['asset'], _MAX_ASSET)):
            _fail(where, 'fixture')
        try:
            l2 = schema_v2.validate_json(fixture['registry'], expected_area='L2')
        except schema_v2.SchemaError:
            _fail(where, 'registry')
        if l2['roots'] != ['.agent-contract']:
            _fail(where, 'roots')
        if not any(row['kind'] == 'rule' for row in l2['entries']):
            _fail(where, 'fixture')
        try:
            schema_v2.validate_catalog({'L0': l0, 'L1': installed, 'L2': l2})
        except schema_v2.SchemaError:
            _fail(where, 'registry')
        docs[name] = l2
    # Разные метки, ревизии или форматирование JSON не создают два разных набора правил.
    rules = [sorted(canonical_bytes(row) for row in docs[name]['entries'] if row['kind'] == 'rule') for name in _ASSET]
    if rules[0] == rules[1]:
        _fail('projects', 'same_fixture')
    return docs


def _place(root, files, where):
    try:
        for rel, raw in files.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as stream:
                if stream.write(raw) != len(raw):
                    raise OSError('short_write')
    except OSError:
        _fail(where, 'write')


def _marks(root, where):
    result = {}
    for path in root.rglob('*'):
        s = path.lstat()
        if not (stat.S_ISREG(s.st_mode) and s.st_nlink == 1 or stat.S_ISDIR(s.st_mode)):
            _fail(where, 'modified')
        result[path.relative_to(root).as_posix()] = (s.st_mode, s.st_size, s.st_ino, s.st_mtime_ns)
    return result


def _catalog(rows, kind):
    return [{key: row[key] for key in _CATALOG_FIELDS} for row in rows if row['kind'] == kind]


def _listed(session, request, area, revision, entries, where):
    try:
        plan = session.plan(request)
    except StoreError:
        _fail(where, 'listing')
    if (type(plan) is not dict or plan.get('outcome') != 'listed' or plan.get('dry_run') is not True
            or 'ticket' in plan or 'diff' in plan or plan.get('result') != {'target': area, 'revision': revision, 'entries': entries}):
        _fail(where, 'listing')


def _trial(root, files, profile, project, entry, *, installed, where):
    _place(root, files, where)
    before = _marks(root, where)
    try:
        session = bootstrap.BootstrapSession(registry_store.Layout(root, _PROFILE_ROOT), profile_id=_PROFILE_ID)
    except StoreError:
        _fail(where, 'bootstrap')
    revision = profile['revision']
    catalog = _catalog(profile['entries'], 'protocol')
    active = _catalog(registry_policy.active_entries(profile), 'protocol')
    rules = _catalog(project['entries'], 'rule')
    _listed(session, 'Покажи протоколы в профиле staged.', 'L1', revision, catalog, where)
    _listed(session, 'Покажи действующие протоколы в профиле staged.', 'L1', revision, active, where)
    _listed(session, 'Покажи правила в L2.', 'L2', project['revision'], rules, where)
    if installed:
        _listed(session, f"Покажи только текст протокола «{entry['id']}» в профиле staged.", 'L1', revision,
                [{'id': entry['id'], 'text': entry['text']}], where)
    candidate_visible = any(row['id'] == entry['id'] for row in catalog)
    candidate_active = any(row['id'] == entry['id'] for row in active)
    if candidate_visible != installed or candidate_active:
        _fail(where, 'listing')
    if (before != _marks(root, where) or any((root / rel).read_bytes() != raw for rel, raw in files.items())):
        _fail(where, 'modified')
    return {'profile_revision': revision, 'candidate_visible': candidate_visible, 'candidate_active': candidate_active,
            'text_verified': installed, 'l2_rules': len(rules), 'entry_bytes': session.inputs[0]['bytes'],
            'section0_bytes': session.inputs[1]['bytes'], 'unchanged': True}


def simulate(candidate_profile, *, control_profile, witness, startup, system, projects, target='stand'):
    """Успех только для точного черновика, прочитанного в обеих новых тестовых раскладках."""
    if type(target) is not str or target != 'stand':
        _fail('target', 'stand_only')
    control, installed, entry = _profiles(candidate_profile, control_profile, witness)
    docs = _validate_projects(startup, system, projects, installed)
    results = []
    try:
        with TemporaryDirectory(prefix='ack-simulate-') as folder:
            root = Path(folder)
            for name, asset in _ASSET.items():
                where = 'project/' + name
                row = {'fixture': name, 'asset': asset}
                for variant, raw, profile in (('control', control_profile, control), ('installed', candidate_profile, installed)):
                    files = {_ENTRY: startup['entry'], _START: startup['start'], _L0: system,
                             _PROFILE_ROOT + '/registry.json': raw, _L2: projects[name]['registry'], asset: projects[name]['asset']}
                    row[variant] = _trial(root / name / variant, files, profile, docs[name], entry,
                                          installed=variant == 'installed', where=where)
                results.append(row)
    except OSError:
        _fail('workspace', 'io')
    return {'simulation_format': SIMULATION_FORMAT, 'outcome': 'simulated', 'projects': results,
            **{name: witness[name] for name in ('entry_sha256', 'control_sha256', 'profile_sha256')}}
