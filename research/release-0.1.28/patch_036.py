"""Правки выпуска 0.1.26 (И-046): метрики — стоимость и шум.

§15 спрашивает, что стоит держать и что считается шумом. До 0.1.26 числа брались бы из размера реестра, а
это неверная мерка: `draft` и `suspended` лежат в реестре, но не действуют, а `active`-правило под
недействующим контрактом не действует, хотя выглядит действующим. Машина состояний
`draft → active ⇄ suspended → revoked` задаёт, что считать.

Что появляется — команда `metrics` (чтение, `writes: false`):

1. **Действующее.** `active` — то, что реально попадает в набор: `kind != 'contract'`, `state == 'active'`
   и контракт `active`, в пределах `target`. Считаются правила и байты их текста в UTF-8.
2. **Шум.** `noise` — `draft` и `suspended`: реестр помнит, набор не применяет. Тоже с байтами.
3. **Скрытое.** `hidden` — `active`-правила, отсечённые состоянием контракта (или `retired` проекта). Это не
   шум и не действие: правило активно, но в набор не попадает, и молчать об этом нельзя.
4. **Отменённое.** `revoked` — из набора выведено навсегда, но остаётся в истории и в счётчике.
5. **Переходы.** `transitions.by` — сколько раз какой переход случился, по истории решений: видно, гоняют
   ли правило по кругу.
6. **Проверки.** `review.never` и `review.overdue` — правила без срока и с истёкшим сроком (0.1.23).

Схема и операции не меняются: добавлено чтение.
"""

METRICS_OLD = """    if command == 'list':
        need(not drift and not issues, 'ambiguous', 'Нельзя объявить действующим набор с отклонениями или конфликтами.', {'drift': drift, 'conflicts': issues})"""

METRICS_NEW = """    if command == 'metrics':
        # 0.1.26: стоимость и шум считаются по машине состояний, а не по числу строк реестра (И-046, §15).
        exact(payload, '')
        at = timestamp()
        active = [] if s['retired'] else effective(recs, target)
        active_ids = set(e['id'] for e in active)
        def slice_of(items):
            return {'count': len(items),
                    'bytes': sum(len((e.get('text') or '').encode('utf-8')) for e in items)}
        by_state, by_kind = {}, {}
        for e in s['entries']:
            by_state[e['state']] = by_state.get(e['state'], 0) + 1
            by_kind[e['kind']] = by_kind.get(e['kind'], 0) + 1
        noise = [e for e in s['entries'] if e['kind'] != 'contract' and e['state'] in ('draft', 'suspended')]
        hidden = [e for e in s['entries'] if e['kind'] != 'contract' and e['state'] == 'active'
                  and e['id'] not in active_ids]
        revoked = [e for e in s['entries'] if e['state'] == 'revoked']
        transitions = [d for d in s['decisions'] if d['op'] == 'transition']
        moves = {}
        for d in transitions:
            for c in d.get('changes', []):
                if c['field'] == 'state':
                    key = (c['before'] or '?') + '→' + (c['after'] or '?')
                    moves[key] = moves.get(key, 0) + 1
        rules = [e for e in s['entries'] if e['kind'] == 'rule' and e['state'] != 'revoked']
        never = len([e for e in rules if e.get('review_by') is None])
        overdue = len([e for e in rules if e.get('review_by') is not None and e['review_by'] <= at])
        return {'writes': False, 'target': target, 'checked_at': at,
                'entries': {'total': len(s['entries']), 'by_state': by_state, 'by_kind': by_kind},
                'active': slice_of(active),
                'noise': dict(slice_of(noise), states=['draft', 'suspended'],
                              why='реестр помнит, набор не применяет'),
                'hidden': dict(slice_of(hidden), ids=[e['id'] for e in hidden],
                               why='правило active, но контракт не active или проект retired'),
                'revoked': slice_of(revoked),
                'transitions': {'count': len(transitions), 'by': moves},
                'review': {'never': never, 'overdue': overdue, 'checked_at': at},
                'meaning': {'bytes': 'длина текста в UTF-8 — стоимость чтения участником',
                            'active': 'active-правило под active-контрактом, в пределах target',
                            'noise': 'draft и suspended: место в реестре без действия',
                            'hidden': 'active-правило, отсечённое состоянием контракта',
                            'transitions': 'переходы состояний из истории решений'}}
    if command == 'list':
        need(not drift and not issues, 'ambiguous', 'Нельзя объявить действующим набор с отклонениями или конфликтами.', {'drift': drift, 'conflicts': issues})"""

CLI_OLD = """    cli.add_argument('command', choices=('status', 'list', 'history', 'removed', 'updates', 'pending', 'operations', 'inventory', 'adapter', 'brief', 'identity', 'discovery', 'entry', 'repeat', 'session', 'due', 'plan', 'apply'))"""

CLI_NEW = """    cli.add_argument('command', choices=('status', 'list', 'metrics', 'history', 'removed', 'updates', 'pending', 'operations', 'inventory', 'adapter', 'brief', 'identity', 'discovery', 'entry', 'repeat', 'session', 'due', 'plan', 'apply'))"""

TEST_036 = r"""
    @case('X66', 'Метрики считают по машине состояний: draft не действует, suspended-контракт скрывает.', '§15 (И-046).')
    def test_89_metrics_states(self):
        self.install(); self.make()
        self.make('rule','P-1',scope='.',text='действует',state='active')
        self.make('rule','P-1',scope='.',text='черновик',state='draft')
        m=self.call('metrics')
        self.assertFalse(m['writes'])
        self.assertIsNone(m['target'])
        self.assertEqual(m['entries']['by_state'],{'active':2,'draft':1})
        self.assertEqual((m['active']['count'],m['noise']['count'],m['hidden']['count'],m['revoked']['count']),(1,1,0,0))
        self.apply(dict(op='transition',id='P-1',to='suspended',reason='пауза'))
        m=self.call('metrics')
        self.assertEqual(self.call('list')['active'],[])
        self.assertEqual(m['hidden']['count'],1)
        self.assertEqual(m['hidden']['ids'],['P-2'])
        self.assertEqual(m['active']['count'],0)
        self.assertEqual(m['noise']['count'],1)
        self.apply(dict(op='transition',id='P-1',to='active',reason='вернуть'))
        m=self.call('metrics')
        self.assertEqual((m['active']['count'],m['hidden']['count']),(1,0))
        self.assertEqual(len(self.call('list')['active']),1)
        self.apply(dict(op='transition',id='P-2',to='revoked',reason='отменить'))
        m=self.call('metrics')
        self.assertEqual((m['revoked']['count'],m['active']['count']),(1,0))
        self.assertEqual(m['entries']['by_state'],{'active':1,'draft':1,'revoked':1})

    @case('X67', 'Стоимость и шум в байтах, переходы — по истории', '§15 (И-046).')
    def test_90_metrics_bytes(self):
        self.install(); self.make()
        self.make('rule','P-1',scope='.',text='aaaa',state='active')
        self.make('rule','P-1',scope='.',text='ббб',state='draft')
        m=self.call('metrics')
        self.assertEqual(m['active']['bytes'],4)
        self.assertEqual(m['noise']['bytes'],len('ббб'.encode('utf-8')))
        self.assertEqual(m['noise']['states'],['draft','suspended'])
        self.assertEqual(m['transitions']['count'],0)
        self.assertEqual(m['review']['never'],2)
        self.apply(dict(op='transition',id='P-2',to='suspended',reason='пауза'))
        m=self.call('metrics')
        self.assertEqual(m['noise']['count'],2)
        self.assertEqual(m['transitions']['count'],1)
        self.assertEqual(m['transitions']['by'],{'active→suspended':1})
        self.assertEqual(m['review']['never'],2)
        self.assertEqual(m['review']['overdue'],0)
        self.assertTrue(m['meaning']['bytes'])
"""

PROTOCOL_036 = """

## Метрики: стоимость и шум (0.1.26)

Числа берутся по машине состояний `draft → active ⇄ suspended → revoked`, а не по размеру реестра.

- `{"command": "metrics"}` — чтение, ничего не пишет; `target` сужает набор, как у `list`.
- `active` — то, что действует: `active`-правило под `active`-контрактом, с числом правил и байтами текста.
- `noise` — `draft` и `suspended`: реестр помнит, набор не применяет.
- `hidden` — `active`-правило, отсечённое состоянием контракта или `retired` проекта: не шум и не действие.
- `revoked` — выведено навсегда, но остаётся в истории и в счётчике.
- `transitions.by` — сколько раз какой переход случился: видно, гоняют ли правило по кругу.
- `review.never` и `review.overdue` — правила без срока проверки и с истёкшим сроком.

`bytes` — длина текста в UTF-8: мера того, что участник действительно читает. Пустое правило стоит 0
байт, но занимает место в обзоре; поэтому рядом с байтами всегда стоит `count`.
"""

README_036 = """
## Что изменилось в 0.1.26

Появилась команда `metrics` — чтение без записи: `active` (действующий набор с числом правил и байтами),
`noise` (`draft` и `suspended`), `hidden` (`active`-правила под недействующим контрактом), `revoked`,
`transitions.by` по истории решений и `review` (`never`/`overdue`). Счёт идёт по машине состояний, а не по
размеру реестра.
"""
