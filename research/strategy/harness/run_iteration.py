#!/usr/bin/env python3
"""Харнесс П3–П8 для совместимых спецификаций выпуска 0.1.36 (stdlib)."""
import argparse
from collections import Counter
import io
import json
import operator
from pathlib import Path, PurePosixPath
import re
import subprocess
import zipfile

import probes
from render import render_page, render_report

REPO = Path(__file__).resolve().parents[3]
PLAN = ['П3', 'П4', 'П5', 'П6', 'П7', 'П8']
MIN_CHECKS = 8
PROBE_FILES = {'baseline': 'BASELINE.json', 'cleanroom': 'CLEANROOM.json',
               'release_tests': 'RELEASE-TESTS.json'}
SEALED_OUTPUTS = (*PROBE_FILES.values(), 'ACCEPTANCE.json', 'REPORT.md')
PROBE_NAMES = ('baseline', 'cleanroom')
COMPARISONS = {'==': operator.eq, '!=': operator.ne, '>': operator.gt, '<': operator.lt}


class SpecError(ValueError):
    pass


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def dump_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + '\n',
                    encoding='utf-8', newline='\n')


def emit(data):
    print(json.dumps(data, ensure_ascii=False, indent=2))


def repo_path(value):
    path = PurePosixPath(value)
    if (path.is_absolute() or path.as_posix() != value or not path.parts
            or '..' in path.parts or any(c in value for c in ('\\', ':', '\x00'))):
        raise SpecError('ожидался относительный путь от корня: ' + value)
    target = REPO.joinpath(*path.parts)
    if target.resolve() != target:
        raise SpecError('путь не должен проходить через символьную ссылку: ' + value)
    return target


def text(obj, key):
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SpecError(f'{key}: нужна непустая строка')
    return value


def array(obj, key, item_type):
    value = obj.get(key)
    if not isinstance(value, list) or any(not isinstance(item, item_type) for item in value):
        raise SpecError(f'{key}: нужен массив элементов типа {item_type.__name__}')
    return value


def seal_name(spec):
    return f"AgentContractKit-Iteration-{spec['id']}.zip"


def page_name(spec):
    return f"Итерация-{spec['id']}.html"


def validate_check(check, room):
    kind = text(check, 'type')
    text(check, 'basis')
    text(check, 'criterion')
    if kind == 'json_equal':
        if text(check, 'source') not in PROBE_NAMES:
            raise SpecError('json_equal сравнивает результат пробы baseline или cleanroom')
        reference = repo_path(text(check, 'reference'))
        if not reference.is_file() or reference.is_relative_to(room):
            raise SpecError('json_equal требует существующий эталон вне каталога выхода')
    elif kind == 'json_value':
        if text(check, 'source') not in PROBE_FILES:
            raise SpecError('json_value: неизвестный источник')
        text(check, 'path')
        if text(check, 'op') not in (*COMPARISONS, 'len==') or 'value' not in check:
            raise SpecError('json_value: неизвестный оператор или отсутствует value')
    elif kind == 'steps':
        steps = array(check, 'expect', dict)
        if not steps or any(len(step) < 2 for step in steps):
            raise SpecError('steps: нужен шаг и хотя бы одно ожидаемое поле')
        names = [text(step, 'step') for step in steps]
        if len(set(names)) != len(names):
            raise SpecError('steps: повторяющийся шаг')
    elif kind == 'deterministic':
        if text(check, 'source') not in PROBE_NAMES:
            raise SpecError('deterministic: неизвестная проба')
    elif kind != 'surfaces_absent':
        raise SpecError('неизвестный тип проверки: ' + kind)


def validate(spec, spec_path):
    if not isinstance(spec, dict):
        raise SpecError('спецификация должна быть объектом')
    identifier = text(spec, 'id')
    if not re.fullmatch('[0-9]{3}', identifier):
        raise SpecError('id: ожидаются три цифры')
    room = repo_path(f'research/{identifier}')
    if spec_path != room / 'ITERATION.json':
        raise SpecError('спецификация должна находиться в research/<id>/ITERATION.json')
    for key in ('title', 'phase', 'priority', 'date', 'branch', 'goal', 'hypothesis',
                'success', 'failure', 'rollback', 'next'):
        text(spec, key)
    for key in ('touches', 'not_touched', 'expected_codes'):
        array(spec, key, str)
    for row in array(spec, 'not_run', dict):
        for key in ('what', 'why'):
            text(row, key)
    for row in array(spec, 'findings', dict):
        for key in ('id', 'text', 'basis', 'criterion', 'effect'):
            text(row, key)

    artifact = repo_path(text(spec, 'artifact_zip'))
    if not artifact.is_file() or artifact.is_relative_to(room):
        raise SpecError('артефакт выпуска должен существовать вне каталога выхода')
    if not re.fullmatch('[0-9a-f]{64}', text(spec, 'artifact_sha256')):
        raise SpecError('artifact_sha256: ожидается SHA-256 в hex')

    checks = array(spec, 'checks', dict)
    names = [text(check, 'name') for check in checks]
    if len(checks) < MIN_CHECKS or len(names) != len(set(names)):
        raise SpecError(f'нужно не менее {MIN_CHECKS} проверок с уникальными именами')
    for check in checks:
        validate_check(check, room)
    if not any(check['type'] == 'json_equal' for check in checks):
        raise SpecError('нет регрессии json_equal относительно внешнего эталона')

    outputs = {room / name for name in SEALED_OUTPUTS}
    derived = {room / name for name in ('SEAL.json', 'REPLAY.json', seal_name(spec), page_name(spec))}
    for path in outputs | derived:
        repo_path(path.relative_to(REPO).as_posix())
    members = [repo_path(name) for name in array(spec, 'seal_members', str)]
    if len(members) != len(set(members)) or set(members) & derived:
        raise SpecError('seal_members: дубликат или производный файл печати/страницы')
    if not (outputs | {spec_path}) <= set(members):
        raise SpecError('seal_members: отсутствуют обязательные результаты и/или ITERATION.json')
    if any(path not in outputs and not path.is_file() for path in members):
        raise SpecError('seal_members: входной файл не существует')
    return room, artifact


def json_path(data, path):
    for key in path.split('.'):
        data = data[int(key)] if isinstance(data, list) else data[key]
    return data


def canonical(data):
    return json.dumps(data, ensure_ascii=False, sort_keys=True).encode('utf-8')


def evaluate(check, ctx):
    kind = check['type']
    if kind == 'json_equal':
        value = ctx[check['source']]
        expected = read_json(repo_path(check['reference']))
        ok = canonical(value) == canonical(expected)
        return ok, {'source': check['source'], 'reference': check['reference'], 'equal': ok}
    if kind == 'json_value':
        value = json_path(ctx[check['source']], check['path'])
        op, want = check['op'], check['value']
        if op == 'len==':
            ok = isinstance(value, (str, dict, list)) and len(value) == want
        elif op in ('>', '<'):
            ok = (type(value) in (int, float) and type(want) in (int, float)
                  and COMPARISONS[op](value, want))
        else:
            ok = COMPARISONS[op](canonical(value), canonical(want))
        return ok, {'path': check['path'], 'op': op, 'value': value, 'want': want}
    if kind == 'steps':
        steps = {step['step']: step for step in ctx['cleanroom']['steps']}
        detail = {}
        for expected in check['expect']:
            name = expected['step']
            got = steps.get(name)
            ok = got is not None and all(k in got and got[k] == v for k, v in expected.items())
            detail[name] = {'got': got, 'ok': ok}
        return all(row['ok'] for row in detail.values()), detail
    if kind == 'surfaces_absent':
        surfaces = ctx['baseline']['surfaces']
        missing = sorted(set(probes.EXPECTED_SURFACES) - set(surfaces))
        not_absent = sorted(k for k, v in surfaces.items() if v.get('present') is not False)
        return not missing and not not_absent, {'missing': missing, 'not_absent': not_absent}
    if kind == 'deterministic':
        name = check['source']
        return ctx[name] == ctx['repeat'][name], {'source': name, 'runs': 2}
    raise SpecError('неизвестный тип проверки: ' + kind)


def acceptance(spec, ctx):
    checks = []
    for check in spec['checks']:
        try:
            ok, detail = evaluate(check, ctx)
        except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
            ok, detail = False, {'error': type(exc).__name__, 'check_type': check['type']}
        checks.append({'check': check['name'], 'status': 'pass' if ok else 'fail',
                       'basis': check['basis'], 'criterion': check['criterion'], 'detail': detail})
    skipped = [dict(row, status='not run') for row in spec['not_run']]
    counts = Counter(row['status'] for row in checks + skipped)
    return {'iteration': 'И-' + spec['id'], 'phase': spec['phase'], 'checks': checks,
            'not_run': skipped, 'counts': {key: counts[key] for key in ('pass', 'fail', 'not run')},
            'outcome': 'rejected' if counts['fail'] else 'accepted'}


def seal_bytes(spec):
    buffer = io.BytesIO()
    # Постоянные метаданные и ZIP_STORED: повтор не зависит от mtime и версии zlib.
    with zipfile.ZipFile(buffer, 'w') as archive:
        for name in sorted(spec['seal_members']):
            info = zipfile.ZipInfo(name)
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, repo_path(name).read_bytes())
    raw = buffer.getvalue()
    return raw, {'file': seal_name(spec), 'format': 1, 'iteration': 'И-' + spec['id'],
                 'members': len(spec['seal_members']), 'bytes': len(raw),
                 'sha256': probes.sha256_bytes(raw)}


def replay_seal(spec, room):
    recorded = read_json(room / 'SEAL.json')
    raw, rebuilt = seal_bytes(spec)
    archived = (room / seal_name(spec)).read_bytes()
    return {'outcome': 'ok' if recorded == rebuilt and archived == raw else 'mismatch',
            'recorded_sha256': recorded.get('sha256') if isinstance(recorded, dict) else None,
            'rebuilt_sha256': rebuilt['sha256'],
            'archive_sha256': probes.sha256_bytes(archived)}


def run_iteration(spec, room, artifact):
    actual_hash = probes.sha256_bytes(artifact.read_bytes())
    if actual_hash != spec['artifact_sha256']:
        emit({'error': 'artifact_digest_mismatch', 'expected': spec['artifact_sha256'], 'actual': actual_hash})
        return 1

    # П3: код из checkout измеряет закреплённый артефакт; П4: новые временные деревья.
    loaders = {'baseline': probes.inventory, 'cleanroom': probes.clean_room}
    ctx = {name: probe(artifact) for name, probe in loaders.items()}
    repeat = {c['source'] for c in spec['checks'] if c['type'] == 'deterministic'}
    ctx['repeat'] = {name: probe(artifact) for name, probe in loaders.items() if name in repeat}
    ctx['release_tests'] = probes.release_suite(artifact)
    for name, filename in PROBE_FILES.items():
        dump_json(room / filename, ctx[name])

    # П5–П6: приёмка и итоговый отчёт больше не меняются после формирования печати.
    result = acceptance(spec, ctx)
    dump_json(room / 'ACCEPTANCE.json', result)
    (room / 'REPORT.md').write_text(render_report(spec, ctx, result), encoding='utf-8', newline='\n')

    # П7–П8: повтор не перезаписывает архив или манифест. Страница строится один раз.
    raw, seal = seal_bytes(spec)
    (room / seal_name(spec)).write_bytes(raw)
    dump_json(room / 'SEAL.json', seal)
    replay = replay_seal(spec, room)
    dump_json(room / 'REPLAY.json', replay)
    (room / page_name(spec)).write_text(render_page(spec, ctx, result, seal, replay),
                                        encoding='utf-8', newline='\n')
    ok = result['outcome'] == 'accepted' and replay['outcome'] == 'ok'
    emit({'iteration': result['iteration'], 'outcome': 'accepted' if ok else 'rejected',
          'counts': result['counts'], 'release_tests': ctx['release_tests']['totals'],
          'seal': seal, 'replay': replay['outcome']})
    return 0 if ok else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', action='store_true')
    mode.add_argument('--verify-seal', action='store_true')
    args = parser.parse_args(argv)

    try:
        spec_path = (REPO / args.spec).resolve()
        spec = read_json(spec_path)
        room, artifact = validate(spec, spec_path)
    except (OSError, ValueError) as exc:
        emit({'error': 'spec_invalid', 'message': str(exc)})
        return 2

    try:
        if args.dry_run:
            emit({'plan': PLAN, 'checks': [check['name'] for check in spec['checks']],
                  'seal_members': spec['seal_members']})
            return 0
        if args.verify_seal:
            replay = replay_seal(spec, room)
            emit(replay)
            return 0 if replay['outcome'] == 'ok' else 1
        return run_iteration(spec, room, artifact)
    except (OSError, ValueError, subprocess.TimeoutExpired, zipfile.BadZipFile, KeyError) as exc:
        emit({'error': 'run_error', 'message': str(exc)})
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
