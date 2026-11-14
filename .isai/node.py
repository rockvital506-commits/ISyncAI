"""Root System Folder Object (`isai://root`): Universal Model Driver, Governance, Indexer & Link Injector."""

from __future__ import annotations

from isai.constitution import IntegrityLevel
from isai.contracts import (
    EdgeKind,
    EdgeLinkSpec,
    IOPortSpec,
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
    node_id='isai://root',
    title='Корневой узел-драйвер, индекс гиперграфа и транзакционный инжектор связей ISAI',
    integrity_level=IntegrityLevel.IL_1_KERNEL,
    visibility=VisibilityScope.PUBLIC,
    parent_ref=None,
    goal='Обеспечивать универсальную калибровку любой подключаемой модели/агента, двунаправленную индексацию гиперграфа (EAVT/VAET), транзакционную инъекцию/рефакторинг связей-ссылок и сквозную 360°-верификацию контрактов, портов и колец видимости.',
    success_criteria=(
        'Первые 586 байт (14 строк) файла /README.md побайтово неизменны и совпадают с эталонным SHA-256 IL-0.',
        'Субгенетический фундаментал /FUNDAMENTAL.md (IL-1C) синхронизирован с isai://root#NeuroVascularFundamental и ратифицирован в Chronicle.',
        'Вектор развития /VISION.md синхронизирован с объектом isai://root#MasterVector.',
        "Все связи, порты IOPortSpec (schema_refs), SymbolBindingSpec и кольца видимости верифицированы через 'isai audit'.",
        "Команды 'isai nv', 'isai graph', 'isai link', 'isai rsoc' и 'isai recover' работают детерминированно и атомарно.",
    ),
    capabilities=(
        "Графовая компиляция контекста 'isai rsoc' с доставкой 1-hop интерфейсных стабов соседей.",
        "Двунаправленный индекс гиперграфа HypergraphIndex ('isai graph query | can-mutate | affected-tests').",
        "Транзакционный AST-инжектор и рефактор связей LinkMutator ('isai link add | wire-port | refactor | scaffold-node').",
        "360°-аудит топологии, чистоты AST node.py, совместимости портов, видимости и Markdown-ссылок ('isai audit').",
    ),
    invariants=(
        'THIS-FRAME >> ALL-SUBSEQUENT: ни один дочерний узел не вправе ослабить аксиомы Genesis-ядра.',
        'Order=Absolute | Logic=Linear | Redundancy=FATAL.',
        'Любая мутация связей и структур проходит цикл Admission (Shadow Graph) -> Atomic Batch -> Gate A Audit -> Chronicle.',
    ),
    inputs=(
        IOPortSpec(
            name='user_intent_or_task',
            contract_type='TaskManifest | str',
            schema_refs=(
                'isai.protocol:TaskManifest',
                'builtins:str',
            ),
            description='Целевой запрос оператора или URI узла для сборки рабочего набора RSoC.',
        ),
    ),
    outputs=(
        IOPortSpec(
            name='rsoc_packet',
            contract_type='dict[str, Any]',
            schema_refs=(
                'builtins:dict',
            ),
            description='Предвычисленный минимальный пакет контекста RSoC со стабами связанных соседей.',
        ),
        IOPortSpec(
            name='audit_report',
            contract_type='AuditReport',
            schema_refs=(
                'isai.protocol:AuditReport',
            ),
            description='Детерминированный вердикт целостности всех колец IL-0..IL-3, портов и ссылок.',
        ),
    ),
    owned_files=(
        'README.md',
        'FUNDAMENTAL.md',
        'VISION.md',
        'AGENTS.md',
        'pyproject.toml',
        '.gitignore',
    ),
    system_files=(
        '__init__.py',
        '__main__.py',
        'atomic_io.py',
        'constitution.py',
        'contracts.py',
        'protocol.py',
        'domain_models.py',
        'neuro_vascular.py',
        'vector.py',
        'graph_index.py',
        'engine.py',
        'link_mutator.py',
        'node.py',
        'chronicle.jsonl',
        'vector_ledger.py',
        'health_checks.py',
        'vector_ledger.jsonl',
    ),
    symbol_bindings=(
        SymbolBindingSpec(
            symbol='GenesisKernel',
            kind=SymbolBindingKind.PYTHON_ATTR,
            target='constitution.py:GENESIS_CONSTITUTION',
        ),
        SymbolBindingSpec(
            symbol='NeuroVascularFundamental',
            kind=SymbolBindingKind.PYTHON_ATTR,
            target='neuro_vascular.py:NEURO_VASCULAR_FUNDAMENTAL',
        ),
        SymbolBindingSpec(
            symbol='AlgedonicProtocol',
            kind=SymbolBindingKind.PYTHON_ATTR,
            target='neuro_vascular.py:AlgedonicDeviationCase',
        ),
        SymbolBindingSpec(
            symbol='MasterVector',
            kind=SymbolBindingKind.PYTHON_ATTR,
            target='vector.py:MASTER_VECTOR',
        ),
        SymbolBindingSpec(
            symbol='ISAINodeSpec',
            kind=SymbolBindingKind.PYTHON_ATTR,
            target='contracts.py:ISAINodeSpec',
        ),
        SymbolBindingSpec(
            symbol='PhaseExecutionProtocol',
            kind=SymbolBindingKind.PYTHON_ATTR,
            target='protocol.py:PhaseExecutionState',
        ),
        SymbolBindingSpec(
            symbol='HypergraphIndex',
            kind=SymbolBindingKind.PYTHON_ATTR,
            target='graph_index.py:HypergraphIndex',
        ),
        SymbolBindingSpec(
            symbol='LinkInjector',
            kind=SymbolBindingKind.PYTHON_ATTR,
            target='link_mutator.py:LinkMutator',
        ),
        SymbolBindingSpec(
            symbol='RSoCCompiler',
            kind=SymbolBindingKind.PYTHON_ATTR,
            target='engine.py:compile_rsoc',
        ),
        SymbolBindingSpec(
            symbol='ChronicleLedger',
            kind=SymbolBindingKind.SYSTEM_ARTIFACT,
            target='chronicle.jsonl',
        ),
        SymbolBindingSpec(
            symbol='AtomicPersistence',
            kind=SymbolBindingKind.PYTHON_ATTR,
            target='atomic_io.py:atomic_transaction_batch',
        ),
        SymbolBindingSpec(
            symbol='VectorMutationLedger',
            kind=SymbolBindingKind.PYTHON_ATTR,
            target='vector_ledger.py:VectorMutationLedger',
        ),
        SymbolBindingSpec(
            symbol='SystemHealthGate',
            kind=SymbolBindingKind.PYTHON_ATTR,
            target='health_checks.py:evaluate_gate_v',
        ),
        SymbolBindingSpec(
            symbol='VectorMutationLedgerRecord',
            kind=SymbolBindingKind.SYSTEM_ARTIFACT,
            target='vector_ledger.jsonl',
        ),
    ),
    links=(
        EdgeLinkSpec(
            target_ref='isai://root#GenesisKernel',
            kind=EdgeKind.GOVERNED_BY,
            rsoc_delivery=RSoCDeliveryPolicy.NONE,
            rationale='Конституционный фундамент IL-0.',
        ),
        EdgeLinkSpec(
            target_ref='isai://root#NeuroVascularFundamental',
            kind=EdgeKind.GOVERNED_BY,
            rsoc_delivery=RSoCDeliveryPolicy.NONE,
            rationale='Условно-мутируемый субгенетический нервно-сосудистый фундаментал IL-1C (ISAI-NVF v1.0).',
        ),
        EdgeLinkSpec(
            target_ref='isai://root#MasterVector',
            kind=EdgeKind.GOVERNED_BY,
            rsoc_delivery=RSoCDeliveryPolicy.NONE,
            rationale='Стратегический вектор эволюции системы.',
        ),
        EdgeLinkSpec(
            target_ref='isai://user#OperatorProfile',
            kind=EdgeKind.CALIBRATES,
            rsoc_delivery=RSoCDeliveryPolicy.INTERFACE_STUB,
            rationale='Калибровка когнитивного профиля оператора.',
        ),
        EdgeLinkSpec(
            target_ref='isai://knowledge#EmpiricalCatalog',
            kind=EdgeKind.CALIBRATES,
            rsoc_delivery=RSoCDeliveryPolicy.INTERFACE_STUB,
            rationale='Поставка дистиллированных паттернов в RSoC.',
        ),
        EdgeLinkSpec(
            target_ref='isai://tasks#WatchdogService',
            kind=EdgeKind.DELEGATES_TO,
            rsoc_delivery=RSoCDeliveryPolicy.INTERFACE_STUB,
            rationale='Делегирование фазовых аренд и каскадного надзора.',
        ),
        EdgeLinkSpec(
            target_ref='isai://tasks#CrashRecoveryService',
            kind=EdgeKind.DELEGATES_TO,
            rsoc_delivery=RSoCDeliveryPolicy.INTERFACE_STUB,
            rationale='Аварийное восстановление после прерванных сессий.',
        ),
        EdgeLinkSpec(
            target_ref='isai://tests#SelfVerificationSuite',
            kind=EdgeKind.VERIFIES,
            rsoc_delivery=RSoCDeliveryPolicy.INTERFACE_STUB,
            rationale='Базовый контур модульных и аварийных проверок ядра.',
        ),
        EdgeLinkSpec(
            target_ref='isai://tests#HypergraphCrossTestSuite',
            kind=EdgeKind.VERIFIES,
            rsoc_delivery=RSoCDeliveryPolicy.INTERFACE_STUB,
            rationale='Трёхуровневый контур контрактных кросс-тестов и генеративного фаззинга связей.',
        ),
        EdgeLinkSpec(
            target_ref='isai://tests#NeuroVascularTestSuite',
            kind=EdgeKind.VERIFIES,
            rsoc_delivery=RSoCDeliveryPolicy.INTERFACE_STUB,
            rationale='Трёхуровневый контур проверки субгенетического фундаментала IL-1C и Алгедонического шлюза.',
        ),
    ),
    transitions=(
        TransitionRule(
            trigger='calibrate_operator_context',
            target_ref='isai://user',
            phase_mode=PhaseMode.FAST_READ,
            description='Чтение когнитивного профиля и компетенций оператора для настройки глубины ответов.',
        ),
        TransitionRule(
            trigger='retrieve_or_distill_knowledge',
            target_ref='isai://knowledge',
            phase_mode=PhaseMode.FAST_READ,
            description='Запрос практических паттернов перед планированием или дистилляция опыта закрытого таска.',
        ),
        TransitionRule(
            trigger='execute_phased_task',
            target_ref='isai://tasks',
            phase_mode=PhaseMode.STAGED_TRANSACTION,
            description='Запуск пользовательского таска/исследования в изолированном контуре стейджинга под надзором Watchdog.',
        ),
        TransitionRule(
            trigger='verify_kernel_integrity',
            target_ref='isai://tests',
            phase_mode=PhaseMode.FAST_READ,
            description='Запуск модульных, контрактных и генеративных кросс-тестов ядра.',
        ),
    ),
)
