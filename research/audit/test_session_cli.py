#!/usr/bin/env python3
"""Тесты JSON-lines процесса на синтетических временных реестрах."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'research/audit')]
import core_audit as a


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='kit-session-cli-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        a.make_workspace(self.root)
        self.procs = []
        self.addCleanup(self.cleanup_procs)

    def cleanup_procs(self):
        for process in self.procs:
            if process.stdin and not process.stdin.closed:
                process.stdin.close()
            process.wait(timeout=10)
            process.stdout.close()
            process.stderr.close()

    def process(self):
        p = subprocess.Popen([sys.executable, '-B', str(ROOT/'kit/session_cli.py'),
                              '--workspace', str(self.root), '--profile-root', 'profiles/pilot',
                              '--profile-id', 'Pilot'], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, encoding='utf-8', bufsize=1)
        self.procs.append(p)
        return p

    def send(self, p, obj):
        p.stdin.write(json.dumps(obj, ensure_ascii=False) + '\n'); p.stdin.flush()
        line = p.stdout.readline()
        self.assertTrue(line, 'процесс не вернул JSON')
        return json.loads(line)

    def plan(self, p):
        request = a.card(ident='Q-1')['request']
        out = self.send(p, {'type':'plan','request':request})
        self.assertEqual(out['outcome'], 'planned')
        return out

    def apply_msg(self, plan, token=None):
        return {'type':'apply','plan':plan,'confirmed_ticket':plan['ticket'] if token is None else token}

    def test_pending_move_blocks_preplanned_apply_and_reads(self):
        p=self.process();plan=self.plan(p)
        marker=self.root/'.domain-agent-kit/.move-pending';marker.write_bytes(b'synthetic pending')
        before=a.tree_digest(self.root)
        self.assertEqual(self.send(p,self.apply_msg(plan))['diagnostic']['code'],'move_pending')
        self.assertEqual(self.send(p,{'type':'applicable','scope':'docs/a'})['diagnostic']['code'],'move_pending')
        self.assertEqual(before,a.tree_digest(self.root));self.assertEqual(marker.read_bytes(),b'synthetic pending')
        marker.unlink()  # Только тестовая фикстура, не восстановление.
        self.assertEqual(self.send(p,self.apply_msg(plan))['diagnostic']['code'],'ticket_unknown')

    def test_context_export_plan_confirmation_and_cross_cancellation(self):
        (self.root/'kit/base/registry.json').write_bytes((ROOT/'kit/SYSTEM-L0.json').read_bytes())
        p=self.process();choices={'include':[{'area':'L1','id':'C-1'},{'area':'L2','id':'P-1'}],'exclude':[]}
        with tempfile.TemporaryDirectory(prefix='context-cli-out-') as tmp:
            dest=Path(tmp)/'context.json';request={'type':'context_export_plan','mode':'project','scope':'docs/a','choices':choices,'destination':str(dest)}
            plan=self.send(p,request);self.assertEqual(plan['outcome'],'planned');self.assertFalse(dest.exists())
            attempt={'type':'context_export_apply','plan':plan,'confirmed_ticket':'wrong'}
            self.assertEqual(self.send(p,attempt)['diagnostic']['code'],'confirmation_required');self.assertFalse(dest.exists())
            attempt['confirmed_ticket']=plan['ticket'];result=self.send(p,attempt);self.assertEqual(result['outcome'],'context_file_created')
            self.assertEqual(dest.read_text(),plan['content_utf8']);self.assertEqual(result['agent_application'],'not_checked')
            request['destination']=str(Path(tmp)/'other.json');plan=self.send(p,request);self.assertEqual(plan['outcome'],'planned')
            self.plan(p);attempt={'type':'context_export_apply','plan':plan,'confirmed_ticket':plan['ticket']}
            self.assertEqual(self.send(p,attempt)['diagnostic']['code'],'ticket_unknown');self.assertFalse(Path(request['destination']).exists())
    def test_context_modes_read_and_cancel_pending(self):
        l0=self.root/'kit/base/registry.json';l0.write_bytes((ROOT/'kit/SYSTEM-L0.json').read_bytes())
        p=self.process();before=a.tree_digest(self.root);plan=self.plan(p)
        choices={'include':[{'area':'L1','id':'C-1'},{'area':'L2','id':'P-1'}], 'exclude':[]}
        result=self.send(p,{'type':'context','mode':'project','scope':'docs/a','choices':choices})
        self.assertEqual(result['outcome'],'review_required')
        ids={row['entry']['id'] for row in result['entries'] if row['area']=='L0'}
        self.assertIn('SYS-PROJECT-MODE',ids);self.assertNotIn('SYS-KIT-MODE',ids)
        self.assertEqual(self.send(p,self.apply_msg(plan))['diagnostic']['code'],'ticket_unknown')
        self.assertEqual(before,a.tree_digest(self.root))

    def test_applicable_read_revokes_pending_and_does_not_write(self):
        p=self.process();before=a.tree_digest(self.root);plan=self.plan(p)
        result=self.send(p,{'type':'applicable','scope':'docs/readme.md'})
        self.assertEqual(result['outcome'],'applicable');self.assertEqual(result['coverage'],'selected_scope_only')
        self.assertEqual({row['area'] for row in result['entries']},{'L0','L1','L2'})
        self.assertEqual(self.send(p,self.apply_msg(plan))['diagnostic']['code'],'ticket_unknown')
        self.assertEqual(before,a.tree_digest(self.root))
        plan=self.plan(p)
        self.assertEqual(self.send(p,{'type':'applicable','scope':'../bad'})['diagnostic']['code'],'scope_invalid')
        self.assertEqual(self.send(p,self.apply_msg(plan))['diagnostic']['code'],'ticket_unknown')
        self.assertEqual(before,a.tree_digest(self.root))

    def test_separate_confirmation_and_replay(self):
        p = self.process(); before = a.tree_digest(self.root); plan = self.plan(p)
        self.assertEqual(before, a.tree_digest(self.root))
        denied = self.send(p, self.apply_msg(plan, 'bad'))
        self.assertEqual(denied['diagnostic']['code'], 'confirmation_required')
        self.assertEqual(before, a.tree_digest(self.root))
        ok = self.send(p, self.apply_msg(plan))
        self.assertEqual(ok['outcome'], 'applied')
        after = a.tree_digest(self.root)
        self.assertNotEqual(before, after)
        denied = self.send(p, self.apply_msg(plan))
        self.assertEqual(denied['diagnostic']['code'], 'ticket_unknown')
        self.assertEqual(after, a.tree_digest(self.root))

    def test_foreign_session_denied(self):
        p, q = self.process(), self.process(); before = a.tree_digest(self.root); plan = self.plan(p)
        denied = self.send(q, self.apply_msg(plan))
        self.assertEqual(denied['diagnostic']['code'], 'ticket_unknown')
        self.assertEqual(before, a.tree_digest(self.root))

    def test_cancel_and_invalid_request_revoke(self):
        for invalid in ({'type':'cancel'}, {'type':'apply','plan':{}}, {'type':'unknown'}):
            with self.subTest(invalid=invalid):
                p = self.process(); before = a.tree_digest(self.root); plan = self.plan(p)
                result = self.send(p, invalid)
                self.assertIn(result['outcome'], ('cancelled','error'))
                denied = self.send(p, self.apply_msg(plan))
                self.assertEqual(denied['diagnostic']['code'], 'ticket_unknown')
                self.assertEqual(before, a.tree_digest(self.root))

    def test_cancel_twice_is_idempotent_and_leaves_bytes_unchanged(self):
        p = self.process(); before = a.tree_digest(self.root); plan = self.plan(p)
        self.assertEqual(self.send(p, {'type':'cancel'}), {'outcome':'cancelled'})
        self.assertEqual(self.send(p, {'type':'cancel'}), {'outcome':'cancelled'})
        self.assertEqual(self.send(p, self.apply_msg(plan))['diagnostic']['code'], 'ticket_unknown')
        self.assertEqual(before, a.tree_digest(self.root))

    def test_edited_plan_denied(self):
        p = self.process(); before = a.tree_digest(self.root); plan = self.plan(p)
        forged = json.loads(json.dumps(plan)); forged['diff']['unified'] += 'подмена'
        denied = self.send(p, self.apply_msg(forged))
        self.assertEqual(denied['diagnostic']['code'], 'plan_mismatch')
        self.assertEqual(before, a.tree_digest(self.root))

    def test_new_plan_revokes_old(self):
        p = self.process(); before = a.tree_digest(self.root); old = self.plan(p)
        listed = self.send(p, {'type':'plan','request':'Покажи правила в профиле Pilot.'})
        self.assertEqual(listed['outcome'], 'listed')
        denied = self.send(p, self.apply_msg(old))
        self.assertEqual(denied['diagnostic']['code'], 'ticket_unknown')
        self.assertEqual(before, a.tree_digest(self.root))

    def test_duplicate_json_revokes_pending(self):
        p = self.process(); before = a.tree_digest(self.root); plan = self.plan(p)
        p.stdin.write('{"type":"cancel","type":"plan"}\n'); p.stdin.flush()
        self.assertEqual(json.loads(p.stdout.readline())['code'], 'invalid_request')
        self.assertEqual(self.send(p, self.apply_msg(plan))['diagnostic']['code'], 'ticket_unknown')
        self.assertEqual(before, a.tree_digest(self.root))

    def test_delete_requires_extra_confirmation(self):
        path = self.root/'profiles/pilot/registry.json'
        doc = json.loads(path.read_text(encoding='utf-8'))
        doc['entries'].append(a.entry('Q-1','rule','profile_owner','C-1','docs',state='revoked'))
        a.write(path, doc)
        p = self.process(); before = a.tree_digest(self.root)
        command = {'type':'plan','request':'Удали правило Q-1 в профиле Pilot.'}
        plan = self.send(p, command)
        self.assertEqual(plan['outcome'], 'planned')
        refused = self.send(p, self.apply_msg(plan))
        self.assertEqual(refused['diagnostic']['code'], 'delete_confirmation_required')
        self.assertEqual(before, a.tree_digest(self.root))
        plan = self.send(p, command)
        msg = self.apply_msg(plan); msg['allow_delete'] = True
        self.assertEqual(self.send(p, msg)['outcome'], 'applied')

    def test_oversize_input_terminates_without_writing(self):
        before = a.tree_digest(self.root)
        result = subprocess.run([sys.executable, '-B', str(ROOT/'kit/session_cli.py'),
                                 '--workspace', str(self.root), '--profile-root', 'profiles/pilot',
                                 '--profile-id', 'Pilot'], input=('x' * 1048577 + '\n'),
                                capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)['code'], 'input_too_large')
        self.assertEqual(before, a.tree_digest(self.root))

    def test_stale_input_denied(self):
        p = self.process(); plan = self.plan(p)
        f = self.root/'.domain-agent-kit/project/registry.json'; f.write_bytes(f.read_bytes()+b'\n')
        before = a.tree_digest(self.root)
        denied = self.send(p, self.apply_msg(plan))
        self.assertEqual(denied['diagnostic']['code'], 'stale_plan')
        self.assertEqual(before, a.tree_digest(self.root))


if __name__ == '__main__': unittest.main()
