"""Правки выпуска 0.1.27 (И-047): контур машины состояний — по аудиту A-001.

Аудит A-001 (`research/audit/A-001.md`) прогнал все 16 пар переходов для контракта и правила: матрица
`draft → active ⇄ suspended → revoked` исполняется верно, чтения считают правильно, `purge` и `retired`
ведут себя как объявлено. Дыры нашлись на входе — там, где состояние контракта не спрашивают.

Что меняется:

1. **Мёртвая ветка не принимает записей.** `create` под контрактом `revoked` отклоняется кодом `parent` с
   `{contract, state}`: отмена терминальна, и новая запись там не появляется.
2. **`active` — только в действующем контракте.** `create` с `state: "active"` и `transition` в `active`
   под контрактом `draft`, `suspended` или `revoked` отклоняются кодом `state` с `{contract, parent_state}`.
   Иначе `active` означало бы «числится», а не «действует».
3. **`due` называет состояние.** У каждого элемента появилось поле `state`: работа над черновиком и над
   действующим правилом — разная работа.
4. **`hidden` делит причину.** `metrics.hidden.by_reason`: `parent_draft`, `parent_suspended`,
   `parent_revoked`, `retired`. Одна строка «почему» больше не заставляет выяснять сорт вручную.
5. **Скрытое не зависит от `target`.** `hidden` считается без сужения по области: запись вне `target` — не
   «скрыта контрактом», а просто вне области. `active` при этом остаётся суженным.

Схема не ужесточается: записи, уже лежащие под неактивным контрактом, читаются как прежде, а `hidden`
показывает их с причиной.
"""

CREATE_PARENT_OLD = """        s['entries'].append(e)
        s['next_id'] += 1"""

CREATE_PARENT_NEW = """        # 0.1.27: состояние контракта проверяется на входе, а не объясняется потом через hidden (И-047, A-001).
        if e['contract'] is not None:
            parent = next((x for x in s['entries'] if x['id'] == e['contract']), None)
            need(parent is not None and parent['kind'] == 'contract', 'parent',
                 'Запись должна принадлежать существующему контракту.', {'contract': e['contract']})
            need(parent['state'] != 'revoked', 'parent',
                 'Контракт отменён: новые записи в нём не создаются.', {'contract': parent['id'],
                                                                       'state': parent['state']})
            if e['state'] == 'active':
                need(parent['state'] == 'active', 'state',
                     'Активная запись возможна только в действующем контракте.',
                     {'contract': parent['id'], 'parent_state': parent['state']})
        s['entries'].append(e)
        s['next_id'] += 1"""

TRANSITION_OLD = """        elif op == 'transition':
            need(r['to'] in TRANSITIONS[e['state']], 'transition', 'Переход состояния не разрешён.', {'from': e['state'], 'to': r['to']})
            changes = [{'field': 'state', 'before': e['state'], 'after': r['to']}]
            e['state'] = r['to']"""

TRANSITION_NEW = """        elif op == 'transition':
            need(r['to'] in TRANSITIONS[e['state']], 'transition', 'Переход состояния не разрешён.', {'from': e['state'], 'to': r['to']})
            # 0.1.27: активная запись возможна только в действующем контракте — иначе обход через два шага (И-047, A-001).
            if r['to'] == 'active' and e['kind'] != 'contract':
                parent = next((x for x in s['entries'] if x['id'] == e['contract']), None)
                need(parent is not None and parent['state'] == 'active', 'state',
                     'Активная запись возможна только в действующем контракте.',
                     {'contract': e['contract'], 'parent_state': (parent or {}).get('state')})
            changes = [{'field': 'state', 'before': e['state'], 'after': r['to']}]
            e['state'] = r['to']"""

DUE_STATE_OLD = """            if by is None:
                due.append({'id': e['id'], 'title': e['title'], 'scope': e['scope'], 'owner': e.get('owner'),
                            'review_by': None, 'never': True, 'overdue': False})
            elif by <= at:
                due.append({'id': e['id'], 'title': e['title'], 'scope': e['scope'], 'owner': e.get('owner'),
                            'review_by': by, 'never': False, 'overdue': True})"""

DUE_STATE_NEW = """            if by is None:
                due.append({'id': e['id'], 'title': e['title'], 'scope': e['scope'], 'owner': e.get('owner'),
                            'state': e['state'], 'review_by': None, 'never': True, 'overdue': False})
            elif by <= at:
                due.append({'id': e['id'], 'title': e['title'], 'scope': e['scope'], 'owner': e.get('owner'),
                            'state': e['state'], 'review_by': by, 'never': False, 'overdue': True})"""

HIDDEN_OLD = """        hidden = [e for e in s['entries'] if e['kind'] != 'contract' and e['state'] == 'active'
                  and e['id'] not in active_ids]"""

HIDDEN_NEW = """        # 0.1.27: скрытое — это состояние контракта, а не сужение по target (И-047, A-001, A8).
        hidden = [] if s['retired'] else [e for e in s['entries'] if e['kind'] != 'contract'
                                          and e['state'] == 'active'
                                          and recs[e['contract']]['state'] != 'active']
        if s['retired']:
            hidden = [e for e in s['entries'] if e['kind'] != 'contract' and e['state'] == 'active']
        reasons = {'parent_draft': 0, 'parent_suspended': 0, 'parent_revoked': 0, 'retired': 0}
        for e in hidden:
            if s['retired']:
                reasons['retired'] += 1
            else:
                reasons['parent_' + recs[e['contract']]['state']] += 1"""

HIDDEN_PAYLOAD_OLD = """                'hidden': dict(slice_of(hidden), ids=[e['id'] for e in hidden],
                               why='правило active, но контракт не active или проект retired'),"""

HIDDEN_PAYLOAD_NEW = """                'hidden': dict(slice_of(hidden), ids=[e['id'] for e in hidden], by_reason=reasons,
                               why='правило active, но контракт не active или проект retired'),"""

TEST_037 = r"""
    @case('X68', 'Ввод в мёртвую ветку и активация под неактивным контрактом отклонены.', 'A-001, §15 (И-047).')
    def test_91_entry_guard(self):
        self.install(); self.make()
        self.make('rule','P-1',scope='.',text='действует')
        self.apply(dict(op='transition',id='P-1',to='suspended',reason='пауза'))
        self.assertRefused('state',self.preview,dict(op='create',kind='rule',contract='P-1',title='н',
                                                     scope='.',text='п',basis='f',criterion='o',
                                                     state='active',reason='ввод'))
        self.apply(dict(op='create',kind='rule',contract='P-1',title='черновик',scope='.',text='п',
                        basis='f',criterion='o',state='draft',reason='ввод'))
        self.assertRefused('state',self.preview,dict(op='transition',id='P-3',to='active',reason='активация'))
        self.apply(dict(op='transition',id='P-1',to='active',reason='вернуть'))
        self.apply(dict(op='transition',id='P-3',to='active',reason='активация'))
        self.assertEqual([e for e in self.state()['entries'] if e['id']=='P-3'][0]['state'],'active')
        self.apply(dict(op='transition',id='P-1',to='revoked',reason='отмена'))
        err=self.assertRefused('parent',self.preview,dict(op='create',kind='rule',contract='P-1',title='н',
                                                          scope='.',text='п',basis='f',criterion='o',
                                                          state='draft',reason='ввод'))
        self.assertEqual(err.details,{'contract':'P-1','state':'revoked'})
        self.assertEqual(self.call('status')['health'],'valid')
        met=self.call('metrics')
        self.assertEqual(met['hidden']['ids'],['P-2','P-3'])
        self.assertEqual(met['hidden']['by_reason']['parent_revoked'],2)

    @case('X69', 'due называет состояние; hidden делит причину и не зависит от target.', 'A-001, §15 (И-047).')
    def test_92_due_reason(self):
        self.install(); self.make()
        self.make('rule','P-1',scope='src',text='действует')
        self.make('rule','P-1',scope='other',text='действует вне области')
        self.make('rule','P-1',scope='.',text='черновик',state='draft')
        due=self.call('due')
        self.assertEqual(sorted(d['state'] for d in due['due']),['active','active','draft'])
        self.assertEqual(self.call('metrics')['hidden']['by_reason'],
                         {'parent_draft':0,'parent_revoked':0,'parent_suspended':0,'retired':0})
        narrow=self.call('metrics',target='src')
        self.assertEqual(narrow['active']['count'],1)
        self.assertEqual(narrow['hidden']['count'],0)
        self.apply(dict(op='transition',id='P-1',to='suspended',reason='пауза'))
        met=self.call('metrics')
        self.assertEqual(met['hidden']['by_reason']['parent_suspended'],2)
        self.assertEqual(met['hidden']['ids'],['P-2','P-3'])
        self.assertEqual(self.call('metrics',target='src')['hidden']['count'],2)
        self.apply(dict(op='transition',id='P-1',to='active',reason='вернуть'))
        met=self.call('metrics',target='src')
        self.assertEqual(met['active']['count'],1)
        self.assertEqual(met['hidden']['count'],0)
        self.apply(dict(op='retire',allow_delete=True))
        met=self.call('metrics')
        self.assertEqual(met['hidden']['by_reason']['retired'],2)
        self.assertEqual(met['active']['count'],0)
"""

PROTOCOL_037 = """

## Контур машины состояний (0.1.27)

Машина `draft → active ⇄ suspended → revoked` теперь спрашивает состояние на входе, а не объясняет
последствия задним числом.

- `create` под контрактом `revoked` — отказ `parent` с `{contract, state}`: отмена терминальна.
- `create` с `state: "active"` и `transition` в `active` под контрактом `draft`, `suspended`, `revoked` —
  отказ `state` с `{contract, parent_state}`: активная запись возможна только в действующем контракте.
- `draft` под неактивным контрактом создавать можно: черновик ждёт, пока контракт вернётся.
- `due` называет `state` каждой записи: работа над черновиком и над действующим правилом разная.
- `metrics.hidden.by_reason` — `parent_draft`, `parent_suspended`, `parent_revoked`, `retired`.
  `hidden` считается без сужения по `target`: запись вне области не «скрыта», она просто вне области.

Уже существующие записи под неактивным контрактом читаются как прежде: отказ стоит на входе, а не на чтении.
"""

README_037 = """
## Что изменилось в 0.1.27

Контур машины состояний: `create` под отменённым контрактом отклоняется кодом `parent`, а `active`-запись
(создание или переход) под неактивным контрактом — кодом `state` с указанием состояния родителя. `due`
называет состояние записи, `metrics.hidden.by_reason` делит причины, `hidden` не зависит от `target`. Схема не
ужесточена: старые записи под неактивным контрактом читаются.
"""
