"""Правки выпуска 0.1.21 (И-041): секреты не пишутся и не печатаются.

§9.5 донорского документа требует двух вещей от комплекта: секрет нельзя записать в реестр и нельзя
напечатать. До 0.1.21 в правило можно было вписать токен — он попадал в `state.json`, в `list`, в
`history` и в повтор, а оттуда в любой отчёт.

Что меняется:

1. **Запись отклоняется своим кодом.** `create` и `edit` проверяют поля на образцы секретов (токены
   GitHub, AWS, Slack, Google, OpenAI-подобные ключи, JWT, PEM-ключи, присваивания вида `password=…`) и
   отвечают отказом `secret`. `session` тоже отказывает: разовый запрос не должен нести секрет.
2. **В деталях отказа нет значения.** Только имя поля и вид образца: `{field: "text", kind: "github_token"}`.
3. **Печать закрыта для старых данных.** Любой ответ комплекта проходит через очистку: найденный секрет
   заменяется на `[скрыто]`, а в ответ добавляется счётчик `redacted`. Так проект, куда секрет попал до
   0.1.21, читается, но не расшифровывается.
4. **Схема не ужесточается.** `check_state` не отказывает на секрет в старом реестре: иначе такой проект
   перестал бы открываться. Отказ — на записи, очистка — на чтении.

Правило тождества, операции и уровни достоверности не менялись.
"""

SECRETS_BLOCK = '''SECRET_PATTERNS = (
    ('github_token', re.compile(r'gh[pousr]_[A-Za-z0-9]{20,}')),
    ('github_fine_pat', re.compile(r'github_pat_[A-Za-z0-9_]{20,}')),
    ('aws_key', re.compile(r'AKIA[0-9A-Z]{16}')),
    ('openai_key', re.compile(r'sk-[A-Za-z0-9]{20,}')),
    ('slack_token', re.compile(r'xox[baprs]-[A-Za-z0-9-]{10,}')),
    ('google_key', re.compile(r'AIza[0-9A-Za-z_\\-]{35}')),
    ('private_key', re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----')),
    ('jwt', re.compile(r'eyJ[A-Za-z0-9_\\-]{10,}\\.[A-Za-z0-9_\\-]{10,}\\.[A-Za-z0-9_\\-]{10,}')),
    ('assignment', re.compile(r'(?i)\\b(?:password|passwd|secret|token|api[_-]?key)\\s*[:=]\\s*\\S{6,}')),
)
SECRET_HIDDEN = '[скрыто]'


def secret_hits(text):
    """0.1.21: что похоже на секрет — по виду, а не по значению (И-041, §9.5)."""
    if type(text) is not str:
        return []
    return [kind for kind, pattern in SECRET_PATTERNS if pattern.search(text)]


def redact(value):
    """Найденный секрет заменяется меткой; возвращается ещё и число замен."""
    total = 0
    for _kind, pattern in SECRET_PATTERNS:
        value, n = pattern.subn(SECRET_HIDDEN, value)
        total += n
    return value, total


def scrub(node):
    """Очистка ответа целиком: секрет не печатается, даже если уже лежит в старом реестре."""
    if type(node) is str:
        return redact(node)
    if type(node) is list:
        out, total = [], 0
        for item in node:
            clean, n = scrub(item)
            out.append(clean)
            total += n
        return out, total
    if type(node) is dict:
        out, total = {}, 0
        for key, item in node.items():
            clean, n = scrub(item)
            out[key] = clean
            total += n
        return out, total
    return node, 0


def scrubbed(answer):
    clean, found = scrub(answer)
    if found and type(clean) is dict:
        clean['redacted'] = found
    return clean


'''

DISPATCH_OLD = "def dispatch(lab, project, command, payload, target=None):"

DISPATCH_NEW = '''def serve(lab, project, command, payload, target=None):'''

WRAPPER = '''def dispatch(lab, project, command, payload, target=None):
    """0.1.21: любой ответ проходит очистку — секрет не печатается (И-041, §9.5)."""
    return scrubbed(serve(lab, project, command, payload, target))


'''

SESSION_OLD = """        text = string(payload['text'], 'text', 4000)"""

SESSION_NEW = """        text = string(payload['text'], 'text', 4000)
        # 0.1.21: разовый запрос не несёт секрет — он всё равно уходит в среду и в отчёт (И-041).
        hits = secret_hits(text)
        need(not hits, 'secret',
             'Похоже на секрет: такое значение не передаётся через комплект.',
             {'field': 'text', 'kind': hits[0] if hits else None})"""

CREATE_OLD = """        need(e['state'] in ('draft', 'active'), 'transition', 'Новая запись должна быть draft или active.')
        s['entries'].append(e)"""

CREATE_NEW = """        need(e['state'] in ('draft', 'active'), 'transition', 'Новая запись должна быть draft или active.')
        # 0.1.21: секрет не попадает в реестр. В деталях — поле и вид образца, без значения (И-041, §9.5).
        for field in ('title', 'text', 'basis', 'criterion', 'key', 'value'):
            hits = secret_hits(e[field])
            need(not hits, 'secret', 'Похоже на секрет: значение не записывается и не печатается.',
                 {'field': field, 'kind': hits[0] if hits else None})
        s['entries'].append(e)"""

EDIT_OLD = """            need(e['state'] != 'revoked' and r['fields'], 'edit', 'Отменённая запись или пустое изменение.')"""

EDIT_NEW = """            need(e['state'] != 'revoked' and r['fields'], 'edit', 'Отменённая запись или пустое изменение.')
            for field, value in sorted(r['fields'].items()):
                hits = secret_hits(value)
                need(not hits, 'secret', 'Похоже на секрет: значение не записывается и не печатается.',
                     {'field': field, 'kind': hits[0] if hits else None})"""

TEST_031 = r"""
    @case('X56', 'Секрет не записывается в реестр, а отказ не пересказывает значение.', '§9.5 (И-041).')
    def test_79_secret_refused(self):
        self.install();self.make()
        token='ghp_'+'A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8'
        err=self.assertRefused('secret',self.make,'rule','P-1',title='правило',scope='.',
                               text='токен '+token)
        self.assertEqual(err.details['field'],'text')
        self.assertEqual(err.details['kind'],'github_token')
        self.assertNotIn(token,json.dumps(err.details,ensure_ascii=False))
        self.assertNotIn(token,(self.a/c.STATE).read_text(encoding='utf-8'))
        self.make('rule','P-1',title='правило',scope='.',text='обычный текст')
        ident=self.state()['entries'][-1]['id']
        self.assertRefused('secret',self.preview,dict(op='edit',id=ident,
                                                      fields=dict(text='password=hunter2hunter2'),
                                                      reason='нельзя'))
        self.assertNotIn('hunter2',(self.a/c.STATE).read_text(encoding='utf-8'))
        self.assertRefused('secret',self.call,'session',dict(kind='temporary',text='sk-'+'a'*32))
        self.assertRefused('secret',self.make,'rule','P-1',title='правило',scope='.',
                           text='обычный текст',key='api_key',value='AKIA'+'ABCDEFGHIJKLMNOP')

    @case('X57', 'Секрет из старого реестра не печатается и не пересказывается.', '§9.5 (И-041).')
    def test_80_secret_redacted(self):
        self.install();self.make()
        self.make('rule','P-1',title='правило',scope='.',text='обычный текст')
        token='AKIA'+'ABCDEFGHIJKLMNOP'
        state=self.state()
        state['entries'][1]['text']='ключ '+token
        (self.a/c.STATE).write_bytes(c.encode(state))
        listing=self.call('list')
        dumped=json.dumps(listing,ensure_ascii=False)
        self.assertNotIn(token,dumped)
        self.assertIn(c.SECRET_HIDDEN,dumped)
        self.assertGreaterEqual(listing['redacted'],1)
        history=self.call('history')
        self.assertNotIn(token,json.dumps(history,ensure_ascii=False))
        status=self.call('status')
        self.assertNotIn(token,json.dumps(status,ensure_ascii=False))
"""

PROTOCOL_031 = """

## Секреты (0.1.21)

Секрет — это не правило. Комплект не записывает его в реестр и не печатает ни в одном ответе.

**Запись отклоняется.** `create` и `edit` проверяют поля `title`, `text`, `basis`, `criterion`, `key`,
`value` на образцы: токены GitHub (`ghp_…`, `github_pat_…`), ключи AWS (`AKIA…`), Slack (`xox…`), Google
(`AIza…`), OpenAI-подобные (`sk-…`), JWT (`eyJ…`), PEM-ключи и присваивания вида `password=…`, `token: …`.
Отказ — `secret`, детали `{field, kind}`, без самого значения. `session` отказывает так же: разовый запрос
не должен нести секрет.

**Печать закрыта.** Любой ответ проходит очистку: найденное заменяется на `[скрыто]`, а в ответ добавляется
`redacted` — число замен. Поэтому проект, куда секрет попал до 0.1.21, читается, но не расшифровывается:
схема не ужесточается, иначе такой проект перестал бы открываться. Проверка идёт по виду значения, а не
по списку известных секретов: комплект не знает ваших секретов и не должен.
"""

README_031 = """
## Что изменилось в 0.1.21

Секреты отделены от правил: `create` и `edit` отклоняют значения, похожие на токены и ключи, кодом
`secret` — с именем поля и видом образца, но без самого значения. Любой ответ комплекта очищается:
найденный секрет заменяется на `[скрыто]`, в ответ добавляется счётчик `redacted`, поэтому старый реестр
с секретом читается, но не печатается. Схема не ужесточалась.
"""
