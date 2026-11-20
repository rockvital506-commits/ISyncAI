"""Правки выпуска 0.1.7 (И-027): адаптер GitHub Copilot / VS Code. Только тексты."""

NATIVE_HINTS_OLD = r"""NATIVE_HINTS = ('.github/copilot-instructions.md', '.github/instructions', 'kilo.jsonc', '.kilocode/rules',
                'CLAUDE.md', '.claude/CLAUDE.md', '.cursor/rules', 'GEMINI.md',
                'AGENT.md', '.kilo/kilo.jsonc', '.kilo/rules', '.kilocoderules')
"""

NATIVE_HINTS_NEW = r"""NATIVE_HINTS = ('.github/copilot-instructions.md', '.github/instructions', 'kilo.jsonc', '.kilocode/rules',
                'CLAUDE.md', '.claude/CLAUDE.md', '.cursor/rules', 'GEMINI.md',
                'AGENT.md', '.kilo/kilo.jsonc', '.kilo/rules', '.kilocoderules',
                '.github/agents', '.github/prompts', '.github/skills', '.vscode/settings.json')
"""

COPILOT_BLOCK = r"""# --- 0.1.7: карточка среды GitHub Copilot / VS Code (адаптер, И-027) ----------------
# Отличие от Kilo: вход комплекта у Copilot не рекомендованный, а нижний в своей группе, и часть
# поверхностей его не читает вовсе. Источники сверены 18.11.2026:
#   https://docs.github.com — repository custom instructions, path-specific .instructions.md, порядок
#   https://github.blog/changelog/2025-08-28-copilot-coding-agent-now-supports-agents-md-custom-instructions/
#   https://startdebugging.net/2026/09/... — сводка по поверхностям и оговорка CLI об отсутствии порядка
ADAPTERS['copilot'] = {
    'name': 'copilot',
    'title': 'GitHub Copilot / VS Code',
    'entry': ENTRY,
    'entry_recommended': '.github/copilot-instructions.md',
    'entry_shared': False,
    'entry_fallbacks': ['CLAUDE.md', 'GEMINI.md'],
    'priority': {'tier': 'repository', 'rank': 3, 'of': 5, 'order': [
        {'rank': 1, 'source': 'personal instructions', 'ours': False},
        {'rank': 2, 'source': '.github/instructions/**/*.instructions.md (applyTo)', 'ours': False},
        {'rank': 3, 'source': '.github/copilot-instructions.md', 'ours': False},
        {'rank': 4, 'source': 'AGENTS.md (agent instructions)', 'ours': True},
        {'rank': 5, 'source': 'organization custom instructions', 'ours': False}],
        'note': 'Все применимые наборы передаются модели; старшинство решает конфликт, а не убирает проигравшего.'},
    'sources': ['.github/copilot-instructions.md', '.github/instructions', '.github/agents',
                '.github/prompts', '.github/skills', '.vscode/settings.json', 'CLAUDE.md',
                '.claude/CLAUDE.md', 'GEMINI.md', 'AGENT.md'],
    'never_writes': ['.github/', '.vscode/', 'CLAUDE.md', 'GEMINI.md'],
    'environment_facts': {'instructions_are_prose_not_enforced_rules': True,
                          'path_specific_files_require_applyTo_frontmatter': True,
                          'cli_defines_no_general_precedence_order': True,
                          'agents_md_outside_workspace_root_off_by_default': True},
    'coverage': {'reads_agents_md': ['Copilot cloud agent', 'Copilot code review (GitHub.com)',
                                     'Copilot CLI', 'Copilot Chat in VS Code'],
                 'coverage_gap': ['Copilot Chat on github.com', 'inline suggestions'],
                 'reads_repo_wide_file': 'all surfaces supporting custom instructions at all'},
    'not_proven': ['auto-discovery', 'content_was_read', 'behaviour_with_model'],
    'discovery_proven': False,
}


"""

CONNECT_OLD = r"""    elif op in ('connect', 'disconnect', 'retire'):
        exact(r, 'op', 'ack_existing' if op == 'connect' else 'allow_delete')
        adapter = s['adapter']"""

CONNECT_NEW = r"""    elif op in ('connect', 'disconnect', 'retire'):
        exact(r, 'op', 'ack_existing entry_path' if op == 'connect' else 'allow_delete')
        adapter = s['adapter']
        if op == 'connect' and r.get('entry_path', ENTRY) != ENTRY:
            # Запрет на второй реестр как код отказа: комплект ведёт ровно один вход. Второй вход —
            # это два указателя, которые расходятся; вместо него — ручное чтение START.md или выбор
            # одной среды.
            raise Refusal('second_entry', 'Второй вход не создаётся: комплект ведёт ровно один вход. '
                          'Для сред, которые читают свой файл, доступно ручное чтение START.md.',
                          {'requested': r['entry_path'], 'entry': ENTRY})"""

TEST_017 = r"""
    @case('X27', 'Второй вход не создаётся: попытка указать другой путь входа отклоняется кодом second_entry.')
    def test_50_second_entry(self):
        self.install()
        self.assertRefused('second_entry',self.preview,dict(op='connect',entry_path='.github/copilot-instructions.md'))
        self.assertRefused('second_entry',self.preview,dict(op='connect',entry_path='CLAUDE.md'))
        self.apply(dict(op='connect',entry_path='AGENTS.md'))
        self.assertTrue((self.a/'AGENTS.md').exists())
        self.assertFalse((self.a/'.github').exists())

    @case('X28', 'Карточка Copilot: наш вход ниже двух родных файлов и покрывает не все поверхности.')
    def test_51_copilot_card(self):
        self.install()
        card=self.call('adapter',dict(name='copilot'))
        self.assertEqual(card['entry'],'AGENTS.md');self.assertEqual(card['entry_recommended'],'.github/copilot-instructions.md')
        self.assertFalse(card['entry_shared']);self.assertEqual(card['priority']['tier'],'repository')
        self.assertEqual([x['rank'] for x in card['priority']['order']],[1,2,3,4,5])
        self.assertEqual(card['priority']['order'][3]['source'],'AGENTS.md (agent instructions)')
        self.assertIn('Copilot Chat on github.com',card['coverage']['coverage_gap'])
        self.assertIn('inline suggestions',card['coverage']['coverage_gap'])
        self.assertFalse(card['discovery_proven']);self.assertFalse(card['writes'])

    @case('X29', 'Инструкции и файлы правил Copilot видны без чтения и требуют подтверждения.')
    def test_52_copilot_sources(self):
        self.install()
        wide=self.a/'.github/copilot-instructions.md';wide.parent.mkdir()
        wide.write_bytes(b'# synthetic copilot instructions\n')
        path_specific=self.a/'.github/instructions/python.instructions.md';path_specific.parent.mkdir()
        path_specific.write_bytes(b'---\napplyTo: "**/*.py"\n---\n- synthetic path rule\n')
        agents=self.a/'.github/agents';agents.mkdir();(agents/'planner.agent.md').write_bytes(b'# synthetic\n')
        settings=self.a/'.vscode/settings.json';settings.parent.mkdir();settings.write_bytes(b'{"synthetic":true}\n')
        inventory=self.call('inventory');self.assertFalse(inventory['contents_read'])
        paths=[x['path'] for x in inventory['native_paths']]
        for want in ('.github/copilot-instructions.md','.github/instructions','.github/agents','.vscode/settings.json'):
            self.assertIn(want,paths)
        card=self.call('adapter',dict(name='copilot'))
        self.assertEqual([x['path'] for x in card['present']],
                         ['.github/copilot-instructions.md','.github/instructions','.github/agents','.vscode/settings.json'])
        self.assertRefused('existing_sources',self.preview,dict(op='connect'))
        self.apply(dict(op='connect',ack_existing=paths))
        self.assertEqual(wide.read_bytes(),b'# synthetic copilot instructions\n')
        self.assertEqual(settings.read_bytes(),b'{"synthetic":true}\n')
        self.evidence['copilot_sources_unchanged']=True

    @case('X30', 'Адаптер Copilot не пишет ни в .github/, ни в .vscode/, ни в чужие входы.')
    def test_53_copilot_never_writes(self):
        self.install()
        wide=self.a/'.github/copilot-instructions.md';wide.parent.mkdir();wide.write_bytes(b'# synthetic\n')
        settings=self.a/'.vscode/settings.json';settings.parent.mkdir();settings.write_bytes(b'{"synthetic":true}\n')
        claude=self.a/'CLAUDE.md';claude.write_bytes(b'# synthetic claude\n')
        inventory=self.call('inventory')
        self.apply(dict(op='connect',ack_existing=[x['path'] for x in inventory['native_paths']]))
        self.call('adapter',dict(name='copilot'));self.call('status');self.call('inventory')
        self.assertEqual(wide.read_bytes(),b'# synthetic\n')
        self.assertEqual(settings.read_bytes(),b'{"synthetic":true}\n')
        self.assertEqual(claude.read_bytes(),b'# synthetic claude\n')
        self.assertEqual(sorted(q.name for q in (self.a/'.github').iterdir()),['copilot-instructions.md'])
"""

PROTOCOL_017 = r"""

## Адаптер GitHub Copilot / VS Code (0.1.7)

У Copilot инструкции вместо правил, и вход комплекта здесь не главный. Документированный порядок: личные инструкции, затем файлы репозитория — сначала path-specific `.github/instructions/**/*.instructions.md` с полем `applyTo` во front matter, затем общий `.github/copilot-instructions.md`, затем инструкции агента (`AGENTS.md`, а также `CLAUDE.md` и `GEMINI.md` в корне), затем инструкции организации. Все применимые наборы передаются модели: старшинство решает конфликт, но не убирает проигравшего. Покрытие `AGENTS.md` неполное: его читают cloud agent, code review на GitHub.com, CLI и Chat в VS Code, а Chat на github.com и встроенные подсказки — нет. CLI, по своей документации, общего порядка между файлами не определяет. Поэтому карточка `adapter copilot` показывает и старшинство, и пробелы покрытия, и рекомендованный средой файл `.github/copilot-instructions.md`, и честно сообщает `entry_shared: false`: комплект ведёт один вход, а не два. Комплект не пишет ни в `.github/`, ни в `.vscode/`, ни в `CLAUDE.md`/`GEMINI.md`. Запрос `connect` с другим путём входа отклоняется кодом `second_entry`: второй вход — это второй указатель, который неизбежно расходится с первым.
"""

README_017 = r"""
## Что изменилось в 0.1.7

Адаптер GitHub Copilot / VS Code. У этой среды инструкции вместо правил, и вход комплекта стоит ниже двух родных файлов репозитория: path-specific `.github/instructions/**/*.instructions.md` и общего `.github/copilot-instructions.md`; выше — только личные инструкции, ниже — организация. Покрытие `AGENTS.md` неполное: Chat на github.com и встроенные подсказки его не читают. Карточка `adapter copilot` показывает старшинство, пробелы покрытия, рекомендованный файл среды и `entry_shared: false`. Запрет на второй реестр стал кодом отказа: `connect` с другим путём входа отклоняется как `second_entry`. Комплект не пишет ни в `.github/`, ни в `.vscode/`, ни в `CLAUDE.md`/`GEMINI.md`.
"""
