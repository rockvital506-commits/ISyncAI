"""Правки выпуска 0.1.31 (И-051): живые модели — ответ проверяется как данные.

§14 уровень 4 спрашивает не «что модель сделала», а «можно ли её ответ проверить». Поведение модели
не воспроизводимо: два прогона одного вопроса дают разные слова. Но ответ, записанный владельцем,
проверяем: в нём есть утверждения о правилах — идентификатор, состояние, текст, — и каждое сверяется
с машиной состояний.

Что меняется:

1. **Команда `model`** (чтение, `writes: false`): карточка живой части — какие задачи ставятся модели,
   куда владелец кладёт записанный ответ (`.agent-contract/local/model/*.json`), что уже записано и как
   это оценено, и честный `live: false`: комплект модель не вызывает.
2. **Команда `verify`** (чтение): оценивает один ответ как данные — утверждение за утверждением.
   `unknown_rule` — правило не найдено; `state_mismatch` — названное состояние не совпало с измеренным
   (включая `hidden`, когда правило `active`, а контракт нет); `text_mismatch` — текст расходится;
   `same` — совпало. Ответ не той формы отклоняется кодом `answer`.
3. **Список чтения:** `model` и `verify` — чтения, `repeat` их принимает.
4. **`rights.inputs`:** записанные ответы названы входом, а не записью комплекта.

Схема не меняется; закрытый список путей тот же — ответы модели лежат в `local/`, куда комплект не пишет.
"""

MODELS_OLD = """LOCAL = PREFIX + 'local/'"""

MODELS_NEW = """LOCAL = PREFIX + 'local/'
# 0.1.31: записанные ответы модели — вход владельца, а не запись комплекта (И-051, §14 ур. 4).
MODELS = LOCAL + 'model/'"""

HELPERS_OLD = """def case_conflicts(root, paths):"""

HELPERS_NEW = '''MODEL_TASKS = ('explain', 'choose', 'refuse')


def norm_text(s):
    """0.1.31: сравнение ответа модели по словам, а не по типографике (И-051)."""
    return ' '.join((s or '').split())


def reader_state(records, entry, retired):
    """0.1.31: состояние правила глазами читателя — active, hidden, draft, suspended, revoked (И-051)."""
    if retired:
        return 'retired'
    if entry['state'] == 'active' and records[entry['contract']]['state'] != 'active':
        return 'hidden'
    return entry['state']


def grade_answer(records, retired, answer):
    """0.1.31: ответ модели оценивается как данные, а не как поведение (И-051, §14 ур. 4)."""
    need(isinstance(answer, dict), 'answer', 'Ответ модели — объект JSON.')
    claims = answer.get('claims')
    need(isinstance(claims, list) and claims, 'answer',
         'В ответе нет утверждений: оценивать нечего.',
         {'expected': 'claims: [{id, state, text}]'})
    graded = []
    for item in claims:
        need(isinstance(item, dict) and isinstance(item.get('id'), str), 'answer',
             'Утверждение без идентификатора правила.', {'claim': item})
        ident = item['id']
        entry = records.get(ident)
        if entry is None or entry['kind'] == 'contract':
            graded.append({'id': ident, 'verdict': 'fail', 'why': 'unknown_rule',
                           'claimed': {'state': item.get('state'), 'text': item.get('text')},
                           'measured': None})
            continue
        measured = reader_state(records, entry, retired)
        claimed_state = item.get('state')
        claimed_text = item.get('text')
        row = {'id': ident, 'claimed': {'state': claimed_state, 'text': claimed_text},
               'measured': {'state': measured, 'title': entry['title'], 'scope': entry['scope']}}
        if claimed_state is not None and claimed_state != measured:
            row.update(verdict='fail', why='state_mismatch')
            graded.append(row)
            continue
        if claimed_text is not None and norm_text(claimed_text) != norm_text(entry.get('text')):
            row.update(verdict='fail', why='text_mismatch')
            graded.append(row)
            continue
        row.update(verdict='pass', why='same')
        graded.append(row)
    failed = [r for r in graded if r['verdict'] == 'fail']
    return {'answer': {'model': answer.get('model'), 'at': answer.get('at'), 'task': answer.get('task')},
            'claims': graded, 'counts': {'pass': len(graded) - len(failed), 'fail': len(failed)},
            'verdict': 'fail' if failed else 'pass',
            'checked_against': 'реестр и состояния: active, hidden, draft, suspended, revoked',
            'live': False, 'writes': False,
            'note': 'Модель не вызывалась и не будет: проверен записанный ответ. Уровень «модель прочитала» '
                    'остаётся not run, уровень «поведение проверяемо» измерен на записи.'}


def case_conflicts(root, paths):'''

EXACT_OLD = """    exact(payload, '', 'against' if command == 'metrics' else '')"""

EXACT_NEW = """    # 0.1.31: у verify своя форма — ответ модели (И-051, §14 ур. 4).
    if command == 'verify':
        need(isinstance(payload, dict), 'format', 'Ожидается объект JSON.')
    else:
        exact(payload, '', 'against' if command == 'metrics' else '')"""

MODEL_OLD = """    if command == 'rights':"""

MODEL_NEW = '''    if command == 'verify':
        # 0.1.31: ответ модели — данные, а не действие (И-051, §14 ур. 4).
        return grade_answer(recs, s['retired'], payload)
    if command == 'model':
        # 0.1.31: карточка живой части — что спрашивается и что уже записано (И-051, §14 ур. 4).
        exact(payload, '')
        folder = safe(root, MODELS.rstrip('/'))
        recorded = []
        if folder.is_dir():
            for path in sorted(folder.glob('*.json'))[:32]:
                if not path.is_file():
                    continue
                relpath = path.relative_to(root).as_posix()
                try:
                    graded = grade_answer(recs, s['retired'], parse(path.read_bytes()))
                    recorded.append({'path': relpath, 'bytes': path.stat().st_size,
                                     'model': graded['answer']['model'], 'task': graded['answer']['task'],
                                     'verdict': graded['verdict'], 'counts': graded['counts']})
                except (Refusal, OSError) as exc:
                    recorded.append({'path': relpath, 'bytes': path.stat().st_size,
                                     'verdict': 'unreadable', 'why': getattr(exc, 'code', 'io_or_data')})
        failed = [r for r in recorded if r['verdict'] != 'pass']
        return {'live': False, 'writes': False,
                'tasks': list(MODEL_TASKS),
                'answer': {'path': MODELS + '*.json',
                           'format': {'model': 'имя среды', 'at': 'время ответа', 'task': 'одна из tasks',
                                      'claims': '[{id, state, text}]'},
                           'who_writes': 'владелец: это его каталог, комплект сюда не пишет'},
                'recorded': recorded, 'count': len(recorded),
                'levels': {'3_read_by_model': 'not run',
                           '4_behavior_checked': 'not run' if not recorded else 'fail' if failed else 'pass',
                           '5_behavior_repeatable': 'not run'},
                'proven': {'live_call': False, 'answer_graded': bool(recorded)},
                'note': 'Комплект модель не вызывает: он проверяет записанный ответ. Число записей — '
                        'сколько ответов оценил, а не сколько раз модель работала.'}
    if command == 'rights':'''

RIGHTS_INPUTS_OLD = """        return {'reads': sorted([BASE + n for n in FILES] + [STATE, CHECKS, ENTRY, LOCAL + '**']),
                'files': measured,"""

RIGHTS_INPUTS_NEW = """        return {'reads': sorted([BASE + n for n in FILES] + [STATE, CHECKS, ENTRY, LOCAL + '**', MODELS + '**']),
                'inputs': {CHECKS: 'входящие журналы для операции merge',
                           MODELS + '*.json': 'записанные ответы модели для model и verify'},
                'files': measured,"""

READ_ONLY_OLD = """             'adapter', 'brief', 'identity', 'discovery', 'entry', 'session', 'metrics', 'due', 'rights',
             'system')"""

READ_ONLY_NEW = """             'adapter', 'brief', 'identity', 'discovery', 'entry', 'session', 'metrics', 'due', 'rights',
             'system', 'model', 'verify')"""

CLI_OLD = """    cli.add_argument('command', choices=('status', 'list', 'metrics', 'rights', 'system', 'history', 'removed', 'updates', 'pending', 'operations', 'inventory', 'adapter', 'brief', 'identity', 'discovery', 'entry', 'repeat', 'session', 'due', 'plan', 'apply'))"""

CLI_NEW = """    cli.add_argument('command', choices=('status', 'list', 'metrics', 'rights', 'system', 'model', 'verify', 'history', 'removed', 'updates', 'pending', 'operations', 'inventory', 'adapter', 'brief', 'identity', 'discovery', 'entry', 'repeat', 'session', 'due', 'plan', 'apply'))"""

STDIN_OLD = """        if args.command in ('session', 'plan', 'apply', 'adapter', 'discovery', 'entry', 'repeat', 'metrics'):"""

STDIN_NEW = """        if args.command in ('session', 'plan', 'apply', 'adapter', 'discovery', 'entry', 'repeat', 'metrics', 'verify'):"""

TEST_041 = r"""
    @case('X76', 'Ответ модели проверяется как данные: правило, состояние, текст.', '§14 ур. 4 (И-051).')
    def test_99_verify(self):
        self.install(); self.make()
        self.make('rule','P-1',scope='.',text='действует в проекте')
        rule=self.call('list')['active'][0]
        before=snapshot(self.a)
        ok=self.call('verify', dict(model='kilo', at='2026-11-18T10:00:00Z', task='explain',
                                    claims=[dict(id=rule['id'], state='active', text='действует   в проекте')]))
        self.assertEqual(before, snapshot(self.a))
        self.assertEqual(ok['verdict'],'pass')
        self.assertEqual(ok['live'],False)
        self.assertEqual(ok['writes'],False)
        self.assertEqual(ok['counts'],{'pass':1,'fail':0})
        self.assertEqual(ok['claims'][0]['why'],'same')
        bad=self.call('verify', dict(model='kilo', task='choose',
                                     claims=[dict(id=rule['id'], state='draft', text=rule['text']),
                                             dict(id=rule['id'], state='active', text='другое'),
                                             dict(id='P-999', state='active')]))
        self.assertEqual(bad['verdict'],'fail')
        self.assertEqual([c['why'] for c in bad['claims']],
                         ['state_mismatch','text_mismatch','unknown_rule'])
        self.assertEqual(bad['claims'][0]['measured']['state'],'active')
        self.assertRefused('answer', self.call, 'verify', dict(model='kilo'))
        self.assertRefused('answer', self.call, 'verify', dict(model='kilo', claims=[{'state':'active'}]))
        self.assertEqual(before, snapshot(self.a))

    @case('X77', 'Записанные ответы модели: карточка, оценка, список чтения.', '§14 ур. 4 (И-051).')
    def test_100_model(self):
        self.install(); self.make()
        self.make('rule','P-1',scope='.',text='действует в проекте')
        rule=self.call('list')['active'][0]
        card=self.call('model')
        self.assertEqual(card['live'],False)
        self.assertEqual(card['writes'],False)
        self.assertEqual(card['count'],0)
        self.assertEqual(card['levels']['4_behavior_checked'],'not run')
        self.assertEqual(card['answer']['path'],'.agent-contract/local/model/*.json')
        folder=self.a/'.agent-contract/local/model'
        folder.mkdir(parents=True)
        (folder/'good.json').write_text(json.dumps({'model':'kilo','at':'2026-11-18T10:00:00Z',
                                                     'task':'explain',
                                                     'claims':[{'id':rule['id'],'state':'active',
                                                                'text':rule['text']}]}), encoding='utf-8')
        (folder/'bad.json').write_text(json.dumps({'model':'copilot','task':'refuse',
                                                    'claims':[{'id':rule['id'],'state':'suspended'}]}),
                                       encoding='utf-8')
        before=snapshot(self.a)
        card=self.call('model')
        self.assertEqual(before, snapshot(self.a))
        self.assertEqual(card['count'],2)
        self.assertEqual([r['verdict'] for r in card['recorded']],['fail','pass'])
        self.assertEqual(card['levels']['4_behavior_checked'],'fail')
        rights=self.call('rights')
        self.assertIn('.agent-contract/local/model/**', rights['reads'])
        self.assertIn('.agent-contract/local/model/*.json', rights['inputs'])
        (folder/'bad.json').unlink()
        card=self.call('model')
        self.assertEqual(card['levels']['4_behavior_checked'],'pass')
        rep=self.call('repeat', dict(runs=2, requests=[dict(command='model'), dict(command='model')]))
        self.assertEqual(rep['identical'],True)
        self.assertEqual(rep['project_unchanged'],True)
"""

PROTOCOL_041 = """

## Живые модели (0.1.31)

Комплект модель не вызывает. Он делает ответ модели проверяемым:

- `model` (чтение, `writes: false`) — карточка: три задачи (`explain`, `choose`, `refuse`), формат
  записанного ответа, каталог `.agent-contract/local/model/*.json` (пишет владелец, не комплект),
  оценка каждой записи и уровни: `3_read_by_model` — `not run`, `4_behavior_checked` — измерен по записям,
  `5_behavior_repeatable` — `not run`. `live: false` сказано прямо, а не подразумевается.
- `verify` — оценка одного ответа как данных. Утверждение — `{id, state, text}`. Ответы:
  `same` (совпало), `state_mismatch` (названное состояние не равно измеренному; `hidden` — когда правило
  `active`, а контракт нет), `text_mismatch` (текст расходится по словам), `unknown_rule` (правила нет).
  Пустой ответ или утверждение без `id` — отказ `answer`.
- `model` и `verify` — чтения: `repeat` их принимает, файлы проекта не меняются.

Чего здесь нет: вызова модели, оценки качества рассуждения и переноса поведения на новый вопрос. Это
остаётся `not run` — и так и названо в ответе.
"""

README_041 = """
## Что изменилось в 0.1.31

Живые модели: `model` показывает, какие задачи ставятся модели, откуда берётся её записанный ответ и как
он оценён (`4_behavior_checked`), а `verify` проверяет один ответ как данные — по правилу, состоянию и
тексту, с отказами `state_mismatch`, `text_mismatch`, `unknown_rule` и `answer`. Комплект модель не
вызывает: `live: false`. Записанные ответы — вход владельца в `.agent-contract/local/model/`, а не запись
комплекта.
"""
