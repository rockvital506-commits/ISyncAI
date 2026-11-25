#!/usr/bin/env python3
"""Только тестовая репетиция в TemporaryDirectory, не API переноса/восстановления Kit."""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'research/audit')]
import core_audit as audit
import move_recovery_model as model
from kit.base import move_intent, registry_journal, schema_v2, registry_store as store
from kit.base.registry_policy import StoreError

PHASES=('before_marker','after_create','half_record','full_record','marker_synced','parent_synced',
        'target_staged','target_synced','target_replaced','target_parent_synced',
        'source_staged','source_synced','source_replaced','source_parent_synced','finished')


def encode(intent):
    out=dict(intent)
    for key in ('before','after'):
        out[key]={k:base64.b64encode(v).decode('ascii') for k,v in intent[key].items()}
    return json.dumps(out,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()


def decode(raw):
    doc=schema_v2.parse_json(raw)
    for key in ('before','after'):
        doc[key]={k:base64.b64decode(v,validate=True) for k,v in doc[key].items()}
    model._validate(doc)
    return doc


def paths(root):
    return {'L0':root/'kit/base/registry.json','L1':root/'profiles/pilot/registry.json',
            'L2':root/'.domain-agent-kit/project/registry.json'}


def write_all(fd, data):
    view=memoryview(data)
    while view:
        n=os.write(fd,view)
        if n<=0:raise OSError('short write')
        view=view[n:]


def child(root, action, stop, record):
    """Исключительно стендовая реализация, применима только внутри собственной фикстуры теста."""
    files=paths(root);marker=root/'.domain-agent-kit/.move-pending'
    def crash(phase):
        if stop==phase:os._exit(77)
    def sync_fd(fd, label):
        if stop=='fail_'+label:raise OSError('synthetic fsync failure: '+label)
        os.fsync(fd)
    def sync_dir(directory, label):
        fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY)
        try:sync_fd(fd,label)
        finally:os.close(fd)
    def replace(area, raw, prefix):
        path=files[area];stage=path.parent/('.test-move-'+prefix+'-'+os.urandom(12).hex())
        fd=os.open(stage,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        try:
            write_all(fd,raw);crash(prefix+'_staged');sync_fd(fd,prefix);crash(prefix+'_synced')
        finally:os.close(fd)
        os.replace(stage,path);crash(prefix+'_replaced');sync_dir(path.parent,prefix+'_parent');crash(prefix+'_parent_synced')
    lock=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
    try:
        store.fcntl.flock(lock,store.fcntl.LOCK_EX|store.fcntl.LOCK_NB)
        intent=decode(record)
        if action=='start':
            if {k:v.read_bytes() for k,v in files.items()}!=intent['before']:return 'stale'
            crash('before_marker')
            fd=os.open(marker,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            try:
                crash('after_create');mid=len(record)//2;write_all(fd,record[:mid]);crash('half_record')
                write_all(fd,record[mid:]);crash('full_record');sync_fd(fd,'marker');crash('marker_synced')
            finally:os.close(fd)
            sync_dir(marker.parent,'marker_parent');crash('parent_synced')
        elif action=='recover':
            # Эталон передаётся тестом отдельно и доверен только в данной фикстуре.
            try: found=marker.read_bytes()
            except FileNotFoundError:return 'marker_missing'
            if found!=record:return 'marker_untrusted_or_partial'
            # Полный видимый файл не доказывает предыдущего fsync: закрепляем его и родителя.
            fd=os.open(marker,os.O_RDONLY|os.O_NOFOLLOW)
            try:sync_fd(fd,'recovery_marker');crash('recovery_marker_synced')
            finally:os.close(fd)
            sync_dir(marker.parent,'recovery_parent');crash('recovery_parent_synced')
        else:raise ValueError('test only')
        for _ in range(3):
            current={k:v.read_bytes() for k,v in files.items()}
            state={'registries':current,'intent':intent}
            try:result=model.advance(state)
            except model.ModelError:return 'foreign_or_impossible'
            if action=='recover' and result in ('source_deleted','complete_intent_retained'):
                # При предыдущем обрыве после rename синхронизация каталога могла не пройти.
                # Не удаляем источник, пока целевая версия не синхронизирована повторно.
                for area,label in ((intent['target'],'target'),) + (((intent['source'],'source'),) if result=='complete_intent_retained' else ()):
                    fd=os.open(files[area],os.O_RDONLY|os.O_NOFOLLOW)
                    try:sync_fd(fd,'recovery_'+label);crash('recovery_'+label+'_synced')
                    finally:os.close(fd)
                    sync_dir(files[area].parent,'recovery_'+label+'_parent');crash('recovery_'+label+'_parent_synced')
            if result=='complete_intent_retained':
                crash('finished');return 'complete_marker_retained'
            area=intent['target'] if result=='target_written' else intent['source']
            replace(area,state['registries'][area],'target' if area==intent['target'] else 'source')
        raise AssertionError('unexpected state')
    finally:os.close(lock)


@unittest.skipUnless(os.name=='posix' and store.fcntl is not None and hasattr(os,'O_DIRECTORY'),
                     'POSIX directory flock unavailable; not_run')
class FilesystemRehearsal(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(prefix='domain-move-rehearsal-');self.addCleanup(tmp.cleanup)
        self.base=Path(tmp.name).resolve();self.count=0
    def fixture(self,src):
        self.count+=1;root=self.base/str(self.count);root.mkdir();layout=audit.make_workspace(root,parent_scope='.')
        files=paths(root);doc=json.loads(files[src].read_bytes())
        parent='C-1' if src=='L1' else 'P-1';auth='profile_owner' if src=='L1' else 'project_owner'
        doc['entries'].append(audit.entry('SOURCE','rule',auth,parent,'docs',state='active'));audit.write(files[src],doc)
        dst='L2' if src=='L1' else 'L1';target=audit.entry('TARGET','rule','project_owner' if dst=='L2' else 'profile_owner',
                                                           'P-1' if dst=='L2' else 'C-1','docs',state='active')
        raw={k:v.read_bytes() for k,v in files.items()};context=None if src=='L1' else {'project_names':[],'machine_names':[],'project_paths':[]}
        _,intent=model.prepare(raw,source=src,target=dst,entry_id='SOURCE',candidate=target,portability_context=context)
        sibling=root/'neighbor';sibling.write_bytes(b'unchanged synthetic')
        return root,layout,intent,encode(intent),sibling
    def run_child(self,root,action,phase,record):
        proc=subprocess.run([sys.executable,'-I','-S','-B',str(Path(__file__).resolve()),'--child',str(root),action,phase],
                            input=record,capture_output=True,timeout=20)
        return proc
    def test_process_exit_each_step_both_directions_then_recovery(self):
        for src in ('L1','L2'):
            for phase in PHASES:
                with self.subTest(source=src,phase=phase):
                    root,layout,intent,record,sibling=self.fixture(src);files=paths(root);marker=root/'.domain-agent-kit/.move-pending'
                    proc=self.run_child(root,'start',phase,record);self.assertEqual(proc.returncode,77,proc.stderr)
                    observed={k:p.read_bytes() for k,p in files.items()}
                    self.assertEqual(observed['L0'],intent['before']['L0']);self.assertEqual(sibling.read_bytes(),b'unchanged synthetic')
                    self.assertIn(observed[src],(intent['before'][src],intent['after'][src]))
                    self.assertIn(observed[intent['target']],(intent['before'][intent['target']],intent['after'][intent['target']]))
                    if observed[src]==intent['after'][src]:self.assertEqual(observed[intent['target']],intent['after'][intent['target']])
                    if marker.exists():
                        with self.assertRaises(StoreError) as error:store.status(layout)
                        self.assertEqual(error.exception.code,'move_pending')
                    else:self.assertEqual(observed,intent['before'])
                    recovery=self.run_child(root,'recover','never',record)
                    self.assertEqual(recovery.returncode,0,recovery.stderr);out=recovery.stdout.decode().strip()
                    if phase=='before_marker':self.assertEqual(out,'marker_missing');self.assertEqual(observed,{k:p.read_bytes() for k,p in files.items()})
                    elif phase in ('after_create','half_record'):
                        self.assertEqual(out,'marker_untrusted_or_partial');self.assertEqual(observed,{k:p.read_bytes() for k,p in files.items()})
                    else:
                        self.assertEqual(out,'complete_marker_retained')
                        self.assertEqual({k:p.read_bytes() for k,p in files.items()},dict(intent['before'],**intent['after']))
                        self.assertEqual(marker.read_bytes(),record)
                        again=self.run_child(root,'recover','never',record);self.assertEqual(again.stdout.decode().strip(),'complete_marker_retained')
                        for area in ('L1','L2'):
                            doc,journal=registry_journal.unpack_registry(schema_v2.parse_json(files[area].read_bytes()),area=area)
                            ids={e['id'] for e in doc['entries']}
                            self.assertNotIn('SOURCE',ids);self.assertEqual('TARGET' in ids,area==intent['target'])
                            self.assertEqual(journal['decisions'][-1]['operation'],'delete' if area==src else 'create')
                    self.assertEqual(sibling.read_bytes(),b'unchanged synthetic')
    def test_intent_diagnoses_real_interrupted_states_without_unblocking(self):
        for src in ('L1','L2'):
            for phase,expected in (('parent_synced','before_both'),('target_replaced','target_after_source_before'),
                                   ('source_replaced','after_both')):
                with self.subTest(src=src,phase=phase):
                    root,layout,original,record,sibling=self.fixture(src);files=paths(root)
                    preview=original['preview']
                    report,portable=move_intent.build(original['before'],source=src,target=original['target'],
                        entry_id=preview['source_entry']['id'],candidate=preview['target_entry'],
                        portability_context=original['portability_context'])
                    self.assertEqual(self.run_child(root,'start',phase,record).returncode,77)
                    observed={k:v.read_bytes() for k,v in files.items()}
                    result=move_intent.assess(portable,intent_pin=report['intent_sha256'],observed=observed)
                    self.assertEqual(result['state'],expected);self.assertEqual(result['marker'],'not_checked')
                    with self.assertRaises(StoreError) as error:store.status(layout)
                    self.assertEqual(error.exception.code,'move_pending');self.assertEqual(sibling.read_bytes(),b'unchanged synthetic')

    def test_crash_during_recovery_is_retryable_with_retained_marker(self):
        points=('recovery_marker_synced','recovery_parent_synced','target_staged','target_synced',
                'target_replaced','target_parent_synced','recovery_target_synced','recovery_target_parent_synced',
                'source_staged','source_synced','source_replaced','source_parent_synced',
                'recovery_source_synced','recovery_source_parent_synced')
        for phase in points:
            with self.subTest(phase=phase):
                root,layout,intent,record,sibling=self.fixture('L2');files=paths(root);marker=root/'.domain-agent-kit/.move-pending'
                self.assertEqual(self.run_child(root,'start','parent_synced',record).returncode,77)
                failed=self.run_child(root,'recover',phase,record)
                self.assertEqual(failed.returncode,77,failed.stderr)
                self.assertEqual(marker.read_bytes(),record)
                with self.assertRaises(StoreError) as error:store.status(layout)
                self.assertEqual(error.exception.code,'move_pending')
                recovered=self.run_child(root,'recover','never',record)
                self.assertEqual(recovered.stdout.decode().strip(),'complete_marker_retained')
                self.assertEqual({k:p.read_bytes() for k,p in files.items()},dict(intent['before'],**intent['after']))
                self.assertEqual(marker.read_bytes(),record);self.assertEqual(sibling.read_bytes(),b'unchanged synthetic')

    def test_fsync_failures_never_report_success_and_are_recoverable_in_fixture(self):
        for label in ('marker','marker_parent','target','target_parent','source','source_parent'):
            with self.subTest(fsync=label):
                root,layout,intent,record,sibling=self.fixture('L1');files=paths(root);marker=root/'.domain-agent-kit/.move-pending'
                failed=self.run_child(root,'start','fail_'+label,record)
                self.assertNotEqual(failed.returncode,0);self.assertNotIn(b'complete_marker_retained',failed.stdout)
                self.assertEqual(marker.read_bytes(),record)
                with self.assertRaises(StoreError) as error:store.status(layout)
                self.assertEqual(error.exception.code,'move_pending')
                recovered=self.run_child(root,'recover','never',record)
                self.assertEqual(recovered.stdout.decode().strip(),'complete_marker_retained')
                self.assertEqual({k:p.read_bytes() for k,p in files.items()},dict(intent['before'],**intent['after']))
                self.assertEqual(marker.read_bytes(),record);self.assertEqual(sibling.read_bytes(),b'unchanged synthetic')

    def test_recovery_sync_failure_refuses_further_writes(self):
        for label in ('recovery_marker','recovery_parent','recovery_target','recovery_target_parent',
                      'recovery_source','recovery_source_parent'):
            with self.subTest(fsync=label):
                root,layout,intent,record,sibling=self.fixture('L2');files=paths(root);marker=root/'.domain-agent-kit/.move-pending'
                phase='source_replaced' if label.startswith('recovery_source') else 'target_replaced'
                self.assertEqual(self.run_child(root,'start',phase,record).returncode,77)
                before={k:v.read_bytes() for k,v in files.items()}
                failed=self.run_child(root,'recover','fail_'+label,record)
                self.assertNotEqual(failed.returncode,0);self.assertEqual(before,{k:v.read_bytes() for k,v in files.items()})
                self.assertEqual(marker.read_bytes(),record)
                recovered=self.run_child(root,'recover','never',record)
                self.assertEqual(recovered.stdout.decode().strip(),'complete_marker_retained')
                self.assertEqual({k:p.read_bytes() for k,p in files.items()},dict(intent['before'],**intent['after']))
                self.assertEqual(sibling.read_bytes(),b'unchanged synthetic')

    def test_drift_and_corruption_block_without_any_registry_write(self):
        for changed in ('L0','L1','L2','marker'):
            with self.subTest(changed=changed):
                root,layout,intent,record,sibling=self.fixture('L1');files=paths(root);marker=root/'.domain-agent-kit/.move-pending'
                self.assertEqual(self.run_child(root,'start','parent_synced',record).returncode,77)
                path=marker if changed=='marker' else files[changed];path.write_bytes(path.read_bytes()+b'foreign')
                before={k:v.read_bytes() for k,v in files.items()};marker_before=marker.read_bytes()
                result=self.run_child(root,'recover','never',record)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(result.stdout.decode().strip(),'marker_untrusted_or_partial' if changed=='marker' else 'foreign_or_impossible')
                self.assertEqual(before,{k:v.read_bytes() for k,v in files.items()});self.assertEqual(marker.read_bytes(),marker_before)
                self.assertEqual(sibling.read_bytes(),b'unchanged synthetic')
    def test_impossible_order_blocks_recovery(self):
        root,layout,intent,record,sibling=self.fixture('L1');files=paths(root)
        self.assertEqual(self.run_child(root,'start','parent_synced',record).returncode,77)
        files['L1'].write_bytes(intent['after']['L1']);before={k:v.read_bytes() for k,v in files.items()}
        result=self.run_child(root,'recover','never',record)
        self.assertEqual(result.stdout.decode().strip(),'foreign_or_impossible');self.assertEqual(before,{k:v.read_bytes() for k,v in files.items()})

if __name__=='__main__':
    if len(sys.argv)==5 and sys.argv[1]=='--child':
        result=child(Path(sys.argv[2]),sys.argv[3],sys.argv[4],sys.stdin.buffer.read())
        print(result,flush=True)
    else:unittest.main()
