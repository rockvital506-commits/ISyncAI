"""Стенд И-103, не CLI Kit: решения матрицы и L1 рядом с настоящим 0.1.36."""
import json
from pathlib import Path
import re
import tempfile
import zipfile

BASELINE = '0.1.36'
TARGET = '0.2.0'
PROJECT = 'A'
PACKAGE_MANIFEST = re.compile(r'AgentContractLab/releases/(0\.1\.(?:0|[1-9][0-9]*))/manifest\.json')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + '\n',
                    encoding='utf-8', newline='\n')


def candidate_route(matrix, shipped, source, schema, target):
    """Классификация, не авторизация. Пакет/снимок проверяются отдельно."""
    fallback = {key: matrix['default'][key] for key in ('decision', 'evidence')}
    if not isinstance(source, str) or not isinstance(target, str):
        return fallback
    baseline_patch = int(BASELINE.rsplit('.', 1)[1])
    older = {v for v in shipped if int(v.rsplit('.', 1)[1]) < baseline_patch}
    source_groups = {'older_shipped': older}
    target_groups = {'shipped_baseline_or_older': older | ({BASELINE} & shipped)}
    for row in matrix['rows']:
        if (source in source_groups.get(row['source'], {row['source']})
                and type(schema) is type(row['source_schema']) and schema == row['source_schema']
                and target in target_groups.get(row['target'], {row['target']})):
            return {key: row[key] for key in ('decision', 'evidence')}
    return fallback


def init_profile(root):
    root.mkdir(parents=True)
    write(root / 'profile.json', {'revision': 0})
    write(root / 'rules.json', {'entries': [{'id': 'R-1', 'kind': 'contract', 'scope': '.'}]})


def rule(n):
    return {'id': f'R-{n + 1}', 'kind': 'rule', 'contract': 'R-1', 'scope': '.',
            'text': f'Синтетическое правило №{n}', 'basis': 'Стенд И-103',
            'criterion': 'ID присутствует в rules.json'}


def add_rule(root, expected_revision, entry):
    """Стендовая запись двух файлов. Не реализация атомарной транзакции L1."""
    meta_file, rules_file = root / 'profile.json', root / 'rules.json'
    meta, registry = read(meta_file), read(rules_file)
    if type(expected_revision) is not int or expected_revision != meta['revision']:
        return 'stale_revision'
    records = {record['id']: record for record in registry['entries']}
    parent = records.get(entry.get('contract'))
    if entry.get('kind') != 'rule' or not parent or parent['kind'] != 'contract':
        return 'parent'
    previous = records.get(entry['id'])
    if previous is not None:
        return 'no_change' if previous == entry else 'fixture_conflict'
    registry['entries'].append(entry)
    write(rules_file, registry)
    write(meta_file, {'revision': meta['revision'] + 1})
    return 'committed'


def package_facts(archive):
    members = archive.namelist()
    shipped = set()
    for name in members:
        match = PACKAGE_MANIFEST.fullmatch(name)
        if match and json.loads(archive.read(name))['base_version'] == match[1]:
            shipped.add(match[1])
    return {'profile_members': sum(name.startswith('AgentContractLab/profiles/') for name in members),
            'shipped_manifests': sorted(shipped, key=lambda v: int(v.rsplit('.', 1)[1]))}


def matrix_evidence(matrix, shipped):
    cases = [
        (BASELINE, 1, BASELINE, 'use_baseline', 'baseline_observed'),
        (BASELINE, 1, TARGET, 'migration_required', 'not run'),
        ('0.1.0', 1, TARGET, 'review_upgrade_path', 'not run'),
        ('0.1.35', 1, TARGET, 'review_upgrade_path', 'not run'),
        ('absent', None, TARGET, 'clean_install', 'not run'),
        (TARGET, 2, BASELINE, 'restore_snapshot_only', 'not run'),
        (TARGET, 2, '0.1.35', 'restore_snapshot_only', 'not run'),
        ('0.1.1', 1, TARGET, 'unknown_version', 'policy_only'),
        ('0.1.2', 1, TARGET, 'unknown_version', 'policy_only'),
        ('0.1.3', 1, TARGET, 'unknown_version', 'policy_only'),
        ('0.1.37', 1, TARGET, 'unknown_version', 'policy_only'),
        (BASELINE, 99, TARGET, 'unknown_version', 'policy_only'),
        (BASELINE, 1, '1.0.0', 'unknown_version', 'policy_only'),
    ]
    rows = []
    for source, schema, target, decision, evidence in cases:
        result = candidate_route(matrix, shipped, source, schema, target)
        rows.append({'source': source, 'source_schema': schema, 'target': target, **result,
                     'matches': result == {'decision': decision, 'evidence': evidence}})
    return {'matches_cases': all(row['matches'] for row in rows), 'cases': rows}


def run_stand(lab, kit):
    project = lab / PROJECT
    project.mkdir()
    project_prefix = project / '.agent-contract'
    state_file = project_prefix / 'project/state.json'
    installed = project_prefix / 'base'
    canonical = lab / 'kit/base'
    published = lab / kit.PIN_OF

    def approve(request):
        rc, out = kit.plan_apply(lab, PROJECT, request)
        if rc or out.get('outcome') != 'committed':
            raise ValueError(f"Стенд: {request['op']} не выполнен (rc={rc}, {out.get('error')})")

    def status():
        rc, out = kit.run(lab, PROJECT, 'status')
        if rc or out.get('health') != 'valid':
            raise ValueError(f"Стенд: ожидался status valid (rc={rc}, {out.get('error')})")
        return out

    def sample_l0(view):
        manifest = installed / 'manifest.json'
        return {'base_version': view['base']['version'], 'pin': view['base']['pin'],
                'installed_manifest_version': read(manifest)['base_version'],
                'installed_manifest_sha256': kit.sha256_bytes(manifest.read_bytes()),
                'installed_tree': kit.tree_facts(installed), 'kit_base_tree': kit.tree_facts(canonical),
                'package_tree': kit.tree_facts(published), 'kit_tree': kit.tree_facts(lab / 'kit'),
                'releases_tree': kit.tree_facts(lab / 'releases')}

    install = {'op': 'install', 'package': kit.PIN_OF, 'pin': kit.manifest_pin(lab)}
    empty = kit.tree_facts(project)
    rc, rejected = kit.run(lab, PROJECT, 'plan', {**install, 'pin': '0' * 64})
    bad_pin = {'rc': rc, 'error': rejected.get('error'), 'no_write': kit.tree_facts(project) == empty}
    approve(install)
    approve({'op': 'connect'})
    initial_view = status()
    initial_l0 = sample_l0(initial_view)
    creation_revisions = [initial_view['project_revision']]
    shared = {'op': 'create', 'scope': '.', 'state': 'active', 'text': 'Данные только для стенда И-103',
              'basis': 'Снимок 0.1.36 в И-103', 'criterion': 'list видит сущность', 'reason': 'проверка версии'}
    approve({**shared, 'kind': 'contract', 'title': 'Контракт стенда'})
    after_contract = status()
    creation_revisions.append(after_contract['project_revision'])
    approve({**shared, 'kind': 'rule', 'title': 'Правило стенда', 'contract': 'P-1'})
    after_create = status()
    creation_revisions.append(after_create['project_revision'])
    steady = initial_l0 == sample_l0(after_contract) == sample_l0(after_create)
    initial_project = kit.tree_facts(project)

    profile = lab / 'profiles/iteration-103'
    init_profile(profile)
    profile_file, rules_file = profile / 'profile.json', profile / 'rules.json'
    revisions = [read(profile_file)['revision']]
    digests = {kit.sha256_bytes(rules_file.read_bytes())}
    observations = []
    for i in range(1, 11):
        outcome = add_rule(profile, revisions[-1], rule(i))
        revision = read(profile_file)['revision']
        rules_digest = kit.sha256_bytes(rules_file.read_bytes())
        view = status()
        same_l0 = sample_l0(view) == initial_l0
        same_project = (view['project_revision'] == creation_revisions[-1]
                        and kit.tree_facts(project) == initial_project)
        observations.append({'outcome': outcome, 'revision': revision, 'rules_digest': rules_digest,
                             'l0_unchanged': same_l0, 'l2_unchanged': same_project})
        revisions.append(revision)
        digests.add(rules_digest)

    entries = read(rules_file)['entries']
    before_retry = kit.tree_facts(profile)
    retries = []
    for expected, entry in ((10, rule(10)), (9, rule(11))):
        outcome = add_rule(profile, expected, entry)
        retries.append({'outcome': outcome, 'revision': read(profile_file)['revision'],
                        'unchanged': kit.tree_facts(profile) == before_retry})
    final_l0 = sample_l0(status())
    final_project = kit.tree_facts(project)

    # Негативный вход создаётся только во временном проекте, после снятия штатных точек.
    write(state_file, {**read(state_file), 'schema_version': 99})
    before_refusal = kit.tree_facts(project)
    rc, rejected = kit.run(lab, PROJECT, 'plan', {**shared, 'kind': 'contract', 'title': 'Не должно появиться'})
    return {
        'system': {'initial': initial_l0, 'final': final_l0,
                   'pin_matches_install': initial_l0['pin'] == initial_l0['installed_manifest_sha256'] == install['pin']
                   and initial_l0['base_version'] == initial_l0['installed_manifest_version']
                   and initial_l0['installed_tree'] == initial_l0['kit_base_tree'] == initial_l0['package_tree'],
                   'steady': steady and initial_l0 == final_l0 and all(row['l0_unchanged'] for row in observations)},
        'project': {'schema_version': after_create['schema_version'], 'create_revisions': creation_revisions,
                    'unchanged_during_profile_writes': initial_project == final_project
                    and all(row['l2_unchanged'] for row in observations)},
        'profile': {'kind': 'synthetic_fixture', 'revisions': revisions, 'distinct_rules_digests': len(digests),
                    'committed_mutations': sum(row['outcome'] == 'committed' for row in observations),
                    'child_ids': [row['id'] for row in entries if row.get('contract') == 'R-1'],
                    'only_counter_and_registry': set(read(profile_file)) == {'revision'}
                    and set(read(rules_file)) == {'entries'}
                    and all(all('version' not in key for key in row) for row in entries),
                    'observations': observations, 'retries': retries},
        'refusals': {'bad_pin': bad_pin, 'unknown_schema': {'rc': rc, 'error': rejected.get('error'),
                                                         'no_write': kit.tree_facts(project) == before_refusal}},
    }


def collect(artifact, matrix_path, kit):
    matrix = read(matrix_path)
    if matrix.get('format') != 1:
        raise ValueError('Неизвестный формат COMPATIBILITY.json')
    with tempfile.TemporaryDirectory(prefix='ack-version-stand-') as tmp:
        with zipfile.ZipFile(artifact) as archive:
            package = package_facts(archive)
            archive.extractall(tmp)
        return {'package': package, **run_stand(Path(tmp) / 'AgentContractLab', kit),
                'compatibility': matrix_evidence(matrix, set(package['shipped_manifests']))}
