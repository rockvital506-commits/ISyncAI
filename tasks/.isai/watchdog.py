"""Event-Driven Watchdog & Crash Recovery Service (`isai://tasks#WatchdogService`)."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from isai.atomic_io import TEMP_ARTIFACT_PREFIX, atomic_write_text, repository_write_lock
from isai.constitution import DEFAULT_BOUNDARY_IGNORE, GENESIS_SHA256, IntegrityLevel
from isai.contracts import parse_entity_ref, scope_to_rel_path
from isai.engine import (
    append_chronicle,
    discover_nodes,
    evaluate_interface_cascade,
    find_torn_temp_artifacts,
    salvage_chronicle,
    sync_repository,
    write_chronicle_atomic,
)
from isai.graph_index import load_repo_master_vector, load_repo_nvf
from isai.neuro_vascular import AlgedonicDeviationCase
from isai.protocol import (
    ChronicleEvent,
    DEFAULT_LEASE_TTL_SECONDS,
    HandleAccess,
    HandleRecord,
    ImpactAssessment,
    PhaseNodeSpec,
    RecoveryReport,
    SystemStateSnapshot,
    utc_now_iso,
)


class TaskWatchdog:
    """
    Trigger-start deterministic supervisor inspired by Windows NT Object Manager & CBS:
      - Tracks active phase handles (READ / WRITE_LEASE) with TTL lease fencing & MVCC safety.
      - Evaluates post-mutation cascade scope via N-hop Salsa Early-Cutoff (interface_digest).
      - Releases handles (HandleCount -> 0) on task close and heals dirty crash states ('recover').
    """

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.snapshot_path = self.repo_root / "tasks" / ".isai" / "state_snapshot.json"

    def load_snapshot(self) -> SystemStateSnapshot:
        return SystemStateSnapshot.model_validate_json(
            self.snapshot_path.read_text(encoding="utf-8")
        )

    def save_snapshot(self, snapshot: SystemStateSnapshot) -> None:
        with repository_write_lock(self.repo_root):
            atomic_write_text(self.snapshot_path, snapshot.model_dump_json(indent=2) + "\n")

    def register_phase_handles(
        self,
        current: SystemStateSnapshot,
        task_ref: str,
        phase: PhaseNodeSpec,
        *,
        acquired_at_utc: str | None = None,
        lease_ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS,
        algedonic_case: AlgedonicDeviationCase | None = None,
    ) -> SystemStateSnapshot:
        """
        Open READ and WRITE_LEASE handles for an activated phase, rejecting Read-Write / Write-Write races,
        IL-0 immutability violations, and unratified IL-1C mutations.
        """
        nodes = discover_nodes(self.repo_root)
        repo_vec = load_repo_master_vector(self.repo_root)
        repo_nvf = load_repo_nvf(self.repo_root)
        other_handles = [
            h
            for h in current.open_handles
            if not (h.owner_task_ref == task_ref and h.phase_id == phase.phase_id)
        ]

        for w_target in phase.write_set:
            w_scope, _ = parse_entity_ref(w_target)
            w_nid = f"isai://{w_scope}"
            if w_target == "isai://root#GenesisKernel" or (
                w_nid in nodes and nodes[w_nid][1].integrity_level == IntegrityLevel.IL_0_GENESIS
            ):
                raise ValueError(
                    f"IL-0 Constitutional violation: cannot acquire WRITE_LEASE on immutable Genesis target '{w_target}'."
                )
            if w_target == "isai://root#NeuroVascularFundamental" or (
                w_nid in nodes and nodes[w_nid][1].integrity_level == IntegrityLevel.IL_1C_FUNDAMENTAL
            ):
                if algedonic_case is None or not algedonic_case.is_ratified_for_execution():
                    raise ValueError(
                        f"IL-1C Conditional-Mutability violation: cannot acquire WRITE_LEASE on '{w_target}' "
                        "without a complete 6-Step AlgedonicDeviationCase ratified by the Operator (operator_confirmed=True)."
                    )
            for existing in other_handles:
                if existing.target_ref == w_target and existing.owner_task_ref != task_ref:
                    raise ValueError(
                        f"Concurrency conflict on '{w_target}': held by '{existing.owner_task_ref}' "
                        f"with access '{existing.access.value}'."
                    )
        for r_target in phase.read_set:
            for existing in other_handles:
                if (
                    existing.target_ref == r_target
                    and existing.access == HandleAccess.WRITE_LEASE
                    and existing.owner_task_ref != task_ref
                ):
                    raise ValueError(
                        f"Read-Write hazard on '{r_target}': active WRITE_LEASE held by '{existing.owner_task_ref}'."
                    )

        stamp = acquired_at_utc or utc_now_iso()
        new_handles = list(other_handles)
        for idx, r_ref in enumerate(phase.read_set, start=1):
            base_scope = r_ref.split("#", 1)[0]
            base_iface = nodes[base_scope][1].interface_digest() if base_scope in nodes else "symbol"
            new_handles.append(
                HandleRecord(
                    handle_id=f"{phase.phase_id}:R{idx}",
                    owner_task_ref=task_ref,
                    phase_id=phase.phase_id,
                    target_ref=r_ref,
                    access=HandleAccess.READ,
                    base_interface_digest=base_iface,
                    acquired_at_utc=stamp,
                    lease_ttl_seconds=lease_ttl_seconds,
                )
            )
        for idx, w_ref in enumerate(phase.write_set, start=1):
            base_scope = w_ref.split("#", 1)[0]
            base_iface = nodes[base_scope][1].interface_digest() if base_scope in nodes else "symbol"
            new_handles.append(
                HandleRecord(
                    handle_id=f"{phase.phase_id}:W{idx}",
                    owner_task_ref=task_ref,
                    phase_id=phase.phase_id,
                    target_ref=w_ref,
                    access=HandleAccess.WRITE_LEASE,
                    base_interface_digest=base_iface,
                    acquired_at_utc=stamp,
                    lease_ttl_seconds=lease_ttl_seconds,
                )
            )

        active_tasks = tuple(dict.fromkeys([*current.active_tasks, task_ref]))
        return SystemStateSnapshot(
            revision=current.revision,
            timestamp_utc=utc_now_iso(),
            genesis_sha256=GENESIS_SHA256,
            nvf_version=repo_nvf.version,
            nvf_digest=repo_nvf.dsl_sha256(),
            master_vector_version=repo_vec.version,
            master_vector_digest=repo_vec.spec_digest(),
            active_tasks=active_tasks,
            open_handles=tuple(new_handles),
            node_spec_digests={nid: n.spec_digest() for nid, (_, n) in sorted(nodes.items())},
            node_interface_digests={nid: n.interface_digest() for nid, (_, n) in sorted(nodes.items())},
            audit_status="STAGING",
        )

    def evaluate_mutation_impact(
        self,
        mutated_node_ref: str,
        previous_interface_digest: str,
    ) -> ImpactAssessment:
        """Run Salsa Early-Cutoff + Transitive N-hop BFS check."""
        nodes = discover_nodes(self.repo_root)
        return evaluate_interface_cascade(nodes, mutated_node_ref, previous_interface_digest)

    def close_task_and_release_handles(
        self,
        current: SystemStateSnapshot,
        closed_task_ref: str,
        new_revision: int,
    ) -> SystemStateSnapshot:
        """Release all handles owned by closed_task_ref (HandleCount -> 0) and refresh clean digests."""
        nodes = discover_nodes(self.repo_root)
        repo_vec = load_repo_master_vector(self.repo_root)
        repo_nvf = load_repo_nvf(self.repo_root)
        remaining_tasks = tuple(t for t in current.active_tasks if t != closed_task_ref)
        remaining_handles = tuple(
            h for h in current.open_handles if h.owner_task_ref != closed_task_ref
        )
        status = "STAGING" if remaining_tasks else "VALID"
        return SystemStateSnapshot(
            revision=new_revision,
            timestamp_utc=utc_now_iso(),
            genesis_sha256=GENESIS_SHA256,
            nvf_version=repo_nvf.version,
            nvf_digest=repo_nvf.dsl_sha256(),
            master_vector_version=repo_vec.version,
            master_vector_digest=repo_vec.spec_digest(),
            active_tasks=remaining_tasks,
            open_handles=remaining_handles,
            node_spec_digests={nid: n.spec_digest() for nid, (_, n) in sorted(nodes.items())},
            node_interface_digests={nid: n.interface_digest() for nid, (_, n) in sorted(nodes.items())},
            audit_status=status,
        )

    def recover(
        self,
        *,
        now_utc: datetime | None = None,
        abort_all_active: bool = False,
    ) -> RecoveryReport:
        """
        Deterministic Boot / Crash Recovery procedure:
          1. Sweep leftover .isai_tmp_* crash artifacts.
          2. Salvage valid Chronicle prefix if trailing line was torn.
          3. Detect corrupted/missing state_snapshot.json, expired handle leases, or missing task dirs.
          4. Remove unregistered orphan staging folders inside tasks/.
          5. Re-sync README/VISION digests and, ONLY if dirty state existed, commit RECOVER transaction.
        """
        with repository_write_lock(self.repo_root):
            return self._recover_unlocked(now_utc=now_utc, abort_all_active=abort_all_active)

    def _recover_unlocked(
        self,
        *,
        now_utc: datetime | None = None,
        abort_all_active: bool = False,
    ) -> RecoveryReport:
        removed_temps: list[str] = []
        for torn in find_torn_temp_artifacts(self.repo_root):
            rel_t = torn.relative_to(self.repo_root).as_posix()
            if torn.is_dir():
                shutil.rmtree(torn)
            else:
                torn.unlink(missing_ok=True)
            removed_temps.append(rel_t)

        events, chronicle_corrupted = salvage_chronicle(self.repo_root)
        if chronicle_corrupted:
            write_chronicle_atomic(self.repo_root, events)
        latest_rev = events[-1].revision if events else 0

        snapshot_corrupted = False
        existing_snap: SystemStateSnapshot | None = None
        if not self.snapshot_path.is_file():
            snapshot_corrupted = True
        else:
            try:
                existing_snap = self.load_snapshot()
            except Exception:
                snapshot_corrupted = True

        aborted_tasks: list[str] = []
        surviving_tasks: list[str] = []
        surviving_handles: list[HandleRecord] = []

        if existing_snap is not None:
            expired_owners = {
                h.owner_task_ref
                for h in existing_snap.open_handles
                if abort_all_active or h.is_expired(now_utc)
            }
            if abort_all_active:
                expired_owners.update(existing_snap.active_tasks)

            for t_ref in existing_snap.active_tasks:
                scope, sym = parse_entity_ref(t_ref)
                # If task is scoped to a staging directory tasks/<ID>, verify directory exists
                missing_task_dir = False
                if sym is None and scope.startswith("tasks/"):
                    t_dir = self.repo_root / scope_to_rel_path(scope)
                    if not (t_dir / ".isai" / "node.py").is_file():
                        missing_task_dir = True

                if t_ref in expired_owners or missing_task_dir:
                    aborted_tasks.append(t_ref)
                    if sym is None and scope.startswith("tasks/"):
                        t_dir = self.repo_root / scope_to_rel_path(scope)
                        if t_dir.is_dir():
                            shutil.rmtree(t_dir)
                else:
                    surviving_tasks.append(t_ref)

            surviving_set = set(surviving_tasks)
            surviving_handles = [
                h for h in existing_snap.open_handles if h.owner_task_ref in surviving_set
            ]

        # Sweep unregistered orphan staging folders inside tasks/
        removed_orphan_dirs: list[str] = []
        tasks_dir = self.repo_root / "tasks"
        surviving_scopes = {parse_entity_ref(t)[0] for t in surviving_tasks}
        if tasks_dir.is_dir():
            for child in sorted(tasks_dir.iterdir(), key=lambda p: p.name):
                if not child.is_dir() or child.name == ".isai":
                    continue
                rel_child = child.relative_to(self.repo_root)
                if DEFAULT_BOUNDARY_IGNORE.is_ignored(rel_child):
                    continue
                expected_scope = rel_child.as_posix()
                if expected_scope not in surviving_scopes:
                    shutil.rmtree(child)
                    removed_orphan_dirs.append(expected_scope)

        # Ensure README.md, VISION.md, and FUNDAMENTAL.md sync blocks match live nodes
        sync_res = sync_repository(self.repo_root)
        nodes = discover_nodes(self.repo_root)
        repo_vec = load_repo_master_vector(self.repo_root)
        repo_nvf = load_repo_nvf(self.repo_root)
        live_spec_map = {nid: n.spec_digest() for nid, (_, n) in sorted(nodes.items())}
        live_iface_map = {nid: n.interface_digest() for nid, (_, n) in sorted(nodes.items())}

        snapshot_drifted = False
        if existing_snap is not None and not surviving_tasks:
            if (
                existing_snap.revision != latest_rev
                or existing_snap.audit_status != "VALID"
                or existing_snap.master_vector_digest != repo_vec.spec_digest()
                or existing_snap.nvf_digest != repo_nvf.dsl_sha256()
                or existing_snap.node_spec_digests != live_spec_map
                or existing_snap.node_interface_digests != live_iface_map
            ):
                snapshot_drifted = True

        dirty_detected = bool(
            removed_temps
            or chronicle_corrupted
            or snapshot_corrupted
            or aborted_tasks
            or removed_orphan_dirs
            or sync_res.updated_files
            or snapshot_drifted
        )

        if not dirty_detected:
            return RecoveryReport(
                recovered=False,
                rebuilt_snapshot_revision=latest_rev,
                chronicle_tx_id=None,
            )

        new_rev = latest_rev + 1
        tx_id = f"TX-{new_rev:04d}"
        append_chronicle(
            self.repo_root,
            ChronicleEvent(
                tx_id=tx_id,
                revision=new_rev,
                timestamp_utc=utc_now_iso(),
                actor="ISAI-Watchdog-Recovery",
                phase_ref="isai://tasks#CrashRecoveryService",
                operation="RECOVER",
                touched_refs=("isai://tasks", "isai://root"),
                interface_changed=False,
                summary=(
                    f"Crash recovery healed dirty state (temps={len(removed_temps)}, "
                    f"orphans={len(removed_orphan_dirs)}, aborted_tasks={len(aborted_tasks)})."
                ),
            ),
        )

        healed_snap = SystemStateSnapshot(
            revision=new_rev,
            timestamp_utc=utc_now_iso(),
            genesis_sha256=GENESIS_SHA256,
            nvf_version=repo_nvf.version,
            nvf_digest=repo_nvf.dsl_sha256(),
            master_vector_version=repo_vec.version,
            master_vector_digest=repo_vec.spec_digest(),
            active_tasks=tuple(surviving_tasks),
            open_handles=tuple(surviving_handles),
            node_spec_digests=live_spec_map,
            node_interface_digests=live_iface_map,
            audit_status="STAGING" if surviving_tasks else "VALID",
        )
        self.save_snapshot(healed_snap)

        return RecoveryReport(
            recovered=True,
            removed_temp_files=tuple(removed_temps),
            removed_orphan_staging_dirs=tuple(removed_orphan_dirs),
            expired_tasks_aborted=tuple(aborted_tasks),
            rebuilt_snapshot_revision=new_rev,
            chronicle_tx_id=tx_id,
        )


def recover_repository(
    repo_root: Path,
    *,
    now_utc: datetime | None = None,
    abort_all_active: bool = False,
) -> RecoveryReport:
    """Functional entrypoint bound to isai://tasks#CrashRecoveryService."""
    return TaskWatchdog(repo_root).recover(now_utc=now_utc, abort_all_active=abort_all_active)
