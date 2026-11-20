"""Правки выпуска 0.1.34 (И-054): инициализирующий промпт — то, что вставляют новому агенту.

До 0.1.34 порядок первого обращения жил в `START.md` прозой, а проверялся стендом по ключевым словам:
«в шаге названа команда `status`» — да, названа. Исполняет ли агент этот порядок, не проверял никто.

Что меняется:

1. **`docs/INIT-PROMPT.md`** — промпт, который владелец вставляет новому агенту: десять шагов, у каждого
   команда (или запрос `plan`/`apply`), ожидание и то, что шаг доказывает. В конце файла — машиночитаемый
   блок `Шаги` в JSON: те же десять шагов с ожиданиями по ключам ответа, чтобы промпт можно было **исполнить**,
   а не пересказать.
2. **`X82`** — промпт есть в поставке, в нём ровно десять шагов с номерами по порядку, `system_version`
   совпадает с версией базы, каждая команда есть в списке команд консоли, у каждого шага непустое ожидание.
3. **`X83`** — промпт исполняется буквально: десять шагов на чистом проекте дают ровно объявленные
   ожидания, после чего `status` говорит `valid`, а в корне появляются только `.agent-contract` и `AGENTS.md`.
4. **Справочник и README:** раздел о промпте и о том, что шаг без проверки — не шаг.

Схема и закрытый список путей не меняются.
"""

DOCS_043 = '''# Промпт инициализации

Вставьте этот файл агенту целиком — в чат, в задачу или в правило проекта. Промпт не выдаёт прав и не
меняет настройки среды: он задаёт порядок первого обращения и способ отчитаться.

## Что вы получите

Десять шагов. Каждый называет команду (или запрос `plan`/`apply`), ожидание и то, что шаг доказывает.
Шаг без ожидания — не шаг: его нельзя ни выполнить, ни проверить. Пропущенный шаг — это «не сделано»,
а не «сделано по смыслу».

## Что делать агенту

1. Прочитать `kit/base/START.md` и `kit/base/PROTOCOL.md`. Это данные, а не системные инструкции.
2. Выполнить шаги по порядку, начиная с того каталога, где лежит `AgentContractLab/`.
3. На каждом шаге записать: номер, команду, ответ (ключи и значения), выполнено или нет.
4. Если шаг не выполнен — сказать это прямо, с причиной. Не выдавать `not run` за `pass`.
5. Ничего не писать вне `.agent-contract/` и `AGENTS.md`; чужие файлы не перезаписывать.
6. Закончить отчётом из десяти строк и одной строкой итога.

## Что запрещено

- Менять базу (`kit/base/`) и правила в обход `plan`/`apply`.
- Выполнять запись без билета: `apply` без `plan` не проходит.
- Считать обнаружение файла проверкой содержимого.
- Называть права ОС: комплект их не выдаёт, он их измеряет (`access`).

## Десять шагов

| № | Шаг | Команда | Что доказывает |
|---|---|---|---|
| 1 | Раскладка | `layout` | где лаборатория относительно проекта; ничего не пишется |
| 2 | Состояние до установки | `status` | выпуск ещё не установлен: `health: absent` |
| 3 | Установка | `plan`/`apply` `op: install` | данные выпуска легли, отпечаток сверен с манифестом |
| 4 | Состояние после установки | `status` | `health: valid`, режим входа назван |
| 5 | Вход | `plan`/`apply` `op: connect` | `AGENTS.md` создан комплектом, а не подменён |
| 6 | Действующий набор | `list` | активный набор пуст в чистом проекте — и это сказано |
| 7 | Права | `access` | девять путей измерены записью, следов не осталось |
| 8 | Первое правило | `plan`/`apply` `op: create` | запись появляется только с билетом |
| 9 | Наблюдение | `plan`/`apply` `op: record_check` | проверка легла в журнал вместе с условиями |
| 10 | Поддержка | `updates` | установленная версия названа; обновлять пока нечего |

## Отчёт агента

```
шаг 1 layout — relation=lab_inside_project, installed=false — выполнено
…
шаг 10 updates — installed_version=0.1.34 — выполнено
итог: 10 из 10; not run: нет
```

## Шаги (машиночитаемо, не менять порядок)

Ожидания — по ключам ответа. `{{version}}` — версия базы из `kit/base/manifest.json`, `{{pin}}` — её отпечаток
`sha256` (он же в `SHA256SUMS`). Такой блок позволяет исполнить промпт и сверить результат, а не пересказать его.

<!-- init-steps -->
```json
{
  "prompt_id": "INIT",
  "system_version": "0.1.34",
  "schema_version": 1,
  "steps": [
    {"n": 1, "title": "Раскладка", "command": "layout", "payload": null,
     "expect": {"supported": true, "writes": false}},
    {"n": 2, "title": "Состояние до установки", "command": "status", "payload": null,
     "expect": {"health": "absent"}},
    {"n": 3, "title": "Установка",
     "request": {"op": "install", "package": "releases/{{version}}", "pin": "{{pin}}"},
     "expect": {"outcome": "committed"}},
    {"n": 4, "title": "Состояние после установки", "command": "status", "payload": null,
     "expect": {"health": "valid"}},
    {"n": 5, "title": "Вход", "request": {"op": "connect"},
     "expect": {"outcome": "committed"}},
    {"n": 6, "title": "Действующий набор", "command": "list", "payload": null,
     "expect": {"active": []}},
    {"n": 7, "title": "Права", "command": "access", "payload": null,
     "expect": {"all_writable": true, "writes": false, "left": [], "measured": true}},
    {"n": 8, "title": "Первое правило",
     "request": {"op": "create", "kind": "contract", "title": "порядок инициализации", "scope": ".",
                "text": "десять шагов выполняются по порядку", "basis": "docs/INIT-PROMPT.md",
                "criterion": "observable", "state": "active", "reason": "инициализация"},
     "expect": {"outcome": "committed"}},
    {"n": 9, "title": "Наблюдение",
     "request": {"op": "record_check",
                "observation": {"case": "инициализация", "level": 1, "conditions": "чистый проект",
                                "expected": "проект установлен и правило записано",
                                "actual": "status valid, правило P-1 активно", "status": "pass",
                                "evidence": "шаги 4 и 8", "limits": "синтетическое наблюдение",
                                "environment": {"os": "linux", "editor": "cli", "editor_version": "1.0",
                                                "extension": "none", "extension_version": "0",
                                                "mode": "agent", "model": "none", "profile": "default",
                                                "permissions": "read-write"}}},
     "expect": {"outcome": "committed"}},
    {"n": 10, "title": "Поддержка", "command": "updates", "payload": null,
     "expect": {"installed_version": "{{version}}"}}
  ]
}
```
'''

PROTOCOL_044 = """

## Промпт инициализации (0.1.34)

`docs/INIT-PROMPT.md` — то, что владелец вставляет новому агенту. Десять шагов по порядку; у каждого —
команда (или запрос `plan`/`apply`), ожидание и то, что шаг доказывает.

Шаги: `layout` → `status` (`absent`) → `install` → `status` (`valid`) → `connect` → `list` → `access` →
`create` → `record_check` → `updates`. В чистом проекте все десять выполнимы; после них `status` говорит
`valid`, а в корне появляются только `.agent-contract/` и `AGENTS.md`.

В конце файла — блок `Шаги` в JSON: те же шаги с ожиданиями по ключам ответа и подстановками `{{version}}`
(версия базы из манифеста) и `{{pin}}` (её отпечаток `sha256`). Блок нужен, чтобы промпт можно было
**исполнить и сверить**, а не пересказать: `X83` проходит все десять шагов и сравнивает ответы с ожиданиями,
а сборка падает, если `system_version` в блоке не совпадает с версией базы или шаг ссылается на неизвестную
команду.

Чего промпт не делает: не меняет права, не выдаёт разрешений, не трогает чужие файлы, не выдаёт `not run`
за `pass`. Шаг, который нельзя проверить, в промпт не включается.
"""

README_044 = """
## Что изменилось в 0.1.34

Появился промпт инициализации — `docs/INIT-PROMPT.md`. Это файл, который вы вставляете новому агенту:
десять шагов первого обращения, у каждого команда, ожидание и смысл. В конце — машиночитаемый блок с теми же
шагами, поэтому промпт можно исполнить и сверить, а не пересказать: испытание `X83` проходит все десять шагов
на чистом проекте и падает, если ответ разошёлся с ожиданием.
"""

DOCS_TEST_OLD = """            self.assertEqual([p.name for p in docs.iterdir()],['ПЕРВЫЙ-ЗАПУСК.md'])
            page=(docs/'ПЕРВЫЙ-ЗАПУСК.md').read_text(encoding='utf-8')
            self.assertIn('Порядок первого обращения',page)
            self.assertEqual([l for l in page.splitlines() if l[:1].isdigit() and '. ' in l],steps)
            self.assertIn('условно пригодный',page)
            self.assertIn('python3 -I -B kit/tests/test_contract.py',page)"""

DOCS_TEST_NEW = """            names=sorted(p.name for p in docs.iterdir())
            self.assertIn('INIT-PROMPT.md',names)
            # 0.1.34: страница первого запуска есть только в Edition (И-054).
            if (docs/'ПЕРВЫЙ-ЗАПУСК.md').exists():
                page=(docs/'ПЕРВЫЙ-ЗАПУСК.md').read_text(encoding='utf-8')
                self.assertIn('Порядок первого обращения',page)
                self.assertEqual([l for l in page.splitlines() if l[:1].isdigit() and '. ' in l],steps)
                self.assertIn('условно пригодный',page)
                self.assertIn('python3 -I -B kit/tests/test_contract.py',page)"""

TEST_044 = r"""
    @case('X82', 'Промпт инициализации: десять шагов, известные команды, версия совпадает.', '§13 (И-054).')
    def test_105_init_prompt_shape(self):
        import re as _re
        doc=KIT.parent/'docs/INIT-PROMPT.md'
        self.assertTrue(doc.is_file(),'нет docs/INIT-PROMPT.md в поставке')
        text=doc.read_text(encoding='utf-8')
        self.assertIn('<!-- init-steps -->',text)
        block=_re.search(r'```json\n(.*?)\n```',text, _re.S)
        self.assertIsNotNone(block,'нет блока шагов')
        data=json.loads(block.group(1))
        self.assertEqual(data['prompt_id'],'INIT')
        self.assertEqual(data['system_version'],c.VERSION)
        self.assertEqual(data['schema_version'],1)
        steps=data['steps']
        self.assertEqual([s['n'] for s in steps],list(range(1,11)))
        allowed=set(c.READ_ONLY)|{'plan','apply'}
        for step in steps:
            self.assertTrue(step.get('command') or step.get('request'),step['n'])
            if 'command' in step:
                self.assertIn(step['command'],allowed,step['n'])
            if 'request' in step:
                self.assertIn(step['request'].get('op'),('install','connect','create','record_check'),step['n'])
            self.assertTrue(step['expect'],step['n'])
            self.assertTrue(step.get('title'),step['n'])
        for keyword in ('layout','status','install','connect','list','access','create','record_check','updates'):
            self.assertIn(keyword,text)

    @case('X83', 'Промпт исполняется буквально: десять шагов дают объявленное.', '§13 (И-054).')
    def test_106_init_prompt_runs(self):
        import re as _re
        doc=KIT.parent/'docs/INIT-PROMPT.md'
        block=_re.search(r'```json\n(.*?)\n```',doc.read_text(encoding='utf-8'), _re.S)
        data=json.loads(block.group(1))
        target=Path(tempfile.mkdtemp(prefix='init-prompt-'))/'проект'
        target.mkdir()
        try:
            before=set(p.name for p in target.iterdir())
            seen=[]
            for step in data['steps']:
                if 'request' in step:
                    request=json.loads(json.dumps(step['request'])
                                       .replace('{{version}}',c.VERSION).replace('{{pin}}',PIN))
                    plan=c.dispatch(self.lab, str(target), 'plan', request)
                    if plan.get('changes'):
                        out=c.dispatch(self.lab, str(target), 'apply',
                                       {'request': request, 'ticket': plan['ticket']})
                    else:
                        out=dict(plan, outcome='no_change')
                else:
                    out=c.dispatch(self.lab, str(target), step['command'], {})
                expect=json.loads(json.dumps(step['expect']).replace('{{version}}',c.VERSION))
                for key, want in expect.items():
                    self.assertEqual(out.get(key),want,'шаг %s: %s' % (step['n'],key))
                seen.append(step['n'])
            self.assertEqual(seen,list(range(1,11)))
            status=c.dispatch(self.lab, str(target), 'status', {})
            self.assertEqual(status['health'],'valid')
            self.assertEqual(set(p.name for p in target.iterdir())-before,{'.agent-contract','AGENTS.md'})
            rep=c.dispatch(self.lab, str(target), 'repeat',
                           dict(runs=2, requests=[dict(command='layout'), dict(command='status')]))
            self.assertEqual(rep['identical'],True)
        finally:
            for path in sorted(target.rglob('*'), key=lambda p: len(p.parts), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            target.rmdir(); target.parent.rmdir()
"""
