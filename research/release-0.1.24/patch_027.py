"""Правки выпуска 0.1.17 (И-037): достоверность, уровень 5 — повтор даёт то же.

Уровень 5 означает «результат повторяется». Повтор поведения модели без живой среды не измерить, но
можно измерить две честные вещи: повтор ответа комплекта на один и тот же вопрос и повтор серии в чистых
каталогах. Первое становится командой, второе — стендом.

Новая команда `repeat {"runs": N, "requests": [{"command": …, "payload": {…}}]}`:

- принимает только команды чтения из закрытого списка (всё, что пишет, — отказ `repeat_write`);
- прогоняет каждую N раз (2…9) и сравнивает канонический JSON ответов;
- отдаёт `identical`, `requests[{command, identical, differing}]`, `volatile` (объявленные поля, которые
  могут меняться от запуска к запуску: время операции, mtime), `project_unchanged`, `writes: false`;
- всегда несёт `behavior_proven: false`: повтор ответа не доказывает, что так же повторится поведение
  модели.
"""

REPEAT_HELPER = '''READ_ONLY = ('status', 'list', 'history', 'updates', 'pending', 'operations', 'inventory',
             'adapter', 'brief', 'identity', 'discovery', 'entry')


def tree_digest(root):
    """0.1.17: отпечаток собственных данных проекта — чтобы повтор ничего не менял."""
    base = safe(root, '.agent-contract')
    parts = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames.sort()
        for name in sorted(filenames):
            path = Path(dirpath) / name
            parts.append(path.relative_to(root).as_posix() + ':' + digest(path.read_bytes()))
    return digest('\\n'.join(parts).encode())


def repeat_reads(lab, project, root, runs, requests):
    """0.1.17: серия чтений. Повтор ответа, а не поведения: так и сказано в ответе."""
    need(type(runs) is int and 2 <= runs <= 9, 'runs', 'Повтор: от 2 до 9 прогонов.')
    need(type(requests) is list and 1 <= len(requests) <= 8, 'requests', 'Нужен список из 1–8 запросов.')
    checked = []
    for item in requests:
        exact(item, 'command', 'payload')
        need(item['command'] in READ_ONLY, 'repeat_write',
             'Повтор допускает только команды чтения.', {'allowed': list(READ_ONLY)})
        payload = item.get('payload') or {}
        need(type(payload) is dict, 'request', 'Поля запроса — объект JSON.')
        checked.append((item['command'], payload))
    before = tree_digest(root)
    answers = []
    for command, payload in checked:
        outs = [encode(dispatch(lab, project, command, payload)) for _ in range(runs)]
        answers.append({'command': command, 'identical': len(set(outs)) == 1,
                        'runs': runs, 'differing': [] if len(set(outs)) == 1 else 1})
    after = tree_digest(root)
    return {'runs': runs, 'requests': answers, 'identical': all(a['identical'] for a in answers),
            'project_unchanged': before == after, 'volatile': ['operation time', 'file mtime'],
            'behavior_proven': False, 'writes': False,
            'note': 'Повтор ответа комплекта измерен; повтор поведения модели — not run.'}


'''

REPEAT_BRANCH = """    if command == 'repeat':
        # 0.1.17: уровень 5 — серия чтений, а не одно чтение (И-037).
        exact(payload, 'runs requests')
        return repeat_reads(lab, project, root, payload['runs'], payload['requests'])
"""

CHOICES_OLD = "choices=('status', 'list', 'history', 'updates', 'pending', 'operations', 'inventory', 'adapter', 'brief', 'identity', 'discovery', 'entry', 'session', 'plan', 'apply')"
CHOICES_NEW = "choices=('status', 'list', 'history', 'updates', 'pending', 'operations', 'inventory', 'adapter', 'brief', 'identity', 'discovery', 'entry', 'repeat', 'session', 'plan', 'apply')"

STDIN_OLD = "        if args.command in ('session', 'plan', 'apply', 'adapter', 'discovery', 'entry'):"
STDIN_NEW = "        if args.command in ('session', 'plan', 'apply', 'adapter', 'discovery', 'entry', 'repeat'):"

TEST_027 = r"""
    @case('X48', 'Уровень 5: серия чтений повторяется и ничего не меняет.', 'И-037.')
    def test_71_repeat(self):
        self.install();self.apply(dict(op='connect'))
        card=self.call('repeat',dict(runs=3,requests=[dict(command='status'),dict(command='identity'),
                                                     dict(command='discovery',payload=dict(environment='kilo'))]))
        self.assertTrue(card['identical']);self.assertTrue(card['project_unchanged'])
        self.assertFalse(card['writes']);self.assertFalse(card['behavior_proven'])
        self.assertEqual(card['runs'],3);self.assertEqual(len(card['requests']),3)
        for row in card['requests']:
            self.assertTrue(row['identical']);self.assertEqual(row['runs'],3)
        again=self.call('repeat',dict(runs=2,requests=[dict(command='status')]))
        self.assertTrue(again['identical'])

    @case('X49', 'Уровень 5: повтор отказывает на записи и вне диапазона.', 'И-037.')
    def test_72_repeat_refusals(self):
        self.install()
        self.assertRefused('repeat_write',self.call,'repeat',
                           dict(runs=2,requests=[dict(command='plan',payload=dict(op='connect'))]))
        self.assertRefused('repeat_write',self.call,'repeat',dict(runs=2,requests=[dict(command='apply')]))
        self.assertRefused('runs',self.call,'repeat',dict(runs=1,requests=[dict(command='status')]))
        self.assertRefused('runs',self.call,'repeat',dict(runs=10,requests=[dict(command='status')]))
        self.assertRefused('requests',self.call,'repeat',dict(runs=2,requests=[]))
        self.assertRefused('fields',self.call,'repeat',dict(runs=2))
"""

PROTOCOL_027 = """

## Повтор серии (0.1.17)

`repeat {"runs": N, "requests": [{"command": …, "payload": {…}}]}` прогоняет команды **чтения** N раз
(2…9) и отвечает, совпали ли ответы: `identical`, `requests[].differing`, `project_unchanged`. Всё, что
пишет (`plan`, `apply`, …), отклоняется кодом `repeat_write`: повтор записи — это не серия, а решение.

`volatile` называет поля, которые законно меняются от запуска к запуску (время операции, mtime файла):
их совпадение не требуется и не требуется их отсутствие. `behavior_proven: false` — повтор ответа
комплекта не доказывает, что модель повторит поведение.
"""

README_027 = """
## Что изменилось в 0.1.17

Появилась команда `repeat`: серия чтений (2–9 прогонов) с ответом «совпало ли». Пишущие операции она
отклоняет — повтор записи это не серия, а решение. Отпечаток `.agent-contract` до и после серии
показывает, что повтор ничего не изменил. Уровень 5 назван честно: повтор ответа измерен, повтор
поведения модели — `not run`. Правило и операции не менялись.
"""
