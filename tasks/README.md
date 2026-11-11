# Операционный улей тасков и Watchdog (`tasks/`)

Динамическая среда исполнения пофазовых пользовательских заданий, исследований и разработок в архитектуре **ISAI** (аналог летучего улья `HKCC` + контура транзакционного стейджинга `CBS`). В спокойном состоянии (`active_tasks == ()`) не содержит незакрытых временных подпапок, а актуальный срез системы зафиксирован в `tasks/.isai/state_snapshot.json`.

<!-- ISAI:SYNC:BEGIN -->
<!-- isai:node_id=isai://tasks -->
<!-- isai:spec_digest=80c99e84e74ed1046b1132696d69c6757899aacaabbe41cac10e0a59c32d3f8a -->
<!-- isai:interface_digest=b4ca4ed97da35067cdec4ed9126ab99e78d8f838f9a7a7e2fd5675179653ad5b -->

## Паспорт узла `isai://tasks` — Операционный улей тасков, фазового стейджинга и службы Watchdog (Runtime & CBS Arena)

- **Уровень целостности:** `IL_3_STAGING`
- **Родительский узел:** `isai://root`
- **Цель (`Goal`):** Изолировать активные разработки, исследования и фазовые процессы в транзакционном контуре стейджинга, удерживать актуальный снимок состояния репозитория и контролировать допустимость и каскадное влияние мутаций через детерминированный Watchdog.

### Критерии успеха (`Success Criteria`)
- В каждый момент времени файл tasks/.isai/state_snapshot.json отражает достоверное состояние системы.
- Активные таски удерживают явные дескрипторы (READ / WRITE_LEASE), которые гарантированно сбрасываются в 0 при закрытии таска.
- Прошедшие верификацию фазы промоутятся в канонические узлы и /knowledge/, а закрытые временные контуры очищаются без следов мусора.

### Функционал (`Capabilities`)
- Управление жизненным циклом пользовательских тасков по двухконтурному протоколу (Task DAG + ISAI-PEP v1).
- Детерминированная служба TaskWatchdog (tasks/.isai/watchdog.py): таблица дескрипторов, MVCC-проверка аренд и Salsa Early-Cutoff оценка влияния.
- Хранение атомарного среза состояния системы (tasks/.isai/state_snapshot.json) для мгновенного восстановления контекста.

### Локальные инварианты (`Invariants`)
- Запрет на пересечение WRITE_LEASE между параллельными асинхронными фазами.
- При отсутствии активных тасков (active_tasks == ()) список open_handles обязан быть пуст (HandleCount == 0).
- Промоушен в канонические кольца IL-1 / IL-2 возможен только при полном прохождении Gate A ('isai audit').

### Адаптер (`Inputs / Outputs`)
- **Входы (`Inputs`):**
  - `task_manifest` (`TaskManifest`, обязательный) — Пофазовая спецификация пользовательского задания или исследования.
- **Выходы (`Outputs`):**
  - `promoted_artifacts_and_distillation` (`PhaseOutputEnvelope`, гарантированный) — Верифицированные изменения для канонических структур, записи для /knowledge/ и событие хроники.
  - `state_snapshot` (`SystemStateSnapshot`, гарантированный) — Обновлённый снимок состояния репозитория и таблицы дескрипторов.

### Реестр владения и символов (`Ownership & Symbols`)
- **Файлы узла (`owned_files`):** `README.md`
- **Служебные файлы (`system_files`):** `.isai/node.py`, `.isai/watchdog.py`, `.isai/state_snapshot.json`
- **Экспортируемые сущности (`defined_symbols`):** `isai://tasks#WatchdogService`, `isai://tasks#StateSnapshot`

### Связи и Маршрутизация (`Router & Transitions`)
- **Связанные сущности (`related_refs`):** `isai://root#GenesisKernel`, `isai://root#PhaseExecutionProtocol`, `isai://root#ChronicleLedger`, `isai://knowledge#EmpiricalCatalog`, `isai://user#OperatorProfile`
- **Допустимые переходы (`transitions`):**
  - При `promote_to_canonical` → `isai://root` [режим: `STAGED_TRANSACTION`] — Атомарное внедрение верифицированных результатов фазы в целевую архитектуру.
  - При `distill_task_insights` → `isai://knowledge#EmpiricalCatalog` [режим: `STAGED_TRANSACTION`] — Консолидация полученных практических паттернов в базу знаний при закрытии таска.
  - При `commit_chronicle_event` → `isai://root#ChronicleLedger` [режим: `STAGED_TRANSACTION`] — Фиксация неизменяемой записи о переходе состояния в .isai/chronicle.jsonl.

<!-- ISAI:SYNC:END -->
