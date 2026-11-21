#!/usr/bin/env python3
"""П2: целевые случаи, ожидаемые исходы независимы от валидатора."""
import copy
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PREPARATION = ROOT / 'research/strategy/pre-104'
AREAS = ('L0', 'L1', 'L2')
AUTHORITY = {'L0': 'system_release', 'L1': 'profile_owner', 'L2': 'project_owner'}


def read(path):
    return json.loads(path.read_bytes())


def encode(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, allow_nan=False).encode()


def fixtures():
    samples = read(PREPARATION / 'SCHEMA-CASES.json')['samples']
    body = (PREPARATION / 'PHASED-PROMPT-PROTOCOL.md').read_bytes().decode('utf-8')
    documents = {}
    for area in AREAS:
        sample = samples[area]
        revision = {'release_version': '0.2.0'} if area == 'L0' else {'revision': 0}
        entries = []
        for row in sample['entries']:
            entry = {k: v for k, v in row.items() if k not in ('alias', 'text_file')}
            entry.update(id=row['alias'], authority=AUTHORITY[area])
            if 'text_file' in row:
                if row['text_file'] != 'PHASED-PROMPT-PROTOCOL.md':
                    raise ValueError('В корпусе изменился источник тела кандидата')
                entry['text'] = body
            entries.append(entry)
        documents[area] = {'schema_version': 2, 'area': area, 'roots': [sample['proposed_root']],
                           **revision, 'entries': entries}
    return documents


def inputs(case, filled):
    target = case['input']
    if target == 'raw':
        return case['raw'].encode('utf-8')
    data = copy.deepcopy(filled if target == 'group' else filled[target])
    if case['fixture'] == 'empty':
        for document in data.values() if target == 'group' else (data,):
            document['entries'] = []
    elif case['fixture'] != 'filled':
        raise ValueError('Неизвестный вид фикстуры')
    if change := case.get('change'):
        obj = data
        *path, key = change['path']
        for part in path:
            obj = obj[part]
        if change['op'] == 'drop':
            del obj[key]
        elif change['op'] == 'set':
            obj[key] = copy.deepcopy(change['value'])
        else:
            raise ValueError('Неизвестная мутация фикстуры')
    return data


def execute(schema, case, filled):
    data = inputs(case, filled)
    before = data if type(data) is bytes else encode(data)
    target = case['input']
    observed = {'ok': True}
    try:
        if target == 'raw':
            parsed = schema.validate_json(data, expected_area='L2')
            if encode(parsed) != encode(json.loads(data)):
                raise ValueError('JSON был нормализован или изменён')
        elif target == 'group':
            schema.validate_catalog(data)
        else:
            schema.validate_registry(data, expected_area=case.get('expected_area', target))
    except schema.SchemaError as error:
        observed = {'ok': False, 'stage': error.stage, 'code': error.code, 'path': error.path}
    after = data if type(data) is bytes else encode(data)
    unchanged = before == after
    return {'id': case['id'], 'status': 'pass' if unchanged and encode(observed) == encode(case['expected']) else 'fail',
            'observed': observed, 'unchanged': unchanged}


def main():
    # Явный каталог модуля: запуск допускается с -I, без PYTHONPATH и установленного Kit.
    sys.path.insert(0, str(ROOT / 'kit/base'))
    import schema_v2

    casebook = read(HERE / 'CASES.json')
    cases = casebook['cases']
    if casebook.get('format') != 1 or not cases or len({row['id'] for row in cases}) != len(cases):
        raise ValueError('Некорректный обязательный список И-104')
    filled = fixtures()
    rows = [execute(schema_v2, case, filled) for case in cases]
    candidate = filled['L1']['entries'][1]
    facts = {'entry_counts': {area: len(filled[area]['entries']) for area in AREAS},
             'candidate': {k: candidate[k] for k in ('id', 'kind', 'state', 'parent')},
             'candidate_body_sha256': hashlib.sha256(candidate['text'].encode('utf-8')).hexdigest()}
    print(json.dumps({'schema_version': schema_v2.SCHEMA_VERSION, 'rows': rows, 'facts': facts},
                     ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if all(row['status'] == 'pass' for row in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
