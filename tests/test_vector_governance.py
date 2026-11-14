"""Tri-Tier Verification Suite for `[VECTOR-GOVERNANCE]` (ISAI-NVF v1.1, VM1..VM8).

Tier V1 — Ledger algebra & operator-signal fidelity (deterministic invariants).
Tier V2 — Gate V pre-PR system health, drift detection & atomic apply ceremony.
Tier V3 — Generative Hypothesis state machine over arbitrary proposal lifecycles.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule
from pydantic import ValidationError

from _isai_sandbox import quiesce_staging

from isai.atomic_io import atomic_write_text
from isai.constitution import DEFAULT_BOUNDARY_IGNORE, GENESIS_CONSTITUTION
from isai.domain_models import MasterVectorHorizon, MasterVectorPillar, MasterVectorSpec
from isai.engine import (
    append_chronicle,
    audit_repository,
    build_clean_snapshot,
    load_module_attr,
    read_chronicle,
    sync_repository,
)
from isai.graph_index import load_repo_master_vector
from isai.health_checks import (
    DEVIATION_STATUS,
    NO_DEVIATION_STATUS,
    evaluate_gate_v,
)
from isai.protocol import ChronicleEvent, utc_now_iso
from isai.vector_ledger import (
    MAX_DEFERRALS,
    ConfirmationChannel,
    LedgerEventKind,
    MutationKind,
    OperatorSignal,
    ProposalStatus,
    RiskLevel,
    VectorAnchorKind,
    VectorMutationLedger,
    VectorMutationProposal,
    anchor_fingerprint,
    anchor_digest_profile,
    apply_confirmed_proposal,
    evaluate_ledger_deviations,
    fold_events,
    parse_operator_signal,
    render_proposal_checkboxes,
    resolve_anchor_text,
    vector_profile_digest,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def _clone_repo_to_tmp(tmp_path: Path) -> Path:
    dest = tmp_path / "isai_vector_sandbox"

    def _ignore(dir_str: str, names: list[str]) -> set[str]:
        rel_dir = Path(dir_str).resolve().relative_to(REPO_ROOT)
        ignored: set[str] = set()
        for name in names:
            cand = Path(name) if rel_dir == Path(".") else rel_dir / name
            if DEFAULT_BOUNDARY_IGNORE.is_ignored(cand):
                ignored.add(name)
        return ignored

    shutil.copytree(REPO_ROOT, dest, ignore=_ignore)
    quiesce_staging(dest)
    return dest


def _vector(root: Path) -> MasterVectorSpec:
    return load_repo_master_vector(root)


def _fresh_ledger(root: Path) -> VectorMutationLedger:
    """Reset a sandbox copy's ledger to a single BASELINE genesis event."""
    ledger = VectorMutationLedger(root)
    if ledger.path.is_file():
        ledger.path.unlink()
    ledger.initialize(_vector(root))
    return ledger


def _mk_proposal(vector: MasterVectorSpec, **overrides: object) -> VectorMutationProposal:
    kind = overrides.get("anchor_kind", VectorAnchorKind.CORE_OBJECTIVE)
    index = overrides.get("anchor_index", 0)
    base = dict(
        proposal_id="VMP-0001",
        anchor_kind=kind,
        anchor_index=index,
        anchor_label="Синтетическая цель теста",
        mutation_kind=MutationKind.EDIT,
        proposed_text="Уточнённая формулировка цели.",
        rationale=(
            "Обоснование достаточной глубины: эмпирические данные показывают системный разрыв, "
            "который данная правка закрывает на уровне ориентира."
        ),
        evidence_refs=("B-EXP-13", "tests/test_vector_governance.py"),
        risk_level=RiskLevel.LOW,
        expected_benefit="Устраняет неоднозначность целевого ориентира.",
        anchor_fingerprint=anchor_fingerprint(vector, kind, index),  # type: ignore[arg-type]
        base_vector_digest=vector_profile_digest(vector),
        created_at_utc=utc_now_iso(),
    )
    base.update(overrides)
    return VectorMutationProposal.model_validate(base)


# ============================================================================
# TIER V1: Operator-signal fidelity (VM3)
# ============================================================================


@pytest.mark.isai_scope("isai://root#MasterVector", "isai://root#VectorMutationLedger")
def test_operator_signal_detects_standalone_phrase_and_checked_boxes() -> None:
    """VM3: only standalone control lines and real checkboxes are ratification signals."""
    signal = parse_operator_signal(
        "- [x] VMP-0003\n"
        "- [ ] VMP-0004\n"
        "- [!] VMP-0005\n"
        "[x] VMP-0006 — согласен с обоснованием\n"
    )
    assert signal.checked_proposal_ids == ("VMP-0003", "VMP-0006")
    assert signal.rejected_proposal_ids == ("VMP-0005",)
    assert signal.phrase_confirmed is False

    phrase = parse_operator_signal("подтвердить вектор системы")
    assert phrase.phrase_confirmed is True
    assert phrase.checked_proposal_ids == ()

    with_marks = parse_operator_signal("**Подтвердить вектор системы!**\n")
    assert with_marks.phrase_confirmed is True
    assert with_marks.matched_line is not None

    yo_form = parse_operator_signal("Подтвердить вектор системы")
    assert yo_form.phrase_confirmed is True


@pytest.mark.isai_scope("isai://root#MasterVector")
def test_operator_signal_ignores_fenced_code_inline_code_and_quoted_prose() -> None:
    """Anti-self-confirmation reflex: documenting or quoting the protocol must never ratify it."""
    documentation = (
        "Правило требует, чтобы оператор написал `подтвердить вектор системы`.\n"
        "```markdown\n"
        "- [x] VMP-0001\n"
        "подтвердить вектор системы\n"
        "```\n"
        "Пример: \"подтвердить вектор системы\" — цитата внутри прозы.\n"
        "- В тексте выше встречается фраза: подтвердить вектор системы и это не сигнал.\n"
    )
    signal = parse_operator_signal(documentation)
    assert signal.phrase_confirmed is False
    assert signal.checked_proposal_ids == ()
    assert signal.suppressed_candidates >= 1


@pytest.mark.isai_scope("isai://root#MasterVector")
def test_rejected_box_wins_over_checked_box_for_same_proposal() -> None:
    """A proposal marked both ways in one prompt must not be silently confirmed."""
    signal = parse_operator_signal("- [x] VMP-0009\n- [!] VMP-0009\n")
    assert signal.checked_proposal_ids == ()
    assert signal.rejected_proposal_ids == ("VMP-0009",)


# ============================================================================
# TIER V1: Ledger algebra (VM1, VM2, VM4, VM5)
# ============================================================================


@pytest.mark.isai_scope("isai://root#VectorMutationLedger")
def test_proposal_binding_rejects_shallow_rationale_and_missing_evidence() -> None:
    """VM2: an unjustified checkbox mutation is structurally impossible to create."""
    vector = _vector(REPO_ROOT)
    with pytest.raises(ValidationError, match=">= 60 characters"):
        _mk_proposal(vector, rationale="Надо.")
    with pytest.raises(ValidationError, match="evidence reference"):
        _mk_proposal(vector, evidence_refs=())
    with pytest.raises(ValidationError, match="singular"):
        _mk_proposal(vector, anchor_kind=VectorAnchorKind.NORTH_STAR, anchor_index=3)
    with pytest.raises(ValidationError):
        _mk_proposal(vector, proposal_id="PROP-1")


@pytest.mark.isai_scope("isai://root#VectorMutationLedger")
def test_ledger_fold_blocks_apply_without_confirm_and_broken_digest_chain(tmp_path: Path) -> None:
    """VM4: Apply-Without-Confirm and non-contiguous digest chains are fatal at fold time."""
    vector = _vector(REPO_ROOT)
    root = tmp_path / "ledger_math"
    root.mkdir()
    ledger = VectorMutationLedger(root)
    ledger.initialize(vector)
    proposal = _mk_proposal(vector)
    ledger.propose(proposal)

    with pytest.raises(ValueError, match="Apply-Without-Confirm"):
        ledger.append(
            kind=LedgerEventKind.APPLIED,
            channel=ConfirmationChannel.CHECKBOX,
            proposal_id=proposal.proposal_id,
            vector_digest_before=vector_profile_digest(vector),
            vector_digest_after="a" * 64,
            chronicle_tx_id="TX-9999",
        )

    # Confirmed proposals cannot be re-confirmed (idempotency guard).
    ledger.confirm(proposal.proposal_id)
    with pytest.raises(ValueError, match="Cannot confirm"):
        ledger.confirm(proposal.proposal_id)

    # A proposal from another base digest cannot be injected into a fresh chain.
    other = _vector(REPO_ROOT)
    stale = _mk_proposal(other, proposal_id="VMP-0002", base_vector_digest="b" * 64)
    with pytest.raises(ValueError, match="declares base digest"):
        ledger.propose(stale)

    # Non-monotonic sequence numbers are rejected.
    events = ledger.read_events()
    broken = events[-1].model_copy(update={"seq": 99})
    with pytest.raises(ValueError, match="Non-monotonic"):
        fold_events([*events[:-1], broken])


@pytest.mark.isai_scope("isai://root#VectorMutationLedger")
def test_deferral_decay_expires_proposals_after_two_windows(tmp_path: Path) -> None:
    """VM5: a proposal deferred twice expires and must return with fresh evidence."""
    vector = _vector(REPO_ROOT)
    root = tmp_path / "decay"
    root.mkdir()
    ledger = VectorMutationLedger(root)
    ledger.initialize(vector)
    ledger.propose(_mk_proposal(vector))

    first = ledger.ingest_operator_signal(
        OperatorSignal(phrase_confirmed=True), vector, note="window 1"
    )
    assert first["reaffirmed"] is True
    assert first["deferred"] == ["VMP-0001"]
    assert first["expired"] == []
    assert ledger.state().status_of("VMP-0001") == ProposalStatus.PENDING

    second = ledger.ingest_operator_signal(
        OperatorSignal(phrase_confirmed=True), vector, note="window 2"
    )
    assert second["deferred"] == ["VMP-0001"]
    assert second["expired"] == ["VMP-0001"]
    assert ledger.state().status_of("VMP-0001") == ProposalStatus.EXPIRED
    assert ledger.state().deferrals["VMP-0001"] == MAX_DEFERRALS


@pytest.mark.isai_scope("isai://root#VectorMutationLedger")
def test_phrase_ratification_defers_but_never_blanket_confirms(tmp_path: Path) -> None:
    """VM3: 'подтвердить вектор системы' ratifies the vector, it does not consent to mutations."""
    vector = _vector(REPO_ROOT)
    root = tmp_path / "phrase_only"
    root.mkdir()
    ledger = VectorMutationLedger(root)
    ledger.initialize(vector)
    ledger.propose(_mk_proposal(vector))

    result = ledger.ingest_operator_signal(OperatorSignal(phrase_confirmed=True), vector)
    state = ledger.state()
    assert result["confirmed"] == []
    assert state.status_of("VMP-0001") == ProposalStatus.PENDING
    assert state.last_reaffirmed_digest == vector_profile_digest(vector)

    # A checkbox in the SAME prompt takes precedence: no blanket deferral, and the ratified
    # mutation is materialised atomically (never left dangling as an un-auditable wedge).
    ledger.propose(_mk_proposal(vector, proposal_id="VMP-0002"))
    mixed = ledger.ingest_operator_signal(
        OperatorSignal(phrase_confirmed=True, checked_proposal_ids=("VMP-0001",)), vector
    )
    assert mixed["confirmed"] == ["VMP-0001"]
    assert mixed["reaffirmed"] is False
    state = ledger.state()
    assert state.status_of("VMP-0001") == ProposalStatus.APPLIED
    # The ledger is internally consistent against the vector it actually produced.
    assert evaluate_ledger_deviations(state, _vector(ledger.repo_root)) == []


@pytest.mark.isai_scope("isai://root#VectorMutationLedger")
def test_checkbox_block_renders_informed_consent_evidence() -> None:
    """VM2/VM3: the operator must see anchor, rationale, exact text and evidence digests."""
    vector = _vector(REPO_ROOT)
    proposal = _mk_proposal(vector)
    block = render_proposal_checkboxes((proposal,))
    assert "- [ ] **VMP-0001** `EDIT` CORE_OBJECTIVE[0]" in block
    assert proposal.rationale in block
    assert proposal.anchor_fingerprint[:12] in block
    assert proposal.base_vector_digest[:12] in block
    assert "подтвердить вектор системы" in block
    assert render_proposal_checkboxes(()) == ""


# ============================================================================
# TIER V2: Drift detection (VM6) and staleness (VM2)
# ============================================================================


@pytest.mark.isai_scope("isai://root#MasterVector", "isai://root#VectorMutationLedger")
def test_unconfirmed_vector_drift_is_critical_deviation(tmp_path: Path) -> None:
    """VM6: editing the vector without a confirmed+applied proposal must fail both ledger and audit."""
    sandbox = _clone_repo_to_tmp(tmp_path)
    vector = _vector(sandbox)
    ledger = _fresh_ledger(sandbox)
    assert evaluate_ledger_deviations(ledger.state(), vector) == []

    drift = _vector(sandbox).model_copy(update={"version": "9.9.9"})
    deviations = evaluate_ledger_deviations(ledger.state(), drift)
    codes = {d.code for d in deviations if d.severity == "CRITICAL"}
    assert "UNCONFIRMED_VECTOR_DRIFT" in codes

    # And the live repository audit rejects a hand-edited vector.py that the ledger never saw.
    vec_py = sandbox / ".isai" / "vector.py"
    atomic_write_text(
        vec_py,
        vec_py.read_text(encoding="utf-8").replace('version="1.2.5"', 'version="1.2.6"'),
    )
    sync_repository(sandbox)
    report = audit_repository(sandbox, require_clean_snapshot=False)
    codes_live = {i.code for i in report.issues}
    assert "VECTOR_DRIFT_UNCONFIRMED" in codes_live
    assert report.valid is False


@pytest.mark.isai_scope("isai://root#MasterVector")
def test_stale_anchor_proposal_cannot_be_applied(tmp_path: Path) -> None:
    """VM2: after an applied mutation shifts indices, an old proposal fingerprint must be stale."""
    sandbox = _clone_repo_to_tmp(tmp_path)
    vector = _vector(sandbox)
    ledger = _fresh_ledger(sandbox)
    ledger.propose(_mk_proposal(vector, anchor_kind=VectorAnchorKind.ANTI_GOAL, anchor_index=0))

    shifted = vector.model_copy(
        update={"anti_goals": ("Новая цель-заглушка в начале списка.", *vector.anti_goals)}
    )
    deviations = evaluate_ledger_deviations(ledger.state(), shifted)
    assert any(d.code == "STALE_PROPOSAL_ANCHOR" for d in deviations)

    # An unconfirmed proposal can never be applied, stale or not.
    unconfirmed = apply_confirmed_proposal(
        sandbox, "VMP-0001", shifted, summary="attempt unconfirmed apply"
    )
    assert unconfirmed.applied is False
    assert unconfirmed.reason is not None and "Apply-Without-Confirm" in unconfirmed.reason

    # Even when confirmed, the ceremony refuses to materialise a stale anchor: it re-derives the
    # mutation from the *live* vector, so the fingerprint check must be performed against a vector
    # whose prefix was shifted (simulating a foreign change inside the addressed sequence).
    ledger.confirm("VMP-0001")
    shifted_prefix = vector.model_copy(
        update={
            "anti_goals": (
                "Чужое анти-правило, вклинившееся в начало списка.",
                *vector.anti_goals,
            )
        }
    )
    outcome = apply_confirmed_proposal(sandbox, "VMP-0001", shifted_prefix, summary="stale apply")
    assert outcome.applied is False
    assert outcome.reason is not None and (
        "Stale anchor" in outcome.reason or "Stale proposal" in outcome.reason
    )


@pytest.mark.isai_scope("isai://root#MasterVector", "isai://root#ChronicleLedger")
def test_apply_ceremony_is_atomic_and_version_bump_is_enforced(tmp_path: Path) -> None:
    """VM4: apply writes chronicle + ledger + snapshot + VISION in one transaction; version must bump."""
    sandbox = _clone_repo_to_tmp(tmp_path)
    vector = _vector(sandbox)
    ledger = _fresh_ledger(sandbox)
    ledger.propose(_mk_proposal(vector, anchor_kind=VectorAnchorKind.CORE_OBJECTIVE, anchor_index=0))
    ledger.confirm("VMP-0001")

    # The ceremony materialises the mutation itself (deterministic strategy), atomically.
    outcome = apply_confirmed_proposal(sandbox, "VMP-0001", summary="Test vector mutation.")
    assert outcome.applied is True, outcome.reason
    assert outcome.chronicle_tx_id is not None
    assert outcome.digest_after != outcome.digest_before

    applied_vector = _vector(sandbox)
    assert applied_vector.version != vector.version, "version must be bumped by the ceremony"
    assert applied_vector.core_objectives[0] == "Уточнённая формулировка цели."
    assert applied_vector.core_objectives[1:] == vector.core_objectives[1:]

    events = read_chronicle(sandbox)
    assert events[-1].operation == "MUTATE_VECTOR"
    assert events[-1].operator_approved is True
    assert "isai://root#VectorMutationLedger" in events[-1].touched_refs

    state = VectorMutationLedger(sandbox).state()
    assert state.status_of("VMP-0001") == ProposalStatus.APPLIED
    assert state.applied[-1]["after"] == vector_profile_digest(applied_vector)
    assert state.applied[-1]["before"] == vector_profile_digest(vector)

    report = audit_repository(sandbox)
    assert report.valid is True, f"Post-apply audit failed: {report.issues}"


@pytest.mark.isai_scope("isai://root#MasterVector")
def test_version_change_without_version_proposal_is_flagged(tmp_path: Path) -> None:
    """VM6: silent version bumps are a traceability loss even when anchors are untouched."""
    vector = _vector(REPO_ROOT)
    root = tmp_path / "version_guard"
    root.mkdir()
    ledger = VectorMutationLedger(root)
    ledger.initialize(vector)
    bumped = vector.model_copy(update={"version": "3.0.0"})
    codes = {d.code for d in evaluate_ledger_deviations(ledger.state(), bumped)}
    assert "UNCONFIRMED_VERSION_BUMP" in codes


# ============================================================================
# TIER V2: Gate V pre-PR system health (VM7)
# ============================================================================


@pytest.mark.isai_scope("isai://root#SystemHealthGate")
def test_gate_v_clean_repository_emits_evidence_bound_status() -> None:
    """Gate V on the live repo: no systemic deviation, machine-produced status with a digest."""
    report = evaluate_gate_v(REPO_ROOT)
    assert report.status == NO_DEVIATION_STATUS, [
        (r.check_id, r.message, r.evidence) for r in report.results if not r.passed
    ]
    assert report.critical_failures == ()
    assert len(report.evidence_digest) == 64
    assert report.status_token_ru == "системных отклонений не выявлено"
    assert {r.domain.value for r in report.results} == {
        "ROOT",
        "TASKS",
        "KNOWLEDGE",
        "UNIVERSE",
        "TESTS",
        "SYSTEM_SUBFOLDERS",
    }


@pytest.mark.isai_scope("isai://root#SystemHealthGate")
def test_gate_v_detects_unregistered_staging_and_orphan_leases(tmp_path: Path) -> None:
    """Gate V must catch an undeclared staging directory before it reaches a pull request."""
    sandbox = _clone_repo_to_tmp(tmp_path)
    rogue = sandbox / "tasks" / "TASK-ROGUE"
    rogue.mkdir()
    (rogue / "scratch.txt").write_text("unregistered staging", encoding="utf-8")

    report = evaluate_gate_v(sandbox)
    assert report.status == DEVIATION_STATUS
    assert "H-TASKS-06" in report.critical_failures


@pytest.mark.isai_scope("isai://root#SystemHealthGate", "isai://knowledge#EmpiricalCatalog")
def test_gate_v_detects_knowledge_registry_drift_and_dangling_anchors(tmp_path: Path) -> None:
    """Gate V must catch catalog drift (undocumented or dangling knowledge entries)."""
    sandbox = _clone_repo_to_tmp(tmp_path)
    from isai.domain_models import KnowledgeCatalogSpec, KnowledgeEntry

    catalog_py = sandbox / "knowledge" / ".isai" / "catalog.py"
    catalog = load_module_attr(catalog_py, "_gate_v_test_catalog", "KNOWLEDGE_CATALOG")
    assert isinstance(catalog, KnowledgeCatalogSpec)
    extra = KnowledgeEntry(
        entry_id="PAT_GHOST_REFERENCE",
        category="pattern",
        title="Призрачная запись",
        distilled_insight="Ссылается на несуществующий символ, чтобы проверить Gate V.",
        applicability_tags=("gate_v",),
        related_node_ref="isai://root#GhostSymbol",
        origin_tx_id=catalog.entries[0].origin_tx_id,
        verified_revision=1,
    )
    updated = catalog.upsert(extra)
    source = catalog_py.read_text(encoding="utf-8")
    rendered_entry = (
        "\n        KnowledgeEntry(\n"
        f"            entry_id={extra.entry_id!r},\n"
        f"            category={extra.category!r},\n"
        f"            title={extra.title!r},\n"
        f"            distilled_insight=(\n                {extra.distilled_insight!r}\n            ),\n"
        f"            applicability_tags={tuple(extra.applicability_tags)!r},\n"
        f"            related_node_ref={extra.related_node_ref!r},\n"
        f"            origin_tx_id={extra.origin_tx_id!r},\n"
        f"            verified_revision={extra.verified_revision!r},\n"
        "        ),\n"
    )
    final = source.replace("\n    ),\n)", rendered_entry + "    ),\n)")
    atomic_write_text(catalog_py, final)

    report = evaluate_gate_v(sandbox)
    assert report.status == DEVIATION_STATUS
    assert "H-KNOW-04" in report.critical_failures
    assert "H-KNOW-05" in report.critical_failures
    assert updated.entries


@pytest.mark.isai_scope("isai://root#SystemHealthGate", "isai://knowledge")
def test_gate_v_detects_universe_purity_breach(tmp_path: Path) -> None:
    """Implementation leaking into the knowledge universe must fail Gate V."""
    sandbox = _clone_repo_to_tmp(tmp_path)
    (sandbox / "knowledge" / "leaky_module.py").write_text(
        "import os\n\ndef run():\n    return open('/etc/passwd').read()\n", encoding="utf-8"
    )
    report = evaluate_gate_v(sandbox)
    assert report.status == DEVIATION_STATUS
    assert "H-UNI-01" in report.critical_failures


@pytest.mark.isai_scope("isai://root#SystemHealthGate", "isai://tests")
def test_gate_v_detects_unmarked_tests_and_missing_gate_check(tmp_path: Path) -> None:
    """Every test must carry an isai_scope marker, otherwise VAET test selection silently rots."""
    sandbox = _clone_repo_to_tmp(tmp_path)
    (sandbox / "tests" / "test_unmarked_rogue.py").write_text(
        "def test_without_scope_marker():\n    assert True\n", encoding="utf-8"
    )
    report = evaluate_gate_v(sandbox)
    assert report.status == DEVIATION_STATUS
    assert "H-TEST-01" in report.critical_failures
    assert "H-TEST-02" in report.critical_failures


@pytest.mark.isai_scope("isai://root#SystemHealthGate", "isai://root#GenesisKernel")
def test_gate_v_detects_genesis_tamper_and_torn_artifacts(tmp_path: Path) -> None:
    """Gate V is the last line of defence: IL-0 corruption and torn writes must block the PR."""
    sandbox = _clone_repo_to_tmp(tmp_path)
    raw = bytearray((sandbox / "README.md").read_bytes())
    raw[5] = ord("Z")
    (sandbox / "README.md").write_bytes(bytes(raw))
    (sandbox / ".isai" / ".isai_tmp_777_vision").write_text("partial", encoding="utf-8")

    report = evaluate_gate_v(sandbox)
    assert report.status == DEVIATION_STATUS
    assert "H-ROOT-01" in report.critical_failures
    assert "H-ROOT-06" in report.critical_failures


@pytest.mark.isai_scope("isai://root#SystemHealthGate")
def test_gate_v_is_read_only() -> None:
    """Gate V must never mutate the repository it inspects."""
    before = {
        p: p.read_bytes()
        for p in sorted(REPO_ROOT.rglob("*"))
        if p.is_file() and not DEFAULT_BOUNDARY_IGNORE.is_ignored(p.relative_to(REPO_ROOT))
    }
    evaluate_gate_v(REPO_ROOT)
    after = {
        p: p.read_bytes()
        for p in sorted(REPO_ROOT.rglob("*"))
        if p.is_file() and not DEFAULT_BOUNDARY_IGNORE.is_ignored(p.relative_to(REPO_ROOT))
    }
    assert before == after


# ============================================================================
# TIER V2: NVF v1.1 integration & RSoC delivery
# ============================================================================


@pytest.mark.isai_scope("isai://root#NeuroVascularFundamental", "isai://root#RSoCCompiler")
def test_nvf_v11_vector_governance_is_ratified_and_anchored_in_rsoc() -> None:
    """IL-1C v1.1 must be Operator-ratified and deliver VM1..VM8 in both Primacy and Recency slots."""
    from isai.engine import compile_rsoc
    from isai.graph_index import load_repo_nvf

    nvf = load_repo_nvf(REPO_ROOT)
    assert nvf.frame_id == "ISAI-NVF/1.1"
    assert nvf.version == "1.1"
    assert "VectorMutation=CHECKBOX_RATIFIED_LEDGER_ONLY" in nvf.mutability_law
    dsl = nvf.render_dsl()
    for rule in ("VM1.SingleSource:", "VM2.ProposalBinding:", "VM3.SignalSource:",
                 "VM4.ApplyCeremony:", "VM5.DeferralDecay:", "VM6.DriftDetect:",
                 "VM7.GateV-PrePR:", "VM8.TurnBoundary:"):
        assert rule in dsl

    events = read_chronicle(REPO_ROOT)
    ratify = [e for e in events if e.operation == "RATIFY_FUNDAMENTAL"]
    assert ratify and ratify[-1].ratified_nvf_digest == nvf.dsl_sha256()

    packet = compile_rsoc(REPO_ROOT, "isai://root")
    head = packet["enforced_neuro_vascular_frame"]
    tail = packet["terminal_execution_guard"]
    assert head["frame_id"] == "ISAI-NVF/1.1"
    assert len(head["vector_governance"]) == 8
    assert tail["vector_mutation_law"] == nvf.mutability_law
    assert list(packet.keys())[-1] == "terminal_execution_guard"


@pytest.mark.isai_scope("isai://root#NeuroVascularFundamental")
def test_nvf_v11_amendment_is_blocked_without_operator_ratification(tmp_path: Path) -> None:
    """The IL-1C lock still holds after the amendment: any further silent edit is fatal."""
    sandbox = _clone_repo_to_tmp(tmp_path)
    nvf_py = sandbox / ".isai" / "neuro_vascular.py"
    atomic_write_text(
        nvf_py,
        nvf_py.read_text(encoding="utf-8").replace("Deferrals>=2", "Deferrals>=9"),
    )
    sync_repository(sandbox)
    report = audit_repository(sandbox, require_clean_snapshot=False)
    codes = {i.code for i in report.issues}
    assert "UNRATIFIED_FUNDAMENTAL_MUTATION" in codes


@pytest.mark.isai_scope("isai://root#VectorMutationLedger", "isai://root#ChronicleLedger")
def test_live_ledger_is_anchored_and_chronicle_is_monotonic() -> None:
    """The live repository must carry an anchored ledger whose head matches the live vector."""
    vector = _vector(REPO_ROOT)
    ledger = VectorMutationLedger(REPO_ROOT)
    assert ledger.path.is_file(), "live vector ledger missing"
    state = ledger.state()
    assert state.baseline_digest is not None
    head = state.applied[-1]["after"] if state.applied else state.baseline_digest
    live = vector_profile_digest(vector)
    # Either the ledger head equals the live vector, or exactly one confirmed mutation awaits apply.
    if head != live:
        assert [p.proposal_id for p in state.confirmed()], (
            "Live vector drifted from the ledger head without a confirmed pending apply."
        )
    assert [d for d in evaluate_ledger_deviations(state, vector) if d.severity == "CRITICAL"] == []

    events = read_chronicle(REPO_ROOT)
    assert [e.revision for e in events] == list(range(1, len(events) + 1))
    assert genesis_ok(REPO_ROOT)


def genesis_ok(root: Path) -> bool:
    return GENESIS_CONSTITUTION.verify_genesis_header(root / "README.md").valid


# ============================================================================
# TIER V3: Generative state machine over the vector governance lifecycle
# ============================================================================


class VectorGovernanceMachine(RuleBasedStateMachine):
    """Generative lifecycle: propose -> confirm/reject/defer -> apply, with hard invariants."""

    def __init__(self) -> None:
        super().__init__()
        self.vector = _vector(REPO_ROOT)
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.ledger = VectorMutationLedger(self.root)
        self.ledger.initialize(self.vector)
        self.proposals: list[str] = []
        self.confirmed: set[str] = set()
        self.applied: set[str] = set()
        self.rejected: set[str] = set()
        self._live = self.vector

    def teardown(self) -> None:
        self._tmp.cleanup()

    @rule()
    def propose_new(self) -> None:
        state = self.ledger.state()
        pid = state.next_proposal_id()
        # Bind the proposal to the append sentinel of the anti-goal sequence.
        proposal = _mk_proposal(
            self._live,
            proposal_id=pid,
            anchor_kind=VectorAnchorKind.ANTI_GOAL,
            anchor_index=len(self._live.anti_goals),
            mutation_kind=MutationKind.ADD,
            proposed_text=f"Сгенерированное анти-правило #{len(self.proposals) + 1}",
        )
        self.ledger.propose(proposal)
        self.proposals.append(pid)

    @rule(pid=st.sampled_from(["VMP-0001", "VMP-0002", "VMP-0003", "VMP-0004"]))
    def try_confirm(self, pid: str) -> None:
        state = self.ledger.state()
        if state.status_of(pid) == ProposalStatus.PENDING:
            self.ledger.confirm(pid)
            self.confirmed.add(pid)

    @rule(pid=st.sampled_from(["VMP-0001", "VMP-0002", "VMP-0003", "VMP-0004"]))
    def try_reject(self, pid: str) -> None:
        state = self.ledger.state()
        if state.status_of(pid) == ProposalStatus.PENDING:
            self.ledger.reject(pid)
            self.rejected.add(pid)

    @rule()
    def reaffirm_window(self) -> None:
        self.ledger.ingest_operator_signal(OperatorSignal(phrase_confirmed=True), self._live)

    @rule()
    def apply_confirmed(self) -> None:
        available = sorted(self.confirmed - self.applied)
        if not available:
            return
        pid = available[0]
        outcome = apply_confirmed_proposal(
            self.root, pid, summary=f"generative apply {pid}"
        )
        assert outcome.applied is True, outcome.reason
        self.applied.add(pid)
        self._live = _vector(self.root)

    @invariant()
    def statuses_are_terminal_or_pending(self) -> None:
        state = self.ledger.state()
        for pid, status in state.statuses.items():
            assert status in {
                ProposalStatus.PENDING,
                ProposalStatus.CONFIRMED,
                ProposalStatus.APPLIED,
                ProposalStatus.REJECTED,
                ProposalStatus.EXPIRED,
                ProposalStatus.SUPERSEDED,
            }, f"{pid} has impossible status {status}"

    @invariant()
    def applied_mutations_form_a_contiguous_chain(self) -> None:
        state = self.ledger.state()
        previous = state.baseline_digest
        for item in state.applied:
            assert item["before"] == previous, "digest chain broken by the state machine"
            previous = item["after"]
        assert previous == vector_profile_digest(self._live)

    @invariant()
    def rejected_or_pending_never_applied(self) -> None:
        state = self.ledger.state()
        for pid in self.applied:
            assert pid not in self.rejected
            assert state.status_of(pid) == ProposalStatus.APPLIED
        for pid in self.rejected:
            assert pid not in self.applied

    @invariant()
    def deferrals_never_exceed_policy(self) -> None:
        state = self.ledger.state()
        for pid, count in state.deferrals.items():
            assert count <= MAX_DEFERRALS + 1, f"{pid} exceeded deferral policy: {count}"


TEST_GOVERNANCE_MACHINE = VectorGovernanceMachine.TestCase
TEST_GOVERNANCE_MACHINE.settings = settings(
    max_examples=40,
    deadline=None,
    derandomize=True,
    database=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
)
