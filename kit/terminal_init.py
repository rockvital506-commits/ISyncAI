#!/usr/bin/env python3
"""Опытная терминальная инициализация нового workspace; не установка кода."""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import subprocess
import sys

if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kit import init_workspace as init, move_recovery_inspect as reader, terminal_session as ui

PIN = re.compile(r'[0-9a-f]{64}\Z')


def _read_l0(value,pin):
    if type(pin) is not str or PIN.fullmatch(pin) is None:
        raise ui.TerminalError('independent_pin_required')
    path = Path(value)
    if not path.is_absolute() or '..' in path.parts or not path.name:
        raise ui.TerminalError('l0_path_invalid')
    parent = None
    try:
        parent, _ = init._open_parent(path.parent)
        raw = reader._read(parent,path.name,init.MAX_L0)
        if not hmac.compare_digest(hashlib.sha256(raw).hexdigest(),pin):
            raise ui.TerminalError('l0_pin_mismatch')
        return raw.decode('utf-8')
    except ui.TerminalError:
        raise
    except (init.InitializationError,OSError,ValueError,TypeError,UnicodeError,AttributeError,NotImplementedError) as exc:
        raise ui.TerminalError('l0_unavailable') from exc
    finally:
        if parent is not None:
            try:os.close(parent)
            except OSError as exc:raise ui.TerminalError('l0_unavailable') from exc


class InitBackend(ui.Backend):
    def __init__(self):
        script=Path(__file__).resolve().parent/'init_workspace_cli.py'
        self.proc=subprocess.Popen([sys.executable,'-I','-S','-B',str(script)],stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE,stderr=None,close_fds=True)


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    if not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode):
        print('Требуется Python -I -S -B.',file=sys.stderr);return 2
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print('Требуется интерактивный терминал для ввода и полного показа плана.',file=sys.stderr);return 2
    backend=None;applying=False
    try:
        print('Только новый workspace: не установка кода и не обновление существующего проекта. '
              'L0 и план могут содержать секреты.',flush=True)
        destination=ui.ask('Абсолютный путь нового workspace: ')
        profile=ui.ask('Относительный корень нового профиля: ')
        l0_path=ui.ask('Абсолютный путь доверенного файла L0: ')
        pin=ui.ask('Отдельно удостоверенный SHA-256 L0: ')
        text=_read_l0(l0_path,pin)
        backend=InitBackend()
        plan=backend.request({'type':'plan_atomic','destination':destination,'profile_root':profile,
                              'l0_utf8':text,'system_pin':pin})
        ui.display(plan)
        if plan.get('outcome')!='planned':return 1
        ticket=plan.get('ticket')
        if type(ticket) is not str:raise ui.TerminalError('plan_invalid')
        apply={'type':'apply','plan':plan,'confirmed_ticket':ticket}
        if len((json.dumps(apply,ensure_ascii=False,separators=(',', ':'))+'\n').encode('utf-8'))>ui.MAX_COMMAND:
            backend.request({'type':'cancel'})
            ui.display({'outcome':'error','code':'plan_too_large_to_apply'})
            return 1
        if ui.ask('Для полного показанного плана введите ПОДТВЕРЖДАЮ; иной ответ отменяет: ')!='ПОДТВЕРЖДАЮ':
            ui.display(backend.request({'type':'cancel'}));return 0
        applying=True
        result=backend.request(apply)
        ui.display(result)
        applying=False
        if result.get('outcome')!='published_unverified_origin':
            print('Инициализация не подтверждена; не повторяйте и не удаляйте staging вслепую.',file=sys.stderr)
            return 1
        print('Создан новый workspace; происхождение L0, права и применение агентом не подтверждены.',flush=True)
        return 0
    except (EOFError,KeyboardInterrupt):
        print('\nВыход без отправки неподтверждённого плана.',file=sys.stderr)
        return 1 if applying else 0
    except (OSError,ui.TerminalError,ValueError,TypeError,RecursionError) as exc:
        print('Ошибка терминальной инициализации: '+str(exc),file=sys.stderr);return 1
    finally:
        if applying:
            print('Исход отправленной публикации неизвестен; не повторяйте и не удаляйте staging вслепую.',file=sys.stderr)
        if backend is not None:backend.close()


if __name__=='__main__':raise SystemExit(main())
