"""Empirical Knowledge Catalog (`isai://knowledge#EmpiricalCatalog`) — Distilled from TASK-000."""

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
            title="Маппинг скрытого пакета .isai и беcколлизионная загрузка узлов node.py",
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
                "инварианты предков, контракт узла и фильтрованные срезы /user/ и /knowledge/) без карт "
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
                "(interface_digest по входам/выходам, символам, инвариантам и переходам) позволяет "
                "Watchdog мгновенно останавливать рекурсивную инвалидацию (Early Cutoff), если "
                "изменилась только внутренняя реализация папки."
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
    ),
)
