"""Comprehensive Gate A Self-Verification & Adversarial Mutation Tests for ISAI v0.1."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from isai.constitution import (
    DEFAULT_BOUNDARY_IGNORE,
    GENESIS_BYTE_LENGTH,
    GENESIS_CONSTITUTION,
    GENESIS_SHA256,
    IntegrityLevel,
)
from isai.contracts import IOPortSpec, ISAINodeSpec
from isai.domain_models import KnowledgeCatalogSpec, KnowledgeEntry
from isai.engine import (
    audit_repository,
    compile_rsoc,
    discover_nodes,
    evaluate_interface_cascade,
    load_module_attr,
    sync_repository,
)
from isai.protocol import (
    DiagnosticEntry,
    PhaseExecutionState,
    PhaseNodeSpec,
    PhaseOutputEnvelope,
    PhaseStatus,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def _clone_repo_to_tmp(tmp_path: Path) -> Path:
    """Copy tracked functional files of REPO_ROOT into an isolated temporary workspace."""
    dest = tmp_path / "repo"

    def _ignore(src: str, names: list[str]) -> set[str]:
        src_path = Path(src)
        ignored: set[str] = set()
        for name in names:
            rel = (src_path / name).relative_to(REPO_ROOT)
            if DEFAULT_BOUNDARY_IGNORE.is_ignored(rel):
                ignored.add(name)
        return ignored

    shutil.copytree(REPO_ROOT, dest, ignore=_ignore)
    return dest


def test_live_repository_passes_full_audit() -> None:
    """Live repository must satisfy 100% of Ring 0..3 topological, digest, and snapshot checks."""
    genesis_check = GENESIS_CONSTITUTION.verify_genesis_header(REPO_ROOT / "README.md")
    assert genesis_check.valid is True
    assert genesis_check.actual_sha256 == GENESIS_SHA256
    assert genesis_check.actual_byte_length == GENESIS_BYTE_LENGTH

    report = audit_repository(REPO_ROOT)
    assert report.valid is True, f"Audit failed with issues: {report.issues}"
    assert report.issues == ()
    assert set(report.checked_nodes) >= {
        "isai://root",
        "isai://user",
        "isai://knowledge",
        "isai://tasks",
        "isai://tests",
    }


def test_detects_genesis_header_tampering(tmp_path: Path) -> None:
    """Modifying even a single byte inside the first 586 bytes of README.md must trigger GENESIS_TAMPERED."""
    sandbox = _clone_repo_to_tmp(tmp_path)
    readme = sandbox / "README.md"
    raw = bytearray(readme.read_bytes())
    # Flip a single ASCII character inside the Genesis block
    raw[2] = ord("i")
    readme.write_bytes(bytes(raw))

    report = audit_repository(sandbox, require_clean_snapshot=False)
    assert report.valid is False
    codes = {i.code for i in report.issues}
    assert "GENESIS_TAMPERED" in codes

    with pytest.raises(RuntimeError, match="Refusing sync"):
        sync_repository(sandbox)


def test_detects_orphan_files_and_orphan_system_files(tmp_path: Path) -> None:
    """Unregistered files in either a folder or its .isai/ folder must fail zero-orphan-nodes."""
    sandbox = _clone_repo_to_tmp(tmp_path)
    (sandbox / "user" / "unregistered_note.md").write_text("orphan", encoding="utf-8")
    (sandbox / "user" / ".isai" / "rogue_helper.py").write_text("X = 1\n", encoding="utf-8")

    report = audit_repository(sandbox, require_clean_snapshot=False)
    assert report.valid is False
    codes = {i.code for i in report.issues}
    assert "ORPHAN_FILE" in codes
    assert "ORPHAN_SYSTEM_FILE" in codes


def test_detects_broken_entity_ref_and_readme_desync(tmp_path: Path) -> None:
    """Dangling EntityRefs and manual README digest drift must be caught deterministically."""
    sandbox = _clone_repo_to_tmp(tmp_path)

    # Corrupt digest marker inside user/README.md
    user_readme = sandbox / "user" / "README.md"
    user_readme.write_text(
        user_readme.read_text(encoding="utf-8").replace("spec_digest=", "spec_digest=0000"),
        encoding="utf-8",
    )

    # Inject a dangling reference into tests/.isai/node.py
    tests_node_py = sandbox / "tests" / ".isai" / "node.py"
    tests_node_py.write_text(
        tests_node_py.read_text(encoding="utf-8").replace(
            '"isai://tasks#WatchdogService"',
            '"isai://ghost/missing#Phantom"',
        ),
        encoding="utf-8",
    )

    report = audit_repository(sandbox, require_clean_snapshot=False)
    assert report.valid is False
    codes = {i.code for i in report.issues}
    assert "README_DIGEST_MISMATCH" in codes
    assert "UNRESOLVED_ENTITY_REF" in codes


def test_isai_pep_v1_lifecycle_and_conditional_research() -> None:
    """ISAI-PEP v1 state machine must enforce max 3 iterations, conditional research, and strict convergence."""
    state = PhaseExecutionState(
        phase_ref="isai://tasks#phase-test",
        description="Verify phase state machine",
        rsoc_digest="a" * 64,
        goals=["Implement verified module"],
        knowledge_gaps=["Check setuptools package-dir behavior"],
    )
    assert state.should_run_research() is True

    # Cannot converge without realization envelope
    with pytest.raises(ValueError, match="realization is None"):
        state.record_gate_outcome(passed=True)

    # Fail iteration 0 without needing new research (code bug only)
    status_1 = state.record_gate_outcome(
        passed=False,
        new_diagnostics=[
            DiagnosticEntry(
                failed_gate_id="GATE-A1",
                evidence="ImportError in node loader",
                root_cause="Missing unique namespace in spec_from_file_location",
                remediation_action="Add deterministic slug per relative path",
                requires_new_research=False,
            )
        ],
    )
    assert status_1 == PhaseStatus.RUNNING
    assert state.iteration == 1
    assert state.should_run_research() is False  # Skips redundant research on retry!
    assert "[GATE-A1]" in state.build_task_context()

    # Fail iterations 1 and 2 -> hits MAX_PHASE_ITERATIONS (3) -> EXHAUSTED
    diag_research = [
        DiagnosticEntry(
            failed_gate_id="GATE-A2",
            evidence="API mismatch",
            root_cause="Unknown schema constraint",
            remediation_action="Inspect Pydantic v2 docs",
            requires_new_research=True,
        )
    ]
    assert state.record_gate_outcome(passed=False, new_diagnostics=diag_research) == PhaseStatus.RUNNING
    assert state.should_run_research() is True
    assert state.record_gate_outcome(passed=False, new_diagnostics=diag_research) == PhaseStatus.EXHAUSTED
    assert state.iteration == 3

    # Fresh run converging cleanly on iteration 0
    clean_state = PhaseExecutionState(
        phase_ref="isai://tasks#phase-ok",
        description="Clean pass",
        rsoc_digest="b" * 64,
        realization=PhaseOutputEnvelope(summary="All checks green"),
    )
    assert clean_state.record_gate_outcome(passed=True) == PhaseStatus.CONVERGED


def test_watchdog_mvcc_handles_early_cutoff_and_release(tmp_path: Path) -> None:
    """TaskWatchdog must enforce disjoint WriteSets, Salsa Early-Cutoff, and HandleCount -> 0 on close."""
    sandbox = _clone_repo_to_tmp(tmp_path)
    watchdog_cls = load_module_attr(
        sandbox / "tasks" / ".isai" / "watchdog.py",
        "_test_watchdog_mod",
        "TaskWatchdog",
    )
    wd = watchdog_cls(sandbox)
    base_snap = wd.load_snapshot()
    # Ensure clean starting point for concurrency test
    if base_snap.active_tasks:
        for active_t in list(base_snap.active_tasks):
            base_snap = wd.close_task_and_release_handles(base_snap, active_t, base_snap.revision)

    phase_a = PhaseNodeSpec(
        phase_id="P1",
        title="Mutate knowledge",
        target_node_ref="isai://knowledge",
        read_set=("isai://root",),
        write_set=("isai://knowledge",),
    )
    snap_after_a = wd.register_phase_handles(base_snap, "isai://tasks#TaskA", phase_a)
    assert "isai://tasks#TaskA" in snap_after_a.active_tasks
    assert len(snap_after_a.open_handles) == 2
    assert snap_after_a.audit_status == "STAGING"

    # Conflicting TaskB writing or reading locked 'isai://knowledge' must be rejected
    conflicting_phase = PhaseNodeSpec(
        phase_id="P1",
        title="Conflicting write",
        target_node_ref="isai://knowledge",
        write_set=("isai://knowledge",),
    )
    with pytest.raises(ValueError, match="Concurrency conflict"):
        wd.register_phase_handles(snap_after_a, "isai://tasks#TaskB", conflicting_phase)

    # Disjoint TaskC writing 'isai://user' must succeed in parallel
    disjoint_phase = PhaseNodeSpec(
        phase_id="P1",
        title="Parallel user update",
        target_node_ref="isai://user",
        read_set=("isai://root",),
        write_set=("isai://user",),
    )
    snap_parallel = wd.register_phase_handles(snap_after_a, "isai://tasks#TaskC", disjoint_phase)
    assert set(snap_parallel.active_tasks) == {"isai://tasks#TaskA", "isai://tasks#TaskC"}

    # Salsa Early-Cutoff check: unchanged public interface -> early_cutoff=True
    nodes = discover_nodes(sandbox)
    _, k_node = nodes["isai://knowledge"]
    unchanged_impact = evaluate_interface_cascade(
        nodes, "isai://knowledge", k_node.interface_digest()
    )
    assert unchanged_impact.early_cutoff is True
    assert unchanged_impact.impacted_dependents == ()

    # Simulated public contract change -> early_cutoff=False & dependents discovered
    altered_node = ISAINodeSpec(
        **{
            **k_node.model_dump(),
            "outputs": (
                IOPortSpec(
                    name="new_port",
                    contract_type="dict",
                    description="Changed public output contract",
                ),
            ),
        }
    )
    assert altered_node.interface_digest() != k_node.interface_digest()
    changed_impact = evaluate_interface_cascade(
        {**nodes, "isai://knowledge": (sandbox / "knowledge", altered_node)},
        "isai://knowledge",
        k_node.interface_digest(),
    )
    assert changed_impact.early_cutoff is False
    assert "isai://root" in changed_impact.impacted_dependents
    assert "isai://tasks" in changed_impact.impacted_dependents

    # Closing both tasks drops open_handles to () and restores VALID status
    snap_closed_1 = wd.close_task_and_release_handles(snap_parallel, "isai://tasks#TaskA", 1)
    assert snap_closed_1.audit_status == "STAGING"
    snap_closed_all = wd.close_task_and_release_handles(snap_closed_1, "isai://tasks#TaskC", 1)
    assert snap_closed_all.active_tasks == ()
    assert snap_closed_all.open_handles == ()
    assert snap_closed_all.audit_status == "VALID"


def test_rsoc_compiler_minimal_clean_payload() -> None:
    """RSoC packet must contain constitutional & node context while omitting Watchdog hash clutter."""
    packet = compile_rsoc(REPO_ROOT, "isai://tasks", focus_tags=("ai",))
    assert packet["requested_uri"] == "isai://tasks"
    assert packet["enforced_genesis"]["priority"] == "THIS-FRAME >> ALL-SUBSEQUENT"
    assert packet["inherited_scope_invariants"][0]["node_id"] == "isai://root"
    assert packet["active_node_contract"]["node_id"] == "isai://tasks"
    assert "node_spec_digests" not in packet
    assert packet["operator_calibration"]["archetype"] == "FiduSys-Novator & Chronitect"


def test_knowledge_catalog_deduplicating_upsert() -> None:
    """KnowledgeCatalogSpec must forbid duplicate IDs and consolidate updates via upsert."""
    e1 = KnowledgeEntry(
        entry_id="PAT_01",
        category="pattern",
        title="Initial pattern",
        distilled_insight="v1 insight",
        applicability_tags=("isai",),
        related_node_ref="isai://root",
        origin_tx_id="TX-0001",
        verified_revision=1,
    )
    with pytest.raises(ValidationError, match="Redundancy=FATAL"):
        KnowledgeCatalogSpec(entries=(e1, e1))

    cat = KnowledgeCatalogSpec(entries=(e1,))
    e1_v2 = KnowledgeEntry(
        entry_id="PAT_01",
        category="pattern",
        title="Refined pattern",
        distilled_insight="v2 consolidated insight",
        applicability_tags=("isai", "core"),
        related_node_ref="isai://root",
        origin_tx_id="TX-0002",
        verified_revision=2,
    )
    updated_cat = cat.upsert(e1_v2)
    assert len(updated_cat.entries) == 1
    assert updated_cat.entries[0].distilled_insight == "v2 consolidated insight"
