# Улей практических знаний (`knowledge/`)

Структурированное хранилище эмпирических паттернов, архитектурных решений, фактов о среде и антипаттернов (`isai://knowledge#EmpiricalCatalog`), дистиллированных из завершённых тасков и исследований симбиоза **ISAI**.

## Реестр верифицированных единиц знаний (`rev=6`)

| ID | Категория | Краткая суть | Узел | Транзакция |
| :--- | :--- | :--- | :--- | :--- |
| `PAT_GENESIS_PREFIX_GUARD` | `architecture_decision` | Изоляция первых 586 байт `/README.md` (`IL-0`) от динамического блока синхронизации ниже по файлу | `isai://root` | `TX-0001` |
| `PAT_DOT_PACKAGE_AND_ISOLATED_LOADER` | `pattern` | Маппинг пакета `isai -> .isai` + загрузка `.isai/node.py` через изолированные `importlib` пространства имён | `isai://root` | `TX-0001` |
| `PAT_RSOC_CONTROL_DATA_SPLIT` | `pattern` | Подача в окно модели чистого пакета `RSoC` при удержании графа связей и хешей в детерминированном `Watchdog` | `isai://root` | `TX-0001` |
| `PAT_SALSA_INTERFACE_EARLY_CUTOFF` | `pattern` | Отсечение ложных каскадов перевалидации через разделение `spec_digest` и публичного `interface_digest` | `isai://tasks` | `TX-0001` |
| `PAT_DUAL_GATE_ISAI_PEP` | `anti_pattern` | Защита от коррелированной самооценки LLM через двухступенчатый шлюз `Gate A (код/тесты) + Gate B` в `ISAI-PEP v1` | `isai://tests` | `TX-0001` |
| `PAT_VERIFIED_SYMBOL_BINDINGS` | `architecture_decision` | Физически верифицируемые привязки символов `SymbolBindingSpec` с вычисляемым `defined_symbols` (`ZERO-Redundancy`) | `isai://root` | `TX-0002` |
| `PAT_360_HYPERGRAPH_AND_PROSE_IMMUNITY` | `pattern` | 360°-аудит достижимости от `isai://root`, циклобезопасный `N-hop` каскад и валидация ссылок в `Markdown`-прозе | `isai://tests` | `TX-0002` |
| `PAT_ATOMIC_IO_AND_LEASE_RECOVERY` | `pattern` | Атомарный `I/O` (`fsync + os.replace`), `TTL`-аренды `HandleRecord` и идемпотентный `Crash Recovery` (`isai recover`) | `isai://tasks` | `TX-0002` |
| `PAT_EAVT_VAET_BIDIRECTIONAL_INDEX` | `architecture_decision` | Однократная декларация связей с двунаправленным индексом `EAVT + VAET` без ручных обратных ссылок | `isai://root#HypergraphIndex` | `TX-0003` |
| `PAT_BDCT_PORT_WIRING_AND_STRUCTURAL_DIGEST` | `pattern` | Двунаправленная совместимость схем портов (`BDCT`) и структурный дайджест `Pydantic`-моделей в `interface_digest` | `isai://root#ISAINodeSpec` | `TX-0003` |
| `PAT_TRANSACTIONAL_AST_LINK_MUTATOR_AND_STATEFUL_PBT` | `pattern` | Транзакционный AST-инжектор связей (`LinkMutator`) с откатом и генеративным `Hypothesis` фаззингом | `isai://root#LinkInjector` | `TX-0003` |
| `PAT_SUB_GENESIS_IL1C_AND_ALGEDONIC_RATIFICATION` | `architecture_decision` | Условно-мутируемое кольцо `IL-1C` (`ISAI-NVF`) со сверкой `SHA-256` по `RATIFY_FUNDAMENTAL` и 6-шаговым Алгедоническим шлюзом | `isai://root#NeuroVascularFundamental` | `TX-0005` |
| `PAT_BIMODAL_RSOC_PRIMACY_RECENCY_SANDWICH` | `pattern` | Бимодальная подача `IL-1C` в `RSoC v0.2.5`: `Primacy Head` сразу после `Genesis` + `terminal_execution_guard` в конце пакета | `isai://root#RSoCCompiler` | `TX-0005` |
| `PAT_EPHEMERAL_STAGING_SCAFFOLD_AND_SANDBOX_ISOLATION` | `environment_fact` | Атомарная связка `scaffold-node` с `active_tasks` (`PREC-10`) и нормализация классов изолированного загрузчика (`PREC-11`) | `isai://root#LinkInjector` | `TX-0005` |

<!-- ISAI:SYNC:BEGIN -->
<!-- isai:node_id=isai://knowledge -->
<!-- isai:spec_digest=c3f203b8d0f61251762776c8e705996a52103b0a150cb811c4791205c63fe41b -->
<!-- isai:interface_digest=f14da2d5c9dd1d5583fdb9e6a58adbcafe96e2df71ac8ba08453728a0a6e4917 -->

## Паспорт узла `isai://knowledge` — Улей практических знаний и верифицированных паттернов (Empirical Knowledge Hive)

- **Уровень целостности:** `IL_2_CANONICAL` | **Видимость:** `PUBLIC`
- **Родительский узел:** `isai://root`
- **Цель (`Goal`):** Накапливать, дедуплицировать и выдавать по запросу атомарные единицы практического знания (паттерны, архитектурные решения, ограничения среды и антипаттерны), дистиллированные из завершённых тасков и исследований.

### Критерии успеха (`Success Criteria`)
- Каждая запись в каталоге имеет уникальное имя, теги применимости и ссылку на подтверждённый tx_id хроники.
- В хранилище отсутствуют сырые логи и дубликаты (обновление через KnowledgeCatalogSpec.upsert).
- Компилятор RSoC автоматически включает релевантные записи по связанным узлам и тегам.

### Функционал (`Capabilities`)
- Хранение типизированного каталога KNOWLEDGE_CATALOG в knowledge/.isai/catalog.py.
- Дедуплицирующая консолидация знаний (Upsert) при закрытии тасков из /tasks/.
- Таргетированная выборка практик по графу связей и предметным тегам для минимизации контекста модели.

### Локальные инварианты (`Invariants`)
- Запрет на перенос в /knowledge/ неверифицированных черновиков или полных дампов закрытых задач.
- 100% трассируемость каждой единицы знания до записи ChronicleEvent в .isai/chronicle.jsonl.

### Адаптер и Связывание Портов (`Adapter & Port Wirings`)
- **Входы (`Inputs`):**
  - `distilled_knowledge_envelope` (`PhaseOutputEnvelope`, опциональный) [схемы: `isai.protocol:PhaseOutputEnvelope`] — Верифицированный конверт реализации и дистилляции, поступающий при промоушене таска.
- **Выходы (`Outputs`):**
  - `filtered_knowledge_slice` (`dict[str, Any]`, гарантированный) [схемы: `builtins:dict`] — Релевантные единицы знаний для включения в пакет RSoC текущей фазы.
- **Контрактная коммутация портов (`port_wirings`):**
  - вход `distilled_knowledge_envelope` ← `isai://tasks#WatchdogService` (выход `promoted_artifacts_and_distillation`) — Приём верифицированных результатов закрытого таска для дистилляции паттернов.

### Реестр владения и верифицируемых символов (`Ownership & Symbol Bindings`)
- **Файлы узла (`owned_files`):** `README.md`
- **Служебные файлы (`system_files`):** `.isai/node.py`, `.isai/catalog.py`
- **Экспортируемые сущности (`symbol_bindings`):**
  - `isai://knowledge#EmpiricalCatalog` (`python_attr` → `catalog.py:KNOWLEDGE_CATALOG`, видимость: `PUBLIC`)

### Типизированные связи и Маршрутизация (`Typed Links & Router`)
- **Типизированные связи (`links`):**
  - `isai://root#GenesisKernel` [`GOVERNED_BY` | RSoC: `NONE`]
  - `isai://root#RSoCCompiler` [`CALIBRATES` | RSoC: `INTERFACE_STUB`] — Интеграция знаний в графовый пакет RSoC.
  - `isai://root#ChronicleLedger` [`CONSUMES_CONTRACT` | RSoC: `INTERFACE_STUB`] — Проверка origin_tx_id каждой записи каталога по хронике.
  - `isai://root#NeuroVascularFundamental` [`GOVERNED_BY` | RSoC: `NONE`] — Подчинение субгенетическому нервно-сосудистому фундаменталу IL-1C.
- **Допустимые переходы (`transitions`):**
  - При `supply_patterns_to_rsoc` → `isai://root#RSoCCompiler` [режим: `FAST_READ`] — Подача релевантных паттернов и ограничений среды при компиляции контекста фазы.
  - При `consolidate_knowledge_catalog` → `isai://tasks` [режим: `STAGED_TRANSACTION`] — Периодическая компакция и слияние накопленных записей через транзакционную фазу.

<!-- ISAI:SYNC:END -->
