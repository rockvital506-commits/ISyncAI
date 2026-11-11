# Улей практических знаний (`knowledge/`)

Структурированное хранилище эмпирических паттернов, архитектурных решений, фактов о среде и антипаттернов (`isai://knowledge#EmpiricalCatalog`), дистиллированных из завершённых тасков и исследований симбиоза **ISAI**.

## Реестр верифицированных единиц знаний (`rev=1`)

| ID | Категория | Краткая суть | Узел | Транзакция |
| :--- | :--- | :--- | :--- | :--- |
| `PAT_GENESIS_PREFIX_GUARD` | `architecture_decision` | Изоляция первых 586 байт `/README.md` (`IL-0`) от динамического блока синхронизации ниже по файлу | `isai://root` | `TX-0001` |
| `PAT_DOT_PACKAGE_AND_ISOLATED_LOADER` | `pattern` | Маппинг пакета `isai -> .isai` + загрузка `.isai/node.py` через изолированные `importlib` пространства имён | `isai://root` | `TX-0001` |
| `PAT_RSOC_CONTROL_DATA_SPLIT` | `pattern` | Подача в окно модели чистого пакета `RSoC` при удержании графа связей и хешей в детерминированном `Watchdog` | `isai://root` | `TX-0001` |
| `PAT_SALSA_INTERFACE_EARLY_CUTOFF` | `pattern` | Отсечение ложных каскадов перевалидации через разделение `spec_digest` и публичного `interface_digest` | `isai://tasks` | `TX-0001` |
| `PAT_DUAL_GATE_ISAI_PEP` | `anti_pattern` | Защита от коррелированной самооценки LLM через двухступенчатый шлюз `Gate A (код/тесты) + Gate B` в `ISAI-PEP v1` | `isai://tests` | `TX-0001` |

<!-- ISAI:SYNC:BEGIN -->
<!-- isai:node_id=isai://knowledge -->
<!-- isai:spec_digest=cebfddc7f16523122dcbd53c637d653ddc6f53858bda007a9004ea67c51c2f56 -->
<!-- isai:interface_digest=a9c47a01b00764192ca3ccce336482c008fa20ef697994d1a44f1a280dc1c14f -->

## Паспорт узла `isai://knowledge` — Улей практических знаний и верифицированных паттернов (Empirical Knowledge Hive)

- **Уровень целостности:** `IL_2_CANONICAL`
- **Родительский узел:** `isai://root`
- **Цель (`Goal`):** Накапливать, дедуплицировать и выдавать по запросу атомарные единицы практического знания (паттерны, архитектурные решения, ограничения среды и антипаттерны), дистиллированные из завершённых тасков и исследований.

### Критерии успеха (`Success Criteria`)
- Каждая запись в каталоге имеет уникальное имя, теги применимости и ссылку на подтверждённый tx_id хроники.
- В хранилище отсутствуют сырые логи и дубликаты (обновление через KnowledgeCatalogSpec.upsert).
- Компилятор RSoC автоматически включает релевантные записи в контекст новых фаз.

### Функционал (`Capabilities`)
- Хранение типизированного каталога KNOWLEDGE_CATALOG в knowledge/.isai/catalog.py.
- Дедуплицирующая консолидация знаний (Upsert) при закрытии тасков из /tasks/.
- Таргетированная выборка практик по узлу и предметным тегам для минимизации контекста модели.

### Локальные инварианты (`Invariants`)
- Запрет на перенос в /knowledge/ неверифицированных черновиков или полных дампов закрытых задач.
- 100% трассируемость каждой единицы знания до записи ChronicleEvent в .isai/chronicle.jsonl.

### Адаптер (`Inputs / Outputs`)
- **Входы (`Inputs`):**
  - `distilled_knowledge_entries` (`tuple[KnowledgeEntry, ...]`, опциональный) — Верифицированные выжимки паттернов и фактов, поступающие при промоушене таска.
- **Выходы (`Outputs`):**
  - `filtered_knowledge_slice` (`list[dict[str, Any]]`, гарантированный) — Релевантные единицы знаний для включения в пакет RSoC текущей фазы.

### Реестр владения и символов (`Ownership & Symbols`)
- **Файлы узла (`owned_files`):** `README.md`
- **Служебные файлы (`system_files`):** `.isai/node.py`, `.isai/catalog.py`
- **Экспортируемые сущности (`defined_symbols`):** `isai://knowledge#EmpiricalCatalog`

### Связи и Маршрутизация (`Router & Transitions`)
- **Связанные сущности (`related_refs`):** `isai://root#GenesisKernel`, `isai://root#RSoCCompiler`, `isai://root#ChronicleLedger`, `isai://tasks#WatchdogService`
- **Допустимые переходы (`transitions`):**
  - При `supply_patterns_to_rsoc` → `isai://root#RSoCCompiler` [режим: `FAST_READ`] — Подача релевантных паттернов и ограничений среды при компиляции контекста фазы.
  - При `consolidate_knowledge_catalog` → `isai://tasks` [режим: `STAGED_TRANSACTION`] — Периодическая компакция и слияние накопленных записей через транзакционную фазу.

<!-- ISAI:SYNC:END -->
