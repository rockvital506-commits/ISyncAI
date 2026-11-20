"""Правки выпуска 0.1.23 (И-043): что версионируется и когда проверять.

§10.2–10.3 спрашивают, что именно получает новую версию и когда правило перечитывают. До 0.1.23 ответ
был неявным: `revision` записи росла от любого решения — включая смену состояния, — а повтор той же
правки проходил молча, без следа и без объяснения.

Что меняется:

1. **Версионируется содержимое.** `revision` записи растёт только от `edit`, меняющего поля. Смена
   состояния (`transition`) попадает в историю проекта (ревизия `s['revision']`), но версию содержимого
   не двигает: правило не изменилось, изменилось его место в наборе.
2. **Повтор — не правка.** `edit` со значениями, равными текущим, не пишет ничего и отвечает планом с
   полем `same` — перечнем полей: вызов не считается правкой, версия не двигается, и это сказано, а не
   проглочено.
3. **Срок проверки — данные записи.** Поля `reviewed_at`, `review_by` и `review_days` (1…3650, по
   умолчанию 90). Операция `review` отмечает проверку от имени владельца и переносит срок вперёд.
4. **Просроченное видно.** Команда `due` перечисляет правила, которых не проверяли вовсе
   (`never: true`) или у которых срок истёк (`overdue: true`). Чтение ничего не пишет.

Схема не ужесточается: все четыре поля необязательны, проект 0.1.22 без них открывается.
"""

ENTRY_EXACT_OLD = """            exact(e, ENTRY_KEYS, 'owner')"""

ENTRY_EXACT_NEW = """            exact(e, ENTRY_KEYS, 'owner review_days reviewed_at review_by')
            # 0.1.23: срок проверки — дата в записи, а не память участника (И-043, §10.3).
            for name in ('reviewed_at', 'review_by'):
                need(e.get(name) is None or date_ok(e[name]), 'review', 'Срок проверки — дата.',
                     {'field': name})
            need(e.get('review_days') is None or (integer(e['review_days'], 1) and e['review_days'] <= 3650),
                 'review_days', 'Срок проверки — целое от 1 до 3650 дней.')"""

CREATE_EXACT_OLD = """        exact(r, 'op kind title scope text basis criterion reason', 'contract state key value owner')"""

CREATE_EXACT_NEW = """        exact(r, 'op kind title scope text basis criterion reason',
              'contract state key value owner review_days')"""

EDITABLE_OLD = """    editable = 'title scope text basis criterion owner key value'"""

EDITABLE_NEW = """    editable = 'title scope text basis criterion owner key value review_days'"""

MUTATE_EXACT_OLD = """        exact(r, {'edit': 'op id fields reason', 'transition': 'op id to reason',
                  'purge': 'op id reason allow_delete'}[op],
              'allow_scope allow_owner actor' if op == 'edit' else 'actor')"""

MUTATE_EXACT_NEW = """        exact(r, {'edit': 'op id fields reason', 'transition': 'op id to reason',
                  'purge': 'op id reason allow_delete', 'review': 'op id reason'}[op],
              'allow_scope allow_owner actor' if op == 'edit'
              else 'review_days actor' if op == 'review' else 'actor')"""

SAME_OLD = """            if all(e[k] == v for k, v in r['fields'].items()):
                return"""

SAME_NEW = """            if all(e[k] == v for k, v in r['fields'].items()):
                # 0.1.23: повтор тем же значением — не правка. Ответ явный, версия не двигается (И-043, §10.2).
                return sorted(r['fields'])"""

PLAN_CALL_OLD = """        mutate_entry(s, r, p.at)"""

PLAN_CALL_NEW = """        same = mutate_entry(s, r, p.at)
        if same:
            p.same = same
            p.notes.append('Значения совпадают с текущими: правки нет, версия не меняется (same: '
                           + ', '.join(same) + ').')
"""

DESCRIBE_OLD = """                'request': self.request, 'writes': False}"""

DESCRIBE_NEW = """                'request': self.request, 'writes': False,
                **({'same': self.same} if getattr(self, 'same', None) else {})}"""

REVIEW_OLD = """        elif op == 'transition':
            need(r['to'] in TRANSITIONS[e['state']], 'transition', 'Переход состояния не разрешён.', {'from': e['state'], 'to': r['to']})
            changes = [{'field': 'state', 'before': e['state'], 'after': r['to']}]
            e['state'] = r['to']
        else:"""

REVIEW_NEW = """        elif op == 'transition':
            need(r['to'] in TRANSITIONS[e['state']], 'transition', 'Переход состояния не разрешён.', {'from': e['state'], 'to': r['to']})
            changes = [{'field': 'state', 'before': e['state'], 'after': r['to']}]
            e['state'] = r['to']
        elif op == 'review':
            # 0.1.23: когда проверять правило. Отметка проверки — решение, срок — данные записи (И-043, §10.3).
            need(e['state'] != 'revoked', 'review', 'Отменённую запись не проверяют.')
            days = r.get('review_days', e.get('review_days') or 90)
            need(integer(days, 1) and days <= 3650, 'review_days', 'Срок проверки — целое от 1 до 3650 дней.',
                 {'review_days': days})
            before = e.get('review_by')
            e.update(reviewed_at=at, review_days=days, review_by=plus_days(at, days))
            changes = [{'field': 'review_by', 'before': before, 'after': e['review_by']}]
        else:"""

REVISION_OLD = """        e['revision'] += 1
        e['updated_at'], e['reason'] = at, string(r['reason'])"""

REVISION_NEW = """        if op == 'edit':
            # 0.1.23: версионируется содержимое правила, а не факт решения (И-043, §10.2).
            e['revision'] += 1
        e['updated_at'], e['reason'] = at, string(r['reason'])"""

PLUS_DAYS_OLD = """def mutate_entry(s, r, at):"""

PLUS_DAYS_NEW = """def plus_days(stamp, days):
    # 0.1.23: срок проверки считается от времени решения, а не от «сегодня» читателя (И-043, §10.3).
    moment = dt.datetime.strptime(stamp, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=dt.timezone.utc)
    return (moment + dt.timedelta(days=days)).strftime('%Y-%m-%dT%H:%M:%SZ')


def mutate_entry(s, r, at):"""

DUE_OLD = """    if command == 'list':
        need(not drift and not issues, 'ambiguous', 'Нельзя объявить действующим набор с отклонениями или конфликтами.', {'drift': drift, 'conflicts': issues})"""

DUE_NEW = """    if command == 'due':
        # 0.1.23: когда проверять правило. Ответ — данные записи, чтение ничего не пишет (И-043, §10.3).
        exact(payload, '')
        at = timestamp()
        due = []
        for e in s['entries']:
            if e['kind'] != 'rule' or e['state'] == 'revoked':
                continue
            by = e.get('review_by')
            if by is None:
                due.append({'id': e['id'], 'title': e['title'], 'scope': e['scope'], 'owner': e.get('owner'),
                            'review_by': None, 'never': True, 'overdue': False})
            elif by <= at:
                due.append({'id': e['id'], 'title': e['title'], 'scope': e['scope'], 'owner': e.get('owner'),
                            'review_by': by, 'never': False, 'overdue': True})
        return {'due': sorted(due, key=lambda x: x['id']), 'count': len(due), 'checked_at': at,
                'writes': False,
                'note': 'Правила без срока проверки или с истёкшим сроком. Отметить проверку — операция review.'}
    if command == 'list':
        need(not drift and not issues, 'ambiguous', 'Нельзя объявить действующим набор с отклонениями или конфликтами.', {'drift': drift, 'conflicts': issues})"""

APPLY_OPS_OLD = """    if op in ('create', 'edit', 'transition', 'purge'):"""

APPLY_OPS_NEW = """    if op in ('create', 'edit', 'transition', 'purge', 'review'):"""

CLI_OLD = """    cli.add_argument('command', choices=('status', 'list', 'history', 'removed', 'updates', 'pending', 'operations', 'inventory', 'adapter', 'brief', 'identity', 'discovery', 'entry', 'repeat', 'session', 'plan', 'apply'))"""

CLI_NEW = """    cli.add_argument('command', choices=('status', 'list', 'history', 'removed', 'updates', 'pending', 'operations', 'inventory', 'adapter', 'brief', 'identity', 'discovery', 'entry', 'repeat', 'session', 'due', 'plan', 'apply'))"""

TEST_033 = r"""
    @case('X60', 'Версию двигает содержимое, а не факт решения.', '§10.2 (И-043).')
    def test_83_content_version(self):
        self.install();self.make()
        self.make('rule','P-1',scope='.',text='второй текст',state='draft')
        second=self.state()['entries'][1]['id']
        same=self.preview(dict(op='edit',id=second,fields=dict(text='второй текст'),reason='повтор'))
        self.assertEqual(same['same'],['text'])
        self.assertEqual(self.apply(dict(op='edit',id=second,fields=dict(text='второй текст'),
                                         reason='повтор'))['outcome'],'no_change')
        self.assertEqual(self.state()['entries'][1]['revision'],1)
        self.apply(dict(op='transition',id=second,to='active',reason='принять'))
        entry=[e for e in self.state()['entries'] if e['id']==second][0]
        self.assertEqual((entry['state'],entry['revision']),('active',1))
        self.apply(dict(op='edit',id=second,fields=dict(text='третий текст'),reason='уточнение'))
        entry=[e for e in self.state()['entries'] if e['id']==second][0]
        self.assertEqual((entry['text'],entry['revision']),('третий текст',2))
        again=self.preview(dict(op='edit',id=second,fields=dict(text='третий текст'),reason='повтор'))
        self.assertEqual(again['same'],['text'])
        self.assertEqual([e for e in self.state()['entries'] if e['id']==second][0]['revision'],2)

    @case('X61', 'Срок проверки — данные записи, и просроченное видно.', '§10.3 (И-043).')
    def test_84_review_due(self):
        self.install();self.make()
        self.make('rule','P-1',title='правило',scope='.',text='текст',owner='alice')
        ident=self.state()['entries'][1]['id']
        before=self.call('due')
        self.assertEqual([d['id'] for d in before['due']],[ident])
        self.assertTrue(before['due'][0]['never'])
        self.assertFalse(before['writes'])
        self.assertRefused('not_owner',self.preview,dict(op='review',id=ident,reason='проверка',actor='bob'))
        self.apply(dict(op='review',id=ident,reason='проверка',actor='alice'))
        entry=[e for e in self.state()['entries'] if e['id']==ident][0]
        self.assertTrue(entry['review_by']>entry['reviewed_at'])
        self.assertEqual(entry['review_days'],90)
        self.assertEqual(entry['revision'],1)
        after=self.call('due')
        self.assertEqual(after['due'],[])
        self.assertEqual(after['count'],0)
        self.apply(dict(op='review',id=ident,reason='повторная проверка',actor='alice',review_days=30))
        self.assertEqual([e for e in self.state()['entries'] if e['id']==ident][0]['review_days'],30)
        self.assertRefused('review_days',self.preview,dict(op='review',id=ident,reason='проверка',
                                                           actor='alice',review_days=0))
        last=self.call('history')['decisions'][-1]
        self.assertEqual(last['op'],'review')
"""

PROTOCOL_033 = """

## Что версионируется и когда проверять (0.1.23)

**Версия — это содержимое.** `revision` записи растёт только от `edit`, который меняет поля. Смена
состояния попадает в историю проекта, но версию содержимого не двигает: правило не изменилось,
изменилось его место в наборе. Повтор той же правки — не правка:
`{"op": "edit", "id": "P-1", "fields": {"text": "тот же текст"}, "reason": "…"}` отклоняется кодом `same`
с перечнем полей, версия остаётся прежней.

**Срок проверки — данные записи.** Поля `reviewed_at`, `review_by` и `review_days` (целое от 1 до 3650,
по умолчанию 90). Отметка проверки — отдельная операция, и она идёт от имени владельца:
`{"op": "review", "id": "P-1", "actor": "alice", "reason": "просмотрено"}`. Она ставит `reviewed_at`,
переносит `review_by` вперёд и попадает в историю; `edit` со `review_days` меняет срок, не отмечая проверку.

**Просроченное видно.** `{"command": "due"}` перечисляет правила, которых не проверяли вовсе
(`never: true`), и правила с истёкшим сроком (`overdue: true`), с владельцем и сроком. Чтение ничего не
пишет: `writes: false`.
"""

README_033 = """
## Что изменилось в 0.1.23

Версия записи (`revision`) теперь означает версию содержимого: её двигает только правка полей, а смена
состояния — нет. Повтор той же правки отклоняется кодом `same` с перечнем полей. Появился срок проверки:
`reviewed_at`, `review_by`, `review_days` (1…3650, по умолчанию 90), операция `review` от имени владельца и
команда `due` — правила без срока и с истёкшим сроком, чтение без записи. Схема не ужесточена.
"""
