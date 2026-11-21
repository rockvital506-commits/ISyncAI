#!/usr/bin/env python3
"""Замороженная разметка И-113: входы синтетические, протокол не сохраняет значения."""
from collections import Counter
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import platform
import sys
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
from kit.base import schema_v2

MODULE = 'kit/base/project_specificity.py'
FIELDS = ('id', 'parent', 'scope', 'title', 'text', 'basis', 'criterion', 'key', 'value')
CODES = {
    'path': ('posix_local', 'windows_drive', 'unc_path', 'home_path', 'file_uri', 'project_prefix'),
    'project_name': ('known_project',),
    'machine': ('known_machine',),
    'secret': ('credential_assignment', 'credential_value', 'bearer_literal', 'private_key_header'),
}
OUTCOMES = ('no_markers', 'project_specific', 'possible_secret', 'invalid_input')


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def fixture(book, case):
    kind = case['kind']
    entry = {'kind': kind, 'id': 'R-fixture', 'parent': None if kind == 'contract' else 'C-fixture',
             'authority': 'project_owner', 'state': 'draft', 'scope': '.',
             'title': 'Предложение о сверке', 'text': 'Покажи проверенное основание перед выводом.',
             'basis': 'Синтетическая разметка', 'criterion': 'Основание и критерий указаны отдельно.'}
    entry.update(case.get('fields', {}))
    context = deepcopy({**book['context'], **case.get('context', {})})
    mode = case.get('mode')
    if mode == 'pem-marker':
        # Только признак формата; ни тела ключа, ни даже фиктивного криптографического материала.
        entry['text'] = 'Образец заголовка: ' + '-' * 5 + 'BEGIN ' + 'RSA ' + 'PRIVATE KEY' + '-' * 5
    elif mode == 'envelope':
        entry = {'area': 'L2', 'schema_version': 2, 'revision': 0, 'roots': ['sandbox'], 'entries': [entry]}
    elif mode == 'oversize-entry':
        entry['text'] = 'x' * 65_537
    elif mode == 'oversize-context':
        context['project_names'] = [f'dummy-{i}' for i in range(33)]
    return entry, context


def safe_view(value):
    """Не выводим сырой результат даже при регрессии: только фиксированный словарь кодов."""
    if type(value) is not dict or canonical(value.get('analysis_format')) != b'1':
        return None
    outcome = value.get('outcome')
    if type(outcome) is not str or outcome not in OUTCOMES or type(value.get('findings')) is not list:
        return None
    keys = {'analysis_format', 'outcome', 'findings'}
    if outcome == 'invalid_input':
        keys.add('code')
        if value.get('code') not in ('invalid_entry', 'invalid_context') or value['findings']:
            return None
    if value.keys() != keys:
        return None
    for f in value['findings']:
        if (type(f) is not dict or f.keys() != {'field', 'category', 'code'}
                or any(type(v) is not str for v in f.values())
                or f['field'] not in FIELDS or f['code'] not in CODES.get(f['category'], ())):
            return None
    return value


class Guard:
    """Счётчик I/O и аналогов в фазе вызова: перехватываем до доступа, без записи аргументов."""
    def __init__(self):
        self.active = False
        self.events = 0
        sys.addaudithook(self._audit)

    def _fail(self, *_args, **_kwargs):
        self.events += 1
        raise AssertionError('detector_io')

    def _audit(self, event, _args):
        if self.active and (event == 'open' or event.startswith(('os.', 'socket.', 'subprocess.', 'tempfile.', 'urllib.'))):
            self._fail()

    def _environment(self):
        trap = self._fail

        class Denied:
            get = keys = items = values = copy = __iter__ = __getitem__ = __setitem__ = __contains__ = __len__ = trap

        return Denied()

    def call(self, fn):
        stdout, stderr = io.StringIO(), io.StringIO()
        self.events = 0
        with ExitStack() as stack:
            stack.enter_context(redirect_stdout(stdout))
            stack.enter_context(redirect_stderr(stderr))
            stack.enter_context(patch.object(os, 'environ', self._environment()))
            for method in ('getcwd', 'getenv', 'stat', 'lstat'):
                stack.enter_context(patch.object(os, method, self._fail))
            self.active = True
            try:
                value, error = fn(), False
            except Exception:  # Никаких исходных значений или текста исключения в артефактах.
                value, error = None, True
            finally:
                self.active = False
        return value, {'exception': error, 'io_events': self.events, 'quiet': not stdout.getvalue() and not stderr.getvalue()}


def expected_observation(case):
    return {'classification': case['expected'], 'calls': 2, 'io_events': 0, 'quiet': True,
            'inputs_unchanged': True, 'stable': True, 'safe_shape': True, 'exceptions': 0}


def observe(inspect, book, case, guard):
    entry, context = fixture(book, case)
    reversed_context = {k: list(reversed(v)) if type(v) is list else v for k, v in reversed(list(context.items()))}
    again = deepcopy(entry)
    before = canonical([entry, context, again, reversed_context])
    first, a = guard.call(lambda: inspect(entry, context=context))
    second, b = guard.call(lambda: inspect(again, context=reversed_context))
    try:
        left, right = safe_view(first), safe_view(second)
        unchanged = canonical([entry, context, again, reversed_context]) == before
        stable = left is not None and right is not None and canonical(left) == canonical(right)
    except (TypeError, ValueError, RecursionError):
        left, right, unchanged, stable = None, None, False, False
    return {'classification': left, 'calls': 2, 'io_events': a['io_events'] + b['io_events'],
            'quiet': a['quiet'] and b['quiet'], 'inputs_unchanged': unchanged, 'stable': stable,
            'safe_shape': left is not None and right is not None, 'exceptions': int(a['exception']) + int(b['exception'])}


def baseline(book, guard):
    control = next(c for c in book['cases'] if c['id'] == 'S01')
    entry, _ = fixture(book, control)
    doc = {'schema_version': 2, 'area': 'L2', 'roots': ['sandbox'], 'revision': 0, 'entries': [
        dict(entry, id='C-fixture', kind='contract', parent=None, text='Синтетический родитель.'), entry]}
    before = canonical(doc)
    result, facts = guard.call(lambda: schema_v2.validate_registry(doc, expected_area='L2'))
    return {'missing': MODULE, 'control': 'S01', 'schema_accepted': result is None and not facts['exception'],
            'unchanged': canonical(doc) == before, **facts}


def main():
    book = json.loads((HERE / 'CASES.json').read_bytes())
    guard = Guard()
    if not (ROOT / MODULE).is_file():
        red = baseline(book, guard)
        rows = [{'id': c['id'], 'status': 'fail', 'reason': 'detector_missing'} for c in book['cases']]
    else:
        from kit.base.project_specificity import inspect_entry
        red = None
        rows = []
        for case in book['cases']:
            observation = observe(inspect_entry, book, case, guard)
            ok = canonical(observation) == canonical(expected_observation(case))
            rows.append({'id': case['id'], 'status': 'pass' if ok else 'fail', 'observation': observation})
    tally = Counter(r['status'] for r in rows)
    print(json.dumps({'format': 1, 'os': platform.system(), 'python': platform.python_version(), 'baseline': red,
                      'rows': rows, 'counts': {k: tally[k] for k in ('pass', 'fail', 'not run')}}, ensure_ascii=False))
    return int(tally['fail'] != 0)


if __name__ == '__main__':
    raise SystemExit(main())
