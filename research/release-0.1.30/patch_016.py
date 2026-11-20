"""Правки выпуска 0.1.6 (И-026): адаптер Kilo Code. Только тексты, ничего не исполняется."""

NATIVE_HINTS_OLD = r"""NATIVE_HINTS = ('.github/copilot-instructions.md', '.github/instructions', 'kilo.jsonc', '.kilocode/rules',
                'CLAUDE.md', '.claude/CLAUDE.md', '.cursor/rules', 'GEMINI.md')
"""

NATIVE_HINTS_NEW = r"""NATIVE_HINTS = ('.github/copilot-instructions.md', '.github/instructions', 'kilo.jsonc', '.kilocode/rules',
                'CLAUDE.md', '.claude/CLAUDE.md', '.cursor/rules', 'GEMINI.md',
                'AGENT.md', '.kilo/kilo.jsonc', '.kilo/rules', '.kilocoderules')
"""

ADAPTERS_BLOCK = r'''# --- 0.1.6: карточка среды (адаптер Kilo Code, И-026) -------------------------------
# Среда описана данными, а не поведением: что Kilo читает, в каком порядке старшинства, что комплект
# не имеет права трогать и что здесь не проверено. Источники сверены 18.11.2026:
#   https://kilo.ai/docs/customize/agents-md — вход, старшинство, защита файла, применение в новых задачах
#   https://deepwiki.com/Kilo-Org/kilocode/8.3-agent-rules-and-workflows — каталоги правил и подкаталоги
ADAPTERS = {
    'kilo': {
        'name': 'kilo',
        'title': 'Kilo Code',
        'entry': ENTRY,
        'entry_fallback': 'AGENT.md',
        'priority': {'rank': 3, 'of': 4, 'order': [
            {'rank': 1, 'source': 'agent prompt in config', 'ours': False},
            {'rank': 2, 'source': 'instructions key in project kilo.jsonc', 'ours': False},
            {'rank': 3, 'source': 'root AGENTS.md', 'ours': True},
            {'rank': 4, 'source': 'instructions key in global kilo.jsonc', 'ours': False}]},
        'sources': ['.kilo/kilo.jsonc', '.kilo/rules', '.kilocode/rules', '.kilocoderules', 'AGENT.md'],
        'never_writes': ['.kilo/', '.kilocode/', '.kilocoderules', 'kilo.jsonc'],
        'environment_facts': {'entry_is_write_protected': True, 'changes_apply_in_new_tasks': True,
                              'per_directory_agents_md_loaded_on_read': True},
        'not_proven': ['auto-discovery', 'content_was_read', 'behaviour_with_model'],
        'discovery_proven': False,
    },
}


'''

ADAPTER_COMMAND = r"""    if command == 'adapter':
        exact(payload, 'name')
        need(payload['name'] in ADAPTERS, 'adapter_unknown', 'Неизвестная среда: карточка не выдаётся.',
             sorted(ADAPTERS))
        card = dict(ADAPTERS[payload['name']])
        card['priority'] = dict(card['priority'])
        known = set(card['sources'])
        card['present'] = [h for h in native_hints(root) if h['path'] in known]
        card['writes'] = False
        card['contents_read'] = False
        card['discovery_proven'] = False
        return card
"""

TEST_016 = r"""
    @case('X23', 'Карточка адаптера Kilo выдаётся без записи в проект; неизвестная среда отклонена.')
    def test_46_adapter_card(self):
        self.install();before=sorted(q.as_posix() for q in self.a.rglob('*'))
        card=self.call('adapter',dict(name='kilo'))
        self.assertEqual(card['entry'],'AGENTS.md');self.assertEqual(card['entry_fallback'],'AGENT.md')
        self.assertEqual(card['priority']['rank'],3);self.assertEqual([x['rank'] for x in card['priority']['order']],[1,2,3,4])
        self.assertFalse(card['discovery_proven']);self.assertFalse(card['writes'])
        self.assertEqual(before,sorted(q.as_posix() for q in self.a.rglob('*')))
        self.assertRefused('adapter_unknown',self.call,'adapter',dict(name='synthetic-unknown'))

    @case('X24', 'Источники Kilo учитываются без чтения и требуют подтверждения; файлы среды не меняются.')
    def test_47_kilo_sources(self):
        self.install()
        cfg=self.a/'.kilo/kilo.jsonc';cfg.parent.mkdir();cfg.write_bytes(b'{"instructions":["rules/a.md"]}\n')
        rules=self.a/'.kilo/rules';rules.mkdir();(rules/'a.md').write_text('- synthetic rule\n',encoding='utf-8')
        inventory=self.call('inventory');self.assertFalse(inventory['contents_read'])
        self.assertIn('.kilo/kilo.jsonc',[x['path'] for x in inventory['native_paths']])
        self.assertIn('.kilo/rules',[x['path'] for x in inventory['native_paths']])
        card=self.call('adapter',dict(name='kilo'))
        self.assertEqual([x['path'] for x in card['present']],['.kilo/kilo.jsonc','.kilo/rules'])
        self.assertRefused('existing_sources',self.preview,dict(op='connect'))
        self.apply(dict(op='connect',ack_existing=['.kilo/kilo.jsonc','.kilo/rules']))
        self.assertEqual(cfg.read_bytes(),b'{"instructions":["rules/a.md"]}\n')
        self.assertEqual((rules/'a.md').read_text(encoding='utf-8'),'- synthetic rule\n')
        self.evidence['kilo_sources_unchanged']=True

    @case('X25', 'Запасное имя входа Kilo (AGENT.md) тоже требует подтверждения и не перезаписывается.')
    def test_48_kilo_fallback_entry(self):
        self.install();alt=self.a/'AGENT.md';alt.write_text('synthetic fallback entry\n',encoding='utf-8')
        self.assertRefused('existing_sources',self.preview,dict(op='connect'))
        self.apply(dict(op='connect',ack_existing=['AGENT.md']))
        self.assertEqual(alt.read_text(encoding='utf-8'),'synthetic fallback entry\n')
        self.assertEqual((self.a/'AGENTS.md').read_bytes(),(self.kbase/'entry.txt').read_bytes())

    @case('X26', 'Адаптер не пишет в конфигурацию среды ни при каких командах.')
    def test_49_adapter_never_writes_config(self):
        self.install()
        cfg=self.a/'kilo.jsonc';cfg.write_bytes(b'{"synthetic":true}\n')
        rules=self.a/'.kilocode/rules';rules.mkdir(parents=True);(rules/'b.md').write_text('- synthetic\n',encoding='utf-8')
        self.apply(dict(op='connect',ack_existing=['kilo.jsonc','.kilocode/rules']))
        self.call('adapter',dict(name='kilo'));self.call('status');self.call('inventory')
        self.assertEqual(cfg.read_bytes(),b'{"synthetic":true}\n')
        self.assertEqual([q.name for q in rules.iterdir()],['b.md'])
"""

PROTOCOL_016 = r"""

## Адаптер Kilo Code (0.1.6)

Среда Kilo Code читает вход `AGENTS.md` в корне проекта; `AGENT.md` — запасное имя, регистр обязателен. Старшинство источников: промпт агента в конфиге, затем ключ `instructions` в проектном `kilo.jsonc`, затем корневой `AGENTS.md`, затем глобальный `instructions`; навыки подгружаются по требованию. Значит вход комплекта стоит третьим из четырёх, и два источника старше него — оба конфигурация. Каталоги правил среды: `.kilo/rules/` (текущий), `.kilocode/rules/` (совместимость), `.kilocoderules` (наследие). Среда защищает `AGENTS.md` от записи агентом и применяет правки в новых задачах. Команда `adapter` с именем среды выдаёт карточку: вход, старшинство, список источников, что комплект не пишет никогда и что не проверено. Карточка ничего не пишет; присутствие источников показывается, но их содержимое не читается; поле `discovery_proven` всегда `false` — обнаружение и чтение проверяются отдельно, уровнями достоверности, и не выводятся из наличия файла.
"""

README_016 = r"""
## Что изменилось в 0.1.6

Адаптер Kilo Code. Вход комплекта совпадает с входом среды (`AGENTS.md`), но стоит в её старшинстве третьим из четырёх: выше — промпт агента и ключ `instructions` в проектном `kilo.jsonc`. Поэтому появилась команда `adapter`: она отдаёт карточку среды — вход, старшинство, источники (`.kilo/kilo.jsonc`, `.kilo/rules`, `.kilocode/rules`, `.kilocoderules`, `AGENT.md`), что комплект не пишет никогда и что не проверено, — и расширено обнаружение чужих точек входа: перечисленные источники требуют подтверждения до создания входа и остаются байт в байт. Правило тождества не менялось.
"""
