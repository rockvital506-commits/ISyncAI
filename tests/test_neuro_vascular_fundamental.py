"""Tri-Tier Verification Suite for Ring IL-1C Neuro-Vascular Fundamental (`ISAI-NVF v1.0`),
Bimodal RSoC v0.2.5 Delivery, Advisory Write Locking, and the 6-Step Algedonic Governance Gate.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from hypothesis import settings
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule
from hypothesis import strategies as st
from pydantic import ValidationError

from isai.__main__ import main as isai_cli_main
from isai.atomic_io import atomic_write_text, repository_write_lock
from isai.constitution import DEFAULT_BOUNDARY_IGNORE, GENESIS_CONSTITUTION
from isai.engine import (
    append_chronicle,
    audit_repository,
    build_clean_snapshot,
    compile_rsoc,
    load_module_attr,
    read_chronicle,
    sync_repository,
)
from isai.graph_index import build_hypergraph_index, load_repo_nvf
from isai.link_mutator import LinkMutationError, LinkMutator
from isai.neuro_vascular import (
    ALGEDONIC_STEP_ORDER,
    AlgedonicDeviationCase,
    NEURO_VASCULAR_FUNDAMENTAL,
)
from isai.protocol import (
    ChronicleEvent,
    CriterionSpec,
    GateKind,
    PhaseNodeSpec,
    TaskManifest,
    utc_now_iso,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
EXPECTED_NVF_V1_SHA256 = "f5b1a1ca16ab955374d9f30eba6c8b868c177b88347e39ef630ef20116981d4c"


def _clone_repo_to_tmp(tmp_path: Path) -> Path:
    dest = tmp_path / "isai_nvf_sandbox"

    def _ignore(dir_str: str, names: list[str]) -> set[str]:
        rel_dir = Path(dir_str).resolve().relative_to(REPO_ROOT)
        ignored: set[str] = set()
        for name in names:
            cand = Path(name) if rel_dir == Path(".") else rel_dir / name
            if DEFAULT_BOUNDARY_IGNORE.is_ignored(cand):
                ignored.add(name)
        return ignored

    shutil.copytree(REPO_ROOT, dest, ignore=_ignore)
    return dest


def _tree_sha256(root: Path) -> dict[str, str]:
    digests: dict[str, str] = {}
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if DEFAULT_BOUNDARY_IGNORE.is_ignored(rel):
            continue
        digests[rel.as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return digests


def _sample_task_manifest() -> TaskManifest:
    return TaskManifest(
        task_id="TASK-ALG-001",
        title="Ratified IL-1C Constitutional Amendment",
        ultimate_goal="Update IL-1C parameter safely under Operator ratification.",
        global_criteria=(
            CriterionSpec(
                gate_id="G1",
                kind=GateKind.DETERMINISTIC,
                criterion="isai audit == 0",
            ),
        ),
        phases=(
            PhaseNodeSpec(
                phase_id="P1",
                title="Amend IL-1C with Operator ratification",
                target_node_ref="isai://root",
                write_set=("isai://root#NeuroVascularFundamental",),
            ),
        ),
    )


# ============================================================================
# TIER 1: Lossless DSL Fidelity, Bimodal RSoC v0.2.5 & VAET Anchoring
# ============================================================================


@pytest.mark.isai_scope("isai://root#NeuroVascularFundamental", "isai://root")
def test_nvf_dsl_lossless_fidelity_and_cli_show_verify(capsys: pytest.CaptureFixture[str]) -> None:
    """ISAI-NVF v1.0 must render byte-identically (53 lines, 6568 UTF-8 bytes) with 0% semantic loss."""
    dsl = NEURO_VASCULAR_FUNDAMENTAL.render_dsl()
    lines = dsl.splitlines()
    assert len(lines) == 53
    assert len(dsl.encode("utf-8")) == 6568
    assert NEURO_VASCULAR_FUNDAMENTAL.dsl_sha256() == EXPECTED_NVF_V1_SHA256

    for mandatory_token in (
        "[FRAME-ID]: ISAI-NVF/1.0 | TIER: IL-1C_SUB_GENESIS | GOVERNED-BY: isai://root#GenesisKernel",
        "[PRIORITY-ORDER]: IL-0_GENESIS >> IL-1C_NVF >> IL-1_KERNEL >> IL-2_CANONICAL >> IL-3_STAGING",
        "[MUTABILITY-LAW]: CONDITIONALLY_LOCKED[RoutineEdit=FATAL | AmendVia=ALGEDONIC_6STEP_ONLY]",
        "[LEXICON-ANCHORS]:",
        "N1.Addressing:",
        "N7.Spinal-Reflexes:",
        "N8.TriTier-GateA:",
        "V1.RSoC-Artery:",
        "V5.Hemostasis-Recovery:",
        "Precedents[PREC-01..09]:",
        "Bottleneck-Guards[BN-01..06]:",
        "Mode-1.Homeostasis(Autonomous):",
        "Mode-2.Algedonic-Escalation(Operator-Gated):",
        "1.CONFIRM_DEVIATION",
        "6.AWAIT_OPERATOR_CONFIRMATION",
        "STOP-1[IL-0]:",
        "STOP-2[LINKS]:",
        "STOP-3[PROMOTE]:",
        "STOP-4[AMEND]:",
    ):
        assert mandatory_token in dsl

    rc_show = isai_cli_main(["--root", str(REPO_ROOT), "nv", "show"])
    out_show = capsys.readouterr().out
    assert rc_show == 0
    assert out_show == dsl

    rc_verify = isai_cli_main(["--root", str(REPO_ROOT), "nv", "verify"])
    out_verify = json.loads(capsys.readouterr().out)
    assert rc_verify == 0
    assert out_verify["ratified_in_chronicle"] is True
    assert out_verify["dsl_sha256"] == EXPECTED_NVF_V1_SHA256


@pytest.mark.isai_scope("isai://root#RSoCCompiler", "isai://root#NeuroVascularFundamental")
def test_bimodal_rsoc_primacy_head_and_recency_tail_ordering() -> None:
    """RSoC v0.2.5 must sandwich context between Primacy Head (after Genesis) and Recency Tail (last key)."""
    packet = compile_rsoc(REPO_ROOT, "isai://tests")
    keys = list(packet.keys())
    assert packet["rsoc_schema"] == "0.2.5"

    gen_idx = keys.index("enforced_genesis")
    nvf_idx = keys.index("enforced_neuro_vascular_frame")
    assert nvf_idx == gen_idx + 1, f"Expected NVF primacy head right after Genesis, got {keys}"
    assert keys[-1] == "terminal_execution_guard", f"Expected Recency guard as final key, got {keys}"

    head = packet["enforced_neuro_vascular_frame"]
    tail = packet["terminal_execution_guard"]
    assert head["frame_id"] == "ISAI-NVF/1.0"
    assert head["dsl_sha256"] == EXPECTED_NVF_V1_SHA256
    assert len(head["lexicon_anchors"]) == 5
    assert len(tail["governance_routing"]["algedonic_6step_sequence"]) == 6
    assert len(tail["recency_tripwires"]) == 4

    # Control Plane isolation still holds
    for forbidden in ("node_spec_digests", "node_interface_digests", "open_handles"):
        assert forbidden not in packet


@pytest.mark.isai_scope("isai://root#HypergraphIndex", "isai://root#NeuroVascularFundamental")
def test_nvf_vaet_anchoring_and_can_mutate_protection() -> None:
    """HypergraphIndex must anchor IL-1C references in VAET and fail-closed on IL-1C mutations."""
    idx = build_hypergraph_index(REPO_ROOT)
    outbound_targets = {e.target_ref for e in idx.outbound_of("isai://root#NeuroVascularFundamental")}
    assert "isai://root#GenesisKernel" in outbound_targets
    assert "isai://root#MasterVector" in outbound_targets
    assert "isai://root#ChronicleLedger" in outbound_targets

    rep = idx.can_mutate("isai://root#NeuroVascularFundamental", operation="mutate_interface")
    assert rep.safe_without_cascade is False
    assert any("IL-1C" in r for r in rep.blocking_reasons)

    sel = idx.select_affected_tests(("isai://root#NeuroVascularFundamental",))
    assert sel["mode"] == "FULL_SUITE_FAIL_CLOSED"


# ============================================================================
# TIER 2: Tamper Detection, Watchdog Gate, Backdoor Prevention & Advisory Lock
# ============================================================================


@pytest.mark.isai_scope("isai://root#NeuroVascularFundamental", "isai://root#ChronicleLedger")
def test_unratified_nvf_edit_blocked_until_operator_chronicle_ratification(tmp_path: Path) -> None:
    """Editing even 1 token of .isai/neuro_vascular.py without RATIFY_FUNDAMENTAL must fail Gate A."""
    sandbox = _clone_repo_to_tmp(tmp_path)
    nvf_py = sandbox / ".isai" / "neuro_vascular.py"
    orig_text = nvf_py.read_text(encoding="utf-8")
    tampered_text = orig_text.replace("MaxIter=3", "MaxIter=9")
    assert tampered_text != orig_text
    nvf_py.write_text(tampered_text, encoding="utf-8")

    # 1. Before sync: fails both NVF_OUT_OF_SYNC and UNRATIFIED_FUNDAMENTAL_MUTATION
    rep1 = audit_repository(sandbox, require_clean_snapshot=False)
    assert rep1.valid is False
    codes1 = {i.code for i in rep1.issues}
    assert "NVF_OUT_OF_SYNC" in codes1
    assert "UNRATIFIED_FUNDAMENTAL_MUTATION" in codes1

    # 2. Even if an agent runs 'isai sync', UNRATIFIED_FUNDAMENTAL_MUTATION still blocks!
    sync_repository(sandbox)
    rep2 = audit_repository(sandbox, require_clean_snapshot=False)
    assert rep2.valid is False
    codes2 = {i.code for i in rep2.issues}
    assert "NVF_OUT_OF_SYNC" not in codes2
    assert "UNRATIFIED_FUNDAMENTAL_MUTATION" in codes2

    # 3. Only after appending an Operator-approved RATIFY_FUNDAMENTAL event + refreshing snapshot does Gate A pass
    events = read_chronicle(sandbox)
    new_rev = events[-1].revision + 1
    new_nvf = load_repo_nvf(sandbox)
    append_chronicle(
        sandbox,
        ChronicleEvent(
            tx_id=f"TX-{new_rev:04d}",
            revision=new_rev,
            timestamp_utc=utc_now_iso(),
            actor="Operator",
            phase_ref="isai://root#NeuroVascularFundamental",
            operation="RATIFY_FUNDAMENTAL",
            touched_refs=("isai://root#NeuroVascularFundamental",),
            interface_changed=True,
            ratified_nvf_digest=new_nvf.dsl_sha256(),
            operator_approved=True,
            summary="Operator-approved test amendment of MaxIter.",
        ),
    )
    snap = build_clean_snapshot(sandbox, revision=new_rev)
    atomic_write_text(sandbox / "tasks" / ".isai" / "state_snapshot.json", snap.model_dump_json(indent=2) + "\n")

    rep3 = audit_repository(sandbox)
    assert rep3.valid is True, f"Expected clean audit after ratification, got {rep3.issues}"


@pytest.mark.isai_scope("isai://tasks#WatchdogService", "isai://root#AlgedonicProtocol")
def test_watchdog_blocks_unratified_il1c_write_lease_and_accepts_6step_ratification(
    tmp_path: Path,
) -> None:
    """TaskWatchdog must block WRITE_LEASE on IL-1C unless a complete 6-Step ratified case is provided."""
    sandbox = _clone_repo_to_tmp(tmp_path)
    wd_cls = load_module_attr(sandbox / "tasks" / ".isai" / "watchdog.py", "_test_nvf_wd", "TaskWatchdog")
    wd = wd_cls(sandbox)
    base_snap = wd.load_snapshot()

    amend_phase = PhaseNodeSpec(
        phase_id="P-AMEND",
        title="Attempt IL-1C amendment",
        target_node_ref="isai://root",
        write_set=("isai://root#NeuroVascularFundamental",),
    )

    # Blocked without AlgedonicDeviationCase
    with pytest.raises(ValueError, match="IL-1C Conditional-Mutability violation"):
        wd.register_phase_handles(base_snap, "isai://tasks#UnapprovedAmend", amend_phase)

    # Blocked when Step 6 (operator_confirmed) is False
    unconfirmed_case = AlgedonicDeviationCase(
        case_id="ALG-UNCONFIRMED",
        confirmed_deviation_evidence="Detected structural bottleneck.",
        operator_warning_alert="Alert surfaced to Operator.",
        deep_research_findings=("Paper A", "Paper B"),
        recommended_mechanisms=("Mechanism M1",),
        proposed_task=_sample_task_manifest(),
        operator_confirmed=False,
    )
    assert unconfirmed_case.is_ratified_for_execution() is False
    with pytest.raises(ValueError, match="IL-1C Conditional-Mutability violation"):
        wd.register_phase_handles(
            base_snap,
            "isai://tasks#UnconfirmedAmend",
            amend_phase,
            algedonic_case=unconfirmed_case,
        )

    # Permitted ONLY with all 6 steps + operator_confirmed=True
    ratified_case = AlgedonicDeviationCase(
        case_id="ALG-RATIFIED",
        confirmed_deviation_evidence="Detected structural bottleneck.",
        operator_warning_alert="Alert surfaced to Operator.",
        deep_research_findings=("Paper A", "Paper B"),
        recommended_mechanisms=("Mechanism M1",),
        proposed_task=_sample_task_manifest(),
        operator_confirmed=True,
        operator_confirmation_note="Operator explicitly confirmed phased amendment.",
    )
    assert ratified_case.is_ratified_for_execution() is True
    leased_snap = wd.register_phase_handles(
        base_snap,
        "isai://tasks#RatifiedAmend",
        amend_phase,
        algedonic_case=ratified_case,
    )
    assert any(
        h.target_ref == "isai://root#NeuroVascularFundamental" for h in leased_snap.open_handles
    )


@pytest.mark.isai_scope("isai://root#LinkInjector", "isai://root#NeuroVascularFundamental")
def test_link_mutator_blocks_il1c_refactor_backdoor_and_supports_ephemeral_task_scaffold(
    tmp_path: Path,
) -> None:
    """LinkMutator must refuse refactoring IL-1C or its anchored symbols, while supporting atomic task staging."""
    sandbox = _clone_repo_to_tmp(tmp_path)
    mutator = LinkMutator(sandbox)
    before = _tree_sha256(sandbox)

    with pytest.raises(ValueError, match="Cannot refactor constitutional anchor"):
        mutator.refactor_entity_ref(
            "isai://root#NeuroVascularFundamental",
            "isai://root#RenamedFundamental",
        )

    with pytest.raises(LinkMutationError, match="IL-1C"):
        mutator.refactor_entity_ref(
            "isai://root#MasterVector",
            "isai://root#RenamedMasterVector",
        )

    assert _tree_sha256(sandbox) == before

    # Atomic scaffold + decommission of EPHEMERAL_STAGING task node
    scaf = mutator.scaffold_node(
        "tasks/TASK-777",
        title="Ephemeral Staging Test",
        goal="Verify PREC-10 atomic active_tasks registration and cleanup.",
    )
    assert scaf.applied is True
    assert audit_repository(sandbox).valid is True

    dec = mutator.decommission_node("isai://tasks/TASK-777")
    assert dec.applied is True
    assert not (sandbox / "tasks" / "TASK-777").exists()
    assert audit_repository(sandbox).valid is True
    assert GENESIS_CONSTITUTION.verify_genesis_header(sandbox / "README.md").valid is True


@pytest.mark.isai_scope("isai://root#AtomicPersistence")
def test_reentrant_advisory_write_lock_leaves_clean_audit_state(tmp_path: Path) -> None:
    """Re-entrant repository_write_lock must never self-deadlock and must not trigger ORPHAN_FILE."""
    sandbox = _clone_repo_to_tmp(tmp_path)
    with repository_write_lock(sandbox) as lock_a:
        with repository_write_lock(sandbox) as lock_b:
            assert lock_a == lock_b
            sync_repository(sandbox)

    rep = audit_repository(sandbox)
    assert rep.valid is True, f"Lock file caused audit issue: {rep.issues}"


# ============================================================================
# TIER 3: Generative Stateful Hypothesis Fuzzing of 6-Step Algedonic Gate
# ============================================================================


@settings(
    max_examples=35,
    stateful_step_count=20,
    deadline=None,
    database=None,
    derandomize=True,
)
class AlgedonicGovernanceMachine(RuleBasedStateMachine):
    """
    Stateful property-based fuzzer proving across arbitrary step mutations and Watchdog calls:
      1. Out-of-order Algedonic step population ALWAYS raises SkipStep=FATAL.
      2. Chronicle RATIFY_FUNDAMENTAL without operator_approved=True or 64-hex digest ALWAYS fails validation.
      3. IL-1C execution ratification holds IFF all 6 steps (1..6) are populated in strict order AND confirmed.
    """

    def __init__(self) -> None:
        super().__init__()
        self.step_1: str | None = None
        self.step_2: str | None = None
        self.step_3: tuple[str, ...] = ()
        self.step_4: tuple[str, ...] = ()
        self.step_5: TaskManifest | None = None
        self.step_6_confirmed: bool = False
        self.step_6_note: str | None = None

    def _has_gap(
        self,
        s1: str | None,
        s2: str | None,
        s3: tuple[str, ...],
        s4: tuple[str, ...],
        s5: TaskManifest | None,
        s6: bool,
    ) -> bool:
        flags = [bool(s1), bool(s2), len(s3) > 0, len(s4) > 0, s5 is not None, bool(s6)]
        seen_false = False
        for f in flags:
            if not f:
                seen_false = True
            elif seen_false:
                return True
        return False

    @rule(step_idx=st.integers(min_value=0, max_value=5))
    def try_populate_step(self, step_idx: int) -> None:
        cand = [
            self.step_1,
            self.step_2,
            self.step_3,
            self.step_4,
            self.step_5,
            self.step_6_confirmed,
        ]
        note = self.step_6_note
        if step_idx == 0:
            cand[0] = "Quantified critical goal drift."
        elif step_idx == 1:
            cand[1] = "Surfaced Algedonic alert to Operator."
        elif step_idx == 2:
            cand[2] = ("Research source 1", "Research source 2")
        elif step_idx == 3:
            cand[3] = ("Recommended neutralization pattern",)
        elif step_idx == 4:
            cand[4] = _sample_task_manifest()
        elif step_idx == 5:
            cand[5] = True
            note = "Explicit Operator confirmation granted."

        expect_gap = self._has_gap(
            cand[0],  # type: ignore[arg-type]
            cand[1],  # type: ignore[arg-type]
            cand[2],  # type: ignore[arg-type]
            cand[3],  # type: ignore[arg-type]
            cand[4],  # type: ignore[arg-type]
            bool(cand[5]),
        )

        if expect_gap:
            with pytest.raises(ValidationError, match="SkipStep=FATAL"):
                AlgedonicDeviationCase(
                    case_id="FUZZ",
                    confirmed_deviation_evidence=cand[0],  # type: ignore[arg-type]
                    operator_warning_alert=cand[1],  # type: ignore[arg-type]
                    deep_research_findings=cand[2],  # type: ignore[arg-type]
                    recommended_mechanisms=cand[3],  # type: ignore[arg-type]
                    proposed_task=cand[4],  # type: ignore[arg-type]
                    operator_confirmed=bool(cand[5]),
                    operator_confirmation_note=note,
                )
        else:
            case = AlgedonicDeviationCase(
                case_id="FUZZ",
                confirmed_deviation_evidence=cand[0],  # type: ignore[arg-type]
                operator_warning_alert=cand[1],  # type: ignore[arg-type]
                deep_research_findings=cand[2],  # type: ignore[arg-type]
                recommended_mechanisms=cand[3],  # type: ignore[arg-type]
                proposed_task=cand[4],  # type: ignore[arg-type]
                operator_confirmed=bool(cand[5]),
                operator_confirmation_note=note,
            )
            self.step_1 = case.confirmed_deviation_evidence
            self.step_2 = case.operator_warning_alert
            self.step_3 = case.deep_research_findings
            self.step_4 = case.recommended_mechanisms
            self.step_5 = case.proposed_task
            self.step_6_confirmed = case.operator_confirmed
            self.step_6_note = case.operator_confirmation_note

    @rule(approved=st.booleans(), valid_digest=st.booleans())
    def try_chronicle_ratification_event(self, approved: bool, valid_digest: bool) -> None:
        digest = EXPECTED_NVF_V1_SHA256 if valid_digest else "short"
        if not approved or not valid_digest:
            with pytest.raises(ValidationError):
                ChronicleEvent(
                    tx_id="TX-9999",
                    revision=99,
                    timestamp_utc="2026-11-11T00:00:00Z",
                    actor="Fuzzer",
                    phase_ref="isai://root#NeuroVascularFundamental",
                    operation="RATIFY_FUNDAMENTAL",
                    touched_refs=("isai://root#NeuroVascularFundamental",),
                    ratified_nvf_digest=digest,
                    operator_approved=approved,
                    summary="Fuzz ratify attempt",
                )
        else:
            ev = ChronicleEvent(
                tx_id="TX-9999",
                revision=99,
                timestamp_utc="2026-11-11T00:00:00Z",
                actor="Fuzzer",
                phase_ref="isai://root#NeuroVascularFundamental",
                operation="RATIFY_FUNDAMENTAL",
                touched_refs=("isai://root#NeuroVascularFundamental",),
                ratified_nvf_digest=digest,
                operator_approved=True,
                summary="Valid fuzz ratify attempt",
            )
            assert ev.operator_approved is True

    @invariant()
    def ratification_iff_all_six_ordered_steps_complete(self) -> None:
        case = AlgedonicDeviationCase(
            case_id="INV",
            confirmed_deviation_evidence=self.step_1,
            operator_warning_alert=self.step_2,
            deep_research_findings=self.step_3,
            recommended_mechanisms=self.step_4,
            proposed_task=self.step_5,
            operator_confirmed=self.step_6_confirmed,
            operator_confirmation_note=self.step_6_note,
        )
        all_six = bool(
            self.step_1
            and self.step_2
            and len(self.step_3) > 0
            and len(self.step_4) > 0
            and self.step_5 is not None
            and self.step_6_confirmed
        )
        assert case.is_ratified_for_execution() is all_six
        assert list(case.completed_steps) == list(ALGEDONIC_STEP_ORDER[: len(case.completed_steps)])


TestAlgedonicGovernanceMachine = pytest.mark.isai_scope(
    "isai://root#AlgedonicProtocol",
    "isai://root#NeuroVascularFundamental",
)(AlgedonicGovernanceMachine.TestCase)
