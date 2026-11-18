#!/usr/bin/env python3
"""Offline acceptance tests. All writes go to fresh, synthetic run folders, not to a consumer project."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import unittest
import uuid

KIT = Path(__file__).resolve().parents[1]
CLI = KIT / 'tools/contract.py'
spec = importlib.util.spec_from_file_location('contract_tested', CLI)
c = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = c
spec.loader.exec_module(c)
RUN = None
PIN = c.digest((KIT/'base/manifest.json').read_bytes())
BASE_VERSION = c.parse((KIT/'base/manifest.json').read_bytes())['base_version']
_M, _m, _p = map(int, BASE_VERSION.split('.'))
NEXT_VERSION = f'{_M}.{_m}.{_p+1}'
LATER_VERSION = f'{_M}.{_m}.{_p+2}'
PACKAGE = 'releases/' + BASE_VERSION

def case(number, expected, limitation='Только проверенные синтетические данные; не проверка поведения модели.'):
    def label(fn):
        fn.meta = (number, expected, limitation)
        return fn
    return label


def snapshot(root):
    return {p.relative_to(root).as_posix(): c.digest(p.read_bytes()) for p in sorted(root.rglob('*')) if p.is_file() and not p.is_symlink()}


def record(i, kind, parent=None, state='active', title='fixture'):
    return dict(id=i, kind=kind, contract=parent, title=title, state=state, scope='.', text='synthetic '+title,
                basis='acceptance fixture', criterion='observable output', key=None, value=None,
                revision=1, updated_at='2026-01-01T00:00:00Z', reason='isolated fixture')


class ContractCases(unittest.TestCase):
    def setUp(self):
        global RUN
        if RUN is None:  # also supports unittest discovery without a special launcher
            RUN = c.safe(KIT.parent, 'runs/test-' + uuid.uuid4().hex)
            c.mkdirs(RUN)
        self.lab = c.safe(RUN, self._testMethodName)
        self.lab.mkdir()
        for name in ('A', 'B', 'C'):
            (self.lab/name).mkdir()
            (self.lab/name/'demo.txt').write_text('synthetic input\n', encoding='utf-8')
        self.a = self.lab/'A'
        self.evidence = {}
        self.kbase = self.lab/'kit/base'
        # Never copy arbitrary files from a user checkout or include unlisted inputs.
        for root in (self.kbase, self.lab/PACKAGE):
            root.mkdir(parents=True)
            for name in c.FILES:
                (root/name).write_bytes((KIT/'base'/name).read_bytes())
        self.install_req = dict(op='install', package=PACKAGE, pin=PIN)

    def call(self, command, r=None, project='A', target=None):
        return c.dispatch(self.lab, project, command, {} if r is None else r, target)

    def preview(self, r, project='A'):
        return self.call('plan', r, project)

    def apply(self, r, project='A'):
        view = self.preview(r, project)
        return self.call('apply', {'request': r, 'ticket': view['ticket']}, project)

    def install(self, project='A'):
        return self.apply(self.install_req, project)

    def make(self, kind='contract', child=None, **props):
        r = dict(op='create', kind=kind, title='fixture', scope='.', text='synthetic token', basis='test',
                 criterion='exact output', reason='isolated test', state='active')
        if child: r['contract'] = child
        r.update(props)
        return self.apply(r)

    def assertRefused(self, code, f, *args, **kw):
        with self.assertRaises(c.Refusal) as caught:
            f(*args, **kw)
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def state(self):
        return c.parse((self.a/c.STATE).read_bytes())

    def cli(self, command, obj=None, where='A'):
        proc = subprocess.run([sys.executable, '-I', '-B', str(CLI), '--lab', str(self.lab), '--project', where, command],
                              input=c.encode(obj or {}) if obj is not None else b'', capture_output=True, timeout=15)
        self.assertEqual(proc.stderr, b'')
        return proc.returncode, c.parse(proc.stdout) if len(proc.stdout) < c.MAX_BYTES else json.loads(proc.stdout)

    def publish(self, version=NEXT_VERSION):
        info = self.apply(dict(op='publish', version=version, origin='local:test', adapter_version=1))
        return dict(op='update', package=info['package'], pin=info['pin'])

    @case('T01', 'Чистая база имеет пустые реестры, проверяемый состав, отключённый адаптер; отсутствие файла блокирует чтение.')
    def test_01_composition(self):
        raw = snapshot(self.a)
        view = self.preview(self.install_req)
        self.assertEqual(snapshot(self.a), raw)
        self.assertEqual(len(view['changes']), len(c.FILES)+2)
        self.assertEqual(self.call('status')['health'], 'absent')
        self.install()
        self.assertEqual(self.call('list')['active'], [])
        self.assertEqual(self.state()['entries'], [])
        self.assertFalse((self.a/c.ENTRY).exists())
        self.assertEqual(self.call('status')['observations'], [])
        # Construct an incomplete private fixture from scratch (no deletes).
        (self.lab/'B'/c.STATE).parent.mkdir(parents=True)
        (self.lab/'B'/c.STATE).write_bytes((self.a/c.STATE).read_bytes())
        err = self.assertRefused('missing', self.call, 'status', None, 'B')
        self.evidence.update(files=len(view['changes']), missing=err.details, pin=PIN)

    @case('T02', 'Исправные ссылки разобраны; битая ссылка в новом выпуске не публикуется.')
    def test_02_links(self):
        self.install()
        f = self.kbase/'START.md'
        f.write_bytes(f.read_bytes()+b'\n[broken](no-such-file.md)\n')
        self.assertRefused('link', self.publish)
        self.assertFalse((self.lab/(NEXT_VERSION and 'releases/'+NEXT_VERSION)).exists())
        self.evidence['blocked'] = 'START.md → no-such-file.md'

    @case('T03', 'Повтор ID, в том числе с другим текстом, и повтор ключа JSON не разрешены.')
    def test_03_duplicate_keys_ids(self):
        x = record('B-1', 'contract')
        (self.kbase/'rules.json').write_bytes(c.encode({'schema_version': 1, 'entries': [x, dict(x, text='other')]}))
        self.assertRefused('id', self.publish)
        self.assertRefused('duplicate_key', c.parse, b'{"state":"revoked","state":"active"}')
        self.evidence['blocked'] = ['B-1 twice', 'duplicate JSON field']

    @case('T04', 'Неизвестные версия, состояние, поля и переход не вызывают потери данных.')
    def test_04_fail_closed(self):
        self.install(); self.make()
        self.assertRefused('transition', self.preview, dict(op='transition', id='P-1', to='active', reason='fixture'))
        state = self.state(); state['schema_version'] = 99; state['future_field'] = 'keep'
        raw = c.encode(state); (self.a/c.STATE).write_bytes(raw)
        self.assertRefused('schema', self.preview, dict(op='connect'))
        self.assertEqual(raw, (self.a/c.STATE).read_bytes())
        self.assertRefused('state', c.registry, [record('B-1','contract',state='unknown')], [])
        self.evidence['untouched_sha256'] = c.digest(raw)

    @case('T05', 'Без согласия нет записи; подтверждённое добавление даёт одну запись и одно решение.')
    def test_05_decisions_and_types(self):
        self.install(); self.make(); old = self.state()
        r = dict(op='create',kind='protocol',contract='P-1',title='проба',scope='.',text='fixture',basis='test',criterion='observable',reason='testing')
        view = self.preview(r)
        self.assertEqual(self.state(), old)
        self.apply(r); new = self.state(); self.assertEqual(new['revision'], old['revision']+1)
        self.assertEqual(new['entries'][-1]['state'], 'draft')
        self.assertEqual(len(new['decisions']), new['revision'])
        for k in ('rule','constraint','preference'): self.make(k, 'P-1')
        self.assertEqual(len(self.call('list')['active']), 3)
        self.evidence['decision'] = new['decisions'][-1]
        self.evidence['reviewed_paths'] = [x['path'] for x in view['changes']]

    @case('T06', 'Изменение сохраняет ID; устаревший, чужой или изменённый план отклонён.')
    def test_06_stale_plan(self):
        self.install(); self.make()
        a = dict(op='edit', id='P-1', fields={'text':'первый'}, reason='fixture')
        stale = self.preview(a)['ticket']
        self.apply(dict(a, fields={'text':'другой'}))
        old = snapshot(self.a)
        self.assertRefused('stale_plan', self.call, 'apply', {'request':a, 'ticket':stale})
        self.assertEqual(old, snapshot(self.a))
        self.apply(a); e = self.state()['entries'][0]; self.assertEqual((e['id'],e['revision'],e['text']),('P-1',3,'первый'))
        self.assertEqual(self.apply(a)['outcome'], 'no_change')
        self.install('B'); self.assertRefused('stale_plan', self.call, 'apply', {'request':{'op':'connect'}, 'ticket':self.preview({'op':'connect'})['ticket']}, 'B')
        self.evidence.update(id=e['id'], revision=e['revision'], stale='blocked')

    @case('T07', 'Приостановка и возобновление контракта скрывает/возвращает запись без изменения ребёнка.')
    def test_07_lifecycle(self):
        self.install(); self.make(); self.make('rule','P-1',scope='src')
        for st, n in [('suspended',0),('active',1)]:
            self.apply(dict(op='transition',id='P-1',to=st,reason='fixture'))
            self.assertEqual(len(self.call('list', target='src/demo')['active']),n)
        self.assertEqual(self.call('list',target='src2')['active'],[])
        self.assertEqual(self.state()['entries'][1]['revision'],1)
        self.evidence.update(child_rev=1, active_counts=[0,1], sibling_scope=0)

    @case('T08', 'Отмена терминальна; физическое удаление требует отдельного разрешения и не сносит детей.')
    def test_08_revoke_purge(self):
        self.install(); self.make(); self.make('rule','P-1')
        rev = lambda i: self.apply(dict(op='transition',id=i,to='revoked',reason='fixture'))
        purge = lambda i: dict(op='purge',id=i,allow_delete=True,reason='explicit test')
        rev('P-2'); self.assertEqual(self.state()['entries'][1]['state'],'revoked')
        self.assertRefused('transition', self.preview, dict(op='transition',id='P-2',to='active',reason='fixture'))
        self.assertRefused('delete', self.preview, dict(purge('P-2'), allow_delete=False))
        rev('P-1'); self.assertRefused('parent', self.preview,purge('P-1'))
        self.apply(purge('P-2'));self.apply(purge('P-1'));self.make()
        self.assertEqual(self.state()['entries'][0]['id'],'P-3');self.evidence['new_id']='P-3'

    @case('T09', 'Разовое указание, гипотеза, предложение и обычное чтение не меняют ни одного байта.')
    def test_09_ephemeral_intent(self):
        self.install(); before=snapshot(self.a)
        for k in ('temporary','hypothesis','proposal'):
            self.assertFalse(self.call('session',dict(kind=k,text='isolated text'))['persisted'])
        for cmd in ('list','status','history','pending','operations','updates'): self.call(cmd)
        self.assertEqual(snapshot(self.a),before);self.evidence['changed_files']=0

    @case('T10', 'Конфликт на пересечении двух областей раскрывает обе записи, непересекающиеся не блокируются.')
    def test_10_conflicts(self):
        self.install();self.make();self.make('rule','P-1',scope='src',key='example.format',value='one')
        err=self.assertRefused('conflict',self.make,'rule','P-1',scope='SRC/nested',key='example.format',value='two')
        self.assertEqual(len(err.details[0]),2)
        self.make('rule','P-1',scope='src2',key='example.format',value='two')
        self.evidence['conflicting_ids']=[e['id'] for e in err.details[0]]

    @case('T11', 'Один общий вход; повторное подключение не меняет дерево, чужой вход не присваивается.')
    def test_11_connect_disconnect(self):
        self.install();self.apply({'op':'connect'});h=snapshot(self.a)
        self.assertEqual(self.apply({'op':'connect'})['outcome'],'no_change');self.assertEqual(snapshot(self.a),h)
        self.install('B');(self.lab/'B/AGENTS.md').write_bytes(b'owner\r\n')
        self.assertRefused('foreign_entry',self.preview,{'op':'connect'},'B')
        self.assertRefused('delete',self.preview,{'op':'disconnect'})
        self.apply({'op':'disconnect','allow_delete':True});self.assertFalse((self.a/c.ENTRY).exists())
        self.assertEqual((self.lab/'B/AGENTS.md').read_bytes(),b'owner\r\n');self.evidence['second_connect_diff']=0

    @case('T12-process', 'Новый процесс CLI читает ранее сохранённое состояние, C остаётся без контракта.', 'Не проверяет автообнаружение, чтение и соблюдение правил расширениями.')
    def test_12_cold_process(self):
        rc, view=self.cli('plan',self.install_req);self.assertEqual(rc,0)
        rc,res=self.cli('apply',{'request':self.install_req,'ticket':view['ticket']});self.assertEqual(rc,0)
        self.make(); self.make('rule','P-1',text='fresh-process-canary')
        rc,res=self.cli('list');self.assertEqual((rc,res['active'][0]['text']),(0,'fresh-process-canary'))
        self.assertEqual(self.cli('status',where='C')[1]['health'],'absent')
        self.evidence.update(fresh_process=True,control='absent',editor_executed=False)

    @case('T13', 'Второй проект имеет одобренную базу, собственную ревизию, пустые правила и отдельный вход.')
    def test_13_transfer(self):
        self.install();self.make();self.apply({'op':'connect'});self.install('B')
        self.assertEqual(snapshot(self.a/c.BASE),snapshot(self.lab/'B'/c.BASE));self.assertEqual(self.call('list',project='B')['active'],[])
        self.assertFalse((self.lab/'B/AGENTS.md').exists());self.assertEqual(self.call('status',project='B')['project_revision'],1)
        self.evidence['package_files']=list(c.FILES)

    @case('T14', 'Локальная метка А и неразрешённый файл релиза не попадают в Б.')
    def test_14_no_leakage(self):
        self.install(); marker='SOURCE_PROJECT_ONLY_479';self.make(text=marker)
        (self.lab/PACKAGE/'unlisted-synthetic.txt').write_text(marker)
        self.install('B');self.assertFalse(any(marker.encode() in p.read_bytes() for p in (self.lab/'B').rglob('*') if p.is_file()))
        self.assertFalse((self.lab/'B'/c.BASE/'unlisted-synthetic.txt').exists());self.evidence['marker_hits_in_B']=0

    @case('T15', 'Три версии: независимые добавления по ID сохраняются, конфликт одного ID не разрешается без выбора.')
    def test_15_update_records(self):
        self.install();self.make();a=record('B-1','contract');b=record('B-2','contract')
        def reg(path,entries):path.write_bytes(c.encode({'schema_version':1,'entries':entries}))
        reg(self.a/c.BASE/'rules.json',[a]);reg(self.kbase/'rules.json',[b]);req=self.publish();self.apply(req)
        self.assertEqual(set(x['id'] for x in self.call('list')['contracts']),{'B-1','B-2','P-1'})
        merged=[a, dict(b,title='local text')];reg(self.a/c.BASE/'rules.json',merged)
        reg(self.kbase/'rules.json',[dict(b,title='new release')]);req=self.publish(LATER_VERSION)
        err=self.assertRefused('merge_conflict',self.preview,req); k=err.details[0]['key'];self.assertEqual(k,'rules.json:B-2')
        self.apply(dict(req,resolutions={k:'local'}));status=self.call('status');self.assertEqual(status['base_local_edits'],['rules.json'])
        self.evidence.update(conflict=k,installed=status['base']['version'],preserved='local text')

    @case('T16', 'Реальное завершение изолированного процесса между записями оставляет диагностируемую pending-операцию.', 'Остановка процесса на данной ОС, не обрыв питания и не тест расширения.')
    def test_16_process_exit(self):
        r=self.install_req;t=self.preview(r)['ticket'];script='''
import sys,importlib.util,os,json,pathlib
s=importlib.util.spec_from_file_location('offline_child',sys.argv[1]);m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m)
r,t=json.loads(sys.stdin.buffer.read());m.apply(pathlib.Path(sys.argv[2]),'A',r,t,_after_write=lambda n: os._exit(75) if n==2 else None)
'''
        proc=subprocess.run([sys.executable,'-I','-B','-c',script,str(CLI),str(self.lab)],input=c.encode([r,t]),capture_output=True,timeout=15)
        self.assertEqual((proc.returncode,proc.stderr),(75,b''));tx=self.call('pending')['pending'][0]
        self.assertEqual(self.call('status')['health'],'partial');self.assertRefused('pending',self.preview,r)
        rr=dict(op='restore',tx=tx);view=self.preview(rr); cl=view['notes'][0]['classification']
        self.assertEqual(list(cl.values()).count('delete_requires_consent'),2);self.assertEqual(self.apply(rr)['outcome'],'partial')
        rr['allow_delete']=True;self.assertEqual(self.apply(rr)['outcome'],'restored');self.install()
        self.evidence.update(child_exit=75,retry=self.call('status')['health'],classes=cl)

    @case('T17', 'Безопасные файлы восстановлены побайтово; посторонняя правка сохранена; повторное восстановление идемпотентно.')
    def test_17_foreign_and_rollback(self):
        self.install(); self.apply({'op':'connect'}); original=snapshot(self.a/c.BASE)
        for n in ('START.md','entry.txt'): (self.kbase/n).write_bytes((self.kbase/n).read_bytes()+b'\nfixture update\n')
        r=self.publish();t=self.preview(r)['ticket']
        def stop(n):
            if n==3:raise RuntimeError('fixture stop')
        with self.assertRaisesRegex(RuntimeError,'fixture stop'):c.apply(self.lab,'A',r,t,_after_write=stop)
        tx=self.call('pending')['pending'][0];foreign=self.a/c.BASE/'START.md';new=foreign.read_bytes();foreign.write_bytes(b'owner changed after stop\r\n')
        rr=dict(op='restore', tx=tx);self.assertEqual(self.apply(rr)['outcome'],'partial');self.assertEqual(foreign.read_bytes(),b'owner changed after stop\r\n')
        self.assertEqual(c.digest((self.a/c.BASE/'manifest.json').read_bytes()),original['manifest.json'])
        # Synthetic owner resolves the unexpected state for this fixture; the utility never overwrites it.
        foreign.write_bytes(new);self.assertEqual(self.apply(rr)['outcome'],'restored');self.assertEqual(self.apply(rr)['outcome'],'no_change')
        self.assertEqual(snapshot(self.a/c.BASE),original);self.assertEqual(self.call('pending')['pending'],[])
        self.evidence.update(foreign_preserved=True,restored_hashes=original,repeat='no_change')

    @case('X01', 'Опубликованный выпуск воспроизводим, не перезаписывается; подмена данных и неверный пин обнаружены.')
    def test_18_publish_trust(self):
        self.assertRefused('trust',self.preview,dict(self.install_req,pin='0'*64))
        info=self.publish();obs=self.call('updates')['local_candidates'];self.assertEqual(len(obs),2);self.assertFalse(any(x['trust_verified'] for x in obs))
        self.assertRefused('occupied',self.publish)
        (self.lab/info['package']/'START.md').write_bytes(b'unapproved release edit')
        self.assertRefused('integrity',self.preview,dict(info,op='install'));self.assertFalse((self.a/c.STATE).exists())
        self.evidence.update(pin_required=True,occupied_release_replaced=False)

    @case('X02', 'Недоступный исходный выпуск не подменяет трёхстороннее сравнение двухсторонним.')
    def test_19_unknown_ancestor(self):
        self.install();r=self.publish();(self.lab/PACKAGE/'START.md').write_bytes(b'missing original content');before=snapshot(self.a)
        self.assertRefused('no_ancestor',self.preview,r);self.assertEqual(snapshot(self.a),before);self.evidence['baseline']='unavailable, no write'

    @case('X03', 'Миграция 0 → 1 сохраняет записи и отклоняет неизвестные поля без записи.')
    def test_20_migration(self):
        self.install();self.make();self.make('rule','P-1');s=self.state();old=s['revision'];s['schema_version']=0;s['project_revision']=s.pop('revision')
        for e in s['entries']:e['status']=e.pop('state')
        req=dict(op='migrate',reason='synthetic interchange');(self.a/c.STATE).write_bytes(c.encode(dict(s,future=True)))
        self.assertRefused('fields',self.preview,req);(self.a/c.STATE).write_bytes(c.encode(s));self.apply(req)
        self.assertEqual(self.state()['revision'],old+1);self.assertEqual([e['id'] for e in self.call('list')['active']],['P-2'])
        self.evidence.update(source=0,target=1,records=len(self.state()['entries']))

    @case('X04', 'Ошибочная завершённая операция откатывается по отдельному билету, но не поверх новой правки.')
    def test_21_completed_undo(self):
        self.install();self.make();f=self.a/c.STATE;before=f.read_bytes()
        r=self.apply(dict(op='edit',id='P-1',fields={'text':'new'},reason='fixture'));after=f.read_bytes()
        rr=dict(op='undo',tx=r['transaction']);view=self.preview(rr);f.write_bytes(after+b'\n')
        self.assertRefused('undo_guard',self.call,'apply',{'request':rr,'ticket':view['ticket']});f.write_bytes(after)
        self.assertEqual(self.apply(rr)['outcome'],'restored');self.assertEqual(f.read_bytes(),before)
        self.assertEqual(len(self.call('operations')['operations']),3);self.evidence['before_sha256']=c.digest(before)

    @case('X05', 'Чужая правка входа блокирует обновление и отключение; вывод из эксплуатации сохраняет историю.')
    def test_22_retire(self):
        self.install();self.make();self.apply(dict(op='connect'));p=self.a/c.ENTRY;old=p.read_bytes();p.write_bytes(old+b'owner')
        self.assertEqual(self.call('status')['entry'],'drift');self.assertRefused('adapter_drift',self.preview,dict(op='retire',allow_delete=True))
        self.assertRefused('adapter_drift',self.preview,self.publish());p.write_bytes(old);self.apply(dict(op='retire',allow_delete=True))
        self.assertEqual(self.call('list')['contracts'],[]);self.assertEqual(len(self.state()['entries']),1)
        self.assertRefused('retired',self.preview,dict(op='connect'));self.evidence['retired']=True

    @case('X06', 'Статус наблюдения требует доказательства; чужая версия среды не получает успех автоматически.')
    def test_23_observations(self):
        self.install();o=dict(case='synthetic-file',level=1,conditions='Linux fixture',expected='exists',actual='exists',status='pass',evidence='',limits='presence only',
                        environment={k:'synthetic' for k in c.ENV_KEYS.split()});r=dict(op='record_check',observation=o)
        self.assertRefused('field',self.preview,r);o['evidence']='file fingerprint '+c.digest((self.a/c.STATE).read_bytes());self.apply(r)
        st=self.call('status');self.assertEqual(st['observations'][0]['revision'],1);self.assertFalse(st['runtime_inferred']);self.evidence['level']=1

    @case('X07', 'Конкурирующий процесс не применяет изменение во время удержания межпроцессной блокировки.')
    def test_24_two_writers(self):
        self.install();req={'op':'connect'};t=self.preview(req)['ticket']
        with c.writer(self.a):
            rc,o=self.cli('apply',dict(request=req,ticket=t));self.assertEqual((rc,o.get('error')),(2,'writer_busy'))
        self.assertFalse((self.a/c.ENTRY).exists());self.apply(req);self.evidence['competing_exit']=rc

    @case('X08', 'Выход из корня, UNC/drive, неоднозначные имена Windows и служебные пути не разрешены.', 'Лексическая проверка путей не заменяет тест Windows NTFS.')
    def test_25_paths(self):
        for x in ('../A','A/../B','C:/A','//host/share','A\\B','a/PRN.txt','a/COM¹.log','n.','n ','d:a','a//b','.git/objects','.env'):
            with self.subTest(x=x):self.assertRefused('path',c.rel,x)
        self.assertRefused('root',self.call,'status',None,'kit/base');self.evidence['rejected_examples']=12

    @case('X09', 'Ссылки и hard links в управляемом дереве блокируют чтение/запись без касания другой папки.', 'Проверяется на доступной файловой системе; не тест конкурентной подмены каталога.')
    def test_26_links_boundary(self):
        self.install();outside=self.lab/'C/demo.txt';old=outside.read_bytes();link=self.a/c.ENTRY
        try:link.symlink_to(outside)
        except (OSError,NotImplementedError) as exc:self.skipTest('symlink unavailable: '+type(exc).__name__)
        self.assertRefused('boundary',self.preview,{'op':'connect'});self.assertEqual(outside.read_bytes(),old)
        # Separate synthetic project; do not remove the link to perform the other check.
        self.install('B');os.link(outside,self.lab/'B/AGENTS.md');self.assertRefused('boundary',self.preview,{'op':'connect'},'B')
        self.evidence['outside_unchanged']=c.digest(old)

    @case('X10', 'Несовпадающие байты источника не считаются совпадающими, исходные CRLF при откате сохранены.')
    def test_27_crlf(self):
        self.install();f=self.a/c.STATE;raw=f.read_bytes().replace(b'\n',b'\r\n');f.write_bytes(raw);r=self.make();self.apply(dict(op='undo',tx=r['transaction']))
        self.assertEqual(raw,f.read_bytes());self.evidence['restored_bytes_sha256']=c.digest(raw)

    @case('X11', 'Обновление выявляет семантический конфликт между новым базовым и локальным слоем.')
    def test_28_cross_layer(self):
        self.install();self.make();self.make('rule','P-1',key='example.key',value='first')
        entries=[record('B-1','contract'),dict(record('B-2','rule','B-1'),key='example.key',value='second')]
        (self.kbase/'rules.json').write_bytes(c.encode(dict(schema_version=1,entries=entries)));r=self.publish();old=snapshot(self.a)
        self.assertRefused('conflict',self.preview,r);self.assertEqual(snapshot(self.a),old);self.evidence['project_untouched']=True

    @case('X12', 'Повреждённая копия для восстановления не используется; несогласованные пути в журнале блокируются.')
    def test_29_journal_integrity(self):
        self.install();r=self.make();tx=r['transaction'];rr=dict(op='undo',tx=tx)
        backup=self.a/(c.OPS+tx+'/before/'+c.STATE);backup.write_bytes(b'corrupt fixture');old=(self.a/c.STATE).read_bytes()
        self.assertRefused('backup',self.preview,rr);self.assertEqual((self.a/c.STATE).read_bytes(),old)
        marker=self.a/c.journal_name(tx);j=c.parse(marker.read_bytes());j['files']['unknown-target']={'before':None,'after':PIN};marker.write_bytes(c.encode(j));self.assertRefused('journal',self.call,'pending')
        self.evidence['rejections']=['backup','journal']

    @case('X13', 'Одинаковая версия с другими байтами или понижение не принимаются, пустое обновление идемпотентно.')
    def test_30_update_versions(self):
        self.install();self.assertEqual(self.apply(dict(self.install_req,op='update'))['outcome'],'no_change')
        nxt=self.publish();self.apply(nxt);self.assertRefused('downgrade',self.preview,dict(self.install_req,op='update'))
        # The original pin in state is independently checked; replacing a same-number release cannot count as a trusted ancestor.
        path=self.lab/nxt['package']/'manifest.json';m=c.parse(path.read_bytes());m['origin']='different';path.write_bytes(c.encode(m));self.assertRefused('no_ancestor',self.preview,dict(nxt,pin=c.digest(path.read_bytes())))
        self.evidence['version_before_rejected_update']=NEXT_VERSION

    @case('X14', 'Проверка reparse point отвергает каталог junction на доступной Windows.', 'Проверка только на Windows; вне Windows фиксируется not run.')
    def test_31_windows_junction(self):
        if os.name!='nt': self.skipTest('Нет Windows/NTFS в данном прогоне.')
        # mklink /J is used only with co-located, generated fixture paths; no user documents.
        junction=self.lab/'junction';target=self.lab/'C'
        cmd=subprocess.run(['cmd.exe','/d','/c','mklink','/J',str(junction),str(target)],capture_output=True,timeout=10)
        if cmd.returncode: self.skipTest('Junction недоступен в тестовом окружении.')
        self.assertRefused('boundary',c.safe,self.lab,'junction/demo.txt');self.evidence['blocked']=True

    @case('X15', 'Другие известные точки входа учитываются без чтения; изменение после предпросмотра аннулирует билет.')
    def test_32_existing_sources(self):
        self.install()
        f=self.a/'.github/copilot-instructions.md';f.parent.mkdir();f.write_bytes(b'\xff synthetic external data')
        inventory=self.call('inventory');self.assertFalse(inventory['contents_read']);self.assertEqual(inventory['native_paths'][0]['path'],'.github/copilot-instructions.md')
        self.assertRefused('existing_sources',self.preview,dict(op='connect'))
        r=dict(op='connect',ack_existing=['.github/copilot-instructions.md']);t=self.preview(r)['ticket'];f.write_bytes(f.read_bytes()+b' changed')
        self.assertRefused('stale_plan',self.call,'apply',dict(request=r,ticket=t));self.apply(r)
        self.assertEqual(f.read_bytes(),b'\xff synthetic external data changed');self.evidence['external_bytes_unchanged_after_connect']=True

    @case('X16', 'Локальные кандидаты отличены от одобренных обновлений; UNC отклонён до обращения к ФС.')
    def test_33_offline_candidates(self):
        self.install();self.publish();view=self.call('updates');self.assertEqual(view['installed_version'],BASE_VERSION)
        self.assertEqual([r['newer'] for r in view['local_candidates']],[False,True]);self.assertFalse(view['network'])
        for arg in ('//example.invalid/share/lab',r'\\example.invalid\share\lab'):
            self.assertRefused('root',c.labroot,arg)
        self.evidence.update(network=False,newer_candidates=1,source_trusted_automatically=False)

    @case('X17', 'Точный повтор наблюдения не создаёт записи; изменение любого поля создаёт новую.',
          'Правило 0.1.3: совпадение девяти полей целиком.')
    def test_40_exact_repeat(self):
        self.install();env={k:'synthetic' for k in c.ENV_KEYS.split()}
        o=dict(case='synthetic-exact',level=1,conditions='Linux fixture',expected='exists',actual='exists',status='pass',
               evidence='file fingerprint '+c.digest(b'synthetic input\n'),limits='presence only',environment=env)
        self.apply(dict(op='record_check',observation=dict(o)));before=(self.a/c.CHECKS).read_bytes()
        self.assertEqual(self.apply(dict(op='record_check',observation=dict(o)))['outcome'],'no_change')
        self.assertEqual(before,(self.a/c.CHECKS).read_bytes());self.assertEqual(len(self.call('status')['observations']),1)
        self.apply(dict(op='record_check',observation=dict(o,limits='presence only, second run')))
        self.assertEqual(len(self.call('status')['observations']),2)

    @case('X18', 'Пересказ того же наблюдения не создаёт записи: регистр, пунктуация, словоформа, порядок слов.',
          'Допуск измерен на корпусе И-020 (112 пар); проверяется правило, не поведение модели.')
    def test_41_semantic_repeat(self):
        self.install();env={k:'synthetic' for k in c.ENV_KEYS.split()}
        base=dict(case='synthetic-semantic',level=1,conditions='Условия синтетические, прогон один',expected='exists',
                  actual='Файл есть, строка 17',status='pass',evidence='file fingerprint '+c.digest(b'synthetic input\n'),
                  limits='только наличие',environment=env)
        self.apply(dict(op='record_check',observation=dict(base)));before=(self.a/c.CHECKS).read_bytes()
        forms=[dict(base,actual='файл есть строка 17'),
               dict(base,actual='Файл есть, строки 17'),
               dict(base,conditions='Условия синтетичесие, прогон один'),
               dict(base,conditions='прогон один, условия синтетические')]
        for form in forms:
            self.assertEqual(self.apply(dict(op='record_check',observation=form))['outcome'],'no_change')
            self.assertEqual(before,(self.a/c.CHECKS).read_bytes())
        self.assertEqual(len(self.call('status')['observations']),1)
        self.evidence['reworded_forms']=len(forms)

    @case('X19', 'Добавленное или снятое слово, другой факт или другая смысловая фраза создают новую запись.',
          'Проверяется запрет склейки; близость текста сама по себе не склеивает.')
    def test_42_semantic_boundary(self):
        self.install();env={k:'synthetic' for k in c.ENV_KEYS.split()}
        base=dict(case='synthetic-boundary',level=1,conditions='Условия синтетические, прогон один',expected='exists',
                  actual='Файл есть, строка 17',status='pass',evidence='file fingerprint '+c.digest(b'synthetic input\n'),
                  limits='только наличие',environment=env)
        self.apply(dict(op='record_check',observation=dict(base)))
        others=[dict(base,actual='Файл есть, строка 17; прогон повторён, результат тот же'),
                dict(base,limits='только наличие. Ограничение снято.'),
                dict(base,evidence='file fingerprint '+c.digest(b'synthetic input\n')+' (по памяти, файл не открывался)'),
                dict(base,conditions='Условия синтетические, прогон один. Только при повторном прогоне.'),
                dict(base,actual='Файл есть, строка 18'),
                dict(base,expected='absent'),
                dict(base,environment=dict(env,os='other'))]
        for i,other in enumerate(others,1):
            self.assertEqual(self.apply(dict(op='record_check',observation=other))['outcome'],'committed')
            self.assertEqual(len(self.call('status')['observations']),i+1)


class Results(unittest.TextTestResult):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.rows=[]
    def _row(self,test,status,actual):
        number,expected,limits=getattr(test,test._testMethodName).meta
        self.rows.append(dict(case=number,test=test._testMethodName,conditions='Отдельная синтетическая A/B/C: '+test._testMethodName,
                         expected=expected,actual=actual,status=status,evidence=getattr(test,'evidence',{}),limits=limits))
    def addSuccess(self,test):super().addSuccess(test);self._row(test,'pass','Все утверждения сценария выполнены.')
    def addSkip(self,test,reason):super().addSkip(test,reason);self._row(test,'not run',reason)
    def addFailure(self,test,err):super().addFailure(test,err);self._row(test,'fail',self._exc_info_to_string(err,test))
    def addError(self,test,err):super().addError(test,err);self._row(test,'fail',self._exc_info_to_string(err,test))
    def addSubTest(self,test,subtest,err):
        super().addSubTest(test,subtest,err)
        if err:self._row(test,'fail',self._exc_info_to_string(err,test))


def run():
    global RUN
    ap=argparse.ArgumentParser(description='Автоматические испытания в новой папке runs/<id>')
    ap.add_argument('--run-id',default='test-'+uuid.uuid4().hex[:12]);args=ap.parse_args();c.rel(args.run_id)
    if '/' in args.run_id:ap.error('ID прогона — один компонент имени')
    RUN=c.safe(KIT.parent,'runs/'+args.run_id);RUN.parent.mkdir(exist_ok=True);RUN.mkdir()  # never reuse a run
    start=time.monotonic();result=unittest.TextTestRunner(resultclass=Results,verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(ContractCases))
    for client in ('GitHub Copilot','Kilo Code'):
        result.rows.append(dict(case='T12-live',test=client,conditions='Windows 11 / VS Code 1.146.0 / отдельный новый сеанс',expected='Отдельные свидетельства обнаружения, чтения, выполнения и повторения.',
                                actual='Сеанс расширения не запускался.',status='not run',evidence=None,limits='Офлайн-раннер не обращается к редактору, аккаунту или модели.'))
    report=dict(version=c.VERSION,at=c.timestamp(),environment=dict(os=platform.system(),python=platform.python_version(),editor_run=False),
                duration_seconds=round(time.monotonic()-start,3),release_pin=PIN,tool_sha256=c.digest(CLI.read_bytes()),tests_sha256=c.digest(Path(__file__).read_bytes()),
                totals={k:sum(r['status']==k for r in result.rows) for k in ('pass','fail','not run','inconclusive')},cases=result.rows)
    (RUN/'CHECKS.json').write_bytes(c.encode(report));print(json.dumps(report['totals']),RUN/'CHECKS.json');return 0 if result.wasSuccessful() else 1

if __name__=='__main__':raise SystemExit(run())
