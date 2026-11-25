#!/usr/bin/env python3
"""Синтетическая проекция в памяти, не миграция настоящего проекта."""
import base64
import copy
import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'research/audit')]
from test_compare_old import fixture, raw
from kit.legacy_capsule import prepare
from kit.legacy_projection import ProjectionError, analyze, project
from kit.base import schema_v2, registry_journal


class ProjectionTests(unittest.TestCase):
    def setUp(self):
        self.state, self.checks, self.base, self.target, self.source, self.candidate = fixture()

    def capsule(self):
        self.source['state'] = raw(self.state)
        self.source['checks'] = raw(self.checks)
        self.source['base_rules'] = raw(self.base)
        return prepare(self.source)

    def run_project(self, roots=None):
        item = self.capsule()
        return project(item['archive'], pin=item['archive_sha256'], roots=['.agent-contract'] if roots is None else roots)

    def test_exact_core_projection_and_comparison(self):
        report, registry = self.run_project()
        self.assertEqual(report['outcome'], 'proposed')
        self.assertFalse(report['migration_ready'])
        self.assertEqual(report['source_health'], 'not_checked')
        self.assertEqual(report['comparison']['outcome'], 'core_and_archives_equal')
        self.assertEqual(report['registry_sha256'], hashlib.sha256(registry).hexdigest())
        parsed = schema_v2.validate_json(registry, expected_area='L2')
        self.assertEqual(parsed, self.target)
        _, journal = registry_journal.unpack_registry(parsed, area='L2')
        self.assertEqual(journal, {'base_revision': 2, 'decisions': []})
        self.assertIn('legacy_decisions', report['not_in_registry'])
        self.assertIn('legacy_record_metadata', report['not_in_registry'])
        self.assertNotIn(b'Synthetic Owner', registry)

    def test_new_v2_history_starts_at_old_revision_not_imported(self):
        report, data = self.run_project()
        registry, journal = registry_journal.unpack_registry(json.loads(data), area='L2')
        previous = copy.deepcopy(registry)
        new = copy.deepcopy(registry['entries'][1]); new['id'] = 'P-10'
        registry['entries'].append(new); registry['revision'] += 1
        envelope = registry_journal.with_change(registry, previous, journal,
                                                 operation='create', before=None, after=new)
        verified, new_journal = registry_journal.unpack_registry(envelope, area='L2')
        self.assertEqual(verified['revision'], 3)
        self.assertEqual(new_journal['base_revision'], 2)
        self.assertEqual(len(new_journal['decisions']), 1)
        self.assertEqual(new_journal['decisions'][0]['entry_id'], 'P-10')
        self.assertIn('legacy_decisions', report['not_in_registry'])

    def test_determinism_no_io_or_input_mutation(self):
        item = self.capsule(); before = copy.deepcopy(item); roots = ['project/contracts']; original = roots[:]
        with patch('builtins.open', side_effect=AssertionError('unexpected I/O')):
            a = project(item['archive'], pin=item['archive_sha256'], roots=roots)
            b = project(item['archive'], pin=item['archive_sha256'], roots=roots)
            summary = analyze(item['archive'], pin=item['archive_sha256'], roots=roots)
        self.assertEqual(a, b); self.assertEqual(a[0], summary)
        self.assertEqual(item, before); self.assertEqual(roots, original)
        text = json.dumps(summary, ensure_ascii=False)
        self.assertNotIn('Синтетический текст правила', text)
        self.assertNotIn('Synthetic Owner', text)

    def test_roots_change_proposal_digest_without_changing_entry_data(self):
        first, a = self.run_project(['one'])
        second, b = self.run_project(['two'])
        self.assertNotEqual(first['registry_sha256'], second['registry_sha256'])
        self.assertEqual(json.loads(a)['entries'], json.loads(b)['entries'])
        self.assertEqual(json.loads(a)['roots'], ['one'])
        self.assertEqual(json.loads(b)['roots'], ['two'])

    def test_cross_layer_parent_blocks_without_rebinding(self):
        self.state['entries'][1]['contract'] = 'B-1'
        report, data = self.run_project()
        self.assertIsNone(data); self.assertEqual(report['outcome'], 'blocked')
        self.assertEqual(report['blockers'], [{'code':'cross_layer_parent','id':'P-2','parent':'B-1'}])
        self.assertIsNone(report['comparison']); self.assertIsNone(report['registry_sha256'])

    def test_tombstone_and_retirement_block(self):
        self.state['retired'] = True; self.state['tombstones'] = [{'id': 'P-9'}]
        report, data = self.run_project()
        self.assertIsNone(data)
        self.assertEqual([row['code'] for row in report['blockers']], ['project_retired','legacy_tombstones'])

    def test_v2_incompatible_scope_and_parent_scope_block(self):
        for parent, child, code in [('.', '../escape', 'path'), ('docs', 'src', 'scope_outside')]:
            with self.subTest(parent=parent, child=child):
                self.state['entries'][0]['scope'] = parent; self.state['entries'][1]['scope'] = child
                report, data = self.run_project()
                self.assertIsNone(data); self.assertEqual(report['outcome'], 'blocked')
                self.assertEqual(report['blockers'][0]['schema_code'], code)
                self.assertNotIn('escape', json.dumps(report))

    def test_invalid_roots(self):
        for roots in ([], ['../bad'], ['a','a/b'], ['NUL'], None, 'a', [True]):
            with self.subTest(roots=roots):
                item = self.capsule()
                with self.assertRaises(ProjectionError) as error:
                    project(item['archive'], pin=item['archive_sha256'], roots=roots)
                self.assertEqual(error.exception.code, 'invalid_roots')

    def test_source_version_corruption_and_history_fail_closed(self):
        for mutation, code in [('version','unknown_version'), ('history','legacy_data_invalid'),
                               ('counter','source_invalid'), ('base_schema','unknown_version')]:
            with self.subTest(mutation=mutation):
                self.setUp()
                if mutation == 'version': self.state['base']['version'] = '0.1.35'
                if mutation == 'history': self.state['decisions'][0] = 'bad'
                if mutation == 'counter': self.state['next_id'] = 1
                if mutation == 'base_schema': self.base['schema_version'] = 3
                with self.assertRaises(ProjectionError) as error: self.run_project()
                self.assertEqual(error.exception.code, code)

    def test_pin_and_capsule_corruption_rejected(self):
        item = self.capsule()
        for archive, pin, code in [(item['archive'],'0'*64,'capsule_digest_mismatch'),
                                  (item['archive']+b' ',item['archive_sha256'],'capsule_digest_mismatch'),
                                  (item['archive'],None,'pin_required')]:
            with self.subTest(code=code), self.assertRaises(ProjectionError) as error:
                project(archive,pin=pin,roots=['x'])
            self.assertEqual(error.exception.code,code)

    def test_all_project_kinds_states_and_optional_pairs_preserved(self):
        self.state['entries'][1].update(kind='preference', state='suspended', key=None, value=None)
        report, data = self.run_project()
        entry = json.loads(data)['entries'][1]
        self.assertEqual((entry['kind'],entry['state']),('preference','suspended'))
        self.assertNotIn('key',entry); self.assertNotIn('value',entry)
        self.assertEqual(report['comparison']['outcome'],'core_and_archives_equal')

    def test_cli_analyze_project_blocked_and_errors(self):
        item = self.capsule()
        def call(req):
            return subprocess.run([sys.executable,'-I','-S','-B',str(ROOT/'kit/legacy_projection.py')],
                                  input=json.dumps(req).encode(),capture_output=True,timeout=30)
        req = {'format':1,'action':'analyze','archive_base64':base64.b64encode(item['archive']).decode(),
               'pin':item['archive_sha256'],'roots':['.agent-contract']}
        p = call(req); self.assertEqual(p.returncode,0,p.stderr)
        self.assertNotIn(b'registry_base64',p.stdout)
        self.assertNotIn('Синтетический текст правила'.encode(),p.stdout)
        req['action']='project'; p=call(req); self.assertEqual(p.returncode,0,p.stderr)
        obj=json.loads(p.stdout); self.assertEqual(json.loads(base64.b64decode(obj['registry_base64'])),self.target)
        req['pin']='0'*64; p=call(req); self.assertEqual(p.returncode,1)
        self.assertEqual(json.loads(p.stdout)['code'],'capsule_digest_mismatch')
        self.state['retired']=True; item=self.capsule(); req['pin']=item['archive_sha256']
        req['archive_base64']=base64.b64encode(item['archive']).decode()
        p=call(req); self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(json.loads(p.stdout)['report']['outcome'],'blocked')
        self.assertIsNone(json.loads(p.stdout)['registry_base64'])

    def test_cli_invalid_request_has_no_input_echo(self):
        p=subprocess.run([sys.executable,'-I','-S','-B',str(ROOT/'kit/legacy_projection.py')],
                         input=b'{"SECRET":"SECRET"}',capture_output=True,timeout=30)
        self.assertEqual(p.returncode,1); self.assertEqual(json.loads(p.stdout)['code'],'request_invalid')
        self.assertNotIn(b'SECRET',p.stdout+p.stderr)


if __name__ == '__main__': unittest.main()
