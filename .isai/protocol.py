"""Operational Symbiosis Runtime Models: ISAI-PEP v1, Task DAG, Watchdog Handles, Snapshot & Chronicle."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from isai.contracts import EntityRef, PhaseMode

MAX_PHASE_ITERATIONS: int = 3
MAX_MACRO_REPLANS: int = 2


class GateKind(StrEnum):
    """Dual-Gate Verification layers preventing correlated LLM self-evaluation bias."""

    DETERMINISTIC = "deterministic"  # Executed via code/CLI/Pydantic/tests (Gate A)
    SEMANTIC = "semantic"            # Verified against anti-hedging semantic rubric (Gate B)


class CriterionSpec(BaseModel):
    """Measurable acceptance gate for a phase or task."""

    model_config = ConfigDict(frozen=True)

    gate_id: str = Field(min_length=1)
    kind: GateKind
    criterion: str = Field(min_length=1)
    verification_cmd: str | None = None


class PatternSpec(BaseModel):
    """Validated engineering pattern selected or synthesized for phase execution."""

    model_config = ConfigDict(frozen=True)

    pattern_id: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    source_ref: EntityRef | None = None


class DiagnosticEntry(BaseModel):
    """Structured failure reflection preventing verbosity & moralizing drift across retries."""

    model_config = ConfigDict(frozen=True)

    failed_gate_id: str = Field(min_length=1)
    evidence: str = Field(min_length=1)
    root_cause: str = Field(min_length=1)
    remediation_action: str = Field(min_length=1)
    requires_new_research: bool = False


class PhaseOutputEnvelope(BaseModel):
    """Typed realization envelope returned by a completed phase."""

    model_config = ConfigDict(frozen=True)

    summary: str = Field(min_length=1)
    staged_artifacts: tuple[str, ...] = ()
    touched_refs: tuple[EntityRef, ...] = ()
    distilled_knowledge_ids: tuple[str, ...] = ()


class PhaseStatus(StrEnum):
    INIT = "INIT"
    RUNNING = "RUNNING"
    CONVERGED = "CONVERGED"
    EXHAUSTED = "EXHAUSTED"


class PhaseExecutionState(BaseModel):
    """
    ISAI-PEP v1: Adapted & Optimized Phase Execution Protocol State.
    Enforces max 3 iterations, conditional delta-research, and Dual-Gate verification.
    """

    schema_version: str = "0.1.0"
    phase_ref: EntityRef
    description: str = Field(min_length=1)
    rsoc_digest: str = Field(min_length=1)
    iteration: int = Field(default=0, ge=0, le=MAX_PHASE_ITERATIONS)
    status: PhaseStatus = PhaseStatus.INIT

    goals: list[str] = Field(default_factory=list)
    knowledge_gaps: list[str] = Field(default_factory=list)
    patterns: list[PatternSpec] = Field(default_factory=list)
    success_criteria: list[CriterionSpec] = Field(default_factory=list)
    plan_and_strategies: str = ""
    diagnostics: list[DiagnosticEntry] = Field(default_factory=list)
    realization: PhaseOutputEnvelope | None = None

    def build_task_context(self) -> str:
        """Step 1 of ISAI-PEP v1: Assemble compact delta-aware context without raw failed drafts."""
        causes = "\n- ".join(
            f"[{d.failed_gate_id}] {d.root_cause} (evidence: {d.evidence})"
            for d in self.diagnostics
        )
        recs = "\n- ".join(
            f"[{d.failed_gate_id}] {d.remediation_action} (research={d.requires_new_research})"
            for d in self.diagnostics
        )
        cause_block = f"- {causes}" if causes else "-"
        rec_block = f"- {recs}" if recs else "-"
        return (
            f"# description:\n- {self.description}\n"
            f"# problem_causes:\n{cause_block}\n"
            f"# recommendations:\n{rec_block}"
        )

    def should_run_research(self) -> bool:
        """Step 3 Conditional Research guard: skip redundant searches when gaps are empty."""
        if not self.knowledge_gaps:
            return False
        if self.iteration == 0:
            return True
        return any(d.requires_new_research for d in self.diagnostics)

    def record_gate_outcome(
        self,
        *,
        passed: bool,
        new_diagnostics: list[DiagnosticEntry] | None = None,
    ) -> PhaseStatus:
        """Step 8 Deterministic Branching: converge on pass or advance retry counter up to MAX_PHASE_ITERATIONS."""
        if passed:
            if self.realization is None:
                raise ValueError("Cannot mark phase CONVERGED when realization is None.")
            self.status = PhaseStatus.CONVERGED
            return self.status

        if not new_diagnostics:
            raise ValueError("Failed verification must provide at least one DiagnosticEntry.")
        self.diagnostics = list(new_diagnostics)
        self.iteration += 1
        if self.iteration >= MAX_PHASE_ITERATIONS:
            self.status = PhaseStatus.EXHAUSTED
        else:
            self.status = PhaseStatus.RUNNING
        return self.status


class PhaseNodeSpec(BaseModel):
    """Single node in a user task's Macro-Orchestrator Phase DAG."""

    model_config = ConfigDict(frozen=True)

    phase_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    target_node_ref: EntityRef
    mode: PhaseMode = PhaseMode.STAGED_TRANSACTION
    depends_on: tuple[str, ...] = ()
    read_set: tuple[EntityRef, ...] = ()
    write_set: tuple[EntityRef, ...] = ()


class TaskManifest(BaseModel):
    """Macro-Orchestrator specification of a phased user task."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "0.1.0"
    task_ref: EntityRef
    title: str = Field(min_length=1)
    bootstrap_mode: bool = False
    ultimate_goal: str = Field(min_length=1)
    global_criteria: tuple[CriterionSpec, ...] = Field(min_length=1)
    phases: tuple[PhaseNodeSpec, ...] = Field(min_length=1)
    replan_count: int = Field(default=0, ge=0, le=MAX_MACRO_REPLANS)
    status: Literal["ACTIVE", "PROMOTED", "ESCALATED", "ABORTED"] = "ACTIVE"


class HandleAccess(StrEnum):
    """Windows Object Manager inspired handle modes tracked by Watchdog."""

    READ = "READ"
    WRITE_LEASE = "WRITE_LEASE"


class HandleRecord(BaseModel):
    """Active reference handle held by a running task/phase in Watchdog."""

    model_config = ConfigDict(frozen=True)

    handle_id: str = Field(min_length=1)
    owner_task_ref: EntityRef
    phase_id: str = Field(min_length=1)
    target_ref: EntityRef
    access: HandleAccess
    base_interface_digest: str = Field(min_length=1)


class ImpactAssessment(BaseModel):
    """Watchdog Salsa Early-Cutoff evaluation result after a node mutation."""

    model_config = ConfigDict(frozen=True)

    mutated_node_ref: EntityRef
    previous_interface_digest: str
    new_interface_digest: str
    early_cutoff: bool
    impacted_dependents: tuple[EntityRef, ...] = ()


class SystemStateSnapshot(BaseModel):
    """Atomic point-in-time state snapshot stored at tasks/.isai/state_snapshot.json."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "0.1.0"
    revision: int = Field(ge=0)
    timestamp_utc: str = Field(min_length=1)
    genesis_sha256: str = Field(min_length=64, max_length=64)
    master_vector_version: str = Field(min_length=1)
    master_vector_digest: str = Field(min_length=64, max_length=64)
    active_tasks: tuple[EntityRef, ...] = ()
    open_handles: tuple[HandleRecord, ...] = ()
    node_spec_digests: dict[str, str] = Field(default_factory=dict)
    node_interface_digests: dict[str, str] = Field(default_factory=dict)
    audit_status: Literal["VALID", "STAGING", "DIRTY"] = "VALID"

    @model_validator(mode="after")
    def _validate_handle_consistency(self) -> SystemStateSnapshot:
        active_set = set(self.active_tasks)
        for h in self.open_handles:
            if h.owner_task_ref not in active_set:
                raise ValueError(
                    f"Leaked HandleRecord '{h.handle_id}': owner '{h.owner_task_ref}' "
                    "is not in active_tasks (HandleCount must drop to 0 on task close)."
                )
        # Verify no two active tasks hold conflicting WRITE_LEASE on the same target_ref
        write_owners: dict[str, str] = {}
        for h in self.open_handles:
            if h.access == HandleAccess.WRITE_LEASE:
                prev = write_owners.get(h.target_ref)
                if prev is not None and prev != f"{h.owner_task_ref}:{h.phase_id}":
                    raise ValueError(
                        f"MVCC Write-Write lease conflict on '{h.target_ref}' "
                        f"between '{prev}' and '{h.owner_task_ref}:{h.phase_id}'."
                    )
                write_owners[h.target_ref] = f"{h.owner_task_ref}:{h.phase_id}"
        return self


class ChronicleEvent(BaseModel):
    """Immutable append-only ledger entry in .isai/chronicle.jsonl."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "0.1.0"
    tx_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    timestamp_utc: str = Field(min_length=1)
    actor: str = Field(min_length=1)
    phase_ref: EntityRef
    operation: Literal["BOOTSTRAP", "CREATE", "UPDATE", "PROMOTE", "DISTILL", "CLOSE_TASK"]
    touched_refs: tuple[EntityRef, ...] = Field(min_length=1)
    interface_changed: bool = False
    summary: str = Field(min_length=1)
