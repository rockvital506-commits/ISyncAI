"""Comprehensive Gate A 360° Hypergraph, Cross-Link & Crash Recovery Tests for ISAI v0.2.0."""

from __future__ import annotations

import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from _isai_sandbox import quiesce_staging

from isai.__main__ import main as isai_cli_main
from isai.atomic_io import TEMP_ARTIFACT_PREFIX, atomic_write_text
from isai.constitution import (
    DEFAULT_BOUNDARY_IGNORE,
    GENESIS_BYTE_LENGTH,
    GENESIS_CONSTITUTION,
    GENESIS_SHA256,
    IntegrityLevel,
)
from isai.contracts import (
    EdgeKind,
    EdgeLinkSpec,
    IOPortSpec,
    ISAINodeSpec,
    PhaseMode,
    SymbolBindingKind,
    SymbolBindingSpec,
    TransitionRule,
)
from isai.domain_models import KnowledgeCatalogSpec, KnowledgeEntry
from isai.engine import (
    audit_repository,
    compile_rsoc,
    evaluate_interface_cascade,
    load_module_attr,
    read_chronicle,
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
    quiesce_staging(dest)
    return dest


@pytest.mark.isai_scope("isai://root", "isai://user", "isai://knowledge", "isai://tasks", "isai://tests")
def test_live_repository_passes_full_360_audit_and_idempotent_recover(tmp_path: Path) -> None:
    """Live repository must satisfy 100% of 360° checks, and 'isai recover' must be a no-op on clean state."""
    genesis_check = GENESIS_CONSTITUTION.verify_genesis_header(REPO_ROOT / "README.md")
    assert genesis_check.valid is True
    assert genesis_check.actual_sha256 == GENESIS_SHA256
    assert genesis_check.actual_byte_length == GENESIS_BYTE_LENGTH

    report = audit_repository(REPO_ROOT)
    assert report.valid is True, f"Audit failed with issues: {report.issues}"
    assert report.issues == ()
    assert report.verified_symbols_count >= 16
    assert report.verified_port_wirings_count >= 5
    assert report.checked_markdown_files_count >= 7
    canonical_hives = {
        "isai://root",
        "isai://user",
        "isai://knowledge",
        "isai://tasks",
        "isai://tests",
    }
    checked = set(report.checked_nodes)
    assert canonical_hives <= checked
    # Nothing may exist beyond the canonical hives except explicitly active staging tasks.
    extra = checked - canonical_hives
    assert all(node.startswith("isai://tasks/TASK-") for node in extra), extra

    # Verify recover idempotency on a clean clone (zero new Chronicle transactions)
    sandbox = _clone_repo_to_tmp(tmp_path)
    recover_fn = load_module_attr(
        sandbox / "tasks" / ".isai" / "watchdog.py",
        "_test_clean_recover",
        "recover_repository",
    )
    before_events = read_chronicle(sandbox)
    rec_report = recover_fn(sandbox)
    after_events = read_chronicle(sandbox)
    assert rec_report.recovered is False
    assert rec_report.chronicle_tx_id is None
    assert len(after_events) == len(before_events)


@pytest.mark.isai_scope("isai://root#GenesisKernel")
def test_detects_genesis_header_tampering(tmp_path: Path) -> None:
    """Modifying even a single byte inside the first 586 bytes of README.md must trigger GENESIS_TAMPERED."""
    sandbox = _clone_repo_to_tmp(tmp_path)
    readme = sandbox / "README.md"
    raw = bytearray(readme.read_bytes())
    raw[2] = ord("i")
    readme.write_bytes(bytes(raw))

    report = audit_repository(sandbox, require_clean_snapshot=False)
    assert report.valid is False
    codes = {i.code for i in report.issues}
    assert "GENESIS_TAMPERED" in codes

    with pytest.raises(RuntimeError, match="Refusing sync"):
        sync_repository(sandbox)


@pytest.mark.isai_scope("isai://root", "isai://user")
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


@pytest.mark.isai_scope("isai://tests", "isai://user", "isai://root#HypergraphIndex")
def test_detects_broken_entity_ref_valid_node_missing_symbol_and_readme_desync(
    tmp_path: Path,
) -> None:
    """Both missing nodes AND valid nodes with nonexistent #Symbol must fail UNRESOLVED_ENTITY_REF."""
    sandbox = _clone_repo_to_tmp(tmp_path)

    user_readme = sandbox / "user" / "README.md"
    user_readme.write_text(
        user_readme.read_text(encoding="utf-8").replace("spec_digest=", "spec_digest=0000"),
        encoding="utf-8",
    )

    tests_node_py = sandbox / "tests" / ".isai" / "node.py"
    tests_node_py.write_text(
        tests_node_py.read_text(encoding="utf-8")
        .replace("isai://root#HypergraphIndex", "isai://tasks#NonExistentSymbol")
        .replace("isai://tasks#CrashRecoveryService", "isai://ghost/missing#Phantom"),
        encoding="utf-8",
    )

    report = audit_repository(sandbox, require_clean_snapshot=False)
    assert report.valid is False
    codes = {i.code for i in report.issues}
    assert "README_DIGEST_MISMATCH" in codes
    unresolved_msgs = [i.message for i in report.issues if i.code == "UNRESOLVED_ENTITY_REF"]
    assert any("isai://tasks#NonExistentSymbol" in m for m in unresolved_msgs)
    assert any("isai://ghost/missing#Phantom" in m for m in unresolved_msgs)


@pytest.mark.isai_scope("isai://user#OperatorProfile")
def test_detects_broken_physical_symbol_binding_and_schema_guard(tmp_path: Path) -> None:
    """Deleting/renaming a bound Python symbol in code must trigger BROKEN_SYMBOL_BINDING."""
    with pytest.raises(ValidationError, match="registered in neither"):
        ISAINodeSpec(
            node_id="isai://demo",
            title="Invalid binding node",
            integrity_level=IntegrityLevel.IL_2_CANONICAL,
            parent_ref="isai://root",
            goal="Test guard",
            success_criteria=("Must reject unlisted file",),
            capabilities=("Schema validation",),
            owned_files=("README.md",),
            system_files=("node.py",),
            symbol_bindings=(
                SymbolBindingSpec(
                    symbol="GhostAttr",
                    kind=SymbolBindingKind.PYTHON_ATTR,
                    target="unlisted.py:OBJ",
                ),
            ),
        )

    sandbox = _clone_repo_to_tmp(tmp_path)
    profile_py = sandbox / "user" / ".isai" / "profile.py"
    profile_py.write_text(
        profile_py.read_text(encoding="utf-8").replace("USER_PROFILE =", "RENAMED_PROFILE ="),
        encoding="utf-8",
    )

    report = audit_repository(sandbox, require_clean_snapshot=False)
    assert report.valid is False
    binding_issues = [i for i in report.issues if i.code == "BROKEN_SYMBOL_BINDING"]
    assert len(binding_issues) == 1
    assert "OperatorProfile" in binding_issues[0].location
    assert "USER_PROFILE" in binding_issues[0].message


@pytest.mark.isai_scope("isai://root")
def test_detects_unreachable_island_node(tmp_path: Path) -> None:
    """A synced directory node without any incoming Router transition from isai://root must fail UNREACHABLE_NODE."""
    sandbox = _clone_repo_to_tmp(tmp_path)
    island_dir = sandbox / "island"
    (island_dir / ".isai").mkdir(parents=True)
    (island_dir / "README.md").write_text("# Island\n", encoding="utf-8")
    (island_dir / ".isai" / "node.py").write_text(
        """from isai.constitution import IntegrityLevel
from isai.contracts import EdgeKind, EdgeLinkSpec, ISAINodeSpec

NODE = ISAINodeSpec(
    node_id="isai://island",
    title="Unrouted Island Node",
    integrity_level=IntegrityLevel.IL_2_CANONICAL,
    parent_ref="isai://root",
    goal="Exist without any incoming transition from root",
    success_criteria=("Detected as unreachable",),
    capabilities=("Synthetic island node",),
    owned_files=("README.md",),
    system_files=("node.py",),
    links=(EdgeLinkSpec(target_ref="isai://root#GenesisKernel", kind=EdgeKind.GOVERNED_BY),),
)
""",
        encoding="utf-8",
    )
    sync_repository(sandbox)

    report = audit_repository(sandbox, require_clean_snapshot=False)
    assert report.valid is False
    codes = {i.code for i in report.issues}
    assert "UNREACHABLE_NODE" in codes
    assert all(
        c not in codes for c in ("MISSING_README", "README_DIGEST_MISMATCH", "ORPHAN_FILE")
    )


@pytest.mark.isai_scope("isai://tasks#WatchdogService")
def test_transitive_n_hop_cascade_with_mutual_cycles_and_early_cutoff() -> None:
    """evaluate_interface_cascade must traverse multi-hop dependencies in topological distance order without looping."""

    def _mk_node(nid: str, refs: tuple[str, ...], out_name: str = "out") -> ISAINodeSpec:
        return ISAINodeSpec(
            node_id=nid,
            title=nid,
            integrity_level=IntegrityLevel.IL_2_CANONICAL,
            parent_ref="isai://root" if nid != "isai://root" else None,
            goal="Cascade test",
            success_criteria=("Deterministic N-hop cascade",),
            capabilities=("Synthetic dependency node",),
            outputs=(IOPortSpec(name=out_name, contract_type="dict", description="port"),),
            owned_files=("README.md",),
            system_files=("node.py",),
            links=tuple(
                EdgeLinkSpec(target_ref=r, kind=EdgeKind.CONSUMES_CONTRACT) for r in refs
            ),
            transitions=(
                TransitionRule(
                    trigger="step",
                    target_ref=refs[0],
                    phase_mode=PhaseMode.FAST_READ,
                    description="hop",
                ),
            )
            if refs
            else (),
        )

    node_a = _mk_node("isai://a", ())
    node_b = _mk_node("isai://b", ("isai://a", "isai://c"))
    node_c = _mk_node("isai://c", ("isai://b",))
    node_d = _mk_node("isai://d", ("isai://c",))

    graph = {
        "isai://a": (Path("/tmp/a"), node_a),
        "isai://b": (Path("/tmp/b"), node_b),
        "isai://c": (Path("/tmp/c"), node_c),
        "isai://d": (Path("/tmp/d"), node_d),
    }

    no_impact = evaluate_interface_cascade(graph, "isai://a", node_a.interface_digest())
    assert no_impact.early_cutoff is True
    assert no_impact.impacted_dependents == ()
    assert no_impact.max_hop_depth == 0

    node_a_v2 = _mk_node("isai://a", (), out_name="out_v2")
    graph_v2 = {**graph, "isai://a": (Path("/tmp/a"), node_a_v2)}
    impact = evaluate_interface_cascade(graph_v2, "isai://a", node_a.interface_digest())
    assert impact.early_cutoff is False
    assert impact.impacted_dependents == ("isai://b", "isai://c", "isai://d")
    assert impact.max_hop_depth == 3


@pytest.mark.isai_scope("isai://user", "isai://knowledge")
def test_detects_broken_markdown_links_and_prose_citations(tmp_path: Path) -> None:
    """Markdown scanner must catch dead relative links, EntityRefs, TX-xxxx, and PAT_xxx while ignoring code blocks."""
    sandbox = _clone_repo_to_tmp(tmp_path)
    user_md = sandbox / "user" / "README.md"
    injected_prose = (
        "\n### Тестовая заметка\n"
        "- Валидный шаблон в прозе: `isai://<scope>[#<symbol>]`.\n"
        "- Ссылка в code-блоке игнорируется:\n"
        "```markdown\n"
        "[ignored](missing_in_code.md) isai://fake#InCode TX-8888 PAT_IN_CODE\n"
        "```\n"
        "- Битая файловая ссылка: [Dead Doc](missing_folder/doc.md)\n"
        "- Битый символ в прозе: `isai://user#MissingSymbol`\n"
        "- Несуществующая транзакция: `TX-9999`\n"
        "- Несуществующий паттерн: `PAT_DOES_NOT_EXIST`\n\n"
    )
    original = user_md.read_text(encoding="utf-8")
    marker = "<!-- ISAI:SYNC:BEGIN -->"
    atomic_write_text(user_md, original.replace(marker, injected_prose + marker, 1))

    report = audit_repository(sandbox, require_clean_snapshot=False)
    assert report.valid is False
    md_links = [i for i in report.issues if i.code == "BROKEN_MARKDOWN_LINK"]
    prose_refs = [i for i in report.issues if i.code == "BROKEN_PROSE_REF"]

    assert len(md_links) == 1
    assert "missing_folder/doc.md" in md_links[0].message

    assert len(prose_refs) == 3
    joined = " | ".join(i.message for i in prose_refs)
    assert "isai://user#MissingSymbol" in joined
    assert "TX-9999" in joined
    assert "PAT_DOES_NOT_EXIST" in joined
    assert "TX-8888" not in joined
    assert "PAT_IN_CODE" not in joined


@pytest.mark.isai_scope("isai://tasks#CrashRecoveryService", "isai://tasks#WatchdogService")
def test_crash_recovery_heals_multi_fault_chaos_and_restores_valid_audit(
    tmp_path: Path,
) -> None:
    """Inject simultaneous mid-flight crash faults and verify 'isai recover' heals the repo back to 100% VALID."""
    sandbox = _clone_repo_to_tmp(tmp_path)
    watchdog_cls = load_module_attr(
        sandbox / "tasks" / ".isai" / "watchdog.py",
        "_test_chaos_wd",
        "TaskWatchdog",
    )
    wd = watchdog_cls(sandbox)

    crash_task_dir = sandbox / "tasks" / "TASK-CRASH"
    (crash_task_dir / ".isai").mkdir(parents=True)
    (crash_task_dir / "README.md").write_text("# Crash Task\n", encoding="utf-8")
    (crash_task_dir / ".isai" / "node.py").write_text(
        """from isai.constitution import IntegrityLevel
from isai.contracts import ISAINodeSpec, VisibilityScope

NODE = ISAINodeSpec(
    node_id="isai://tasks/TASK-CRASH",
    title="Interrupted Staging Task",
    integrity_level=IntegrityLevel.IL_3_STAGING,
    visibility=VisibilityScope.EPHEMERAL_STAGING,
    parent_ref="isai://tasks",
    goal="Simulate mid-flight agent crash",
    success_criteria=("Aborted on lease expiry",),
    capabilities=("Synthetic crash staging node",),
    owned_files=("README.md",),
    system_files=("node.py",),
)
""",
        encoding="utf-8",
    )
    sync_repository(sandbox)

    two_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    base_snap = wd.load_snapshot()
    staged_snap = wd.register_phase_handles(
        base_snap,
        "isai://tasks/TASK-CRASH",
        PhaseNodeSpec(
            phase_id="P-CRASH",
            title="Interrupted write",
            target_node_ref="isai://user",
            write_set=("isai://user",),
        ),
        acquired_at_utc=two_hours_ago,
        lease_ttl_seconds=60,
    )
    wd.save_snapshot(staged_snap)

    (sandbox / ".isai" / f"{TEMP_ARTIFACT_PREFIX}999_chronicle").write_text("partial", encoding="utf-8")
    (sandbox / "user" / f"{TEMP_ARTIFACT_PREFIX}999_readme").write_text("partial", encoding="utf-8")

    chronicle_file = sandbox / ".isai" / "chronicle.jsonl"
    chronicle_file.write_text(
        chronicle_file.read_text(encoding="utf-8") + '{"tx_id": "TX-BROKEN", "half_json": ',
        encoding="utf-8",
    )

    (sandbox / "tasks" / "ORPHAN-999").mkdir(parents=True)
    (sandbox / "tasks" / "ORPHAN-999" / "scratch.txt").write_text("junk", encoding="utf-8")
    (sandbox / "user" / "README.md").write_text("# Drifted README without markers\n", encoding="utf-8")

    broken_audit = audit_repository(sandbox)
    assert broken_audit.valid is False
    broken_codes = {i.code for i in broken_audit.issues}
    assert "TORN_TEMP_ARTIFACT" in broken_codes
    assert "INVALID_CHRONICLE" in broken_codes
    assert "EXPIRED_HANDLE_LEASE" in broken_codes
    assert "README_SYNC_MARKERS_MISSING" in broken_codes

    exit_code = isai_cli_main(["--root", str(sandbox), "recover"])
    assert exit_code == 0

    assert not crash_task_dir.exists()
    assert not (sandbox / "tasks" / "ORPHAN-999").exists()
    assert not (sandbox / ".isai" / f"{TEMP_ARTIFACT_PREFIX}999_chronicle").exists()

    healed_audit = audit_repository(sandbox)
    assert healed_audit.valid is True, f"Post-recovery audit failed: {healed_audit.issues}"
    assert healed_audit.issues == ()

    healed_snap = wd.load_snapshot()
    assert healed_snap.active_tasks == ()
    assert healed_snap.open_handles == ()
    assert healed_snap.audit_status == "VALID"

    events = read_chronicle(sandbox)
    assert events[-1].operation == "RECOVER"

    rec_again = wd.recover()
    assert rec_again.recovered is False
    assert len(read_chronicle(sandbox)) == len(events)


@pytest.mark.isai_scope("isai://root#PhaseExecutionProtocol")
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

    with pytest.raises(ValueError, match="realization is None"):
        state.record_gate_outcome(passed=True)

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
    assert state.should_run_research() is False
    assert "[GATE-A1]" in state.build_task_context()

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

    clean_state = PhaseExecutionState(
        phase_ref="isai://tasks#phase-ok",
        description="Clean pass",
        rsoc_digest="b" * 64,
        realization=PhaseOutputEnvelope(summary="All checks green"),
    )
    assert clean_state.record_gate_outcome(passed=True) == PhaseStatus.CONVERGED


@pytest.mark.isai_scope("isai://tasks#WatchdogService")
def test_watchdog_mvcc_handles_and_release(tmp_path: Path) -> None:
    """TaskWatchdog must enforce disjoint WriteSets and reset HandleCount -> 0 on close."""
    sandbox = _clone_repo_to_tmp(tmp_path)
    watchdog_cls = load_module_attr(
        sandbox / "tasks" / ".isai" / "watchdog.py",
        "_test_watchdog_mod",
        "TaskWatchdog",
    )
    wd = watchdog_cls(sandbox)
    base_snap = wd.load_snapshot()

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

    conflicting_phase = PhaseNodeSpec(
        phase_id="P1",
        title="Conflicting write",
        target_node_ref="isai://knowledge",
        write_set=("isai://knowledge",),
    )
    with pytest.raises(ValueError, match="Concurrency conflict"):
        wd.register_phase_handles(snap_after_a, "isai://tasks#TaskB", conflicting_phase)

    disjoint_phase = PhaseNodeSpec(
        phase_id="P1",
        title="Parallel user update",
        target_node_ref="isai://user",
        read_set=("isai://root",),
        write_set=("isai://user",),
    )
    snap_parallel = wd.register_phase_handles(snap_after_a, "isai://tasks#TaskC", disjoint_phase)
    assert set(snap_parallel.active_tasks) == {"isai://tasks#TaskA", "isai://tasks#TaskC"}

    snap_closed_1 = wd.close_task_and_release_handles(snap_parallel, "isai://tasks#TaskA", base_snap.revision)
    assert snap_closed_1.audit_status == "STAGING"
    snap_closed_all = wd.close_task_and_release_handles(snap_closed_1, "isai://tasks#TaskC", base_snap.revision)
    assert snap_closed_all.active_tasks == ()
    assert snap_closed_all.open_handles == ()
    assert snap_closed_all.audit_status == "VALID"


@pytest.mark.isai_scope("isai://root#RSoCCompiler", "isai://knowledge#EmpiricalCatalog")
def test_rsoc_compiler_and_knowledge_upsert() -> None:
    """RSoC v0.2.5 packet must expose bimodal IL-1C slices + symbol_bindings + 1-hop linked_interface_stubs, and KnowledgeCatalogSpec.upsert must deduplicate."""
    packet = compile_rsoc(REPO_ROOT, "isai://tests")
    assert packet["rsoc_schema"] == "0.2.5"
    assert packet["requested_uri"] == "isai://tests"
    assert packet["enforced_genesis"]["priority"] == "THIS-FRAME >> ALL-SUBSEQUENT"
    assert packet["inherited_scope_invariants"][0]["node_id"] == "isai://root"
    assert packet["active_node_contract"]["node_id"] == "isai://tests"
    assert any(
        b["symbol"] == "HypergraphCrossTestSuite"
        for b in packet["active_node_contract"]["symbol_bindings"]
    )
    stub_ids = {s["node_id"] for s in packet["linked_interface_stubs"]}
    assert {"isai://root", "isai://tasks"} <= stub_ids
    assert "node_spec_digests" not in packet

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
