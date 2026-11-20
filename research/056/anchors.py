#!/usr/bin/env python3
"""Проверка якорей README-вектора до сборки: каждая ссылка должна разрешаться в дереве поставки."""
import json, pathlib, re, sys

TREE = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else '../release-0.1.35/base/AgentContractLab').resolve()
KIT = TREE / 'kit'
PLACES = {'manifest': 'kit/base/manifest.json', 'schema': 'kit/base/schema.json',
          'rules': 'kit/base/rules.json', 'entry': 'kit/base/entry.txt',
          'CHECKS': 'reports/CHECKS.json', 'PIPELINE': 'reports/PIPELINE.json',
          'SUMS': 'SHA256SUMS', 'TRACE': 'TRACEABILITY.json'}
TEXTS = {'START': KIT / 'base/START.md', 'PROTOCOL': KIT / 'base/PROTOCOL.md',
         'INIT': TREE / 'docs/INIT-PROMPT.md', 'КАЛИБРОВКА': TREE / 'docs/КАЛИБРОВКА.md'}


def main() -> int:
    readme = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else '/tmp/README-056.md').resolve()
    text = readme.read_text(encoding='utf-8')
    body = '\n'.join(line for line in text.splitlines()
                     if not re.match(r'\A- \[.+\(#.+\)\Z', line.strip()))
    lines = body.splitlines()
    heads = {n for n, line in enumerate(lines[:-1])
             if line.strip().startswith('|') and lines[n + 1].strip().startswith('|-')}
    tests = (KIT / 'tests/test_contract.py').read_text(encoding='utf-8')
    book = json.loads((KIT / 'calibration.json').read_text(encoding='utf-8'))
    ids = [p['id'] for p in book['prompts']]
    dead = []
    for anchor in sorted(set(re.findall(r'\[([^\[\]]+)\]', body))):
        if anchor in PLACES:
            ok = (TREE / PLACES[anchor]).is_file()
        elif re.fullmatch(r'X\d+', anchor):
            ok = ('@case(\'' + anchor + '\'') in tests
        elif re.fullmatch(r'K\d+', anchor):
            ok = anchor in ids
        elif re.fullmatch(r'releases/\d+\.\d+\.\d+', anchor):
            ok = (TREE / 'releases' / anchor.split('/')[1]).is_dir()
        else:
            m = re.fullmatch(r'(START|PROTOCOL|INIT|КАЛИБРОВКА):\s*(.+)', anchor)
            ok = bool(m) and TEXTS[m.group(1)].is_file() and \
                m.group(2).strip().lower() in TEXTS[m.group(1)].read_text(encoding='utf-8').lower()
        if not ok:
            dead.append(anchor)
    print(json.dumps({'size': len(readme.read_bytes()), 'anchors': len(set(re.findall(r'\[([^\[\]]+)\]', body))),
                      'dead': dead}, ensure_ascii=False, indent=1))
    return 1 if dead else 0


if __name__ == '__main__':
    raise SystemExit(main())
