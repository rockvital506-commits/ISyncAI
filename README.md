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


<!-- ISAI:SYNC:BEGIN -->
<!-- isai:node_id=isai://root -->
<!-- isai:spec_digest=ab7bba045c8104734b5364a261a1a2ea3c12b8487e7dd6ee9629c707c7070ffc -->
<!-- isai:interface_digest=77035afa9a40320491389b53d2e64622a82d74cb8b495793184d2cec62e51ccf -->

## Паспорт узла `isai://root` — Корневой узел-драйвер и конституционное ядро ISyncAI (ISAI)

- **Уровень целостности:** `IL_1_KERNEL`
- **Родительский узел:** `None (Root Node)`
- **Цель (`Goal`):** Обеспечивать универсальную калибровку любой подключаемой модели/агента, конституционный контроль целостности репозитория и маршрутизацию по четырём системным ульям (.isai/, user/, knowledge/, tasks/) и контуру верификации (tests/).

### Критерии успеха (`Success Criteria`)
- Первые 586 байт (14 строк) файла /README.md побайтово неизменны и совпадают с эталонным SHA-256 IL-0.
- Вектор развития /VISION.md синхронизирован с объектом isai://root#MasterVector.
- 100% директорий и файлов репозитория включены в граф владения без единого узла-сироты (zero-orphan-nodes).
- Команда 'python -m isai audit' завершается со статусом valid=True и 0 ошибок.

### Функционал (`Capabilities`)
- Калибровка подключаемого агента через тонкий бутлоадер AGENTS.md и компилятор контекста 'isai rsoc'.
- Детерминированная верификация топологии, ссылок EntityRef, хешей синхронизации и хроники ('isai audit').
- Автоматическая проекция контрактов .isai/node.py в парные секции README.md и VISION.md ('isai sync').
- Хранение базовых схем, протокола фаз ISAI-PEP v1 и неизменяемого журнала транзакций .isai/chronicle.jsonl.

### Локальные инварианты (`Invariants`)
- THIS-FRAME >> ALL-SUBSEQUENT: ни один дочерний узел не вправе ослабить аксиомы Genesis-ядра.
- Order=Absolute | Logic=Linear | Redundancy=FATAL.
- Любая мутация канонических структур проходит цикл AUDIT -> CONSTRUCT -> CHRONICLE.

### Адаптер (`Inputs / Outputs`)
- **Входы (`Inputs`):**
  - `user_intent_or_task` (`TaskManifest | EntityRef`, обязательный) — Целевой запрос оператора или идентификатор узла для сборки рабочего набора RSoC.
- **Выходы (`Outputs`):**
  - `rsoc_packet` (`dict[str, Any]`, гарантированный) — Предвычисленный минимальный пакет контекста (Resultant Set of Context) для окна модели.
  - `audit_report` (`AuditReport`, гарантированный) — Детерминированный вердикт целостности всех колец IL-0..IL-3.

### Реестр владения и символов (`Ownership & Symbols`)
- **Файлы узла (`owned_files`):** `README.md`, `VISION.md`, `AGENTS.md`, `pyproject.toml`, `.gitignore`
- **Служебные файлы (`system_files`):** `.isai/__init__.py`, `.isai/__main__.py`, `.isai/constitution.py`, `.isai/contracts.py`, `.isai/protocol.py`, `.isai/domain_models.py`, `.isai/vector.py`, `.isai/engine.py`, `.isai/node.py`, `.isai/chronicle.jsonl`
- **Экспортируемые сущности (`defined_symbols`):** `isai://root#GenesisKernel`, `isai://root#MasterVector`, `isai://root#ISAINodeSpec`, `isai://root#PhaseExecutionProtocol`, `isai://root#RSoCCompiler`, `isai://root#ChronicleLedger`

### Связи и Маршрутизация (`Router & Transitions`)
- **Связанные сущности (`related_refs`):** `isai://root#GenesisKernel`, `isai://root#MasterVector`, `isai://user#OperatorProfile`, `isai://knowledge#EmpiricalCatalog`, `isai://tasks#WatchdogService`, `isai://tests#SelfVerificationSuite`
- **Допустимые переходы (`transitions`):**
  - При `calibrate_operator_context` → `isai://user` [режим: `FAST_READ`] — Чтение когнитивного профиля и компетенций оператора для настройки глубины ответов.
  - При `retrieve_or_distill_knowledge` → `isai://knowledge` [режим: `FAST_READ`] — Запрос практических паттернов перед планированием или дистилляция опыта закрытого таска.
  - При `execute_phased_task` → `isai://tasks` [режим: `STAGED_TRANSACTION`] — Запуск пользовательского таска/исследования в изолированном контуре стейджинга под надзором Watchdog.
  - При `verify_kernel_integrity` → `isai://tests` [режим: `FAST_READ`] — Запуск модульных автотестов самоверификации ядра и детекторов нарушений.

<!-- ISAI:SYNC:END -->
