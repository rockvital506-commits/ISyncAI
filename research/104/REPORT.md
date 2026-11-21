# И‑104 — Самостоятельная схема v2

`arena/4e000a5e-isyncai` · Ф1. Модель данных · P0 · 2026-11-18

## П0–П2. Замысел и пределы

Исходная сверка: v1.5 · 0418089. [Замысел](DESIGN.md) и [обязательные испытания](CASES.json) записаны до валидатора. Подготовительная проверка в этот момент прошла пять тестов шлюза, целевая проба закономерно не импортировала ещё не написанный `schema_v2`.

[Исполнимый контракт](../../kit/base/schema_v2.py) и [формат](../../kit/base/SCHEMA-V2.md). Обязательных случаев на прогон: **62** (13 положительных, 49 отрицательных). SHA‑256 списка П2: `64ecfe701b9918cb010b0905d335beebda6bf088e16fdf726fec9674837686bd`.

## П3–П4. Два целевых прогона и отдельный донорский контроль

| Прогон | Результат | Свидетельство |
| --- | --- | --- |
| П3 · checkout | 62 pass / 0 fail / 0 not run; rc 0 | CHECKOUT.json |
| П4 · чистая копия | 62 pass / 0 fail / 0 not run; rc 0 | CLEANROOM.json |
| Донор 0.1.36 | совпал со старым эталоном | DONOR-CONTROL.json; не целевые тесты |

Целевой процесс запускается с `-B -I -S`. В чистую копию входят только пять файлов из `target_inputs`, **без ZIP 0.1.36, ISAI и исследовательского харнесса**. Сравнены SHA‑256 входов, список файлов и фактические результаты. Это независимый повтор процесса, а не независимый тест-агент и не гарантия прав среды.

Контроль донора отдельно запускает `check_preparation.py`: сверяет его архив и проверяет `install → connect → create` черновика в L2 без калибровки, отказ для неизвестного родителя и неизменность L0 **донора**. Это не `compat --old` и не повтор полного набора 0.1.36.

## П5. Приёмка

[ACCEPTANCE.json](ACCEPTANCE.json): **accepted**, 8 pass / 0 fail / 4 not run. Здесь считаются ворота приёмки и вынесенные работы, а не сумма двух целевых прогонов.

| Проверка | Статус | basis | criterion |
| --- | --- | --- | --- |
| p2_casebook | pass | DESIGN.md; ITERATION.json; CASES.json; SCHEMA-CASES.json | Список заморожен в П2; все 14 карточек И-104 разложены на обязательные случаи. |
| target_checkout | pass | CASES.json; CHECKOUT.json | Все обязательные ID ровно один раз; исход, тип, причина, путь и неизменность точны. |
| target_cleanroom | pass | CASES.json; CLEANROOM.json | Все обязательные ID ровно один раз; исход, тип, причина, путь и неизменность точны. |
| isolated_inputs | pass | ITERATION.json: target_inputs; CLEANROOM.json | Чистая копия содержит только перечисленные входы; 0.1.36, ISAI и харнесс в неё не копируются. |
| source_repeat | pass | CHECKOUT.json; CLEANROOM.json | Входы по SHA-256 одинаковы и не меняются; результаты двух процессов совпадают. |
| filled_and_draft | pass | CHECKOUT.json: facts; V01; PHASED-PROMPT-PROTOCOL.md | Три наполненные области; текст кандидата точен, R-2 остаётся draft внутри R-1. |
| acceptance_selftest | pass | test_acceptance.py; ACCEPTANCE.json: checks | Шлюз отклоняет пропуски, неверные ID, значения, типы и изменения входа. |
| donor_control | pass | DONOR-CONTROL.json; pre-104/EVIDENCE.json | Отдельный закреплённый 0.1.36 повторяет черновик L2, отказ parent и неизменность его L0. |

## П6. Находки

| ID | Наблюдение | basis | criterion | Следствие |
| --- | --- | --- | --- | --- |
| F1 | Известное, но чужое authority не согласуется с областью, а область загрузки задаётся извне. | N03-context, N04-known-wrong | shape:area_mismatch и shape:authority_area; входы прежние. | Допустимая декларация не выдаёт прав; в И-105 читатель передаёт expected_area, И-107 проверяет операцию. |
| F2 | Ссылка на настоящий контракт вне данного документа — не существующая локальная связь; префикса пути недостаточно. | N08-foreign, V03-scope-self, N07-sibling | Внешняя ссылка и docs2/guide отвергнуты, точный scope принят. | Раздельный формат не ищет родителя в других слоях. Для старых ссылок И-131 нужен явный разбор. |
| F3 | Строгое чтение и проверка типов нужны независимо от прав и связей. | N19-duplicate-json, N05-bool, N05-decimal, N16-floating-tag | Дубликат отклонён; логические и вещественные значения не приняты за целочисленный счётчик. | Адаптер разбирает через validate_json и не заменяет отсутствующее поле догадкой. |
| F4 | Лексическое совпадение или вложенность roots обнаруживаются, даже когда физического дерева нет. | N14-declared-equal, N14-declared-nested, V05-other-root | Совпадающие/вложенные отвергнуты; похожее имя kit-extra принято. | Не считать это проверкой реальной раскладки, прав, ссылок и регистрозависимости ФС. |
| F5 | Подготовительный корпус полезен и без рабочего профиля; отрицания проверяются по наблюдаемым ответам. | V01–V02, CHECKOUT.json, CLEANROOM.json, test_acceptance.py | Все обязательные ID в двух процессах; черновик не изменился; ложные пропуски шлюз отклонил. | Не активировать протокол и не считать сохранение/исполнение доказанным. Следующий шаг — реальная раскладка. |

### Обязательные случаи (результаты совпали в обеих копиях)

| ID | Покрытие исходного требования | Наблюдение |
| --- | --- | --- |
| V01-L0 | V01 | принят |
| V02-L0 | V02 | принят |
| V01-L1 | V01 | принят |
| V02-L1 | V02 | принят |
| V01-L2 | V01 | принят |
| V02-L2 | V02 | принят |
| V01-group | V01 | принят |
| V02-group | V02 | принят |
| V03-scope-self | A4 | принят |
| V04-independent-id | P2 | принят |
| V05-other-root | A1: declarations | принят |
| V06-semver | P2 | принят |
| V07-raw-json | JSON | принят |
| N01-missing | N01 | отказ `shape:missing_field` на `/entries/1/basis` |
| N02-blank | N02 | отказ `shape:blank` на `/entries/1/criterion` |
| N03-enum | N03 | отказ `shape:unknown_area` на `/area` |
| N03-context | N03 | отказ `shape:area_mismatch` на `/area` |
| N04-enum | N04 | отказ `shape:authority` на `/entries/1/authority` |
| N04-known-wrong | N04 | отказ `shape:authority_area` на `/entries/1/authority` |
| N05-bool | N05 | отказ `shape:type` на `/revision` |
| N05-string | N05 | отказ `shape:type` на `/revision` |
| N05-negative | N05 | отказ `shape:revision` на `/revision` |
| N05-null | N05 | отказ `shape:type` на `/revision` |
| N05-decimal | N05 | отказ `shape:type` на `/revision` |
| N06-up | N06 | отказ `shape:path` на `/entries/1/scope` |
| N06-absolute | N06 | отказ `shape:path` на `/entries/1/scope` |
| N06-drive | N06 | отказ `shape:path` на `/entries/1/scope` |
| N06-backslash | N06 | отказ `shape:path` на `/entries/1/scope` |
| N06-noncanonical | N06 | отказ `shape:path` на `/entries/1/scope` |
| N06-dot-alias | N06 | отказ `shape:path` на `/entries/1/scope` |
| N07-sibling | N07 | отказ `links:scope_outside` на `/entries/1/scope` |
| N07-parent-wider | N07 | отказ `links:scope_outside` на `/entries/1/scope` |
| N07-case | N07 | отказ `links:scope_outside` на `/entries/1/scope` |
| N08-dangling | N08 | отказ `links:parent_missing` на `/entries/1/parent` |
| N08-kind | N08 | отказ `links:parent_kind` на `/entries/1/parent` |
| N08-omitted | N08 | отказ `shape:missing_field` на `/entries/1/parent` |
| N08-null | N08 | отказ `shape:type` на `/entries/1/parent` |
| N08-foreign | N08 | отказ `links:parent_missing` на `/L1/entries/1/parent` |
| N09-value | N09 | отказ `shape:key_pair` на `/entries/1/value` |
| N09-key | N09 | отказ `shape:key_pair` на `/entries/1/key` |
| N09-value-null | N09 | отказ `shape:type` на `/entries/1/value` |
| N10-duplicate | N10 | отказ `links:duplicate_id` на `/entries/2/id` |
| N11-missing | N11 | отказ `shape:missing_field` на `/roots` |
| N11-type | N11 | отказ `shape:type` на `/roots` |
| N11-empty | N11 | отказ `shape:roots_empty` на `/roots` |
| N11-dot | N11 | отказ `shape:path` на `/roots/0` |
| N12-state | N12 | отказ `shape:state` на `/entries/1/state` |
| N13-contract-parent | A4 | отказ `shape:parent_forbidden` на `/entries/0/parent` |
| N14-declared-equal | A1: declarations | отказ `links:roots_overlap` на `/L1/roots/0` |
| N14-declared-nested | A1: declarations | отказ `links:roots_overlap` на `/L1/roots/0` |
| N14-local-duplicate | A1: declarations | отказ `links:roots_overlap` на `/roots/1` |
| N15-bad-semver | P2 | отказ `shape:release_version` на `/release_version` |
| N15-profile-semver | P2 | отказ `shape:unknown_field` на `/release_version` |
| N15-project-semver | P2 | отказ `shape:unknown_field` на `/release_version` |
| N15-system-counter | P2 | отказ `shape:unknown_field` на `/revision` |
| N16-old-schema | P2 | отказ `shape:schema_version` на `/schema_version` |
| N16-floating-tag | P2 | отказ `shape:type` на `/schema_version` |
| N17-not-inline | P2 | отказ `shape:unknown_field` на `/entries/1/text_file` |
| N18-opaque-id | A4 | отказ `shape:id` на `/entries/1/id` |
| N19-duplicate-json | JSON | отказ `parse:duplicate_member` на `<root>` |
| N19-nonfinite-json | JSON | отказ `parse:non_finite` на `<root>` |
| N19-invalid-json | JSON | отказ `parse:invalid_json` на `<root>` |

### Не выполнялось

| Что | Где проверяется |
| --- | --- |
| Рабочие операции, журнал и физические границы областей (включая NTFS/ACL). | И-105–И-107; лексический формат не проверяет ФС. |
| Выдача прав, конфликт действующих правил, активация и перенос R-2. | И-107, Ф2–Ф3; приняты только данные синтетической записи. |
| Чистая установка выпуска 0.2.0, миграция и восстановление. | И-112/И-140 и И-131/132; работа схемы не равна работе поставки. |
| Чтение и исполнение в Arena, Kilo и Copilot. | И-125 и Ф8; живые сеансы не запускались. |

## П7–П9. Печать, страница и сверка

[Печать](SEAL.json) включает замысел, код, входы и принятый отчёт с приёмкой. [Повтор](REPLAY.json) сравнивает сохранённые байты без их замены. Страница производная и не входит в печать. Сверка: [стратегия v1.6](../STRATEGY.md) и [журнал](../strategy/SYNC-LOG.md), запись 14. Состав P0, A1–A4 и граф фаз не изменены.

Воспроизведение из корня снимка Git этой итерации: `python3 -B research/104/run.py`; проверка уже сохранённой печати и страницы без записи: `python3 -B research/104/run.py --verify-seal`.

## Дальше

И-105 — реальные раздельные корни и первая штатная мутация L1 со снимками L0 и L2; И-105 ещё не начата.
