#!/usr/bin/env python3
"""Стендовая JSON-сессия нового контейнера: не доверенная доставка и не готовый установщик."""
import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(HERE), str(ROOT)]
import release_archive_cli_study as reader
import release_archive_study as archive
import release_ed25519_study as openssl
import release_policy_study as policy
import release_install_study as install

MAX_LINE = 2_097_152


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', required=True, type=Path)
    parser.add_argument('--statement', required=True, type=Path)
    parser.add_argument('--policy', required=True, type=Path)
    parser.add_argument('--policy-pin', required=True)
    parser.add_argument('--signature-hex', required=True)
    parser.add_argument('--openssl', required=True, type=Path)
    parser.add_argument('--openssl-pin', required=True)
    parser.add_argument('--destination', required=True, type=Path)
    parser.add_argument('--profile-root', required=True)
    args = parser.parse_args()
    if not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode):
        print(json.dumps({'outcome':'violation','reason':'isolated_python_required'}),file=sys.stderr)
        return 2
    try:
        if reader.SIGNATURE.fullmatch(args.signature_hex) is None: raise reader.InputError('signature_invalid')
        wire = reader.read_regular(args.policy, reader.MAX_POLICY)
        trusted_policy = reader.parse_policy(wire, args.policy_pin)
        statement = reader.read_regular(args.statement, reader.MAX_STATEMENT)
        raw = reader.read_regular(args.archive, archive.MAX_ARCHIVE)
        def verify(public, message, signature):
            return openssl.verify(public, message, signature, executable=args.openssl, executable_pin=args.openssl_pin)
        session = install.InstallSession(args.destination, profile_root=args.profile_root, archive_bytes=raw,
                    statement=statement, signature=bytes.fromhex(args.signature_hex), policy=trusted_policy,
                    verify_signature=verify)
    except (reader.InputError, ValueError, TypeError) as error:
        print(json.dumps({'outcome':'violation','reason':str(error)},sort_keys=True),file=sys.stderr)
        return 1
    def respond(value): print(json.dumps(value,ensure_ascii=False,sort_keys=True,allow_nan=False),flush=True)
    while True:
        line = sys.stdin.buffer.readline(MAX_LINE+1)
        if not line: return 0
        if len(line)>MAX_LINE:
            session.cancel(); respond({'outcome':'error','code':'input_too_large'}); return 1
        try:
            request = policy._parse(line)
            if request == {'type':'plan'}:
                result = session.plan()
                # Эти сведения показаны, но не служат удостоверением источника.
                result = {'outcome':'planned','install_plan':result, 'ticket':result['ticket'],
                          'policy_sha256':args.policy_pin,'provider_path':str(args.openssl),
                          'provider_sha256':args.openssl_pin,'input_observation':'captured_once_at_start',
                          'policy_origin':'assumed_not_verified','installation':'study_only'}
                probe={'type':'apply','plan':result,'confirmed_ticket':result['ticket']}
                if len((json.dumps(probe,ensure_ascii=False)+'\n').encode('utf-8'))>MAX_LINE:
                    session.cancel(); raise install.InstallError('plan_too_large_to_apply')
            elif (type(request) is dict and set(request)=={'type','stage_name'} and
                  request['type']=='inspect' and type(request['stage_name']) is str):
                result = session.inspect(stage_name=request['stage_name'])
                result.update(policy_sha256=args.policy_pin, provider_sha256=args.openssl_pin,
                              input_observation='captured_once_at_start')
            elif request == {'type':'cancel'}:
                session.cancel(); result = {'outcome':'cancelled'}
            elif (type(request) is dict and set(request)=={'type','plan','confirmed_ticket'} and
                  request['type']=='apply' and type(request['plan']) is dict and
                  type(request['confirmed_ticket']) is str):
                # Метаданные конверта фиксируются и сверяются целиком, а не игнорируются.
                envelope=request['plan']
                if (set(envelope) != {'outcome','install_plan','ticket','policy_sha256','provider_path',
                                      'provider_sha256','input_observation','policy_origin','installation'} or
                    envelope.get('outcome')!='planned' or envelope.get('policy_sha256')!=args.policy_pin or
                    envelope.get('provider_path')!=str(args.openssl) or envelope.get('provider_sha256')!=args.openssl_pin or
                    envelope.get('input_observation')!='captured_once_at_start' or
                    envelope.get('policy_origin')!='assumed_not_verified' or envelope.get('installation')!='study_only' or
                    type(envelope.get('install_plan')) is not dict or
                    envelope.get('ticket')!=envelope['install_plan'].get('ticket')):
                    session.cancel(); raise install.InstallError('plan_mismatch')
                result=session.apply(envelope['install_plan'],confirmed_ticket=request['confirmed_ticket'])
            else:
                session.cancel(); raise ValueError('request')
        except install.InstallError as error:
            result={'outcome':'error','code':str(error)}
        except (ValueError,TypeError,UnicodeError,RecursionError):
            session.cancel(); result={'outcome':'error','code':'invalid_request'}
        respond(result)


if __name__=='__main__': raise SystemExit(main())
