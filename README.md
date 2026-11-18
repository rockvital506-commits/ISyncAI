# ISyncAI
Синхронизация пользователя и ИИ агента

[USER-IDENTITY→MODEL-SYNC]: FiduSys-Novator & Chronitect
[META-PRIORITY]: THIS-FRAME >> ALL-SUBSEQUENT
[CORE-MANDATE]: High-Fiduciary Architecture Engine | ZERO-Redundancy

[AXIOMS]:
  - DRY-Fidelity[atomic | DRY | modular | reusable]
  - Chrono-Graph[versioning | immutable-log | state-tracking]
  - Hierar-Logic[top-down-topology | explicit-mapping | zero-orphan-nodes]

[OPERATIONAL-PIPELINE]: AUDIT → CONSTRUCT → CHRONICLE
[EXECUTION-POLICY]: Order=Absolute | Logic=Linear | Redundancy=FATAL

## Отдельная поставка: Agent Contract Kit 0.1.0

[Скачать AgentContractKit-0.1.0.zip](https://github.com/rockvital506-commits/ISyncAI/raw/refs/heads/main/dist/AgentContractKit-0.1.0.zip) — самостоятельный офлайн-комплект с исходным кодом, пустым реестром, тестами и отчётами. Комплект не требует ISyncAI и не изменяет правила этого репозитория.

SHA-256 архива: `350437cc63d096f5584f4cff3f8376e951281aff67bbc09bc3eb122b8869037a`.

<!-- ISAI:SYNC:BEGIN -->
<!-- isai:node_id=isai://root -->
<!-- isai:spec_digest=d09849bc6c63af66b231abb051d46a353d776518ca3c913f417c108b252cd1d3 -->
<!-- isai:interface_digest=91e04b470e92f32de989a81c771b34f6891eac3ac66a6ebc43f3a87e37dda06a -->

## Паспорт узла `isai://root` — Корневой узел-драйвер, индекс гиперграфа и транзакционный инжектор связей ISAI

- **Уровень целостности:** `IL_1_KERNEL` | **Видимость:** `PUBLIC`
- **Родительский узел:** `None (Root Node)`
- **Цель (`Goal`):** Обеспечивать универсальную калибровку любой подключаемой модели/агента, двунаправленную индексацию гиперграфа (EAVT/VAET), транзакционную инъекцию/рефакторинг связей-ссылок и сквозную 360°-верификацию контрактов, портов и колец видимости.

### Критерии успеха (`Success Criteria`)
- Первые 586 байт (14 строк) файла /README.md побайтово неизменны и совпадают с эталонным SHA-256 IL-0.
- Субгенетический фундаментал /FUNDAMENTAL.md (IL-1C) синхронизирован с isai://root#NeuroVascularFundamental и ратифицирован в Chronicle.
- Вектор развития /VISION.md синхронизирован с объектом isai://root#MasterVector.
- Все связи, порты IOPortSpec (schema_refs), SymbolBindingSpec и кольца видимости верифицированы через 'isai audit'.
- Команды 'isai nv', 'isai graph', 'isai link', 'isai rsoc' и 'isai recover' работают детерминированно и атомарно.

### Функционал (`Capabilities`)
- Графовая компиляция контекста 'isai rsoc' с доставкой 1-hop интерфейсных стабов соседей.
- Двунаправленный индекс гиперграфа HypergraphIndex ('isai graph query | can-mutate | affected-tests').
- Транзакционный AST-инжектор и рефактор связей LinkMutator ('isai link add | wire-port | refactor | scaffold-node').
- 360°-аудит топологии, чистоты AST node.py, совместимости портов, видимости и Markdown-ссылок ('isai audit').

### Локальные инварианты (`Invariants`)
- THIS-FRAME >> ALL-SUBSEQUENT: ни один дочерний узел не вправе ослабить аксиомы Genesis-ядра.
- Order=Absolute | Logic=Linear | Redundancy=FATAL.
- Любая мутация связей и структур проходит цикл Admission (Shadow Graph) -> Atomic Batch -> Gate A Audit -> Chronicle.

### Адаптер и Связывание Портов (`Adapter & Port Wirings`)
- **Входы (`Inputs`):**
  - `user_intent_or_task` (`TaskManifest | str`, обязательный) [схемы: `isai.protocol:TaskManifest`, `builtins:str`] — Целевой запрос оператора или URI узла для сборки рабочего набора RSoC.
- **Выходы (`Outputs`):**
  - `rsoc_packet` (`dict[str, Any]`, гарантированный) [схемы: `builtins:dict`] — Предвычисленный минимальный пакет контекста RSoC со стабами связанных соседей.
  - `audit_report` (`AuditReport`, гарантированный) [схемы: `isai.protocol:AuditReport`] — Детерминированный вердикт целостности всех колец IL-0..IL-3, портов и ссылок.

### Реестр владения и верифицируемых символов (`Ownership & Symbol Bindings`)
- **Файлы узла (`owned_files`):** `README.md`, `FUNDAMENTAL.md`, `VISION.md`, `AGENTS.md`, `pyproject.toml`, `.gitignore`
- **Служебные файлы (`system_files`):** `.isai/__init__.py`, `.isai/__main__.py`, `.isai/atomic_io.py`, `.isai/constitution.py`, `.isai/contracts.py`, `.isai/protocol.py`, `.isai/domain_models.py`, `.isai/neuro_vascular.py`, `.isai/vector.py`, `.isai/graph_index.py`, `.isai/engine.py`, `.isai/link_mutator.py`, `.isai/node.py`, `.isai/chronicle.jsonl`
- **Экспортируемые сущности (`symbol_bindings`):**
  - `isai://root#GenesisKernel` (`python_attr` → `constitution.py:GENESIS_CONSTITUTION`, видимость: `PUBLIC`)
  - `isai://root#NeuroVascularFundamental` (`python_attr` → `neuro_vascular.py:NEURO_VASCULAR_FUNDAMENTAL`, видимость: `PUBLIC`)
  - `isai://root#AlgedonicProtocol` (`python_attr` → `neuro_vascular.py:AlgedonicDeviationCase`, видимость: `PUBLIC`)
  - `isai://root#MasterVector` (`python_attr` → `vector.py:MASTER_VECTOR`, видимость: `PUBLIC`)
  - `isai://root#ISAINodeSpec` (`python_attr` → `contracts.py:ISAINodeSpec`, видимость: `PUBLIC`)
  - `isai://root#PhaseExecutionProtocol` (`python_attr` → `protocol.py:PhaseExecutionState`, видимость: `PUBLIC`)
  - `isai://root#HypergraphIndex` (`python_attr` → `graph_index.py:HypergraphIndex`, видимость: `PUBLIC`)
  - `isai://root#LinkInjector` (`python_attr` → `link_mutator.py:LinkMutator`, видимость: `PUBLIC`)
  - `isai://root#RSoCCompiler` (`python_attr` → `engine.py:compile_rsoc`, видимость: `PUBLIC`)
  - `isai://root#ChronicleLedger` (`system_artifact` → `chronicle.jsonl`, видимость: `PUBLIC`)
  - `isai://root#AtomicPersistence` (`python_attr` → `atomic_io.py:atomic_transaction_batch`, видимость: `PUBLIC`)

### Типизированные связи и Маршрутизация (`Typed Links & Router`)
- **Типизированные связи (`links`):**
  - `isai://root#GenesisKernel` [`GOVERNED_BY` | RSoC: `NONE`] — Конституционный фундамент IL-0.
  - `isai://root#NeuroVascularFundamental` [`GOVERNED_BY` | RSoC: `NONE`] — Условно-мутируемый субгенетический нервно-сосудистый фундаментал IL-1C (ISAI-NVF v1.0).
  - `isai://root#MasterVector` [`GOVERNED_BY` | RSoC: `NONE`] — Стратегический вектор эволюции системы.
  - `isai://user#OperatorProfile` [`CALIBRATES` | RSoC: `INTERFACE_STUB`] — Калибровка когнитивного профиля оператора.
  - `isai://knowledge#EmpiricalCatalog` [`CALIBRATES` | RSoC: `INTERFACE_STUB`] — Поставка дистиллированных паттернов в RSoC.
  - `isai://tasks#WatchdogService` [`DELEGATES_TO` | RSoC: `INTERFACE_STUB`] — Делегирование фазовых аренд и каскадного надзора.
  - `isai://tasks#CrashRecoveryService` [`DELEGATES_TO` | RSoC: `INTERFACE_STUB`] — Аварийное восстановление после прерванных сессий.
  - `isai://tests#SelfVerificationSuite` [`VERIFIES` | RSoC: `INTERFACE_STUB`] — Базовый контур модульных и аварийных проверок ядра.
  - `isai://tests#HypergraphCrossTestSuite` [`VERIFIES` | RSoC: `INTERFACE_STUB`] — Трёхуровневый контур контрактных кросс-тестов и генеративного фаззинга связей.
  - `isai://tests#NeuroVascularTestSuite` [`VERIFIES` | RSoC: `INTERFACE_STUB`] — Трёхуровневый контур проверки субгенетического фундаментала IL-1C и Алгедонического шлюза.
- **Допустимые переходы (`transitions`):**
  - При `calibrate_operator_context` → `isai://user` [режим: `FAST_READ`] — Чтение когнитивного профиля и компетенций оператора для настройки глубины ответов.
  - При `retrieve_or_distill_knowledge` → `isai://knowledge` [режим: `FAST_READ`] — Запрос практических паттернов перед планированием или дистилляция опыта закрытого таска.
  - При `execute_phased_task` → `isai://tasks` [режим: `STAGED_TRANSACTION`] — Запуск пользовательского таска/исследования в изолированном контуре стейджинга под надзором Watchdog.
  - При `verify_kernel_integrity` → `isai://tests` [режим: `FAST_READ`] — Запуск модульных, контрактных и генеративных кросс-тестов ядра.

<!-- ISAI:SYNC:END -->
