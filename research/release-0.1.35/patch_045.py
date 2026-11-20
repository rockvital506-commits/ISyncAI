"""Правки выпуска 0.1.35 (И-055): калибровка — промпты, ответ, эталон без значений.

До 0.1.35 владелец мог проверить комплект сам, но не мог проверить, **понимает** ли его агент тот же комплект:
порядок и права описаны, а вопроса с известным ответом нет.

Что меняется:

1. **`kit/calibration.json`** — четыре промпта K1–K4: шаги, ключи фактов ответа и **отпечатки** значений
   эталона (sha256 канонической формы). Самих значений в поставке нет: по отпечатку нельзя восстановить
   ответ, можно только сверить свой.
2. **`calibrate`** (чтение, `writes: false`): список промптов, карточка промпта, сравнение ответа с эталоном
   по отпечаткам (`match`, `fields`, `facts_digest`, `reason`, `next`) и отчёт.
3. **`calibrate_answer`** (`plan`/`apply`): ответ записывается в `.agent-contract/local/calibration/answers.json`
   **до** сравнения, с журналом. Второй ответ на тот же промпт — только если первый не сошёлся и по данным,
   и только один раз.
4. **`fix`** (`plan`/`apply`): закрытый список починок — `checks` (пересобрать `checks.json` в канонической
   форме) и `temp` (убрать свои временные файлы в `local/`). Всё остальное — `manual`, с названной причиной.
5. **`docs/КАЛИБРОВКА.md`** — тексты промптов и формат ответа.
6. **Отдельный архив** `AgentContractKit-Calibration-<вер>.zip` с `docs/ЭТАЛОНЫ-ПОСЛЕ.md`: прозаические
   эталоны, которые открывают после отправки своего ответа.

Схема не меняется; закрытый список путей записи становится на один пункт больше — ответ калибровки.
"""

CAL_OLD = """TARGETS = frozenset((ENTRY, STATE, CHECKS, *(BASE + n for n in FILES)))"""

CAL_NEW = """# 0.1.35: ответ калибровки пишется комплектом, поэтому он входит в закрытый список путей (И-055).
CAL = LOCAL + 'calibration/answers.json'
TARGETS = frozenset((ENTRY, STATE, CHECKS, CAL, *(BASE + n for n in FILES)))"""

HELPERS_OLD = """def tree_digest(root):"""

HELPERS_NEW = '''def canonical_facts(facts):
    """Каноническая форма фактов: ключи по возрастанию, UTF-8, без пробелов."""
    need(type(facts) is dict, 'answer', 'facts — объект ключ-значение.')
    for key, value in facts.items():
        need(type(key) is str and key != '', 'answer', 'Ключ факта — непустая строка.')
        need(value is None or isinstance(value, (str, bool, int, float)), 'answer',
             'Значение факта — строка, число, булево или null.', {'key': key})
    return json.dumps(facts, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def facts_digests(facts):
    """Отпечатки по полям: значение не хранится, сверяется только отпечаток."""
    return {key: hashlib.sha256(canonical_facts({key: value}).encode('utf-8')).hexdigest()
            for key, value in facts.items()}


def calibration_book(lab):
    path = Path(lab) / 'kit/calibration.json'
    need(path.is_file(), 'no_calibration', 'В поставке нет kit/calibration.json.')
    book = parse(path.read_bytes())
    need(book.get('schema_version') == 1, 'calibration', 'Неизвестная схема калибровки.')
    need([item.get('id') for item in book.get('prompts', [])] == ['K1', 'K2', 'K3', 'K4'], 'calibration',
         'Промпты калибровки — ровно K1…K4 по порядку.')
    return book


def answers_book(root):
    raw = read(Path(root), CAL)
    if raw is None:
        return {'schema_version': 1, 'answers': []}
    book = parse(raw)
    need(type(book.get('answers')) is list, 'answer', 'Файл ответов повреждён.')
    return book


def compare_answer(book, prompt, answer, attempts):
    need(type(answer) is dict, 'answer', 'Ответ — объект.')
    unknown = set(answer) - set('prompt system_version schema_version environment facts not_run manual verdict_self'.split())
    need(not unknown, 'answer', 'Лишние поля в ответе.', {'unknown': sorted(unknown)})
    need(answer.get('prompt') == prompt['id'], 'answer', 'В ответе другой промпт.', {'expected': prompt['id']})
    need(answer.get('schema_version') == book['schema_version'], 'answer', 'Схема ответа не совпадает.')
    facts = answer.get('facts')
    need(type(facts) is dict, 'answer', 'facts — объект.')
    known = {item['key'] for item in prompt['facts']}
    extra = sorted(set(facts) - known)
    missing = sorted(known - set(facts))
    fields = {}
    for item in prompt['facts']:
        key = item['key']
        if key in missing:
            fields[key] = 'missing'
        else:
            got = hashlib.sha256(canonical_facts({key: facts[key]}).encode('utf-8')).hexdigest()
            fields[key] = 'equal' if got == item['digest'] else 'mismatch'
    for key in extra:
        fields[key] = 'extra'
    matched = all(value == 'equal' for value in fields.values())
    reason = None
    if not matched:
        reason = 'data' if any(value in ('mismatch', 'missing') for value in fields.values()) else 'shape'
    not_run = answer.get('not_run') or []
    manual = answer.get('manual') or []
    need(type(not_run) is list and type(manual) is list, 'answer', 'not_run и manual — списки.')
    next_step = ('done' if matched else
                 'repeat' if reason == 'data' and attempts < 2 else 'manual')
    return {'prompt': prompt['id'], 'match': matched, 'fields': fields, 'reason': reason,
            'facts_digest': hashlib.sha256(canonical_facts(facts).encode('utf-8')).hexdigest(),
            'environment': answer.get('environment'), 'attempts': attempts, 'next': next_step,
            'not_run': not_run, 'manual': manual, 'writes': False,
            'verdict_note': 'Вердикт считается только по facts. Проза (not_run, manual) объясняет человеку, '
                            'но не влияет на match.'}


FIX_KINDS = ('checks', 'temp')


def fix_plan(root, kind):
    """Закрытый список безопасных починок (И-055, §3.5)."""
    need(kind in FIX_KINDS, 'fix_kind', 'Починка вне закрытого списка.', {'allowed': list(FIX_KINDS)})
    changes = {}
    if kind == 'checks':
        raw = read(Path(root), CHECKS)
        need(raw is not None, 'nothing', 'Файла журнала проверок нет.', {'manual': 'запустите install'})
        book = parse(raw)
        need(type(book.get('checks')) is list, 'nothing', 'Журнал проверок повреждён — это ручная работа.')
        fixed = encode(book)
        if fixed != raw:
            changes[CHECKS] = fixed
    if kind == 'temp':
        local = Path(root) / LOCAL
        if local.is_dir():
            for path in sorted(local.rglob('*')):
                if path.is_file() and (path.name.endswith('.tmp') or '.probe-' in path.name
                                       or path.name.startswith('.probe-')):
                    changes[path.relative_to(Path(root)).as_posix()] = None
    return changes


def tree_digest(root):'''

CALIBRATE_OLD = """    if command == 'repeat':"""

CALIBRATE_NEW = '''    if command == 'calibrate':
        # 0.1.35: промпт с известным ответом; значения эталона в поставке отсутствуют (И-055).
        book = calibration_book(lab)
        stored = answers_book(root)
        by_prompt = {}
        for record in stored['answers']:
            by_prompt[record['prompt']] = by_prompt.get(record['prompt'], []) + [record]
        if payload.get('report') is True:
            rows = []
            for prompt in book['prompts']:
                records = by_prompt.get(prompt['id'], [])
                rows.append({'prompt': prompt['id'], 'answered': bool(records),
                             'attempts': len(records),
                             'match': records[-1]['compare']['match'] if records else None,
                             'reason': records[-1]['compare']['reason'] if records else None,
                             'next': records[-1]['compare']['next'] if records else 'answer'})
            return {'report': rows, 'answered': sum(1 for r in rows if r['answered']),
                    'matched': sum(1 for r in rows if r['match'] is True),
                    'remaining_manual': sorted({m for record in stored['answers']
                                                for m in record['compare'].get('manual') or []}),
                    'fixes': list(FIX_KINDS),
                    'reference': 'прозаические эталоны — в отдельном архиве AgentContractKit-Calibration; '
                                 'в поставке только отпечатки, восстановить значение по ним нельзя',
                    'writes': False}
        if 'prompt' not in payload:
            exact(payload, '', 'prompt report')
            return {'prompts': [{'id': p['id'], 'title': p['title'], 'steps': len(p.get('steps') or []),
                                 'facts': [item['key'] for item in p['facts']],
                                 'answered': p['id'] in by_prompt} for p in book['prompts']],
                    'schema_version': book['schema_version'], 'system_version': book['system_version'],
                    'format': 'prompt system_version schema_version environment facts not_run manual verdict_self',
                    'note': 'Эталон хранится отпечатками: сводятся только ваши значения, не наоборот.',
                    'writes': False}
        exact(payload, 'prompt', 'prompt answer')
        prompt = next((p for p in book['prompts'] if p['id'] == payload['prompt']), None)
        need(prompt is not None, 'prompt', 'Неизвестный промпт.', {'known': [p['id'] for p in book['prompts']]})
        if 'answer' not in payload:
            return {'prompt': prompt['id'], 'title': prompt['title'], 'steps': prompt.get('steps') or [],
                    'facts': [{'key': item['key'], 'digest': item['digest']} for item in prompt['facts']],
                    'environment_expected': prompt.get('environment') or {},
                    'expect_not_run': prompt.get('not_run') or [], 'expect_manual': prompt.get('manual') or [],
                    'how': 'запустите шаги, соберите ответ в формате выше и запишите его через plan/apply '
                           'с op calibrate_answer; только после записи compare назовёт совпадение',
                    'writes': False}
        attempts = len(by_prompt.get(prompt['id'], []))
        return compare_answer(book, prompt, payload['answer'], attempts)

    if command == 'repeat':'''

OPS_OLD = """    else:
        raise Refusal('op', 'Операция не поддерживается.')"""

OPS_NEW = """    elif op == 'calibrate_answer':
        # 0.1.35: ответ пишется до сравнения, а повтор допускается один раз и только по данным (И-055).
        exact(r, 'op prompt answer', 'allow_repeat')
        book = calibration_book(lab)
        prompt = next((item for item in book['prompts'] if item['id'] == r['prompt']), None)
        need(prompt is not None, 'prompt', 'Неизвестный промпт.', {'known': [p['id'] for p in book['prompts']]})
        stored = answers_book(root)
        previous = [rec for rec in stored['answers'] if rec['prompt'] == prompt['id']]
        if previous:
            last = previous[-1]['compare']
            need(r.get('allow_repeat') is True, 'repeat_answer',
                 'Ответ на этот промпт уже записан. Повтор — только явным согласием.', {'match': last['match']})
            need(last['match'] is False and last['reason'] == 'data', 'repeat_answer',
                 'Повтор предлагается, только если ответ не сошёлся по данным.', {'reason': last['reason']})
            need(len(previous) < 2, 'repeat_answer', 'Повтор допускается один раз.')
        compare = compare_answer(book, prompt, r['answer'], len(previous))
        stored['answers'].append({'at': p.at, 'prompt': prompt['id'], 'answer': r['answer'], 'compare': compare})
        p.change(CAL, encode(stored))
        p.notes.append({'written_first': True, 'match': compare['match'], 'reason': compare['reason'],
                        'next': compare['next'],
                        'note': 'Ответ записан в local/calibration/answers.json до сравнения: подогнать '
                                'постфактум нельзя, запись останется в журнале.'})
    elif op == 'fix':
        exact(r, 'op kind')
        changes = fix_plan(root, r['kind'])
        removed = []
        for path, data in changes.items():
            if data is None:
                # Свои временные файлы: удаление без журнала — в журнал попадает только содержимое контракта.
                (Path(root) / path).unlink()
                removed.append(path)
            else:
                p.change(path, data)
        p.notes.append({'kind': r['kind'], 'closed_list': list(FIX_KINDS), 'removed': removed,
                        'manual': 'всё, что не в списке, остаётся человеку: база и правила не меняются'})
    else:
        raise Refusal('op', 'Операция не поддерживается.')"""

READ_ONLY_OLD = """             'system', 'model', 'verify', 'layout', 'access')"""

READ_ONLY_NEW = """             'system', 'model', 'verify', 'layout', 'access', 'calibrate')"""

CLI_OLD = """    cli.add_argument('command', choices=('status', 'list', 'metrics', 'rights', 'access', 'system', 'model', 'verify', 'layout', 'history', 'removed', 'updates', 'pending', 'operations', 'inventory', 'adapter', 'brief', 'identity', 'discovery', 'entry', 'repeat', 'session', 'due', 'plan', 'apply'))"""

CLI_NEW = """    cli.add_argument('command', choices=('status', 'list', 'metrics', 'rights', 'access', 'system', 'model', 'verify', 'layout', 'calibrate', 'history', 'removed', 'updates', 'pending', 'operations', 'inventory', 'adapter', 'brief', 'identity', 'discovery', 'entry', 'repeat', 'session', 'due', 'plan', 'apply'))"""

RIGHTS_NOTE_OLD = """                'note': 'Права объявлены данными, а не подразумеваются устройством кода. Объявление — не факт: '
                        'что запись действительно возможна, измеряет команда access.'}"""

RIGHTS_NOTE_NEW = """                'note': 'Права объявлены данными, а не подразумеваются устройством кода. Объявление — не факт: '
                        'что запись действительно возможна, измеряет команда access. Путей записи десять: '
                        'с 0.1.35 в список входит ответ калибровки (local/calibration/answers.json).'}"""


ENV_EXPECTED = {'os': 'posix или nt — как в system', 'case_insensitive': 'как в system',
                'layout': 'как в layout.relation'}

PROMPTS = [
    {'id': 'K1', 'title': 'Что установлено',
     'task': 'Установите выпуск, войдите и опишите, что теперь есть в проекте.',
     'steps': ['layout — назвать раскладку', 'plan/apply op: install', 'plan/apply op: connect', 'status'],
     'facts': [
         {'key': 'status.health', 'command': 'status', 'payload': None, 'path': ['health']},
         {'key': 'status.entry_mode', 'command': 'status', 'payload': None, 'path': ['entry_mode']},
         {'key': 'layout.installed', 'command': 'layout', 'payload': None, 'path': ['installed']},
         {'key': 'layout.supported', 'command': 'layout', 'payload': None, 'path': ['supported']},
     ],
     'not_run': ['живая среда VS Code', 'поведение модели'],
     'manual': ['проверить, что ваш редактор видит AGENTS.md']},
    {'id': 'K2', 'title': 'Права и границы',
     'task': 'Измерьте права и назовите, куда комплект пишет и куда нет.',
     'steps': ['access — девять… десять путей', 'rights — объявленный список'],
     'facts': [
         {'key': 'access.measured', 'command': 'access', 'payload': None, 'path': ['measured']},
         {'key': 'access.writes', 'command': 'access', 'payload': None, 'path': ['writes']},
         {'key': 'rights.writes', 'command': 'rights', 'payload': None, 'path': ['writes']},
         {'key': 'access.all_writable', 'command': 'access', 'payload': None, 'path': ['all_writable']},
         {'key': 'rights.blocks_writes', 'command': 'rights', 'payload': None, 'path': ['blocks_writes']},
     ],
     'not_run': ['ACL и NTFS'],
     'manual': ['проверить права своего каталога, если writable false']},
    {'id': 'K3', 'title': 'Модели и обнаружение',
     'task': 'Скажите, что комплект измеряет про модель и что — про обнаружение.',
     'steps': ['model', 'discovery {"environment": "kilo"}'],
     'facts': [
         {'key': 'model.live', 'command': 'model', 'payload': None, 'path': ['live']},
         {'key': 'model.count', 'command': 'model', 'payload': None, 'path': ['count']},
         {'key': 'discovery.contents_read', 'command': 'discovery', 'payload': {'environment': 'kilo'},
          'path': ['contents_read']},
         {'key': 'discovery.discovery_proven', 'command': 'discovery', 'payload': {'environment': 'kilo'},
          'path': ['discovery_proven']},
         {'key': 'discovery.chosen', 'command': 'discovery', 'payload': {'environment': 'kilo'},
          'path': ['chosen']},
     ],
     'not_run': ['чтение правил моделью'],
     'manual': ['объяснить, чем обнаружение отличается от чтения']},
    {'id': 'K4', 'title': 'Поддержка и версия',
     'task': 'Назовите установленную версию и что вы знаете о журнале и обновлениях.',
     'steps': ['updates', 'metrics'],
     'facts': [
         {'key': 'updates.installed_version', 'command': 'updates', 'payload': None, 'path': ['installed_version']},
         {'key': 'updates.network', 'command': 'updates', 'payload': None, 'path': ['network']},
         {'key': 'metrics.entries.total', 'command': 'metrics', 'payload': None, 'path': ['entries', 'total']},
         {'key': 'metrics.active.count', 'command': 'metrics', 'payload': None, 'path': ['active', 'count']},
     ],
     'not_run': ['живая среда'],
     'manual': ['назвать, что значит «обновлять пока нечего»']},
]

REFERENCE = {
    'K1': {'status.health': 'valid', 'status.entry_mode': 'owned',
           'layout.installed': True, 'layout.supported': True},
    'K2': {'access.measured': True, 'access.writes': False, 'rights.writes': False,
           'access.all_writable': True, 'rights.blocks_writes': False},
    'K3': {'model.live': False, 'model.count': 0, 'discovery.contents_read': False,
           'discovery.discovery_proven': False, 'discovery.chosen': 'AGENTS.md'},
    'K4': {'updates.installed_version': '{{version}}', 'updates.network': False,
           'metrics.entries.total': 0, 'metrics.active.count': 0},
}

REFERENCE_PROSE = {
    'K1': 'После установки и входа проект здоров (status.health = valid), вход принадлежит комплекту '
          '(entry_mode = owned), выпуск установлен (layout.installed = true), раскладка поддерживается '
          '(layout.supported = true). Ответ «здоров» без проверки status — не калибровка: это пересказ.',
    'K2': 'Права измерены записью (access.measured = true), комплект при этом ничего не записал '
          '(access.writes = false и rights.writes = false), все десять путей доступны на запись '
          '(access.all_writable = true), посторонней записи нет (rights.blocks_writes = false).',
    'K3': 'Комплект модель не вызывает (model.live = false) и ответов пока не оценено (model.count = 0). '
          'Обнаружение названо порядком, а не проверкой: содержимое не читалось (discovery.contents_read = false), '
          'обнаружение не доказано (discovery.discovery_proven = false), выбран AGENTS.md (discovery.chosen).',
    'K4': 'Установлена версия выпуска (updates.installed_version = {{version}}), сеть не используется '
          '(updates.network = false), в журнале проверок ноль записей (metrics.entries.total = 0) и ноль '
          'действующих правил (metrics.active.count = 0) — в чистом проекте это правильный ответ, а не ошибка.',
}

TEST_045 = r"""
    @case('X84', 'Калибровка: четыре промпта, эталон только отпечатками.', '§4 п. 8–9 (И-055).')
    def test_107_calibration_book(self):
        book=c.parse((KIT/'calibration.json').read_bytes())
        self.assertEqual(book['schema_version'],1)
        self.assertEqual(book['system_version'],c.VERSION)
        self.assertEqual([p['id'] for p in book['prompts']],['K1','K2','K3','K4'])
        for prompt in book['prompts']:
            self.assertTrue(prompt['title'] and prompt['steps'] and prompt['facts'],prompt['id'])
            for item in prompt['facts']:
                self.assertEqual(sorted(item),['command','digest','key','path','payload'],item['key'])
                self.assertRegex(item['digest'],r'\A[0-9a-f]{64}\Z')
                self.assertNotIn('value',item)
        listing=self.call('calibrate')
        self.assertEqual([p['id'] for p in listing['prompts']],['K1','K2','K3','K4'])
        self.assertEqual(listing['writes'],False)
        card=self.call('calibrate',dict(prompt='K3'))
        self.assertEqual(card['prompt'],'K3')
        self.assertTrue(card['steps'])
        self.assertIn('digest',card['facts'][0])
        self.assertNotIn('value',card['facts'][0])

    @case('X85', 'Калибровка: ответ пишется до сравнения, повтор — по правилу.', '§4 п. 8–9 (И-055).')
    def test_108_calibrate(self):
        self.install(); self.apply(dict(op='connect'))
        good=dict(prompt='K1', system_version=c.VERSION, schema_version=1,
                  environment=dict(os='posix', case_insensitive=False),
                  facts={'status.health':'valid','status.entry_mode':'owned',
                         'layout.installed':True,'layout.supported':True},
                  not_run=[{'what':'живая среда VS Code','why':'расширения не запускаются'}],
                  manual=[], verdict_self='checkable')
        out=self.apply(dict(op='calibrate_answer', prompt='K1', answer=good))
        self.assertEqual(out['outcome'],'committed')
        stored=c.parse((self.a/'.agent-contract/local/calibration/answers.json').read_bytes())
        self.assertEqual(len(stored['answers']),1)
        self.assertTrue(stored['answers'][0]['compare']['match'])
        view=self.call('calibrate',dict(prompt='K1', answer=good))
        self.assertTrue(view['match'])
        self.assertEqual(view['next'],'done')
        self.assertEqual(view['writes'],False)
        self.assertEqual(sorted(view['fields'].values()),['equal']*4)
        report=self.call('calibrate',dict(report=True))
        self.assertEqual(report['answered'],1)
        self.assertEqual(report['matched'],1)
        with self.assertRaises(c.Refusal) as ctx:
            self.preview(dict(op='calibrate_answer', prompt='K1', answer=good))
        self.assertEqual(ctx.exception.code,'repeat_answer')
        bad=dict(good, prompt='K2',
                 facts={'access.measured':True,'access.writes':False,'rights.writes':False,
                        'access.all_writable':False,'rights.blocks_writes':False})
        self.apply(dict(op='calibrate_answer', prompt='K2', answer=bad))
        seen=self.call('calibrate',dict(prompt='K2', answer=bad))
        self.assertFalse(seen['match'])
        self.assertEqual(seen['reason'],'data')
        self.assertEqual(seen['fields']['access.all_writable'],'mismatch')
        self.assertEqual(seen['next'],'repeat')
        right=dict(bad, facts=dict(bad['facts'], **{'access.all_writable':True}))
        self.apply(dict(op='calibrate_answer', prompt='K2', answer=right, allow_repeat=True))
        self.assertTrue(self.call('calibrate',dict(prompt='K2', answer=right))['match'])
        with self.assertRaises(c.Refusal) as ctx2:
            self.apply(dict(op='calibrate_answer', prompt='K2', answer=right, allow_repeat=True))
        self.assertEqual(ctx2.exception.code,'repeat_answer')

    @case('X86', 'Починка: только закрытый список, остальное — человеку.', '§4 п. 8–9 (И-055).')
    def test_109_fix(self):
        self.install()
        checks=self.a/'.agent-contract/project/checks.json'
        good=checks.read_bytes()
        checks.write_text(json.dumps(json.loads(good), indent=4), encoding='utf-8')
        self.assertNotEqual(checks.read_bytes(),good)
        self.apply(dict(op='fix', kind='checks'))
        self.assertEqual(checks.read_bytes(), c.encode(c.parse(good)))
        local=self.a/'.agent-contract/local/calibration'
        local.mkdir(parents=True, exist_ok=True)
        (local/'probe.tmp').write_text('мусор',encoding='utf-8')
        (local/'.probe-1').write_text('мусор',encoding='utf-8')
        (local/'answers.json').write_text('{"schema_version": 1, "answers": []}\n',encoding='utf-8')
        self.apply(dict(op='fix', kind='temp'))
        self.assertFalse((local/'probe.tmp').exists())
        self.assertFalse((local/'.probe-1').exists())
        self.assertTrue((local/'answers.json').exists())
        with self.assertRaises(c.Refusal) as ctx:
            self.preview(dict(op='fix', kind='base'))
        self.assertEqual(ctx.exception.code,'fix_kind')
"""

PROTOCOL_045 = """

## Калибровка: промпт с известным ответом (0.1.35)

Комплект можно проверить самому. Калибровка проверяет другое: понимает ли агент тот же комплект так же.
Четыре промпта — `K1` установка, `K2` права, `K3` модели и обнаружение, `K4` версия и журнал.

Порядок:

1. `calibrate` — список промптов; `calibrate {"prompt": "K1"}` — карточка: шаги, ключи фактов, отпечатки.
2. Владелец выполняет шаги и собирает ответ: `prompt`, `system_version`, `schema_version`, `environment`,
   `facts`, `not_run`, `manual`, `verdict_self`.
3. Ответ **записывается** через `plan`/`apply` с `op: calibrate_answer` — в `local/calibration/answers.json`,
   с журналом и **до** сравнения. Подогнать ответ после сравнения нельзя: запись уже в журнале.
4. Сравнение — `calibrate {"prompt": "K1", "answer": {…}}`: `match`, `fields` (`equal`, `mismatch`, `missing`,
   `extra`), `facts_digest`, `reason`, `next`.

Правила:

- **Вердикт только по `facts`.** Каноническая форма: ключи по возрастанию, UTF-8, без пробелов, значения —
  строка, число, булево или `null`. Проза (`not_run`, `manual`) объясняет человеку и на `match` не влияет.
- **Эталон хранится отпечатками.** В `kit/calibration.json` — только `sha256` канонической формы поля.
  По отпечатку значение не восстановить; сверить свой ответ — можно.
- **Повтор — один раз и только по данным.** Если `match: false` и `reason: data`, повтор разрешён явным
  `allow_repeat: true`, не более одного раза на промпт.
- **Прозаические эталоны — в отдельном архиве** `AgentContractKit-Calibration-<версия>.zip`
  (`docs/ЭТАЛОНЫ-ПОСЛЕ.md`). Их открывают после отправки своего ответа, а не до.

Починка (`op: fix`) — закрытый список: `checks` (пересобрать `checks.json` в канонической форме) и `temp`
(убрать свои временные файлы в `local/`). Всё остальное — `manual`; база и правила починкой не меняются.
"""

README_045 = """
## Что изменилось в 0.1.35

Появилась калибровка — четыре промпта с известным ответом (`K1` установка, `K2` права, `K3` модели
и обнаружение, `K4` версия и журнал). Ответ собирается по шагам, **записывается** в
`.agent-contract/local/calibration/answers.json` до сравнения и сверяется по отпечаткам: в поставке лежат
только `sha256` полей эталона, значений нет. Прозаические эталоны — в отдельном архиве
`AgentContractKit-Calibration-<версия>.zip`, их открывают после отправки своего ответа.
"""

CALIBRATION_DOC = '''# Калибровка: четыре промпта

Ответы на эти промпты проверяют не память, а понимание: что установлено, куда комплект пишет, что он
измеряет про модель и что знает о версии и журнале.

## Как отвечать

1. `python3 kit/tools/contract.py --lab . --project <проект> calibrate` — список промптов.
2. `... calibrate` с `{"prompt": "K1"}` — шаги и ключи фактов (значений эталона в поставке нет).
3. Выполнить шаги, собрать ответ:

```json
{
  "prompt": "K1",
  "system_version": "0.1.35",
  "schema_version": 1,
  "environment": {"os": "posix", "case_insensitive": false, "layout": "lab_inside_project"},
  "facts": {"status.health": "valid", "status.entry_mode": "owned",
            "layout.installed": true, "layout.supported": true},
  "not_run": [{"what": "живая среда VS Code", "why": "расширения не запускаются"}],
  "manual": [],
  "verdict_self": "checkable"
}
```

4. Записать ответ: `plan`/`apply` с `{"op": "calibrate_answer", "prompt": "K1", "answer": {…}}`.
5. Сверить: `calibrate` с `{"prompt": "K1", "answer": {…}}` — `match`, `fields`, `reason`, `next`.

## Промпты

### K1. Что установлено

Установите выпуск, войдите и опишите, что теперь есть в проекте. Факты: `status.health`,
`status.entry_mode`, `layout.installed`, `layout.supported`.

### K2. Права и границы

Измерьте права и назовите, куда комплект пишет и куда нет. Факты: `access.measured`, `access.writes`,
`rights.writes`, `access.all_writable`, `rights.blocks_writes`.

### K3. Модели и обнаружение

Скажите, что комплект измеряет про модель и что — про обнаружение. Факты: `model.live`, `model.count`,
`discovery.contents_read`, `discovery.discovery_proven`, `discovery.chosen`.

### K4. Поддержка и версия

Назовите установленную версию и что вы знаете о журнале и обновлениях. Факты: `updates.installed_version`,
`updates.network`, `metrics.entries.total`, `metrics.active.count`.

## Чего здесь нет

- Значений эталона. Только отпечатки: сверить можно, подсмотреть нельзя.
- Оценки рассуждения. Проверяются факты, которые агент утверждает, а не качество его объяснений.
- Автоматических прогонов. Калибровка запускается владельцем.

## Эталоны

Прозаические эталоны с объяснением, почему ответ именно такой, лежат в отдельном архиве
`AgentContractKit-Calibration-<версия>.zip` (`docs/ЭТАЛОНЫ-ПОСЛЕ.md`). Открывайте их после отправки
своего ответа: иначе проверяете не себя.
'''

TEST_FIX_OLD = """        self.assertEqual(len(view['paths']),9)"""

TEST_FIX_NEW = """        self.assertEqual(len(view['paths']),10)"""


ACCESS_FIX_OLD = """            folder = (Path(root) / path).parent
            if not folder.is_dir():
                paths[path] = {'writable': False, 'reason': 'no_directory', 'errno': None}
                continue
            probe = folder / ('.agent-contract-probe-' + uuid.uuid4().hex[:12])"""

ACCESS_FIX_NEW = """            folder = (Path(root) / path).parent
            pending_dir = None
            probe_dir = folder
            while not probe_dir.is_dir() and probe_dir != probe_dir.parent:
                pending_dir = probe_dir
                probe_dir = probe_dir.parent
            if not probe_dir.is_dir():
                paths[path] = {'writable': False, 'reason': 'no_directory', 'errno': None, 'dir': None}
                continue
            # 0.1.35: каталога может ещё не быть — тогда мерим ближайший существующий и говорим об этом (И-055).
            extra = {'dir': None if pending_dir is None else pending_dir.relative_to(root).as_posix() + '/'}
            probe = probe_dir / ('.agent-contract-probe-' + uuid.uuid4().hex[:12])"""

ACCESS_FIX2_OLD = """                paths[path] = {'writable': False, 'reason': reason, 'errno': exc.errno}
            else:
                paths[path] = {'writable': True, 'reason': None, 'errno': None}"""

ACCESS_FIX2_NEW = """                paths[path] = dict({'writable': False, 'reason': reason, 'errno': exc.errno}, **extra)
            else:
                paths[path] = dict({'writable': True, 'reason': None, 'errno': None}, **extra)"""

BOUNDARY_OLD = """        need(path in TARGETS, 'boundary', 'Запись не входит в закрытый список.')"""

BOUNDARY_NEW = """        # 0.1.35: починка убирает свои же временные файлы в local/ — только удаление, не запись (И-055).
        need(path in TARGETS or (path.startswith(LOCAL) and data is None), 'boundary',
             'Запись не входит в закрытый список.')"""


SETUP_OLD = """                (root/name).write_bytes((KIT/'base'/name).read_bytes())"""

SETUP_NEW = """                (root/name).write_bytes((KIT/'base'/name).read_bytes())
        # 0.1.35: лаборатория испытаний повторяет поставку — книга калибровки тоже копируется (И-055).
        if (KIT/'calibration.json').is_file():
            (self.lab/'kit/calibration.json').write_bytes((KIT/'calibration.json').read_bytes())"""


STDIN_OLD = """        if args.command in ('session', 'plan', 'apply', 'adapter', 'discovery', 'entry', 'repeat', 'metrics', 'verify'):"""

STDIN_NEW = """        if args.command in ('session', 'plan', 'apply', 'adapter', 'discovery', 'entry', 'repeat', 'metrics',
                            'verify', 'calibrate'):"""
