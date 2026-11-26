#!/usr/bin/env python3
"""Два штатных процесса на синтетическом workspace; не проверка враждебной среды."""
import errno
import hashlib
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'research/audit')]
import core_audit as audit
from kit.base import registry_store as store, registry_journal
from kit.base.operation_card import compile_prompt
from kit.base.operation_plan import PlanSession
from kit.base.registry_policy import StoreError

SCRIPT = str(Path(__file__).resolve())
SUPPORTED = (os.name == 'posix' and store.fcntl is not None and hasattr(os, 'O_DIRECTORY')
             and hasattr(os, 'O_NOFOLLOW'))
UNSUPPORTED = {getattr(errno, n) for n in ('ENOSYS','ENOTSUP','EOPNOTSUPP') if hasattr(errno, n)}


def emit(data): print(json.dumps(data, ensure_ascii=False), flush=True)


def worker(root):
    session = PlanSession(store.Layout(Path(root), 'profiles/pilot'), profile_id='Pilot')
    plan = None; native = False
    for line in sys.stdin:
        msg = json.loads(line)
        if msg['cmd'] == 'plan':
            where = 'в профиле Pilot' if msg['target'] == 'L1' else 'в проекте'
            text = (f"Создай черновик контракта {msg['id']} {where}, постоянное, "
                    'область «docs», название «Пример», основание «Проба», '
                    'критерий «Запись существует»: Синтетический текст.')
            native = False; plan = session.plan(compile_prompt(text)); emit(plan)
        elif msg['cmd'] == 'plan_native':
            native = True
            entry = audit.entry(msg['id'], 'rule', 'profile_owner', 'C-1', 'docs', state='draft')
            plan = store.plan_create(session._layout, entry); emit(plan)
        elif msg['cmd'] == 'apply':
            real_replace = store._replace
            def pause(path, raw, rel, *, expected_metadata=None):
                emit({'outcome':'paused'})
                if json.loads(sys.stdin.readline()) != {'cmd':'resume'}: raise ValueError('resume')
                return real_replace(path, raw, rel, expected_metadata=expected_metadata)
            def apply():
                if native:
                    return {'outcome':'applied', 'status':store.apply_create(session._layout, plan, confirmed_ticket=msg['ticket'])}
                return session.apply(plan, confirmed_ticket=msg['ticket'])
            try:
                if msg.get('pause'):
                    with patch.object(store, '_replace', side_effect=pause): result = apply()
                else: result = apply()
                emit(result)
            except StoreError as error: emit({'outcome':'error', 'code':error.code})
        else: raise ValueError('command')


@unittest.skipUnless(SUPPORTED, 'POSIX directory flock API unavailable; not_run')
class InterprocessWriteLock(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='isync-dirlock-test-'); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve(); audit.make_workspace(self.root, parent_scope='.')
        self.paths = {'L0': self.root/'kit/base/registry.json', 'L1': self.root/'profiles/pilot/registry.json',
                      'L2': self.root/'.domain-agent-kit/project/registry.json'}
        try:
            fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try: store.fcntl.flock(fd, store.fcntl.LOCK_EX | store.fcntl.LOCK_NB)
            finally: os.close(fd)
        except OSError as error:
            if error.errno in UNSUPPORTED: self.skipTest('directory flock unsupported; not_run')
            raise
        self.procs = []; self.addCleanup(self.cleanup)

    def cleanup(self):
        for proc, _ in self.procs:
            if proc.poll() is None: proc.kill()
            proc.communicate(timeout=10)

    def process(self, root=None):
        return self.spawn([sys.executable, '-I', '-S', '-B', SCRIPT, '--worker', str(root or self.root)])

    def spawn(self, command):
        p = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, encoding='utf-8', bufsize=1)
        lines = queue.Queue()
        def read():
            for line in p.stdout: lines.put(line)
            lines.put(None)
        threading.Thread(target=read, daemon=True).start(); self.procs.append((p, lines))
        return p, lines

    def send(self, peer, msg):
        peer[0].stdin.write(json.dumps(msg)+'\n'); peer[0].stdin.flush()

    def receive(self, peer):
        try: line = peer[1].get(timeout=10)
        except queue.Empty: self.fail('worker response timeout')
        if line is None:
            peer[0].wait(timeout=10); self.fail('worker exited: '+peer[0].stderr.read())
        return json.loads(line)

    def request(self, peer, msg): self.send(peer, msg); return self.receive(peer)
    def plan(self, peer, ident, target):
        plan = self.request(peer, {'cmd':'plan', 'id':ident, 'target':target})
        self.assertEqual(plan['outcome'], 'planned'); return plan
    def snapshot(self): return {area: path.read_bytes() for area, path in self.paths.items()}
    def history(self, area):
        document, journal = registry_journal.unpack_registry(json.loads(self.paths[area].read_bytes()), area=area)
        return document, [d['entry_id'] for d in journal['decisions']]

    def setup_peers(self, area_a, area_b, root_b=None):
        a,b=self.process(),self.process(root_b); before=self.snapshot()
        pa,pb=self.plan(a,'A-9',area_a),self.plan(b,'B-9',area_b)
        self.assertEqual(pa['inputs_sha256'],pb['inputs_sha256']); self.assertEqual(before,self.snapshot())
        self.send(a, {'cmd':'apply','ticket':pa['ticket'],'pause':True})
        self.assertEqual(self.receive(a)['outcome'], 'paused')
        return a,b,pa,pb,before

    def case(self, area_a, area_b, root_b=None):
        a,b,pa,pb,before=self.setup_peers(area_a,area_b,root_b)
        command={'cmd':'apply','ticket':pb['ticket']}
        self.assertEqual(self.request(b,command),{'outcome':'error','code':'write_busy'})
        self.assertEqual(before,self.snapshot())
        self.send(a,{'cmd':'resume'}); self.assertEqual(self.receive(a)['outcome'],'applied')
        after=self.snapshot();self.assertEqual(hashlib.sha256(after[area_a]).hexdigest(),pa['diff']['after_sha256'])
        self.assertEqual(self.request(b,command)['code'],'ticket_unknown')
        self.assertEqual(after,self.snapshot());self.assertEqual(self.history(area_a)[1],['A-9'])
        new=self.plan(b,'B-9',area_b)
        self.assertEqual(self.request(b,{'cmd':'apply','ticket':new['ticket']})['outcome'],'applied')
        if area_a == area_b:self.assertEqual(self.history(area_a)[1],['A-9','B-9'])
        else:
            self.assertEqual(self.history(area_a)[1],['A-9']);self.assertEqual(self.history(area_b)[1],['B-9'])
        self.assertEqual(self.paths['L0'].read_bytes(),before['L0'])

    def test_same_l1(self): self.case('L1','L1')
    def test_same_l2(self): self.case('L2','L2')
    def test_l1_l2(self): self.case('L1','L2')
    def test_l2_l1(self): self.case('L2','L1')
    def test_workspace_symlink_alias_uses_same_lock(self):
        link=self.root.parent/(self.root.name+'-alias');link.symlink_to(self.root, target_is_directory=True)
        self.addCleanup(link.unlink)
        self.case('L1','L1',link)

    def test_native_cannot_write_while_session_holds_directory_lock(self):
        a,b=self.process(),self.process(); pa=self.plan(a,'A-9','L1')
        pb=self.request(b,{'cmd':'plan_native','id':'Q-9'}); before=self.snapshot()
        self.send(a,{'cmd':'apply','ticket':pa['ticket'],'pause':True})
        self.assertEqual(self.receive(a)['outcome'],'paused')
        self.assertEqual(self.request(b,{'cmd':'apply','ticket':pb['ticket']})['code'],'write_busy')
        self.assertEqual(self.snapshot(),before)
        self.send(a,{'cmd':'resume'}); self.assertEqual(self.receive(a)['outcome'],'applied')
        # Нативный билет не сессионный; повтор видит другую ревизию.
        self.assertEqual(self.request(b,{'cmd':'apply','ticket':pb['ticket']})['code'],'stale_revision')
        self.assertEqual(self.history('L1')[1],['A-9'])

    def test_session_cannot_write_while_native_holds_directory_lock(self):
        a,b=self.process(),self.process(); pa=self.request(a,{'cmd':'plan_native','id':'Q-9'})
        pb=self.plan(b,'B-9','L1'); before=self.snapshot()
        self.send(a,{'cmd':'apply','ticket':pa['ticket'],'pause':True})
        self.assertEqual(self.receive(a)['outcome'],'paused')
        self.assertEqual(self.request(b,{'cmd':'apply','ticket':pb['ticket']})['code'],'write_busy')
        self.assertEqual(self.snapshot(),before)
        self.send(a,{'cmd':'resume'}); self.assertEqual(self.receive(a)['outcome'],'applied')
        self.assertEqual(self.request(b,{'cmd':'apply','ticket':pb['ticket']})['code'],'ticket_unknown')
        self.assertEqual(self.history('L1')[1],['Q-9'])

    def test_killed_holder_before_staging_releases_lock(self):
        a,b,_,pb,before=self.setup_peers('L1','L1')
        self.assertEqual(self.request(b,{'cmd':'apply','ticket':pb['ticket']})['code'],'write_busy')
        a[0].kill();a[0].wait(timeout=10);self.assertEqual(before,self.snapshot())
        fresh=self.plan(b,'B-9','L1')
        self.assertEqual(self.request(b,{'cmd':'apply','ticket':fresh['ticket']})['outcome'],'applied')
        self.assertEqual(self.history('L1')[1],['B-9'])

    def test_uncooperative_process_can_still_change_file(self):
        a,b,pa,_,before=self.setup_peers('L1','L1')
        marker=b'synthetic-outside-lock\n'
        result=subprocess.run([sys.executable,'-I','-S','-B','-c',
                               'from pathlib import Path; import sys; Path(sys.argv[1]).write_bytes(b"synthetic-outside-lock\\n")',
                               str(self.paths['L1'])],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(self.paths['L1'].read_bytes(),marker)
        self.send(a,{'cmd':'resume'});self.assertEqual(self.receive(a)['outcome'],'applied')
        self.assertEqual(hashlib.sha256(self.paths['L1'].read_bytes()).hexdigest(),pa['diff']['after_sha256'])
        self.assertNotEqual(self.paths['L1'].read_bytes(),marker)
        self.assertEqual(self.paths['L0'].read_bytes(),before['L0'])

    def test_different_workspaces_can_write_in_separate_processes(self):
        other=self.root/'independent';other.mkdir();audit.make_workspace(other,parent_scope='.')
        a,b=self.process(),self.process(other)
        pa,pb=self.plan(a,'A-9','L1'),self.plan(b,'B-9','L1')
        self.send(a,{'cmd':'apply','ticket':pa['ticket'],'pause':True});self.assertEqual(self.receive(a)['outcome'],'paused')
        self.assertEqual(self.request(b,{'cmd':'apply','ticket':pb['ticket']})['outcome'],'applied')
        self.send(a,{'cmd':'resume'});self.assertEqual(self.receive(a)['outcome'],'applied')
        self.assertEqual(self.history('L1')[1],['A-9'])

    def check_json_interface_lock(self, peer, *, snapshot=False):
        request = {'type':'plan', 'request':audit.card(ident='Q-9')['request']}
        before=self.snapshot();plan=self.request(peer,request)
        self.assertEqual(plan['outcome'],'planned')
        fd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            store.fcntl.flock(fd,store.fcntl.LOCK_EX|store.fcntl.LOCK_NB)
            msg={'type':'apply','plan':plan,'confirmed_ticket':plan['ticket']}
            response=self.request(peer,msg)
            if snapshot:
                self.assertEqual(response,{'outcome':'error','code':'runtime_preflight_failed'})
            else:
                self.assertEqual(response['diagnostic']['code'],'write_busy')
            self.assertEqual(self.snapshot(),before)
        finally: os.close(fd)
        self.assertEqual(self.request(peer,msg)['diagnostic']['code'],'ticket_unknown')
        fresh=self.request(peer,request)
        self.assertEqual(self.request(peer,{'type':'apply','plan':fresh,
                                           'confirmed_ticket':fresh['ticket']})['outcome'],'applied')
        self.assertEqual(self.history('L1')[1],['Q-9'])

    def test_json_cli_enforces_directory_lock(self):
        peer=self.spawn([sys.executable,'-I','-S','-B',str(ROOT/'kit/session_cli.py'),
                         '--workspace',str(self.root),'--profile-root','profiles/pilot','--profile-id','Pilot'])
        self.check_json_interface_lock(peer)

    def test_isolated_snapshot_enforces_directory_lock(self):
        temp=tempfile.TemporaryDirectory(prefix='isync-lock-candidate-');self.addCleanup(temp.cleanup)
        candidate=Path(temp.name).resolve()
        raw=(ROOT/'kit/KIT-VERSION.json').read_bytes(); manifest=json.loads(raw)
        for rel in ('kit/KIT-VERSION.json', *manifest['files']):
            target=candidate/rel;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/rel,target)
        l0=json.loads(self.paths['L0'].read_bytes());l0['release_version']=manifest['version']
        audit.write(self.paths['L0'],l0)
        system_pin=hashlib.sha256(self.paths['L0'].read_bytes()).hexdigest()
        peer=self.spawn([sys.executable,'-I','-S','-B',str(ROOT/'kit/snapshot_session.py'),
                         '--candidate-root',str(candidate),'--workspace',str(self.root),
                         '--profile-root','profiles/pilot','--profile-id','Pilot',
                         '--manifest-pin',hashlib.sha256(raw).hexdigest(),'--system-pin',system_pin])
        self.check_json_interface_lock(peer,snapshot=True)

    def test_missing_or_failed_lock_is_fail_closed(self):
        layout=store.Layout(self.root,'profiles/pilot');session=PlanSession(layout,profile_id='Pilot')
        for mode in ('missing','unsupported','permission','busy','bad_inode'):
            with self.subTest(mode=mode):
                plan=session.plan(audit.card(ident='Q-9'));before=self.snapshot()
                if mode=='missing': mock=patch.object(store,'fcntl',None)
                elif mode=='unsupported': mock=patch.object(store.fcntl,'flock',side_effect=OSError(errno.ENOTSUP,'synthetic'))
                elif mode=='permission': mock=patch.object(store.os,'open',side_effect=OSError(errno.EACCES,'synthetic'))
                elif mode=='busy': mock=patch.object(store.fcntl,'flock',side_effect=OSError(errno.EAGAIN,'synthetic'))
                else:
                    from types import SimpleNamespace
                    mock=patch.object(store.os,'fstat',return_value=SimpleNamespace(st_mode=0, st_ino=0))
                with mock, self.assertRaises(StoreError) as error:
                    session.apply(plan,confirmed_ticket=plan['ticket'])
                self.assertEqual(error.exception.code,'write_busy' if mode=='busy' else 'write_lock_unavailable')
                self.assertEqual(self.snapshot(),before)
                with self.assertRaises(StoreError) as replay: session.apply(plan,confirmed_ticket=plan['ticket'])
                self.assertEqual(replay.exception.code,'ticket_unknown')
        new=session.plan(audit.card(ident='Q-9'))
        self.assertEqual(session.apply(new,confirmed_ticket=new['ticket'])['outcome'],'applied')

    def test_changed_directory_identity_or_missing_metadata_fails_closed(self):
        from types import SimpleNamespace
        layout=store.Layout(self.root,'profiles/pilot');session=PlanSession(layout,profile_id='Pilot')
        real_stat=os.stat
        for mode in ('path_changed','missing_fields'):
            with self.subTest(mode=mode):
                plan=session.plan(audit.card(ident='Q-9'));before=self.snapshot()
                def changed(path, *args, **kwargs):
                    info=real_stat(path,*args,**kwargs)
                    if Path(path)==self.root and kwargs.get('follow_symlinks') is False:
                        return SimpleNamespace(st_mode=info.st_mode,st_dev=info.st_dev,st_ino=info.st_ino+1)
                    return info
                mocked = (patch.object(store.os,'stat',side_effect=changed) if mode=='path_changed'
                          else patch.object(store.os,'fstat',return_value=SimpleNamespace(st_mode=0)))
                with patch.object(store,'_workspace',return_value=self.root), mocked:
                    with self.assertRaises(StoreError) as error:
                        session.apply(plan,confirmed_ticket=plan['ticket'])
                self.assertEqual(error.exception.code,'write_lock_unavailable')
                self.assertEqual(self.snapshot(),before)
                with self.assertRaises(StoreError) as replay: session.apply(plan,confirmed_ticket=plan['ticket'])
                self.assertEqual(replay.exception.code,'ticket_unknown')

    def test_release_failure_reports_uncertain_outcome_and_frees_local_mutex(self):
        layout=store.Layout(self.root,'profiles/pilot');session=PlanSession(layout,profile_id='Pilot')
        plan=session.plan(audit.card(ident='Q-9'));real_close=os.close;real_fstat=os.fstat
        def fail_after_close(fd):
            info=real_fstat(fd);root_info=self.root.stat()
            is_lock=(info.st_dev,info.st_ino)==(root_info.st_dev,root_info.st_ino)
            real_close(fd)
            if is_lock:raise OSError(errno.EIO,'synthetic after lock close')
        with patch.object(store.os,'close',side_effect=fail_after_close):
            with self.assertRaises(StoreError) as error: session.apply(plan,confirmed_ticket=plan['ticket'])
        self.assertEqual(error.exception.code,'write_lock_release_failed')
        self.assertEqual(hashlib.sha256(self.paths['L1'].read_bytes()).hexdigest(),plan['diff']['after_sha256'])
        with self.assertRaises(StoreError) as replay: session.apply(plan,confirmed_ticket=plan['ticket'])
        self.assertEqual(replay.exception.code,'ticket_unknown')
        new=session.plan(audit.card(ident='Q-8'))
        self.assertEqual(session.apply(new,confirmed_ticket=new['ticket'])['outcome'],'applied')


if __name__ == '__main__':
    if len(sys.argv)==3 and sys.argv[1]=='--worker': worker(sys.argv[2])
    else: unittest.main()
