"""Правки выпуска 0.1.22 (И-042): кто вправе менять правило.

§10.1 донорского документа спрашивает, кто вправе менять правило. До 0.1.22 ответа в данных не было:
правило мог изменить любой, кто позвал `edit`, — комплект не различал участников вовсе.

Что меняется:

1. **У правила появляется владелец.** Необязательное поле `owner` — строка до 64 символов; `null` значит
   «общее правило». Новые записи всегда несут это поле, старые читаются без него.
2. **Правка — от имени владельца.** `edit`, `transition` и `purge` у правила с владельцем требуют `actor`,
   равный владельцу; иначе отказ `not_owner` с указанием владельца и того, кто пришёл. Правило без
   владельца правит любой.
3. **Передача владения — отдельное согласие.** `edit` с `fields.owner` требует `allow_owner: true`, иначе
   отказ `owner` с «откуда и куда»; назначение владельца общему правилу (`null` → `X`) идёт так же.
4. **Схема не ужесточается.** `owner` необязателен в записи: проект 0.1.21 без него открывается.

Правило тождества, операции и уровни достоверности не менялись.
"""

ENTRY_EXACT_OLD = """            exact(e, ENTRY_KEYS)"""

ENTRY_EXACT_NEW = """            exact(e, ENTRY_KEYS, 'owner')
            # 0.1.22: владелец назван в данных, иначе «кто вправе» остаётся догадкой (И-042, §10.1).
            if 'owner' in e:
                need(e['owner'] is None or (type(e['owner']) is str and 0 < len(e['owner']) <= 64
                                            and e['owner'].strip() == e['owner']), 'owner',
                     'Владелец — строка до 64 символов без крайних пробелов или null.')"""

CREATE_EXACT_OLD = """        exact(r, 'op kind title scope text basis criterion reason', 'contract state key value')"""

CREATE_EXACT_NEW = """        exact(r, 'op kind title scope text basis criterion reason', 'contract state key value owner')"""

EDITABLE_OLD = """    editable = 'title scope text basis criterion key value'"""

EDITABLE_NEW = """    editable = 'title scope text basis criterion owner key value'"""

MUTATE_EXACT_OLD = """        exact(r, {'edit': 'op id fields reason', 'transition': 'op id to reason',
                  'purge': 'op id reason allow_delete'}[op], 'allow_scope' if op == 'edit' else '')"""

MUTATE_EXACT_NEW = """        exact(r, {'edit': 'op id fields reason', 'transition': 'op id to reason',
                  'purge': 'op id reason allow_delete'}[op],
              'allow_scope allow_owner actor' if op == 'edit' else 'actor')"""

OWNER_OLD = """        need(e is not None, 'id', 'Изменять можно только существующую проектную запись.', {'id': i})"""

OWNER_NEW = """        need(e is not None, 'id', 'Изменять можно только существующую проектную запись.', {'id': i})
        # 0.1.22: кто вправе менять правило. Владелец назван в записи, правка — от его имени (И-042, §10.1).
        owner = e.get('owner')
        if owner is not None:
            need(r.get('actor') == owner, 'not_owner', 'Менять правило вправе только его владелец.',
                 {'owner': owner, 'actor': r.get('actor')})
        new_owner = r['fields']['owner'] if op == 'edit' and 'owner' in r['fields'] else owner
        if op == 'edit' and new_owner != owner:
            need(r.get('allow_owner') is True, 'owner',
                 'Передача владения — отдельное согласие allow_owner.', {'from': owner, 'to': new_owner})"""

TEST_032 = r"""
    @case('X58', 'Правило с владельцем меняет только владелец.', '§10.1 (И-042).')
    def test_81_owner_only(self):
        self.install();self.make()
        self.make('rule','P-1',title='правило',scope='.',text='текст',owner='alice')
        ident=self.state()['entries'][1]['id']
        self.assertEqual(self.state()['entries'][1]['owner'],'alice')
        self.assertRefused('not_owner',self.preview,dict(op='edit',id=ident,fields=dict(text='иначе'),
                                                         reason='нельзя'))
        self.assertRefused('not_owner',self.preview,dict(op='edit',id=ident,fields=dict(text='иначе'),
                                                         actor='bob',reason='нельзя'))
        self.assertRefused('not_owner',self.preview,dict(op='transition',id=ident,to='active',
                                                         actor='bob',reason='нельзя'))
        self.apply(dict(op='edit',id=ident,fields=dict(text='новый текст'),actor='alice',
                        reason='уточнение'))
        self.assertEqual(self.state()['entries'][1]['text'],'новый текст')
        last=self.call('history')['decisions'][-1]
        self.assertEqual(last['changes'],[{'field':'text','before':'текст','after':'новый текст'}])
        self.assertRefused('not_owner',self.preview,dict(op='purge',id=ident,reason='нельзя',
                                                         allow_delete=True,actor='bob'))

    @case('X59', 'Передача владения требует согласия; у общего правила владельца нет.', '§10.1 (И-042).')
    def test_82_owner_transfer(self):
        self.install();self.make()
        self.make('rule','P-1',title='правило',scope='.',text='текст',owner='alice')
        ident=self.state()['entries'][1]['id']
        self.assertRefused('owner',self.preview,dict(op='edit',id=ident,fields=dict(owner='bob'),
                                                     actor='alice',reason='передача'))
        self.apply(dict(op='edit',id=ident,fields=dict(owner='bob'),actor='alice',allow_owner=True,
                        reason='передача'))
        self.assertEqual(self.state()['entries'][1]['owner'],'bob')
        self.assertRefused('not_owner',self.preview,dict(op='edit',id=ident,fields=dict(text='иначе'),
                                                         actor='alice',reason='нельзя'))
        self.apply(dict(op='edit',id=ident,fields=dict(text='после передачи'),actor='bob',reason='уточнение'))
        self.assertEqual(self.state()['entries'][1]['text'],'после передачи')
        self.make('rule','P-1',title='общее',scope='.',text='общий текст')
        common=[e for e in self.state()['entries'] if e['title']=='общее'][0]
        self.assertIsNone(common['owner'])
        self.apply(dict(op='edit',id=common['id'],fields=dict(text='правка общего'),reason='любой'))
        self.apply(dict(op='edit',id=common['id'],fields=dict(owner='carol'),allow_owner=True,
                        reason='назначение владельца'))
        self.assertEqual([e for e in self.state()['entries'] if e['id']==common['id']][0]['owner'],'carol')
        self.assertRefused('owner',self.preview,dict(op='edit',id=common['id'],fields=dict(owner='dave'),
                                                     actor='carol',reason='передача'))
"""

PROTOCOL_032 = """

## Кто вправе менять правило (0.1.22)

У правила может быть владелец: необязательное поле `owner` — строка до 64 символов. `null` значит «общее
правило»; новые записи всегда несут это поле, старые читаются без него.

**Правка от имени владельца.** У правила с владельцем `edit`, `transition` и `purge` требуют `actor`,
равный `owner`: `{"op": "edit", "id": "P-2", "fields": {"text": "…"}, "actor": "alice", "reason": "…"}`.
Иначе отказ `not_owner` с указанием владельца и того, кто пришёл. Правило без владельца правит любой, и
`actor` для него не нужен.

**Передача владения — отдельное согласие.** `{"op": "edit", "id": "P-2", "fields": {"owner": "bob"},
"actor": "alice", "allow_owner": true, "reason": "…"}`. Без `allow_owner` — отказ `owner` с «откуда и
куда». Назначение владельца общему правилу (`null` → `carol`) идёт так же: это тоже передача прав.

Комплект не проверяет, что `actor` — это человек: он фиксирует, от чьего имени пришла правка. Проверка
личности — дело среды, и это объявлено, а не выдано за проверенное.
"""

README_032 = """
## Что изменилось в 0.1.22

У правила появился владелец (`owner`, необязательное поле). Правило с владельцем меняет только он:
`edit`, `transition` и `purge` требуют `actor`, равный владельцу, иначе отказ `not_owner`. Передача
владения — отдельное согласие `allow_owner`, иначе отказ `owner` с «откуда и куда». Общее правило
(`owner: null`) правит любой. Схема не ужесточена: записи 0.1.21 без владельца читаются.
"""
