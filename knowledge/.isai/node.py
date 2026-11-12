"""Empirical Knowledge Store Hive Node (`isai://knowledge` — DriverStore / Pattern Store Equivalent)."""

from __future__ import annotations

from isai.constitution import IntegrityLevel
from isai.contracts import (
    EdgeKind,
    EdgeLinkSpec,
    IOPortSpec,
    ISAINodeSpec,
    PhaseMode,
    PortWiringSpec,
    RSoCDeliveryPolicy,
    SymbolBindingKind,
    SymbolBindingSpec,
    SymbolVisibility,
    TransitionRule,
    VisibilityScope,
)

NODE = ISAINodeSpec(
    node_id='isai://knowledge',
    title='Улей практических знаний и верифицированных паттернов (Empirical Knowledge Hive)',
    integrity_level=IntegrityLevel.IL_2_CANONICAL,
    visibility=VisibilityScope.PUBLIC,
    parent_ref='isai://root',
    goal='Накапливать, дедуплицировать и выдавать по запросу атомарные единицы практического знания (паттерны, архитектурные решения, ограничения среды и антипаттерны), дистиллированные из завершённых тасков и исследований.',
    success_criteria=(
        'Каждая запись в каталоге имеет уникальное имя, теги применимости и ссылку на подтверждённый tx_id хроники.',
        'В хранилище отсутствуют сырые логи и дубликаты (обновление через KnowledgeCatalogSpec.upsert).',
        'Компилятор RSoC автоматически включает релевантные записи по связанным узлам и тегам.',
    ),
    capabilities=(
        'Хранение типизированного каталога KNOWLEDGE_CATALOG в knowledge/.isai/catalog.py.',
        'Дедуплицирующая консолидация знаний (Upsert) при закрытии тасков из /tasks/.',
        'Таргетированная выборка практик по графу связей и предметным тегам для минимизации контекста модели.',
    ),
    invariants=(
        'Запрет на перенос в /knowledge/ неверифицированных черновиков или полных дампов закрытых задач.',
        '100% трассируемость каждой единицы знания до записи ChronicleEvent в .isai/chronicle.jsonl.',
    ),
    inputs=(
        IOPortSpec(
            name='distilled_knowledge_envelope',
            contract_type='PhaseOutputEnvelope',
            schema_refs=(
                'isai.protocol:PhaseOutputEnvelope',
            ),
            description='Верифицированный конверт реализации и дистилляции, поступающий при промоушене таска.',
            required=False,
        ),
    ),
    outputs=(
        IOPortSpec(
            name='filtered_knowledge_slice',
            contract_type='dict[str, Any]',
            schema_refs=(
                'builtins:dict',
            ),
            description='Релевантные единицы знаний для включения в пакет RSoC текущей фазы.',
        ),
    ),
    port_wirings=(
        PortWiringSpec(
            consumer_input_port='distilled_knowledge_envelope',
            producer_ref='isai://tasks#WatchdogService',
            producer_output_port='promoted_artifacts_and_distillation',
            rationale='Приём верифицированных результатов закрытого таска для дистилляции паттернов.',
        ),
    ),
    owned_files=(
        'README.md',
    ),
    system_files=(
        'node.py',
        'catalog.py',
    ),
    symbol_bindings=(
        SymbolBindingSpec(
            symbol='EmpiricalCatalog',
            kind=SymbolBindingKind.PYTHON_ATTR,
            target='catalog.py:KNOWLEDGE_CATALOG',
        ),
    ),
    links=(
        EdgeLinkSpec(
            target_ref='isai://root#GenesisKernel',
            kind=EdgeKind.GOVERNED_BY,
            rsoc_delivery=RSoCDeliveryPolicy.NONE,
        ),
        EdgeLinkSpec(
            target_ref='isai://root#RSoCCompiler',
            kind=EdgeKind.CALIBRATES,
            rsoc_delivery=RSoCDeliveryPolicy.INTERFACE_STUB,
            rationale='Интеграция знаний в графовый пакет RSoC.',
        ),
        EdgeLinkSpec(
            target_ref='isai://root#ChronicleLedger',
            kind=EdgeKind.CONSUMES_CONTRACT,
            rsoc_delivery=RSoCDeliveryPolicy.INTERFACE_STUB,
            rationale='Проверка origin_tx_id каждой записи каталога по хронике.',
        ),
        EdgeLinkSpec(
            target_ref='isai://root#NeuroVascularFundamental',
            kind=EdgeKind.GOVERNED_BY,
            rsoc_delivery=RSoCDeliveryPolicy.NONE,
            rationale='Подчинение субгенетическому нервно-сосудистому фундаменталу IL-1C.',
        ),
    ),
    transitions=(
        TransitionRule(
            trigger='supply_patterns_to_rsoc',
            target_ref='isai://root#RSoCCompiler',
            phase_mode=PhaseMode.FAST_READ,
            description='Подача релевантных паттернов и ограничений среды при компиляции контекста фазы.',
        ),
        TransitionRule(
            trigger='consolidate_knowledge_catalog',
            target_ref='isai://tasks',
            phase_mode=PhaseMode.STAGED_TRANSACTION,
            description='Периодическая компакция и слияние накопленных записей через транзакционную фазу.',
        ),
    ),
)
