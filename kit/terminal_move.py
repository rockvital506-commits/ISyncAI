#!/usr/bin/env python3
"""Опытный терминальный перенос через закреплённую move-сессию; не установщик."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kit import terminal_session as ui


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate key')
        result[key] = value
    return result


def _object(text):
    value = json.loads(text, object_pairs_hook=_unique,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError('constant')))
    if type(value) is not dict:
        raise ValueError('object required')
    return value


def _external_destination(value, args):
    """Ограничение расположения, не защита от замены или mount-алиасов."""
    try:
        path = Path(value)
        if not path.is_absolute() or '..' in path.parts or not path.name or path.name == '.move-pending':
            raise ValueError('path')
        target = path.parent.resolve(strict=True) / path.name
        roots = (Path(args.workspace).resolve(strict=True), Path(args.candidate_root).resolve(strict=True),
                 Path(__file__).resolve(strict=True).parent)
        if any(target == root or root in target.parents for root in roots):
            raise ValueError('protected')
        return target
    except (OSError, ValueError, TypeError, RuntimeError) as exc:
        raise ui.TerminalError('intent_destination_invalid') from exc


class MoveBackend(ui.Backend):
    def __init__(self, args):
        script = Path(__file__).resolve().parent/'snapshot_move_session.py'
        command = [sys.executable, '-I', '-S', '-B', str(script),
                   '--candidate-root', args.candidate_root, '--workspace', args.workspace,
                   '--profile-root', args.profile_root, '--manifest-pin', args.manifest_pin,
                   '--system-pin', args.system_pin]
        self.proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=None, close_fds=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('candidate-root','workspace','profile-root','manifest-pin','system-pin'):
        parser.add_argument('--'+name, required=True)
    args = parser.parse_args()
    if not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode):
        print('Требуется Python -I -S -B.', file=sys.stderr); return 2
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print('Требуется интерактивный терминал для ввода и полного показа планов.', file=sys.stderr); return 2
    backend = None
    state = {'applying':False, 'marker_possible':False}
    try:
        print('Перенос удаляет исходную запись после записи цели. Все ответы и intent могут содержать секреты.', flush=True)
        source = ui.ask('Источник L1 или L2: ')
        if source not in ('L1','L2'):
            raise ui.TerminalError('source_invalid')
        target = 'L2' if source == 'L1' else 'L1'
        ident = ui.ask('ID исходной записи: ')
        candidate = _object(ui.ask('Полная целевая запись, один JSON-объект: '))
        portability = None
        if source == 'L2':
            portability = _object(ui.ask('Признаки переносимости, JSON-объект project_names/machine_names/project_paths: '))
        backend = MoveBackend(args)
        built = backend.request({'type':'build','source':source,'target':target,'entry_id':ident,
                                 'candidate':candidate,'portability_context':portability})
        ui.display(built)
        if built.get('outcome') != 'intent_draft_only':
            return 1
        raw, pin = built.get('intent_utf8'), built.get('intent_sha256')
        if type(raw) is not str or type(pin) is not str:
            raise ui.TerminalError('intent_invalid')
        configured = backend.request({'type':'configure','intent_utf8':raw,'intent_pin':pin})
        ui.display(configured)
        if configured.get('outcome') != 'configured':
            return 1
        dest = ui.ask('Абсолютный путь новой внешней копии intent (пустая строка отменяет): ')
        if not dest:
            return 0
        protected = _external_destination(dest,args)

        def step(action, expected, **extra):
            response = backend.request({'type':'plan','action':action, **extra})
            ui.display(response)
            if response.get('outcome') != 'planned' or type(response.get('plan')) is not dict:
                return False
            plan = response['plan']; ticket = plan.get('ticket')
            if type(ticket) is not str:
                raise ui.TerminalError('plan_invalid')
            apply = {'type':'apply','plan':plan,'confirmed_ticket':ticket}
            if len((json.dumps(apply,ensure_ascii=False,separators=(',', ':'))+'\n').encode('utf-8')) > ui.MAX_COMMAND:
                ui.display({'outcome':'error','code':'plan_too_large_to_apply'})
                backend.request({'type':'cancel'})
                return False
            if ui.ask('Для этого плана введите ПОДТВЕРЖДАЮ; иной ответ останавливает: ') != 'ПОДТВЕРЖДАЮ':
                ui.display(backend.request({'type':'cancel'}))
                return False
            if action == 'export' and _external_destination(dest,args) != protected:
                raise ui.TerminalError('intent_destination_changed')
            # После отправки reserve marker может существовать даже без ответа.
            if action == 'reserve':
                state['marker_possible'] = True
            state['applying'] = True
            result = backend.request(apply)
            ui.display(result)
            state['applying'] = False
            if result.get('outcome') != expected:
                return False
            if action == 'finalize':
                state['marker_possible'] = False
            return True

        if not step('export','exported_unverified_origin',destination=dest):
            return 1
        print('Сохраните показанный intent_sha256 отдельно от файла по доверенному каналу.', flush=True)
        if ui.ask('Введите PIN СОХРАНЁН после отдельного сохранения pin; иной ответ останавливает: ') != 'PIN СОХРАНЁН':
            return 0
        for action, outcome in (('reserve','reserved_not_moved'),
                                ('execute','registries_updated_marker_retained'),
                                ('finalize','marker_removed_after_both')):
            if not step(action,outcome):
                return 1
        print('Этапы завершены. Это не подтверждение прав, доверенной поставки или устойчивости к отказу питания.', flush=True)
        return 0
    except (EOFError, KeyboardInterrupt):
        print('\nОстановлено; неподтверждённые этапы не отправлены.', file=sys.stderr)
        return 1 if state['applying'] or state['marker_possible'] else 0
    except (OSError, ui.TerminalError, ValueError, TypeError, RecursionError) as exc:
        print('Ошибка терминального переноса: '+str(exc), file=sys.stderr)
        return 1
    finally:
        if state['applying']:
            print('Исход отправленного этапа неизвестен; не повторяйте вслепую.', file=sys.stderr)
        if state['marker_possible']:
            print('Marker может существовать. Не удаляйте его и не повторяйте вслепую; '
                  'сохраните внешний intent и pin, используйте отдельную диагностику восстановления.', file=sys.stderr)
        if backend is not None:
            backend.close()


if __name__ == '__main__':
    raise SystemExit(main())
