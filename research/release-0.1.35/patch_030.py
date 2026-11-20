"""Правки выпуска 0.1.20 (И-040): отмена и удаление — со следом.

§9.4 донорского документа требует, чтобы у отмены и удаления были свои процедуры и свой след. Отмена
(`transition` → `revoked`) была и остаётся: запись сохраняется в реестре, но перестаёт действовать.
Удаление (`purge`) было, а следа не было: запись исчезала из `entries`, и от неё оставалась только строка
решения с идентификатором.

Что меняется:

1. **Удаление оставляет след.** `purge` переносит запись в `tombstones`: идентификатор, вид, контракт,
   область, заголовок, время, причина и ревизия на момент удаления. Содержимое (текст, основание, критерий,
   ключ, значение) не сохраняется — удалённое удалено.
2. **След виден.** Читающая команда `removed` отдаёт список следов; `status` называет их число.
3. **Идентификатор не переиспользуется.** Проверка схемы не даёт одному идентификатору быть и в `entries`,
   и в `tombstones`; счётчик `next_id` по-прежнему только растёт.
4. **Старые данные читаются.** `tombstones` — необязательное поле: проект 0.1.19 без него открывается и
   получает след при первом удалении.

Правило тождества, операции и уровни достоверности не менялись.
"""

CHECK_STATE_OLD = """    exact(s, 'schema_version revision next_id entries decisions base adapter retired')"""

CHECK_STATE_NEW = """    exact(s, 'schema_version revision next_id entries decisions base adapter retired', 'tombstones')"""

ENTRIES_CHECK_OLD = """    for e in s['entries']:
        need(type(e) is dict and ID.fullmatch(string(e.get('id'), 'id')) and int(e['id'].split('-')[1]) < s['next_id'], 'id', 'Нарушен счётчик ID.')"""

ENTRIES_CHECK_NEW = """    for e in s['entries']:
        need(type(e) is dict and ID.fullmatch(string(e.get('id'), 'id')) and int(e['id'].split('-')[1]) < s['next_id'], 'id', 'Нарушен счётчик ID.')
    for t in s.get('tombstones', []):
        need(type(t) is dict, 'removed', 'След удаления — объект.')
        exact(t, 'id kind contract scope title at reason revision')
        need(ID.fullmatch(string(t['id'], 'id')) and t['kind'] in TYPES, 'removed', 'Неверный след удаления.')
        need(date_ok(t['at']) and integer(t['revision'], 1), 'removed', 'Неверное время или ревизия следа.')
        for k in ('scope', 'title', 'reason'):
            string(t[k], k)
        need(t['contract'] is None or type(t['contract']) is str, 'removed', 'Родитель следа — строка или null.')
    need(not ({t['id'] for t in s.get('tombstones', [])} & {e['id'] for e in s['entries']}), 'removed',
         'Идентификатор не может быть одновременно удалён и занят.')"""

PURGE_OLD = """            s['entries'].remove(e)
            changes = [{'field': 'entry', 'before': i, 'after': None}]"""

PURGE_NEW = """            s['entries'].remove(e)
            # 0.1.20: удаление оставляет след. Содержимое не сохраняется, но запись о записи остаётся,
            # иначе по журналу нельзя ответить, что именно было удалено и когда (И-040, §9.4).
            s.setdefault('tombstones', []).append(
                {'id': i, 'kind': e['kind'], 'contract': e['contract'], 'scope': e['scope'],
                 'title': e['title'], 'at': at, 'reason': string(r['reason']), 'revision': e['revision']})
            changes = [{'field': 'entry', 'before': i, 'after': None}]"""

HISTORY_OLD = """    if command == 'history':
        return {'decisions': s['decisions']}
    raise Refusal('command', 'Неизвестная команда.')"""

HISTORY_NEW = """    if command == 'history':
        return {'decisions': s['decisions']}
    if command == 'removed':
        # 0.1.20: след удаления виден, а содержимого уже нет (И-040, §9.4).
        return {'removed': s.get('tombstones', []), 'count': len(s.get('tombstones', [])),
                'writes': False,
                'note': 'Следы удаления: идентификатор, вид, область, заголовок, время, причина и ревизия. '
                        'Содержимое удалённой записи не сохраняется.'}
    raise Refusal('command', 'Неизвестная команда.')"""

STATUS_OLD = """                'observations': checks['checks'], 'runtime_inferred': False}"""

STATUS_NEW = """                'observations': checks['checks'], 'removed': len(s.get('tombstones', [])),
                'runtime_inferred': False}"""

READ_ONLY_OLD = """READ_ONLY = ('status', 'list', 'history', 'updates', 'pending', 'operations', 'inventory',
             'adapter', 'brief', 'identity', 'discovery', 'entry', 'session')"""

READ_ONLY_NEW = """READ_ONLY = ('status', 'list', 'history', 'removed', 'updates', 'pending', 'operations', 'inventory',
             'adapter', 'brief', 'identity', 'discovery', 'entry', 'session')"""

CHOICES_OLD = "choices=('status', 'list', 'history', 'updates', 'pending', 'operations', 'inventory', 'adapter', 'brief', 'identity', 'discovery', 'entry', 'repeat', 'session', 'plan', 'apply')"

CHOICES_NEW = "choices=('status', 'list', 'history', 'removed', 'updates', 'pending', 'operations', 'inventory', 'adapter', 'brief', 'identity', 'discovery', 'entry', 'repeat', 'session', 'plan', 'apply')"

TEST_030 = r"""
    @case('X54', 'Удаление оставляет след, а содержимое не сохраняется.', '§9.4 (И-040).')
    def test_77_purge_trace(self):
        self.install();self.make()
        self.make('rule','P-1',title='правило',scope='.',text='текст правила',basis='fixture',
                  criterion='observable')
        ident=self.state()['entries'][1]['id']
        self.assertEqual(self.call('removed')['count'],0)
        self.apply(dict(op='transition',id=ident,to='revoked',reason='отзыв'))
        self.apply(dict(op='purge',id=ident,reason='удаление',allow_delete=True))
        state=self.state()
        self.assertNotIn(ident,[e['id'] for e in state['entries']])
        trace=self.call('removed')
        self.assertEqual(trace['count'],1);self.assertFalse(trace['writes'])
        item=trace['removed'][0]
        self.assertEqual(item['id'],ident);self.assertEqual(item['kind'],'rule')
        self.assertEqual(item['reason'],'удаление');self.assertEqual(item['title'],'правило')
        self.assertNotIn('text',item);self.assertNotIn('value',item);self.assertNotIn('key',item)
        self.assertEqual(self.call('status')['removed'],1)
        last=self.call('history')['decisions'][-1]
        self.assertEqual(last['op'],'purge')
        self.assertEqual(last['changes'],[{'field':'entry','before':ident,'after':None}])
        self.assertRefused('id',self.preview,dict(op='purge',id=ident,reason='повтор',allow_delete=True))
        self.make('rule','P-1',title='новое',scope='.',text='новый текст')
        self.assertNotEqual(self.state()['entries'][-1]['id'],ident)

    @case('X55', 'Отмена сохраняет запись и не оставляет следа удаления.', '§9.4 (И-040).')
    def test_78_revoked_kept(self):
        self.install();self.make()
        self.make('rule','P-1',title='правило',scope='.',text='текст правила',basis='fixture',
                  criterion='observable')
        ident=self.state()['entries'][1]['id']
        self.apply(dict(op='transition',id=ident,to='revoked',reason='отзыв'))
        entry=[e for e in self.state()['entries'] if e['id']==ident][0]
        self.assertEqual(entry['state'],'revoked');self.assertEqual(entry['text'],'текст правила')
        self.assertEqual(self.call('removed')['count'],0)
        self.assertEqual(self.call('status')['removed'],0)
        self.assertRefused('edit',self.preview,dict(op='edit',id=ident,fields=dict(text='иначе'),reason='нельзя'))
        self.assertRefused('transition',self.preview,dict(op='transition',id=ident,to='active',reason='назад'))
        self.assertRefused('fields',self.preview,dict(op='purge',id=ident,reason='без согласия'))
        self.assertRefused('delete',self.preview,dict(op='purge',id=ident,reason='без согласия',allow_delete=False))
        self.assertIn(ident,[e['id'] for e in self.state()['entries']])
        self.assertEqual([e['id'] for e in self.call('list')['active']],[])
"""

PROTOCOL_030 = """

## Отмена и удаление (0.1.20)

Отмена и удаление — разные операции, и след у них разный.

**Отмена** — `{"op": "transition", "id": "P-2", "to": "revoked", "reason": "…"}`. Запись остаётся в
реестре со своим текстом и историей, но перестаёт действовать. Отменённую запись нельзя править
(`edit` → `edit`), вернуть в действие (`transition` из `revoked` не разрешён) и удалить без согласия
(`purge` требует `allow_delete: true`).

**Удаление** — `{"op": "purge", "id": "P-2", "reason": "…", "allow_delete": true}` и только после отмены.
Запись исчезает из `entries` и из действующего набора, но оставляет след в `tombstones`: идентификатор,
вид, контракт, область, заголовок, время, причина и ревизия на момент удаления. Содержимое — текст,
основание, критерий, ключ и значение — не сохраняется: удалённое удалено. Следы видны командой `removed`
(`count`, `removed`), а `status` называет их число (`removed`). Идентификатор удалённой записи не
переиспользуется: `next_id` только растёт, и схема не допускает один и тот же ID в `entries` и
`tombstones`.
"""

README_030 = """
## Что изменилось в 0.1.20

Удаление оставляет след: `purge` переносит запись в `tombstones` — идентификатор, вид, контракт, область,
заголовок, время, причина и ревизия; содержимое не сохраняется. Следы видны командой `removed`, их число —
в `status`. Отмена (`revoked`) по-прежнему сохраняет запись целиком и следа не создаёт. Идентификатор
удалённой записи не переиспользуется. Поле `tombstones` необязательное: данные 0.1.19 читаются.
"""
