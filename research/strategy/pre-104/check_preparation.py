#!/usr/bin/env python3
"""Проверка подготовки: согласованность корпуса и нативный черновик L2. Не валидатор v2."""
import json
from pathlib import Path, PurePosixPath
import sys
import tempfile
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent / 'harness'))
import probes

ZIP_PATH = 'research/release-0.1.36/AgentContractKit-0.1.36.zip'


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def need(condition, message):
    if not condition:
        raise ValueError(message)


def scopes_contained(child, parent):
    # Только для заведомо синтетических положительных примеров, не проверка путей v2.
    c, p = PurePosixPath(child), PurePosixPath(parent)
    return not c.is_absolute() and '..' not in c.parts and c.is_relative_to(p)


def samples_of(corpus):
    samples = corpus['samples']
    need(set(samples) == {'L0', 'L1', 'L2'}, 'Потерян образец области')
    cases = corpus['cases']
    need(len({case['id'] for case in cases}) == len(cases), 'Дубликат ID сценария')
    refs, by_alias = {'empty'}, {}
    for area, sample in samples.items():
        entries = {row['alias']: row for row in sample['entries']}
        need(entries and len(entries) == len(sample['entries']), f'{area}: нет записей или дубликат')
        refs.add(area)
        refs.update(f'{area}:{alias}' for alias in entries)
        need(not by_alias.keys() & entries.keys(), 'Метки примеров не уникальны')
        by_alias.update(entries)
        for alias, row in entries.items():
            need(bool(row['basis'].strip() and row['criterion'].strip()), f'{alias}: потеряно основание или критерий')
            if row['kind'] == 'contract':
                need(row['parent'] is None, f'{alias}: у тестового контракта есть родитель')
            else:
                parent = entries.get(row['parent'])
                need(parent and parent['kind'] == 'contract' and scopes_contained(row['scope'], parent['scope']),
                     f'{alias}: потеряна положительная связь с контрактом')
    for case in cases:
        need(all(item in refs for item in case['sample'].split(',')), f"{case['id']}: несуществующий пример")
    candidate = by_alias['R-2']
    need(candidate['kind'] == 'protocol' and candidate['state'] == 'draft', 'Потерян статус кандидата')
    need(candidate['text_file'] == 'PHASED-PROMPT-PROTOCOL.md', 'Потерян единственный источник текста')
    return candidate, {'entry_counts': {area: len(sample['entries']) for area, sample in samples.items()},
                       'planned_cases': len(cases)}


def examine_release(path, legacy):
    digest = probes.sha256_bytes(path.read_bytes())
    baseline = load(HERE.parent / 'BASELINE.json')
    need(digest == legacy['sha256'] == baseline['zip']['sha256'] and legacy['artifact'] == ZIP_PATH,
         'ZIP не совпадает с утверждённым baseline')
    with zipfile.ZipFile(path) as archive:
        base = 'AgentContractLab/kit/base/'
        raw = archive.read(base + 'manifest.json')
        manifest = json.loads(raw)
        facts = {'version': manifest['base_version'], 'schema': manifest['schema_version'],
                 'manifest_pin': probes.sha256_bytes(raw),
                 'rules_entries': len(json.loads(archive.read(base + 'rules.json'))['entries']),
                 'profile_members': sum(name.startswith('AgentContractLab/profiles/') for name in archive.namelist()),
                 'manifest_files': len(manifest['files']), 'archive_sha256': digest}
        need(facts['version'] == baseline['release'], 'Версия не совпала')
        for field in ('manifest_pin', 'rules_entries', 'profile_members'):
            need(facts[field] == legacy[field], f'{field}: ожидание о выпуске не подтвердилось')
        return facts


def l2_probe(artifact, candidate, body):
    with tempfile.TemporaryDirectory(prefix='ack-before-104-') as tmp:
        with zipfile.ZipFile(artifact) as archive:
            archive.extractall(tmp)
        lab = Path(tmp) / 'AgentContractLab'
        project = lab / 'A'
        project.mkdir()

        def approve(request):
            rc, result = probes.plan_apply(lab, 'A', request)
            need(rc == 0 and result.get('outcome') == 'committed',
                 f"{request['op']}: не выполнено (rc {rc}, код {result.get('error')})")

        src_base = lab / 'kit/base'
        published = lab / probes.PIN_OF
        installed = project / '.agent-contract/base'
        before = (probes.tree_facts(src_base), probes.tree_facts(published))
        approve({'op': 'install', 'package': probes.PIN_OF, 'pin': probes.manifest_pin(lab)})
        approve({'op': 'connect'})
        installed_tree = probes.tree_facts(installed)
        common = {key: candidate[key] for key in ('title', 'scope', 'basis', 'criterion', 'key', 'value')}
        request = {'op': 'create', **common, 'kind': 'protocol', 'state': 'draft', 'text': body,
                   'reason': 'Черновик проверки в независимой распаковке'}
        prior = probes.tree_facts(project)
        rc, err = probes.run(lab, 'A', 'plan', {**request, 'contract': 'P-999'})
        need(rc == 2 and err.get('error') == 'parent' and probes.tree_facts(project) == prior,
             'Отсутствующий родитель не отклонён без записи')
        approve({'op': 'create', 'kind': 'contract', 'state': 'active', 'scope': candidate['scope'],
                 'title': 'Контракт стенда', 'text': 'Только для проверки черновика.',
                 'basis': 'Нативная проба 0.1.36', 'criterion': 'Дочерний черновик не становится действующим',
                 'reason': 'Родитель для независимой пробы'})
        approve({**request, 'contract': 'P-1'})
        state = load(project / '.agent-contract/project/state.json')
        rc, listed = probes.run(lab, 'A', 'list')
        now = (probes.tree_facts(src_base), probes.tree_facts(published))
        need(rc == 0 and listed['active'] == [] and len(listed['contracts']) == 1, 'Черновик попал в действующий набор')
        need(before == now and probes.tree_facts(installed) == installed_tree, 'Снимок L0 изменился')
        parent, draft = state['entries']
        need(parent['id'] == 'P-1' and draft['id'] == 'P-2' and draft['contract'] == parent['id']
             and draft['kind'] == 'protocol' and draft['state'] == 'draft' and draft['text'] == body,
             'Черновик или связь с контрактом не сохранились')
        return {'install_connect_create': 'pass', 'calibration_used': False,
                'unknown_parent': {'error': err['error'], 'rc': 2, 'no_write': True},
                'draft_id': draft['id'], 'draft_state': draft['state'],
                'effective_entries': len(listed['active']), 'l0_bytes_unchanged': True}


def main():
    corpus = load(HERE / 'SCHEMA-CASES.json')
    candidate, samples = samples_of(corpus)
    body = (HERE / candidate['text_file']).read_bytes()
    result = {'baseline': examine_release(ROOT / ZIP_PATH, corpus['legacy']),
              'sample_catalog': samples,
              'protocol': {'bytes': len(body), 'sha256': probes.sha256_bytes(body)},
              'native_l2_in_temporary_copy': l2_probe(ROOT / ZIP_PATH, candidate, body.decode('utf-8')),
              'not_run': ['схема v2 и её будущие сценарии', 'регистрация и применение L1',
                          'перенос между проектами', 'поведение моделей в живых средах']}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
