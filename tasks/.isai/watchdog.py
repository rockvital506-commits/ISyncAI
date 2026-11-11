"""Event-Driven Watchdog Service (`isai://tasks#WatchdogService`): Handle Table, MVCC Leases & Cascade Gate."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from isai.constitution import GENESIS_SHA256
from isai.engine import discover_nodes, evaluate_interface_cascade
from isai.protocol import (
    HandleAccess,
    HandleRecord,
    ImpactAssessment,
    PhaseNodeSpec,
    SystemStateSnapshot,
)
from isai.vector import MASTER_VECTOR


class TaskWatchdog:
    """
    Trigger-start deterministic supervisor inspired by Windows NT Object Manager & CBS:
      - Tracks active phase handles (READ / WRITE_LEASE) with MVCC conflict rejection.
      - Evaluates post-mutation cascade scope via Salsa Early-Cutoff (interface_digest).
      - Automatically garbage-collects handles (HandleCount -> 0) when a task closes.
    """

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.snapshot_path = self.repo_root / "tasks" / ".isai" / "state_snapshot.json"

    def load_snapshot(self) -> SystemStateSnapshot:
        return SystemStateSnapshot.model_validate_json(
            self.snapshot_path.read_text(encoding="utf-8")
        )

    def save_snapshot(self, snapshot: SystemStateSnapshot) -> None:
        self.snapshot_path.write_text(
            snapshot.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )

    def register_phase_handles(
        self,
        current: SystemStateSnapshot,
        task_ref: str,
        phase: PhaseNodeSpec,
    ) -> SystemStateSnapshot:
        """Open READ and WRITE_LEASE handles for an activated phase, rejecting Read-Write / Write-Write races."""
        nodes = discover_nodes(self.repo_root)
        other_handles = [
            h
            for h in current.open_handles
            if not (h.owner_task_ref == task_ref and h.phase_id == phase.phase_id)
        ]

        # Enforce disjoint WriteSet against all concurrent handles (Read-Write and Write-Write safety)
        for w_target in phase.write_set:
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
                )
            )

        active_tasks = tuple(dict.fromkeys([*current.active_tasks, task_ref]))
        return SystemStateSnapshot(
            revision=current.revision,
            timestamp_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            genesis_sha256=GENESIS_SHA256,
            master_vector_version=MASTER_VECTOR.version,
            master_vector_digest=MASTER_VECTOR.spec_digest(),
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
        """Run Salsa Early-Cutoff check to determine if downstream dependents require re-validation."""
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
        remaining_tasks = tuple(t for t in current.active_tasks if t != closed_task_ref)
        remaining_handles = tuple(
            h for h in current.open_handles if h.owner_task_ref != closed_task_ref
        )
        status = "STAGING" if remaining_tasks else "VALID"
        return SystemStateSnapshot(
            revision=new_revision,
            timestamp_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            genesis_sha256=GENESIS_SHA256,
            master_vector_version=MASTER_VECTOR.version,
            master_vector_digest=MASTER_VECTOR.spec_digest(),
            active_tasks=remaining_tasks,
            open_handles=remaining_handles,
            node_spec_digests={nid: n.spec_digest() for nid, (_, n) in sorted(nodes.items())},
            node_interface_digests={nid: n.interface_digest() for nid, (_, n) in sorted(nodes.items())},
            audit_status=status,
        )
