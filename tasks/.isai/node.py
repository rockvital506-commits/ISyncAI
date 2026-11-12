"""Runtime Task Arena & Watchdog Hive Node (`isai://tasks` — HKCC + CBS Staging Equivalent)."""

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
    node_id='isai://tasks',
    title='Операционный улей тасков, фазового стейджинга и службы Watchdog (Runtime & CBS Arena)',
    integrity_level=IntegrityLevel.IL_3_STAGING,
    visibility=VisibilityScope.PUBLIC,
    parent_ref='isai://root',
    goal='Изолировать активные разработки, исследования и фазовые процессы в транзакционном контуре стейджинга, удерживать атомарный снимок состояния репозитория, контролировать транзитивное каскадное влияние мутаций (включая схемы портов) и обеспечивать Crash Recovery.',
    success_criteria=(
        'В каждый момент времени файл tasks/.isai/state_snapshot.json отражает достоверное состояние системы.',
        'Активные таски имеют видимость EPHEMERAL_STAGING и удерживают арендные дескрипторы с TTL, сбрасываемые в 0 при закрытии.',
        "При сбое процесса служба CrashRecoveryService ('isai recover') очищает оборванный стейджинг и восстанавливает консистентность.",
    ),
    capabilities=(
        'Управление жизненным циклом пользовательских тасков по двухконтурному протоколу (Task DAG + ISAI-PEP v1).',
        'Детерминированная служба TaskWatchdog (tasks/.isai/watchdog.py): MVCC-аренды с TTL, структурный Salsa Early-Cutoff и Crash Recovery.',
        'Атомарное хранение среза состояния системы (tasks/.isai/state_snapshot.json) через fsync + os.replace.',
    ),
    invariants=(
        'Запрет на пересечение WRITE_LEASE между параллельными асинхронными фазами и запрет WRITE_LEASE на IL-0.',
        'При отсутствии активных тасков (active_tasks == ()) список open_handles обязан быть пуст (HandleCount == 0).',
        "Промоушен в канонические кольца IL-1 / IL-2 возможен только при полном прохождении Gate A ('isai audit' + 'pytest').",
    ),
    inputs=(
        IOPortSpec(
            name='task_manifest',
            contract_type='TaskManifest | str',
            schema_refs=(
                'isai.protocol:TaskManifest',
                'builtins:str',
            ),
            description='Пофазовая спецификация пользовательского задания или исследования.',
        ),
        IOPortSpec(
            name='gate_a_audit_verdict',
            contract_type='AuditReport',
            schema_refs=(
                'isai.protocol:AuditReport',
            ),
            description='Вердикт 360°-аудитора ядра перед промоушеном стейджинга.',
            required=False,
        ),
        IOPortSpec(
            name='pytest_gate_verdict',
            contract_type='bool',
            schema_refs=(
                'builtins:bool',
            ),
            description='Сигнал прохождения матрицы автотестов улья /tests/.',
            required=False,
        ),
    ),
    outputs=(
        IOPortSpec(
            name='promoted_artifacts_and_distillation',
            contract_type='PhaseOutputEnvelope',
            schema_refs=(
                'isai.protocol:PhaseOutputEnvelope',
            ),
            description='Верифицированные изменения для канонических структур, записи для /knowledge/ и событие хроники.',
        ),
        IOPortSpec(
            name='state_snapshot',
            contract_type='SystemStateSnapshot',
            schema_refs=(
                'isai.protocol:SystemStateSnapshot',
            ),
            description='Обновлённый снимок состояния репозитория и таблицы дескрипторов.',
        ),
    ),
    port_wirings=(
        PortWiringSpec(
            consumer_input_port='gate_a_audit_verdict',
            producer_ref='isai://root',
            producer_output_port='audit_report',
            rationale='Получение детерминированного отчёта 360°-аудита перед промоушеном.',
        ),
        PortWiringSpec(
            consumer_input_port='pytest_gate_verdict',
            producer_ref='isai://tests#SelfVerificationSuite',
            producer_output_port='pytest_gate_verdict',
            rationale='Получение сигнала прохождения кросс-тестов из улья /tests/.',
        ),
    ),
    owned_files=(
        'README.md',
    ),
    system_files=(
        'node.py',
        'watchdog.py',
        'state_snapshot.json',
    ),
    symbol_bindings=(
        SymbolBindingSpec(
            symbol='WatchdogService',
            kind=SymbolBindingKind.PYTHON_ATTR,
            target='watchdog.py:TaskWatchdog',
        ),
        SymbolBindingSpec(
            symbol='CrashRecoveryService',
            kind=SymbolBindingKind.PYTHON_ATTR,
            target='watchdog.py:recover_repository',
        ),
        SymbolBindingSpec(
            symbol='StateSnapshot',
            kind=SymbolBindingKind.SYSTEM_ARTIFACT,
            target='state_snapshot.json',
        ),
    ),
    links=(
        EdgeLinkSpec(
            target_ref='isai://root#GenesisKernel',
            kind=EdgeKind.GOVERNED_BY,
            rsoc_delivery=RSoCDeliveryPolicy.NONE,
        ),
        EdgeLinkSpec(
            target_ref='isai://root#PhaseExecutionProtocol',
            kind=EdgeKind.CONSUMES_CONTRACT,
            rsoc_delivery=RSoCDeliveryPolicy.INTERFACE_STUB,
            rationale='Исполнение микро-цикла фазы ISAI-PEP v1.',
        ),
        EdgeLinkSpec(
            target_ref='isai://root#LinkInjector',
            kind=EdgeKind.CONSUMES_CONTRACT,
            rsoc_delivery=RSoCDeliveryPolicy.INTERFACE_STUB,
            rationale='Безопасная коммутация и рефакторинг связей внутри фаз.',
        ),
        EdgeLinkSpec(
            target_ref='isai://root#AtomicPersistence',
            kind=EdgeKind.CONSUMES_CONTRACT,
            rsoc_delivery=RSoCDeliveryPolicy.NONE,
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
            trigger='promote_to_canonical',
            target_ref='isai://root',
            phase_mode=PhaseMode.STAGED_TRANSACTION,
            description='Атомарное внедрение верифицированных результатов фазы в целевую архитектуру.',
        ),
        TransitionRule(
            trigger='distill_task_insights',
            target_ref='isai://knowledge#EmpiricalCatalog',
            phase_mode=PhaseMode.STAGED_TRANSACTION,
            description='Консолидация полученных практических паттернов в базу знаний при закрытии таска.',
        ),
        TransitionRule(
            trigger='commit_chronicle_event',
            target_ref='isai://root#ChronicleLedger',
            phase_mode=PhaseMode.STAGED_TRANSACTION,
            description='Фиксация неизменяемой записи о переходе состояния или восстановлении в .isai/chronicle.jsonl.',
        ),
    ),
)
