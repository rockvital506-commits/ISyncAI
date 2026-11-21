#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""И-101: печать итерации.

`build` собирает архив артефактов итерации и печатает размер и хеш ИЗ СВОЕГО вывода
(а не из памяти агента), затем пишет SEAL.json. `replay` пересобирает архив из тех же
файлов и сверяет размер и хеш с записанными — расхождение означает, что артефакты
изменились после печати.

Что НЕ входит в архив (иначе печать ссылается сама на себя):
  ACCEPTANCE.json, SEAL.json, сам архив, страница (Итерация-101.html — производный вид,
  который показывает числа печати и приёмки; в печать он попасть не может по порядку).
"""
import hashlib
import json
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
NAME = 'AgentContractKit-Iteration-101.zip'
ZIP = os.path.join(HERE, NAME)
MEMBERS = [
    ('research/STRATEGY.md', os.path.join(REPO, 'research', 'STRATEGY.md')),
    ('research/strategy/SYNC-LOG.md', os.path.join(REPO, 'research', 'strategy', 'SYNC-LOG.md')),
    ('research/strategy/BASELINE.json', os.path.join(REPO, 'research', 'strategy', 'BASELINE.json')),
    ('research/101/REPORT.md', os.path.join(HERE, 'REPORT.md')),
    ('research/101/CLEANROOM.json', os.path.join(HERE, 'CLEANROOM.json')),
    ('research/101/inventory.py', os.path.join(HERE, 'inventory.py')),
    ('research/101/cleanroom.py', os.path.join(HERE, 'cleanroom.py')),
    ('research/101/acceptance.py', os.path.join(HERE, 'acceptance.py')),
    ('research/101/seal.py', os.path.join(HERE, 'seal.py')),
]


def build():
    with zipfile.ZipFile(ZIP, 'w', zipfile.ZIP_DEFLATED) as z:
        for arcname, path in MEMBERS:
            info = zipfile.ZipInfo(arcname, date_time=(2026, 11, 18, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            with open(path, 'rb') as fh:
                z.writestr(info, fh.read())
    raw = open(ZIP, 'rb').read()
    return {'file': NAME, 'members': len(MEMBERS), 'bytes': len(raw),
            'sha256': hashlib.sha256(raw).hexdigest()}


def main(argv):
    action = argv[0] if argv else 'build'
    if action == 'build':
        facts = build()
        record = dict(facts, format=1, iteration='И-101')
        with open(os.path.join(HERE, 'SEAL.json'), 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + '\n')
        print(json.dumps(record, ensure_ascii=False, indent=2))
        return 0
    if action == 'replay':
        recorded = json.load(open(os.path.join(HERE, 'SEAL.json')))
        facts = build()
        same = all(facts[k] == recorded[k] for k in ('members', 'bytes', 'sha256'))
        print(json.dumps({'replay': 'ok' if same else 'mismatch', 'recorded': recorded,
                          'rebuilt': facts}, ensure_ascii=False, indent=2))
        return 0 if same else 1
    print('usage: seal.py [build|replay]')
    return 2


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
