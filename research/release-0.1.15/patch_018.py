"""Правки выпуска 0.1.8 (И-028): заглушки остальных сред. Только тексты."""

DISPATCH_OLD = r"""        card = dict(ADAPTERS[payload['name']])
        card['priority'] = dict(card['priority'])"""

DISPATCH_NEW = r"""        card = dict(ADAPTERS[payload['name']])
        if 'priority' in card:
            card['priority'] = dict(card['priority'])"""

STUB_BLOCK = r"""# --- 0.1.8: заглушки остальных сред (И-028) -----------------------------------------
# Среда объявлена по имени, но её факты не сверялись и адаптер не реализован. Заглушка отвечает
# ровно это и ничего больше: у неё нет входа, старшинства, источников и покрытия. Отличие от
# «неизвестной среды» в том, что имя известно, а обещаний нет ни одного.
STUB_ENVIRONMENTS = (('claude', 'Claude Code'), ('cursor', 'Cursor'), ('antigravity', 'Antigravity'))
for _name, _title in STUB_ENVIRONMENTS:
    ADAPTERS[_name] = {
        'name': _name,
        'title': _title,
        'status': 'stub',
        'entry': None,
        'entry_recommended': None,
        'entry_shared': None,
        'sources': [],
        'never_writes': [],
        'environment_facts': {},
        'coverage': {'reads_agents_md': [], 'coverage_gap': ['не измерялось: адаптер не реализован']},
        'not_proven': ['adapter_implemented', 'auto-discovery', 'content_was_read', 'behaviour_with_model'],
        'discovery_proven': False,
        'facts_checked_at': None,
        'note': 'Заглушка: среда объявлена по имени; факты не сверялись, адаптер не реализован. '
                'Вход не создаётся, конфигурация среды не читается.',
    }
ADAPTERS['kilo'].update(status='documented', facts_checked_at='2026-11-18')
ADAPTERS['copilot'].update(status='documented', facts_checked_at='2026-11-18')


"""

TEST_018 = r"""
    @case('X31', 'Заглушки: имя среды объявлено, но карточка не заявляет ни входа, ни покрытия.')
    def test_54_stub_cards(self):
        self.install()
        for name in ('claude','cursor','antigravity'):
            card=self.call('adapter',dict(name=name))
            self.assertEqual(card['status'],'stub');self.assertIsNone(card['entry'])
            self.assertEqual(card['sources'],[]);self.assertEqual(card['present'],[])
            self.assertIsNone(card['facts_checked_at'])
            self.assertIn('adapter_implemented',card['not_proven'])
            self.assertFalse(card['discovery_proven']);self.assertFalse(card['writes'])
        self.assertEqual(self.call('adapter',dict(name='kilo'))['status'],'documented')
        self.assertEqual(self.call('adapter',dict(name='copilot'))['status'],'documented')
        self.assertRefused('adapter_unknown',self.call,'adapter',dict(name='synthetic-unknown'))
        self.apply(dict(op='connect'))
        self.assertTrue((self.a/'AGENTS.md').exists())
"""

PROTOCOL_018 = """

Заглушка среды — это карточка с полем `status: "stub"`: имя среды известно, факты не сверялись, адаптер не реализован. У заглушки нет входа (`entry: null`), нет старшинства, нет источников и нет покрытия (`sources: []`, `coverage.reads_agents_md: []`), а `not_proven` начинается с `adapter_implemented`. Отличие от отказа `adapter_unknown` в том, что имя известно и ответ осмысленный: «среда объявлена, обещаний нет». Заглушка не участвует в создании входа и не меняет список обнаружения: наличие файлов чужой среды по-прежнему требует подтверждения `ack_existing`, потому что обнаружение общее, а не адаптерное. У проверенных сред (`kilo`, `copilot`) стоит `status: "documented"` и дата сверки `facts_checked_at`: их факты сверены с документацией среды на эту дату, а обнаружение по-прежнему не доказано (`discovery_proven: false`)."""

README_018 = """
## Что изменилось в 0.1.8

Остальные среды объявлены заглушками, а не адаптерами. У `claude`, `cursor` и `antigravity` карточка отвечает `status: "stub"`: имя известно, входа нет, старшинства нет, покрытия нет, первый пункт `not_proven` — `adapter_implemented`. Проверенные среды помечены `status: "documented"` и датой сверки фактов, при этом обнаружение остаётся недоказанным. Заглушка ничего не отменяет: обнаружение чужих источников общее, поэтому их наличие по-прежнему требует подтверждения `ack_existing`, а вход по-прежнему один — `AGENTS.md`.
"""
