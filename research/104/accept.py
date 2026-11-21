"""Целевая приёмка И-104; не доверяет rc, итоговым счётчикам или строке accepted."""
from collections import Counter
import json


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False)


def case_problems(cases, observation):
    expected = {row['id']: row['expected'] for row in cases}
    if not cases or len(expected) != len(cases):
        return ['invalid_casebook']
    if type(observation) is not dict or type(observation.get('rows')) is not list:
        return ['missing_rows']
    rows = observation['rows']
    if any(type(row) is not dict or type(row.get('id')) is not str for row in rows):
        return ['malformed_row']
    counts = Counter(row['id'] for row in rows)
    issues = [f'missing:{i}' for i in sorted(expected.keys() - counts.keys())]
    issues += [f'unexpected:{i}' for i in sorted(counts.keys() - expected.keys())]
    issues += [f'duplicate:{i}' for i, count in sorted(counts.items()) if count != 1]
    for row in rows:
        i = row['id']
        if i in expected:
            proper = {'id': i, 'status': 'pass', 'observed': expected[i], 'unchanged': True}
            if encoded(row) != encoded(proper):
                issues.append(f'bad_result:{i}')
    return issues
