#!/usr/bin/env python3
"""И-052: исходная точка для ядра — что уже измерено до правок.

Ядро лежит в `.isai/`, а импортируется как `isai` (pyproject: package-dir). Чтобы прогон шёл из
репозитория без установки пакета, скрипт кладёт рядом временный каталог со ссылкой `isai -> .isai`
и запускает `pytest` с ним в PYTHONPATH.

    python3 baseline.py            — прогон в репозитории и запись BASELINE.json
    python3 baseline.py --compare  — плюс прогон в чистой копии без research/ и dist/
    python3 baseline.py --dry-run  — только показать команду

Зависимости прогона: pydantic>=2.7, pytest>=8, hypothesis>=6.100. Их наличие проверяется отдельно и
попадает в BASELINE.json: отсутствие зависимости — это «not run», а не «pass».
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).absolute().parent
ROOT = HERE.parents[1]
CORE = ROOT / '.isai'
TESTS = ROOT / 'tests'
NEED = ('pydantic', 'pytest', 'hypothesis')


def modules() -> dict:
    out = {}
    for name in NEED:
        try:
            mod = __import__(name)
            out[name] = getattr(mod, 'VERSION', None) or getattr(mod, '__version__', 'present')
        except Exception as exc:  # noqa: BLE001 — отсутствие зависимости это факт, а не сбой
            out[name] = None
    return out


def main() -> int:
    found = modules()
    missing = [n for n, v in found.items() if v is None]
    if '--dry-run' in sys.argv:
        print(f'PYTHONPATH=<tmp>/isai={CORE} python3 -m pytest {TESTS} -q')
        return 0
    if missing:
        out = {'iteration': 'И-052', 'core_version': version(), 'ran': False, 'missing': missing,
               'modules': found, 'counts': {'pass': 0, 'fail': 0, 'not_run': 'all'},
               'note': 'Зависимости не установлены: прогон не выполнялся, провалом не считается.'}
        (HERE / 'BASELINE.json').write_text(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
                                            encoding='utf-8')
        print(json.dumps({'ran': False, 'missing': missing}, ensure_ascii=False))
        return 0
    counts = run_suite(ROOT)
    failed = counts.pop('failed')
    errors = []
    out = {'iteration': 'И-052', 'core_version': version(), 'ran': True, 'modules': found, 'counts': counts,
           'failed': failed, 'errors': errors,
           'note': 'Исходная точка до правок: ядро прогоняется в этой машине впервые за линию.'}
    if '--compare' in sys.argv:
        copy = clean_copy()
        try:
            out['clean_copy'] = run_suite(copy)
        finally:
            import shutil
            shutil.rmtree(copy, ignore_errors=True)
        out['clean_copy']['what'] = 'копия репозитория без research/, dist/ и .git' 
    (HERE / 'BASELINE.json').write_text(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
                                        encoding='utf-8')
    print(json.dumps({'ran': True, 'counts': counts, 'failed': out['failed']}, ensure_ascii=False, indent=1))
    return 0


def run_suite(root: pathlib.Path) -> dict:
    """Прогон набора в указанном корне; отчёт junit читается, а не угадывается по последней строке."""
    with tempfile.TemporaryDirectory(prefix='isai-path-') as tmp:
        link = pathlib.Path(tmp) / 'isai'
        link.symlink_to(root / '.isai', target_is_directory=True)
        env = dict(os.environ, PYTHONPATH=tmp, PYTHONDONTWRITEBYTECODE='1')
        report = pathlib.Path(tmp) / 'junit.xml'
        proc = subprocess.run([sys.executable, '-m', 'pytest', str(root / 'tests'), '-q', '--no-header',
                               '-p', 'no:cacheprovider', f'--junitxml={report}'],
                              cwd=str(root), capture_output=True, text=True, env=env)
        result = junit(report)
        text = proc.stdout + proc.stderr
        result['failed'] = [f'{f}::{t}' for f, t in sorted(set(re.findall(r'^FAILED (\S+?)::(\S+)', text, flags=re.M)))]
        result['exit'] = proc.returncode
    return result


def clean_copy() -> pathlib.Path:
    """Копия репозитория без research/, dist/ и .git — чтобы отделить дефект от состава каталогов."""
    tmp = pathlib.Path(tempfile.mkdtemp(prefix='isai-clean-'))
    with open(tmp / 'repo.tar', 'wb') as sink:
        subprocess.run(['tar', '-cf', '-', '--exclude=research', '--exclude=dist', '--exclude=.git',
                        '--exclude=build', '.'], cwd=str(ROOT), check=True, stdout=sink,
                       stderr=subprocess.DEVNULL)
    subprocess.run(['tar', '-xf', str(tmp / 'repo.tar')], cwd=str(tmp), check=True)
    (tmp / 'repo.tar').unlink()
    return tmp


def junit(path) -> dict:
    """Считаем по отчёту, а не по последней строке: pytest с -q её не печатает."""
    import xml.etree.ElementTree as ET
    root = ET.parse(path).getroot()
    suite = root if root.tag == 'testsuite' else root.find('testsuite')
    total, fail = int(suite.get('tests', 0)), int(suite.get('failures', 0))
    errors = int(suite.get('errors', 0))
    skipped = int(suite.get('skipped', 0))
    return {'pass': total - fail - errors - skipped, 'fail': fail, 'error': errors, 'skipped': skipped,
            'total': total}


def version() -> str:
    text = (ROOT / 'pyproject.toml').read_text(encoding='utf-8')
    found = re.search(r'^version = "([^"]+)"', text, flags=re.M)
    return found.group(1) if found else '?'


if __name__ == '__main__':
    raise SystemExit(main())
