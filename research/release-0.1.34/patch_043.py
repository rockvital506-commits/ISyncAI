"""Правки выпуска 0.1.33 (И-053): права измеряются, а не объявляются.

`rights` с 0.1.29 называет закрытый список путей записи — девять путей. Но назвать путь и получить право
писать в него — разные вещи: каталог может быть только для чтения, диск — смонтирован ro, файл — занят.
Раньше комплект об этом молчал: он писал и падал, если не мог.

Что меняется:

1. **Команда `access`** (чтение, `writes: false`): для каждого из девяти путей в каталоге самого пути
   создаётся собственный временный файл `.agent-contract-probe-…`, файл проверяется и удаляется в той же
   операции. Ответ — `{path: {writable, reason, errno}}`, `measured: true`, `all_writable`, `left`
   (что не удалось убрать — пусто в норме) и `note`: права ОС комплект не выдаёт, он их измеряет.
2. **Права ссылаются на измерение:** в ответе `rights` появляется строка о том, что `write_paths` —
   объявление, а факт даёт `access`.
3. **Список чтения и консоль:** `access` — чтение; `repeat` его принимает.
4. **Справочник и README:** раздел о том, что право — это факт, а не обещание, и что делать при `writable: false`.

Схема не меняется; закрытый список путей тот же.
"""

ACCESS_OLD = """    if command == 'layout':"""

ACCESS_NEW = '''    if command == 'access':
        # 0.1.33: право — это факт, а не обещание: измеряем записью в каталоге самого пути (И-053, §4 п. 8–9).
        exact(payload, '')
        paths = {}
        left = []
        for path in sorted(TARGETS):
            folder = (Path(root) / path).parent
            if not folder.is_dir():
                paths[path] = {'writable': False, 'reason': 'no_directory', 'errno': None}
                continue
            probe = folder / ('.agent-contract-probe-' + uuid.uuid4().hex[:12])
            try:
                with open(probe, 'w', encoding='utf-8') as handle:
                    handle.write('probe\\n')
                    handle.flush()
                    os.fsync(handle.fileno())
            except OSError as exc:
                reason = 'permission' if exc.errno in (errno.EACCES, errno.EPERM, errno.EROFS) else 'io'
                paths[path] = {'writable': False, 'reason': reason, 'errno': exc.errno}
            else:
                paths[path] = {'writable': True, 'reason': None, 'errno': None}
            finally:
                with contextlib.suppress(OSError):
                    probe.unlink()
            if probe.exists():
                left.append(probe.relative_to(root).as_posix())
        return {'paths': paths, 'measured': True, 'writes': False, 'left': left,
                'all_writable': all(item['writable'] for item in paths.values()),
                'probe': 'в каталоге самого пути: файл .agent-contract-probe-… создаётся, проверяется и удаляется '
                         'в той же операции; данные проекта не читаются и не меняются',
                'note': 'Права ОС комплект не выдаёт; он их измеряет. Ответ — факт на момент вызова, а не обещание: '
                        'право может измениться сразу после него.'}
    if command == 'layout':'''

RIGHTS_NOTE_OLD = """                'note': 'Права объявлены данными, а не подразумеваются устройством кода.'}"""

RIGHTS_NOTE_NEW = """                'note': 'Права объявлены данными, а не подразумеваются устройством кода. Объявление — не факт: '
                        'что запись действительно возможна, измеряет команда access.'}"""

READ_ONLY_OLD = """             'system', 'model', 'verify', 'layout')"""

READ_ONLY_NEW = """             'system', 'model', 'verify', 'layout', 'access')"""

CLI_OLD = """    cli.add_argument('command', choices=('status', 'list', 'metrics', 'rights', 'system', 'model', 'verify', 'layout', 'history', 'removed', 'updates', 'pending', 'operations', 'inventory', 'adapter', 'brief', 'identity', 'discovery', 'entry', 'repeat', 'session', 'due', 'plan', 'apply'))"""

CLI_NEW = """    cli.add_argument('command', choices=('status', 'list', 'metrics', 'rights', 'access', 'system', 'model', 'verify', 'layout', 'history', 'removed', 'updates', 'pending', 'operations', 'inventory', 'adapter', 'brief', 'identity', 'discovery', 'entry', 'repeat', 'session', 'due', 'plan', 'apply'))"""

IMPORT_OLD = """import difflib
import hashlib"""

IMPORT_NEW = """import difflib
import errno
import hashlib"""

TEST_IMPORT_OLD = """import platform
import subprocess"""

TEST_IMPORT_NEW = """import platform
import stat
import subprocess"""

TEST_043 = r"""
    @case('X80', 'Права измерены: девять путей, после вызова ничего не осталось.', '§4 п. 8–9 (И-053).')
    def test_103_access(self):
        self.install(); self.make()
        before=snapshot(self.a)
        view=self.call('access')
        self.assertEqual(before, snapshot(self.a))
        self.assertEqual(view['writes'],False)
        self.assertEqual(view['measured'],True)
        self.assertEqual(len(view['paths']),9)
        self.assertIn('AGENTS.md', view['paths'])
        self.assertIn('.agent-contract/project/state.json', view['paths'])
        self.assertEqual(view['all_writable'],True)
        self.assertEqual(view['left'],[])
        for path, item in view['paths'].items():
            self.assertEqual(item['writable'],True,path)
            self.assertIsNone(item['reason'],path)
        self.assertEqual([p.name for p in self.a.rglob('.agent-contract-probe-*')],[])
        self.assertEqual([p.name for p in self.lab.rglob('.agent-contract-probe-*')],[])
        rep=self.call('repeat', dict(runs=2, requests=[dict(command='access')]))
        self.assertEqual(rep['identical'],True)
        self.assertEqual(rep['project_unchanged'],True)

    @case('X81', 'Каталог только для чтения: честный writable false с причиной.', '§4 п. 8–9 (И-053).')
    def test_104_access_read_only(self):
        if os.name=='nt':
            self.skipTest('Биты прав не проверяются на Windows.')
        if hasattr(os,'geteuid') and os.geteuid()==0:
            self.skipTest('Суперпользователь обходит биты прав.')
        self.install(); self.make()
        before=snapshot(self.a)
        mode=stat.S_IMODE(self.a.stat().st_mode)
        os.chmod(self.a,0o555)
        try:
            view=c.dispatch(self.lab, str(self.a), 'access', {})
        finally:
            os.chmod(self.a,mode)
        self.assertEqual(before, snapshot(self.a))
        self.assertEqual(view['writes'],False)
        self.assertEqual(view['left'],[])
        self.assertFalse(view['all_writable'])
        entry=view['paths']['AGENTS.md']
        self.assertEqual(entry['writable'],False)
        self.assertEqual(entry['reason'],'permission')
        self.assertEqual(entry['errno'],13)
        self.assertTrue(view['paths']['.agent-contract/project/state.json']['writable'])
"""

PROTOCOL_043 = """

## Права: измеренные и объявленные (0.1.33)

`rights` объявляет закрытый список из девяти путей записи. Это данные, а не факт: каталог может быть только
для чтения, диск — смонтирован только для чтения, файл — занят другой программой.

`access` (чтение, `writes: false`) измеряет каждый из девяти путей записью:

- в каталоге самого пути создаётся собственный временный файл `.agent-contract-probe-…`;
- файл пишется, сбрасывается на диск и удаляется в той же операции;
- ответ: `paths` — `{путь: {writable, reason, errno}}`, `all_writable`, `left` (что не удалось убрать),
  `measured: true`;
- `reason`: `null` — запись возможна; `permission` — нет прав; `io` — иная ошибка ввода-вывода;
  `no_directory` — каталога пути нет (например, проект ещё не установлен).

Что важно:

- комплект **не выдаёт** права и не пытается их обойти; он их измеряет и говорит результат;
- ответ — факт на момент вызова: право может измениться сразу после него;
- после вызова в проекте не остаётся ни одного файла комплекта — это проверяется (`left` и тест X80).

Если `writable: false`:

- `permission` на `AGENTS.md` — каталог проекта только для чтения: комплект не сможет создать вход;
  выдайте право на запись в проект или смените раскладку (см. `layout`);
- `permission` на `.agent-contract/…` — служебный каталог повреждён по правам: восстановите права на
  каталог, содержимое при этом не меняется;
- `no_directory` — установка не выполнялась: сначала `install`, потом `access`.
"""

README_043 = """
## Что изменилось в 0.1.33

`rights` называет девять путей записи, но объявление — не факт. Команда `access` измеряет каждый путь
записью: создаёт собственный временный файл в каталоге пути, проверяет его и удаляет в той же операции.
Ответ: `{путь: {writable, reason}}`, `all_writable`, `left`, `measured: true`. Команда только читает — после
неё в проекте не остаётся ничего. Если `writable: false` с причиной `permission`, комплект не станет писать
наугад: он скажет, какой каталог закрыт.
"""
