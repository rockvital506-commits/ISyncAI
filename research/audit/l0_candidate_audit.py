#!/usr/bin/env python3
"""Локальная механическая сверка системного L0-кандидата; не независимое ревью."""
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'research/audit')]
import l0_proposal_audit as proposal_audit
from kit.base import registry_policy, schema_v2
from kit.verify_candidate import CANDIDATE_VERSION


class CandidateError(ValueError):pass


def check(proposal, roadmap, manifest, system):
    try:
        # Исторический проверяющий проверяет draft, цитаты, роадмап и привязку манифеста.
        proposal_audit.check(proposal,roadmap,manifest)
        manifest_doc=schema_v2.parse_json(manifest)
        if manifest_doc['version'] != CANDIDATE_VERSION:
            raise CandidateError('version')
        document=schema_v2.validate_json(system,expected_area='L0')
        if hashlib.sha256(system).hexdigest() != manifest_doc['files']['kit/SYSTEM-L0.json']:
            raise CandidateError('manifest_binding')
        expected=copy.deepcopy(proposal['registry'])
        for entry in expected['entries']:
            if entry['state'] != 'draft':raise CandidateError('draft')
            entry['state']='active'
        if document != expected or document['release_version'] != CANDIDATE_VERSION:
            raise CandidateError('projection')
        if len(document['entries']) != 10 or len(registry_policy.active_entries(document)) != 10:
            raise CandidateError('active')
    except CandidateError:
        raise
    except (proposal_audit.AuditError, schema_v2.SchemaError, ValueError, TypeError, KeyError, RecursionError) as error:
        raise CandidateError('invalid') from error
    return {'outcome':'local_candidate_shape_pass','entries':10,'active_entries':10,
            'system_sha256':hashlib.sha256(system).hexdigest(),'semantic_review':'not_run',
            'independent_origin':'not_verified','independent_review':'not_run'}


def main():
    try:
        result=check(schema_v2.parse_json((ROOT/'research/kilo/l0-proposal/DRAFT.json').read_bytes()),
                     (ROOT/'research/kilo/ROADMAP.md').read_bytes(),
                     (ROOT/'kit/KIT-VERSION.json').read_bytes(),(ROOT/'kit/SYSTEM-L0.json').read_bytes())
    except (CandidateError,OSError,ValueError,TypeError,RecursionError):
        print(json.dumps({'outcome':'fail','reason':'candidate_invalid'}),file=sys.stderr);return 1
    print(json.dumps(result,sort_keys=True));return 0


if __name__=='__main__':raise SystemExit(main())
