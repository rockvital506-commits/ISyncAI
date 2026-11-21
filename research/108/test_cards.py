#!/usr/bin/env python3
"""П2: независимые карточки, пустой и населённый стенд, контроль доступа и байтов."""
from collections import Counter
import json
import os
from pathlib import Path
import platform
import re
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'research/105'))
from test_layout import digest_tree, encode, snapshot, write

ENVIRONMENTS = ('empty', 'seeded')
_HEX = re.compile(r'[0-9a-f]{64}')


def seed(root, validate):
    def entry(area, id_, *, parent=None):
        authority = {'L1': 'profile_owner', 'L2': 'project_owner'}[area]
        return {'id': id_, 'kind': 'rule' if parent else 'contract', 'parent': parent, 'state': 'active',
                'authority': authority, 'scope': 'docs', 'title': f'Данные стенда {id_}', 'text': 'Не читать при компиляции.',
                'basis': 'Проверить отсутствие подстановки.', 'criterion': 'Карточка не зависит от наличия записей.'}

    docs = {
        'L0': {'release_version': '0.2.0-dev.108', 'roots': ['kit'], 'entries': []},
        'L1': {'revision': 4, 'roots': ['profiles/Pilot'], 'entries': [entry('L1', 'C-1'), entry('L1', 'Q-1', parent='C-1')]},
        'L2': {'revision': 7, 'roots': ['.agent-contract'], 'entries': [entry('L2', 'C-1')]},
    }
    for area, relative in (('L0', 'kit/base/registry.json'), ('L1', 'profiles/Pilot/registry.json'),
                           ('L2', '.agent-contract/project/registry.json')):
        docs[area].update(area=area, schema_version=2)
        write(root / relative, docs[area])
    validate(docs)


def fixture_snapshot(root):
    tree = snapshot(root)
    stamps = {}
    for name in ('', *tree):
        st = (root / name).lstat()
        # Не сравниваем atime; наблюдаем состав, байты, замену и изменения файлов/папок.
        stamps[name] = (st.st_dev, st.st_ino, st.st_mtime_ns, st.st_ctime_ns)
    return tree, stamps


class Audit:
    def __init__(self):
        self.active = False
        self.events = []
        sys.addaudithook(self.record)

    def record(self, event, _args):
        if self.active and (event == 'open' or event.startswith(('os.', 'shutil.', 'tempfile.', 'socket.', 'subprocess.'))):
            self.events.append(event)

    def compile(self, compiler, request, root):
        cwd = Path.cwd()
        before, stamps = fixture_snapshot(root)
        self.events.clear()
        try:
            os.chdir(root)
            self.active = True
            card = compiler(request)
        finally:
            self.active = False
            os.chdir(cwd)
        after, last_stamps = fixture_snapshot(root)
        return {'card': card, 'io_events': self.events[:], 'tree_unchanged': before == after and stamps == last_stamps,
                'digest': {'before': digest_tree(before), 'after': digest_tree(after)}}


def case_checks(cases, evidence):
    rows = evidence.get('rows') if type(evidence) is dict else None
    if type(rows) is not list or any(type(row) is not dict or type(row.get('id')) is not str for row in rows):
        rows = []
    seen = Counter(r['id'] for r in rows)
    by_id = {r['id']: r for r in rows}
    checks = []
    for case in cases:
        i = case['id']
        if seen[i] != 1:
            issue = 'duplicate' if seen[i] else 'missing'
        else:
            outcomes = by_id[i].get('observed')
            issue = None if type(outcomes) is dict and outcomes.keys() == set(ENVIRONMENTS) else 'missing_fixture'
            if issue is None:
                for mode in ENVIRONMENTS:
                    row = outcomes[mode]
                    if type(row) is not dict or encode(row.get('card')) != encode(case['expected']):
                        issue = 'card_mismatch:' + mode
                        break
                    if row.get('io_events') != [] or row.get('tree_unchanged') is not True:
                        issue = 'side_effect:' + mode
                        break
                    d = row.get('digest')
                    if (type(d) is not dict or d.keys() != {'before', 'after'} or any(
                            type(value) is not str or not _HEX.fullmatch(value) for value in d.values()) or d['before'] != d['after']):
                        issue = 'digest_mismatch:' + mode
                        break
                if issue is None and outcomes['empty']['digest']['before'] == outcomes['seeded']['digest']['before']:
                    issue = 'fixtures_not_distinct'
        checks.append({'id': i, 'group': case['group'], 'status': 'pass' if issue is None else 'fail', 'issue': issue})
    checks.extend({'id': i, 'group': 'unexpected', 'status': 'fail', 'issue': 'unexpected'}
                  for i in sorted(seen.keys() - {case['id'] for case in cases}))
    return checks


def main():
    sys.path.insert(0, str(ROOT))
    from kit.base.operation_card import compile_prompt
    from kit.base.schema_v2 import validate_catalog

    book = json.loads((HERE / 'CASES.json').read_bytes())
    cases = book['cases']
    if encode(book['format']) != b'1' or not cases or len({r['id'] for r in cases}) != len(cases):
        raise ValueError('Некорректный список П2')
    audit = Audit()
    rows = []
    for case in cases:
        with tempfile.TemporaryDirectory(prefix='ack-i108-work-') as tmp:
            roots = {mode: Path(tmp).resolve() / mode for mode in ENVIRONMENTS}
            for root in roots.values():
                root.mkdir()
            seed(roots['seeded'], validate_catalog)
            observed = {mode: audit.compile(compile_prompt, case['request'], roots[mode]) for mode in ENVIRONMENTS}
            rows.append({'id': case['id'], 'observed': observed})
    evidence = {'os': platform.system(), 'rows': rows}
    print(json.dumps(evidence, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if all(row['status'] == 'pass' for row in case_checks(cases, evidence)) else 1


if __name__ == '__main__':
    raise SystemExit(main())
