"""Empirical Knowledge Catalog (`isai://knowledge#EmpiricalCatalog`) — Distilled from TASK-000..TASK-002."""

from __future__ import annotations

from isai.domain_models import KnowledgeCatalogSpec, KnowledgeEntry

KNOWLEDGE_CATALOG = KnowledgeCatalogSpec(
    catalog_ref="isai://knowledge#EmpiricalCatalog",
    entries=(
        KnowledgeEntry(
            entry_id="PAT_GENESIS_PREFIX_GUARD",
            category="architecture_decision",
            title="Криптографическая изоляция Genesis-заголовка от синхронизируемого паспорта",
            distilled_insight=(
                "Сохранение первых 586 байт (14 строк) корневого README.md под защитой SHA-256 "
                "при размещении динамического блока синхронизации ниже 586-го байта со встроенным "
                "spec_digest устраняет петлю взаимного хеширования и гарантирует 100% неприкосновенность IL-0."
            ),
            applicability_tags=("genesis", "sync", "security", "isai"),
            related_node_ref="isai://root",
            origin_tx_id="TX-0001",
            verified_revision=1,
        ),
        KnowledgeEntry(
            entry_id="PAT_DOT_PACKAGE_AND_ISOLATED_LOADER",
            category="pattern",
            title="Маппинг скрытого пакета .isai и бесколлизионная загрузка узлов node.py",
            distilled_insight=(
                "Привязка пакета 'isai' к директории '.isai' в pyproject.toml даёт чистые импорты ядра, "
                "а динамическая загрузка распределённых файлов '.isai/node.py' через importlib.util "
                "с уникальным namespace на основе относительного пути исключает коллизии в sys.modules."
            ),
            applicability_tags=("python", "pydantic", "packaging", "topology"),
            related_node_ref="isai://root",
            origin_tx_id="TX-0001",
            verified_revision=1,
        ),
        KnowledgeEntry(
            entry_id="PAT_RSOC_CONTROL_DATA_SPLIT",
            category="pattern",
            title="Разделение Data Plane (RSoC) и Control Plane (Watchdog) по модели GPO RSoP",
            distilled_insight=(
                "Передача в окно модели только предвычисленного пакета RSoC (Enforced-аксиомы, вектор, "
                "инварианты предков, контракт узла, 1-hop стабы соседей и срезы /user/ и /knowledge/) без карт "
                "хешей и дескрипторов экономит контекст и исключает ошибки ручного учёта связей."
            ),
            applicability_tags=("ai", "context", "rsoc", "windows", "optimization"),
            related_node_ref="isai://root",
            origin_tx_id="TX-0001",
            verified_revision=1,
        ),
        KnowledgeEntry(
            entry_id="PAT_SALSA_INTERFACE_EARLY_CUTOFF",
            category="pattern",
            title="Двухуровневое хеширование узла (spec_digest vs interface_digest) для отсечения каскадов",
            distilled_insight=(
                "Разделение полного хеша синхронизации (spec_digest) и хеша публичного контракта "
                "(interface_digest по входам/выходам со структурным хешем схем, символам, инвариантам и переходам) "
                "позволяет Watchdog мгновенно останавливать рекурсивную инвалидацию (Early Cutoff) при локальных правках."
            ),
            applicability_tags=("watchdog", "validation", "cascade", "architecture"),
            related_node_ref="isai://tasks",
            origin_tx_id="TX-0001",
            verified_revision=1,
        ),
        KnowledgeEntry(
            entry_id="PAT_DUAL_GATE_ISAI_PEP",
            category="anti_pattern",
            title="Защита от коррелированной самооценки и раздувания рефлексии в цикле фазы",
            distilled_insight=(
                "Чистая LLM-самооценка подвержена языковому взлому метрик и росту объёма при повторах. "
                "Протокол ISAI-PEP v1 блокирует это за счёт обязательного внешнего Gate A (Python/Pydantic/pytest) "
                "перед Gate B, условного дельта-исследования и жёсткого формата DiagnosticEntry (лимит 3 итерации)."
            ),
            applicability_tags=("ai", "agents", "protocol", "testing", "isai"),
            related_node_ref="isai://tests",
            origin_tx_id="TX-0001",
            verified_revision=1,
        ),
        KnowledgeEntry(
            entry_id="PAT_VERIFIED_SYMBOL_BINDINGS",
            category="architecture_decision",
            title="Физически верифицируемые привязки символов SymbolBindingSpec без дублирования",
            distilled_insight=(
                "Замена декларативного списка имён defined_symbols на типизированный реестр SymbolBindingSpec "
                "(python_attr, system_artifact, owned_artifact) с вычисляемым @property defined_symbols исключает "
                "мёртвые экспорты: 'isai audit' проверяет реальное наличие Python-объектов и артефактов на диске."
            ),
            applicability_tags=("contracts", "audit", "python", "topology", "isai"),
            related_node_ref="isai://root",
            origin_tx_id="TX-0002",
            verified_revision=2,
        ),
        KnowledgeEntry(
            entry_id="PAT_360_HYPERGRAPH_AND_PROSE_IMMUNITY",
            category="pattern",
            title="Замкнутый 360°-аудит: достижимость от корня, N-hop BFS и ссылки в Markdown-прозе",
            distilled_insight=(
                "Комбинация нисходящего обхода transitions от isai://root (с учётом динамических active_tasks), "
                "циклобезопасного транзитивного N-hop BFS для каскадов и сканера Markdown-документов (после очистки "
                "fenced code blocks и шаблонных плейсхолдеров <...>/[...]) устраняет острова и протухшие ссылки в прозе."
            ),
            applicability_tags=("hypergraph", "markdown", "cascade", "audit", "testing"),
            related_node_ref="isai://tests",
            origin_tx_id="TX-0002",
            verified_revision=2,
        ),
        KnowledgeEntry(
            entry_id="PAT_ATOMIC_IO_AND_LEASE_RECOVERY",
            category="pattern",
            title="Атомарная запись (fsync + os.replace) и идемпотентный Crash Recovery аренд с TTL",
            distilled_insight=(
                "Запись всех критических артефактов через соседний .isai_tmp_* файл с fsync файла и директории "
                "в связке с TTL-арендами HandleRecord позволяет команде 'isai recover' детерминированно лечить "
                "прерванные сессии (чистка темпов, просроченных локов, осиротевших стейджингов) без лишних коммитов на чистом репо."
            ),
            applicability_tags=("recovery", "watchdog", "atomic_io", "reliability", "tasks"),
            related_node_ref="isai://tasks",
            origin_tx_id="TX-0002",
            verified_revision=2,
        ),
        KnowledgeEntry(
            entry_id="PAT_EAVT_VAET_BIDIRECTIONAL_INDEX",
            category="architecture_decision",
            title="Однократная декларация связей с двунаправленным индексом EAVT + VAET (Datomic-модель)",
            distilled_insight=(
                "Хранение рёбер только на стороне источника (EdgeLinkSpec, PortWiringSpec) с автоматической сборкой "
                "прямого (EAVT) и обратного (VAET) индексов по коду, портам и Markdown-прозе обеспечивает O(1) проверку "
                "'can-mutate' и 'Finalizer'-защиту от удаления узлов при строгом соблюдении аксиомы ZERO-Redundancy."
            ),
            applicability_tags=("hypergraph", "index", "datomic", "links", "isai"),
            related_node_ref="isai://root#HypergraphIndex",
            origin_tx_id="TX-0003",
            verified_revision=3,
        ),
        KnowledgeEntry(
            entry_id="PAT_BDCT_PORT_WIRING_AND_STRUCTURAL_DIGEST",
            category="pattern",
            title="Двунаправленная контрактная совместимость портов (BDCT) и структурный дайджест схем",
            distilled_insight=(
                "Привязка входов и выходов IOPortSpec к реальным Python/Pydantic типам (schema_refs) с проверкой "
                "включения подтипов set(producer) <= set(consumer) и включением JSON-схемы модели в interface_digest "
                "перехватывает несовместимые мутации сигнатур без запуска тяжёлых интеграционных пайплайнов."
            ),
            applicability_tags=("contracts", "ports", "bdct", "pydantic", "validation"),
            related_node_ref="isai://root#ISAINodeSpec",
            origin_tx_id="TX-0003",
            verified_revision=3,
        ),
        KnowledgeEntry(
            entry_id="PAT_TRANSACTIONAL_AST_LINK_MUTATOR_AND_STATEFUL_PBT",
            category="pattern",
            title="Транзакционный AST-инжектор связей (LinkMutator) и генеративный Stateful фаззинг (Hypothesis)",
            distilled_insight=(
                "Все мутации связей, портов и символов выполняются через AST-рендерер внутри atomic_transaction_batch "
                "(включая pre-image бэкап README/VISION/snapshot) и прямую компиляцию исходников без .pyc-кэша "
                "(исключая коллизии PEP 3147 (int(mtime), size), обнаруженные автоматом Hypothesis RuleBasedStateMachine)."
            ),
            applicability_tags=("ast", "refactoring", "transactions", "hypothesis", "testing"),
            related_node_ref="isai://root#LinkInjector",
            origin_tx_id="TX-0003",
            verified_revision=3,
        ),
        KnowledgeEntry(
            entry_id="PAT_SUB_GENESIS_IL1C_AND_ALGEDONIC_RATIFICATION",
            category="architecture_decision",
            title="Субконституционное кольцо IL-1C (ISAI-NVF) с криптографической Chronicle-ратификацией и Алгедоническим шлюзом",
            distilled_insight=(
                "Выделение условно-мутируемого кольца IL_1C_FUNDAMENTAL (между IL-0 и IL-1) с двойным изоморфным носителем "
                "(.isai/neuro_vascular.py <-> FUNDAMENTAL.md), сверкой SHA-256 DSL с последней записью RATIFY_FUNDAMENTAL "
                "(operator_approved=True) в chronicle.jsonl и блокировкой WRITE_LEASE/refactor без 6-шагового автомата "
                "AlgedonicDeviationCase гарантирует нулевую потерю смыслов при 100% суверенитете Оператора."
            ),
            applicability_tags=("constitution", "il-1c", "algedonic", "governance", "isai"),
            related_node_ref="isai://root#NeuroVascularFundamental",
            origin_tx_id="TX-0005",
            verified_revision=5,
        ),
        KnowledgeEntry(
            entry_id="PAT_BIMODAL_RSOC_PRIMACY_RECENCY_SANDWICH",
            category="pattern",
            title="Бимодальная подача субгенетического фрейма в RSoC (Primacy Head + Terminal Recency Guard)",
            distilled_insight=(
                "Размещение одного монолитного блока правил только в начале длинного RSoC-пакета ослабляет стоп-триггеры "
                "из-за U-образного провала внимания в середине окна ('Lost in the Middle'); разделение на "
                "enforced_neuro_vascular_frame сразу после Genesis и terminal_execution_guard последним ключом пакета "
                "удерживает оба пика внимания (Primacy Sink + RoPE Recency)."
            ),
            applicability_tags=("rsoc", "attention", "lnte", "context", "prompting"),
            related_node_ref="isai://root#RSoCCompiler",
            origin_tx_id="TX-0005",
            verified_revision=5,
        ),
        KnowledgeEntry(
            entry_id="PAT_EPHEMERAL_STAGING_SCAFFOLD_AND_SANDBOX_ISOLATION",
            category="environment_fact",
            title="Атомарная связка scaffold-node с active_tasks (PREC-10) и нормализация классов изолированного загрузчика (PREC-11)",
            distilled_insight=(
                "Эфемерные узлы tasks/TASK-* не имеют статических переходов от isai://tasks, поэтому scaffold-node и "
                "decommission-node обязаны атомарно обновлять state_snapshot.json#active_tasks; а при динамической "
                "компиляции доменных модулей в песочнице (load_module_attr_isolated) самоопределённые Pydantic-классы "
                "нормализуются через model_validate(obj.model_dump()) во избежание ложного расхождения isinstance."
            ),
            applicability_tags=("staging", "sandbox", "pydantic", "loader", "transactions"),
            related_node_ref="isai://root#LinkInjector",
            origin_tx_id="TX-0005",
            verified_revision=5,
        ),
        KnowledgeEntry(
            entry_id="PAT_OPERADIC_PIPELINE_VS_HYPERGRAPH_BOUNDARY",
            category="architecture_decision",
            title="Граница применимости операдной сборки (Ген/ДНК/Геном) и гиперграфа EAVT/VAET (R&D TASK-004)",
            distilled_insight=(
                "Древовидная операдная сборка с полярностями {PRE, POST, AROUND, PARALLEL}, разреженными локусами и "
                "декларативными EntityRef-ссылками даёт 100% выразительность конвейеров (RSoC, Audit, Shadow-Tx), "
                "0% конфликтов слияния и до 5.14x ускорения при плоской/AST-компиляции, но на ромбовидных DAG и циклах "
                "порождает экспоненциальное дублирование (2^k) и RecursionError — макротопология обязана оставаться гиперграфом."
            ),
            applicability_tags=("operad", "pipeline", "hypergraph", "rsoc", "architecture"),
            related_node_ref="isai://root#ISAINodeSpec",
            origin_tx_id="TX-0007",
            verified_revision=7,
        ),
        KnowledgeEntry(
            entry_id="PAT_TRIPLET_GENOTYPE_EPIGENOME_INTERFACE_HASH",
            category="pattern",
            title="Триплетная криптографическая идентификация конвейеров: Нормальная форма ДНК + Эпигеном + Интерфейс",
            distilled_insight=(
                "Хеш рантайм-замыканий недетерминирован между процессами, а сырой хеш словаря ДНК чувствителен к "
                "перенумерации и вложенности; устойчивую идентификацию обеспечивает триплет: genotype_nf_sha "
                "(нормальная форма шагов + AST без докстрингов), epigenetic_sha (связанные параметры RSoC) и "
                "interface_sha (типы входов/выходов + маска эффектов для отсечения каскадов Salsa Early-Cutoff)."
            ),
            applicability_tags=("hashing", "salsa", "contracts", "unison", "validation"),
            related_node_ref="isai://root#HypergraphIndex",
            origin_tx_id="TX-0007",
            verified_revision=7,
        ),
        KnowledgeEntry(
            entry_id="PAT_BIO_UNIVERSE_PYDANTIC_HOLON_EPOCH_RIBOSOME",
            category="architecture_decision",
            title="Каталогизированная Био-Вселенная (Атом/Ген/Плазмида/Рибосома) и Эпохальное связывание Pydantic-Холонов (R&D TASK-005)",
            distilled_insight=(
                "Хранение в Pydantic-объектах (Holon) символьных URI-кодонов к Вселенной снимает 110.7x раздутие ромбовидных DAG "
                "через мемоизацию Плазмид, ловит 100% структурных ошибок на model_validate(context={'universe': u}), а кэш Рибосомы "
                "с проверкой эпохи (compiled_epoch == universe.epoch) ускоряет диспетчеризацию в 3.18x и мгновенно распространяет "
                "чистые оптимизации Генов на все объекты под защитой Дифференциального шлюза эквивалентности и frozen=True Атомов."
            ),
            applicability_tags=("bio_universe", "ribosome", "pydantic", "plasmid", "optimization"),
            related_node_ref="isai://root#ISAINodeSpec",
            origin_tx_id="TX-0008",
            verified_revision=8,
        ),
        KnowledgeEntry(
            entry_id="PAT_GENE_GRANULARITY_CROSSOVER_AND_VAET_APOPTOSIS",
            category="pattern",
            title="Порог гранулярности Генов (>=3 SLOC), LNTE-срез контекста и Апоптоз мёртвых генов по VAET (R&D TASK-005)",
            distilled_insight=(
                "Нано-гены в 1 строку раздувают JSON-ДНК (-26.7%..-57.5% токенов), тогда как мезо-гены >=3..25 SLOC с LNTE-нотацией "
                "и дедуплицированными микро-контрактами экономят 70.8%..96.2% токенов, транзитивный срез контекста — 74.6%..97.2%, "
                "упаковка генов в Хромосомы ускоряет I/O в 3.53x, а сборщик Апоптоза по индексу VAET (ref_count==0) вычищает 100% "
                "зомби-генов (54.5% каталога после 300 качественных форков)."
            ),
            applicability_tags=("granularity", "lnte", "rsoc", "apoptosis", "vaet"),
            related_node_ref="isai://root#RSoCCompiler",
            origin_tx_id="TX-0008",
            verified_revision=8,
        ),
        KnowledgeEntry(
            entry_id="PAT_DUAL_ZONE_LNTE_SHELL_AND_DEMATERIALIZATION_BARRIER",
            category="architecture_decision",
            title="Чистые LNTE-оболочки knowledge/, Двухзонная арена тасков и Барьер дематериализации (R&D TASK-006)",
            distilled_insight=(
                "Отбор сущностей из knowledge/ без материализации через Degree-Penalized BioGraph-ранжирование сжимает контекст в 2668x "
                "и снижает шум супер-хабов со 100% до 10%; разделение Тасков на Зону А (компилируемый Python + Dual-Guard EWMA маркеры "
                "отклонений с дедупликацией корневой причины) и Зону Б (агенты) экономит 99.95% токенов, а барьер дематериализации "
                "в конце итерации удерживает плоское окно O(1) (710 против 29420 токенов, -97.6% на 20 шагах)."
            ),
            applicability_tags=("lnte", "dual_zone", "dematerialization", "retrieval", "telemetry"),
            related_node_ref="isai://tasks#WatchdogService",
            origin_tx_id="TX-0009",
            verified_revision=9,
        ),
        KnowledgeEntry(
            entry_id="PAT_CRYO_TRANSITIVE_APOPTOSIS_AND_AST_HOMOLOGY",
            category="pattern",
            title="Транзитивный Крио-Апоптоз, AST-консолидация гомологов и Зеркальный реестр рукопожатий (R&D TASK-006)",
            distilled_insight=(
                "Наивное мгновенное удаление элементов без прямых ссылок на сущности ломает 100% под-генов Плазмид и URI-откаты savepoint; "
                "решение — транзитивный Mark-and-Sweep + Cryo-Archive (100% откат, 0% пересозданий), периодическая AST-консолидация "
                "параметрических клонов (-59.2% раздутия пула) и подтверждённое зеркало связей EAVT/VAET (-100.5x перезаписей при рефакторинге)."
            ),
            applicability_tags=("garbage_collection", "cryo_archive", "ast_homology", "links", "bio_universe"),
            related_node_ref="isai://root#HypergraphIndex",
            origin_tx_id="TX-0009",
            verified_revision=9,
        ),
        KnowledgeEntry(
            entry_id="PAT_VECTOR_MUTATION_LEDGER_AND_CHECKBOX_RATIFICATION",
            category="architecture_decision",
            title="Append-only реестр мутаций вектора, чекбоксная ратификация из промпта и атомарная церемония применения (R&D TASK-007)",
            distilled_insight=(
                "Вектор цели нельзя править файлом: истина — детерминированная свёртка append-only журнала, где каждая "
                "мутация несёт anchor_fingerprint, base_vector_digest, обоснование (>=60 символов) и доказательства. "
                "Единственный канал ратификации — следующий промпт Оператора (чекбокс [x] VMP-… либо отдельная строка "
                "'подтвердить вектор системы'), причём фенсед-код, inline-код и цитаты не являются сигналом (30/30 "
                "состязательных форм). Подтверждение и материализация обязаны происходить в одном шлюзе: отложенное "
                "применение оставляет CONFIRMED-предложение без возможности применения после сдвига индексов якорей "
                "(0 заблокированных ратификаций на 1200 ходах, 0 потерянных предложений, 0 применений без подтверждения)."
            ),
            applicability_tags=("vector_governance", "ledger", "ratification", "checkbox", "anti_self_confirmation"),
            related_node_ref="isai://root#VectorMutationLedger",
            origin_tx_id="TX-0009",
            verified_revision=9,
        ),
        KnowledgeEntry(
            entry_id="PAT_PRE_PR_GATE_V_AND_ATOMIC_VECTOR_APPLY",
            category="pattern",
            title="Шлюз Gate V перед PR, инъекционное мутационное тестирование (14/14) и побайтовый откат церемонии вектора",
            distilled_insight=(
                "Статус 'системных отклонений не выявлено' обязан выдаваться только инструментом вместе с SHA-256 "
                "дайджестом набора доказательств, а не утверждаться прозой. 26 read-only проверок в 6 доменах против 14 "
                "классов инъекций дают 100% полноту при 0% ложных срабатываний (в среднем ~86 мс). Материализация "
                "мутации должна проектироваться из самой спецификации: снапшот, собранный из ещё не записанного файла, "
                "отстаёт на ревизию, а откат атомарного пакета восстанавливает vector.py, VISION.md и снапшот побайтово — "
                "состояние аудита после сбоя идентично состоянию до него. Дублирующая проверка усечения журнала удалена "
                "по ZERO-Redundancy без потери полноты."
            ),
            applicability_tags=("gate_v", "pre_pr", "mutation_testing", "rollback", "atomic_transaction"),
            related_node_ref="isai://root#SystemHealthGate",
            origin_tx_id="TX-0009",
            verified_revision=9,
        ),
    ),
)
