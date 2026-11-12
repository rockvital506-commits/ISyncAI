"""Operational Symbiosis Runtime Models (v0.2.0): ISAI-PEP v1, Audit, Watchdog, Mutation Plans & Chronicle."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from isai.contracts import EntityRef, PhaseMode

MAX_PHASE_ITERATIONS: int = 3
MAX_MACRO_REPLANS: int = 2
DEFAULT_LEASE_TTL_SECONDS: int = 1800


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_utc_iso(ts: str) -> datetime:
    if ts.endswith("Z"):
        return datetime.fromisoformat(ts[:-1] + "+00:00")
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class AuditIssue(BaseModel):
    """Single structural, cryptographic, referential, contract, or crash-state violation."""

    model_config = ConfigDict(frozen=True)

    code: str
    location: str
    message: str


class AuditReport(BaseModel):
    """Comprehensive deterministic Gate A 360° verification report."""

    model_config = ConfigDict(frozen=True)

    valid: bool
    checked_nodes: tuple[str, ...] = ()
    verified_symbols_count: int = 0
    verified_port_wirings_count: int = 0
    resolved_refs_count: int = 0
    checked_markdown_files_count: int = 0
    chronicle_events_count: int = 0
    current_revision: int = 0
    issues: tuple[AuditIssue, ...] = ()


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
    ISAI-PEP v1 Micro-Loop State Machine (Inner Contour).
    Adapts the Artifact Protocol to ISAI's context-compiled, dual-gated architecture.
    """

    phase_ref: EntityRef
    description: str = Field(min_length=1)
    phase_mode: PhaseMode = PhaseMode.STAGED_TRANSACTION
    iteration: int = Field(default=0, ge=0, le=MAX_PHASE_ITERATIONS)
    status: PhaseStatus = PhaseStatus.INIT

    rsoc_digest: str = Field(min_length=1)
    goals: list[str] = Field(default_factory=list)
    acceptance_gates: list[CriterionSpec] = Field(default_factory=list)
    knowledge_gaps: list[str] = Field(default_factory=list)
    research_findings: list[str] = Field(default_factory=list)
    selected_patterns: list[PatternSpec] = Field(default_factory=list)
    execution_plan: list[str] = Field(default_factory=list)
    realization: PhaseOutputEnvelope | None = None
    diagnostics: list[DiagnosticEntry] = Field(default_factory=list)

    def should_run_research(self) -> bool:
        if self.iteration == 0:
            return len(self.knowledge_gaps) > 0
        return any(d.requires_new_research for d in self.diagnostics)

    def build_task_context(self) -> str:
        sections: list[str] = [
            f"PHASE: {self.phase_ref} (mode={self.phase_mode.value}, iter={self.iteration}/{MAX_PHASE_ITERATIONS})",
            f"TASK: {self.description}",
            f"RSOC_DIGEST: {self.rsoc_digest}",
        ]
        if self.diagnostics:
            diag_lines = [
                f"  - [{d.failed_gate_id}] Cause: {d.root_cause} -> Fix: {d.remediation_action}"
                for d in self.diagnostics
            ]
            sections.append("DIAGNOSTICS_DELTA:\n" + "\n".join(diag_lines))
        return "\n".join(sections)

    def record_gate_outcome(
        self,
        passed: bool,
        new_diagnostics: list[DiagnosticEntry] | None = None,
    ) -> PhaseStatus:
        if passed:
            if self.realization is None:
                raise ValueError("Cannot converge phase when realization is None.")
            self.status = PhaseStatus.CONVERGED
            return self.status

        if new_diagnostics:
            self.diagnostics.extend(new_diagnostics)
        self.iteration += 1
        if self.iteration >= MAX_PHASE_ITERATIONS:
            self.status = PhaseStatus.EXHAUSTED
        else:
            self.status = PhaseStatus.RUNNING
        return self.status


class PhaseNodeSpec(BaseModel):
    """Single node inside a Macro Task Phase DAG (Outer Contour)."""

    model_config = ConfigDict(frozen=True)

    phase_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    target_node_ref: EntityRef
    depends_on: tuple[str, ...] = ()
    phase_mode: PhaseMode = PhaseMode.STAGED_TRANSACTION
    read_set: tuple[EntityRef, ...] = ()
    write_set: tuple[EntityRef, ...] = ()


class TaskManifest(BaseModel):
    """Macro Task Execution Strategy supporting localized subgraph replanning."""

    model_config = ConfigDict(frozen=True)

    task_id: str = Field(min_length=1)
    ultimate_goal: str = Field(min_length=1)
    global_criteria: tuple[CriterionSpec, ...] = Field(min_length=1)
    phases: tuple[PhaseNodeSpec, ...] = Field(min_length=1)
    replan_count: int = Field(default=0, ge=0, le=MAX_MACRO_REPLANS)

    @model_validator(mode="after")
    def _validate_dag_acyclic(self) -> TaskManifest:
        ids = [p.phase_id for p in self.phases]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate phase_id in TaskManifest (Redundancy=FATAL).")
        known = set(ids)
        adj = {p.phase_id: p.depends_on for p in self.phases}
        for pid, deps in adj.items():
            for dep in deps:
                if dep not in known:
                    raise ValueError(f"Phase '{pid}' depends on unknown phase '{dep}'.")
                if dep == pid:
                    raise ValueError(f"Phase '{pid}' cannot depend on itself.")

        visiting: set[str] = set()
        visited: set[str] = set()

        def _dfs(node: str) -> None:
            if node in visiting:
                raise ValueError(f"Cycle detected in TaskManifest DAG at '{node}'.")
            if node in visited:
                return
            visiting.add(node)
            for dep in adj[node]:
                _dfs(dep)
            visiting.remove(node)
            visited.add(node)

        for pid in ids:
            _dfs(pid)
        return self


class HandleAccess(StrEnum):
    """NT Object Manager-inspired handle access modes."""

    READ = "READ"
    WRITE_LEASE = "WRITE_LEASE"


class HandleRecord(BaseModel):
    """Active object handle tracked by Watchdog with TTL lease fencing for Crash Recovery."""

    model_config = ConfigDict(frozen=True)

    handle_id: str = Field(min_length=1)
    owner_task_ref: EntityRef
    phase_id: str = Field(min_length=1)
    target_ref: EntityRef
    access: HandleAccess
    base_interface_digest: str = Field(min_length=1)
    acquired_at_utc: str = Field(default_factory=utc_now_iso)
    lease_ttl_seconds: int = Field(default=DEFAULT_LEASE_TTL_SECONDS, ge=1)

    def is_expired(self, now_utc: datetime | None = None) -> bool:
        ref_now = now_utc.astimezone(timezone.utc) if now_utc else datetime.now(timezone.utc)
        acquired_dt = parse_utc_iso(self.acquired_at_utc)
        elapsed = (ref_now - acquired_dt).total_seconds()
        return elapsed > float(self.lease_ttl_seconds)


class ImpactAssessment(BaseModel):
    """Result of Salsa Early-Cutoff & Transitive N-hop BFS Cascade Analysis."""

    model_config = ConfigDict(frozen=True)

    mutated_node_ref: EntityRef
    previous_interface_digest: str
    new_interface_digest: str
    early_cutoff: bool
    impacted_dependents: tuple[EntityRef, ...] = ()
    max_hop_depth: int = 0


class CanMutateReport(BaseModel):
    """Pact 'can-i-deploy' inspired preflight safety report over the VAET reverse index."""

    model_config = ConfigDict(frozen=True)

    target_uri: str
    operation: Literal["decommission", "remove_symbol", "mutate_interface"]
    safe_without_cascade: bool
    blocking_reasons: tuple[str, ...] = ()
    external_inbound_sources: tuple[str, ...] = ()
    transitive_dependents: tuple[str, ...] = ()
    affected_tests: tuple[str, ...] = ()


class MutationPlan(BaseModel):
    """Buildozer 'emit-and-apply' structured plan/result for transactional link mutations."""

    model_config = ConfigDict(frozen=True)

    operation: str
    dry_run: bool
    applied: bool
    touched_files: tuple[str, ...] = ()
    deleted_paths: tuple[str, ...] = ()
    added_edges: tuple[str, ...] = ()
    removed_edges: tuple[str, ...] = ()
    impacted_dependents: tuple[str, ...] = ()
    affected_tests: tuple[str, ...] = ()


class RecoveryReport(BaseModel):
    """Deterministic Crash Recovery outcome returned by 'isai recover'."""

    model_config = ConfigDict(frozen=True)

    recovered: bool
    removed_temp_files: tuple[str, ...] = ()
    removed_orphan_staging_dirs: tuple[str, ...] = ()
    expired_tasks_aborted: tuple[str, ...] = ()
    rebuilt_snapshot_revision: int = Field(ge=0)
    chronicle_tx_id: str | None = None


class ChronicleEvent(BaseModel):
    """Immutable append-only Chrono-Graph ledger record (.isai/chronicle.jsonl)."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "0.2.5"
    tx_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    timestamp_utc: str = Field(min_length=1)
    actor: str = Field(min_length=1)
    phase_ref: EntityRef
    operation: Literal[
        "BOOTSTRAP",
        "PROMOTE",
        "MUTATE_VECTOR",
        "RATIFY_FUNDAMENTAL",
        "ALGEDONIC_ALERT",
        "DISTILL",
        "REPLAN",
        "RECOVER",
    ]
    touched_refs: tuple[EntityRef, ...] = Field(min_length=1)
    interface_changed: bool = False
    ratified_nvf_digest: str | None = None
    operator_approved: bool = False
    summary: str = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_ratification_invariants(self) -> ChronicleEvent:
        if self.operation == "RATIFY_FUNDAMENTAL":
            if not self.ratified_nvf_digest or len(self.ratified_nvf_digest) != 64:
                raise ValueError(
                    "RATIFY_FUNDAMENTAL ChronicleEvent requires a 64-char SHA-256 ratified_nvf_digest."
                )
            if not self.operator_approved:
                raise ValueError(
                    "RATIFY_FUNDAMENTAL ChronicleEvent requires operator_approved=True (Algedonic Step 6)."
                )
        return self


class SystemStateSnapshot(BaseModel):
    """Volatile HKCC-equivalent runtime state snapshot (tasks/.isai/state_snapshot.json)."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "0.2.5"
    revision: int = Field(ge=0)
    timestamp_utc: str = Field(min_length=1)
    genesis_sha256: str = Field(min_length=64, max_length=64)
    nvf_version: str = Field(default="1.0", min_length=1)
    nvf_digest: str = Field(default="", max_length=64)
    master_vector_version: str = Field(min_length=1)
    master_vector_digest: str = Field(min_length=64, max_length=64)
    active_tasks: tuple[EntityRef, ...] = ()
    open_handles: tuple[HandleRecord, ...] = ()
    node_spec_digests: dict[str, str] = Field(default_factory=dict)
    node_interface_digests: dict[str, str] = Field(default_factory=dict)
    audit_status: Literal["VALID", "STAGING", "DIRTY"] = "VALID"

    @model_validator(mode="after")
    def _check_quiescent_handles(self) -> SystemStateSnapshot:
        if not self.active_tasks and self.open_handles:
            raise ValueError(
                "Handle leak detected: open_handles must be empty when active_tasks is empty."
            )
        return self
