#!/usr/bin/env python3
"""Опытное терминальное наблюдение и отдельные действия при незавершённом переносе."""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import sys

if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kit import init_workspace as init, move_recovery_inspect as reader
from kit import terminal_move as move, terminal_session as ui

MAX_INTENT = 16 * 1024 * 1024
PIN = re.compile(r'[0-9a-f]{64}\Z')
ACTIONS = {'execute','finalize','cancel_reservation','cancel_partial','cleanup_stage'}
DESTRUCTIVE = {'finalize','cancel_reservation','cancel_partial','cleanup_stage'}
EXPECTED = {'execute':'registries_updated_marker_retained','finalize':'marker_removed_after_both',
            'cancel_reservation':'reservation_cancelled','cancel_partial':'partial_marker_removed',
            'cleanup_stage':'selected_stage_removed'}


def _read_external(value, pin, args):
    if type(pin) is not str or PIN.fullmatch(pin) is None:
        raise ui.TerminalError('independent_pin_required')
    move._external_destination(value,args)
    path = Path(value)
    parent = None
    try:
        parent, _ = init._open_parent(path.parent)
        raw = reader._read(parent,path.name,MAX_INTENT)
        if not hmac.compare_digest(hashlib.sha256(raw).hexdigest(),pin):
            raise ui.TerminalError('intent_pin_mismatch')
        return raw.decode('utf-8')
    except ui.TerminalError:
        raise
    except (init.InitializationError,OSError,ValueError,TypeError,UnicodeError,AttributeError,NotImplementedError) as exc:
        raise ui.TerminalError('intent_unavailable') from exc
    finally:
        if parent is not None:
            try: os.close(parent)
            except OSError as exc: raise ui.TerminalError('intent_unavailable') from exc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('candidate-root','workspace','profile-root','manifest-pin','system-pin'):
        parser.add_argument('--'+name,required=True)
    args = parser.parse_args()
    if not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode):
        print('Требуется Python -I -S -B.',file=sys.stderr); return 2
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print('Требуется интерактивный терминал для ввода и полного показа планов.',file=sys.stderr); return 2
    backend = None
    applying = False
    try:
        print('Неизвестный marker или стадия не являются разрешением на удаление. '
              'Совпадение префикса не доказывает происхождения. Данные могут содержать секреты.',flush=True)
        path = ui.ask('Абсолютный путь внешней доверенной копии intent: ')
        pin = ui.ask('Отдельно удостоверенный SHA-256 intent: ')
        intent = _read_external(path,pin,args)
        backend = move.MoveBackend(args)
        configured = backend.request({'type':'configure','intent_utf8':intent,'intent_pin':pin})
        ui.display(configured)
        if configured.get('outcome') != 'configured': return 1
        observed = backend.request({'type':'inspect'})
        ui.display(observed)
        if observed.get('code') == 'runtime_preflight_failed': return 1
        print('Наблюдение не является разрешением или рекомендацией. Частичный marker может не читаться inspect.',flush=True)
        while True:
            action = ui.ask('Действие inspect, execute, finalize, cancel_reservation, cancel_partial, cleanup_stage или /выход: ')
            if action == '/выход': return 0
            if action == 'inspect':
                observed = backend.request({'type':'inspect'}); ui.display(observed)
                if observed.get('code') == 'runtime_preflight_failed': return 1
                continue
            if action not in ACTIONS:
                ui.display({'outcome':'error','code':'action_invalid'})
                continue
            extra = {}
            if action == 'cleanup_stage':
                extra['area'] = ui.ask('Область L1 или L2: ')
                extra['name'] = ui.ask('Точное имя стадии: ')
            response = backend.request({'type':'plan','action':action,**extra})
            ui.display(response)
            if response.get('outcome') != 'planned' or type(response.get('plan')) is not dict:
                return 1
            plan = response['plan']; ticket = plan.get('ticket')
            if type(ticket) is not str: raise ui.TerminalError('plan_invalid')
            apply = {'type':'apply','plan':plan,'confirmed_ticket':ticket}
            if len((json.dumps(apply,ensure_ascii=False,separators=(',', ':'))+'\n').encode('utf-8')) > ui.MAX_COMMAND:
                backend.request({'type':'cancel'})
                ui.display({'outcome':'error','code':'plan_too_large_to_apply'})
                return 1
            if action in DESTRUCTIVE:
                if ui.ask('Независимо проверено происхождение и право? Введите ПРОВЕРЕНО; иной ответ отменяет: ') != 'ПРОВЕРЕНО':
                    ui.display(backend.request({'type':'cancel'})); return 0
            if ui.ask('Для полного показанного плана введите ПОДТВЕРЖДАЮ; иной ответ отменяет: ') != 'ПОДТВЕРЖДАЮ':
                ui.display(backend.request({'type':'cancel'})); return 0
            applying = True
            result = backend.request(apply)
            ui.display(result)
            applying = False
            if result.get('outcome') != EXPECTED[action]:
                print('Остановлено после отказа или неожиданного ответа; состояние необходимо выяснить отдельно, не повторяйте вслепую.',file=sys.stderr)
                return 1
            print('Этап завершён; следующий шаг не выбран автоматически.',flush=True)
    except (EOFError,KeyboardInterrupt):
        print('\nВыход без отправки неподтверждённого этапа.',file=sys.stderr)
        return 1 if applying else 0
    except (OSError,ui.TerminalError,ValueError,TypeError,RecursionError) as exc:
        print('Ошибка терминальной диагностики: '+str(exc),file=sys.stderr); return 1
    finally:
        if applying:
            print('Исход отправленного этапа неизвестен; не повторяйте и не удаляйте marker вслепую.',file=sys.stderr)
        if backend is not None: backend.close()


if __name__ == '__main__':
    raise SystemExit(main())
