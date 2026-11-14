"""System Folder Object Manifest for `isai://research`."""

from __future__ import annotations

from isai.constitution import IntegrityLevel
from isai.contracts import (
    EdgeKind,
    EdgeLinkSpec,
    ISAINodeSpec,
    PhaseMode,
    RSoCDeliveryPolicy,
    SymbolBindingKind,
    SymbolBindingSpec,
    SymbolVisibility,
    TransitionRule,
    VisibilityScope,
)

NODE = ISAINodeSpec(
    node_id='isai://research',
    title='Лаборатория эмбеддинг-исследований (Embedding Research Lab)',
    integrity_level=IntegrityLevel.IL_2_CANONICAL,
    visibility=VisibilityScope.PUBLIC,
    parent_ref='isai://root',
    goal='Эмпирически измерять перспективность векторной (эмбеддинговой) логики связей в ISAI: метрики попадания, скорости, чистоты контекста, экономичности — на собственном корпусе системы, без внешних зависимостей в рантайме.',
    success_criteria=(
        "Контракт узла isai://research синхронизирован и проходит 'isai audit'.",
    ),
    capabilities=(
        "Инкапсуляция логики и артефактов домена 'research'.",
    ),
    owned_files=(
        'README.md',
        'FINDINGS.md',
    ),
    system_files=(
        'node.py',
    ),
    symbol_bindings=(
        SymbolBindingSpec(
            symbol='ResearchDoc',
            kind=SymbolBindingKind.OWNED_ARTIFACT,
            target='README.md',
        ),
    ),
    links=(
        EdgeLinkSpec(
            target_ref='isai://root#GenesisKernel',
            kind=EdgeKind.GOVERNED_BY,
            rsoc_delivery=RSoCDeliveryPolicy.NONE,
        ),
        EdgeLinkSpec(
            target_ref='isai://root#NeuroVascularFundamental',
            kind=EdgeKind.GOVERNED_BY,
            rsoc_delivery=RSoCDeliveryPolicy.NONE,
        ),
    ),
    transitions=(
        TransitionRule(
            trigger='route_lab',
            target_ref='isai://research/lab',
            phase_mode=PhaseMode.STAGED_TRANSACTION,
            description='Маршрутизация в дочерний узел isai://research/lab.',
        ),
        TransitionRule(
            trigger='route_results',
            target_ref='isai://research/results',
            phase_mode=PhaseMode.STAGED_TRANSACTION,
            description='Маршрутизация в дочерний узел isai://research/results.',
        ),
    ),
)
