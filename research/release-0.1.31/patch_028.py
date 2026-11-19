"""Правки выпуска 0.1.18 (И-038): изменение существующего правила записывается как «до/после».

§9.2 донорского документа требует для изменения записи своей процедуры и своего отказа. Процедура была:
`edit`, `transition`, `purge` с причиной и ревизией. Отказа не хватало в одном месте: `edit` мог молча
сменить `scope` — область применения записи, то есть охват действующего набора правил. Это не правка
текста, а смена того, на какие пути правило распространяется.

Что меняется:

1. **Смена области — отдельное согласие.** `edit` с полем `scope`, которое действительно меняет значение,
   требует `allow_scope: true`, иначе отказ `scope`. Правка title/text/basis/criterion/key/value идёт как
   раньше.
2. **Решение записывает «до/после».** В `decisions` появляется `changes: [{field, before, after}]` для
   `edit` и `transition`. Раньше история знала причину и предмет, но не то, что именно изменилось, —
   восстановить прежний текст по журналу было нельзя.

Правило тождества, операции и уровни достоверности не менялись.
"""

DECISION_OLD = """def decision(s, op, at, reason, subject):
    s['revision'] += 1
    s['decisions'].append({'revision': s['revision'], 'op': op, 'at': at, 'reason': string(reason, 'reason'), 'subject': subject})"""

DECISION_NEW = """def decision(s, op, at, reason, subject, changes=None):
    # 0.1.18: изменение правила записывается как «до/после», иначе историю нельзя восстановить (И-038).
    s['revision'] += 1
    item = {'revision': s['revision'], 'op': op, 'at': at, 'reason': string(reason, 'reason'),
            'subject': subject}
    if changes:
        item['changes'] = changes
    s['decisions'].append(item)"""

CHANGES_CHECK = """        for c in d.get('changes', []):
            exact(c, 'field before after')
            string(c['field'], 'field')
            for k in ('before', 'after'):
                need(c[k] is None or type(c[k]) is str, 'history', 'Неверное значение «до/после».')"""

MUTATE_OLD_START = "def mutate_entry(s, r, at):"
MUTATE_OLD_END = "def safe_target(lab, project):"

CHECK_STATE_OLD = """    for n, d in enumerate(s['decisions'], 1):
        exact(d, 'revision at op reason subject')"""

CHECK_STATE_NEW = """    for n, d in enumerate(s['decisions'], 1):
        exact(d, 'revision at op reason subject', 'changes')"""

MUTATE_OLD_START = "def mutate_entry(s, r, at):"
MUTATE_OLD_END = "def safe_target(lab, project):"

MUTATE_NEW = '''def mutate_entry(s, r, at):
    op = r['op']
    editable = 'title scope text basis criterion key value'
    changes = []
    if op == 'create':
        exact(r, 'op kind title scope text basis criterion reason', 'contract state key value')
        i = 'P-' + str(s['next_id'])
        e = {k: r.get(k) for k in editable.split()}
        e.update(id=i, kind=r['kind'], contract=r.get('contract'), state=r.get('state', 'draft'), revision=1, updated_at=at, reason=string(r['reason']))
        need(e['state'] in ('draft', 'active'), 'transition', 'Новая запись должна быть draft или active.')
        s['entries'].append(e)
        s['next_id'] += 1
    else:
        exact(r, {'edit': 'op id fields reason', 'transition': 'op id to reason',
                  'purge': 'op id reason allow_delete'}[op], 'allow_scope' if op == 'edit' else '')
        i = string(r['id'], 'id')
        e = next((x for x in s['entries'] if x['id'] == i), None)
        need(e is not None, 'id', 'Изменять можно только существующую проектную запись.', {'id': i})
        if op == 'edit':
            exact(r['fields'], '', editable)
            need(e['state'] != 'revoked' and r['fields'], 'edit', 'Отменённая запись или пустое изменение.')
            if all(e[k] == v for k, v in r['fields'].items()):
                return
            # 0.1.18: область — не текст. Её смена меняет охват действующего набора и требует согласия.
            if 'scope' in r['fields'] and r['fields']['scope'] != e['scope']:
                need(r.get('allow_scope') is True, 'scope',
                     'Смена области меняет охват правила. Нужно отдельное согласие allow_scope.',
                     {'from': e['scope'], 'to': r['fields']['scope']})
            changes = [{'field': k, 'before': e[k], 'after': v}
                       for k, v in r['fields'].items() if e[k] != v]
            e.update(r['fields'])
        elif op == 'transition':
            need(r['to'] in TRANSITIONS[e['state']], 'transition', 'Переход состояния не разрешён.', {'from': e['state'], 'to': r['to']})
            changes = [{'field': 'state', 'before': e['state'], 'after': r['to']}]
            e['state'] = r['to']
        else:
            need(e['state'] == 'revoked' and r['allow_delete'] is True, 'delete', 'Удаление только после отмены и отдельного согласия.')
            need(not any(x['contract'] == i for x in s['entries']), 'parent', 'Есть дочерние записи. Каскадное удаление запрещено.')
            s['entries'].remove(e)
            changes = [{'field': 'entry', 'before': i, 'after': None}]
        e['revision'] += 1
        e['updated_at'], e['reason'] = at, string(r['reason'])
    decision(s, op, at, r['reason'], i, changes)


'''

TEST_028 = r"""
    @case('X50', 'Изменение правила записывается как «до/после» и восстанавливает прежний текст.', '§9.2 (И-038).')
    def test_73_edit_changes(self):
        self.install();self.make()
        self.make(kind='rule',child='P-1',title='правило',scope='src',text='исходный текст',state='draft')
        before=self.state()['entries'][1]
        self.assertEqual(before['text'],'исходный текст')
        self.apply(dict(op='edit',id=before['id'],fields=dict(text='новый текст'),
                        reason='уточнение формулировки'))
        after=self.state()['entries'][1]
        self.assertEqual(after['text'],'новый текст');self.assertEqual(after['revision'],before['revision']+1)
        last=self.call('history')['decisions'][-1]
        self.assertEqual(last['op'],'edit')
        self.assertEqual(last['changes'],[{'field':'text','before':'исходный текст','after':'новый текст'}])
        restored={e['field']:e['before'] for e in last['changes']}
        self.assertEqual(restored['text'],'исходный текст')
        same=self.preview(dict(op='edit',id=before['id'],fields=dict(text='новый текст'),reason='повтор'))
        self.assertEqual(same['changes'],[])
        self.assertEqual(len(self.call('history')['decisions']),len(self.state()['decisions']))
        self.apply(dict(op='transition',id=before['id'],to='active',reason='введение в действие'))
        moved=self.call('history')['decisions'][-1]
        self.assertEqual(moved['op'],'transition')
        self.assertEqual(moved['changes'],[{'field':'state','before':'draft','after':'active'}])

    @case('X51', 'Смена области требует согласия; прочие поля неизменяемы.', '§9.2 (И-038).')
    def test_74_scope_consent(self):
        self.install();self.make()
        self.make(kind='rule',child='P-1',title='правило',scope='src',text='текст',state='active')
        ident=self.state()['entries'][1]['id']
        self.assertRefused('scope',self.preview,dict(op='edit',id=ident,fields=dict(scope='docs'),
                                                     reason='перенос области'))
        self.apply(dict(op='edit',id=ident,fields=dict(scope='docs'),allow_scope=True,
                        reason='перенос области'))
        entry=self.state()['entries'][1]
        self.assertEqual(entry['scope'],'docs')
        moved=self.call('history')['decisions'][-1]
        self.assertEqual(moved['changes'],[{'field':'scope','before':'src','after':'docs'}])
        for bad in (dict(kind='contract'),dict(id='P-9'),dict(contract='P-1'),dict(revision=99)):
            self.assertRefused('fields',self.preview,{'op':'edit','id':ident,'fields':bad,'reason':'нельзя'})
        self.assertRefused('id',self.preview,dict(op='edit',id='P-99',fields=dict(text='x'),reason='нет'))
"""

PROTOCOL_028 = """

## Изменение правила (0.1.18)

Изменять существующую запись можно только полями `title`, `scope`, `text`, `basis`, `criterion`, `key`,
`value`; идентификатор, вид, контракт и ревизия неизменяемы — попытка даёт отказ `fields`.

**Область — не текст.** Смена `scope` меняет охват действующего набора правил, поэтому требует
отдельного согласия: `{"op": "edit", "id": "P-1", "fields": {"scope": "docs"}, "allow_scope": true,
"reason": "…"}`. Без `allow_scope` — отказ `scope` с указанием «откуда и куда».

**История помнит «до/после».** В решении появляется `changes: [{field, before, after}]` для `edit` (включая
смену области) и для `transition` (`state`). Поэтому прежний текст восстанавливается по журналу, а не по
памяти. Повтор того же изменения — `no_change`, и в плане `changes` пуст.
"""

README_028 = """
## Что изменилось в 0.1.18

Изменение существующего правила стало явным: смена области (`scope`) требует отдельного согласия
`allow_scope`, потому что меняет охват действующего набора, а не текст. Решение теперь хранит «до/после»
(`changes`), так что прежний текст восстанавливается по журналу. Идентификатор, вид, контракт и ревизия
по-прежнему неизменяемы. Правило тождества и операции не менялись.
"""
