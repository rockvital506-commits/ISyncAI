#!/usr/bin/env python3
"""Одна сессия планов v2 через JSON-строки stdin/stdout; установка не выполняется."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Для прямого запуска -I; при импорте проверенным загрузчиком не расширяем sys.path.
if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kit.base import schema_v2
from kit.base.operation_card import compile_prompt
from kit.base.operation_plan import PlanSession
from kit.base.registry_store import Layout, StoreError

MAX_LINE = 1_048_576


def respond(data):
    sys.stdout.write(json.dumps(data, ensure_ascii=False, sort_keys=True, allow_nan=False) + '\n')
    sys.stdout.flush()


def main(*, preflight=None, bootstrap=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--profile-root', required=True)
    parser.add_argument('--profile-id', required=True)
    args = parser.parse_args()
    try:
        session = PlanSession(Layout(args.workspace, args.profile_root), profile_id=args.profile_id)
    except (TypeError, ValueError):
        print('invalid_profile_id', file=sys.stderr)
        return 2
    while True:
        line = sys.stdin.buffer.readline(MAX_LINE + 1)
        if not line:
            return 0
        if len(line) > MAX_LINE:
            # Не разбивать одну чрезмерную команду на несколько трактуемых запросов.
            session._pending = None
            respond({'outcome': 'error', 'code': 'input_too_large'})
            return 1
        if preflight is not None:
            try:
                preflight()
            except Exception:
                # Отказ проверки отзывает даже ранее показанный ожидающий план.
                session._pending = None
                respond({'outcome': 'error', 'code': 'runtime_preflight_failed'})
                continue
        try:
            data = schema_v2.parse_json(line)
            if type(data) is not dict or type(data.get('type')) is not str:
                raise ValueError('request')
            mode = data['type']
            if mode == 'bootstrap' and set(data) == {'type'} and bootstrap is not None:
                respond(bootstrap)
            elif mode == 'plan' and set(data) == {'type', 'request'} and type(data['request']) is str:
                plan = session.plan(compile_prompt(data['request']))
                respond(plan)
            elif (mode == 'apply' and set(data) in ({'type', 'plan', 'confirmed_ticket'},
                                                     {'type', 'plan', 'confirmed_ticket', 'allow_delete'})
                  and type(data['plan']) is dict and type(data['confirmed_ticket']) is str
                  and ('allow_delete' not in data or type(data['allow_delete']) is bool)):
                result = session.apply(data['plan'], confirmed_ticket=data['confirmed_ticket'],
                                       allow_delete=data.get('allow_delete', False))
                respond(result)
            elif mode == 'cancel' and set(data) == {'type'}:
                session._pending = None
                respond({'outcome': 'cancelled'})
            else:
                raise ValueError('request')
        except StoreError as exc:
            respond({'outcome': 'error', 'diagnostic': exc.diagnostic()})
        except (schema_v2.SchemaError, ValueError, TypeError, UnicodeError, RecursionError):
            # Некорректная новая команда не сохраняет потенциально забытый ожидающий план.
            session._pending = None
            respond({'outcome': 'error', 'code': 'invalid_request'})


if __name__ == '__main__':
    raise SystemExit(main())
