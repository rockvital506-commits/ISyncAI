"""System Folder Object Manifest for `isai://research/lab`."""

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
    node_id='isai://research/lab',
    title='Измерительный стенд (Embedding Lab Harness)',
    integrity_level=IntegrityLevel.IL_2_CANONICAL,
    visibility=VisibilityScope.PUBLIC,
    parent_ref='isai://research',
    goal='Содержать исполняемые эксперименты E1..E7 по векторной логике связей: загрузчик вселенной, корпусный эмбеддер, метрики попадания, чистоты контекста, экономичности и масштабируемости.',
    success_criteria=(
        'Каждый эксперимент воспроизводим при повторном запуске.',
    ),
    capabilities=(
        'Независимый замер системы снаружи: стенд не импортирует isai в измерительном ядре.',
    ),
    invariants=(
        'Детерминизм индекса: blake2b вместо hash(), без PYTHONHASHSEED.',
    ),
    owned_files=(
        'README.md',
        'universe.py',
        'e1_link_hit.py',
        'e2_cost.py',
        'e3_context.py',
        'e5_scale.py',
        'e6_mini.py',
        'e7_plasmid.py',
        'e0_summary.py',
    ),
    system_files=(
        'node.py',
    ),
    symbol_bindings=(
        SymbolBindingSpec(
            symbol='UniverseLoader',
            kind=SymbolBindingKind.OWNED_ARTIFACT,
            target='universe.py',
        ),
        SymbolBindingSpec(
            symbol='CorpusEmbedder',
            kind=SymbolBindingKind.OWNED_ARTIFACT,
            target='universe.py',
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
