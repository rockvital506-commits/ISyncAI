"""Правки выпуска 0.1.32 (И-052): раскладка названа — лаборатория, проект и корень.

Ваш сценарий: распаковать архив **в корень репозитория** и работать с этим корнем как с проектом.
Так архив и раскладывается: `<repo>/AgentContractLab/`, проект — сам `<repo>`. Комплект это выдерживает,
но **нигде не называет**: ни того, что раскладка поддерживается, ни того, что лаборатория внутри проекта
не управляется контрактом и не считается посторонней записью.

Что меняется:

1. **Команда `layout`** (чтение, `writes: false`): называет `project` и `lab` (абсолютные пути),
   `relation` — `lab_inside_project` | `project_inside_lab` | `siblings` | `elsewhere`, `lab_relative`
   (путь лаборатории внутри проекта), `contract` и `entry`, `installed`, `supported` и `notes` —
   что раскладка значит на практике.
2. **Список чтения и консоль:** `layout` — чтение; `repeat` его принимает.
3. **Справочник и README:** раздел о раскладках и о том, что «в корень» = `<repo>/AgentContractLab/`.

Схема не меняется; закрытый список путей тот же.
"""

LAYOUT_OLD = """    p = Review(root, {}, timestamp())"""

LAYOUT_NEW = '''    if command == 'layout':
        # 0.1.32: где лаборатория относительно проекта — раскладка названа, а не подразумевается (И-052).
        exact(payload, '')
        proj = Path(root).resolve()
        kit_root = Path(lab).resolve()

        def inside(child, parent):
            return child != parent and parent in child.parents

        if inside(kit_root, proj):
            relation = 'lab_inside_project'
        elif inside(proj, kit_root):
            relation = 'project_inside_lab'
        elif proj.parent == kit_root.parent:
            relation = 'siblings'
        else:
            relation = 'elsewhere'
        relative = kit_root.relative_to(proj).as_posix() if relation == 'lab_inside_project' else None
        notes = {
            'lab_inside_project': 'Архив распакован в корень проекта: проект — сам корень, лаборатория — '
                                  'каталог внутри него. Комплект пишет только в .agent-contract/ и AGENTS.md; '
                                  'файлы лаборатории (kit/, releases/, reports/) остаются как есть и контрактом '
                                  'не управляются. При переносе проекта лабораторию переносят вместе с ним.',
            'project_inside_lab': 'Проект лежит внутри лаборатории: обновление и восстановление берут архивы '
                                  'из releases/ лаборатории. Чтобы перенести проект отдельно, скопируйте '
                                  'лабораторию и проект вместе — иначе обновлять будет нечем.',
            'siblings': 'Лаборатория и проект — соседние каталоги: проект переносим отдельно, лаборатория '
                        'остаётся общей для нескольких проектов.',
            'elsewhere': 'Лаборатория вне проекта: пути не связаны. Проект переносится отдельно; проверьте, '
                         'что лаборатория остаётся доступной при переносе.',
        }
        warnings = []
        if relation == 'lab_inside_project':
            warnings.append('лаборатория внутри проекта: каталог ' + str(relative) +
                            '/ может попасть в систему контроля версий — исключите его, если не нужен в репозитории')
        return {'project': proj.as_posix(), 'lab': kit_root.as_posix(), 'relation': relation,
                'lab_relative': relative, 'contract': PREFIX.rstrip('/'), 'entry': ENTRY,
                'installed': (proj / STATE).is_file(), 'supported': True,
                'note': notes[relation], 'warnings': warnings,
                'how': ['распакуйте архив в корень проекта', 'проверьте раскладку этой командой',
                        'дальше — порядок первого обращения в START.md'],
                'writes': False}
    p = Review(root, {}, timestamp())'''

READ_ONLY_OLD = """             'system', 'model', 'verify')"""

READ_ONLY_NEW = """             'system', 'model', 'verify', 'layout')"""

CLI_OLD = """    cli.add_argument('command', choices=('status', 'list', 'metrics', 'rights', 'system', 'model', 'verify', 'history', 'removed', 'updates', 'pending', 'operations', 'inventory', 'adapter', 'brief', 'identity', 'discovery', 'entry', 'repeat', 'session', 'due', 'plan', 'apply'))"""

CLI_NEW = """    cli.add_argument('command', choices=('status', 'list', 'metrics', 'rights', 'system', 'model', 'verify', 'layout', 'history', 'removed', 'updates', 'pending', 'operations', 'inventory', 'adapter', 'brief', 'identity', 'discovery', 'entry', 'repeat', 'session', 'due', 'plan', 'apply'))"""

IMPORT_OLD = """import subprocess
import sys
import time"""

IMPORT_NEW = """import subprocess
import sys
import tempfile
import time"""

TEST_042 = r"""
    @case('X78', 'Раскладка названа: где лаборатория относительно проекта.', '§3 переносимость (И-052).')
    def test_101_layout(self):
        self.install(); self.make()
        before=snapshot(self.a)
        inner=self.call('layout')
        self.assertEqual(before, snapshot(self.a))
        self.assertEqual(inner['writes'],False)
        self.assertEqual(inner['relation'],'project_inside_lab')
        self.assertIsNone(inner['lab_relative'])
        self.assertEqual(inner['contract'],'.agent-contract')
        self.assertEqual(inner['entry'],'AGENTS.md')
        self.assertEqual(inner['installed'],True)
        self.assertEqual(inner['supported'],True)
        parent=self.lab.parent
        outer=c.dispatch(self.lab, str(parent), 'layout', {})
        self.assertEqual(outer['relation'],'lab_inside_project')
        self.assertEqual(outer['lab_relative'], self.lab.name)
        self.assertTrue(any('лаборатория' in w for w in outer['warnings']))
        sibling=parent/'sibling-project'
        sibling.mkdir()
        self.assertEqual(c.dispatch(self.lab, str(sibling), 'layout', {})['relation'],'siblings')
        far=Path(tempfile.mkdtemp(prefix='layout-far-'))
        try:
            view=c.dispatch(self.lab, str(far), 'layout', {})
            self.assertEqual(view['relation'],'elsewhere')
            self.assertEqual(view['installed'],False)
        finally:
            far.rmdir()
        rep=self.call('repeat', dict(runs=2, requests=[dict(command='layout')]))
        self.assertEqual(rep['identical'],True)
        self.assertEqual(rep['project_unchanged'],True)

    @case('X79', 'Архив распакован в корень: проект — корень, лаборатория внутри, установка работает.', '§3 (И-052).')
    def test_102_deploy_root(self):
        parent=self.lab.parent
        before={p.name for p in parent.iterdir()}
        view=c.dispatch(self.lab, str(parent), 'layout', {})
        self.assertEqual(view['relation'],'lab_inside_project')
        req=dict(op='install', package=PACKAGE, pin=PIN)
        plan=c.dispatch(self.lab, str(parent), 'plan', req)
        out=c.dispatch(self.lab, str(parent), 'apply', {'request': req, 'ticket': plan['ticket']})
        self.assertEqual(out['outcome'],'committed')
        req2=dict(op='connect')
        plan2=c.dispatch(self.lab, str(parent), 'plan', req2)
        out2=c.dispatch(self.lab, str(parent), 'apply', {'request': req2, 'ticket': plan2['ticket']})
        self.assertEqual(out2['outcome'],'committed')
        status=c.dispatch(self.lab, str(parent), 'status', {})
        self.assertEqual(status['health'],'valid')
        after={p.name for p in parent.iterdir()}
        self.assertEqual(after-before, {'.agent-contract','AGENTS.md'})
        self.assertTrue((parent/'.agent-contract'/'base'/'START.md').is_file())
        self.assertEqual(c.dispatch(self.lab, str(parent), 'layout', {})['installed'],True)
"""

PROTOCOL_042 = """

## Раскладка: лаборатория, проект и корень (0.1.32)

Архив разворачивается как `<repo>/AgentContractLab/`. Проект — сам корень `<repo>`; лаборатория лежит
внутри него. Это поддерживаемая раскладка, и теперь она названа.

`layout` (чтение, `writes: false`) отвечает:

- `project`, `lab` — абсолютные пути обеих сторон;
- `relation` — `lab_inside_project` (архив распакован в корень проекта), `project_inside_lab`
  (проект внутри лаборатории), `siblings` (соседние каталоги), `elsewhere` (пути не связаны);
- `lab_relative` — путь лаборатории внутри проекта (для `lab_inside_project`);
- `contract`, `entry`, `installed` — где служебный каталог, где вход и установлен ли выпуск;
- `warnings` — что стоит проверить: например, каталог лаборатории внутри проекта может попасть в систему
  контроля версий;
- `note` — что раскладка значит на практике, в том числе при переносе проекта.

Что не меняется: комплект пишет только в закрытый список путей — `.agent-contract/` и `AGENTS.md`.
Файлы лаборатории (`kit/`, `releases/`, `reports/`) контрактом не управляются и остаются как есть.
"""

README_042 = """
## Что изменилось в 0.1.32

Раскладка названа. Ваш сценарий — распаковать архив в корень проекта — теперь проверяем командой `layout`:
она говорит, где лаборатория относительно проекта (`lab_inside_project`, `project_inside_lab`, `siblings`,
`elsewhere`), где служебный каталог и вход, установлен ли выпуск, и что раскладка значит при переносе.
Команда только читает: ничего не создаётся и не меняется.
"""
