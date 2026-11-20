"""Правки выпуска 0.1.28 (И-048): два сценария рядом — сравнение действующего, а не реестра.

§15 спрашивает не только «сколько стоит набор», но и «что даёт другой набор». В 0.1.26–0.1.27 метрики
считают один проект; чтобы выбрать сценарий, владельцу приходится сравнивать два JSON глазами.

Что меняется:

1. **`metrics` принимает `against`** — путь ко второму проекту. Ответ получает раздел `compare`:
   `here`/`there` (действующее с числом правил и байтами), `cost.delta`, `noise`, `hidden`.
2. **Сравнивается действующее, а не реестр.** Обе стороны сводятся к набору `active` по машине состояний
   (0.1.27): `draft`, `suspended`, `hidden` и `revoked` в сравнение не входят, но видны числами.
3. **Правила опознаются смыслом, а не `id`:** структурный факт — `key` + `scope` и значение; свободное
   правило — текст + `scope`. Отсюда четыре ответа: `same`, `changed` (тот же `key`, другое значение),
   `only_here`, `only_there`.
4. **Второй сценарий читается как действующий набор:** если он не читается (нет пути, дрейф, конфликт,
   чужая схема), `metrics` отвечает отказом `compare` с причиной, а не сравнивает половину.
5. **Сравнение ничего не пишет** (`writes: false`) и не требует `target` на второй стороне: `target`
   сужает оба сценария одинаково.

Схема не меняется: `against` — параметр чтения, поля записи те же.
"""

HELPERS_OLD = """def dispatch(lab, project, command, payload, target=None):"""

HELPERS_NEW = '''def scene_set(items):
    """0.1.28: сценарий — действующий набор, сведённый к фактам (И-048, §15)."""
    facts = {}
    for e in items:
        key = e.get('key')
        ident = ('key', key, e['scope']) if key else ('text', (e.get('text') or ''), e['scope'])
        facts.setdefault(ident, []).append({'id': e['id'], 'title': e['title'], 'scope': e['scope'],
                                            'key': key, 'value': e.get('value'),
                                            'bytes': len((e.get('text') or '').encode('utf-8'))})
    return facts


def scene_compare(here, there):
    """Сравнение двух наборов: same, changed по значению, только здесь и только там (И-048)."""
    same, changed, only_here, only_there = [], [], [], []
    for ident, rows in here.items():
        other = there.get(ident)
        if other is None:
            only_here.extend(rows)
            continue
        values = {r['value'] for r in rows} | {r['value'] for r in other}
        if ident[0] == 'key' and len(values) > 1:
            changed.append({'key': ident[1], 'scope': ident[2], 'here': [r['id'] for r in rows],
                            'there': [r['id'] for r in other],
                            'values_here': sorted({r['value'] for r in rows}, key=str),
                            'values_there': sorted({r['value'] for r in other}, key=str)})
        else:
            same.extend(rows)
    for ident, rows in there.items():
        if ident not in here:
            only_there.extend(rows)
    return {'same': same, 'changed': changed, 'only_here': only_here, 'only_there': only_there}


def dispatch(lab, project, command, payload, target=None):'''

CLI_STDIN_OLD = """        if args.command in ('session', 'plan', 'apply', 'adapter', 'discovery', 'entry', 'repeat'):"""

CLI_STDIN_NEW = """        if args.command in ('session', 'plan', 'apply', 'adapter', 'discovery', 'entry', 'repeat', 'metrics'):"""

GENERAL_EXACT_OLD = """    exact(payload, '')
    if command == 'inventory':"""

GENERAL_EXACT_NEW = """    # 0.1.28: у metrics есть параметр чтения against — сравнение с другим сценарием (И-048).
    exact(payload, '', 'against' if command == 'metrics' else '')
    if command == 'inventory':"""

METRICS_PAYLOAD_OLD = """        # 0.1.26: стоимость и шум считаются по машине состояний, а не по числу строк реестра (И-046, §15).
        exact(payload, '')"""

METRICS_PAYLOAD_NEW = """        # 0.1.26: стоимость и шум считаются по машине состояний, а не по числу строк реестра (И-046, §15).
        # 0.1.28: против второго сценария — сравнение действующего набора (И-048, §15).
        exact(payload, '', 'against')"""

METRICS_COMPARE_OLD = """        return {'writes': False, 'target': target, 'checked_at': at,
                'entries': {'total': len(s['entries']), 'by_state': by_state, 'by_kind': by_kind},"""

METRICS_COMPARE_NEW = """        answer = {'writes': False, 'target': target, 'checked_at': at,
                'entries': {'total': len(s['entries']), 'by_state': by_state, 'by_kind': by_kind},"""

METRICS_TAIL_OLD = """                'meaning': {'bytes': 'длина текста в UTF-8 — стоимость чтения участником',
                            'active': 'active-правило под active-контрактом, в пределах target',
                            'noise': 'draft и suspended: место в реестре без действия',
                            'hidden': 'active-правило, отсечённое состоянием контракта',
                            'transitions': 'переходы состояний из истории решений'}}"""

METRICS_TAIL_NEW = """                'meaning': {'bytes': 'длина текста в UTF-8 — стоимость чтения участником',
                            'active': 'active-правило под active-контрактом, в пределах target',
                            'noise': 'draft и suspended: место в реестре без действия',
                            'hidden': 'active-правило, отсечённое состоянием контракта',
                            'transitions': 'переходы состояний из истории решений'}}
        against = payload.get('against')
        if against is not None:
            need(isinstance(against, str) and against.strip(), 'against',
                 'Нужен путь ко второму сценарию.', {'against': against})
            try:
                other_root = safe_target(lab, against)
                other_state, _, _, other_recs, _, _, _ = read_project(Review(other_root, {}, at))
            except Refusal as e:
                raise Refusal('compare', 'Второй сценарий не читается как действующий набор.',
                              {'against': against, 'reason': e.code, 'details': e.details})
            there = [] if other_state['retired'] else effective(other_recs, target)
            diff = scene_compare(scene_set(active), scene_set(there))
            here_bytes = sum(len((e.get('text') or '').encode('utf-8')) for e in active)
            there_bytes = sum(len((e.get('text') or '').encode('utf-8')) for e in there)
            answer['compare'] = {
                'against': str(other_root),
                'here': dict(slice_of(active), ids=[e['id'] for e in active]),
                'there': dict(slice_of(there), ids=[e['id'] for e in there]),
                'cost': {'bytes_here': here_bytes, 'bytes_there': there_bytes,
                         'delta': here_bytes - there_bytes},
                'active': {'same': [r['id'] for r in diff['same']],
                           'changed': diff['changed'],
                           'only_here': diff['only_here'],
                           'only_there': diff['only_there']},
                'noise': {'here': len(noise),
                          'there': len([e for e in other_state['entries']
                                        if e['kind'] != 'contract' and e['state'] in ('draft', 'suspended')])},
                'note': 'Сравнивается действующий набор обоих сценариев: draft, suspended, hidden и revoked '
                        'в сравнение не входят. Правило опознаётся key+scope (иначе текстом) — id у сценариев свой.'}
        return answer"""

TEST_038 = r"""
    @case('X70', 'Два сценария сравниваются по действующему набору.', '§15 (И-048).')
    def test_93_compare_scenarios(self):
        self.install(); self.make()
        self.make('rule','P-1',scope='.',text='действует',key='k.review',value='90')
        self.make('rule','P-1',scope='.',text='без ключа')
        self.make('rule','P-1',scope='.',text='только здесь',key='k.only_here',value='1')
        self.make('rule','P-1',scope='.',text='черновик',state='draft',key='k.draft',value='x')
        self.install('B')
        def in_b(**props):
            r = dict(op='create', kind='rule', contract='P-1', title='fixture', scope='.', text='synthetic token',
                     basis='test', criterion='exact output', reason='isolated test', state='active')
            r.update(props)
            return self.apply(r, project='B')
        self.apply(dict(op='create', kind='contract', title='fixture', scope='.', text='synthetic token',
                        basis='test', criterion='exact output', reason='isolated test', state='active'), project='B')
        in_b(text='действует', key='k.review', value='30')
        in_b(text='без ключа')
        in_b(text='только там', key='k.only_there', value='2')
        in_b(text='шум', state='draft', key='k.noise', value='y')
        before = snapshot(self.a)
        view=self.call('metrics', {'against': str(self.lab/'B')})
        self.assertEqual(before, snapshot(self.a))
        cmp=view['compare']
        self.assertEqual(view['writes'],False)
        self.assertEqual([r['id'] for r in cmp['active']['only_here']],['P-4'])
        self.assertEqual([r['id'] for r in cmp['active']['only_there']],['P-4'])
        self.assertEqual(cmp['active']['changed'],
                         [{'key':'k.review','scope':'.','here':['P-2'],'there':['P-2'],
                           'values_here':['90'],'values_there':['30']}])
        self.assertEqual(cmp['active']['same'],['P-3'])
        self.assertEqual(cmp['here']['count'],3)
        self.assertEqual(cmp['there']['count'],3)
        self.assertEqual(cmp['cost']['delta'], cmp['cost']['bytes_here'] - cmp['cost']['bytes_there'])
        self.assertEqual(cmp['noise'], {'here':1,'there':1})
        self.assertEqual(cmp['active']['only_here'][0]['bytes'], len('только здесь'.encode('utf-8')))

    @case('X71', 'Сравнение отказывает, если второй сценарий не действует, и ничего не пишет.', '§15 (И-048).')
    def test_94_compare_refusals(self):
        self.install(); self.make()
        self.make('rule','P-1',scope='.',text='действует')
        err=self.assertRefused('against', self.call, 'metrics', {'against': 7})
        self.assertEqual(err.details, {'against': 7})
        err=self.assertRefused('compare', self.call, 'metrics', {'against': str(self.lab/'нет-такого')})
        self.assertEqual(err.details['reason'], 'root')
        self.install('B')
        self.apply(dict(op='create', kind='contract', title='fixture', scope='.', text='synthetic token',
                        basis='test', criterion='exact output', reason='isolated test', state='active'), project='B')
        self.apply(dict(op='create', kind='rule', contract='P-1', title='fixture', scope='.',
                        text='synthetic token', basis='test', criterion='exact output',
                        reason='isolated test', state='active'), project='B')
        base=self.lab/'B/.agent-contract/base/START.md'
        base.write_text(base.read_text(encoding='utf-8') + '\nправка\n', encoding='utf-8')
        before=snapshot(self.lab/'B')
        err=self.assertRefused('compare', self.call, 'metrics', {'against': str(self.lab/'B')})
        self.assertEqual(err.details['reason'], 'drift')
        self.assertEqual(snapshot(self.lab/'B'), before)
        err=self.assertRefused('compare', self.call, 'metrics', {'against': str(self.a/'kit')})
        self.assertEqual(err.details['reason'], 'root')
"""

PROTOCOL_038 = """

## Два сценария рядом (0.1.28)

`metrics` принимает `against` — путь ко второму проекту — и отвечает разделом `compare`.

- Сравнивается **действующий** набор обоих сценариев: `active`-правило под `active`-контрактом.
  `draft`, `suspended`, `hidden`, `revoked` в сравнение не входят, но остаются числами (`noise`).
- Правило опознаётся смыслом: структурный факт — `key` и `scope`, свободное правило — текст и `scope`.
  `id` у сценариев свой, поэтому он не сравнивается.
- Четыре ответа: `same` — те же факты; `changed` — тот же `key`, другое значение (видно оба);
  `only_here` и `only_there` — чего нет в другом сценарии.
- `cost.delta` — разница байтов текста; `here`/`there` — число правил и байты каждой стороны.
- Второй сценарий читается как действующий набор: нет пути, дрейф, конфликт или чужая схема — отказ
  `compare` с `{against, reason, details}`, а не сравнение половины.
- `target` сужает оба сценария одинаково; чтение ничего не пишет (`writes: false`).
"""

README_038 = """
## Что изменилось в 0.1.28

`metrics` умеет сравнивать два сценария: `{"against": "<путь ко второму проекту>"}` добавляет раздел
`compare` — действующий набор обеих сторон (`same`, `changed`, `only_here`, `only_there`), стоимость и
разницу байтов, шум и скрытое числами. Сравнивается действующее, а не реестр; `id` не сравнивается —
правило опознаётся `key`+`scope` или текстом. Нечитаемый второй сценарий даёт отказ `compare` с причиной.
"""
