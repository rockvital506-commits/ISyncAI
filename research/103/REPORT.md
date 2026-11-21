# Итерация И-103 — «Версии и совместимость»

Ветка: `arena/4e000a5e-isyncai` · Дата: 2026-11-18 · Ф0. Каркас программы · P0

## П0–П1. Сверка и замысел до прогона

См. [DESIGN.md](DESIGN.md) и [ITERATION.json](ITERATION.json).

| Пункт | Содержание |
| --- | --- |
| Цель | Зафиксировать разделение SemVer L0, revision L1 и состояния L2, допустимые маршруты перехода и политику Git. |
| Гипотеза | Десять реальных записей в стенд L1 изменят только его ревизию; измеренные версия, pin и файлы настоящего L0 и состояние реального L2 не изменятся. |
| Изменяемая поверхность | `research/103/`, `research/strategy/`, `research/STRATEGY.md` |
| Что НЕ трогаем | `.isai/`, `выпуск 0.1.36 и рабочий Kit`, `артефакты И-101/И-102`, `пользовательские проекты` |
| Ожидаемые коды отказа | `trust (CLI 0.1.36, pin)`, `unknown_schema (CLI 0.1.36)`, `stale_revision (стенд)`, `unknown_version (политика)` |
| Критерий успеха | Полные результаты И-101 воспроизводятся; 10 стендовых мутаций сравниваются с настоящими версиями и байтами; отказы не пишут; границы совместимости и Git зафиксированы. |
| Критерий провала | Дрейф L0/L2 от действий в другом слое, сдвиг ревизии при отказе или незаметное объявление непроверенной миграции поддержанной. |
| Откат | Отменить только коммит И-103; постоянные проекты и архив выпуска не затронуты. |

## П2. Испытания

Эталоны И‑101 и негативные сценарии заданы в `ITERATION.json` и `test_versioning.py`. Воспроизведение фикстур: `python3 -B research/103/test_versioning.py`.

## П3. Прогон в репозитории

Харнесс из рабочего дерева измеряет отслеживаемый архив `research/release-0.1.36/AgentContractKit-0.1.36.zip`. Машинные данные — `BASELINE.json`; выпуск не пересобирался и не менялся.

| Показатель | Значение |
| --- | --- |
| Выпуск | 0.1.36 |
| ZIP: байт / членов | 774894 / 220 |
| SHA-256 выпуска | e9f817c5286cea4bb4230ccd4f0fd307be3193ad3d46754d230cafc1bea66bf6 |
| Дерево: файлов | 220 |
| Дерево: digest | 159de6bda79871f6c4128d1839e1fccb86ca298c54a75d9d87d65b0b185d9fdc |
| Команд / операций | 26 / 15 |
| Digest baseline | 9d2cb89bf03cd58f616a34c05ddd047072f781b3ef3cbd67791f8c8239e09585 |

## П4. Прогон в чистой копии

Свежая распаковка, пустой проект `A`, без калибровки.

| Шаг | rc | Результат |
| --- | --- | --- |
| 1-status-before | 0 | absent |
| 2-install | 0 | успех |
| 3-status-after-install | 0 | valid |
| 4-connect | 0 | успех |
| 5a-create-contract | 0 | успех |
| 5b-create-rule | 0 | успех |
| 6-list | 0 | контрактов: 1; активных записей: 1 (P-2, P-1) |
| 7-adapter-arena | 2 | adapter_unknown |
| 8-status-final | 0 | valid |

Digest точек замера (`CLEANROOM.json`): `4a40a6ee099fe6e398b09480831a8c44552e987b96147b012cad80b400d0ede8`.

Отдельная распаковка: `kit/tests/test_contract.py` → **105 pass / 0 fail / 3 not run** (rc 0, inconclusive: 0). Это офлайн-регрессия выпуска, не проверка живой модели; её пропуски в `RELEASE-TESTS.json`.

Результаты дополнительных проб П3–П4: [VERSION-EVIDENCE.json](VERSION-EVIDENCE.json).

## П5. Приёмка

`ACCEPTANCE.json`: **accepted**, 19 pass / 0 fail / 3 not run. Счётчики харнесса и набора выпуска ведутся отдельно.

| Проверка | Статус | basis | criterion |
| --- | --- | --- | --- |
| baseline_matches_i101 | pass | research/strategy/BASELINE.json | Полный инвентарь совпадает с И-101 |
| cleanroom_matches_i101 | pass | research/101/CLEANROOM.json | Чистая установка, подключение и создание без калибровки совпадают с И-101 |
| release_regression | pass | RELEASE-TESTS.json: totals | Офлайн-набор выпуска не потерял проверок |
| release_exit | pass | RELEASE-TESTS.json: rc | Нативные тесты завершились с rc 0 |
| no_native_l1 | pass | VERSION-EVIDENCE.json: package.profile_members | ZIP 0.1.36 не поставляет profiles; проба не выдаётся за штатную функцию |
| l1_revision_sequence | pass | VERSION-EVIDENCE.json: profile.revisions | Из файлов прочитано 0 → 1 … → 10, а не из номера цикла |
| l1_ten_commits | pass | VERSION-EVIDENCE.json: profile.committed_mutations | Каждая из десяти записей завершилась как committed |
| l1_content_changed | pass | VERSION-EVIDENCE.json: profile.distinct_rules_digests | Различны SHA-256 начального и каждого из десяти состояний rules.json |
| l1_new_rules_linked | pass | VERSION-EVIDENCE.json: profile.child_ids | Десять различных дочерних записей прочитаны из rules.json |
| l1_no_product_version | pass | VERSION-EVIDENCE.json: profile.only_counter_and_registry | Стендовые файлы L1 содержат счётчик и реестр без полей версии продукта |
| l1_retries_no_write | pass | VERSION-EVIDENCE.json: profile.retries | Повтор правила и просроченная ожидаемая ревизия не меняют ни одного из двух файлов |
| native_l0_stays_pinned | pass | VERSION-EVIDENCE.json: system.initial.base_version | Версия из status настоящего CLI |
| native_identity_matches_pin | pass | VERSION-EVIDENCE.json: system.pin_matches_install | Хеш установленного манифеста равен pin; начальная копия L0 тождественна источнику и одобренному пакету |
| native_l0_not_mutated | pass | VERSION-EVIDENCE.json: system.steady | Штатные L2 create и десять смен L1 не меняют версию, установочный pin и хеши исходного/установленного L0 |
| native_l2_own_counter | pass | VERSION-EVIDENCE.json: project.create_revisions | status.project_revision прочитан до create и после каждого create, не берётся из SemVer |
| native_l2_not_mutated_by_l1 | pass | VERSION-EVIDENCE.json: project.unchanged_during_profile_writes | Снимок всего реального проекта и его счётчик не меняются на каждом шаге L1 |
| unknown_native_schema | pass | VERSION-EVIDENCE.json: refusals.unknown_schema | 0.1.36 отказывает plan мутации при неизвестной схеме без изменения байтов |
| bad_native_pin | pass | VERSION-EVIDENCE.json: refusals.bad_pin | Верный SemVer с неутверждённым pin не разрешает install |
| compat_routes | pass | VERSION-EVIDENCE.json: compatibility.matches_cases | Точные пары, неподдержанные варианты и rollback соответствуют независимым ожиданиям; классификация не запускает миграцию |

## П6. Находки

| # | Находка | basis | criterion | Следствие |
| --- | --- | --- | --- | --- |
| F1 | L1 не входит в поставку 0.1.36: десять мутаций проверяют стенд рядом с настоящим L0, а не штатный интерфейс. | VERSION-EVIDENCE.json: package, profile, system | Все 10 шагов сохраняют байты L0/L2 и повышают сохранённый revision стенда. | В §4 разведены проверка политики И-103 и функциональная проверка И-105/И-106. |
| F2 | Ревизию проекта нативный status даёт как project_revision. base.version остаётся ссылкой на L0, schema_version — меткой формата. | VERSION-EVIDENCE.json: project, system.initial; contract.py:2012–2014 в базовом ZIP | Контракт и дочернее правило сдвигают счётчик проекта, а версию, pin и файлы L0 — нет. | Раздельные поля закреплены в VERSIONING.md и §3.2 стратегии. |
| F3 | Совпадения SemVer или наличия старого пакета недостаточно для миграции: pin и поддержанная схема проверяются отдельно. | VERSION-EVIDENCE.json: refusals, compatibility; COMPATIBILITY.json | У 0.1.36 неверный pin даёт trust, незнакомая схема — unknown_schema; оба отказа без записи. | Только 0.1.36 со схемой 1 — прямой кандидат; переход на 0.2.0 остаётся not run до И-131. |
| F4 | Семейство 0.1.x не является сплошным подтверждённым диапазоном: в закреплённом ZIP нет манифестов 0.1.1, 0.1.2 и 0.1.3. | VERSION-EVIDENCE.json: package.shipped_manifests и compatibility.cases | Классификатор отказывает отсутствующим номерам; для найденных старых выпусков решение — только проверка цепочки до 0.1.36. | Матрица не использует wildcard-поддержку 0.1.x и не выдаёт список пакетов за тест миграции. |

### Что не выполнялось (not run)

| Что | Почему |
| --- | --- |
| Рабочие схема и CLI L1, атомарность и журнал профильных операций | В 0.1.36 L1 нет; реализация и повтор на ней — И-104–И-106. |
| Фактические установка, миграция и восстановление 0.2.0; сплошная совместимость всех 0.1.x | 0.2.0 ещё не выпущена; матрица задаёт проверяемые маршруты, а не результаты И-112/И-131/И-132/И-140. |
| Живые сеансы Arena/Kilo/Copilot и локальный Git‑цикл на Windows/VS Code | Нужны отдельные прогоны сред; И-124/И-125/И-134/И-135. |

## П7–П8. Печать и страница

Размер и хеш — только в `SEAL.json` и на странице. `REPLAY.json` фиксирует сверку сохранённого ZIP и манифеста с повторной сборкой по итоговым файлам. Этот отчёт входит в печать и после неё не перезаписывается.

## Следующая итерация

После закрытия Ф0 — И-104 (Ф1): схема v2 и отрицательные фикстуры для областей, полномочий, scope и реестров. Реализация L1 и миграции не засчитана.
