# Операционный улей тасков и Watchdog (`tasks/`)

Динамическая среда исполнения пофазовых пользовательских заданий, исследований и разработок в архитектуре **ISAI** (аналог летучего улья `HKCC` + контура транзакционного стейджинга `CBS`). В спокойном состоянии (`active_tasks == ()`) не содержит незакрытых временных подпапок, а актуальный срез системы зафиксирован в `tasks/.isai/state_snapshot.json`.

<!-- ISAI:SYNC:BEGIN -->
<!-- isai:node_id=isai://tasks -->
<!-- isai:spec_digest=c6bfc963b6def96988c40c7a0639f6fe9a52d15ba8fadc7bf3e1bdd9e072a1bb -->
<!-- isai:interface_digest=6235e13f8e9d3421aedebfeae8b55e08450632fb61739acf6f98337d6765b000 -->

## Паспорт узла `isai://tasks` — Операционный улей тасков, фазового стейджинга и службы Watchdog (Runtime & CBS Arena)

- **Уровень целостности:** `IL_3_STAGING` | **Видимость:** `PUBLIC`
- **Родительский узел:** `isai://root`
- **Цель (`Goal`):** Изолировать активные разработки, исследования и фазовые процессы в транзакционном контуре стейджинга, удерживать атомарный снимок состояния репозитория, контролировать транзитивное каскадное влияние мутаций (включая схемы портов) и обеспечивать Crash Recovery.

### Критерии успеха (`Success Criteria`)
- В каждый момент времени файл tasks/.isai/state_snapshot.json отражает достоверное состояние системы.
- Активные таски имеют видимость EPHEMERAL_STAGING и удерживают арендные дескрипторы с TTL, сбрасываемые в 0 при закрытии.
- При сбое процесса служба CrashRecoveryService ('isai recover') очищает оборванный стейджинг и восстанавливает консистентность.

### Функционал (`Capabilities`)
- Управление жизненным циклом пользовательских тасков по двухконтурному протоколу (Task DAG + ISAI-PEP v1).
- Детерминированная служба TaskWatchdog (tasks/.isai/watchdog.py): MVCC-аренды с TTL, структурный Salsa Early-Cutoff и Crash Recovery.
- Атомарное хранение среза состояния системы (tasks/.isai/state_snapshot.json) через fsync + os.replace.

### Локальные инварианты (`Invariants`)
- Запрет на пересечение WRITE_LEASE между параллельными асинхронными фазами и запрет WRITE_LEASE на IL-0.
- При отсутствии активных тасков (active_tasks == ()) список open_handles обязан быть пуст (HandleCount == 0).
- Промоушен в канонические кольца IL-1 / IL-2 возможен только при полном прохождении Gate A ('isai audit' + 'pytest').

### Адаптер и Связывание Портов (`Adapter & Port Wirings`)
- **Входы (`Inputs`):**
  - `task_manifest` (`TaskManifest | str`, обязательный) [схемы: `isai.protocol:TaskManifest`, `builtins:str`] — Пофазовая спецификация пользовательского задания или исследования.
  - `gate_a_audit_verdict` (`AuditReport`, опциональный) [схемы: `isai.protocol:AuditReport`] — Вердикт 360°-аудитора ядра перед промоушеном стейджинга.
  - `pytest_gate_verdict` (`bool`, опциональный) [схемы: `builtins:bool`] — Сигнал прохождения матрицы автотестов улья /tests/.
- **Выходы (`Outputs`):**
  - `promoted_artifacts_and_distillation` (`PhaseOutputEnvelope`, гарантированный) [схемы: `isai.protocol:PhaseOutputEnvelope`] — Верифицированные изменения для канонических структур, записи для /knowledge/ и событие хроники.
  - `state_snapshot` (`SystemStateSnapshot`, гарантированный) [схемы: `isai.protocol:SystemStateSnapshot`] — Обновлённый снимок состояния репозитория и таблицы дескрипторов.
- **Контрактная коммутация портов (`port_wirings`):**
  - вход `gate_a_audit_verdict` ← `isai://root` (выход `audit_report`) — Получение детерминированного отчёта 360°-аудита перед промоушеном.
  - вход `pytest_gate_verdict` ← `isai://tests#SelfVerificationSuite` (выход `pytest_gate_verdict`) — Получение сигнала прохождения кросс-тестов из улья /tests/.

### Реестр владения и верифицируемых символов (`Ownership & Symbol Bindings`)
- **Файлы узла (`owned_files`):** `README.md`
- **Служебные файлы (`system_files`):** `.isai/node.py`, `.isai/watchdog.py`, `.isai/state_snapshot.json`
- **Экспортируемые сущности (`symbol_bindings`):**
  - `isai://tasks#WatchdogService` (`python_attr` → `watchdog.py:TaskWatchdog`, видимость: `PUBLIC`)
  - `isai://tasks#CrashRecoveryService` (`python_attr` → `watchdog.py:recover_repository`, видимость: `PUBLIC`)
  - `isai://tasks#StateSnapshot` (`system_artifact` → `state_snapshot.json`, видимость: `PUBLIC`)

### Типизированные связи и Маршрутизация (`Typed Links & Router`)
- **Типизированные связи (`links`):**
  - `isai://root#GenesisKernel` [`GOVERNED_BY` | RSoC: `NONE`]
  - `isai://root#PhaseExecutionProtocol` [`CONSUMES_CONTRACT` | RSoC: `INTERFACE_STUB`] — Исполнение микро-цикла фазы ISAI-PEP v1.
  - `isai://root#LinkInjector` [`CONSUMES_CONTRACT` | RSoC: `INTERFACE_STUB`] — Безопасная коммутация и рефакторинг связей внутри фаз.
  - `isai://root#AtomicPersistence` [`CONSUMES_CONTRACT` | RSoC: `NONE`]
  - `isai://root#NeuroVascularFundamental` [`GOVERNED_BY` | RSoC: `NONE`] — Подчинение субгенетическому нервно-сосудистому фундаменталу IL-1C.
- **Допустимые переходы (`transitions`):**
  - При `promote_to_canonical` → `isai://root` [режим: `STAGED_TRANSACTION`] — Атомарное внедрение верифицированных результатов фазы в целевую архитектуру.
  - При `distill_task_insights` → `isai://knowledge#EmpiricalCatalog` [режим: `STAGED_TRANSACTION`] — Консолидация полученных практических паттернов в базу знаний при закрытии таска.
  - При `commit_chronicle_event` → `isai://root#ChronicleLedger` [режим: `STAGED_TRANSACTION`] — Фиксация неизменяемой записи о переходе состояния или восстановлении в .isai/chronicle.jsonl.

<!-- ISAI:SYNC:END -->
