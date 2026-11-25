#!/usr/bin/env python3
"""Опытный JSON-lines протокол нового workspace; не доверенная установка релиза."""
from __future__ import annotations

import json
import sys
from pathlib import Path

if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kit.base import schema_v2
from kit.atomic_init import AtomicInitializationSession
from kit.init_workspace import InitializationError, InitializationSession, MAX_L0

# План содержит L0, закодированный внутри JSON. Наихудшее экранирование — шесть байтов на
# один исходный ASCII-байт, плюс накладные поля и L1/L2; не разбивать большую строку на команды.
MAX_LINE = 16 * 1024 * 1024


def respond(value):
    sys.stdout.write(json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False) + '\n')
    sys.stdout.flush()


def main():
    session = None
    while True:
        line = sys.stdin.buffer.readline(MAX_LINE + 1)
        if not line:
            return 0
        if len(line) > MAX_LINE:
            session = None
            respond({'outcome':'error', 'code':'input_too_large'})
            return 1
        try:
            obj = schema_v2.parse_json(line)
            if type(obj) is not dict or type(obj.get('type')) is not str:
                raise ValueError('request')
            if obj == {'type':'cancel'}:
                session = None
                respond({'outcome':'cancelled'})
            elif obj['type'] in ('plan','plan_atomic') and set(obj) == {'type','destination','profile_root','l0_utf8','system_pin'}:
                session = None
                if any(type(obj[k]) is not str for k in ('destination','profile_root','l0_utf8','system_pin')):
                    raise ValueError('request')
                if any(len(obj[k].encode('utf-8')) > 4096 for k in ('destination','profile_root')):
                    raise ValueError('request')
                raw = obj['l0_utf8'].encode('utf-8')
                if len(raw) > MAX_L0:
                    raise InitializationError('system_invalid')
                factory = AtomicInitializationSession if obj['type'] == 'plan_atomic' else InitializationSession
                session = factory(obj['destination'], profile_root=obj['profile_root'],
                                  l0_bytes=raw, system_pin=obj['system_pin'])
                try:
                    plan = session.plan()
                except InitializationError:
                    session = None
                    raise
                respond(plan)
            elif (obj['type'] == 'apply' and set(obj) == {'type','plan','confirmed_ticket'}
                  and type(obj['plan']) is dict and type(obj['confirmed_ticket']) is str):
                if session is None:
                    raise InitializationError('ticket_unknown')
                respond(session.apply(obj['plan'], confirmed_ticket=obj['confirmed_ticket']))
            else:
                raise ValueError('request')
        except InitializationError as error:
            respond({'outcome':'error', 'code':str(error)})
        except (schema_v2.SchemaError, ValueError, TypeError, UnicodeError, RecursionError):
            session = None
            respond({'outcome':'error', 'code':'invalid_request'})


if __name__ == '__main__':
    raise SystemExit(main())
