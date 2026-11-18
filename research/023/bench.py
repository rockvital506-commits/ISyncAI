#!/usr/bin/env python3
"""Стенд И-023: восемь настоящих журналов + один написанный рукой контроль.

Каждый журнал — объединённый stdout+stderr настоящей команды, записанный как есть.
Провенанс (команда, код возврата, время, версии, отпечаток файла) пишется в journals/provenance.json.
Скрипт ничего не правит в выводе: только запускает и сохраняет.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tarfile
import urllib.request

HERE = pathlib.Path(__file__).absolute().parent
ROOT = HERE.parents[1]
JOURNALS = HERE / 'journals'
WORK = pathlib.Path(os.environ.get('ISAI023_WORK_DIR', '/tmp/isai023'))
REQUESTS_TAG = 'v2.32.3'
REQUESTS_URL = f'https://codeload.github.com/psf/requests/tar.gz/refs/tags/{REQUESTS_TAG}'


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def version(cmd) -> str:
    out = subprocess.run(cmd, capture_output=True, text=True)
    return (out.stdout or out.stderr).strip().splitlines()[0]


def run(journal_id, cmd, cwd, env_extra=None, note='', kind='journal'):
    """Запускает команду, пишет объединённый вывод дословно, возвращает запись провенанса."""
    env = dict(os.environ)
    env.update(env_extra or {})
    started = dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    proc = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, errors='replace')
    finished = dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    log = JOURNALS / f'{journal_id}.log'
    log.write_text(proc.stdout + proc.stderr, encoding='utf-8', newline='')
    return dict(id=journal_id, kind=kind, command=cmd, cwd=str(cwd), exit_code=proc.returncode,
                started=started, finished=finished, log=log.name, log_lines=log.read_text().count('\n'),
                log_bytes=log.stat().st_size, log_sha256=sha(log), note=note)


def main():
    JOURNALS.mkdir(parents=True, exist_ok=True)
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)

    # --- подготовка стенда: тоже настоящие команды, но это не журналы, а вход ---
    tarball = WORK / 'requests.tar.gz'
    urllib.request.urlretrieve(REQUESTS_URL, tarball)
    with tarfile.open(tarball) as tf:
        tf.extractall(WORK)
    repo = WORK / f'requests-{REQUESTS_TAG[1:]}'
    deps = WORK / 'deps'
    setup = []
    setup.append(run('setup-pip-deps', ['pip3', 'install', '-q', '--target', str(deps), '-r',
                                        'requirements-dev.txt'], repo, note='вход стенда', kind='setup'))

    env_pytest = {'PYTHONPATH': f'{deps}:{repo / "src"}', 'PYTHONDONTWRITEBYTECODE': '1'}
    gulp_dir = WORK / 'gulp'
    gulp_dir.mkdir()
    nolock_dir = WORK / 'nolock'
    nolock_dir.mkdir()

    journals = [
        run('pip-resolver', ['pip3', 'download', '-d', str(WORK / 'out'), 'flask==3.0.*', 'werkzeug<2'],
            WORK, note='конфликт требований'),
        run('pip-build', ['pip3', 'install', '--no-cache-dir', '--target', str(WORK / 't6'),
                          'pycrypto==2.6.1'], WORK, note='сборка из исходников'),
        run('pytest-run1', ['python3', '-m', 'pytest', '-q', '-p', 'no:cacheprovider', 'tests'],
            repo, env_pytest, note='первый прогон набора'),
        run('pytest-run2', ['python3', '-m', 'pytest', '-q', '-p', 'no:cacheprovider', 'tests'],
            repo, env_pytest, note='второй прогон того же кода'),
        run('pytest-utils', ['python3', '-m', 'pytest', '-q', '-p', 'no:cacheprovider', 'tests/test_utils.py'],
            repo, env_pytest, note='другой набор того же проекта'),
        run('npm-install', ['npm', 'install', '--no-audit', '--no-fund', 'gulp@3.9.1'],
            gulp_dir, note='установка старого пакета'),
        run('npm-audit', ['npm', 'audit'], gulp_dir, note='проверка уязвимостей'),
        run('npm-ci-nolock', ['npm', 'ci'], nolock_dir, note='npm ci без замка'),
    ]

    # --- контроль: журнал, написанный рукой. В приёмку не входит ---
    authored = JOURNALS / 'authored-control.log'
    authored.write_text(
        'Run tests (authored control)\n'
        '=============================\n'
        'collected 12 items\n'
        '\n'
        'tests/test_sample.py::test_build FAILED\n'
        '\n'
        'FAILED tests/test_sample.py::test_build - TypeError: unsupported operand type(s)\n'
        '1 failed, 11 passed in 0.42s\n', encoding='utf-8')

    provenance = dict(
        iteration='И-023', line='journals bench', created=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
        host=dict(os_name=os.uname().sysname, release=os.uname().release, machine=os.uname().machine,
                  python=sys.version.split()[0], pip=version(['pip3', '--version']).split()[1],
                  node=version(['node', '-v']), npm=version(['npm', '-v'])),
        sources=dict(requests=dict(repo='psf/requests', tag=REQUESTS_TAG, tarball=REQUESTS_URL,
                                   tarball_sha256=sha(tarball), path=str(repo)),
                     gulp=dict(registry='npm', spec='gulp@3.9.1')),
        setup=setup, journals=journals,
        authored=dict(id='authored-control', log=authored.name, log_sha256=sha(authored),
                      note='написан рукой, в приёмку не входит; контроль критерия происхождения'))
    (HERE / 'journals' / 'provenance.json').write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    for row in journals:
        print(f"{row['id']:16} rc={row['exit_code']:>3}  строк {row['log_lines']:>4}  {row['log_bytes']:>7} B")
    print('authored-control написан рукой (контроль)')


if __name__ == '__main__':
    main()
