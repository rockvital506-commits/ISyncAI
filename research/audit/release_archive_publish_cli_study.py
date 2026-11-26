#!/usr/bin/env python3
"""Опытная публикация подписанного архива: JSON-lines, не установка и не доверенный выпуск."""
import argparse
import json
from pathlib import Path
import secrets
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path[:0]=[str(HERE),str(ROOT)]
import release_archive_cli_study as reader
import release_archive_study as archive
import release_ed25519_study as openssl
import release_policy_study as policy
import release_archive_publish_study as publish
from kit import init_workspace as init

MAX_LINE=2_097_152


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',required=True,type=Path);parser.add_argument('--statement',required=True,type=Path)
    parser.add_argument('--policy',required=True,type=Path);parser.add_argument('--policy-pin',required=True)
    parser.add_argument('--signature-hex',required=True);parser.add_argument('--openssl',required=True,type=Path)
    parser.add_argument('--openssl-pin',required=True);parser.add_argument('--destination',required=True,type=Path)
    args=parser.parse_args()
    if not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode):
        print(json.dumps({'outcome':'violation','reason':'isolated_python_required'}),file=sys.stderr);return 2
    try:
        if reader.SIGNATURE.fullmatch(args.signature_hex) is None:raise reader.InputError('signature_invalid')
        wire=reader.read_regular(args.policy,reader.MAX_POLICY);trusted_policy=reader.parse_policy(wire,args.policy_pin)
        statement=reader.read_regular(args.statement,reader.MAX_STATEMENT)
        raw=reader.read_regular(args.archive,archive.MAX_ARCHIVE)
        def verify(public,message,signature):
            return openssl.verify(public,message,signature,executable=args.openssl,executable_pin=args.openssl_pin)
        session=publish.PublishSession(args.destination,archive_bytes=raw,statement=statement,
                    signature=bytes.fromhex(args.signature_hex),policy=trusted_policy,verify_signature=verify)
    except (reader.InputError,ValueError,TypeError) as error:
        print(json.dumps({'outcome':'violation','reason':str(error)},sort_keys=True),file=sys.stderr);return 1
    pending=None
    def respond(obj):print(json.dumps(obj,ensure_ascii=False,sort_keys=True,allow_nan=False),flush=True)
    while True:
        line=sys.stdin.buffer.readline(MAX_LINE+1)
        if not line:return 0
        if len(line)>MAX_LINE:
            session.cancel();respond({'outcome':'error','code':'input_too_large'});return 1
        try:
            request=policy._parse(line)
            if request=={'type':'plan'}:
                pending=None
                inner=session.plan()
                result={'outcome':'planned','publication_plan':inner,'ticket':inner['ticket'],
                        'policy_sha256':args.policy_pin,'provider_path':str(args.openssl),
                        'provider_sha256':args.openssl_pin,'input_observation':'captured_once_at_start',
                        'policy_origin':'assumed_not_verified','installation':'not_performed'}
                pending=(init._canonical(result),inner,result['ticket'])
            elif (type(request) is dict and set(request)=={'type','stage_name'} and request['type']=='inspect'
                  and type(request['stage_name']) is str):
                pending=None
                result=session.inspect(stage_name=request['stage_name'])
                result.update(policy_sha256=args.policy_pin,provider_sha256=args.openssl_pin,
                              input_observation='captured_once_at_start')
            elif request=={'type':'cancel'}:
                pending=None;session.cancel();result={'outcome':'cancelled'}
            elif (type(request) is dict and set(request)=={'type','plan','confirmed_ticket'} and request['type']=='apply'
                  and type(request['plan']) is dict and type(request['confirmed_ticket']) is str):
                if pending is None:raise publish.PublishError('ticket_unknown')
                saved,inner,ticket=pending
                if not secrets.compare_digest(ticket,request['confirmed_ticket']):raise publish.PublishError('confirmation_required')
                pending=None
                if init._canonical(request['plan'])!=saved:
                    session.cancel();raise publish.PublishError('plan_mismatch')
                result=session.apply(inner,confirmed_ticket=ticket)
            else:
                pending=None;session.cancel();raise ValueError('request')
        except publish.PublishError as error:
            result={'outcome':'error','code':str(error)}
        except (ValueError,TypeError,UnicodeError,RecursionError) as error:
            pending=None;session.cancel();result={'outcome':'error','code':'invalid_request'}
        respond(result)


if __name__=='__main__':raise SystemExit(main())
