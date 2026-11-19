"""Правки выпуска 0.1.15 (И-035): достоверность, уровень 2 — обнаружение как данные.

Комплект умеет отвечать, какой вход существует в проекте и какой из них среда прочитает первым по
своему документированному порядку. Это **не** проверка живой среды: карточка прямо говорит, что
обнаружение объявлено, а не доказано (`discovery_proven: false`), а уровни 2, 3 и 5 остаются `not run`.

Новая команда `discovery` ничего не пишет и не читает содержимое чужих файлов: только наличие и имена.
Заглушки (Claude Code, Cursor, Antigravity) отказывают `adapter_stub` — их порядок не сверялся.
"""

DISCOVERY_ORDER = '''
# --- 0.1.15: обнаружение как данные (И-035, уровень достоверности 2) --------------------
# Порядок старшинства из карточек сред, приведённый к путям. Учитывается только наличие: содержимое
# конфигураций сред (например, ключ `instructions` внутри kilo.jsonc) не читается — это объявленный
# пробел, а не проверка. Глобальные уровни (личные и организационные инструкции) в проект не входят.
DISCOVERY_ORDER = {
    'kilo': [
        {'rank': 2, 'path': '.kilo/kilo.jsonc', 'source': 'instructions key in project kilo.jsonc',
         'limits': 'проверяется только наличие файла, ключ внутри не читается'},
        {'rank': 3, 'path': ENTRY, 'source': 'root AGENTS.md', 'limits': None},
    ],
    'copilot': [
        {'rank': 2, 'path': '.github/instructions', 'source': 'path-specific *.instructions.md',
         'limits': 'каталог с applyTo-файлами; содержимое не читается'},
        {'rank': 3, 'path': '.github/copilot-instructions.md', 'source': 'repository instructions',
         'limits': None},
        {'rank': 4, 'path': ENTRY, 'source': 'AGENTS.md (agent instructions)', 'limits': None},
    ],
}


def discovery(root, name):
    """0.1.15: что найдено и что среда прочитает первой — по объявленному порядку, без живых сред."""
    card = ADAPTERS.get(name)
    need(card is not None, 'adapter_unknown', 'Неизвестная среда: карточка не выдаётся.',
         sorted(ADAPTERS))
    need(card.get('status') == 'documented', 'adapter_stub',
         'Карточка-заглушка: порядок обнаружения не сверялся, отвечать нечем.', {'environment': name})
    present = {h['path']: h['kind'] for h in native_hints(root)}
    try:
        st = safe(root, ENTRY).lstat()
        present[ENTRY] = 'directory' if stat.S_ISDIR(st.st_mode) else 'file'
    except FileNotFoundError:
        pass
    order, chosen = [], None
    for step in DISCOVERY_ORDER[name]:
        found = step['path'] in present
        order.append({'rank': step['rank'], 'path': step['path'], 'source': step['source'],
                      'present': found, 'kind': present.get(step['path']), 'limits': step['limits']})
        if found and chosen is None:
            chosen = step['path']
    others = sorted(p for p in present if p not in {s['path'] for s in DISCOVERY_ORDER[name]})
    return {'environment': name, 'title': card['title'], 'entry': ENTRY,
            'found': sorted(present), 'order': order, 'chosen': chosen,
            'chosen_rank': next((o['rank'] for o in order if o['path'] == chosen), None),
            'entry_present': ENTRY in present, 'contract_installed': read(root, STATE) is not None,
            'other_hints': others,
            'levels': {'1_file_present': 'pass' if present else 'fail',
                       '2_environment_found': 'not run', '3_content_read': 'not run',
                       '5_behavior_repeatable': 'not run'},
            'measured': ['file_present', 'names'], 'declared_only': ['environment_found', 'content_read'],
            'contents_read': False, 'discovery_proven': False, 'writes': False,
            'note': 'Это обнаружение по документированному порядку, а не проверка живой среды: '
                    'уровни 2, 3 и 5 не измерялись. Содержимое чужих файлов не читается.'}
'''

DISCOVERY_BRANCH = """    if command == 'discovery':
        # 0.1.15: обнаружение названо данными, но не выдаётся за проверку (И-035, уровень 2).
        exact(payload, 'environment')
        return discovery(root, payload['environment'])
"""

CHOICES_OLD = "choices=('status', 'list', 'history', 'updates', 'pending', 'operations', 'inventory', 'adapter', 'brief', 'identity', 'session', 'plan', 'apply')"
CHOICES_NEW = "choices=('status', 'list', 'history', 'updates', 'pending', 'operations', 'inventory', 'adapter', 'brief', 'identity', 'discovery', 'session', 'plan', 'apply')"

STDIN_OLD = "        if args.command in ('session', 'plan', 'apply', 'adapter'):"
STDIN_NEW = "        if args.command in ('session', 'plan', 'apply', 'adapter', 'discovery'):"

TEST_025 = r"""
    @case('X44', 'Обнаружение названо данными и не выдаётся за проверку.', 'Уровень достоверности 2 (И-035).')
    def test_67_discovery(self):
        self.install();self.apply(dict(op='connect'))
        card=self.call('discovery',dict(environment='kilo'))
        self.assertEqual(card['environment'],'kilo');self.assertFalse(card['writes'])
        self.assertFalse(card['contents_read']);self.assertFalse(card['discovery_proven'])
        self.assertEqual(card['chosen'],'AGENTS.md');self.assertEqual(card['chosen_rank'],3)
        self.assertIn('AGENTS.md',card['found'])
        self.assertEqual(card['levels']['1_file_present'],'pass')
        for level in ('2_environment_found','3_content_read','5_behavior_repeatable'):
            self.assertEqual(card['levels'][level],'not run')
        before=snapshot(self.a)
        self.call('discovery',dict(environment='kilo'))
        self.assertEqual(snapshot(self.a),before)
        (self.a/'AGENTS.md').unlink()
        gone=self.call('discovery',dict(environment='kilo'))
        self.assertIsNone(gone['chosen']);self.assertEqual(gone['levels']['1_file_present'],'fail')

    @case('X45', 'Старшинство обнаружения: выигрывает старший существующий вход.', 'И-035; карточки сред.')
    def test_68_discovery_order(self):
        self.install()
        (self.a/'.github').mkdir()
        (self.a/'.github/copilot-instructions.md').write_text('synthetic\n',encoding='utf-8')
        (self.a/'AGENTS.md').write_text('synthetic entry\n',encoding='utf-8')
        copilot=self.call('discovery',dict(environment='copilot'))
        self.assertEqual(copilot['chosen'],'.github/copilot-instructions.md')
        self.assertEqual(copilot['chosen_rank'],3)
        self.assertIn('AGENTS.md',copilot['found'])
        kilo=self.call('discovery',dict(environment='kilo'))
        self.assertEqual(kilo['chosen'],'AGENTS.md')
        self.assertIn('.github/copilot-instructions.md',kilo['other_hints'])
        self.assertRefused('adapter_stub',self.call,'discovery',dict(environment='claude'))
        self.assertRefused('adapter_unknown',self.call,'discovery',dict(environment='none'))
        self.assertRefused('fields',self.call,'discovery',dict(environment='kilo',extra=1))
"""

PROTOCOL_025 = """

## Обнаружение как данные (0.1.15)

`discovery {"environment": "kilo"}` отвечает на два вопроса: какие объявленные входы существуют в
проекте (`found`) и какой из них среда прочитает первым по своему документированному порядку (`chosen`,
`chosen_rank`, `order`). Файлы только перечисляются: содержимое конфигураций и чужих входов не читается,
ничего не пишется (`writes: false`).

Это **не** проверка живой среды. Уровень 1 (файл есть) измерен, уровень 2 (среда действительно нашла)
и уровень 3 (содержимое прочитано) остаются `not run`; карточка всегда несёт `discovery_proven: false`.
Заглушки (Claude Code, Cursor, Antigravity) отказывают `adapter_stub`: их порядок не сверялся, отвечать
нечем.
"""

README_025 = """
## Что изменилось в 0.1.15

Появилась команда `discovery`: она показывает, какие объявленные входы существуют в проекте и какой из
них среда прочитает первым по документированному старшинству. Обнаружение названо данными и не выдаётся
за проверку — `discovery_proven: false`, уровни 2, 3 и 5 остаются `not run`. Заглушки отказывают
`adapter_stub`. Правило тождества и операции не менялись.
"""
