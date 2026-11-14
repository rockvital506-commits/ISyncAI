"""
VM8 PostPromptGate must be a refusal, not a sentence.

The fundamental declared `PostPromptGate := AuditVector -> AuditResearchWindow -> RankProposals
-> CheckboxRequest | GateSkipped=FATAL`, but nothing executed it, so the gate could be skipped
without a trace. These tests pin the properties that make the executable gate meaningful:

* a clean ledger PASSes;
* a tampered ledger BLOCKs (it must never pass on corruption);
* an unreadable ledger BLOCKs instead of raising — a crashing gate reports nothing, and a caller
  that reads "no result" as "fine" is how a skipped gate hides;
* the gate never mutates the ledger: auditing a turn must not become a turn.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from isai.vector import MASTER_VECTOR
from isai.vector_ledger import VectorMutationLedger, run_post_prompt_gate

REPO_ROOT = Path(__file__).resolve().parents[1]

#: VAET selects affected tests by the symbols *each test* declares it touches. A module-level
#: `pytestmark` and a named alias both fail: the gate reads the decorator call site literally, so
#: every test carries the full `pytest.mark.isai_scope(...)` call below.
_SCOPE_ARGS = (
    "isai://root#VectorMutationLedger",
    "isai://root#MasterVector",
    "isai://tests#VM8PostPromptGateSuite",
)
LIVE_LEDGER = REPO_ROOT / ".isai" / "vector_ledger.jsonl"


def _sandbox(tmp_path: Path) -> Path:
    """A repository-shaped copy holding only what the gate reads."""
    root = tmp_path / "repo"
    (root / ".isai").mkdir(parents=True)
    shutil.copy2(LIVE_LEDGER, root / ".isai" / "vector_ledger.jsonl")
    return root


def _gate(root: Path) -> dict:
    return run_post_prompt_gate(
        repo_root=root,
        ledger=VectorMutationLedger(root),
        vector=MASTER_VECTOR,
        state=None,
    )


@pytest.mark.isai_scope(
    "isai://root#VectorMutationLedger",
    "isai://root#MasterVector",
    "isai://tests#VM8PostPromptGateSuite",
)
def test_clean_ledger_passes(tmp_path: Path) -> None:
    gate = _gate(_sandbox(tmp_path))
    assert gate["gate_status"] == "PASS", gate["reason"]
    assert gate["steps"]["1_audit_vector"]["ok"] is True
    assert gate["steps"]["1_audit_vector"]["deviations"] == []


@pytest.mark.isai_scope(
    "isai://root#VectorMutationLedger",
    "isai://root#MasterVector",
    "isai://tests#VM8PostPromptGateSuite",
)
def test_gate_names_all_four_steps(tmp_path: Path) -> None:
    """A gate that silently drops a step is the defect this whole module exists to prevent."""
    gate = _gate(_sandbox(tmp_path))
    # `3_batch` reports the numbering authority next to the ranking it governs; it is not a fifth
    # step, it is the evidence for step 3. The four declared steps must all still be present.
    assert {
        "1_audit_vector",
        "2_audit_research_window",
        "3_rank_proposals",
        "4_checkbox_request",
    } <= set(gate["steps"])
    assert gate["gate"] == "VM8.PostPromptGate"


@pytest.mark.isai_scope(
    "isai://root#VectorMutationLedger",
    "isai://root#MasterVector",
    "isai://tests#VM8PostPromptGateSuite",
)
def test_tampered_ledger_blocks(tmp_path: Path) -> None:
    root = _sandbox(tmp_path)
    path = root / ".isai" / "vector_ledger.jsonl"
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    event = json.loads(lines[0])
    event["digest"] = "f" * 64
    lines[0] = json.dumps(event, ensure_ascii=False)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    gate = _gate(root)
    assert gate["gate_status"] == "BLOCKED"
    assert gate["reason"]


@pytest.mark.isai_scope(
    "isai://root#VectorMutationLedger",
    "isai://root#MasterVector",
    "isai://tests#VM8PostPromptGateSuite",
)
def test_unreadable_ledger_blocks_instead_of_raising(tmp_path: Path) -> None:
    root = _sandbox(tmp_path)
    (root / ".isai" / "vector_ledger.jsonl").write_text("{not json}\n", encoding="utf-8")

    gate = _gate(root)  # must not raise
    assert gate["gate_status"] == "BLOCKED"
    assert gate["steps"]["1_audit_vector"]["deviations"][0]["code"] == "LEDGER_UNREADABLE"
    assert gate["steps"]["3_rank_proposals"] == []


@pytest.mark.isai_scope(
    "isai://root#VectorMutationLedger",
    "isai://root#MasterVector",
    "isai://tests#VM8PostPromptGateSuite",
)
def test_gate_never_mutates_the_ledger(tmp_path: Path) -> None:
    root = _sandbox(tmp_path)
    path = root / ".isai" / "vector_ledger.jsonl"
    before = path.read_bytes()
    _gate(root)
    assert path.read_bytes() == before


@pytest.mark.isai_scope(
    "isai://root#VectorMutationLedger",
    "isai://root#MasterVector",
    "isai://tests#VM8PostPromptGateSuite",
)
def test_blocked_gate_offers_nothing(tmp_path: Path) -> None:
    """A blocked gate must not hand out a numbered request: that is the whole point of blocking."""
    root = _sandbox(tmp_path)
    (root / ".isai" / "vector_ledger.jsonl").write_text("{not json}\n", encoding="utf-8")
    gate = _gate(root)
    assert gate["steps"]["4_checkbox_request"]["offered"] == 0
    assert gate["steps"]["4_checkbox_request"]["empty_reason"]


@pytest.mark.isai_scope(
    "isai://root#VectorMutationLedger",
    "isai://root#MasterVector",
    "isai://tests#VM8PostPromptGateSuite",
)
def test_gate_ordinals_match_the_batch_the_operator_reads(tmp_path: Path) -> None:
    """
    The gate must number mutations exactly as `isai vector pending` does.

    The first implementation re-enumerated pending proposals in its own order while the batch kept
    insertion order. With five proposals the two maps disagreed at ordinal 1 (`VMP-0002` versus
    `VMP-0001`), so an operator task naming "1" would have applied a mutation they never selected.
    A gate that certifies the wrong mutation is worse than no gate, so the batch is pinned as the
    single numbering authority here.
    """
    from isai.vector_ledger import VectorMutationLedger, run_post_prompt_gate

    root = _sandbox(tmp_path)
    ledger = VectorMutationLedger(root)
    state = ledger.state()
    batch = state.latest_batch()
    if batch is None:
        pytest.skip("no numbered batch in the live ledger; nothing to compare")

    gate = run_post_prompt_gate(
        repo_root=root, ledger=ledger, vector=MASTER_VECTOR, state=state
    )
    assert gate["steps"]["3_batch"]["batch_id"] == batch.batch_id
    reported = [(row["ordinal"], row["proposal_id"]) for row in gate["steps"]["3_rank_proposals"]]
    expected = [(i, pid) for i, pid in enumerate(batch.proposal_ids, start=1)]
    assert reported == expected
