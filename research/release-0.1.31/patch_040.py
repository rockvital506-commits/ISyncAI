"""Правки выпуска 0.1.30 (И-050): чужая файловая система — регистр, длина, права.

§16 спрашивает, что будет на другой машине. Комплект писал `AGENTS.md` и не думал, что `agents.md` на NTFS —
тот же файл; принимал имена длиннее 255 байт, которые POSIX отвергает; и ничего не говорил о правах
файлов, которые сам создаёт.

Что меняется:

1. **Команда `system`** (чтение, `writes: false`): что измерено — чувствительность к регистру (проверка
   соседним именем, без записи), — и что объявлено: лимит длины пути, длина имени, зарезервированные
   имена Windows, форма юникода. У каждого факта есть `proven`: измеренное не выдаётся за объявленное.
2. **Отказ `case`:** имя, совпадающее с существующим без учёта регистра, останавливает запись — на NTFS это
   один файл, и «создать рядом» означает «перезаписать».
3. **Отказ `path` на длину компонента:** имя длиннее 255 байт в UTF-8 не создаётся ни на POSIX, ни на NTFS —
   отказ приходит до записи, а не после неё.
4. **`rights.files`:** измеренные права файлов проекта — режим, доступ на запись другим, размер. На Windows
   режим не измеряется и остаётся `null`, а не выдуманным.

Схема не меняется; закрытый список путей тот же.
"""

CASE_OLD = """def foreign_files(root):"""

CASE_NEW = '''def case_conflicts(root, paths):
    """0.1.30: имена, совпадающие без учёта регистра, на NTFS — один файл (И-050, §16)."""
    found = []
    for path in paths:
        parent_rel, _, name = path.rpartition('/')
        if not parent_rel:
            folder = Path(root)
        elif (Path(root) / parent_rel).is_dir():
            folder = safe(root, parent_rel)
        else:
            continue
        try:
            entries = sorted(folder.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.name != name and entry.name.casefold() == name.casefold():
                found.append({'path': path, 'existing': entry.relative_to(root).as_posix()})
    return found


def foreign_files(root):'''

REL_OLD = """             not re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])', p.split('.')[0], re.I),
             'path', 'Недопустимый относительный путь.', {'path': s})"""

REL_NEW = """             not re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])', p.split('.')[0], re.I),
             'path', 'Недопустимый относительный путь.', {'path': s})
        # 0.1.30: имя длиннее 255 байт не создаётся ни на POSIX, ни на NTFS (И-050, §16).
        need(len(p.encode('utf-8')) <= 255, 'path', 'Имя длиннее 255 байт: файловая система его не примет.',
             {'path': s, 'part': p, 'bytes': len(p.encode('utf-8')), 'limit': 255})"""

PLAN_CASE_OLD = """    # 0.1.29: чужая запись в служебном каталоге — не повод продолжать (И-049, §11).
    guard_writes(root)"""

PLAN_CASE_NEW = """    # 0.1.29: чужая запись в служебном каталоге — не повод продолжать (И-049, §11).
    guard_writes(root)"""

SYSTEM_OLD = """    if command == 'rights':"""

SYSTEM_NEW = """    if command == 'system':
        # 0.1.30: чужая файловая система — что измерено, а что объявлено (И-050, §16).
        exact(payload, '')
        entry = root / ENTRY
        probe = None
        if entry.is_file():
            alt = entry.with_name(entry.name.swapcase())
            probe = {'name': entry.name, 'other_case': alt.name,
                     'same_file': alt.name != entry.name and alt.exists()}
        return {'os': os.name, 'sep': os.sep,
                'case_insensitive': None if probe is None else probe['same_file'],
                'probe': probe,
                'declared': {'max_path': 260 if os.name == 'nt' else 4096,
                             'name_bytes': 255,
                             'reserved': ['CON', 'PRN', 'AUX', 'NUL', 'COM1…COM9', 'LPT1…LPT9'],
                             'forbidden': '\\\\ : " < > | ? * и управляющие символы',
                             'unicode': 'NFC'},
                'proven': {'case_insensitive': probe is not None,
                           'max_path': False, 'name_bytes': False, 'unicode': False},
                'writes': False,
                'note': 'Регистр измерен чтением соседнего имени, без записи. Лимиты и форма юникода '
                        'объявлены: на этой машине они не измерялись.'}
    if command == 'rights':"""

RIGHTS_FILES_OLD = """        foreign = foreign_files(root)
        return {'reads': sorted([BASE + n for n in FILES] + [STATE, CHECKS, ENTRY, LOCAL + '**']),"""

RIGHTS_FILES_NEW = """        foreign = foreign_files(root)
        measured = []
        for path in sorted(TARGETS):
            full = Path(root) / path
            if full.is_file():
                info = full.stat()
                measured.append({'path': path, 'bytes': info.st_size,
                                 'mode': None if os.name == 'nt' else oct(stat.S_IMODE(info.st_mode)),
                                 'world_writable': None if os.name == 'nt' else bool(info.st_mode & stat.S_IWOTH)})
        return {'reads': sorted([BASE + n for n in FILES] + [STATE, CHECKS, ENTRY, LOCAL + '**']),
                'files': measured,"""

READ_ONLY_OLD = """             'adapter', 'brief', 'identity', 'discovery', 'entry', 'session', 'metrics', 'due', 'rights')"""

READ_ONLY_NEW = """             'adapter', 'brief', 'identity', 'discovery', 'entry', 'session', 'metrics', 'due', 'rights',
             'system')"""

CLI_OLD = """    cli.add_argument('command', choices=('status', 'list', 'metrics', 'rights', 'history', 'removed', 'updates', 'pending', 'operations', 'inventory', 'adapter', 'brief', 'identity', 'discovery', 'entry', 'repeat', 'session', 'due', 'plan', 'apply'))"""

CLI_NEW = """    cli.add_argument('command', choices=('status', 'list', 'metrics', 'rights', 'system', 'history', 'removed', 'updates', 'pending', 'operations', 'inventory', 'adapter', 'brief', 'identity', 'discovery', 'entry', 'repeat', 'session', 'due', 'plan', 'apply'))"""

REVIEW_CHANGE_OLD = """    def change(self, path, data):
        need(path in TARGETS, 'boundary', 'Запись не входит в закрытый список.')
        need(data is None or len(data) <= MAX_BYTES, 'limit', 'Результат слишком велик.')
        if data != self.observe(path):"""

REVIEW_CHANGE_NEW = """    def change(self, path, data):
        need(path in TARGETS, 'boundary', 'Запись не входит в закрытый список.')
        need(data is None or len(data) <= MAX_BYTES, 'limit', 'Результат слишком велик.')
        # 0.1.30: имя, совпадающее с существующим без учёта регистра, — тот же файл на NTFS (И-050, §16).
        conflicts = case_conflicts(self.root, [path])
        need(not conflicts, 'case', 'Имя совпадает с существующим без учёта регистра: на NTFS это один файл.',
             {'conflicts': conflicts})
        if data != self.observe(path):"""

TEST_040 = r"""
    @case('X74', 'Файловая система: регистр измерен, лимиты объявлены, чтение не пишет.', '§16 (И-050).')
    def test_97_system(self):
        self.install(); self.make()
        self.apply(dict(op='connect'))
        before=snapshot(self.a)
        view=self.call('system')
        self.assertEqual(before, snapshot(self.a))
        self.assertEqual(view['writes'],False)
        self.assertEqual(view['case_insensitive'], True if os.name == 'nt' else False)
        self.assertEqual(view['proven']['case_insensitive'], True)
        self.assertEqual(view['proven']['max_path'], False)
        self.assertEqual(view['declared']['name_bytes'], 255)
        self.assertIn('CON', view['declared']['reserved'])
        self.assertEqual(view['probe']['name'], 'AGENTS.md')
        rights=self.call('rights')
        self.assertTrue(rights['files'])
        for row in rights['files']:
            self.assertIn(row['path'], c.TARGETS)
            if os.name == 'nt':
                self.assertIsNone(row['mode'])
            else:
                self.assertTrue(row['mode'].startswith('0o'))
                self.assertEqual(row['world_writable'], False)
        rep=self.call('repeat', dict(runs=2, requests=[dict(command='system'), dict(command='rights')]))
        self.assertEqual(rep['identical'],True)

    @case('X75', 'Имена: регистр останавливает запись, длина компонента отклоняется.', '§16 (И-050).')
    def test_98_names(self):
        self.install(); self.make()
        decoy=self.a/'agents.md'
        decoy.write_text('чужое имя в другом регистре\n', encoding='utf-8')
        err=self.assertRefused('case', self.preview, dict(op='connect'))
        self.assertEqual(err.details['conflicts'], [{'path':'AGENTS.md','existing':'agents.md'}])
        decoy.unlink()
        self.apply(dict(op='connect'))
        long_name='x'*300+'.json'
        err=self.assertRefused('path', self.preview,
                               dict(op='merge', incoming='.agent-contract/project/'+long_name))
        self.assertEqual(err.details['limit'], 255)
        self.assertEqual(err.details['bytes'], 305)
        self.assertEqual(self.call('status')['health'],'valid')
"""

PROTOCOL_040 = """

## Чужая файловая система (0.1.30)

`system` (чтение, `writes: false`) разделяет измеренное и объявленное:

- `case_insensitive` — **измерено** чтением соседнего имени: `AGENTS.md` против `agents.MD`. На NTFS это
  один файл, на ext4 — нет. Без существующего входа факт не измеряется и остаётся `null`.
- `declared` — лимит длины пути (260 на Windows, 4096 на POSIX), длина имени (255 байт), зарезервированные
  имена Windows, форма юникода. `proven` говорит, что из этого на этой машине не измерялось.

Отказы на входе:

- `case` — цель записи совпадает с существующим файлом без учёта регистра: «создать рядом» на NTFS значит
  «перезаписать». В деталях — `{path, existing}`.
- `path` — имя компонента длиннее 255 байт в UTF-8 (или путь недопустим по прежним правилам).

`rights` называет `files` — измеренные права файлов проекта: `mode`, `world_writable`, `bytes`. На Windows
режим не измеряется и остаётся `null`, а не выдуманным.
"""

README_040 = """
## Что изменилось в 0.1.30

Чужая файловая система: команда `system` называет измеренную чувствительность к регистру и объявленные
лимиты (длина пути, 255 байт на имя, зарезервированные имена Windows, юникод). Запись останавливается
отказом `case`, если имя совпадает с существующим без учёта регистра, и отказом `path`, если компонент
длиннее 255 байт. `rights` показывает измеренные права файлов проекта.
"""
