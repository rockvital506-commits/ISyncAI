#!/usr/bin/env python3
"""И-023: печать и повтор.

  seal.py build   — собрать build/Iteration-023 (исходники, журналы, результаты, пакеты) и запаковать
  seal.py replay  — распаковать печать в replay/, прогнать из неё извлечение, проверку и пары заново,
                    сравнить JSON с запечатанными результатами и записать REPLAY.json
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import shutil
import subprocess
import sys
import zipfile

HERE = pathlib.Path(__file__).absolute().parent
ROOT = HERE.parents[1]
BUILD = HERE / 'build' / 'Iteration-023'
REPLAY = HERE / 'replay' / 'Iteration-023'
SEAL = HERE / 'AgentContractKit-Iteration-023.zip'
PACKAGES = {
    'AgentContractKit-0.1.4.zip': HERE.parent / 'release-0.1.4' / 'AgentContractKit-0.1.4.zip',
    'AgentContractKitISAIEdition-0.1.4+docs.1.zip':
        HERE.parent / 'release-0.1.4' / 'AgentContractKitISAIEdition-0.1.4+docs.1.zip',
}
SOURCES = ['DESIGN.md', 'REPORT.md', 'bench.py', 'extract.py', 'verify.py', 'pairs.py', 'diagnose.py',
           'acceptance.py']
RESULTS = ['observations.json', 'VERIFY.json', 'DIAGNOSIS.json', 'pairs-023-base.json',
           'pairs-023-edition.json']


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build():
    if BUILD.exists():
        shutil.rmtree(BUILD)
    BUILD.mkdir(parents=True)
    for name in SOURCES:
        shutil.copy2(HERE / name, BUILD / name)
    shutil.copy2(ROOT / 'research/STATUS.md', BUILD / 'STATUS.md')
    shutil.copy2(ROOT / 'research/ROADMAP.md', BUILD / 'ROADMAP.md')
    shutil.copytree(HERE / 'journals', BUILD / 'journals')
    (BUILD / 'results').mkdir()
    for name in RESULTS:
        shutil.copy2(HERE / name, BUILD / 'results' / name)
    (BUILD / 'packages').mkdir()
    for name, source in PACKAGES.items():
        shutil.copy2(source, BUILD / 'packages' / name)
    members = sorted(p for p in BUILD.rglob('*') if p.is_file())
    sums = ''.join(f'{sha(p)}  {p.relative_to(BUILD).as_posix()}\n' for p in members)
    (BUILD / 'SHA256SUMS').write_text(sums, encoding='utf-8')
    if SEAL.exists():
        SEAL.unlink()
    with zipfile.ZipFile(SEAL, 'w', zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(BUILD.rglob('*')):
            zf.write(path, path.relative_to(BUILD.parent).as_posix())
    with zipfile.ZipFile(SEAL) as zf:
        members = [n for n in zf.namelist() if not n.endswith('/')]
        bad = zf.testzip()
    print(json.dumps(dict(seal=SEAL.name, bytes=SEAL.stat().st_size, sha256=sha(SEAL),
                          members=len(members), testzip=bad), ensure_ascii=False))


def run(tree: pathlib.Path, script: str, extra=()):
    proc = subprocess.run([sys.executable, script, *extra], cwd=tree, capture_output=True, text=True)
    return proc.returncode, proc.stdout.strip().splitlines()[-1:] if proc.stdout else []


def replay():
    if REPLAY.exists():
        shutil.rmtree(REPLAY)
    REPLAY.mkdir(parents=True)
    with zipfile.ZipFile(SEAL) as zf:
        zf.extractall(REPLAY.parent)
    tree = REPLAY
    steps = []
    for script in ('extract.py', 'verify.py'):
        code, tail = run(tree, script)
        steps.append(dict(script=script, exit=code, tail=tail))
    shipped = tree / 'shipped'
    shipped.mkdir(exist_ok=True)
    for name in PACKAGES:
        with zipfile.ZipFile(tree / 'packages' / name) as zf:
            zf.extractall(shipped / name.replace('.zip', ''))
    lines = {}
    for line, folder in (('base', 'AgentContractKit-0.1.4'),
                         ('edition', 'AgentContractKitISAIEdition-0.1.4+docs.1')):
        code, tail = run(tree, 'pairs.py', ('--tree', str(shipped / folder / 'AgentContractLab'),
                                            '--line', line))
        lines[line] = dict(exit=code, tail=tail)
        steps.append(dict(script=f'pairs.py --line {line}', exit=code, tail=tail))
    code, tail = run(tree, 'diagnose.py',
                     ('--tree', str(shipped / 'AgentContractKit-0.1.4' / 'AgentContractLab')))
    steps.append(dict(script='diagnose.py', exit=code, tail=tail))
    equal = {}
    for name in RESULTS:
        equal[name] = sha(tree / name) == sha(tree / 'results' / name)
    out = dict(iteration='И-023', seal=SEAL.name, seal_sha256=sha(SEAL), steps=steps,
               equal=equal, identical=all(equal.values()))
    (HERE / 'REPLAY.json').write_text(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
                                      encoding='utf-8')
    print(json.dumps(dict(identical=out['identical'], equal=equal, steps=steps), ensure_ascii=False,
                     indent=1))


if __name__ == '__main__':
    {'build': build, 'replay': replay}[sys.argv[1]]()
