"""Tri-Tier Verification Suite for `[VECTOR-GOVERNANCE]` (ISAI-NVF v1.2, VM1..VM8).

Tier V1 — Ledger algebra & numbered-ratification fidelity (deterministic invariants).
Tier V2 — Gate V pre-PR system health, drift detection & atomic apply ceremony.
Tier V3 — Generative Hypothesis state machine over arbitrary numbered-ratification lifecycles.
"""

from __future__ import annotations

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
    CONFIRM_TASK_ANCHOR_FORMS,
    LEGACY_PHRASE_FORMS,
    MAX_BATCH_SIZE,
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
    anchor_digest_profile,
    anchor_fingerprint,
    apply_confirmed_batch,
    apply_confirmed_proposal,
    evaluate_ledger_deviations,
    fold_events,
    parse_operator_signal,
    render_numbered_mutations,
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


def _task(*ordinals: int) -> OperatorSignal:
    """Build the operator signal of a real confirmation task with the given numbers."""
    anchor = CONFIRM_TASK_ANCHOR_FORMS[0]
    text = anchor if not ordinals else f"{anchor}: " + ", ".join(str(n) for n in ordinals)
    signal = parse_operator_signal(text)
    assert signal.task_present is True
    return signal


def _open_batch(ledger: VectorMutationLedger, proposal_ids: tuple[str, ...]) -> str:
    state = ledger.state()
    event = ledger.open_batch(proposal_ids, base_vector_digest=state.ledger_head() or "")
    assert event.batch is not None
    return event.batch.batch_id


# ============================================================================
# TIER V1: Numbered ratification protocol (VM3 / VM4)
# ============================================================================


@pytest.mark.isai_scope("isai://root#MasterVector", "isai://root#VectorMutationLedger")
def test_confirmation_task_requires_the_exact_anchor_and_its_numbers() -> None:
    """VM3: only the separate explicit task carries consent, and only its numbers name mutations."""
    assert parse_operator_signal("продолжаем работу").task_present is False

    bare = parse_operator_signal("подтвердить мутации вектора системы")
    assert bare.task_present is True
    assert bare.selected_ordinals == ()
    assert bare.confirms_any_mutation is False

    numbered = parse_operator_signal("подтвердить мутации вектора системы: 1, 3")
    assert numbered.task_present is True
    assert numbered.selected_ordinals == (1, 3)
    assert numbered.confirms_any_mutation is True

    decorated = parse_operator_signal("**Подтвердить мутации вектора системы** — № 1 и 3\n")
    assert decorated.selected_ordinals == (1, 3)
    assert parse_operator_signal("- подтвердить мутации вектора системы (2)").selected_ordinals == (2,)
    assert parse_operator_signal("подтвердить мутации вектора системы 1 и 3").selected_ordinals == (1, 3)
    assert parse_operator_signal("Подтвердить мутации вектора системы.").task_present is True


@pytest.mark.isai_scope("isai://root#MasterVector")
def test_versions_years_and_prose_never_become_mutation_numbers() -> None:
    """A version bump, a year or a percentage must never be read as a mutation ordinal."""
    for text in (
        "подтвердить мутации вектора системы: 1.2.5",
        "подтвердить мутации вектора системы: 2026",
        "подтвердить мутации вектора системы: 30% уверенности",
        "подтвердить мутации вектора системы: 1 promt = 1 задача",
    ):
        signal = parse_operator_signal(text)
        assert signal.task_present is True
        assert signal.selected_ordinals == (), text
        assert not signal.confirms_any_mutation

    out_of_range = parse_operator_signal("подтвердить мутации вектора системы: 1 2 3 9")
    assert out_of_range.selected_ordinals == (1, 2, 3)
    assert out_of_range.unknown_ordinal_tokens == (9,)


@pytest.mark.isai_scope("isai://root#MasterVector")
def test_quoting_or_documenting_the_task_never_ratifies_it() -> None:
    """Anti-self-confirmation reflex: fences, inline code, blockquotes and prose are inert."""
    documentation = (
        "Правило требует отдельной задачи `подтвердить мутации вектора системы: 1`.\n"
        "```markdown\n"
        "подтвердить мутации вектора системы: 1\n"
        "```\n"
        "> подтвердить мутации вектора системы: 1\n"
        'Пример: "подтвердить мутации вектора системы: 1" — цитата внутри прозы.\n'
        "Please подтвердить мутации вектора системы: 1\n"
    )
    signal = parse_operator_signal(documentation)
    assert signal.task_present is False
    assert signal.selected_ordinals == ()
    assert signal.suppressed_candidates >= 1


@pytest.mark.isai_scope("isai://root#MasterVector")
def test_superseded_phrase_is_recognised_only_to_be_refused(tmp_path: Path) -> None:
    """The retired one-word phrase must never silently ratify a version or a mutation."""
    for phrase in LEGACY_PHRASE_FORMS:
        signal = parse_operator_signal(phrase)
        assert signal.task_present is False
        assert signal.legacy_phrase_present is True

    vector = _vector(REPO_ROOT)
    root = tmp_path / "legacy"
    root.mkdir()
    ledger = VectorMutationLedger(root)
    ledger.initialize(vector)
    result = ledger.ingest_operator_signal(parse_operator_signal(LEGACY_PHRASE_FORMS[0]), vector)
    assert result["legacy_phrase_refused"] is True
    assert result["version_reaffirmed"] is False
    assert result["confirmed"] == [] and result["applied"] == []
    assert ledger.state().last_reaffirmed_digest == vector_profile_digest(vector)


@pytest.mark.isai_scope("isai://root#VectorMutationLedger")
def test_absent_task_keeps_the_last_confirmed_version_and_changes_nothing(tmp_path: Path) -> None:
    """No confirmation task => the current confirmed version stays in force; nothing happens."""
    vector = _vector(REPO_ROOT)
    root = tmp_path / "no_task"
    root.mkdir()
    ledger = VectorMutationLedger(root)
    ledger.initialize(vector)
    ledger.propose(_mk_proposal(vector))

    before = ledger.read_events()
    result = ledger.ingest_operator_signal(parse_operator_signal("обычный рабочий промпт"), vector)
    assert result["task_present"] is False
    assert ledger.read_events() == before, "an unnumbered prompt must not touch the ledger"
    assert ledger.state().confirmed_version_digest() == vector_profile_digest(vector)


@pytest.mark.isai_scope("isai://root#VectorMutationLedger")
def test_task_without_numbers_confirms_the_version_without_implementing(tmp_path: Path) -> None:
    """VM4: a confirmation task with no numbers ratifies the version and applies nothing."""
    vector = _vector(REPO_ROOT)
    root = tmp_path / "version_only"
    root.mkdir()
    ledger = VectorMutationLedger(root)
    ledger.initialize(vector)
    ledger.propose(_mk_proposal(vector))
    batch_id = _open_batch(ledger, ("VMP-0001",))

    result = ledger.ingest_operator_signal(_task(), vector)
    state = ledger.state()
    assert result["version_reaffirmed"] is True
    assert result["confirmed"] == [] and result["applied"] == []
    assert state.status_of("VMP-0001") == ProposalStatus.PENDING
    assert state.last_reaffirmed_digest == vector_profile_digest(vector)
    assert state.deferrals["VMP-0001"] == 1, "an offered-but-unselected mutation decays (VM5)"
    assert batch_id == "VMB-0001"


@pytest.mark.isai_scope("isai://root#VectorMutationLedger")
def test_numbers_ratify_exactly_the_selected_mutations_atomically(tmp_path: Path) -> None:
    """VM4: the numbered set is composed and committed as one atomic ceremony."""
    sandbox = _clone_repo_to_tmp(tmp_path)
    vector = _vector(sandbox)
    ledger = _fresh_ledger(sandbox)
    sentinel = len(vector.core_objectives)
    for pid in ("VMP-0001", "VMP-0002", "VMP-0003"):
        ledger.propose(
            _mk_proposal(
                vector,
                proposal_id=pid,
                anchor_kind=VectorAnchorKind.CORE_OBJECTIVE,
                anchor_index=sentinel,
                mutation_kind=MutationKind.ADD,
                proposed_text=f"Добавленная цель {pid}",
            )
        )
    _open_batch(ledger, ("VMP-0001", "VMP-0002", "VMP-0003"))

    result = ledger.ingest_operator_signal(_task(1, 3), _vector(sandbox))
    assert result["confirmed"] == ["VMP-0001", "VMP-0003"]
    assert result["applied"] == ["VMP-0001", "VMP-0003"]
    # VMP-0002 was offered but not numbered, and it targeted the *same append sentinel* as the two
    # mutations the Operator did select. Once they land, that sentinel no longer exists, so the
    # proposal can never be materialised: the atomic apply retires it in the same transaction
    # (VM5/VM6 hygiene) rather than leaving an un-appliable pending proposal behind. The Operator's
    # unselected work is not silent: it is superseded, recorded, and must be re-proposed against
    # the live vector with fresh evidence.
    assert "VMP-0002" not in result["applied"]
    assert "VMP-0002" not in result["confirmed"]
    assert result["superseded"] == ["VMP-0002"]

    applied = _vector(sandbox)
    # Both numbered mutations landed on the SAME anchor sequence in one transaction.
    assert applied.core_objectives[sentinel] == "Добавленная цель VMP-0001"
    assert applied.core_objectives[sentinel + 1] == "Добавленная цель VMP-0003"
    assert len(applied.core_objectives) == sentinel + 2

    state = ledger.state()
    assert state.status_of("VMP-0001") == ProposalStatus.APPLIED
    assert state.status_of("VMP-0003") == ProposalStatus.APPLIED
    assert state.status_of("VMP-0002") == ProposalStatus.SUPERSEDED
    assert state.ledger_head() == vector_profile_digest(applied)
    codes = {d.code for d in evaluate_ledger_deviations(state, applied)}
    assert codes == {"UNRELEASED_RATIFIED_MUTATION"}, codes


@pytest.mark.isai_scope("isai://root#VectorMutationLedger")
def test_ordinal_outside_the_batch_is_refused_not_ignored(tmp_path: Path) -> None:
    """An ordinal the request never offered cannot be ratified by guessing."""
    vector = _vector(REPO_ROOT)
    root = tmp_path / "out_of_range"
    root.mkdir()
    ledger = VectorMutationLedger(root)
    ledger.initialize(vector)
    ledger.propose(_mk_proposal(vector))
    _open_batch(ledger, ("VMP-0001",))

    result = ledger.ingest_operator_signal(_task(2), vector)
    assert result["confirmed"] == []
    # The batch offered exactly one mutation, so ordinal 2 names nothing at all: it is refused as
    # unknown, never reinterpreted as "the nearest mutation" and never silently ignored.
    assert result["unknown_ordinals"] == [2]
    assert result["selected_ordinals"] == []
    assert ledger.state().status_of("VMP-0001") == ProposalStatus.PENDING


@pytest.mark.isai_scope("isai://root#VectorMutationLedger")
def test_batch_is_bound_to_the_live_vector_head(tmp_path: Path) -> None:
    """A numbered request is numbered against a digest; a stale request must not be ratified."""
    sandbox = _clone_repo_to_tmp(tmp_path)
    vector = _vector(sandbox)
    ledger = _fresh_ledger(sandbox)
    ledger.propose(_mk_proposal(vector))
    batch_id = _open_batch(ledger, ("VMP-0001",))

    # A second mutation is applied after the request was numbered.
    ledger.propose(_mk_proposal(vector, proposal_id="VMP-0002", anchor_index=1))
    ledger.confirm("VMP-0002", selected_ordinals=(2,))
    outcome = apply_confirmed_proposal(sandbox, "VMP-0002", summary="shift the vector head")
    assert outcome.applied is True, outcome.reason

    result = ledger.ingest_operator_signal(_task(1), _vector(sandbox))
    assert result["confirmed"] == []
    assert result["stale_ordinals"] == [1]
    state = ledger.state()
    assert any(
        d.code == "STALE_NUMBERED_BATCH" for d in evaluate_ledger_deviations(state, _vector(sandbox))
    )
    assert batch_id == "VMB-0001"


@pytest.mark.isai_scope("isai://root#VectorMutationLedger")
def test_seal_makes_the_last_pull_request_the_confirmed_version(tmp_path: Path) -> None:
    """VM5: applied mutations are unreleased until a SEALED record pins the last-PR version."""
    sandbox = _clone_repo_to_tmp(tmp_path)
    vector = _vector(sandbox)
    ledger = _fresh_ledger(sandbox)
    ledger.propose(_mk_proposal(vector))
    _open_batch(ledger, ("VMP-0001",))
    ledger.ingest_operator_signal(_task(1), _vector(sandbox))

    state = ledger.state()
    assert state.confirmed_version_digest() == vector_profile_digest(vector)
    assert [i["proposal_id"] for i in state.unreleased_mutations()] == ["VMP-0001"]
    assert "UNRELEASED_RATIFIED_MUTATION" in {
        d.code for d in evaluate_ledger_deviations(state, _vector(sandbox))
    }

    seal = ledger.seal(_vector(sandbox), pr_ref="#3")
    state = ledger.state()
    assert seal.kind == LedgerEventKind.SEALED
    assert state.last_sealed_pr_ref == "#3"
    assert state.last_sealed_version == _vector(sandbox).version
    assert state.confirmed_version_digest() == vector_profile_digest(_vector(sandbox))
    assert state.unreleased_mutations() == ()
    assert evaluate_ledger_deviations(state, _vector(sandbox)) == []
    assert audit_repository(sandbox).valid is True


@pytest.mark.isai_scope("isai://root#VectorMutationLedger")
def test_deferral_decay_expires_proposals_after_two_windows(tmp_path: Path) -> None:
    """VM5: a proposal deferred twice expires and must return with fresh evidence."""
    vector = _vector(REPO_ROOT)
    root = tmp_path / "decay"
    root.mkdir()
    ledger = VectorMutationLedger(root)
    ledger.initialize(vector)
    ledger.propose(_mk_proposal(vector))
    _open_batch(ledger, ("VMP-0001",))

    first = ledger.ingest_operator_signal(_task(), vector, note="window 1")
    assert first["version_reaffirmed"] is True
    assert first["deferred"] == ["VMP-0001"]
    assert first["expired"] == []
    assert ledger.state().status_of("VMP-0001") == ProposalStatus.PENDING

    second = ledger.ingest_operator_signal(_task(), vector, note="window 2")
    assert second["deferred"] == ["VMP-0001"]
    assert second["expired"] == ["VMP-0001"]
    assert ledger.state().status_of("VMP-0001") == ProposalStatus.EXPIRED
    assert ledger.state().deferrals["VMP-0001"] == MAX_DEFERRALS


@pytest.mark.isai_scope("isai://root#VectorMutationLedger")
def test_numbered_request_renders_ordinals_justifications_and_the_task_anchor() -> None:
    """VM2/VM4: the Operator must see number, anchor, rationale, exact text and evidence digests."""
    from isai.vector_ledger import VectorMutationBatch

    vector = _vector(REPO_ROOT)
    proposal = _mk_proposal(vector)
    batch = VectorMutationBatch(
        batch_id="VMB-0001",
        base_vector_digest=vector_profile_digest(vector),
        proposal_ids=("VMP-0001",),
        created_at_utc=utc_now_iso(),
    )
    block = render_numbered_mutations((proposal,), batch=batch)
    assert "1. **VMP-0001** `EDIT` CORE_OBJECTIVE[0]" in block
    assert proposal.rationale in block
    assert proposal.anchor_fingerprint[:12] in block
    assert proposal.base_vector_digest[:12] in block
    assert CONFIRM_TASK_ANCHOR_FORMS[0] in block
    assert "[ ]" not in block, "the numbered request offers no checkbox consent surface"
    assert render_numbered_mutations(()) == ""


# ============================================================================
# TIER V1: Ledger algebra (VM1, VM2, VM4, VM5)
# ============================================================================


@pytest.mark.isai_scope("isai://root#VectorMutationLedger")
def test_proposal_binding_rejects_shallow_rationale_and_missing_evidence() -> None:
    """VM2: an unjustified mutation is structurally impossible to create."""
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
            channel=ConfirmationChannel.OPERATOR_TASK,
            proposal_id=proposal.proposal_id,
            vector_digest_before=vector_profile_digest(vector),
            vector_digest_after="a" * 64,
            chronicle_tx_id="TX-9999",
        )

    # A confirmation without a selected ordinal is structurally impossible (VM4).
    with pytest.raises(ValueError, match="no selected ordinal"):
        ledger.confirm(proposal.proposal_id)

    # Confirmed proposals cannot be re-confirmed (idempotency guard).
    ledger.confirm(proposal.proposal_id, selected_ordinals=(1,))
    with pytest.raises(ValueError, match="Cannot confirm"):
        ledger.confirm(proposal.proposal_id, selected_ordinals=(1,))

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
    _open_batch(ledger, ("VMP-0001",))
    ledger.confirm("VMP-0001", selected_ordinals=(1,))
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
    _open_batch(ledger, ("VMP-0001",))
    ledger.confirm("VMP-0001", selected_ordinals=(1,))

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

    # VM5: an applied-but-unsealed mutation is *by design* an open deviation — the confirmed
    # version must be the version of the last pull request. The audit therefore refuses until the
    # Operator records the SEAL, and goes clean immediately after it.
    unsealed = audit_repository(sandbox)
    assert unsealed.valid is False
    assert {issue.code for issue in unsealed.issues} == {"VECTOR_LEDGER_INVALID"}

    VectorMutationLedger(sandbox).seal(_vector(sandbox), pr_ref="#TEST")
    report = audit_repository(sandbox)
    assert report.valid is True, f"Post-seal audit failed: {report.issues}"
    assert VectorMutationLedger(sandbox).state().status_of("VMP-0001") == ProposalStatus.APPLIED
    assert VectorMutationLedger(sandbox).state().last_sealed_pr_ref == "#TEST"


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
        # IL-1C v1.2: the text domain (`TE1..TE7` duties, H-TEXT-01..04) is part of Gate V.
        "TEXT",
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
# TIER V2: NVF v1.2 integration & RSoC delivery
# ============================================================================


@pytest.mark.isai_scope("isai://root#NeuroVascularFundamental", "isai://root#RSoCCompiler")
def test_nvf_v12_vector_governance_and_text_engineering_are_anchored_in_rsoc() -> None:
    """IL-1C v1.2 must be Operator-ratified and deliver VM1..VM8 + TE0..TE7 into the RSoC packet."""
    from isai.engine import compile_rsoc
    from isai.graph_index import load_repo_nvf

    nvf = load_repo_nvf(REPO_ROOT)
    assert nvf.frame_id == "ISAI-NVF/1.2"
    assert nvf.version == "1.2"
    assert "VectorMutation=NUMBERED_OPERATOR_TASK_LEDGER_ONLY" in nvf.mutability_law
    dsl = nvf.render_dsl()
    for rule in ("VM1.SingleSource:", "VM2.ProposalBinding:", "VM3.SignalSource:",
                 "VM4.NumberedRatification:", "VM5.ConfirmedBaseline&Decay:", "VM6.DriftDetect:",
                 "VM7.GateV-PrePR:", "VM8.TurnBoundary:"):
        assert rule in dsl
    # IL-1C v1.2 carries the text-engineering duty set (TE0..TE7) as a first-class amendment.
    for rule in ("TE0.LevelLaw:", "TE1.CarrierPurity:", "TE2.DLT-BPE:", "TE3.CommandTruth:",
                 "TE4.FrameLaw:", "TE5.SalienceOrder:", "TE6.ChronicleRegister:",
                 "TE7.VerifyCompile:"):
        assert rule in dsl

    events = read_chronicle(REPO_ROOT)
    ratify = [e for e in events if e.operation == "RATIFY_FUNDAMENTAL"]
    assert ratify and ratify[-1].ratified_nvf_digest == nvf.dsl_sha256()

    packet = compile_rsoc(REPO_ROOT, "isai://root")
    head = packet["enforced_neuro_vascular_frame"]
    tail = packet["terminal_execution_guard"]
    assert head["frame_id"] == "ISAI-NVF/1.2"
    assert len(head["vector_governance"]) == 8
    # The text-engineering circuit is delivered as its own RSoC section, right after the NVF frame.
    assert set(packet["enforced_text_engineering"]["duties"]) == {f"TE{i}" for i in range(8)}
    assert list(packet.keys()).index("enforced_text_engineering") > list(packet.keys()).index(
        "enforced_neuro_vascular_frame"
    )
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
    """
    Generative lifecycle of the numbered protocol: propose -> batch -> ratify by numbers.

    The machine outlaws the two historically observed wedge states: a CONFIRMED mutation that was
    never applied, and an applied batch that left the ledger head off the live vector.
    """

    def __init__(self) -> None:
        super().__init__()
        self.vector = _vector(REPO_ROOT)
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.ledger = VectorMutationLedger(self.root)
        self.ledger.initialize(self.vector)
        self.proposals: list[str] = []
        self.applied: set[str] = set()
        self._live = self.vector

    def teardown(self) -> None:
        self._tmp.cleanup()

    @rule()
    def propose_new(self) -> None:
        state = self.ledger.state()
        pid = state.next_proposal_id()
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

    @rule()
    def open_numbered_request(self) -> None:
        pending = self.ledger.state().pending()
        if not pending:
            return
        chosen = tuple(p.proposal_id for p in pending[:MAX_BATCH_SIZE])
        state = self.ledger.state()
        self.ledger.open_batch(chosen, base_vector_digest=state.ledger_head() or "")

    @rule(ordinals=st.lists(st.integers(min_value=1, max_value=MAX_BATCH_SIZE), max_size=3))
    def ratify_by_numbers(self, ordinals: list[int]) -> None:
        batch = self.ledger.state().latest_batch()
        signal = _task(*ordinals) if ordinals else _task()
        result = self.ledger.ingest_operator_signal(signal, self._live)
        if result["applied"]:
            self._live = _vector(self.root)
            self.applied.update(result["applied"])
        # Every reported application must be visible in the live vector's ledger head.
        assert self.ledger.state().ledger_head() == vector_profile_digest(self._live)
        assert not self.ledger.state().confirmed(), "a ratified mutation was left unapplied (wedge)"
        if batch is not None and not ordinals:
            assert result["version_reaffirmed"] is True

    @rule(ordinals=st.lists(st.integers(min_value=1, max_value=MAX_BATCH_SIZE), max_size=2))
    def seal_current_version(self, ordinals: list[int]) -> None:
        state = self.ledger.state()
        if state.ledger_head() != vector_profile_digest(self._live):
            return
        if state.last_sealed_digest == state.ledger_head():
            return
        self.ledger.seal(self._live, pr_ref="#3")
        assert self.ledger.state().unreleased_mutations() == ()

    @invariant()
    def statuses_are_terminal_or_pending(self) -> None:
        for pid, status in self.ledger.state().statuses.items():
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
    def deferrals_never_exceed_policy(self) -> None:
        state = self.ledger.state()
        for pid, count in state.deferrals.items():
            assert count <= MAX_DEFERRALS + 1, f"{pid} exceeded deferral policy: {count}"

    @invariant()
    def no_mutation_is_ever_applied_without_a_numbered_task(self) -> None:
        state = self.ledger.state()
        # Every APPLIED event in the ledger must be one this machine ratified by numbers: an
        # apply that nobody numbered is exactly the silent-consent failure VM3/VM4 exist to stop.
        for item in state.applied:
            assert item["proposal_id"] in self.applied, (
                f"{item['proposal_id']} was applied without a numbered operator task"
            )
        for pid in self.applied:
            assert state.status_of(pid) == ProposalStatus.APPLIED


TEST_GOVERNANCE_MACHINE = VectorGovernanceMachine.TestCase
TEST_GOVERNANCE_MACHINE.settings = settings(
    max_examples=40,
    deadline=None,
    derandomize=True,
    database=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
)
