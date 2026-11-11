"""Root System Folder Object (`isai://root`): Universal Model Driver, Governance & Seed Hub."""

from __future__ import annotations

from isai.constitution import IntegrityLevel
from isai.contracts import IOPortSpec, ISAINodeSpec, PhaseMode, TransitionRule

NODE = ISAINodeSpec(
    node_id="isai://root",
    title="Корневой узел-драйвер и конституционное ядро ISyncAI (ISAI)",
    integrity_level=IntegrityLevel.IL_1_KERNEL,
    parent_ref=None,
    goal=(
        "Обеспечивать универсальную калибровку любой подключаемой модели/агента, "
        "конституционный контроль целостности репозитория и маршрутизацию по четырём "
        "системным ульям (.isai/, user/, knowledge/, tasks/) и контуру верификации (tests/)."
    ),
    success_criteria=(
        "Первые 586 байт (14 строк) файла /README.md побайтово неизменны и совпадают с эталонным SHA-256 IL-0.",
        "Вектор развития /VISION.md синхронизирован с объектом isai://root#MasterVector.",
        "100% директорий и файлов репозитория включены в граф владения без единого узла-сироты (zero-orphan-nodes).",
        "Команда 'python -m isai audit' завершается со статусом valid=True и 0 ошибок.",
    ),
    capabilities=(
        "Калибровка подключаемого агента через тонкий бутлоадер AGENTS.md и компилятор контекста 'isai rsoc'.",
        "Детерминированная верификация топологии, ссылок EntityRef, хешей синхронизации и хроники ('isai audit').",
        "Автоматическая проекция контрактов .isai/node.py в парные секции README.md и VISION.md ('isai sync').",
        "Хранение базовых схем, протокола фаз ISAI-PEP v1 и неизменяемого журнала транзакций .isai/chronicle.jsonl.",
    ),
    invariants=(
        "THIS-FRAME >> ALL-SUBSEQUENT: ни один дочерний узел не вправе ослабить аксиомы Genesis-ядра.",
        "Order=Absolute | Logic=Linear | Redundancy=FATAL.",
        "Любая мутация канонических структур проходит цикл AUDIT -> CONSTRUCT -> CHRONICLE.",
    ),
    inputs=(
        IOPortSpec(
            name="user_intent_or_task",
            contract_type="TaskManifest | EntityRef",
            description="Целевой запрос оператора или идентификатор узла для сборки рабочего набора RSoC.",
        ),
    ),
    outputs=(
        IOPortSpec(
            name="rsoc_packet",
            contract_type="dict[str, Any]",
            description="Предвычисленный минимальный пакет контекста (Resultant Set of Context) для окна модели.",
        ),
        IOPortSpec(
            name="audit_report",
            contract_type="AuditReport",
            description="Детерминированный вердикт целостности всех колец IL-0..IL-3.",
        ),
    ),
    owned_files=(
        "README.md",
        "VISION.md",
        "AGENTS.md",
        "pyproject.toml",
        ".gitignore",
    ),
    system_files=(
        "__init__.py",
        "__main__.py",
        "constitution.py",
        "contracts.py",
        "protocol.py",
        "domain_models.py",
        "vector.py",
        "engine.py",
        "node.py",
        "chronicle.jsonl",
    ),
    defined_symbols=(
        "GenesisKernel",
        "MasterVector",
        "ISAINodeSpec",
        "PhaseExecutionProtocol",
        "RSoCCompiler",
        "ChronicleLedger",
    ),
    related_refs=(
        "isai://root#GenesisKernel",
        "isai://root#MasterVector",
        "isai://user#OperatorProfile",
        "isai://knowledge#EmpiricalCatalog",
        "isai://tasks#WatchdogService",
        "isai://tests#SelfVerificationSuite",
    ),
    transitions=(
        TransitionRule(
            trigger="calibrate_operator_context",
            target_ref="isai://user",
            phase_mode=PhaseMode.FAST_READ,
            description="Чтение когнитивного профиля и компетенций оператора для настройки глубины ответов.",
        ),
        TransitionRule(
            trigger="retrieve_or_distill_knowledge",
            target_ref="isai://knowledge",
            phase_mode=PhaseMode.FAST_READ,
            description="Запрос практических паттернов перед планированием или дистилляция опыта закрытого таска.",
        ),
        TransitionRule(
            trigger="execute_phased_task",
            target_ref="isai://tasks",
            phase_mode=PhaseMode.STAGED_TRANSACTION,
            description="Запуск пользовательского таска/исследования в изолированном контуре стейджинга под надзором Watchdog.",
        ),
        TransitionRule(
            trigger="verify_kernel_integrity",
            target_ref="isai://tests",
            phase_mode=PhaseMode.FAST_READ,
            description="Запуск модульных автотестов самоверификации ядра и детекторов нарушений.",
        ),
    ),
)
