"""Правки выпуска 0.1.12 (И-032): раскладка владельца, чужой вход, перенос состояния.

Три правки, все измерены стендом обкатки И-031 (P1, P2, P4, P7):

1. Проект может лежать **вне** корня комплекта. Сценарий владельца — распакованный архив внутри
   репозитория; тогда проект задаётся абсолютным путём. Относительные пути по-прежнему считаются от
   лаборатории и не могут выйти наружу.
2. Чужой `AGENTS.md` перестаёт быть тупиком. Комплект никогда не присваивает чужой файл, но теперь у
   владельца есть документированный ручной вход: команда `brief` отдаёт ровно ту строку, которую можно
   вписать в свой файл, и путь к START.md; `status` называет режим входа. Запись проверок работает и
   без адаптера.
3. Журнал операций, приехавший из другого пути, — история, а не поломка. Завершённые операции чужого
   корня больше не мешают работе; незавершённая операция чужого корня по-прежнему отказ, потому что её
   нельзя доигрывать на другой машине.
"""

SAFE_TARGET_OLD = """def safe_target(lab, project):
    root = safe(lab, rel(project))
    need(root.is_dir() and project.split('/')[0].casefold() not in ('releases', 'kit') and
         all(part.casefold() != '.agent-contract' for part in project.split('/')),
         'root', 'Нужна отдельная существующая папка проекта, не kit/releases/служебный каталог.')
    return root"""

SAFE_TARGET_NEW = '''def safe_target(lab, project):
    # 0.1.12: проект может лежать вне корня комплекта — тогда путь задаётся абсолютным (И-032, P1).
    # Относительный путь по-прежнему не выходит из лаборатории и не указывает на kit/releases.
    if project.startswith('/') or re.match(r'^[A-Za-z]:[\\\\/]', project):
        root = Path(project)
        need(root.is_dir(), 'root', 'Нужна существующая папка проекта.', {'path': project})
        lab_root = Path(lab).resolve()
        resolved = root.resolve()
        need(resolved != lab_root, 'root', 'Корень комплекта не может быть проектом.', {'path': project})
        for reserved in ('kit', 'releases'):
            need(resolved != lab_root / reserved and (lab_root / reserved) not in resolved.parents,
                 'root', 'Проект не может быть служебным каталогом комплекта.', {'path': project})
        need(not any(part.casefold() == '.agent-contract' for part in resolved.parts),
             'root', 'Проект не может быть служебным каталогом комплекта.', {'path': project})
        return resolved
    root = safe(lab, rel(project))
    need(root.is_dir() and project.split('/')[0].casefold() not in ('releases', 'kit') and
         all(part.casefold() != '.agent-contract' for part in project.split('/')),
         'root', 'Нужна отдельная существующая папка проекта, не kit/releases/служебный каталог.')
    return root'''

PENDING_OLD = """def pending(root):
    folder = safe(root, OPS.rstrip('/'))
    if not folder.exists():
        return []
    result = []
    for d in sorted(folder.iterdir()):
        need(TX.fullmatch(d.name), 'journal', 'Неизвестный объект в каталоге журналов. Ничего не удалено.')
        marker = safe(root, journal_name(d.name))
        # A preparation without a published marker cannot have modified a destination.
        if marker.exists() and journal(root, d.name)['status'] == 'pending':
            result.append(d.name)
    return result"""

PENDING_NEW = """def pending(root):
    folder = safe(root, OPS.rstrip('/'))
    if not folder.exists():
        return []
    result = []
    for d in sorted(folder.iterdir()):
        need(TX.fullmatch(d.name), 'journal', 'Неизвестный объект в каталоге журналов. Ничего не удалено.')
        marker = safe(root, journal_name(d.name))
        # A preparation without a published marker cannot have modified a destination.
        if not marker.exists():
            continue
        raw = parse(marker.read_bytes())
        # 0.1.12: журнал несёт абсолютный путь проекта. Приехавший из другого пути — это история
        # другой машины, а не незавершённая операция здесь (И-032, F8).
        if isinstance(raw, dict) and raw.get('root') != str(root):
            need(raw.get('status') in ('committed', 'restored'), 'journal_foreign',
                 'Незавершённая операция другой машины: здесь её нельзя продолжать.',
                 {'tx': d.name, 'root': raw.get('root')})
            continue
        if journal(root, d.name)['status'] == 'pending':
            result.append(d.name)
    return result"""

STATUS_OLD = """        entry = ('absent' if not exists else 'unmanaged') if adapter is None else (
            'created' if digest(read(root, ENTRY)) == adapter['sha256'] else 'drift')"""

STATUS_NEW = """        entry = ('absent' if not exists else 'unmanaged') if adapter is None else (
            'created' if digest(read(root, ENTRY)) == adapter['sha256'] else 'drift')
        # 0.1.12: режим входа назван прямо. Чужой файл не присваивается, но и не блокирует работу.
        entry_mode = 'owned' if entry == 'created' else 'foreign' if entry == 'unmanaged' else entry"""

STATUS_RETURN_OLD = """                'schema_version': 1, 'project_revision': s['revision'], 'base': s['base'], 'entry': entry,"""
STATUS_RETURN_NEW = """                'schema_version': 1, 'project_revision': s['revision'], 'base': s['base'], 'entry': entry,
                'entry_mode': entry_mode, 'brief_available': not exists or entry == 'created',"""

BRIEF_BLOCK = """    if command == 'brief':
        # 0.1.12: ручной вход для проекта, где AGENTS.md уже занят (И-032, P2). Комплект ничего не
        # пишет в чужой файл: он отдаёт ровно ту строку, которую владелец вписывает сам, и путь к
        # каноническому источнику. Второй реестр не создаётся: строка только указывает на START.md.
        owned = s['adapter'] is not None
        exists = safe(root, ENTRY).exists()
        return {'entry': ENTRY, 'mode': 'owned' if owned else 'foreign' if exists else 'absent',
                'writes': False, 'start': '.agent-contract/base/START.md',
                'line': files['entry.txt'].decode('utf-8').strip(),
                'how': 'Впишите эту строку в свой AGENTS.md вручную. Комплект чужой файл не '
                       'перезаписывает: содержимое не читалось, второй реестр не создаётся.',
                'start_sha256': digest(files['START.md']), 'entry_sha256': digest(files['entry.txt']),
                'discovery_proven': False}
"""

CHOICES_OLD = "choices=('status', 'list', 'history', 'updates', 'pending', 'operations', 'inventory', 'adapter', 'session', 'plan', 'apply')"
CHOICES_NEW = "choices=('status', 'list', 'history', 'updates', 'pending', 'operations', 'inventory', 'adapter', 'brief', 'session', 'plan', 'apply')"

TEST_022 = r"""
    @case('X37', 'Проект может лежать вне корня комплекта: путь задаётся абсолютным.',
          'Раскладка владельца: распакованный архив внутри репозитория.')
    def test_60_project_outside_lab(self):
        import tempfile as _t
        outside=_t.mkdtemp(prefix='outside-')
        self.addCleanup(lambda: __import__('shutil').rmtree(outside,ignore_errors=True))
        where=Path(outside)/'repo';where.mkdir()
        (where/'AGENTS.md').write_text('# свой файл\n',encoding='utf-8')
        (where/'demo.txt').write_text('synthetic input\n',encoding='utf-8')
        proc=subprocess.run([sys.executable,'-I','-B',str(CLI),'--lab',str(self.lab),'--project',str(where),
                             'plan'],input=c.encode(dict(op='install',package=PACKAGE,pin=PIN)),capture_output=True)
        self.assertEqual(proc.stderr,b'');view=c.parse(proc.stdout)
        self.assertFalse(view['writes'])
        self.assertRefused('root',c.safe_target,self.lab,str(self.lab))
        self.assertRefused('root',c.safe_target,self.lab,str(self.kbase))
        self.assertEqual(c.safe_target(self.lab,str(where)),Path(where))
        self.assertEqual(c.safe_target(self.lab,'A'),self.a)

    @case('X38', 'Чужой вход не присваивается, но появляется ручной вход: brief, режим foreign, запись работает.',
          'Проверяется отсутствие записи в чужой файл, а не поведение среды.')
    def test_61_foreign_entry_brief(self):
        self.install()
        (self.a/'AGENTS.md').write_text('# инструкции проекта\n',encoding='utf-8')
        before=(self.a/'AGENTS.md').read_bytes()
        self.assertRefused('foreign_entry',self.preview,dict(op='connect'))
        statusv=self.call('status')
        self.assertEqual(statusv['entry'],'unmanaged');self.assertEqual(statusv['entry_mode'],'foreign')
        brief=self.call('brief')
        self.assertEqual(brief['mode'],'foreign');self.assertFalse(brief['writes'])
        self.assertEqual(brief['start'],'.agent-contract/base/START.md')
        self.assertTrue(brief['line'].startswith('Контракт этого проекта'))
        self.assertEqual(before,(self.a/'AGENTS.md').read_bytes())
        env={k:'synthetic' for k in c.ENV_KEYS.split()}
        obs=dict(case='запись без адаптера',level=1,conditions='Синтетический проект',expected='Проверка проходит.',
                 actual='Проверка проходит.',status='pass',evidence='tests.log, строка 12',
                 limits='Только синтетические данные.',environment=dict(env))
        self.apply(dict(op='record_check',observation=obs))
        self.assertEqual(len(self.call('status')['observations']),1)
        self.assertEqual(before,(self.a/'AGENTS.md').read_bytes())

    @case('X39', 'Журнал, приехавший из другого пути, — история; незавершённая операция чужого корня — отказ.',
          'Перенос проекта между машинами; доигрывать чужую операцию нельзя.')
    def test_62_foreign_journal(self):
        import shutil as _shutil
        import tempfile as _t
        self.install();self.apply(dict(op='connect'))
        env={k:'synthetic' for k in c.ENV_KEYS.split()}
        obs=dict(case='перенос',level=1,conditions='Синтетический проект',expected='Проверка проходит.',
                 actual='Проверка проходит.',status='pass',evidence='tests.log',limits='Синтетика.',
                 environment=dict(env))
        self.apply(dict(op='record_check',observation=obs))
        outside=_t.mkdtemp(prefix='moved-');self.addCleanup(lambda: _shutil.rmtree(outside,ignore_errors=True))
        moved=Path(outside)/'repo';_shutil.copytree(self.a,moved)
        ring=c.parse((moved/c.STATE).read_bytes())
        self.assertEqual(ring['base']['version'],BASE_VERSION)
        ops=sorted((moved/c.OPS).iterdir())
        self.assertTrue(ops)
        self.assertEqual(c.pending(moved),[])
        self.assertEqual(len(c.dispatch(self.lab,str(moved),'status',{})['observations']),1)
        tx=sorted((moved/c.OPS).iterdir())[-1].name
        journal=c.safe(moved,c.journal_name(tx))
        data=c.parse(journal.read_bytes());data['status']='pending'
        journal.write_bytes(c.encode(data))
        self.assertRefused('journal_foreign',c.pending,moved)
"""

PROTOCOL_022 = """

## Раскладка владельца, чужой вход и перенос (0.1.12)

**Проект вне корня комплекта.** Распакованный архив можно положить внутрь репозитория — тогда проект
задаётся абсолютным путём: `--lab <репозиторий>/AgentContractLab --project <репозиторий>`. Относительный
путь по-прежнему считается от корня комплекта и не может выйти наружу, указывать на `kit`, `releases`
или `.agent-contract`.

**Чужой вход.** Если в проекте уже есть `AGENTS.md`, комплект его не присваивает и не перезаписывает —
содержимое не читается. Вместо тупика есть ручной вход: `status` называет режим (`entry_mode`: `owned`,
`foreign`, `absent`), а команда `brief` отдаёт одну строку для своего файла и путь
`.agent-contract/base/START.md`. Запись проверок от адаптера не зависит: наблюдения можно вести и без
него, пока вход не согласован. Обнаружение средой при этом остаётся недоказанным.

**Перенос состояния.** `.agent-contract` переносится целиком, включая журнал операций: журнал несёт
абсолютный путь проекта, и после `git clone` в другой каталог завершённые операции читаются как история
другой машины, а не как поломка. Незавершённая операция чужого корня — отказ `journal_foreign`: её
нельзя доигрывать там, где она не начиналась.
"""

README_022 = """
## Что изменилось в 0.1.12

Три вещи, которые упёрлись в первые же десять минут обкатки. Распакованный архив теперь можно держать
внутри своего репозитория: проект задаётся абсолютным путём. Чужой `AGENTS.md` перестал быть тупиком —
комплект по-прежнему его не трогает, но `status` называет режим входа, а команда `brief` отдаёт одну
строку, которую владелец вписывает сам, и путь к START.md; записи проверок от этого не зависят.
Журнал операций, приехавший из другого пути, читается как история другой машины, поэтому `.agent-contract`
переносится целиком; незавершённая чужая операция — по-прежнему отказ. Правило тождества не менялось.
"""
