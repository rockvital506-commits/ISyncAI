"""System Folder Object Manifest for `isai://research/results`."""

from __future__ import annotations

from isai.constitution import IntegrityLevel
from isai.contracts import (
    EdgeKind,
    EdgeLinkSpec,
    ISAINodeSpec,
    RSoCDeliveryPolicy,
    SymbolBindingKind,
    SymbolBindingSpec,
    SymbolVisibility,
    VisibilityScope,
)

NODE = ISAINodeSpec(
    node_id='isai://research/results',
    title='Результаты измерений (Measurement Results)',
    integrity_level=IntegrityLevel.IL_2_CANONICAL,
    visibility=VisibilityScope.PUBLIC,
    parent_ref='isai://research',
    goal='Хранить машинно-читаемые артефакты экспериментов: JSON-срезы метрик, достаточные для перепроверки выводов без повторного прогона.',
    success_criteria=(
        'Каждый JSON-срез содержит достаточно метрик для независимой проверки вывода.',
    ),
    capabilities=(
        'Машинно-читаемая фиксация результатов всех экспериментов стенда.',
    ),
    owned_files=(
        'README.md',
        'e1_link_hit.json',
        'e2_cost.json',
        'e3_context.json',
        'e5_scale.json',
        'e6_mini.json',
        'e7_plasmid.json',
        'e0_summary.json',
        'e8_metrics.json',
        'e9_granularity.json',
        'e10_threshold.json',
        'e11_apoptosis.json',
        'e12_epoch.json',
        'e13_phase1_acceptance.json',
    ),
    system_files=(
        'node.py',
    ),
    symbol_bindings=(
        SymbolBindingSpec(
            symbol='MetricsArtifact',
            kind=SymbolBindingKind.OWNED_ARTIFACT,
            target='e1_link_hit.json',
        ),
    ),
    links=(
        EdgeLinkSpec(
            target_ref='isai://root#GenesisKernel',
            kind=EdgeKind.GOVERNED_BY,
            rsoc_delivery=RSoCDeliveryPolicy.NONE,
        ),
    ),
)
