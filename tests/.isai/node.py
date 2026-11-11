"""Self-Verification & Adversarial Test Suite Node (`isai://tests`)."""

from __future__ import annotations

from isai.constitution import IntegrityLevel
from isai.contracts import IOPortSpec, ISAINodeSpec, PhaseMode, TransitionRule

NODE = ISAINodeSpec(
    node_id="isai://tests",
    title="Контур самоверификации и модульных автотестов ядра ISAI (Gate A Test Suite)",
    integrity_level=IntegrityLevel.IL_2_CANONICAL,
    parent_ref="isai://root",
    goal=(
        "Гарантировать детерминированную проверяемость всех инвариантов ISAI (неизменность "
        "Genesis-фрейма, zero-orphan-nodes, синхронизацию README, работу протокола ISAI-PEP v1, "
        "блокировки Watchdog, Salsa Early-Cutoff и компиляцию RSoC) через автоматические тесты."
    ),
    success_criteria=(
        "100% тестов pytest проходят без ошибок на живом репозитории и изолированных мутационных фикстурах.",
        "Проверены как позитивные сценарии, так и перехват каждого класса фатальных нарушений.",
    ),
    capabilities=(
        "Проверка живого состояния репозитория через Gate A ('audit_repository').",
        "Адверсариальное тестирование детекторов взлома IL-0, сирот, битых EntityRef и гонок MVCC.",
        "Проверка конечного автомата фаз PhaseExecutionState и каскадного анализатора Salsa Early-Cutoff.",
    ),
    invariants=(
        "Тесты никогда не мутируют живой корень репозитория — негативные сценарии выполняются только во временных копиях tmp_path.",
    ),
    inputs=(
        IOPortSpec(
            name="live_repo_and_kernel_modules",
            contract_type="Path",
            description="Текущее состояние репозитория и модули пакета isai.",
        ),
    ),
    outputs=(
        IOPortSpec(
            name="pytest_gate_verdict",
            contract_type="bool",
            description="Детерминированный сигнал прохождения Gate A (exit_code == 0).",
        ),
    ),
    owned_files=("README.md", "test_isai_kernel.py"),
    system_files=("node.py",),
    defined_symbols=("SelfVerificationSuite",),
    related_refs=(
        "isai://root#GenesisKernel",
        "isai://root#ISAINodeSpec",
        "isai://root#PhaseExecutionProtocol",
        "isai://tasks#WatchdogService",
    ),
    transitions=(
        TransitionRule(
            trigger="report_gate_a_to_tasks",
            target_ref="isai://tasks#WatchdogService",
            phase_mode=PhaseMode.FAST_READ,
            description="Передача результата автотестов в шлюз промоушена фазы.",
        ),
    ),
)
