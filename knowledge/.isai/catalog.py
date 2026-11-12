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
    ),
)
