#!/usr/bin/env python3
"""И-027: печать и повтор.

  seal.py build   — собрать build/Iteration-027 (скрипты, стенды, результаты, оба архива 0.1.7)
  seal.py replay  — распаковать печать, прогнать из неё оба стенда и совместимость заново,
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
RELEASE = HERE.parent / 'release-0.1.7'
BUILD = HERE / 'build' / 'Iteration-027'
REPLAY = HERE / 'replay' / 'Iteration-027'
SEAL = HERE / 'AgentContractKit-Iteration-027.zip'
PACKAGES = {
    'AgentContractKit-0.1.7.zip': RELEASE / 'AgentContractKit-0.1.7.zip',
    'AgentContractKitISAIEdition-0.1.7+docs.1.zip': RELEASE / 'AgentContractKitISAIEdition-0.1.7+docs.1.zip',
}
SOURCES = ['DESIGN.md', 'REPORT.md', 'EXPECTATIONS.json', 'adapter_check.py', 'pairs_corpus.py',
           'pairs_journals.py', 'compat.py', 'acceptance.py']
RESULTS = ['adapter-base.json', 'adapter-edition.json', 'pairs-027-base.json', 'pairs-027-edition.json',
           'pairs-027-journals-base.json', 'pairs-027-journals-edition.json', 'COMPAT.json',
           'EXPECTATIONS.json']
PREVIOUS = {'prev-0.1.6.zip': HERE.parent / 'release-0.1.6/AgentContractKit-0.1.6.zip'}
TREES = {
    'AgentContractKit-0.1.7': 'base',
    'AgentContractKitISAIEdition-0.1.7+docs.1': 'edition',
}


def sha(path) -> str:
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def build():
    if BUILD.exists():
        shutil.rmtree(BUILD)
    BUILD.mkdir(parents=True)
    for name in SOURCES:
        shutil.copy2(HERE / name, BUILD / name)
    shutil.copy2(ROOT / 'research/STATUS.md', BUILD / 'STATUS.md')
    shutil.copy2(ROOT / 'research/ROADMAP.md', BUILD / 'ROADMAP.md')
    # стенды: корпус и журналы едут внутрь, чтобы повтор был самодостаточным
    shutil.copy2(ROOT / 'research/020/corpus.py', BUILD / 'corpus.py')
    shutil.copy2(HERE.parent / '023/observations.json', BUILD / 'observations.json')
    shutil.copytree(HERE.parent / '023/journals', BUILD / 'journals')
    (BUILD / 'results').mkdir()
    for name in RESULTS:
        shutil.copy2(HERE / name, BUILD / 'results' / name)
    (BUILD / 'packages').mkdir()
    for name, path in {**PACKAGES, **PREVIOUS}.items():
        shutil.copy2(path, BUILD / 'packages' / name)
    for name in ('build.py', 'pipeline_check.py'):
        shutil.copy2(RELEASE / name, BUILD / name)
    members = sorted(p for p in BUILD.rglob('*') if p.is_file())
    (BUILD / 'SHA256SUMS').write_text(
        ''.join(f'{sha(p)}  {p.relative_to(BUILD).as_posix()}\n' for p in members), encoding='utf-8')
    if SEAL.exists():
        SEAL.unlink()
    with zipfile.ZipFile(SEAL, 'w', zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(BUILD.rglob('*')):
            zf.write(path, path.relative_to(BUILD.parent).as_posix())
    with zipfile.ZipFile(SEAL) as zf:
        total = len([n for n in zf.namelist() if not n.endswith('/')])
        bad = zf.testzip()
    print(json.dumps(dict(seal=SEAL.name, bytes=SEAL.stat().st_size, sha256=sha(SEAL), members=total,
                          testzip=bad), ensure_ascii=False))


def run(tree, script, *args):
    proc = subprocess.run([sys.executable, script, *args], cwd=tree, capture_output=True, text=True)
    return proc.returncode, (proc.stdout or proc.stderr).strip().splitlines()[-1:]


def replay():
    if REPLAY.exists():
        shutil.rmtree(REPLAY)
    REPLAY.mkdir(parents=True)
    with zipfile.ZipFile(SEAL) as zf:
        zf.extractall(REPLAY.parent)
    tree = REPLAY
    shipped = tree / 'shipped'
    shipped.mkdir()
    for name, folder in (('AgentContractKit-0.1.7.zip', 'base'),
                         ('AgentContractKitISAIEdition-0.1.7+docs.1.zip', 'edition')):
        with zipfile.ZipFile(tree / 'packages' / name) as zf:
            zf.extractall(shipped / folder)
    with zipfile.ZipFile(tree / 'packages' / 'prev-0.1.6.zip') as zf:
        zf.extractall(shipped / 'prev')
    steps = []
    for folder in ('base', 'edition'):
        tree_path = shipped / folder / 'AgentContractLab'
        proc = subprocess.run([sys.executable, 'adapter_check.py', '--tree', str(tree_path),
                               '--line', folder, '--adapter', 'copilot'], cwd=tree,
                              capture_output=True, text=True)
        steps.append(dict(script='adapter_check.py', line=folder, exit=proc.returncode,
                          tail=(proc.stdout or proc.stderr).strip().splitlines()[-1:]))
        for script, args, out in (
                ('pairs_corpus.py', ('--tree', str(tree_path), '--line', folder),
                 f"pairs-027-{folder}.json"),
                ('pairs_journals.py', ('--tree', str(tree_path), '--line', folder),
                 f"pairs-027-journals-{folder}.json")):
            proc = subprocess.run([sys.executable, script, *args], cwd=tree, capture_output=True, text=True)
            if script == 'pairs_corpus.py' and proc.stdout.strip():
                (tree / out).write_text(proc.stdout, encoding='utf-8')
            steps.append(dict(script=script, line=folder, exit=proc.returncode,
                              tail=(proc.stdout or proc.stderr).strip().splitlines()[-1:]))
    proc = subprocess.run([sys.executable, 'compat.py',
                           '--old', str(shipped / 'prev' / 'AgentContractLab'),
                           '--new', str(shipped / 'base' / 'AgentContractLab')],
                          cwd=tree, capture_output=True, text=True)
    steps.append(dict(script='compat.py (данные 0.1.6 под 0.1.7)', exit=proc.returncode,
                      tail=(proc.stdout or proc.stderr).strip().splitlines()[-1:]))
    equal = {name: sha(tree / name) == sha(tree / 'results' / name)
             for name in RESULTS if (tree / name).exists()}
    out = dict(iteration='И-027', seal=SEAL.name, seal_sha256=sha(SEAL), steps=steps, equal=equal,
               identical=all(equal.values()) and len(equal) == len(RESULTS))
    (HERE / 'REPLAY.json').write_text(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
                                      encoding='utf-8')
    print(json.dumps(dict(identical=out['identical'], equal=equal,
                          steps=[s['script'] + ' ' + s.get('line', '') for s in steps]), ensure_ascii=False,
                     indent=1))


if __name__ == '__main__':
    {'build': build, 'replay': replay}[sys.argv[1]]()
