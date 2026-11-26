#!/usr/bin/env python3
"""Локальная/CI проверка кандидата: checkout и Python предполагаются доверенными."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
PIN='8401cefcf5163c9f576ca0a34a5176ace945a6920b8f5967692b2df792dd1292'
ROADMAP_PIN='7712160f17edda9db74dbf9045f0662c0d7cee90c788e389a0ab68bb1b286e94'
RAN=re.compile(r'Ran (\d+) tests? in ')


class GateError(ValueError):pass


def _run(command,*,timeout=120):
    try:
        result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=timeout)
    except (OSError,subprocess.TimeoutExpired) as error:raise GateError('command_unavailable:'+command[-1]) from error
    if result.returncode:
        raise GateError('command_failed:'+command[-1]+'\n'+result.stdout[-5000:]+result.stderr[-5000:])
    return result.stdout,result.stderr


def _test_status(stdout,stderr):
    combined=stdout+'\n'+stderr
    matches=RAN.findall(combined)
    if len(matches)!=1 or int(matches[0])<1 or 'skipped=' in combined or 'OK (skipped' in combined:
        raise GateError('tests_missing_or_skipped')
    return int(matches[0])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tree',required=True,help='полный Git tree OID или commit OID')
    args=parser.parse_args()
    try:
        import hashlib
        if hashlib.sha256((ROOT/'research/kilo/ROADMAP.md').read_bytes()).hexdigest()!=ROADMAP_PIN:
            raise GateError('roadmap_pin_mismatch')
        python=[sys.executable,'-I','-S','-B']
        _run(python+['kit/verify_candidate.py','--root',str(ROOT),'--pin',PIN])
        _run(python+['kit/guard_tree.py','--repo',str(ROOT),'--tree',args.tree,'--manifest-pin',PIN])
        _run(python+['research/audit/entrypoint_inventory.py','--check','research/kilo/ENTRYPOINT-INVENTORY.json'])
        inventory,_=_run(python+['research/audit/name_inventory.py'])
        if inventory.encode('utf-8')!=(ROOT/'research/kilo/NAME-CHANGE-INVENTORY.json').read_bytes():
            raise GateError('name_inventory_mismatch')
        _run(python+['research/audit/l0_proposal_audit.py'])
        _run(python+['research/audit/l0_candidate_audit.py'])
        _run(python+['research/audit/core_audit.py','--json'])
        files=sorted((ROOT/'research/audit').glob('test_*.py'))
        if not files:raise GateError('no_test_suites')
        cases=0
        for path in files:
            out,err=_run(python+[str(path),'-q'])
            try:cases+=_test_status(out,err)
            except GateError as error:raise GateError(str(error)+':'+path.name) from error
            print('PASS '+path.name,flush=True)
        print(json.dumps({'outcome':'local_candidate_checks_pass','test_suites':len(files),'test_cases':cases,
                          'tree_oid':args.tree,'manifest_pin':PIN,'roadmap_sha256':ROADMAP_PIN,
                          'checker_origin':'not_verified','real_environment':'not_run',
                          'independent_review':'not_run'},sort_keys=True))
        return 0
    except (GateError,OSError,UnicodeError,ValueError) as error:
        print(json.dumps({'outcome':'gate_failed','reason':str(error)},ensure_ascii=False),file=sys.stderr)
        return 1


if __name__=='__main__':raise SystemExit(main())
