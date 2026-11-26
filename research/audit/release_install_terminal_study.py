#!/usr/bin/env python3
"""Стендовая терминальная установка нового контейнера; не доверенная доставка."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path[:0]=[str(ROOT),str(HERE)]
from kit import terminal_session as ui


class Backend(ui.Backend):
    def __init__(self,args):
        cmd=[sys.executable,'-I','-S','-B',str(HERE/'release_install_cli_study.py')]
        for name in ('archive','statement','policy','policy-pin','signature-hex','openssl',
                     'openssl-pin','destination','profile-root'):
            cmd.extend(['--'+name,getattr(args,name.replace('-','_'))])
        self.proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=None,close_fds=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('archive','statement','policy','policy-pin','signature-hex','openssl',
                 'openssl-pin','destination','profile-root'):
        parser.add_argument('--'+name,required=True)
    args=parser.parse_args()
    if not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode):
        print('Требуется Python -I -S -B.',file=sys.stderr);return 2
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print('Требуется интерактивный терминал для полного показа плана.',file=sys.stderr);return 2
    backend=None;applying=False
    try:
        print('Исследование: только новый контейнер; происхождение, полномочия и восстановление не проверены. '
              'План может содержать чувствительные данные.',flush=True)
        backend=Backend(args)
        plan=backend.request({'type':'plan'});ui.display(plan)
        if plan.get('outcome')!='planned':return 1
        ticket=plan.get('ticket')
        if type(ticket) is not str:raise ui.TerminalError('plan_invalid')
        command={'type':'apply','plan':plan,'confirmed_ticket':ticket}
        if len((json.dumps(command,ensure_ascii=False,separators=(',', ':'))+'\n').encode('utf-8'))>ui.MAX_COMMAND:
            backend.request({'type':'cancel'});ui.display({'outcome':'error','code':'plan_too_large_to_apply'});return 1
        if ui.ask('Для полного показанного плана введите ПОДТВЕРЖДАЮ; иной ответ отменяет: ')!='ПОДТВЕРЖДАЮ':
            ui.display(backend.request({'type':'cancel'}));return 0
        applying=True
        result=backend.request(command)
        ui.display(result)
        if result.get('outcome')!='study_container_published_unverified_origin':
            print('Не повторяйте и не удаляйте стадию или цель вслепую.',file=sys.stderr);return 1
        applying=False
        print('Контейнер создан в исследовательской пробе; источник и полномочия не удостоверены.',flush=True)
        return 0
    except (EOFError,KeyboardInterrupt):
        if not applying: print('\nВыход без отправки неподтверждённого плана.',file=sys.stderr)
        return 1 if applying else 0
    except (OSError,ui.TerminalError,ValueError,TypeError,RecursionError) as error:
        print('Ошибка терминальной сессии: '+str(error),file=sys.stderr);return 1
    finally:
        if applying:
            print('Исход отправленной публикации неизвестен; не повторяйте и не удаляйте стадию вслепую.',file=sys.stderr)
        if backend is not None:backend.close()


if __name__=='__main__':raise SystemExit(main())
