"""Правки выпуска 0.1.29 (И-049): права — кто читает и кто пишет.

§11 спрашивает, где границы проекта. До сих пор они держались устройством кода: комплект писал только в
закрытый список и читал только объявленные файлы, но сказать это словами было нечем, а чужая запись в
служебном каталоге проходила незамеченной — изменения шли дальше, будто ничего не случилось.

Что меняется:

1. **Команда `rights`** — чтение без записи (`writes: false`): `reads` (что комплект читает), `writes`
   (закрытый список, куда он пишет), `never` (чего не касается), `roles` (кто здесь писатель) и `foreign`
   (посторонние файлы в служебном каталоге).
2. **Посторонняя запись блокирует изменения.** Файл в `.agent-contract/`, которого комплект не создавал,
   даёт отказ `foreign` на `plan`/`apply` с перечнем. Чтение при этом работает: сначала надо понять, что
   это; восстановление (`restore`/`undo`) не блокируется — оно возвращает проект к известному состоянию.
3. **`status.foreign`** называет посторонние файлы при чтении, чтобы отказ не был первым упоминанием.
4. **`metrics` и `due` входят в список чтения** (`READ_ONLY`): они появились позже и в список не попали,
   поэтому `repeat` отказывал на них кодом `repeat_write`, хотя обе ничего не пишут.

Границы не расширяются: `TARGETS` тот же, схема та же, чтение по-прежнему не пишет.
"""

FOREIGN_OLD = """def repeat_reads(lab, project, root, runs, requests):"""

FOREIGN_NEW = '''def foreign_files(root):
    """0.1.29: файлы в служебном каталоге, которых комплект не создавал (И-049, §11)."""
    folder = PREFIX.rstrip('/')
    if not (Path(root) / folder).is_dir():
        return []
    base = safe(root, folder)
    # checks.incoming.json — объявленный вход операции merge: чужой по автору, но не посторонний.
    allowed = {BASE + n for n in FILES} | {STATE, CHECKS, PREFIX + 'project/checks.incoming.json'}
    found = []
    for dirpath, _dirnames, filenames in os.walk(base):
        for name in filenames:
            rel_path = (Path(dirpath) / name).relative_to(root).as_posix()
            if rel_path.startswith(LOCAL) or rel_path in allowed:
                continue
            found.append(rel_path)
    return sorted(found)


def guard_writes(root):
    """0.1.29: посторонняя запись останавливает изменения, а не притворяется своей (И-049)."""
    foreign = foreign_files(root)
    need(not foreign, 'foreign', 'В служебном каталоге есть посторонние записи: изменения остановлены.',
         {'foreign': foreign,
          'fix': 'уберите файлы или верните проект операцией restore, затем повторите'})


def repeat_reads(lab, project, root, runs, requests):'''

READ_ONLY_OLD = """READ_ONLY = ('status', 'list', 'history', 'removed', 'updates', 'pending', 'operations', 'inventory',
             'adapter', 'brief', 'identity', 'discovery', 'entry', 'session')"""

READ_ONLY_NEW = """# 0.1.29: metrics, due и rights — тоже чтение; они появились позже и в список не попали (И-049, F48).
READ_ONLY = ('status', 'list', 'history', 'removed', 'updates', 'pending', 'operations', 'inventory',
             'adapter', 'brief', 'identity', 'discovery', 'entry', 'session', 'metrics', 'due', 'rights')"""

PLAN_OLD = """    op = r['op']
    need(not pending(root), 'pending', 'Есть незавершённая операция. Сначала диагностика восстановления.')"""

PLAN_NEW = """    op = r['op']
    need(not pending(root), 'pending', 'Есть незавершённая операция. Сначала диагностика восстановления.')
    # 0.1.29: чужая запись в служебном каталоге — не повод продолжать (И-049, §11).
    guard_writes(root)"""

STATUS_OLD = """                'base_local_edits': [n for n in DATA if digest(files[n]) != m['files'][n]], 'conflicts': issues,"""

STATUS_NEW = """                'base_local_edits': [n for n in DATA if digest(files[n]) != m['files'][n]], 'conflicts': issues,
                'foreign': foreign_files(root),"""

RIGHTS_OLD = """    if command == 'list':"""

RIGHTS_NEW = """    if command == 'rights':
        # 0.1.29: границы доступа к проекту — кто читает и кто пишет (И-049, §11).
        exact(payload, '')
        foreign = foreign_files(root)
        return {'reads': sorted([BASE + n for n in FILES] + [STATE, CHECKS, ENTRY, LOCAL + '**']),
                'write_paths': sorted(TARGETS),
                'never': 'всё, что вне reads и writes: содержимое не читается, файлы не меняются',
                'roles': {'writer': 'комплект — единственный, кто пишет, и только в закрытый список write_paths',
                          'reader': 'любой процесс, у которого есть файл; комплект читателей не различает',
                          'foreign': 'чужая запись в служебном каталоге не читается и останавливает изменения'},
                'foreign': foreign,
                'blocks_writes': bool(foreign),
                'writes': False,
                'note': 'Права объявлены данными, а не подразумеваются устройством кода.'}
    if command == 'list':"""

CLI_OLD = """    cli.add_argument('command', choices=('status', 'list', 'metrics', 'history', 'removed', 'updates', 'pending', 'operations', 'inventory', 'adapter', 'brief', 'identity', 'discovery', 'entry', 'repeat', 'session', 'due', 'plan', 'apply'))"""

CLI_NEW = """    cli.add_argument('command', choices=('status', 'list', 'metrics', 'rights', 'history', 'removed', 'updates', 'pending', 'operations', 'inventory', 'adapter', 'brief', 'identity', 'discovery', 'entry', 'repeat', 'session', 'due', 'plan', 'apply'))"""

TEST_039 = r"""
    @case('X72', 'Права названы данными: что читается, что пишется, чего не касаемся.', '§11 (И-049).')
    def test_95_rights(self):
        self.install(); self.make()
        before=snapshot(self.a)
        view=self.call('rights')
        self.assertEqual(before, snapshot(self.a))
        self.assertEqual(view['writes'],False)
        self.assertEqual(view['foreign'],[])
        self.assertEqual(view['blocks_writes'],False)
        self.assertEqual(view['write_paths'], sorted(c.TARGETS))
        self.assertIn('.agent-contract/project/state.json', view['reads'])
        self.assertIn('AGENTS.md', view['reads'])
        self.assertIn('.agent-contract/local/**', view['reads'])
        self.assertIn('writer', view['roles'])
        rep=self.call('repeat', dict(runs=2, requests=[dict(command='metrics'), dict(command='due'),
                                                       dict(command='rights')]))
        self.assertEqual(rep['identical'],True)
        self.assertEqual(rep['project_unchanged'],True)
        self.assertEqual([r['command'] for r in rep['requests']],['metrics','due','rights'])

    @case('X73', 'Посторонняя запись останавливает изменения, но не чтение.', '§11 (И-049).')
    def test_96_foreign_write(self):
        self.install(); self.make()
        self.make('rule','P-1',scope='.',text='действует')
        extra=self.a/'.agent-contract/project/extra.json'
        extra.write_text('{"чужое": true}\n', encoding='utf-8')
        status=self.call('status')
        self.assertEqual(status['foreign'],['.agent-contract/project/extra.json'])
        self.assertEqual(len(self.call('list')['active']),1)
        rights=self.call('rights')
        self.assertEqual(rights['blocks_writes'],True)
        self.assertEqual(rights['foreign'],['.agent-contract/project/extra.json'])
        err=self.assertRefused('foreign', self.call, 'plan',
                               dict(op='create', kind='rule', contract='P-1', title='новое', scope='.',
                                    text='новое', basis='f', criterion='o', state='active', reason='ввод'))
        self.assertEqual(err.details['foreign'],['.agent-contract/project/extra.json'])
        journal_dir=self.a/'.agent-contract/local'
        self.assertTrue(journal_dir.is_dir())
        extra.unlink()
        self.assertEqual(self.call('rights')['foreign'],[])
        self.apply(dict(op='create', kind='rule', contract='P-1', title='новое', scope='.', text='новое',
                        basis='f', criterion='o', state='active', reason='ввод'))
        self.assertEqual(len(self.call('list')['active']),2)
        self.assertEqual(self.call('status')['foreign'],[])
"""

PROTOCOL_039 = """

## Права: кто читает и кто пишет (0.1.29)

Границы проекта объявлены данными, а не подразумеваются устройством кода.

- `rights` (чтение, `writes: false`) называет `reads` — что комплект читает (база, состояние, проверки,
  вход, журналы `local/**`), `writes` — закрытый список, куда он пишет, `never` — чего не касается,
  и `roles` — кто здесь писатель.
- `foreign` — файлы в `.agent-contract/`, которых комплект не создавал. Они не читаются и **останавливают
  изменения**: `plan` и `apply` отвечают отказом `foreign` с перечнем. Чтение при этом работает —
  сначала надо понять, что это.
- `restore` и `undo` не блокируются: восстановление возвращает проект к известному состоянию.
- `status.foreign` называет посторонние файлы при чтении, чтобы отказ не был первым упоминанием.
- `metrics`, `due` и `rights` входят в список чтения: `repeat` принимает их наравне с прочими чтениями.
"""

README_039 = """
## Что изменилось в 0.1.29

Права названы данными: команда `rights` перечисляет, что комплект читает, куда пишет и чего не касается,
а также `foreign` — посторонние файлы в служебном каталоге. Такая запись не читается и останавливает
изменения (отказ `foreign` на `plan`/`apply`), но не мешает чтению; `restore` и `undo` работают.
`metrics`, `due` и `rights` вошли в список чтения для `repeat`.
"""
