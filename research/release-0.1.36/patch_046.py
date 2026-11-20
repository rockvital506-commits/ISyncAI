"""И-056: README-вектор (<= 24 КБ, каждое утверждение с якорем) и TRACEABILITY.json (§2…§18).

Здесь только текст и данные: сборка (build.py) подставляет версию и число испытаний, кладёт README и
трассировку в дерево, вставляет тесты X87–X89 и раздел PROTOCOL. Якорь — ссылка, которую можно проверить:
тест разрешает каждый якорь в файле поставки и падает, если якорь ведёт в никуда.
"""
import json

README_VECTOR = """# Agent Contract Kit • {{version}}

Самостоятельный офлайн-комплект для контрактов между владельцем, проектом и AI-агентом. В чистом выпуске **0 контрактов, 0 пользовательских правил, 0 настроек и 0 пользовательских протоколов**; отсутствуют профили, входы, установленные интеграции и выдуманные успешные проверки. Это описание смысла, а не второй свод правил: правила живут в `kit/base/`, здесь — только вектор и якоря на них. [manifest]

**Правило якорей.** Каждое нормативное утверждение этой памятки заканчивается якорем в квадратных скобках: имя файла и фраза (`START: …`), номер испытания (`X84`), идентификатор промпта (`K2`) или имя файла данных (`manifest`). Якорь проверяет сборка: тест `X87` разрешает каждый из них в файле поставки и падает, если якорь ведёт в никуда или если утверждение осталось без якоря. Поэтому README не может тихо разойтись с `START.md` и `PROTOCOL.md`. [X87]

## Оглавление

- [Как читать якоря](#как-читать-якоря)
- [Если вы пользователь](#если-вы-пользователь)
- [Если вы агент](#если-вы-агент)
- [Если вы проверяющий](#если-вы-проверяющий)
- [Границы и запреты](#границы-и-запреты)
- [Смыслы файлов](#смыслы-файлов)
- [Команды и что они доказывают](#команды-и-что-они-доказывают)
- [Чего нет](#чего-нет)

## Как читать якоря

Якорь — ссылка, которую можно проверить. Форматов немного, и у каждого свой адресат: [START: Показать до записи]

| Формат | Куда ведёт | Пример из этого файла |
|---|---|---|
| `START: фраза` | строка короткого входа `kit/base/START.md` | [START: Обнаружение — не проверка] |
| `PROTOCOL: фраза` | строка полного руководства `kit/base/PROTOCOL.md` | [PROTOCOL: регистр] |
| `INIT: фраза` | строка промпта для нового агента `docs/INIT-PROMPT.md` | [INIT: десять шагов] |
| `КАЛИБРОВКА: фраза` | строка описания калибровки `docs/КАЛИБРОВКА.md` | [КАЛИБРОВКА: отпечат] |
| `X84` | испытание с этим номером в `kit/tests/test_contract.py` | [X84] |
| `K2` | промпт калибровки в `kit/calibration.json` | [K2] |
| `manifest`, `schema`, `rules`, `entry` | шесть файлов данных `kit/base/` | [schema] |
| `CHECKS`, `PIPELINE`, `SUMS`, `TRACE` | отчёты, ведомость отпечатков, трассировка | [SUMS] |

Якорь — не украшение: сборка не выпускает архив, если якорь не разрешился или строка с утверждением осталась без якоря. [X87]

## Если вы пользователь

Десять фраз, десять последствий. Слева — то, что вы говорите агенту; справа — что произойдёт и чем это подтверждено. [START: Порядок первого обращения]

| Вы говорите | Что произойдёт | Якорь |
|---|---|---|
| «Проверь, что установлено» | `status` называет выпуск, ревизию, режим входа и здоровье профиля; чтение ничего не пишет | [START: Обнаружение — не проверка] |
| «Покажи действующие правила» | `list` отдаёт действующий набор в применимой области, `history` — что и когда менялось | [START: Действующие правила] |
| «Какая версия и откуда» | `updates` называет установленную базу и доступные обновления; `manifest.json` — отпечатки шести файлов данных | [START: Версии и происхождение] |
| «Что считается одним событием» | `identity` отдаёт правило данными: сравниваются `os`, `mode`, `model`, `permissions`, а редактор и расширение — происхождение записи | [START: Что считается одним событием] |
| «Что эта среда умеет» | `adapter --name <среда>` возвращает карточку: путь входа, старшинство, названные пробелы; для Claude Code, Cursor и Antigravity — честная заглушка | [START: Ограничения среды] |
| «У меня уже есть свой AGENTS.md» | `brief` отдаёт одну строку для вашего файла, `status` называет режим `foreign`; чужой файл не присваивается | [START: Конфликты с чужими инструкциями] |
| «Покажи, что изменится» | `plan` возвращает список изменений и билет; пока вы не согласились, не записано ничего | [START: Показать до записи] |
| «Запиши, что я проверил» | `record_check` кладёт наблюдение в проектные проверки вместе с объявленной вами средой; запись `pass` без наблюдения — декларация, а не проверка | [START: Запись наблюдения] |
| «Перенеси на другой компьютер» | переносится база и данные проекта; путь проекта задаётся абсолютным, а раскладка «архив распакован в корень проекта» названа данными | [PROTOCOL: раскладк] |
| «Проверь, что ты понял так же, как я» | `calibrate` даёт четыре промпта с известным ответом; ваш ответ записывается до сравнения и сверяется по отпечаткам, а не по прозе | [КАЛИБРОВКА: отпечат] |

Установка одна и та же на любой машине: распакуйте архив, откройте каталог лаборатории и выполните `install`; общий для агентов вход появляется только после одобренного `connect`. [PROTOCOL: второй вход]

Права комплект не выдаёт, а измеряет: `access` пробует каждый из десяти путей записи собственной пробой и честно отвечает `writable: false` с причиной, если каталог закрыт. [PROTOCOL: права]

## Если вы агент

Вы получаете тот же комплект и тот же порядок. Десять шагов ниже — это не пожелание, а исполнимый список: у каждого шага есть команда, ожидание и якорь. [INIT: десять шагов]

| Шаг | Команда | Что доказывает | Якорь |
|---|---|---|---|
| 1 | `layout` | где лаборатория относительно проекта, установлено ли что-то | [INIT: layout] |
| 2 | `status` | до установки профиль отсутствует — это нормальное состояние, а не ошибка | [INIT: status] |
| 3 | `install` | данные установлены, вход агента ещё не создан | [INIT: install] |
| 4 | `status` | после установки профиль `valid`, режим входа назван | [INIT: valid] |
| 5 | `connect` | общий вход появился и он ваш; при занятом входе — режим `foreign` | [INIT: connect] |
| 6 | `list` | действующий набор пуст, пока правил нет | [INIT: list] |
| 7 | `access` | права на десять путей записи измерены, а не объявлены | [INIT: access] |
| 8 | `create` | запись правила проходит `plan` → `apply` с билетом, а не по вашей уверенности | [INIT: create] |
| 9 | `record_check` | наблюдение записано вместе с объявленной средой | [INIT: record_check] |
| 10 | `updates` | установленная база и доступные обновления названы | [INIT: updates] |

Калибровка — отдельный вход, а не экзамен: `calibrate` даёт промпты `K1`…`K4`, ваш ответ пишется в `local/calibration/answers.json` **до** сравнения, вердикт считается только по каноническим `facts`, повтор разрешён один раз и только при расхождении по данным. [K3]

Чего агент не делает никогда: не переписывает файлы базы и правила «для исправления», не создаёт второй реестр, не выдаёт обнаружение за проверку, не объявляет успех без наблюдения, не трогает пути вне закрытого списка. [PROTOCOL: посторонн]

## Если вы проверяющий

`pass` — это выполненное утверждение с названным наблюдением, а не зелёная строка. Отчёт этой сборки: **{{pass_total}} `pass`, 0 `fail`, 3 `not run`**; три `not run` — честные (см. «Чего нет»), а не пропущенные. [CHECKS]

Повторить у себя: `python -I -B kit/tests/test_contract.py`; раннер создаёт свой каталог `runs/`, не использует ваши проекты как полигон и не требует сети. [PROTOCOL: тест]

Что уже измерено: реестр и контракты, машина состояний из 32 пар, перенос, конфликты при слиянии, миграция формата 0 → 1, защита от устаревшего плана, два процесса записи, побайтовое восстановление, регистр и длина имени, права, раскладка, промпт инициализации, калибровка. [PIPELINE]

Калибровка проверяет понимание комплекта, а не качество рассуждения модели: вердикт по `facts`, проза — для человека. Эталоны лежат отдельным архивом и только отпечатками, поэтому подсмотреть ответ можно, а скопировать — нет. [КАЛИБРОВКА: эталон]

## Границы и запреты

| Граница | Что это значит | Якорь |
|---|---|---|
| Согласие обязательно | запись только через `plan` → `apply` с билетом; изменение метаданных аннулирует билет | [START: Показать до записи] |
| Один вход | второй вход не создаётся, чужой `AGENTS.md` не присваивается даже с подтверждением | [PROTOCOL: второй вход] |
| Закрытый список путей | комплект пишет только в `.agent-contract/` и `AGENTS.md`; десять путей перечислены | [PROTOCOL: права] |
| Посторонний файл | запись в служебном каталоге, которой комплект не делал, останавливает изменения, но не чтение | [PROTOCOL: посторонн] |
| Объявление ≠ факт | права, обнаружение и здоровье — измерения с моментом времени, а не обещания | [PROTOCOL: отпечат] |
| Нет молчаливого победителя | при пересечении противоречивых требований видны оба; автоматического приоритета нет | [START: молчаливого победителя] |
| Чужое не переписывается | неизвестный формат, чужая схема и чужая правка входа блокируют запись | [PROTOCOL: схем] |
| Повтор — только чтение | серия чтений повторяема; запись по повтору отклоняется | [PROTOCOL: повтор] |
| Ограничения ОС — данные | регистр и длина имени проверяются до записи, а не после ошибки | [PROTOCOL: регистр] |
| Никаких фоновых действий | комплект не работает сам, не ходит в сеть и не вызывает модель | [PROTOCOL: миграци] |

## Смыслы файлов

| Файл | Смысл | Что проверяемо |
|---|---|---|
| `kit/base/START.md` | короткий вход: что читать, в каком порядке, что доказывает шаг | [START: автономный формат данных] |
| `kit/base/PROTOCOL.md` | полная механика: поля, коды отказа, сценарии, ограничения | [PROTOCOL: схема] |
| `kit/base/schema.json` | формат №1: какие поля и состояния допустимы | [schema] |
| `kit/base/rules.json` | канонический реестр правил; в чистом выпуске пуст | [rules] |
| `kit/base/entry.txt` | шаблон общего входа, по умолчанию неактивен | [entry] |
| `kit/base/manifest.json` | состав и происхождение базы, отпечатки шести файлов | [manifest] |
| `kit/calibration.json` | четыре промпта K1–K4 и отпечатки эталонных фактов без значений | [K1] |
| `kit/tools/contract.py` | исполняемый механизм, только стандартная библиотека, локальный JSON-интерфейс | [X87] |
| `docs/INIT-PROMPT.md` | промпт, который вставляют новому агенту; машиночитаемые шаги с ожиданиями | [INIT: промпт] |
| `docs/КАЛИБРОВКА.md` | тексты промптов и формат ответа; проза вынесена отдельно | [КАЛИБРОВКА: промпт] |
| `TRACEABILITY.json` | покрытие §2…§18: раздел → артефакт → испытание | [TRACE] |
| `reports/CHECKS.json`, `reports/PIPELINE.json` | результаты именно этой сборки и сквозной имитации; в проект не переносятся | [CHECKS] |
| `SHA256SUMS` | отпечатки файлов архива; это не электронная подпись | [SUMS] |
| `releases/0.1.0/` | неизменённый предок: те же шесть файлов данных; вся цепочка до предыдущего выпуска лежит рядом | [releases/0.1.0] |

## Команды и что они доказывают

| Команда | Режим | Что доказывает | Отказ |
|---|---|---|---|
| `status` | чтение | профиль установлен, здоров, режим входа назван | [PROTOCOL: обнаружение] |
| `layout` | чтение | где лаборатория относительно проекта | [PROTOCOL: layout] |
| `list`, `history`, `removed` | чтение | действующий набор, изменения, следы удаления | [PROTOCOL: журнал] |
| `rights`, `access` | чтение | что читается, что пишется, и права на десять путей измерены | [PROTOCOL: права] |
| `system` | чтение | файловая система, регистр, объявленные лимиты | [PROTOCOL: регистр] |
| `metrics` | чтение | стоимость и шум по машине состояний; сравнение двух сценариев | [PROTOCOL: стоимость] |
| `calibrate` | чтение | промпты, карточка, сравнение по отпечаткам, отчёт | [КАЛИБРОВКА: ответ] |
| `plan`, `apply` | запись | изменение с билетом и согласием; отказ до записи при нарушении границы | [PROTOCOL: билет] |
| `restore`, `undo` | запись | восстановление из журнала; отмена решения, а не стирание истории | [PROTOCOL: восстановление] |
| `update`, `migrate` | запись | трёхстороннее сравнение и преобразование формата 0 → 1 | [PROTOCOL: миграци] |

## Чего нет

Честный список: этого в комплекте нет, и он этого не обещает — проверено здесь и сейчас, а не «вообще». [X89]

- **Windows junction** — проверка reparse point не выполнена: здесь Linux (`X14`). [X14]
- **Два настоящих сеанса расширений** — живая среда VS Code с Kilo и Copilot не запускалась (`T12-live`). [PROTOCOL: тест]
- **Поведение моделей** — комплект модель не вызывает; проверено чтение и повтор, а не рассуждение. [PROTOCOL: повтор]
- **Права ACL/NTFS** — измерены только права POSIX на этой машине. [PROTOCOL: права]
- **Сеть, службы, фоновые прогоны** — комплект офлайн и не работает сам. [PROTOCOL: миграци]

Список `not run` сверяется с отчётом сборки: если испытание стало `not run`, а здесь не названо, архив не выпускается. [X89]

Отдельно: `SHA256SUMS` — ведомость отпечатков, не подпись; прозаические эталоны читаемы, и недоступность — порядок работы, а не техническая защита. [SUMS]
"""

PROTOCOL_046 = """
## README — вектор смысла, якоря проверяются (0.1.36)

README перестал быть журналом выпусков: его задача — вернуть смысл тому, кто читает комплект через месяц,
и дать модели ориентир при отклонении. В нём три входа (пользователь, агент, проверяющий), границы, смыслы
файлов, команды и раздел «Чего нет». Каждое нормативное утверждение заканчивается якорем: `[START: фраза]`,
`[PROTOCOL: фраза]`, `[INIT: фраза]`, `[КАЛИБРОВКА: фраза]`, `[X84]`, `[K2]`, `[manifest]`, `[TRACE]`.

Якорь — проверяемая ссылка. Тест `X87` разрешает каждый якорь в файле поставки (фраза ищется в указанном
файле, номер испытания — среди `@case`, идентификатор промпта — в книге калибровки), проверяет лимит
24 КБ и падает, если утверждение осталось без якоря. Поэтому README не может разойтись с `START.md`
и `PROTOCOL.md` молча: расхождение — это якорь в никуда.

`TRACEABILITY.json` лежит в корне поставки и покрывает §2…§18: у каждого раздела названы тема, артефакты
(существующие файлы дерева), испытания (`X…`) и уровни обкатки (`L…`). Тест `X88` требует все семнадцать
разделов, существование артефактов и испытаний; раздел без покрытия валит сборку. Раздел «Чего нет»
сверяется с фактическим списком `not run` отчёта (`X89`), поэтому README не может обещать больше, чем
измерено.
"""

TEST_046 = r'''
    @case('X87', 'README-вектор: лимит 24 КБ, каждый якорь разрешается, утверждений без якоря нет.', '§2, §7, §22 (И-056).')
    def test_110_readme_vector(self):
        readme = (KIT.parent/'README.md')
        raw = readme.read_bytes()
        self.assertLessEqual(len(raw), 24576, 'README больше 24 КБ')
        text = raw.decode('utf-8')
        for entry in ('#если-вы-пользователь', '#если-вы-агент', '#если-вы-проверяющий'):
            self.assertIn(entry, text, 'в оглавлении нет входа ' + entry)
        def resolved(anchor):
            body = anchor.strip()
            m = re.match(r'\A(manifest|schema|rules|entry|CHECKS|PIPELINE|SUMS|TRACE)\Z', body)
            if m:
                places = {'manifest':'kit/base/manifest.json','schema':'kit/base/schema.json',
                          'rules':'kit/base/rules.json','entry':'kit/base/entry.txt',
                          'CHECKS':'reports/CHECKS.json','PIPELINE':'reports/PIPELINE.json',
                          'SUMS':'SHA256SUMS','TRACE':'TRACEABILITY.json'}
                return (KIT.parent/places[body]).is_file()
            m = re.match(r'\AX(\d+)\Z', body)
            if m:
                return ('@case(\'X' + m.group(1) + '\'') in tests_source
            m = re.match(r'\AK(\d+)\Z', body)
            if m:
                book = c.parse((KIT/'calibration.json').read_bytes())
                return m.group(0) in [p['id'] for p in book['prompts']]
            m = re.match(r'\Areleases/(\d+\.\d+\.\d+)\Z', body)
            if m:
                return (KIT.parent/'releases'/m.group(1)).is_dir()
            m = re.match(r'\A(START|PROTOCOL|INIT|КАЛИБРОВКА):\s*(.+)\Z', body)
            if m:
                places = {'START': KIT/'base/START.md', 'PROTOCOL': KIT/'base/PROTOCOL.md',
                          'INIT': KIT.parent/'docs/INIT-PROMPT.md',
                          'КАЛИБРОВКА': KIT.parent/'docs/КАЛИБРОВКА.md'}
                path = places[m.group(1)]
                if not path.is_file():
                    return False
                return m.group(2).strip().lower() in path.read_text(encoding='utf-8').lower()
            return False
        tests_source = (KIT/'tests/test_contract.py').read_text(encoding='utf-8')
        prose = '\n'.join(line for line in text.splitlines()
                          if not re.match(r'\A- \[.+\(#.+\)\Z', line.strip()))
        anchors = re.findall(r'\[([^\[\]]+)\]', prose)
        self.assertTrue(anchors, 'в README нет ни одного якоря')
        dead = sorted({a for a in anchors if not resolved(a)})
        self.assertEqual(dead, [], 'якоря в никуда: ' + ', '.join(dead))
        unanchored, fenced, row = [], False, 0
        lines = text.splitlines()
        heads = {n for n, line in enumerate(lines[:-1])
                 if line.strip().startswith('|') and lines[n + 1].strip().startswith('|-')}
        for number, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('```'):
                fenced = not fenced
                continue
            if fenced or not stripped or stripped.startswith('#') or number in heads:
                continue
            if stripped.startswith('|-') or set(stripped) <= set('|-: '):
                continue
            if stripped.startswith('<!--'):
                continue
            if re.match(r'\A- \[.+\]\(#.+\)\Z', stripped):
                continue
            if '[' not in stripped:
                unanchored.append(stripped[:60])
            row += 1
        self.assertGreater(row, 40, 'README слишком короткий, чтобы быть вектором')
        self.assertEqual(unanchored, [], 'утверждения без якоря: ' + ' | '.join(unanchored[:4]))

    @case('X88', 'Трассировка: §2…§18 покрыты, артефакты и испытания существуют.', '§2, §7, §22 (И-056).')
    def test_111_traceability(self):
        trace = c.parse((KIT.parent/'TRACEABILITY.json').read_bytes())
        self.assertEqual(trace['system_version'], c.VERSION)
        self.assertEqual(trace['schema_version'], 1)
        sections = [item['section'] for item in trace['sections']]
        want = ['§' + str(n) for n in range(2, 19)]
        self.assertEqual(sections, want, 'покрытие §2…§18 неполное')
        tests_source = (KIT/'tests/test_contract.py').read_text(encoding='utf-8')
        for item in trace['sections']:
            self.assertTrue(item['theme'], item['section'] + ': нет темы')
            self.assertTrue(item['artifacts'], item['section'] + ': нет артефактов')
            for artifact in item['artifacts']:
                self.assertTrue((KIT.parent/artifact).exists(), item['section'] + ': нет файла ' + artifact)
            self.assertTrue(item['tests'] or item['levels'], item['section'] + ': нет покрытия')
            for test in item['tests']:
                self.assertIn("@case('" + test + "'", tests_source, item['section'] + ': нет испытания ' + test)
            self.assertEqual(item['status'], 'covered', item['section'] + ': раздел не покрыт')
        self.assertTrue(trace['not_run'], 'нет раздела «чего нет»')

    @case('X89', 'Чего нет: README называет тот же список not run, что и трассировка.', '§2, §7, §22 (И-056).')
    def test_112_not_run(self):
        trace = c.parse((KIT.parent/'TRACEABILITY.json').read_bytes())
        text = (KIT.parent/'README.md').read_text(encoding='utf-8')
        section = text.split('## Чего нет')[1] if '## Чего нет' in text else ''
        self.assertTrue(section, 'в README нет раздела «Чего нет»')
        for entry in trace['not_run']:
            self.assertIn(entry['what'].lower(), section.lower(), 'не названо: ' + entry['what'])
            if entry.get('code'):
                self.assertIn(entry['code'], section, 'не назван код: ' + entry['code'])
        for promise in ('проверено в живой среде', 'подтверждено в VS Code', 'поведение модели проверено'):
            self.assertNotIn(promise, text, 'README обещает больше, чем измерено: ' + promise)
'''


def traceability(version: str) -> str:
    common = dict(status='covered')
    sections = [
        dict(section='§2', theme='роли: владелец, агент, проверяющий — у каждого свой вход в памятку',
             artifacts=['README.md', 'docs/INIT-PROMPT.md', 'kit/base/START.md'],
             tests=['X87', 'X82'], levels=['L7', 'L10'], **common),
        dict(section='§3', theme='переносимость: архив распакован в корень, путь проекта абсолютный',
             artifacts=['kit/base/PROTOCOL.md', 'docs/INIT-PROMPT.md'],
             tests=['X78', 'X79', 'X37'], levels=['L6'], **common),
        dict(section='§4', theme='границы и права: закрытый список путей, права измерены, объявление не факт',
             artifacts=['kit/base/PROTOCOL.md', 'kit/base/rules.json'],
             tests=['X72', 'X73', 'X80', 'X81'], levels=['L4W'], **common),
        dict(section='§5', theme='правила и области: событие, область, ключ и значение, состояние',
             artifacts=['kit/base/schema.json', 'kit/base/rules.json'],
             tests=['X22', 'X34', 'X40', 'X51'], levels=['L4C'], **common),
        dict(section='§6', theme='предположение не выдаётся за проверку: наблюдение требует доказательства',
             artifacts=['kit/base/START.md', 'kit/base/PROTOCOL.md'],
             tests=['X06', 'X17', 'X22'], levels=['L1', 'L2'], **common),
        dict(section='§7', theme='отказы: код, причина, состояние до и после; ошибка не теряет данные',
             artifacts=['kit/base/PROTOCOL.md', 'kit/tools/contract.py'],
             tests=['X04', 'X08', 'X09', 'X12', 'X62'], levels=['L3F'], **common),
        dict(section='§8', theme='секреты и владение: значение не печатается и не пересказывается',
             artifacts=['kit/base/PROTOCOL.md', 'kit/base/rules.json'],
             tests=['X56', 'X57', 'X58'], levels=['L4D'], **common),
        dict(section='§9', theme='правила: создание, изменение до/после, удаление, отмена, владелец',
             artifacts=['kit/base/PROTOCOL.md', 'kit/base/rules.json'],
             tests=['X50', 'X51', 'X54', 'X55', 'X58'], levels=['L4V'], **common),
        dict(section='§10', theme='контракты: создание, переходы, отмена, мёртвые ветки',
             artifacts=['kit/base/schema.json', 'kit/base/PROTOCOL.md'],
             tests=['T04', 'X68', 'X69'], levels=['L4T'], **common),
        dict(section='§11', theme='обновление: трёхстороннее сравнение, миграция формата 0 → 1',
             artifacts=['kit/base/PROTOCOL.md', 'kit/base/manifest.json'],
             tests=['X01', 'X02', 'X03', 'X13'], levels=['L4X'], **common),
        dict(section='§12', theme='журнал и восстановление: побайтово, идемпотентно, без потери чужого',
             artifacts=['kit/base/PROTOCOL.md', 'kit/tools/contract.py'],
             tests=['T16', 'T17', 'X63', 'X64', 'X65'], levels=['L4S'], **common),
        dict(section='§13', theme='адаптеры и входы: карточка среды, один вход, чужой файл не присваивается',
             artifacts=['kit/base/START.md', 'kit/base/entry.txt'],
             tests=['X23', 'X27', 'X31', 'X38'], levels=['L4O'], **common),
        dict(section='§14', theme='уровни достоверности 1–5: обнаружение, чтение, поведение, повтор',
             artifacts=['kit/base/PROTOCOL.md', 'kit/tools/contract.py'],
             tests=['X44', 'X46', 'X48', 'X49'], levels=['L1', 'L2', 'L3', 'L5a', 'L5b'], **common),
        dict(section='§15', theme='метрики: стоимость, шум, сравнение двух сценариев',
             artifacts=['kit/tools/contract.py', 'kit/base/PROTOCOL.md'],
             tests=['X66', 'X67', 'X70', 'X71'], levels=['L4K'], **common),
        dict(section='§16', theme='данные и совместимость: схема, неизвестная версия, чужая файловая система',
             artifacts=['kit/base/schema.json', 'kit/base/manifest.json'],
             tests=['X03', 'X62', 'X74', 'X75'], levels=['L4F'], **common),
        dict(section='§17', theme='обкатка через собственный интерфейс: матрица P1–P8',
             artifacts=['kit/base/START.md', 'docs/INIT-PROMPT.md'],
             tests=['X36', 'X42', 'X43'], levels=['L6', 'L7', 'L8', 'L9', 'L10'], **common),
        dict(section='§18', theme='тесты и приёмка: что считается pass, повтор из печати',
             artifacts=['kit/tests/test_contract.py', 'reports/CHECKS.json', 'TRACEABILITY.json'],
             tests=['X85', 'X87', 'X88', 'X89'], levels=['L10'], **common),
    ]
    data = dict(system_version=version, schema_version=1,
                note='Раздел → артефакт → испытание. Раздел без покрытия валит сборку (X88).',
                sections=[dict(section=s['section'], theme=s['theme'], artifacts=s['artifacts'],
                               tests=s['tests'], levels=s['levels'], status=s['status']) for s in sections],
                not_run=[dict(what='Windows junction', code='X14', why='проверка reparse point не выполнена'),
                         dict(what='два настоящих сеанса расширений', code='T12-live',
                              why='живая среда VS Code здесь не запускается'),
                         dict(what='поведение моделей', why='комплект модель не вызывает'),
                         dict(what='права ACL/NTFS', why='измерены только права POSIX'),
                         dict(what='живая среда VS Code с Kilo и Copilot', why='расширения не запускались')])
    payload = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False) + '\n'
    return payload


def readme_vector(version: str, pass_total: int) -> str:
    return README_VECTOR.replace('{{version}}', version).replace('{{pass_total}}', str(pass_total))
