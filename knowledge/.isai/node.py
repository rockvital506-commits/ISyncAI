"""Empirical Knowledge Store Hive Node (`isai://knowledge` — DriverStore / Pattern Store Equivalent)."""

from __future__ import annotations

from isai.constitution import IntegrityLevel
from isai.contracts import IOPortSpec, ISAINodeSpec, PhaseMode, TransitionRule

NODE = ISAINodeSpec(
    node_id="isai://knowledge",
    title="Улей практических знаний и верифицированных паттернов (Empirical Knowledge Hive)",
    integrity_level=IntegrityLevel.IL_2_CANONICAL,
    parent_ref="isai://root",
    goal=(
        "Накапливать, дедуплицировать и выдавать по запросу атомарные единицы практического "
        "знания (паттерны, архитектурные решения, ограничения среды и антипаттерны), "
        "дистиллированные из завершённых тасков и исследований."
    ),
    success_criteria=(
        "Каждая запись в каталоге имеет уникальное имя, теги применимости и ссылку на подтверждённый tx_id хроники.",
        "В хранилище отсутствуют сырые логи и дубликаты (обновление через KnowledgeCatalogSpec.upsert).",
        "Компилятор RSoC автоматически включает релевантные записи в контекст новых фаз.",
    ),
    capabilities=(
        "Хранение типизированного каталога KNOWLEDGE_CATALOG в knowledge/.isai/catalog.py.",
        "Дедуплицирующая консолидация знаний (Upsert) при закрытии тасков из /tasks/.",
        "Таргетированная выборка практик по узлу и предметным тегам для минимизации контекста модели.",
    ),
    invariants=(
        "Запрет на перенос в /knowledge/ неверифицированных черновиков или полных дампов закрытых задач.",
        "100% трассируемость каждой единицы знания до записи ChronicleEvent в .isai/chronicle.jsonl.",
    ),
    inputs=(
        IOPortSpec(
            name="distilled_knowledge_entries",
            contract_type="tuple[KnowledgeEntry, ...]",
            description="Верифицированные выжимки паттернов и фактов, поступающие при промоушене таска.",
            required=False,
        ),
    ),
    outputs=(
        IOPortSpec(
            name="filtered_knowledge_slice",
            contract_type="list[dict[str, Any]]",
            description="Релевантные единицы знаний для включения в пакет RSoC текущей фазы.",
        ),
    ),
    owned_files=("README.md",),
    system_files=("node.py", "catalog.py"),
    defined_symbols=("EmpiricalCatalog",),
    related_refs=(
        "isai://root#GenesisKernel",
        "isai://root#RSoCCompiler",
        "isai://root#ChronicleLedger",
        "isai://tasks#WatchdogService",
    ),
    transitions=(
        TransitionRule(
            trigger="supply_patterns_to_rsoc",
            target_ref="isai://root#RSoCCompiler",
            phase_mode=PhaseMode.FAST_READ,
            description="Подача релевантных паттернов и ограничений среды при компиляции контекста фазы.",
        ),
        TransitionRule(
            trigger="consolidate_knowledge_catalog",
            target_ref="isai://tasks",
            phase_mode=PhaseMode.STAGED_TRANSACTION,
            description="Периодическая компакция и слияние накопленных записей через транзакционную фазу.",
        ),
    ),
)
