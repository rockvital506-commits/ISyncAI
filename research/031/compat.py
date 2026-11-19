#!/usr/bin/env python3
"""И-025: переход 0.1.4 → 0.1.5 на данных предыдущего выпуска.

Проверяется три вещи, и все три — без правки файлов:
  1. данные, записанные 0.1.4, читаются 0.1.5 и не переписываются;
  2. повтор того же наблюдения по правилу 0.1.5 не создаёт записи и не меняет файл;
  3. наблюдение, пришедшее из другого места (другой журнал, другая строка), остаётся тем же.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import shutil
import sys
import tempfile

HERE = pathlib.Path(__file__).absolute().parent
ap = __import__('argparse').ArgumentParser()
ap.add_argument('--old', required=True, help='дерево 0.1.4')
ap.add_argument('--new', required=True, help='дерево 0.1.5')
args = ap.parse_args()


def load(tree, name):
    spec = importlib.util.spec_from_file_location(name, pathlib.Path(tree) / 'kit/tools/contract.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    old_tree, new_tree = pathlib.Path(args.old).absolute(), pathlib.Path(args.new).absolute()
    old, new = load(old_tree, 'old_contract'), load(new_tree, 'new_contract')
    lab = pathlib.Path(tempfile.mkdtemp(prefix='i025-'))
    shutil.copytree(old_tree / 'releases', lab / 'releases')
    # данные 0.1.5 кладём рядом, чтобы установка нового выпуска была возможна в том же проекте
    for name in (new_tree / 'releases').iterdir():
        target = lab / 'releases' / name.name
        if not target.exists():
            shutil.copytree(name, target)
    project = 'P0'
    (lab / project).mkdir()
    old_version = old.parse((old_tree / 'kit/base/manifest.json').read_bytes())['base_version']
    new_version = new.parse((new_tree / 'kit/base/manifest.json').read_bytes())['base_version']
    env = {k: 'synthetic' for k in old.ENV_KEYS.split()}
    base = dict(case='compat', level=3, conditions='Linux fixture, прогон один', expected='Тесты проходят.',
                actual='Итог прогона: 1 failed, 589 passed in 77.89s (0:01:17).', status='pass',
                evidence='tests.log, строка 400', limits='только наличие', environment=env)

    def approved(module, request):
        view = module.dispatch(lab, project, 'plan', request)
        return module.dispatch(lab, project, 'apply', {'request': request, 'ticket': view['ticket']})

    approved(old, dict(op='install', package=f'releases/{old_version}',
                       pin=old.digest((old_tree / 'kit/base/manifest.json').read_bytes())))
    approved(old, dict(op='connect'))
    first = approved(old, dict(op='record_check', observation=dict(base)))
    written = (lab / project / old.CHECKS).read_bytes()

    # новый проект на 0.1.5, в него кладётся файл наблюдений предыдущего выпуска
    project = 'P1'
    (lab / project).mkdir()
    approved(new, dict(op='install', package=f'releases/{new_version}',
                       pin=new.digest((new_tree / 'kit/base/manifest.json').read_bytes())))
    approved(new, dict(op='connect'))
    (lab / project / new.CHECKS).parent.mkdir(parents=True, exist_ok=True)
    (lab / project / new.CHECKS).write_bytes(written)
    read_back = new.parse(written)
    untouched = (lab / project / new.CHECKS).read_bytes() == written
    status_after = new.dispatch(lab, project, 'status', {})
    repeat = approved(new, dict(op='record_check', observation=dict(
        base, actual='Итог прогона: 1 failed, 589 passed in 77.86s (0:01:18).',
        evidence='other.log, строка 91')))
    after_repeat = (lab / project / new.CHECKS).read_bytes() == written
    different = approved(new, dict(op='record_check', observation=dict(
        base, actual='Итог прогона: 1 failed, 590 passed in 77.86s (0:01:18).')))

    out = dict(iteration='И-030', old_version=old_version, new_version=new_version,
               first_write=first['outcome'], records_written=len(read_back['checks']),
               old_data_reads=len(read_back['checks']) == 1, old_data_untouched=untouched,
               observations_after_status=len(status_after['observations']),
               repeat_outcome=repeat['outcome'], repeat_kept_bytes=after_repeat,
               different_outcome=different['outcome'], checks_bytes=len(written))
    shutil.rmtree(lab, ignore_errors=True)
    out['ok'] = (out['first_write'] == 'committed' and out['old_data_reads'] and out['old_data_untouched']
                 and out['repeat_outcome'] == 'no_change' and out['repeat_kept_bytes']
                 and out['different_outcome'] == 'committed')
    (HERE / 'COMPAT.json').write_text(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
                                      encoding='utf-8')
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
