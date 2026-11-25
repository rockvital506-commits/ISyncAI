#!/usr/bin/env python3
"""Опытная интерактивная оболочка обычных операций над закреплённой сессией."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import unicodedata

MAX_INPUT = 65536
MAX_REPLY = 16 * 1024 * 1024
MAX_COMMAND = 1_048_576


class TerminalError(Exception):
    pass


def display(value):
    """Полный JSON; экранировать терминальные и невидимые форматирующие символы."""
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
    text = ''.join(('\\u%04x' % ord(ch) if ord(ch) <= 0xffff else '\\U%08x' % ord(ch))
                   if unicodedata.category(ch) in ('Cf', 'Cs', 'Cc') and ch not in '\n\r\t'
                   else ch for ch in text)
    print(text, flush=True)


def ask(prompt):
    print(prompt, end='', flush=True)
    raw = sys.stdin.buffer.readline(MAX_INPUT + 1)
    if not raw:
        raise EOFError
    if len(raw) > MAX_INPUT or not raw.endswith(b'\n'):
        raise TerminalError('input_too_large_or_incomplete')
    try:
        return raw.rstrip(b'\r\n').decode('utf-8')
    except UnicodeDecodeError as exc:
        raise TerminalError('invalid_utf8') from exc


class Backend:
    def __init__(self, args):
        script = Path(__file__).resolve().parent/'snapshot_session.py'
        command = [sys.executable, '-I', '-S', '-B', str(script),
                   '--candidate-root', args.candidate_root, '--workspace', args.workspace,
                   '--profile-root', args.profile_root, '--profile-id', args.profile_id,
                   '--manifest-pin', args.manifest_pin, '--system-pin', args.system_pin]
        self.proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=None, close_fds=True)

    def request(self, value):
        wire = (json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)+'\n').encode('utf-8')
        if len(wire) > MAX_COMMAND:
            raise TerminalError('command_too_large')
        try:
            self.proc.stdin.write(wire)
            self.proc.stdin.flush()
            raw = self.proc.stdout.readline(MAX_REPLY + 1)
            if not raw or len(raw) > MAX_REPLY or not raw.endswith(b'\n'):
                raise TerminalError('backend_response_unavailable')
            result = json.loads(raw.decode('utf-8'))
            if type(result) is not dict or type(result.get('outcome')) is not str:
                raise TerminalError('backend_response_invalid')
            return result
        except (OSError, UnicodeError, ValueError, BrokenPipeError, RecursionError) as exc:
            raise TerminalError('backend_response_unavailable') from exc

    def close(self):
        if self.proc.stdin:
            try:
                self.proc.stdin.close()
            except OSError:
                pass
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
        if self.proc.stdout:
            self.proc.stdout.close()


def context_review(backend, mode, scope):
    """Владелец классифицирует каждую запись; контекст никому не доставляется."""
    print('Контекст не доставляется агенту; безопасность, полнота и смысл не проверены.', flush=True)
    report = backend.request({'type':'applicable','scope':scope})
    display(report)
    if report.get('outcome') != 'applicable':
        return
    rows = report.get('entries')
    inputs = report.get('inputs_sha256')
    if type(rows) is not list or type(inputs) is not dict:
        raise TerminalError('applicability_invalid')
    choices = {'include':[], 'exclude':[]}
    seen = set()
    for row in rows:
        if type(row) is not dict or row.get('area') not in ('L0','L1','L2') or type(row.get('entry')) is not dict:
            raise TerminalError('applicability_invalid')
        if row['area'] == 'L0':
            continue
        ident = row['entry'].get('id')
        if type(ident) is not str or (row['area'],ident) in seen:
            raise TerminalError('applicability_invalid')
        seen.add((row['area'],ident))
        display(row)
        decision = ask('Введите включить или исключить; иной ответ отменяет обзор: ')
        if decision not in ('включить','исключить'):
            display({'outcome':'context_cancelled'})
            return
        choices['include' if decision == 'включить' else 'exclude'].append({'area':row['area'],'id':ident})
    result = backend.request({'type':'context','mode':mode,'scope':scope,'choices':choices})
    if result.get('outcome') == 'review_required' and result.get('inputs_sha256') != inputs:
        display({'outcome':'error','code':'context_inputs_changed',
                 'message':'Источники изменились после показа. Начните обзор заново.'})
        return
    display(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('candidate-root','workspace','profile-root','profile-id','manifest-pin','system-pin'):
        parser.add_argument('--'+name, required=True)
    args = parser.parse_args()
    if not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode):
        print('Требуется Python -I -S -B.', file=sys.stderr); return 2
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print('Требуется интерактивный терминал для ввода и полного показа плана.', file=sys.stderr); return 2
    backend = None
    applying = False
    try:
        backend = Backend(args)
        bootstrap = backend.request({'type':'bootstrap'})
        display(bootstrap)
        if bootstrap.get('outcome') != 'bootstrap':
            return 1
        print('Введите обычную фразу, /контекст project|kit scope или /выход. Ответы могут содержать секреты.', flush=True)
        while True:
            phrase = ask('\nЗапрос> ')
            if phrase == '/выход':
                return 0
            if not phrase.strip():
                continue
            if phrase.startswith('/контекст'):
                parts = phrase.split()
                if len(parts) != 3 or parts[0] != '/контекст' or parts[1] not in ('project','kit'):
                    display({'outcome':'error','code':'context_command_invalid'})
                else:
                    context_review(backend, parts[1], parts[2])
                continue
            plan = backend.request({'type':'plan','request':phrase})
            display(plan)
            if plan.get('outcome') != 'planned':
                continue
            card = plan.get('card')
            ticket = plan.get('ticket')
            if type(card) is not dict or type(ticket) is not str or type(card.get('operation')) is not str:
                raise TerminalError('invalid_plan')
            operation = card['operation']
            apply = {'type':'apply','plan':plan,'confirmed_ticket':ticket}
            if operation == 'delete':
                apply['allow_delete'] = True
            # Backend имеет жёсткий предел размера команды. Нельзя спрашивать согласие,
            # если этот полный план заведомо нельзя передать обратно.
            if len((json.dumps(apply,ensure_ascii=False,separators=(',', ':'))+'\n').encode('utf-8')) > MAX_COMMAND:
                display({'outcome':'error','code':'plan_too_large_to_apply'})
                backend.request({'type':'cancel'})
                continue
            if ask('Для показанного плана введите ПОДТВЕРЖДАЮ; иной ответ отменяет: ') != 'ПОДТВЕРЖДАЮ':
                display(backend.request({'type':'cancel'}))
                continue
            if operation == 'delete' and ask('Удаление: отдельно введите УДАЛИТЬ; иной ответ отменяет: ') != 'УДАЛИТЬ':
                display(backend.request({'type':'cancel'}))
                continue
            applying = True
            result = backend.request(apply)
            display(result)
            applying = False
    except (EOFError, KeyboardInterrupt):
        if applying:
            print('\nИсход применения неизвестен; проверьте состояние, не повторяйте вслепую.', file=sys.stderr)
            return 1
        print('\nВыход без подтверждения ожидающего плана.', file=sys.stderr)
        return 0
    except (OSError, TerminalError, ValueError) as exc:
        print('Ошибка терминальной сессии: '+str(exc), file=sys.stderr)
        if applying:
            print('Исход применения неизвестен; проверьте состояние, не повторяйте вслепую.', file=sys.stderr)
        return 1
    finally:
        if backend is not None:
            backend.close()


if __name__ == '__main__':
    raise SystemExit(main())
