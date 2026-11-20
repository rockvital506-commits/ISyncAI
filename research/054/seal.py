#!/usr/bin/env python3
"""И-054: печать и повтор.

  seal.py build   — собрать build/Iteration-054 (скрипты, стенд обкатки, три корпуса через консоль, результаты, архивы 0.1.34)
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
RELEASE = HERE.parent / 'release-0.1.34'
BUILD = HERE / 'build' / 'Iteration-054'
REPLAY = HERE / 'replay' / 'Iteration-054'
SEAL = HERE / 'AgentContractKit-Iteration-054.zip'
PACKAGES = {
    'AgentContractKit-0.1.34.zip': RELEASE / 'AgentContractKit-0.1.34.zip',
    'AgentContractKitISAIEdition-0.1.34+docs.1.zip': RELEASE / 'AgentContractKitISAIEdition-0.1.34+docs.1.zip',
}
SOURCES = ['DESIGN.md', 'REPORT.md', 'EXPECTATIONS.json', 'pilot.py', 'stand_env.py', 'stand_reader.py', 'pairs_cli.py',
           'pairs_journals.py', 'compat.py', 'acceptance.py']
RESULTS = ['PILOT-base.json', 'PILOT-edition.json',
           'pairs-054-cli-punct-base.json', 'pairs-054-cli-punct-edition.json',
           'pairs-054-cli-corpus80-base.json', 'pairs-054-cli-corpus80-edition.json',
           'pairs-054-cli-corpus112-base.json', 'pairs-054-cli-corpus112-edition.json',
           'pairs-054-journals-base.json', 'pairs-054-journals-edition.json',
           'COMPAT.json', 'EXPECTATIONS.json']
PREVIOUS = {'prev-0.1.33.zip': HERE.parent / 'release-0.1.33/AgentContractKit-0.1.33.zip'}
TREES = {
    'AgentContractKit-0.1.34': 'base',
    'AgentContractKitISAIEdition-0.1.34+docs.1': 'edition',
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
    shutil.copy2(HERE.parent / '030/pairs-030-corpus.json', BUILD / 'pairs-030-corpus.json')
    shutil.copy2(HERE.parent / '030/pairs-029-corpus.json', BUILD / 'pairs-029-corpus.json')
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
    # Печать не должна зависеть от момента сборки: иначе её sha тасуется при том же содержимом (F32).
    with zipfile.ZipFile(SEAL, 'w', zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(BUILD.rglob('*')):
            name = path.relative_to(BUILD.parent).as_posix()
            info = zipfile.ZipInfo(name + '/' if path.is_dir() else name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            if path.is_dir():
                zf.writestr(info, b'')
            else:
                info.external_attr = 0o644 << 16
                zf.writestr(info, path.read_bytes())
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
    for name, folder in (('AgentContractKit-0.1.34.zip', 'base'),
                         ('AgentContractKitISAIEdition-0.1.34+docs.1.zip', 'edition')):
        with zipfile.ZipFile(tree / 'packages' / name) as zf:
            zf.extractall(shipped / folder)
    with zipfile.ZipFile(tree / 'packages' / 'prev-0.1.33.zip') as zf:
        zf.extractall(shipped / 'prev')
    steps = []
    for folder in ('base', 'edition'):
        tree_path = shipped / folder / 'AgentContractLab'
        for script, extra, out in (('pilot.py', (), f"PILOT-{folder}.json"),
                                   ('pairs_cli.py', ('--set', 'punct'), f"pairs-054-cli-punct-{folder}.json"),
                                   ('pairs_cli.py', ('--set', 'corpus80'), f"pairs-054-cli-corpus80-{folder}.json"),
                                   ('pairs_cli.py', ('--set', 'corpus112'), f"pairs-054-cli-corpus112-{folder}.json"),
                                   ('pairs_journals.py', (), f"pairs-054-journals-{folder}.json")):
            proc = subprocess.run([sys.executable, script, '--tree', str(tree_path),
                                   '--line', folder, *extra], cwd=tree, capture_output=True, text=True)
            steps.append(dict(script=script, line=folder, exit=proc.returncode,
                              tail=(proc.stdout or proc.stderr).strip().splitlines()[-1:]))
    proc = subprocess.run([sys.executable, 'compat.py',
                           '--old', str(shipped / 'prev' / 'AgentContractLab'),
                           '--new', str(shipped / 'base' / 'AgentContractLab')],
                          cwd=tree, capture_output=True, text=True)
    steps.append(dict(script='compat.py (данные 0.1.33 под 0.1.34)', exit=proc.returncode,
                      tail=(proc.stdout or proc.stderr).strip().splitlines()[-1:]))
    equal = {name: sha(tree / name) == sha(tree / 'results' / name)
             for name in RESULTS if (tree / name).exists()}
    out = dict(iteration='И-054', seal=SEAL.name, seal_sha256=sha(SEAL), steps=steps, equal=equal,
               identical=all(equal.values()) and len(equal) == len(RESULTS))
    (HERE / 'REPLAY.json').write_text(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
                                      encoding='utf-8')
    print(json.dumps(dict(identical=out['identical'], equal=equal,
                          steps=[s['script'] + ' ' + s.get('line', '') for s in steps]), ensure_ascii=False,
                     indent=1))


if __name__ == '__main__':
    {'build': build, 'replay': replay}[sys.argv[1]]()
