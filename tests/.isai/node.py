"""Self-Verification, Contract Compatibility & Stateful Graph Fuzzing Node (`isai://tests`)."""

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
    node_id='isai://tests',
    title='Контур самоверификации, контрактных кросс-тестов и генеративного фаззинга связей (Gate A Suite)',
    integrity_level=IntegrityLevel.IL_2_CANONICAL,
    visibility=VisibilityScope.PUBLIC,
    parent_ref='isai://root',
    goal='Гарантировать трёхуровневую детерминированную проверяемость всех инвариантов ISAI (контрактная совместимость портов и колец видимости, транзакционная инъекция/рефакторинг связей и генеративный Stateful фаззинг последовательностей мутаций гиперграфа) через pytest и Hypothesis.',
    success_criteria=(
        '100% модульных, кросс-контрактных и генеративных Hypothesis-тестов проходят с кодом 0.',
        'Любое нарушение совместимости портов, видимости колец, чистоты AST node.py или прозы перехватывается профильным AuditIssue.',
    ),
    capabilities=(
        "Проверка живого состояния репозитория и матрицы PortWiringSpec ('audit_repository').",
        'Кросс-тестирование транзакционного инжектора LinkMutator (add, wire-port, refactor, scaffold, decommission + rollback).',
        'Генеративный автомат Hypothesis RuleBasedStateMachine для проверки произвольных цепочек мутаций графа.',
    ),
    invariants=(
        'Тесты никогда не мутируют живой корень репозитория — негативные и генеративные сценарии работают только в tmp_path без кэша .hypothesis на диске.',
    ),
    inputs=(
        IOPortSpec(
            name='live_state_snapshot',
            contract_type='SystemStateSnapshot',
            schema_refs=(
                'isai.protocol:SystemStateSnapshot',
            ),
            description='Актуальный снимок состояния и дескрипторов Watchdog.',
        ),
        IOPortSpec(
            name='rsoc_context_packet',
            contract_type='dict[str, Any]',
            schema_refs=(
                'builtins:dict',
            ),
            description='Скомпилированный графовый пакет контекста RSoC со стабами соседей.',
        ),
    ),
    outputs=(
        IOPortSpec(
            name='pytest_gate_verdict',
            contract_type='bool',
            schema_refs=(
                'builtins:bool',
            ),
            description='Детерминированный сигнал прохождения Gate A (exit_code == 0).',
        ),
    ),
    port_wirings=(
        PortWiringSpec(
            consumer_input_port='live_state_snapshot',
            producer_ref='isai://tasks#StateSnapshot',
            producer_output_port='state_snapshot',
            rationale='Кросс-проверка синхронности снимка Watchdog с живой топологией.',
        ),
        PortWiringSpec(
            consumer_input_port='rsoc_context_packet',
            producer_ref='isai://root#RSoCCompiler',
            producer_output_port='rsoc_packet',
            rationale='Кросс-тестирование графовой доставки linked_interface_stubs.',
        ),
    ),
    owned_files=(
        'README.md',
        'test_isai_kernel.py',
        'test_hypergraph_cross_links.py',
        'test_neuro_vascular_fundamental.py',
    ),
    system_files=(
        'node.py',
    ),
    symbol_bindings=(
        SymbolBindingSpec(
            symbol='SelfVerificationSuite',
            kind=SymbolBindingKind.OWNED_ARTIFACT,
            target='test_isai_kernel.py',
        ),
        SymbolBindingSpec(
            symbol='HypergraphCrossTestSuite',
            kind=SymbolBindingKind.OWNED_ARTIFACT,
            target='test_hypergraph_cross_links.py',
        ),
        SymbolBindingSpec(
            symbol='NeuroVascularTestSuite',
            kind=SymbolBindingKind.OWNED_ARTIFACT,
            target='test_neuro_vascular_fundamental.py',
        ),
    ),
    links=(
        EdgeLinkSpec(
            target_ref='isai://root#GenesisKernel',
            kind=EdgeKind.GOVERNED_BY,
            rsoc_delivery=RSoCDeliveryPolicy.NONE,
        ),
        EdgeLinkSpec(
            target_ref='isai://root#HypergraphIndex',
            kind=EdgeKind.VERIFIES,
            rsoc_delivery=RSoCDeliveryPolicy.INTERFACE_STUB,
            rationale='Верификация двунаправленного индекса EAVT/VAET.',
        ),
        EdgeLinkSpec(
            target_ref='isai://root#LinkInjector',
            kind=EdgeKind.VERIFIES,
            rsoc_delivery=RSoCDeliveryPolicy.INTERFACE_STUB,
            rationale='Верификация транзакционного инжектора и рефактора связей.',
        ),
        EdgeLinkSpec(
            target_ref='isai://tasks#CrashRecoveryService',
            kind=EdgeKind.VERIFIES,
            rsoc_delivery=RSoCDeliveryPolicy.INTERFACE_STUB,
            rationale='Инъекция аварийных сбоев и проверка идемпотентности восстановления.',
        ),
        EdgeLinkSpec(
            target_ref='isai://root#NeuroVascularFundamental',
            kind=EdgeKind.GOVERNED_BY,
            rsoc_delivery=RSoCDeliveryPolicy.NONE,
            rationale='Подчинение субгенетическому нервно-сосудистому фундаменталу IL-1C.',
        ),
        EdgeLinkSpec(
            target_ref='isai://root#AlgedonicProtocol',
            kind=EdgeKind.VERIFIES,
            rsoc_delivery=RSoCDeliveryPolicy.INTERFACE_STUB,
            rationale='Генеративный фаззинг 6-шагового Алгедонического автомата и блокировки аренды.',
        ),
    ),
    transitions=(
        TransitionRule(
            trigger='report_gate_a_to_tasks',
            target_ref='isai://tasks#WatchdogService',
            phase_mode=PhaseMode.FAST_READ,
            description='Передача результата автотестов в шлюз промоушена фазы.',
        ),
    ),
)
