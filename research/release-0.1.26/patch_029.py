"""Правки выпуска 0.1.19 (И-039): разовый запрос — не правило.

§9.3 донорского документа требует различить правило и разовый запрос: правило действует на будущее и
живёт в реестре с ревизией и историей, запрос исполняется один раз и не сохраняется. Команда `session`
с 0.1.0 объявляла `persisted: false`, но не проверяла это утверждение и молчала, когда запрос пытались
сохранить.

Что меняется:

1. **Разовый запрос не сохраняется — и это отказ.** `persist`/`save` в запросе дают `not_saved` с
   направлением к `create`: правило оформляется отдельным решением, а не продолжением запроса.
2. **Запрос не притворяется правилом.** `kind: "rule"` даёт `not_a_request`; допустимы только
   `temporary`, `proposal`, `hypothesis`.
3. **Неизменность измеряется.** Ответ несёт `project_unchanged` — отпечаток `.agent-contract` до и после
   разбора запроса; `stored`, `writes`, `rule_created` — `false`, `applies` — «этот запуск».
4. **`session` входит в `READ_ONLY`.** Серия разовых запросов проверяется повтором (`repeat`) наравне с
   чтением: она тоже ничего не меняет.

Правило тождества, операции и уровни достоверности не менялись.
"""

READ_ONLY_OLD = """READ_ONLY = ('status', 'list', 'history', 'updates', 'pending', 'operations', 'inventory',
             'adapter', 'brief', 'identity', 'discovery', 'entry')"""

READ_ONLY_NEW = """READ_ONLY = ('status', 'list', 'history', 'updates', 'pending', 'operations', 'inventory',
             'adapter', 'brief', 'identity', 'discovery', 'entry', 'session')"""

SESSION_OLD = """    if command == 'session':
        exact(payload, 'kind text')
        need(payload['kind'] in ('temporary', 'proposal', 'hypothesis'), 'intent', 'Ожидается временное указание, предложение или гипотеза.')
        string(payload['text'])
        return {'kind': payload['kind'], 'persisted': False, 'active_rule_created': False}"""

SESSION_NEW = """    if command == 'session':
        # 0.1.19: разовый запрос — не правило. Он не сохраняется, и попытка сохранить его отклоняется
        # своим кодом, а не молчаливым согласием (И-039, §9.3).
        exact(payload, 'kind text', 'scope persist save')
        need(payload['kind'] in ('temporary', 'proposal', 'hypothesis'), 'not_a_request',
             'Это не разовый запрос: правило создаётся отдельной операцией create, с причиной и ревизией.',
             {'kind': payload['kind'], 'allowed': ['temporary', 'proposal', 'hypothesis'],
              'as_rule': {'op': 'create', 'kind': 'rule', 'reason': '…'}})
        if payload.get('persist') is True or payload.get('save') is True:
            raise Refusal('not_saved',
                          'Разовый запрос не сохраняется: у него нет ревизии, истории и области действия. '
                          'Чтобы правило действовало на будущее, оформите его операцией create.',
                          {'as_rule': {'op': 'create', 'kind': 'rule', 'scope': payload.get('scope', '.'),
                                       'text': payload.get('text'), 'reason': '…'}})
        text = string(payload['text'], 'text', 4000)
        scope = payload.get('scope', '.')
        rel(scope, dot=True)
        before = tree_digest(root)
        answer = {'kind': payload['kind'], 'persisted': False, 'stored': False, 'writes': False,
                  'active_rule_created': False, 'rule_created': False, 'applies': 'этот запуск',
                  'scope': scope, 'text_bytes': len(text.encode('utf-8')),
                  'as_rule': {'op': 'create', 'kind': 'rule', 'scope': scope, 'reason': '…'},
                  'note': 'Разовый запрос исполняется в этом запуске и не попадает в реестр: у него нет '
                          'ревизии, истории и области действия. Правило — отдельное решение create.'}
        answer['project_unchanged'] = tree_digest(root) == before
        return answer"""

TEST_029 = r"""
    @case('X52', 'Разовый запрос не сохраняется и не меняет проект.', '§9.3 (И-039).')
    def test_75_session_not_stored(self):
        self.install();before=snapshot(self.a)
        card=self.call('session',dict(kind='temporary',text='проверь сборку один раз',scope='src'))
        self.assertFalse(card['persisted']);self.assertFalse(card['stored'])
        self.assertFalse(card['writes']);self.assertFalse(card['rule_created'])
        self.assertFalse(card['active_rule_created'])
        self.assertTrue(card['project_unchanged']);self.assertEqual(card['applies'],'этот запуск')
        self.assertEqual(card['scope'],'src');self.assertEqual(card['as_rule']['op'],'create')
        self.assertEqual(snapshot(self.a),before)
        series=self.call('repeat',dict(runs=2,requests=[dict(command='session',
                                                             payload=dict(kind='hypothesis',text='что если'))]))
        self.assertTrue(series['identical']);self.assertTrue(series['project_unchanged'])
        self.assertEqual(snapshot(self.a),before)

    @case('X53', 'Разовый запрос отклоняет сохранение и не притворяется правилом.', '§9.3 (И-039).')
    def test_76_session_refusals(self):
        self.install();before=snapshot(self.a)
        err=self.assertRefused('not_a_request',self.call,'session',dict(kind='rule',text='правило'))
        self.assertIn('create',err.details['as_rule']['op'])
        saved=self.assertRefused('not_saved',self.call,'session',
                                 dict(kind='temporary',text='разово',persist=True))
        self.assertEqual(saved.details['as_rule']['op'],'create')
        self.assertRefused('not_saved',self.call,'session',dict(kind='proposal',text='предложение',save=True))
        self.assertRefused('field',self.call,'session',dict(kind='temporary',text='   '))
        self.assertRefused('field',self.call,'session',dict(kind='temporary',text='x'*4001))
        self.assertRefused('fields',self.call,'session',dict(kind='temporary',text='разово',extra=1))
        self.assertRefused('path',self.call,'session',dict(kind='temporary',text='разово',scope='../вне'))
        self.assertEqual(snapshot(self.a),before)
"""

PROTOCOL_029 = """

## Разовый запрос (0.1.19)

Запрос и правило — разные вещи. Правило живёт в реестре: у него есть ревизия, история и область действия.
Разовый запрос исполняется один раз и **не сохраняется**; в реестре от него не остаётся ничего.

`session {"kind": "temporary" | "proposal" | "hypothesis", "text": "…", "scope": "."}` отвечает
`persisted: false`, `stored: false`, `rule_created: false`, `applies: "этот запуск"` и измеренным
`project_unchanged`: отпечаток `.agent-contract` до и после разбора совпадает. Так же, как чтение, запрос
допустим внутри `repeat` — серия запросов тоже ничего не меняет.

Сохранение отклоняется своим кодом. `persist`/`save` в запросе → отказ `not_saved` с направлением к
`create`. `kind: "rule"` → отказ `not_a_request`: это не запрос, а правило, и оформляется оно отдельной
операцией `create` — с причиной, ревизией и записью в историю. Пустой или слишком длинный текст (свыше
4000 символов) → `field`; неизвестное поле → `fields`.
"""

README_029 = """
## Что изменилось в 0.1.19

Разовый запрос отделён от правила. `session` не сохраняет ничего и измеряет это: `project_unchanged`
считается по отпечатку `.agent-contract` до и после. Попытка сохранить запрос отклоняется кодом
`not_saved` с направлением к `create`, а `kind: "rule"` — кодом `not_a_request`. Запрос допустим внутри
`repeat`: серия запросов тоже не меняет проект. Правило тождества, операции и уровни достоверности не
менялись.
"""
