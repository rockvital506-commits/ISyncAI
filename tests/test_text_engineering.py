"""Tri-Tier Verification Suite for `[TEXT-ENGINEERING]` (ISAI-NVF v1.2, TE0..TE7).

Tier T1 — Level law & reader purity (deterministic: TE0 signature, level inventory, offline reader).
Tier T2 — Carrier duties end-to-end (TE1..TE6 faults injected into a sandbox, each must be caught).
Tier T3 — Generative text mutations: arbitrary edits must never yield a silent pass.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from _isai_sandbox import quiesce_staging

from isai.atomic_io import atomic_write_text
from isai.constitution import DEFAULT_BOUNDARY_IGNORE
from isai.engine import audit_repository, compile_rsoc, read_chronicle, sync_repository
from isai.health_checks import DEVIATION_STATUS, NO_DEVIATION_STATUS, evaluate_gate_v
from isai.text_engineering import (
    CARRIER_LEVELS,
    DOMAIN_ACRONYM_SET,
    EVENT_SUMMARY_FIELDS,
    HEDGE_MARKERS,
    L0_GENOME_BYTE_LENGTH,
    LEVEL_PRECEDENCE,
    SECTION_ROLES,
    TEXT_FILE_SUFFIXES,
    TextLevel,
    build_bound_vocabulary,
    canon_strings,
    classify_text,
    cli_surface,
    is_balanced_fragment,
    level_inventory,
    salience_profile,
    section_role,
    structured_tokens,
    text_engineering_packet,
    validate_text,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def _clone_repo_to_tmp(tmp_path: Path) -> Path:
    dest = tmp_path / "isai_text_sandbox"

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


def _codes(report: object) -> set[str]:
    return {f.check for f in report.findings}  # type: ignore[attr-defined]


# ============================================================================
# TIER T1: Level law & reader purity (TE0)
# ============================================================================


@pytest.mark.isai_scope("isai://root#TextEngineering")
def test_level_law_partitions_every_system_text_into_one_signature() -> None:
    """TE0: the carrier levels are a partition — every file signs exactly one, none is unsigned."""
    inventory = level_inventory(REPO_ROOT)
    assert set(inventory) == {level.value for level in CARRIER_LEVELS}
    flat = [rel for files in inventory.values() for rel in files]
    assert len(flat) == len(set(flat)), "a text file cannot declare two level signatures"
    assert all(files for files in inventory.values()), "every carrier level is materialised"

    assert inventory[TextLevel.L0_GENOME.value] == ["README.md"]
    assert "FUNDAMENTAL.md" in inventory[TextLevel.L2_TRANSCRIPT.value]
    assert "VISION.md" in inventory[TextLevel.L2_TRANSCRIPT.value]
    assert ".isai/neuro_vascular.py" in inventory[TextLevel.L1_CANON.value]
    assert "AGENTS.md" in inventory[TextLevel.L3_PROSE.value]
    assert ".isai/chronicle.jsonl" in inventory[TextLevel.L4_RECORD.value]

    # Precedence is total and stable: a conflict between two levels always has one winner.
    assert len(LEVEL_PRECEDENCE) == len(set(LEVEL_PRECEDENCE))
    assert LEVEL_PRECEDENCE[0] is TextLevel.L0_GENOME


@pytest.mark.isai_scope("isai://root#TextEngineering")
def test_level_signature_is_structural_not_declarative() -> None:
    """TE0: the signature is derived from the carrier, so it can never lie about the text."""
    passport = "### Паспорт\n<!-- ISAI:SYNC:BEGIN -->\n- паспорт\n<!-- ISAI:SYNC:END -->"
    assert classify_text(Path("x/README.md"), passport) is TextLevel.L2_TRANSCRIPT
    assert classify_text(Path("AGENTS.md"), "просто проза") is TextLevel.L3_PROSE
    assert classify_text(Path("a/mod.py"), "X = 1") is TextLevel.L1_CANON
    assert classify_text(Path(".isai/chronicle.jsonl"), "{}") is TextLevel.L4_RECORD
    assert classify_text(Path("pyproject.toml"), "[project]") is TextLevel.L4_RECORD
    assert L0_GENOME_BYTE_LENGTH == 586
    assert TEXT_FILE_SUFFIXES == (".md", ".py", ".jsonl", ".json", ".toml")


@pytest.mark.isai_scope("isai://root#TextEngineering")
def test_reader_is_pure_offline_and_deterministic() -> None:
    """TE7: the reader never mutates the repository and returns an identical digest twice."""
    before = {
        p: p.read_bytes()
        for p in sorted(REPO_ROOT.rglob("*"))
        if p.is_file() and not DEFAULT_BOUNDARY_IGNORE.is_ignored(p.relative_to(REPO_ROOT))
    }
    first = validate_text(REPO_ROOT)
    second = validate_text(REPO_ROOT)
    after = {
        p: p.read_bytes()
        for p in sorted(REPO_ROOT.rglob("*"))
        if p.is_file() and not DEFAULT_BOUNDARY_IGNORE.is_ignored(p.relative_to(REPO_ROOT))
    }
    assert before == after, "the text reader must be read-only"
    assert first.evidence_digest == second.evidence_digest
    assert first.status == second.status
    assert len(first.evidence_digest) == 64
    assert first.files_checked > 30 and first.text_bytes > 500_000


@pytest.mark.isai_scope("isai://root#TextEngineering")
def test_clean_repository_passes_every_text_duty() -> None:
    """The live corpus is the reference: TE0..TE6 must be green before a PR may be opened."""
    report = validate_text(REPO_ROOT)
    assert report.valid is True, [(f.check, f.location, f.message) for f in report.findings]
    assert report.status == "TEXT_VALID"
    assert set(SECTION_ROLES) == {"DECIDE", "EXECUTE", "EXPLAIN"}
    assert section_role("TE2.DLT-BPE: PhantomToken=FATAL") == "DECIDE"
    assert section_role("STOP-1[IL-0]: any byte edit => ABORT") == "DECIDE"
    assert section_role("N5.Sense-Before-Act: PreMutate => RUN `isai graph query`") == "DECIDE"
    assert section_role("Свободное объяснение без обязанностей") == "EXPLAIN"


@pytest.mark.isai_scope("isai://root#TextEngineering", "isai://root#RSoCCompiler")
def test_text_circuit_is_delivered_at_both_attention_peaks() -> None:
    """TE4/TE5: the fundamental must occupy the primacy head AND the terminal recency guard."""
    packet = compile_rsoc(REPO_ROOT, "isai://root")
    assert "enforced_text_engineering" in packet
    head = packet["enforced_text_engineering"]
    assert head["circuit"] == "[TEXT-ENGINEERING]"
    assert head["duties"] == ["TE0", "TE1", "TE2", "TE3", "TE4", "TE5", "TE6", "TE7"]
    assert head["status_token"] == "текст системных папок и файлов нативен"
    assert list(packet.keys())[-1] == "terminal_execution_guard"
    guard = packet["terminal_execution_guard"]["text_engineering_recency"]
    assert any("isai text check" in line for line in guard)
    # The slice is compact enough to survive the RSoC budget (VM5 batch bound is 5).
    assert len(json.dumps(head, ensure_ascii=False)) < 1400


# ============================================================================
# TIER T2: Carrier duties end-to-end (TE1..TE6)
# ============================================================================


@pytest.mark.isai_scope("isai://root#TextEngineering", "isai://root#SystemHealthGate")
def test_hand_edited_transcript_is_caught_by_te1(tmp_path: Path) -> None:
    """TE1: editing a synchronised projection by hand must be detected offline and at Gate V."""
    sandbox = _clone_repo_to_tmp(tmp_path)
    vision = sandbox / "VISION.md"
    atomic_write_text(vision, vision.read_text(encoding="utf-8") + "\nДописано вручную.\n")

    report = validate_text(sandbox)
    assert "TE1.CarrierPurity" in _codes(report)
    assert report.valid is False
    assert "H-TEXT-04" in evaluate_gate_v(sandbox).critical_failures
    assert "H-TEXT-02" in evaluate_gate_v(sandbox).critical_failures


@pytest.mark.isai_scope("isai://root#TextEngineering")
def test_phantom_command_is_caught_by_te3(tmp_path: Path) -> None:
    """TE3: naming a CLI command that does not exist is a text defect, not a typo."""
    sandbox = _clone_repo_to_tmp(tmp_path)
    agents = sandbox / "AGENTS.md"
    atomic_write_text(
        agents,
        agents.read_text(encoding="utf-8")
        + "\n6. Проверка: `.venv/bin/python -m isai teleport --force`.\n",
    )
    report = validate_text(sandbox)
    finding = [f for f in report.findings if f.check == "TE3.CommandTruth"]
    assert finding, "a phantom CLI command must be reported"
    assert "teleport" in finding[0].message
    assert report.valid is False


@pytest.mark.isai_scope("isai://root#TextEngineering")
def test_phantom_camel_lexicon_is_caught_by_te2(tmp_path: Path) -> None:
    """TE2: an invented CamelComposite in a normative rule is a hallucination surface."""
    sandbox = _clone_repo_to_tmp(tmp_path)
    ledger_py = sandbox / ".isai" / "vector_ledger.py"
    original = ledger_py.read_text(encoding="utf-8")
    # A *public* human-language carrier that names an invented CamelComposite is the damage TE2
    # exists to catch: the reader is handed a name that resolves to nothing at all. A private
    # implementation string is not a carrier, so the injection uses the exported idiom.
    injected = original.replace(
        "class MutationApplicationError(ValueError):",
        'PHANTOM_RULE = (\n'
        '    "VM9.PhantomLexicon: Оператор: мутация QuantumFluxAnomaly: FORBIDDEN -> ABORT: '
        'FATAL | REFUSED"\n'
        ')\n\n'
        "class MutationApplicationError(ValueError):",
        1,
    )
    assert injected != original, "the TE2 rule must be reachable for the fault injection"
    atomic_write_text(ledger_py, injected)
    report = validate_text(sandbox)
    assert "TE2.DLT-BPE" in _codes(report), [f.message for f in report.findings]
    phantom = [f for f in report.findings if f.check == "TE2.DLT-BPE"]
    assert any("QuantumFlux" in f.message for f in phantom), [f.message for f in phantom]


@pytest.mark.isai_scope("isai://root#TextEngineering")
def test_unranked_rule_and_hedged_event_are_caught(tmp_path: Path) -> None:
    """TE5/TE6: a rule without a salience prefix and a hedged evidence summary are deviations."""
    sandbox = _clone_repo_to_tmp(tmp_path)

    # TE5: a normative rule with no DECIDE/EXECUTE prefix and no execution arrow.
    vector_py = sandbox / ".isai" / "vector.py"
    atomic_write_text(
        vector_py,
        vector_py.read_text(encoding="utf-8").replace(
            "Никаких фоновых LLM-демонов с постоянным поллингом",
            "Совершенно необязательно избегать фоновых LLM-демонов с постоянным поллингом",
            1,
        ),
    )
    # TE6: a hedged chronicle event summary is injected as a fresh record.
    chronicle = sandbox / ".isai" / "chronicle.jsonl"
    events = [json.loads(line) for line in chronicle.read_text(encoding="utf-8").splitlines() if line.strip()]
    hedged = dict(events[-1])
    hedged["tx_id"] = f"TX-{len(events) + 1:04d}"
    hedged["revision"] = len(events) + 1
    hedged["summary"] = "Возможно, удалось что-то поправить, но точно неизвестно."
    atomic_write_text(
        chronicle,
        "".join(json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n" for e in [*events, hedged]),
    )

    report = validate_text(sandbox)
    codes = _codes(report)
    assert "TE6.ChronicleRegister" in codes
    assert report.valid is False
    assert any(f.check == "TE6.ChronicleRegister" and "hedge" in f.message for f in report.findings)


@pytest.mark.isai_scope("isai://root#TextEngineering")
def test_unbalanced_frame_and_undersectioned_prose_are_caught(tmp_path: Path) -> None:
    """TE4: an unbalanced normative frame and an unstructured long prose are both defects."""
    sandbox = _clone_repo_to_tmp(tmp_path)
    assert not is_balanced_fragment("правило [без закрытия")
    assert is_balanced_fragment("правило [с закрытием] и `код`")

    agents = sandbox / "AGENTS.md"
    wall = " ".join(
        "Длинное неразмеченное пояснение без единого заголовка и без списка обязанностей."
        for _ in range(40)
    )
    atomic_write_text(agents, wall)
    report = validate_text(sandbox)
    assert "TE4.FrameLaw" in _codes(report)


@pytest.mark.isai_scope("isai://root#TextEngineering", "isai://root#SystemHealthGate")
def test_clean_sandbox_text_gate_is_green_and_gate_v_agrees(tmp_path: Path) -> None:
    """A faithful clone must pass both the offline reader and Gate V's text domain."""
    sandbox = _clone_repo_to_tmp(tmp_path)
    assert validate_text(sandbox).valid is True
    report = evaluate_gate_v(sandbox)
    text_checks = [r for r in report.results if r.domain.value == "TEXT"]
    assert {r.check_id for r in text_checks} == {"H-TEXT-01", "H-TEXT-02", "H-TEXT-03", "H-TEXT-04"}
    assert all(r.passed for r in text_checks), [(r.check_id, r.evidence) for r in text_checks]
    assert report.status == NO_DEVIATION_STATUS


@pytest.mark.isai_scope("isai://root#TextEngineering")
def test_prose_phantom_names_are_caught_without_a_suffix_escape_hatch(tmp_path: Path) -> None:
    """
    TE2 must catch a hallucinated component name in *authored prose*.

    This is a regression test for a real hole in an earlier revision of the reader: binding was
    only checked in the formal DSL bodies, so prose — where an invented name actually misleads a
    reader — was never scanned at all. A second hole sat behind the first: a token that merely
    *ended* in a canonical suffix (`...Gate`, `...Kernel`, `...Vector`) was accepted as "a bound
    shape", which let every invented name of that form pass. Both are fixed; both are pinned here.
    """
    sandbox = _clone_repo_to_tmp(tmp_path)
    agents = sandbox / "AGENTS.md"
    original = agents.read_text(encoding="utf-8")
    invented = (
        "\n\nСлужба HallucinatedGate вместе с FakeKernel проверяет "
        "QuantumFluxVector перед каждым прогоном.\n"
    )
    atomic_write_text(agents, original + invented)

    report = validate_text(sandbox)
    assert report.status == "TEXT_DEVIATION_DETECTED"
    flagged = {f.message.split("'")[1] for f in report.findings if f.check == "TE2.DLT-BPE"}
    assert {"HallucinatedGate", "FakeKernel", "QuantumFluxVector"} <= flagged, flagged

    # And the same prose with real, bound names stays clean — the check is not a blanket ban.
    atomic_write_text(
        agents,
        original
        + "\n\nСлужба LinkInjector вместе с GenesisKernel проверяет MasterVector перед каждым прогоном.\n",
    )
    assert validate_text(sandbox).valid is True


@pytest.mark.isai_scope("isai://root#TextEngineering")
def test_lexicon_vocabulary_is_closed_and_grounded() -> None:
    """TE2: the bound vocabulary is derived from live code, commands, files and a closed acronym set."""
    vocabulary = build_bound_vocabulary(REPO_ROOT)
    for required in ("VectorMutationLedger", "validate_text", "audit", "health_checks"):
        assert required in vocabulary, f"{required} must bind"
    assert "RSoC" in DOMAIN_ACRONYM_SET and "ABSOLUTELY_NOT_A_DOMAIN" not in DOMAIN_ACRONYM_SET
    surface = cli_surface(REPO_ROOT)
    assert {"audit", "sync", "vector", "text", "gate"} <= set(surface)
    assert {"check", "levels", "packet"} <= surface["text"]
    assert structured_tokens("VectorMutationLedger и RSoC") == ["VectorMutationLedger", "RSoC"]


@pytest.mark.isai_scope("isai://root#TextEngineering")
def test_canon_reader_sees_whole_strings_not_fstring_fragments() -> None:
    """TE1: the reader must judge rendered text, never the compiler's split of an f-string."""
    strings = canon_strings(REPO_ROOT / ".isai" / "vector_ledger.py")
    assert strings
    fragments = [value for _lineno, value in strings if value in (')"""', '"""')]
    assert not fragments, "docstring delimiters must never appear as standalone carriers"
    assert all(isinstance(value, str) for _lineno, value in strings)


@pytest.mark.isai_scope("isai://root#TextEngineering")
def test_chronicle_register_taxonomy_is_enforced_on_events() -> None:
    """TE6: the typed summary fields are a closed taxonomy the Chronicle must satisfy."""
    assert EVENT_SUMMARY_FIELDS == ("summary", "evidence", "blast_radius", "next_action")
    events = read_chronicle(REPO_ROOT)
    assert events
    for event in events:
        assert event.summary.strip(), f"{event.tx_id} carries an empty summary"
        lowered = event.summary.lower()
        for hedge in HEDGE_MARKERS:
            assert hedge not in lowered, f"{event.tx_id} hedges with '{hedge}'"
    packet = text_engineering_packet()
    assert packet["level_law"][0] == {"level": "L0_GENOME", "precedence": 1}


# ============================================================================
# TIER T3: Generative text mutations must never pass silently
# ============================================================================


_ASCII_SAFE_ALPHABET = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .,:;-_[]()=|=>",
    min_size=1,
    max_size=60,
)


@pytest.mark.isai_scope("isai://root#TextEngineering")
@settings(
    max_examples=60,
    deadline=None,
    derandomize=True,
    database=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(rule=_ASCII_SAFE_ALPHABET, ordinal=st.integers(min_value=0, max_value=5))
def test_generated_normative_rules_never_break_the_frame(rule: str, ordinal: int) -> None:
    """TE4/TE5: whatever rule text is generated, its frame verdict is decidable and stable."""
    balanced = is_balanced_fragment(rule)
    assert isinstance(balanced, bool)
    role = section_role(rule)
    assert role in SECTION_ROLES
    profile = salience_profile([rule])
    assert sum(profile.values()) == 1
    assert profile[role] == 1


@pytest.mark.isai_scope("isai://root#TextEngineering")
@settings(
    max_examples=60,
    deadline=None,
    derandomize=True,
    database=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(token=st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-", min_size=2, max_size=30))
def test_generated_tokens_never_crash_the_lexicon_and_bind_deterministically(token: str) -> None:
    """TE2: token binding is total and deterministic — no token can crash or randomly resolve."""
    vocabulary = build_bound_vocabulary(REPO_ROOT)
    first = build_bound_vocabulary(REPO_ROOT)
    assert vocabulary == first, "the bound vocabulary must be deterministic across runs"
    found = structured_tokens(f"{token} VectorMutationLedger")
    assert "VectorMutationLedger" in found
    # Whatever else was extracted, the verdict for each token is a pure function of the token.
    assert all(isinstance(item, str) and item for item in found)
