"""Правки выпуска 0.1.13 (И-033): одно событие и две машины — оба решения владельца Б.

1. **P3 → Б.** Единство события проверяется по условиям (`os`, `mode`, `model`, `permissions`), а
   наблюдатель остаётся происхождением. Это уже действующее правило с 0.1.9, но оно нигде не было
   названо данными. Появляется команда `identity`: она перечисляет, что сравнивается, что нет, и
   ссылается на решения И-029 и И-033.
2. **P4 → Б.** Слияние состояния внутри продукта. Два писателя правят один `checks.json`; git даёт
   конфликт содержимого, и разруливать его руками нельзя. Появляется операция `merge`: она читает
   входящий файл проверок (например, версию из другой ветки), объединяет наблюдения по тому же правилу
   тождества, отбрасывает уже известные и записывает результат через обычный план и билет.

Правило тождества не менялось: `merge` использует то же `same_observation`, что и `record_check`.
"""

MERGE_HELPER = '''def merge_checks(local_checks, incoming_checks):
    """0.1.13: объединение наблюдений двух машин по правилу тождества (И-033, решение Б по P4).

    Свои записи остаются на месте и в своём порядке. Из входящих добавляются только те, что ещё не
    известны: совпадение определяется тем же `same_observation`, что и при записи. Ничего не удаляется
    и не переписывается — объединение только добавляет.
    """
    merged = {'schema_version': 1, 'checks': [dict(item) for item in local_checks['checks']]}
    added, duplicates = 0, 0
    for item in incoming_checks['checks']:
        if any(same_observation(existing['observation'], item['observation']) for existing in merged['checks']):
            duplicates += 1
            continue
        merged['checks'].append(dict(item))
        added += 1
    return merged, added, duplicates


'''

MERGE_BRANCH = """    elif op == 'merge':
        exact(r, 'op incoming')
        need(type(r['incoming']) is str, 'path', 'Нужен путь к входящему файлу проверок.')
        raw = read(root, rel(r['incoming']), required=True)
        incoming = check_results(raw)
        local = check_results(p.observe(CHECKS, True))
        merged, added, duplicates = merge_checks(local, incoming)
        p.notes.append({'added': added, 'duplicates': duplicates,
                        'identity': 'CONDITIONS', 'deleted': 0,
                        'incoming': r['incoming'], 'writes_foreign': False})
        if added:
            p.change(CHECKS, encode(merged))
        return p
"""

IDENTITY_COMMAND = """    if command == 'identity':
        # 0.1.13: правило единства события названо данными, а не только абзацем в справочнике.
        exact(payload, '')
        return {'decision': 'Б', 'iteration': 'И-033',
                'compared': list(CONDITIONS), 'ignored': list(OBSERVER),
                'meaning': 'Событие — то, что видел такой-то участник: платформа, режим, модель и права '
                           'входят в тождество, редактор и расширение — происхождение записи.',
                'observer_out_since': '0.1.9', 'identity_since': '0.1.9',
                'declared_not_measured': True, 'writes': False}
"""

CHOICES_OLD = "choices=('status', 'list', 'history', 'updates', 'pending', 'operations', 'inventory', 'adapter', 'brief', 'session', 'plan', 'apply')"
CHOICES_NEW = "choices=('status', 'list', 'history', 'updates', 'pending', 'operations', 'inventory', 'adapter', 'brief', 'identity', 'session', 'plan', 'apply')"

TEST_023 = r"""
    @case('X40', 'Правило единства события названо данными: что сравнивается и что нет.',
          'Решение владельца Б по P3 (И-033).')
    def test_63_identity(self):
        self.install()
        card=self.call('identity')
        self.assertEqual(card['decision'],'Б');self.assertFalse(card['writes'])
        self.assertEqual(card['compared'],list(c.CONDITIONS))
        self.assertEqual(card['ignored'],list(c.OBSERVER))
        self.assertIn('model',card['compared']);self.assertIn('os',card['compared'])
        self.assertIn('extension',card['ignored'])
        env={k:'synthetic' for k in c.ENV_KEYS.split()}
        base=dict(case='одно событие',level=1,conditions='Синтетический проект',expected='Проверка проходит.',
                  actual='Проверка проходит.',status='pass',evidence='tests.log',limits='Синтетика.',
                  environment=dict(env))
        self.apply(dict(op='record_check',observation=dict(base)))
        seen=dict(env,editor='another-editor',editor_version='9',extension='other',extension_version='9',profile='x')
        self.apply(dict(op='record_check',observation=dict(base,environment=seen)))
        self.assertEqual(len(self.call('status')['observations']),1)
        other=dict(env,model='synthetic-b')
        self.apply(dict(op='record_check',observation=dict(base,environment=other)))
        self.assertEqual(len(self.call('status')['observations']),2)

    @case('X41', 'Слияние состояния: входящие наблюдения добавляются, известные отбрасываются.',
          'Решение владельца Б по P4 (И-033); тот же same_observation, что и при записи.')
    def test_64_merge(self):
        self.install();self.apply(dict(op='connect'))
        env={k:'synthetic' for k in c.ENV_KEYS.split()}
        def obs(case,model='synthetic'):
            return dict(case=case,level=1,conditions='Синтетический проект',expected='Проверка проходит.',
                        actual='Проверка проходит.',status='pass',evidence='tests.log',limits='Синтетика.',
                        environment=dict(env,model=model))
        self.apply(dict(op='record_check',observation=obs('сборка локально','local-model')))
        incoming={'schema_version':1,'checks':[
            {'at':'2026-01-02T00:00:00Z','revision':1,'base_version':BASE_VERSION,'adapter_version':None,
             'observation':obs('сборка в облаке','cloud-model')},
            {'at':'2026-01-03T00:00:00Z','revision':1,'base_version':BASE_VERSION,'adapter_version':None,
             'observation':obs('сборка локально','local-model')}]}
        path='.agent-contract/project/checks.incoming.json'
        (self.a/path).write_bytes(c.encode(incoming))
        view=self.preview(dict(op='merge',incoming=path))
        self.assertEqual(view['notes'][0]['added'],1);self.assertEqual(view['notes'][0]['duplicates'],1)
        self.assertEqual(self.apply(dict(op='merge',incoming=path))['outcome'],'committed')
        self.assertEqual(len(self.call('status')['observations']),2)
        self.assertEqual(self.apply(dict(op='merge',incoming=path))['outcome'],'no_change')
        self.assertEqual(len(self.call('status')['observations']),2)
        (self.a/path).write_bytes(c.encode({'schema_version':1,'checks':[{'at':'нет'}]}))
        self.assertRefused('fields',self.preview,dict(op='merge',incoming=path))
        self.assertRefused('path',self.preview,dict(op='merge',incoming='../outside.json'))
"""

PROTOCOL_023 = """

## Одно событие и две машины (0.1.13, решения владельца Б)

**Что считается одним событием.** Сравниваются условия: `os`, `mode`, `model`, `permissions`.
Наблюдатель — `editor`, `editor_version`, `extension`, `extension_version`, `profile` — это
происхождение записи и в сравнение не входит. Поэтому одно событие, увиденное Kilo и Copilot в одном
проекте, — одна запись, а то же событие на другой платформе или другой моделью — два разных факта.
Команда `identity` отдаёт это правило данными: `compared`, `ignored`, `decision: "Б"`.

**Слияние состояния.** Два писателя (локальная машина и облачный агент) правят один
`.agent-contract/project/checks.json`, и git даёт конфликт содержимого. Порядок разрешения:

1. `git pull` — конфликт в `checks.json`. Сначала входящая версия сохраняется файлом
   (`git show :3:.agent-contract/project/checks.json >
   .agent-contract/project/checks.incoming.json`), затем рабочая остаётся локальной
   (`git checkout --ours -- .agent-contract/project/checks.json`);
2. `plan {"op": "merge", "incoming": ".agent-contract/project/checks.incoming.json"}` — показ того, что
   добавится и что уже известно;
3. `apply` с билетом — объединение записывается через обычную операцию с журналом и резервной копией;
4. `git add -A && git commit` — слияние завершено, входящий файл можно удалить.

`merge` только добавляет: известные наблюдения отбрасываются по тому же правилу тождества, ничего не
удаляется и не перезаписывается. Формат входящего файла проверяется целиком; путь не может выйти за
пределы проекта.
"""

README_023 = """
## Что изменилось в 0.1.13

Два решения владельца по обкатке. Событие считается одним по условиям (`os`, `mode`, `model`,
`permissions`), а наблюдатель остаётся происхождением записи — это правило теперь отдаётся данными
командой `identity`. Слияние состояния двух машин стало операцией комплекта: `merge` читает входящий
файл проверок, добавляет неизвестные наблюдения по тому же правилу тождества и ничего не удаляет;
порядок разрешения конфликта git описан в справочнике. Правило тождества не менялось.
"""
