"""Runtime Task Arena & Watchdog Hive Node (`isai://tasks` — HKCC + CBS Staging Equivalent)."""

from __future__ import annotations

from isai.constitution import IntegrityLevel
from isai.contracts import IOPortSpec, ISAINodeSpec, PhaseMode, TransitionRule

NODE = ISAINodeSpec(
    node_id="isai://tasks",
    title="Операционный улей тасков, фазового стейджинга и службы Watchdog (Runtime & CBS Arena)",
    integrity_level=IntegrityLevel.IL_3_STAGING,
    parent_ref="isai://root",
    goal=(
        "Изолировать активные разработки, исследования и фазовые процессы в транзакционном "
        "контуре стейджинга, удерживать актуальный снимок состояния репозитория и контролировать "
        "допустимость и каскадное влияние мутаций через детерминированный Watchdog."
    ),
    success_criteria=(
        "В каждый момент времени файл tasks/.isai/state_snapshot.json отражает достоверное состояние системы.",
        "Активные таски удерживают явные дескрипторы (READ / WRITE_LEASE), которые гарантированно сбрасываются в 0 при закрытии таска.",
        "Прошедшие верификацию фазы промоутятся в канонические узлы и /knowledge/, а закрытые временные контуры очищаются без следов мусора.",
    ),
    capabilities=(
        "Управление жизненным циклом пользовательских тасков по двухконтурному протоколу (Task DAG + ISAI-PEP v1).",
        "Детерминированная служба TaskWatchdog (tasks/.isai/watchdog.py): таблица дескрипторов, MVCC-проверка аренд и Salsa Early-Cutoff оценка влияния.",
        "Хранение атомарного среза состояния системы (tasks/.isai/state_snapshot.json) для мгновенного восстановления контекста.",
    ),
    invariants=(
        "Запрет на пересечение WRITE_LEASE между параллельными асинхронными фазами.",
        "При отсутствии активных тасков (active_tasks == ()) список open_handles обязан быть пуст (HandleCount == 0).",
        "Промоушен в канонические кольца IL-1 / IL-2 возможен только при полном прохождении Gate A ('isai audit').",
    ),
    inputs=(
        IOPortSpec(
            name="task_manifest",
            contract_type="TaskManifest",
            description="Пофазовая спецификация пользовательского задания или исследования.",
        ),
    ),
    outputs=(
        IOPortSpec(
            name="promoted_artifacts_and_distillation",
            contract_type="PhaseOutputEnvelope",
            description="Верифицированные изменения для канонических структур, записи для /knowledge/ и событие хроники.",
        ),
        IOPortSpec(
            name="state_snapshot",
            contract_type="SystemStateSnapshot",
            description="Обновлённый снимок состояния репозитория и таблицы дескрипторов.",
        ),
    ),
    owned_files=("README.md",),
    system_files=("node.py", "watchdog.py", "state_snapshot.json"),
    defined_symbols=("WatchdogService", "StateSnapshot"),
    related_refs=(
        "isai://root#GenesisKernel",
        "isai://root#PhaseExecutionProtocol",
        "isai://root#ChronicleLedger",
        "isai://knowledge#EmpiricalCatalog",
        "isai://user#OperatorProfile",
    ),
    transitions=(
        TransitionRule(
            trigger="promote_to_canonical",
            target_ref="isai://root",
            phase_mode=PhaseMode.STAGED_TRANSACTION,
            description="Атомарное внедрение верифицированных результатов фазы в целевую архитектуру.",
        ),
        TransitionRule(
            trigger="distill_task_insights",
            target_ref="isai://knowledge#EmpiricalCatalog",
            phase_mode=PhaseMode.STAGED_TRANSACTION,
            description="Консолидация полученных практических паттернов в базу знаний при закрытии таска.",
        ),
        TransitionRule(
            trigger="commit_chronicle_event",
            target_ref="isai://root#ChronicleLedger",
            phase_mode=PhaseMode.STAGED_TRANSACTION,
            description="Фиксация неизменяемой записи о переходе состояния в .isai/chronicle.jsonl.",
        ),
    ),
)
