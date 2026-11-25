#!/usr/bin/env python3
"""Опытная JSON-lines сессия переноса, не sandbox и не доверенная поставка."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

if __name__=='__main__':
    sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from kit import (move_execution, move_finalize, move_intent_export, move_partial_cancel,
                 move_recovery_inspect, move_reservation, move_stage_cleanup)
from kit.base import move_intent, registry_store, schema_v2
from kit.base.registry_policy import StoreError

# План включает intent и полные диффы. Это ограничение команды, не гарантия доступной памяти.
MAX_LINE=96*1024*1024
_ERROR=re.compile(r'[a-z0-9_]{1,100}\Z')


class MoveConsole:
    def __init__(self,layout):
        self.layout=layout;self.raw=None;self.pin=None;self.pending=None

    def _cancel(self):
        if self.pending is not None:
            self.pending.cancel();self.pending=None

    def _configured(self):
        if self.raw is None:raise StoreError('move_intent_required','intent')

    def handle(self,data):
        if type(data) is not dict or type(data.get('type')) is not str:raise ValueError('request')
        kind=data['type']
        if kind=='apply':
            if (set(data)!={'type','plan','confirmed_ticket'} or type(data['plan']) is not dict
                    or type(data['confirmed_ticket']) is not str):
                self._cancel();raise ValueError('request')
            if self.pending is None:raise StoreError('ticket_unknown','ticket')
            return self.pending.apply(data['plan'],confirmed_ticket=data['confirmed_ticket'])
        # Любая новая команда, даже ошибочная, отзывает предыдущий план.
        self._cancel()
        if kind=='cancel' and set(data)=={'type'}:
            return {'outcome':'plan_cancelled','intent_retained':self.raw is not None}
        if kind=='build' and set(data)=={'type','source','target','entry_id','candidate','portability_context'}:
            self.raw=None;self.pin=None
            current=registry_store._load(self.layout)
            report,raw=move_intent.build(current.raw,source=data['source'],target=data['target'],entry_id=data['entry_id'],
                                         candidate=data['candidate'],portability_context=data['portability_context'])
            return {'outcome':'intent_draft_only','intent_utf8':raw.decode('utf-8'),
                    'intent_sha256':report['intent_sha256'],'report':report,'configured':False}
        if kind=='configure' and set(data)=={'type','intent_utf8','intent_pin'}:
            self.raw=None;self.pin=None
            if type(data['intent_utf8']) is not str or type(data['intent_pin']) is not str:raise ValueError('request')
            raw=data['intent_utf8'].encode('utf-8');_,before,_=move_intent._verified(raw,data['intent_pin'])
            move_recovery_inspect._check_intent_roots(self.layout,before)
            self.raw=raw;self.pin=data['intent_pin']
            return {'outcome':'configured','intent_sha256':self.pin,'origin':'not_verified','authorization':'not_checked'}
        if kind=='inspect' and set(data)=={'type'}:
            self._configured();return move_recovery_inspect.inspect(self.layout,intent_pin=self.pin)
        if kind=='plan' and type(data.get('action')) is str:
            self._configured();action=data['action'];keys=set(data)
            common={'layout':self.layout,'intent_bytes':self.raw,'intent_pin':self.pin}
            if action in ('reserve','cancel_reservation') and keys=={'type','action'}:
                obj=move_reservation.ReservationSession(**common)
                plan=obj.plan(action='reserve' if action=='reserve' else 'cancel')
            elif action=='execute' and keys=={'type','action'}:
                obj=move_execution.MoveExecutionSession(**common);plan=obj.plan()
            elif action=='finalize' and keys=={'type','action'}:
                obj=move_finalize.MoveFinalizationSession(**common);plan=obj.plan()
            elif action=='cancel_partial' and keys=={'type','action'}:
                obj=move_partial_cancel.PartialReservationCancelSession(**common);plan=obj.plan()
            elif (action=='cleanup_stage' and keys=={'type','action','area','name'}
                  and type(data['area']) is str and type(data['name']) is str):
                obj=move_stage_cleanup.MoveStageCleanupSession(**common);plan=obj.plan(area=data['area'],name=data['name'])
            elif action=='export' and keys=={'type','action','destination'} and type(data['destination']) is str:
                obj=move_intent_export.IntentExportSession(Path(data['destination']),intent_bytes=self.raw,intent_pin=self.pin);plan=obj.plan()
            else:raise ValueError('request')
            self.pending=obj
            return {'outcome':'planned','action':action,'plan':plan}
        raise ValueError('request')


def main(*, preflight=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',type=Path,required=True);parser.add_argument('--profile-root',required=True)
    args=parser.parse_args();session=MoveConsole(registry_store.Layout(args.workspace,args.profile_root))
    def respond(value):
        sys.stdout.write(json.dumps(value,ensure_ascii=False,sort_keys=True,allow_nan=False)+'\n');sys.stdout.flush()
    while True:
        line=sys.stdin.buffer.readline(MAX_LINE+1)
        if not line:return 0
        if len(line)>MAX_LINE:
            session._cancel();respond({'outcome':'error','code':'input_too_large'});return 1
        if preflight is not None:
            try:preflight()
            except Exception:
                session._cancel();session.raw=None;session.pin=None
                respond({'outcome':'error','code':'runtime_preflight_failed'});continue
        try:
            data=schema_v2.parse_json(line)
            respond(session.handle(data))
        except StoreError as error:
            respond({'outcome':'error','diagnostic':error.diagnostic()})
        except move_intent_export.IntentExportError as error:
            code=str(error)
            respond({'outcome':'error','code':code if _ERROR.fullmatch(code) else 'export_failed'})
        except (schema_v2.SchemaError,ValueError,TypeError,UnicodeError,RecursionError):
            session._cancel();respond({'outcome':'error','code':'invalid_request'})


if __name__=='__main__':raise SystemExit(main())
