#!/usr/bin/env python3
"""Сквозная синтетическая репетиция; не подписанный выпуск и не приёмка."""
import hashlib
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'research/audit')]
import test_source_release_trust as signing
import test_atomic_init as atomic_tests
import core_audit as audit


@unittest.skipUnless(signing.SUPPORTED and atomic_tests.SUPPORTED, 'OpenSSL/Linux unavailable; not_run')
class DeliveryWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.fixture = signing.SourceTrustTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.ctx.root
        self.destination = self.root/'new-workspace'
        self.l0 = (ROOT/'kit/SYSTEM-L0.json').read_bytes()
        self.system_pin = hashlib.sha256(self.l0).hexdigest()
        self.processes = []
        self.addCleanup(self.close_processes)

    def close_processes(self):
        for p in self.processes:
            if p.stdin and not p.stdin.closed:
                p.stdin.close()
            try:
                p.wait(timeout=15)
            except subprocess.TimeoutExpired:
                p.kill(); p.wait(timeout=15)
            p.stdout.close(); p.stderr.close()

    def start(self, command):
        p = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, encoding='utf-8', bufsize=1)
        self.processes.append(p)
        return p

    def send(self, proc, obj):
        proc.stdin.write(json.dumps(obj, ensure_ascii=False)+'\n'); proc.stdin.flush()
        ready, _, _ = select.select([proc.stdout], [], [], 15)
        self.assertTrue(ready, 'истекло время ожидания ответа процесса')
        line = proc.stdout.readline()
        self.assertTrue(line, 'процесс не ответил')
        return json.loads(line)

    def init(self):
        proc = self.start([sys.executable, '-I', '-S', '-B', str(ROOT/'kit/init_workspace_cli.py')])
        req = {'type':'plan_atomic', 'destination':str(self.destination), 'profile_root':'profiles/pilot',
               'l0_utf8':self.l0.decode(), 'system_pin':self.system_pin}
        plan = self.send(proc, req)
        self.assertEqual(plan['outcome'], 'planned', plan)
        self.assertFalse(self.destination.exists())
        denied = self.send(proc, {'type':'apply','plan':plan,'confirmed_ticket':'wrong'})
        self.assertEqual(denied['code'], 'confirmation_required')
        self.assertFalse(self.destination.exists())
        result = self.send(proc, {'type':'apply','plan':plan,'confirmed_ticket':plan['ticket']})
        self.assertEqual(result['outcome'], 'published_unverified_origin', result)
        return proc

    def snapshot_args(self, pin):
        return [sys.executable, '-I', '-S', '-B', str(ROOT/'kit/snapshot_session.py'),
                '--candidate-root', str(self.fixture.ctx.candidate), '--workspace', str(self.destination),
                '--profile-root', 'profiles/pilot', '--profile-id', 'Pilot',
                '--manifest-pin', pin, '--system-pin', self.system_pin]

    def test_signed_candidate_new_workspace_and_confirmed_operation(self):
        signed = self.fixture.verify()
        self.init()
        proc = self.start(self.snapshot_args(signed['manifest_sha256']))
        bootstrap = self.send(proc, {'type':'bootstrap'})
        self.assertEqual(bootstrap['outcome'], 'bootstrap', bootstrap)
        for mode, expected in (('project','SYS-PROJECT-MODE'), ('kit','SYS-KIT-MODE')):
            context = self.send(proc, {'type':'context','mode':mode,'scope':'docs/a',
                                       'choices':{'include':[],'exclude':[]}})
            self.assertEqual(context['outcome'], 'review_required', context)
            system_ids = {row['entry']['id'] for row in context['entries'] if row['area']=='L0'}
            self.assertIn(expected, system_ids)
        before = audit.tree_digest(self.destination)
        request = self.fixture.ctx.request()
        plan = self.send(proc, request)
        self.assertEqual(plan['outcome'], 'planned', plan)
        self.assertEqual(before, audit.tree_digest(self.destination))
        denied = self.send(proc, {'type':'apply','plan':plan,'confirmed_ticket':'wrong'})
        self.assertEqual(denied['diagnostic']['code'], 'confirmation_required')
        self.assertEqual(before, audit.tree_digest(self.destination))
        result = self.send(proc, {'type':'apply','plan':plan,'confirmed_ticket':plan['ticket']})
        self.assertEqual(result['outcome'], 'applied', result)
        self.assertNotEqual(before, audit.tree_digest(self.destination))
        replay = self.send(proc, {'type':'apply','plan':plan,'confirmed_ticket':plan['ticket']})
        self.assertEqual(replay['diagnostic']['code'], 'ticket_unknown')

        move = self.start([sys.executable, '-I', '-S', '-B', str(ROOT/'kit/snapshot_move_session.py'),
                           '--candidate-root', str(self.fixture.ctx.candidate), '--workspace', str(self.destination),
                           '--profile-root', 'profiles/pilot', '--manifest-pin', signed['manifest_sha256'],
                           '--system-pin', self.system_pin])
        candidate = audit.entry('P-9', 'contract', 'project_owner', None, 'docs', state='draft')
        built = self.send(move, {'type':'build','source':'L1','target':'L2','entry_id':'C-9',
                                 'candidate':candidate,'portability_context':None})
        self.assertEqual(built['outcome'], 'intent_draft_only', built)
        configured = self.send(move, {'type':'configure','intent_utf8':built['intent_utf8'],
                                      'intent_pin':built['intent_sha256']})
        self.assertEqual(configured['outcome'], 'configured', configured)
        for action, expected in (('reserve','reserved_not_moved'),
                                 ('execute','registries_updated_marker_retained'),
                                 ('finalize','marker_removed_after_both')):
            planned = self.send(move, {'type':'plan','action':action})
            self.assertEqual(planned['outcome'], 'planned', planned)
            p = planned['plan']
            rejected = self.send(move, {'type':'apply','plan':p,'confirmed_ticket':'wrong'})
            self.assertEqual(rejected['diagnostic']['code'], 'confirmation_required', rejected)
            applied = self.send(move, {'type':'apply','plan':p,'confirmed_ticket':p['ticket']})
            self.assertEqual(applied['outcome'], expected, applied)
        profile = json.loads((self.destination/'profiles/pilot/registry.json').read_bytes())
        project = json.loads((self.destination/'.domain-agent-kit/project/registry.json').read_bytes())
        self.assertNotIn('C-9', {entry['id'] for entry in profile['registry']['entries']})
        self.assertIn('P-9', {entry['id'] for entry in project['registry']['entries']})
        self.assertFalse((self.destination/'.domain-agent-kit/.move-pending').exists())

    def test_signed_pin_does_not_accept_changed_candidate_or_l0(self):
        signed = self.fixture.verify()
        self.init()
        before = audit.tree_digest(self.destination)
        path = self.fixture.ctx.candidate/'kit/base/operation_plan.py'
        original = path.read_bytes(); path.write_bytes(original+b'\n# tamper\n')
        p = subprocess.run(self.snapshot_args(signed['manifest_sha256']), input='', text=True,
                           capture_output=True, timeout=30)
        self.assertEqual(p.returncode, 1)
        self.assertEqual(json.loads(p.stderr)['reason'], 'candidate_unverified')
        self.assertEqual(before, audit.tree_digest(self.destination))
        path.write_bytes(original)
        l0 = self.destination/'kit/base/registry.json'
        l0.write_bytes(l0.read_bytes()+b' ')
        changed = audit.tree_digest(self.destination)
        p = subprocess.run(self.snapshot_args(signed['manifest_sha256']), input='', text=True,
                           capture_output=True, timeout=30)
        self.assertEqual(p.returncode, 1)
        self.assertEqual(json.loads(p.stderr)['reason'], 'runtime_unverified')
        self.assertEqual(changed, audit.tree_digest(self.destination))

if __name__ == '__main__':
    unittest.main()
