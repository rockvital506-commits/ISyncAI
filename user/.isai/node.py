"""User Cognitive & Competency Hive Node (`isai://user` — HKCU Equivalent)."""

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
    node_id='isai://user',
    title='Улей когнитивного профиля и компетенций оператора (User Twin / HKCU)',
    integrity_level=IntegrityLevel.IL_2_CANONICAL,
    visibility=VisibilityScope.PUBLIC,
    parent_ref='isai://root',
    goal='Хранить и развивать верифицированную модель оператора (когнитивный стиль, инженерные директивы и матрицу компетенций) для точной калибровки любой подключаемой модели без пересказа очевидных базовых концепций.',
    success_criteria=(
        'Профиль содержит только подтверждённые директивы и компетенции без домыслов.',
        "Компилятор 'isai rsoc' выбирает из профиля релевантные задаче теги компетенций.",
        'Любое обновление профиля проходит через фазовый CRUD и фиксируется в хронике.',
    ),
    capabilities=(
        'Хранение типизированного объекта USER_PROFILE (UserProfileSpec) в user/.isai/profile.py.',
        'Фильтрация компетенций по доменным тегам при сборке контекста фазы (RSoC).',
        'Переносимая калибровка глубины, строгости и формата коммуникации модели.',
    ),
    invariants=(
        'Запрет на галлюцинацию неподтверждённых биографических или технических фактов об операторе.',
        'Соответствие архетипу Genesis-ядра: FiduSys-Novator & Chronitect.',
    ),
    inputs=(
        IOPortSpec(
            name='verified_skill_or_preference_delta',
            contract_type='CompetencyRecord | CognitiveDirective',
            schema_refs=(
                'isai.domain_models:CompetencyRecord',
                'isai.domain_models:CognitiveDirective',
            ),
            description='Подтверждённое в ходе совместных тасков обновление навыков или предпочтений оператора.',
            required=False,
        ),
    ),
    outputs=(
        IOPortSpec(
            name='operator_calibration_slice',
            contract_type='dict[str, Any]',
            schema_refs=(
                'builtins:dict',
            ),
            description='Компактный срез директив и релевантных компетенций для включения в RSoC.',
        ),
    ),
    owned_files=(
        'README.md',
    ),
    system_files=(
        'node.py',
        'profile.py',
    ),
    symbol_bindings=(
        SymbolBindingSpec(
            symbol='OperatorProfile',
            kind=SymbolBindingKind.PYTHON_ATTR,
            target='profile.py:USER_PROFILE',
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
            rationale='Подача калибровочного среза в компилятор RSoC.',
        ),
        EdgeLinkSpec(
            target_ref='isai://tasks#WatchdogService',
            kind=EdgeKind.CONSUMES_CONTRACT,
            rsoc_delivery=RSoCDeliveryPolicy.INTERFACE_STUB,
            rationale='Транзакционный контроль мутаций профиля.',
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
            trigger='inject_into_rsoc',
            target_ref='isai://root#RSoCCompiler',
            phase_mode=PhaseMode.FAST_READ,
            description='Передача релевантного среза профиля в компилятор контекста фазы.',
        ),
        TransitionRule(
            trigger='evolve_operator_profile',
            target_ref='isai://tasks',
            phase_mode=PhaseMode.STAGED_TRANSACTION,
            description='Инициация транзакционной фазы обновления компетенций по итогам практической работы.',
        ),
    ),
)
