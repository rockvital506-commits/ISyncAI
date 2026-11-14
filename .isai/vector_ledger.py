"""Structured Ultimate-Goal Vector Mutation Ledger (`isai://root#VectorMutationLedger`).

Implements `ISAI-NVF v1.1` `[VECTOR-GOVERNANCE]` rules VM1..VM6:

  VM1 Append-only ledger of record: every proposed mutation of the Master Vector
      (`isai://root#MasterVector`, `.isai/vector.py` -> `VISION.md`) is an event in
      `.isai/vector_ledger.jsonl`; the authoritative state is a deterministic fold of
      those events and no proposal may ever be silently dropped.
  VM2 Proposal binding: a proposal must declare a resolvable anchor, mutation kind,
      proposed text, a non-trivial rationale, evidence references, risk level and the
      exact `base_vector_digest` it was derived from.
  VM3 Confirmation signal: the *next* operator prompt is the only ratification channel,
      and the only confirmation control line is a standalone task
      `подтвердить мутации вектора системы` followed by the **numbers** of the mutations
      to implement. Fenced code, inline code spans, blockquotes and embedded quotations are
      never signals (anti-self-confirmation reflex); checkboxes are not a confirmation
      channel at all.
  VM4 Numbered ratification: the agent's implementation request is a *numbered* list of
      promising mutations, each with a substantive justification. A confirmation task that
      lists no numbers ratifies the current version **without** applying any mutation; a
      confirmation task that lists numbers applies exactly those mutations (auto-bump +
      atomic apply ceremony). A confirmed proposal may only be applied once the vector file
      actually changes, and the application must atomically write the Chronicle
      `MUTATE_VECTOR` event, the refreshed state snapshot and the `APPLIED` ledger event.
  VM5 Confirmed baseline & deferral decay: the current confirmed version is the version of
      the last pull request (`RELEASED` seal); applied mutations that were not yet sealed
      into a PR are an unreleased-ratification deviation. Absent a confirmation task the
      last confirmed version simply stays in force and the next selection proceeds from it.
      A proposal deferred twice expires and must be re-proposed with fresh evidence;
      orphaned pending proposals are a critical deviation.
  VM6 Drift detection: if any vector anchor differs from the baseline recorded at ledger
      genesis while no `APPLIED` event covers that anchor, that is an unconfirmed vector
      drift (critical deviation).
"""

from __future__ import annotations

import hashlib
import json
import re
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from isai.atomic_io import atomic_transaction_batch, atomic_write_text, repository_write_lock
from isai.domain_models import MasterVectorSpec
from isai.graph_index import load_repo_master_vector
from isai.protocol import ChronicleEvent, SystemStateSnapshot, utc_now_iso

VECTOR_LEDGER_REL_PATH = Path(".isai") / "vector_ledger.jsonl"

#: Canonical anchor of the *separate explicit task* that ratifies a numbered mutation batch.
#:
#: The task is the only confirmation channel (`VM3`): the text after the anchor carries the
#: numbers of the mutations to implement. The anchor alone (without numbers) ratifies the
#: current version *without* implementing anything (`VM4`).
CONFIRM_TASK_ANCHOR_FORMS: tuple[str, ...] = (
    "подтвердить мутации вектора системы",
    "подтверждаю мутации вектора системы",
    "confirm system vector mutations",
)

#: Superseded control line. Parsed **only** to emit an honest refusal: it confers no consent
#: (it names no mutations, so it can neither ratify a batch nor silently ratify the version).
LEGACY_PHRASE_FORMS: tuple[str, ...] = (
    "подтвердить вектор системы",
    "подтверждаю вектор системы",
    "vector-confirm",
)

#: Maximum number of deferral windows a pending proposal may survive before it expires.
MAX_DEFERRALS: int = 2

#: Maximum size of one numbered mutation batch offered to the Operator.
MAX_BATCH_SIZE: int = 5

_PROPOSAL_ID_RE = re.compile(r"^VMP-(?P<num>[0-9]{4,})$")
_BATCH_ID_RE = re.compile(r"^VMB-(?P<num>[0-9]{4,})$")
_FENCE_RE = re.compile(r"```[\s\S]*?```")
_INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
_BULLET_RE = re.compile(r"^(?:[-*+\u2022]|(?P<ord>[0-9]{1,3})[.)])[ \t]+")
_QUOTE_CHARS = "\"'`\u00ab\u00bb\u201c\u201d\u201e\u2018\u2019"
_TRAILING_PUNCT = ".!?;:,\u2014\u2013-\u2026"
#: Integer tokens that denote mutation ordinals. Version-like (`1.2.5`), year-like (`2026`) and
#: percentage-like (`30%`) tokens are masked out first so a version bump can never be read as a
#: mutation number.
_NUMBER_MASK_RE = re.compile(r"\b\d+\.\d+(?:\.\d+)*\b|\b\d{4}\b|\b\d+%")
_NUMBER_RE = re.compile(r"\d{1,3}")


class VectorAnchorKind(StrEnum):
    """Addressable anchor of the structured ultimate-goal vector (`MasterVectorSpec`)."""

    NORTH_STAR = "NORTH_STAR"
    CORE_OBJECTIVE = "CORE_OBJECTIVE"
    PILLAR = "PILLAR"
    HORIZON = "HORIZON"
    ANTI_GOAL = "ANTI_GOAL"
    VERSION = "VERSION"


class MutationKind(StrEnum):
    """Direction of a vector mutation."""

    ADD = "ADD"
    EDIT = "EDIT"
    REMOVE = "REMOVE"


class ProposalStatus(StrEnum):
    """Derived lifecycle status of a single vector mutation proposal."""

    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    APPLIED = "APPLIED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    SUPERSEDED = "SUPERSEDED"
    RESEARCH_WINDOW_OPENED = "RESEARCH_WINDOW_OPENED"


class ConfirmationChannel(StrEnum):
    """Provenance channel of a ledger transition decision."""

    BASELINE = "BASELINE"
    OPERATOR_TASK = "OPERATOR_TASK"
    NONE = "NONE"


class LedgerEventKind(StrEnum):
    """Append-only event vocabulary of the vector mutation ledger."""

    BASELINE = "BASELINE"
    PROPOSED = "PROPOSED"
    BATCH_PROPOSED = "BATCH_PROPOSED"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    DEFERRED = "DEFERRED"
    VERSION_REAFFIRMED = "VERSION_REAFFIRMED"
    APPLIED = "APPLIED"
    SEALED = "SEALED"
    EXPIRED = "EXPIRED"
    SUPERSEDED = "SUPERSEDED"
    RESEARCH_WINDOW_OPENED = "RESEARCH_WINDOW_OPENED"


class RiskLevel(StrEnum):
    """Blast-radius class declared by the proposing agent."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class VectorMutationProposal(BaseModel):
    """A single structured mutation proposal against the ISAI Master Vector."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    proposal_id: str = Field(min_length=8, max_length=16)
    anchor_kind: VectorAnchorKind
    anchor_index: int = Field(ge=0, default=0)
    anchor_label: str = Field(min_length=1)
    mutation_kind: MutationKind
    proposed_text: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    evidence_refs: tuple[str, ...] = ()
    risk_level: RiskLevel = RiskLevel.LOW
    expected_benefit: str = Field(min_length=1)
    anchor_fingerprint: str = Field(min_length=64, max_length=64)
    base_vector_digest: str = Field(min_length=64, max_length=64)
    created_at_utc: str = Field(min_length=1)

    @field_validator("proposal_id")
    @classmethod
    def _validate_proposal_id(cls, value: str) -> str:
        if not _PROPOSAL_ID_RE.match(value):
            raise ValueError(f"Proposal id '{value}' must match 'VMP-<dddd>'.")
        return value

    @field_validator("rationale")
    @classmethod
    def _validate_rationale_depth(cls, value: str) -> str:
        if len(value.strip()) < 60:
            raise ValueError(
                "Rationale must carry a substantive justification (>= 60 characters); "
                "unjustified mutations are forbidden (VM2)."
            )
        return value

    @field_validator("evidence_refs")
    @classmethod
    def _validate_evidence(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        cleaned = tuple(item.strip() for item in value if item.strip())
        if not cleaned:
            raise ValueError("At least one non-empty evidence reference is required (VM2).")
        return cleaned

    @model_validator(mode="after")
    def _validate_anchor_arity(self) -> VectorMutationProposal:
        if self.anchor_kind in (VectorAnchorKind.NORTH_STAR, VectorAnchorKind.VERSION):
            if self.anchor_index != 0:
                raise ValueError(
                    f"Anchor '{self.anchor_kind.value}' is singular; anchor_index must be 0."
                )
        return self


class VectorMutationBatch(BaseModel):
    """
    One numbered implementation request (`VM4`): the promising mutations offered to the Operator.

    The ordinal is the number the Operator writes into the confirmation task. A batch is a
    *request*, never a consent: only `POST /confirm`-style evidence — a separate explicit task
    carrying the numbers — may move a member of the batch to CONFIRMED.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    batch_id: str = Field(min_length=8, max_length=16)
    base_vector_digest: str = Field(min_length=64, max_length=64)
    proposal_ids: tuple[str, ...] = Field(min_length=1, max_length=MAX_BATCH_SIZE)
    created_at_utc: str = Field(min_length=1)

    @field_validator("batch_id")
    @classmethod
    def _validate_batch_id(cls, value: str) -> str:
        if not _BATCH_ID_RE.match(value):
            raise ValueError(f"Batch id '{value}' must match 'VMB-<dddd>'.")
        return value

    @field_validator("proposal_ids")
    @classmethod
    def _validate_unique_members(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("A numbered mutation batch cannot list the same proposal twice.")
        for item in value:
            if not _PROPOSAL_ID_RE.match(item):
                raise ValueError(f"Batch member '{item}' must match 'VMP-<dddd>'.")
        return value


class VectorLedgerEvent(BaseModel):
    """One immutable line of `.isai/vector_ledger.jsonl`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    seq: int = Field(ge=1)
    event_id: str = Field(min_length=1)
    timestamp_utc: str = Field(min_length=1)
    kind: LedgerEventKind
    channel: ConfirmationChannel = ConfirmationChannel.NONE
    operator_note: str | None = None
    proposal: VectorMutationProposal | None = None
    proposal_id: str | None = None
    batch: VectorMutationBatch | None = None
    batch_id: str | None = None
    selected_ordinals: tuple[int, ...] = ()
    vector_digest_before: str | None = Field(default=None, min_length=64, max_length=64)
    vector_digest_after: str | None = Field(default=None, min_length=64, max_length=64)
    chronicle_tx_id: str | None = None
    baseline_digest: str | None = Field(default=None, min_length=64, max_length=64)
    baseline_version: str | None = None
    baseline_anchor_digests: dict[str, str] | None = None
    vector_version: str | None = None
    prompt_ref: str | None = None

    @model_validator(mode="after")
    def _validate_payload_by_kind(self) -> VectorLedgerEvent:
        if self.kind == LedgerEventKind.PROPOSED and self.proposal is None:
            raise ValueError("PROPOSED event requires an embedded proposal payload.")
        if self.kind != LedgerEventKind.PROPOSED and self.proposal is not None:
            raise ValueError("Only PROPOSED events may embed a proposal payload.")
        if self.kind == LedgerEventKind.BATCH_PROPOSED:
            if self.batch is None or not self.batch_id:
                raise ValueError("BATCH_PROPOSED event requires an embedded batch payload.")
        elif self.batch is not None:
            raise ValueError("Only BATCH_PROPOSED events may embed a batch payload.")
        elif self.batch_id is not None and self.kind not in (
            LedgerEventKind.CONFIRMED,
            LedgerEventKind.REJECTED,
        ):
            raise ValueError(
                "Only BATCH_PROPOSED, CONFIRMED and REJECTED events may reference a batch."
            )
        if self.kind in (
            LedgerEventKind.CONFIRMED,
            LedgerEventKind.REJECTED,
            LedgerEventKind.DEFERRED,
            LedgerEventKind.EXPIRED,
            LedgerEventKind.SUPERSEDED,
            LedgerEventKind.APPLIED,
        ) and not self.proposal_id:
            raise ValueError(f"{self.kind.value} event requires proposal_id.")
        if self.kind == LedgerEventKind.SEALED:
            if not (self.vector_digest_after and self.operator_note and self.vector_version):
                raise ValueError(
                    "SEALED event requires vector_digest_after, vector_version and an operator_note (PR ref)."
                )
        if self.kind == LedgerEventKind.RESEARCH_WINDOW_OPENED:
            if not self.vector_digest_after:
                raise ValueError("RESEARCH_WINDOW_OPENED requires the head digest it was opened at.")
        if self.kind == LedgerEventKind.BASELINE:
            if not self.baseline_digest or not self.baseline_version:
                raise ValueError("BASELINE event requires baseline_digest and baseline_version.")
            if not self.baseline_anchor_digests:
                raise ValueError("BASELINE event requires baseline_anchor_digests.")
        if self.kind == LedgerEventKind.VERSION_REAFFIRMED:
            if self.channel != ConfirmationChannel.OPERATOR_TASK:
                raise ValueError("VERSION_REAFFIRMED is only reachable through an OPERATOR_TASK.")
            if not self.vector_digest_after:
                raise ValueError("VERSION_REAFFIRMED requires the confirmed digest.")
        if self.kind == LedgerEventKind.APPLIED:
            if not (self.vector_digest_before and self.vector_digest_after and self.chronicle_tx_id):
                raise ValueError(
                    "APPLIED event requires vector_digest_before, vector_digest_after and chronicle_tx_id."
                )
            if self.vector_digest_before == self.vector_digest_after:
                raise ValueError("APPLIED event must record an actual vector digest change.")
        return self


# ---------------------------------------------------------------------------
# Anchor resolution & digest profile
# ---------------------------------------------------------------------------


def resolve_anchor_text(vector: MasterVectorSpec, kind: VectorAnchorKind, index: int) -> str | None:
    """Return the live anchor text addressed by (kind, index), or None when unresolvable."""
    if kind == VectorAnchorKind.NORTH_STAR:
        return vector.north_star_statement if index == 0 else None
    if kind == VectorAnchorKind.VERSION:
        return vector.version if index == 0 else None
    if kind == VectorAnchorKind.CORE_OBJECTIVE:
        seq = vector.core_objectives
    elif kind == VectorAnchorKind.PILLAR:
        seq = vector.architectural_pillars
    elif kind == VectorAnchorKind.HORIZON:
        seq = vector.evolution_horizons
    elif kind == VectorAnchorKind.ANTI_GOAL:
        seq = vector.anti_goals
    else:  # pragma: no cover - exhaustive enum
        return None
    if 0 <= index < len(seq):
        return json.dumps(seq[index], ensure_ascii=False, sort_keys=True, default=str)
    return None


def anchor_fingerprint(vector: MasterVectorSpec, kind: VectorAnchorKind, index: int) -> str:
    """
    Exact fingerprint of the addressed anchor, captured at proposal time (VM2).

    A proposal whose fingerprint no longer matches the live anchor is *stale*: indices may
    have shifted because another mutation was applied in between, so blind application
    would corrupt a neighbouring goal. Stale proposals must be re-proposed, never applied.
    """
    resolved = resolve_anchor_text(vector, kind, index)
    if resolved is None:
        # ADD proposal at the append sentinel: bind to the *prefix* only, so that later
        # appends (which by definition keep the prefix intact) never invalidate the proposal,
        # while any insertion/removal inside the prefix still does.
        seq = _anchor_sequence(vector, kind)[:index]
        resolved = "PREFIX:" + json.dumps(seq, ensure_ascii=False, sort_keys=True, default=str)
    payload = f"{kind.value}|{index}|{resolved}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _anchor_sequence(vector: MasterVectorSpec, kind: VectorAnchorKind) -> list[Any]:
    """Return the ordered anchor sequence addressed by `kind` (singular anchors have length 1)."""
    return {
        VectorAnchorKind.NORTH_STAR: [vector.north_star_statement],
        VectorAnchorKind.CORE_OBJECTIVE: list(vector.core_objectives),
        VectorAnchorKind.PILLAR: [p.model_dump(mode="json") for p in vector.architectural_pillars],
        VectorAnchorKind.HORIZON: [h.model_dump(mode="json") for h in vector.evolution_horizons],
        VectorAnchorKind.ANTI_GOAL: list(vector.anti_goals),
        VectorAnchorKind.VERSION: [vector.version],
    }[kind]


def anchor_digest_profile(vector: MasterVectorSpec) -> dict[str, str]:
    """Deterministic per-anchor SHA-256 profile used for machine drift detection (VM6)."""
    raw: dict[str, Any] = {
        VectorAnchorKind.NORTH_STAR.value: [vector.north_star_statement],
        VectorAnchorKind.CORE_OBJECTIVE.value: list(vector.core_objectives),
        VectorAnchorKind.PILLAR.value: [p.model_dump(mode="json") for p in vector.architectural_pillars],
        VectorAnchorKind.HORIZON.value: [h.model_dump(mode="json") for h in vector.evolution_horizons],
        VectorAnchorKind.ANTI_GOAL.value: list(vector.anti_goals),
        VectorAnchorKind.VERSION.value: [vector.version],
    }
    return {
        key: hashlib.sha256(
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        for key, value in raw.items()
    }


def vector_profile_digest(vector: MasterVectorSpec) -> str:
    """
    Canonical ledger digest of the vector.

    Deliberately identical to `MasterVectorSpec.spec_digest()` — the very digest embedded in
    `VISION.md` and `state_snapshot.master_vector_digest` — so that one identifier governs the
    ledger head, the human-readable projection and the runtime snapshot with zero duplication.
    """
    return vector.spec_digest()


# ---------------------------------------------------------------------------
# Operator signal parsing (VM3)
# ---------------------------------------------------------------------------


class OperatorSignal(BaseModel):
    """
    Deterministic parse result of one operator prompt (`VM3`).

    A confirmation exists **only** when the prompt carries the separate explicit task
    `подтвердить мутации вектора системы`. Everything else is either a numbered
    implementation request or ordinary prompt text with no ratification power.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    task_present: bool = False
    selected_ordinals: tuple[int, ...] = ()
    matched_line: str | None = None
    suppressed_candidates: int = 0
    legacy_phrase_present: bool = False
    unknown_ordinal_tokens: tuple[int, ...] = ()

    @property
    def confirms_any_mutation(self) -> bool:
        """True when the task names at least one ordinal (apply exactly those mutations)."""
        return self.task_present and bool(self.selected_ordinals)


def _normalize(text: str) -> str:
    value = text.replace("\u0451", "\u0435").replace("\u0401", "\u0415")
    value = value.lower()
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _strip_wrapping(line: str) -> str:
    candidate = line.strip()
    # Drop leading markdown headings / list decoration and emphasis markers.
    candidate = re.sub(r"^#{1,6}[ \t]+", "", candidate)
    candidate = re.sub(r"^(?:\*\*|__|\*|_)+", "", candidate)
    candidate = re.sub(r"(?:\*\*|__|\*|_)+$", "", candidate)
    candidate = candidate.strip()
    changed = True
    while changed and candidate:
        changed = False
        if candidate and candidate[0] in _QUOTE_CHARS:
            candidate = candidate[1:].strip()
            changed = True
        if candidate and candidate[-1] in _QUOTE_CHARS:
            candidate = candidate[:-1].strip()
            changed = True
        if candidate and candidate[-1] in _TRAILING_PUNCT:
            candidate = candidate[:-1].strip()
            changed = True
    return candidate


def _numbers_from_tail(tail: str) -> list[int]:
    """
    Read ordinals out of a confirmation tail, refusing anything that is not a bare number list.

    The tail is acceptable only when *nothing but* numbers, separators and the conjunctions
    `и`/`and`/`или`/`or` remain after the numbers are removed — so prose such as
    ``1 promt за задачу`` or ``30% уверенности`` never silently ratifies a mutation.
    """
    numbers = _NUMBER_RE.findall(tail)
    leftover = _NUMBER_RE.sub(" ", tail)
    leftover = re.sub(r"\b(?:и|and|или|or)\b", " ", leftover)
    leftover = re.sub(r"[\s,;/|&+\u2116#:()\[\]\-\u2013\u2014.\u0001]+", "", leftover)
    if leftover:
        return []
    return [int(n) for n in numbers]


def _extract_ordinals(text: str) -> tuple[list[int], list[int]]:
    """
    Extract mutation ordinals from the tail of a confirmation task line.

    Version-like (``1.2.5``), year-like (``2026``) and percentage (``30%``) tokens are masked
    first so a version bump or an evidence year can never be mistaken for a mutation number.
    Parenthesised/bracketed selections such as ``(1, 3)`` are honoured explicitly.
    """
    masked = _NUMBER_MASK_RE.sub("\u0001", text)

    def _scrub(match: re.Match[str]) -> str:
        inner = match.group(1) if match.group(1) is not None else (match.group(2) or "")
        found = _numbers_from_tail(inner)
        return (": " + " ".join(str(n) for n in found)) if found else " "

    scrubbed = re.sub(r"\(([^()]*)\)|\[([^\[\]]*)\]", _scrub, masked)
    parts = re.split(r"[\u2116#:]", scrubbed, maxsplit=1)
    tail = parts[1] if len(parts) > 1 else scrubbed
    raw = _numbers_from_tail(tail)

    known: list[int] = []
    unknown: list[int] = []
    for value in raw:
        if 1 <= value <= MAX_BATCH_SIZE:
            if value not in known:
                known.append(value)
        elif value not in unknown:
            unknown.append(value)
    return known, unknown


def parse_operator_signal(prompt_text: str) -> OperatorSignal:
    """
    Extract the vector-mutation confirmation signal from one operator prompt.

    Rules (`VM3`/`VM4`) — all deliberately fail-closed:

    * Fenced code, inline code spans and blockquotes are stripped first: documenting the
      protocol can never ratify it, and quoting the operator cannot impersonate them.
    * The confirmation task must be a *standalone control line* (optionally bulleted or
      headed) whose normalized text starts with a `CONFIRM_TASK_ANCHOR_FORMS` anchor.
    * Numbers listed anywhere in that control line are the selected mutation ordinals; if no
      number is listed the task confirms the current version **without** applying anything.
    * The superseded phrase `подтвердить вектор системы` is recognised only to be refused.
    """
    without_fences = _FENCE_RE.sub("\n", prompt_text)
    suppressed = len(_INLINE_CODE_RE.findall(without_fences))
    task_present = False
    legacy_present = False
    matched_line: str | None = None
    known: list[int] = []
    unknown: list[int] = []
    in_quote = False

    for raw_line in without_fences.splitlines():
        line = _INLINE_CODE_RE.sub(" ", raw_line)
        candidate = line.strip()
        if not candidate:
            in_quote = False
            continue
        if candidate.startswith(">"):
            in_quote = True
            continue
        if in_quote:
            continue
        candidate = _BULLET_RE.sub("", candidate)
        control = _strip_wrapping(candidate)
        if not control:
            continue
        normalized = _normalize(control)
        if normalized in LEGACY_PHRASE_FORMS:
            legacy_present = True
            continue
        for anchor in CONFIRM_TASK_ANCHOR_FORMS:
            if normalized == anchor or normalized.startswith(anchor):
                task_present = True
                matched_line = control
                found_known, found_unknown = _extract_ordinals(normalized[len(anchor) :])
                known.extend(n for n in found_known if n not in known)
                unknown.extend(n for n in found_unknown if n not in unknown)
                break

    return OperatorSignal(
        task_present=task_present,
        selected_ordinals=tuple(sorted(known)),
        matched_line=matched_line,
        suppressed_candidates=suppressed,
        legacy_phrase_present=legacy_present,
        unknown_ordinal_tokens=tuple(sorted(unknown)),
    )


# ---------------------------------------------------------------------------
# Ledger storage & deterministic fold
# ---------------------------------------------------------------------------


class VectorLedgerState(BaseModel):
    """Deterministic fold of all ledger events (the authoritative derived state)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    baseline_digest: str | None = None
    baseline_version: str | None = None
    baseline_anchor_digests: dict[str, str] = Field(default_factory=dict)
    proposals: dict[str, VectorMutationProposal] = Field(default_factory=dict)
    statuses: dict[str, ProposalStatus] = Field(default_factory=dict)
    deferrals: dict[str, int] = Field(default_factory=dict)
    batches: dict[str, VectorMutationBatch] = Field(default_factory=dict)
    applied: tuple[dict[str, Any], ...] = ()
    last_reaffirmed_digest: str | None = None
    last_reaffirmed_at: str | None = None
    last_sealed_digest: str | None = None
    last_sealed_version: str | None = None
    last_sealed_pr_ref: str | None = None
    last_sealed_at: str | None = None
    research_window_open_at: str | None = None
    events_count: int = 0

    def status_of(self, proposal_id: str) -> ProposalStatus | None:
        return self.statuses.get(proposal_id)

    def pending(self) -> tuple[VectorMutationProposal, ...]:
        return tuple(
            p for pid, p in sorted(self.proposals.items()) if self.statuses.get(pid) == ProposalStatus.PENDING
        )

    def confirmed(self) -> tuple[VectorMutationProposal, ...]:
        return tuple(
            p for pid, p in sorted(self.proposals.items()) if self.statuses.get(pid) == ProposalStatus.CONFIRMED
        )

    def next_proposal_id(self) -> str:
        highest = 0
        for pid in self.proposals:
            match = _PROPOSAL_ID_RE.match(pid)
            if match:
                highest = max(highest, int(match.group("num")))
        return f"VMP-{highest + 1:04d}"

    def next_batch_id(self) -> str:
        highest = 0
        for bid in self.batches:
            match = _BATCH_ID_RE.match(bid)
            if match:
                highest = max(highest, int(match.group("num")))
        return f"VMB-{highest + 1:04d}"

    def latest_batch(self) -> VectorMutationBatch | None:
        if not self.batches:
            return None
        return self.batches[sorted(self.batches)[-1]]

    def ledger_head(self) -> str | None:
        """Digest of the last applied mutation, or the baseline digest when nothing was applied."""
        return self.applied[-1]["after"] if self.applied else self.baseline_digest

    def confirmed_version_digest(self) -> str | None:
        """
        Digest of the currently confirmed vector version.

        A ratified version becomes *confirmed* only when it is sealed into a pull request
        (`SEALED`); before the first seal the ledger genesis is the confirmed version. Mutations
        applied but not yet sealed are therefore never mistaken for the confirmed baseline.
        """
        return self.last_sealed_digest or self.baseline_digest

    def released_proposal_ids(self) -> set[str]:
        """Proposals applied at or before the last `SEALED` (last-PR) digest."""
        sealed_head = self.last_sealed_digest
        if sealed_head is None:
            return set()
        released: set[str] = set()
        for item in self.applied:
            released.add(item["proposal_id"])
            if item["after"] == sealed_head:
                break
        else:
            return set()
        return released

    def unreleased_mutations(self) -> tuple[dict[str, Any], ...]:
        """Applied mutations that are not yet covered by a `SEALED` (last-PR) record."""
        released = self.released_proposal_ids()
        return tuple(item for item in self.applied if item["proposal_id"] not in released)

    def batch_members(self, batch_id: str) -> tuple[VectorMutationProposal, ...]:
        batch = self.batches.get(batch_id)
        if batch is None:
            return ()
        return tuple(self.proposals[pid] for pid in batch.proposal_ids if pid in self.proposals)


def _require_event(events: list[VectorLedgerEvent], kind: LedgerEventKind, ev: VectorLedgerEvent) -> None:
    if ev.kind != kind:  # pragma: no cover - defensive
        raise ValueError(f"Expected {kind.value} event, got {ev.kind.value}.")


def fold_events(events: list[VectorLedgerEvent]) -> VectorLedgerState:
    """Validate the append-only transition grammar and fold it into `VectorLedgerState`."""
    baseline_digest: str | None = None
    baseline_version: str | None = None
    baseline_anchors: dict[str, str] = {}
    proposals: dict[str, VectorMutationProposal] = {}
    statuses: dict[str, ProposalStatus] = {}
    deferrals: dict[str, int] = {}
    batches: dict[str, VectorMutationBatch] = {}
    applied: list[dict[str, Any]] = []
    reaffirmed_digest: str | None = None
    reaffirmed_at: str | None = None
    sealed_digest: str | None = None
    sealed_version: str | None = None
    sealed_pr_ref: str | None = None
    sealed_at: str | None = None
    research_open_at: str | None = None
    expected_seq = 1

    for ev in events:
        if ev.seq != expected_seq:
            raise ValueError(
                f"Non-monotonic ledger sequence: expected {expected_seq}, got {ev.seq} (event {ev.event_id})."
            )
        expected_seq += 1

        if ev.kind == LedgerEventKind.BASELINE:
            if baseline_digest is not None:
                raise ValueError("Duplicate BASELINE event: the vector ledger has a single genesis.")
            baseline_digest = ev.baseline_digest
            baseline_version = ev.baseline_version
            baseline_anchors = dict(ev.baseline_anchor_digests or {})
            reaffirmed_digest = baseline_digest
            reaffirmed_at = ev.timestamp_utc
            continue

        if baseline_digest is None:
            raise ValueError("Ledger events cannot precede the BASELINE genesis event.")

        head_now = applied[-1]["after"] if applied else baseline_digest

        if ev.kind == LedgerEventKind.SEALED:
            assert ev.vector_digest_after is not None
            if ev.vector_digest_after != head_now:
                raise ValueError(
                    "SEALED cannot declare a version that is not the current ledger head "
                    f"({ev.vector_digest_after[:12]}... != {head_now[:12]}...)."
                )
            sealed_digest = ev.vector_digest_after
            sealed_version = ev.vector_version
            sealed_pr_ref = ev.operator_note
            sealed_at = ev.timestamp_utc
            research_open_at = None
            continue

        if ev.kind == LedgerEventKind.VERSION_REAFFIRMED:
            assert ev.vector_digest_after is not None
            if ev.vector_digest_after != head_now:
                raise ValueError(
                    "VERSION_REAFFIRMED cannot confirm a digest that is not the current ledger head."
                )
            reaffirmed_digest = ev.vector_digest_after
            reaffirmed_at = ev.timestamp_utc
            research_open_at = None
            continue

        pid = ev.proposal_id
        if ev.kind == LedgerEventKind.RESEARCH_WINDOW_OPENED:
            research_open_at = ev.vector_digest_after
            continue

        if ev.kind == LedgerEventKind.BATCH_PROPOSED:
            assert ev.batch is not None
            batch = ev.batch
            if batch.batch_id in batches:
                raise ValueError(f"Duplicate batch id '{batch.batch_id}' (Redundancy=FATAL).")
            unknown = [pid_ for pid_ in batch.proposal_ids if pid_ not in proposals]
            if unknown:
                raise ValueError(f"Batch '{batch.batch_id}' references unknown proposals {unknown}.")
            if batch.base_vector_digest != head_now:
                raise ValueError(
                    f"Batch '{batch.batch_id}' declares base digest "
                    f"{batch.base_vector_digest[:12]}... but the ledger head is {head_now[:12]}...: "
                    f"a numbered request must be numbered against the live vector."
                )
            batches[batch.batch_id] = batch
            continue

        if ev.kind == LedgerEventKind.PROPOSED:
            assert ev.proposal is not None
            if ev.proposal.proposal_id in proposals:
                raise ValueError(
                    f"Duplicate proposal id '{ev.proposal.proposal_id}' (Redundancy=FATAL)."
                )
            if ev.proposal.base_vector_digest != head_now:
                raise ValueError(
                    f"Proposal '{ev.proposal.proposal_id}' declares base digest "
                    f"{ev.proposal.base_vector_digest[:12]}... but the ledger head is "
                    f"{head_now[:12]}...: a proposal must be bound to the live vector."
                )
            proposals[ev.proposal.proposal_id] = ev.proposal
            statuses[ev.proposal.proposal_id] = ProposalStatus.PENDING
            deferrals[ev.proposal.proposal_id] = 0
            continue

        if pid is None or pid not in proposals:
            raise ValueError(f"Event {ev.kind.value} references unknown proposal '{pid}'.")
        current = statuses[pid]
        if (
            ev.kind == LedgerEventKind.SUPERSEDED
            and current == ProposalStatus.CONFIRMED
            and not (ev.operator_note and ev.operator_note.strip())
        ):
            raise ValueError(
                f"Superseding a CONFIRMED proposal '{pid}' requires an explicit operator_note "
                f"(the Operator ratified it; the record must explain why it cannot be delivered)."
            )

        if ev.kind == LedgerEventKind.CONFIRMED:
            if current != ProposalStatus.PENDING:
                raise ValueError(f"Cannot confirm '{pid}' in status {current.value}.")
            if ev.channel != ConfirmationChannel.OPERATOR_TASK:
                raise ValueError(
                    f"Confirmation of '{pid}' must be issued through an explicit OPERATOR_TASK."
                )
            if ev.batch_id is not None:
                batch = batches.get(ev.batch_id)
                if batch is None:
                    raise ValueError(f"Confirmation of '{pid}' references unknown batch '{ev.batch_id}'.")
                if pid not in batch.proposal_ids:
                    raise ValueError(f"'{pid}' is not a member of batch '{ev.batch_id}'.")
                ordinal = batch.proposal_ids.index(pid) + 1
                if ordinal not in ev.selected_ordinals:
                    raise ValueError(
                        f"Confirmation of '{pid}' is not backed by its ordinal {ordinal} in the batch."
                    )
            elif not ev.selected_ordinals:
                raise ValueError(
                    f"Confirmation of '{pid}' carries no selected ordinal: version-only tasks "
                    f"never confirm a mutation (VM4)."
                )
            statuses[pid] = ProposalStatus.CONFIRMED
        elif ev.kind == LedgerEventKind.REJECTED:
            if current != ProposalStatus.PENDING:
                raise ValueError(f"Cannot reject '{pid}' in status {current.value}.")
            statuses[pid] = ProposalStatus.REJECTED
        elif ev.kind == LedgerEventKind.DEFERRED:
            if current != ProposalStatus.PENDING:
                raise ValueError(f"Cannot defer '{pid}' in status {current.value}.")
            deferrals[pid] = deferrals.get(pid, 0) + 1
        elif ev.kind == LedgerEventKind.EXPIRED:
            if current != ProposalStatus.PENDING:
                raise ValueError(f"Cannot expire '{pid}' in status {current.value}.")
            statuses[pid] = ProposalStatus.EXPIRED
        elif ev.kind == LedgerEventKind.SUPERSEDED:
            if current not in (ProposalStatus.PENDING, ProposalStatus.CONFIRMED):
                raise ValueError(f"Cannot supersede '{pid}' in status {current.value}.")
            statuses[pid] = ProposalStatus.SUPERSEDED
        elif ev.kind == LedgerEventKind.APPLIED:
            if current != ProposalStatus.CONFIRMED:
                raise ValueError(
                    f"Apply-Without-Confirm violation (VM4): '{pid}' is in status {current.value}."
                )
            if ev.vector_digest_before != head_now:
                raise ValueError(
                    f"Broken digest chain on '{pid}': before={ev.vector_digest_before[:12]}... "
                    f"does not continue the ledger head."
                )
            statuses[pid] = ProposalStatus.APPLIED
            research_open_at = None
            applied.append(
                {
                    "proposal_id": pid,
                    "before": ev.vector_digest_before,
                    "after": ev.vector_digest_after,
                    "tx_id": ev.chronicle_tx_id,
                    "anchor_kind": proposals[pid].anchor_kind.value,
                }
            )
        else:  # pragma: no cover - exhaustive enum
            raise ValueError(f"Unhandled ledger event kind {ev.kind.value}.")

    return VectorLedgerState(
        baseline_digest=baseline_digest,
        baseline_version=baseline_version,
        baseline_anchor_digests=baseline_anchors,
        proposals=proposals,
        statuses=statuses,
        deferrals=deferrals,
        batches=batches,
        applied=tuple(applied),
        last_reaffirmed_digest=reaffirmed_digest,
        last_reaffirmed_at=reaffirmed_at,
        last_sealed_digest=sealed_digest,
        last_sealed_version=sealed_version or (baseline_version if sealed_digest else None),
        last_sealed_pr_ref=sealed_pr_ref,
        last_sealed_at=sealed_at,
        research_window_open_at=research_open_at,
        events_count=len(events),
    )


class VectorMutationLedger:
    """Crash-safe append-only ledger over `.isai/vector_ledger.jsonl`."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.path = self.repo_root / VECTOR_LEDGER_REL_PATH

    # -- reading ---------------------------------------------------------
    def read_events(self) -> list[VectorLedgerEvent]:
        if not self.path.is_file():
            return []
        events: list[VectorLedgerEvent] = []
        for index, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                events.append(VectorLedgerEvent.model_validate_json(stripped))
            except Exception as exc:  # pragma: no cover - defensive
                raise ValueError(f"Corrupted vector ledger line {index}: {exc}") from exc
        return events

    def state(self) -> VectorLedgerState:
        return fold_events(self.read_events())

    def is_initialized(self) -> bool:
        return any(ev.kind == LedgerEventKind.BASELINE for ev in self.read_events())

    # -- writing ---------------------------------------------------------
    def _serialize(self, events: list[VectorLedgerEvent]) -> str:
        return "".join(
            json.dumps(ev.model_dump(mode="json"), ensure_ascii=False, sort_keys=True) + "\n"
            for ev in events
        )

    def append(self, **payload: Any) -> VectorLedgerEvent:
        """Validate the transition, then atomically append the event under the repository lock."""
        with repository_write_lock(self.repo_root):
            events = self.read_events()
            fold_events(events)  # fail-closed on any pre-existing corruption
            event = VectorLedgerEvent(
                seq=(events[-1].seq + 1) if events else 1,
                event_id=f"VL-{(events[-1].seq + 1) if events else 1:05d}",
                timestamp_utc=utc_now_iso(),
                **payload,
            )
            fold_events([*events, event])
            atomic_write_text(self.path, self._serialize([*events, event]))
            return event

    def initialize(self, vector: MasterVectorSpec, note: str | None = None) -> VectorLedgerEvent:
        """Anchor the ledger genesis to the current live vector (idempotent)."""
        if self.is_initialized():
            raise ValueError("Vector ledger already has a BASELINE genesis event.")
        return self.append(
            kind=LedgerEventKind.BASELINE,
            channel=ConfirmationChannel.BASELINE,
            operator_note=note,
            baseline_digest=vector_profile_digest(vector),
            baseline_version=vector.version,
            baseline_anchor_digests=anchor_digest_profile(vector),
            vector_digest_after=vector_profile_digest(vector),
        )

    # -- lifecycle operations -------------------------------------------
    def propose(self, proposal: VectorMutationProposal) -> VectorLedgerEvent:
        """Register one candidate mutation of the vector (a *request*, never a consent)."""
        return self.append(
            kind=LedgerEventKind.PROPOSED,
            channel=ConfirmationChannel.NONE,
            proposal=proposal,
        )

    def open_batch(
        self,
        proposal_ids: tuple[str, ...],
        *,
        base_vector_digest: str,
        note: str | None = None,
    ) -> VectorLedgerEvent:
        """
        Register the numbered implementation request (`VMB-<dddd>`) over existing proposals.

        Ordinals are positional: the n-th `proposal_ids` entry is mutation number `n`.
        Proposals absent from a batch are not offered, so they can never be ratified.
        """
        state = self.state()
        batch = VectorMutationBatch(
            batch_id=state.next_batch_id(),
            base_vector_digest=base_vector_digest,
            proposal_ids=proposal_ids,
            created_at_utc=utc_now_iso(),
        )
        return self.append(
            kind=LedgerEventKind.BATCH_PROPOSED,
            channel=ConfirmationChannel.NONE,
            batch=batch,
            batch_id=batch.batch_id,
            operator_note=note,
        )

    def confirm(
        self,
        proposal_id: str,
        note: str | None = None,
        *,
        batch_id: str | None = None,
        selected_ordinals: tuple[int, ...] = (),
    ) -> VectorLedgerEvent:
        """Confirm one proposal — reachable only from a numbered operator task (`VM4`)."""
        return self.append(
            kind=LedgerEventKind.CONFIRMED,
            channel=ConfirmationChannel.OPERATOR_TASK,
            proposal_id=proposal_id,
            batch_id=batch_id,
            selected_ordinals=selected_ordinals,
            operator_note=note,
        )

    def reject(
        self,
        proposal_id: str,
        note: str | None = None,
        *,
        batch_id: str | None = None,
        selected_ordinals: tuple[int, ...] = (),
    ) -> VectorLedgerEvent:
        return self.append(
            kind=LedgerEventKind.REJECTED,
            channel=ConfirmationChannel.OPERATOR_TASK,
            proposal_id=proposal_id,
            batch_id=batch_id,
            selected_ordinals=selected_ordinals,
            operator_note=note,
        )

    def defer(self, proposal_id: str, note: str | None = None) -> VectorLedgerEvent:
        return self.append(
            kind=LedgerEventKind.DEFERRED,
            channel=ConfirmationChannel.NONE,
            proposal_id=proposal_id,
            operator_note=note,
        )

    def expire(self, proposal_id: str, note: str | None = None) -> VectorLedgerEvent:
        return self.append(
            kind=LedgerEventKind.EXPIRED,
            channel=ConfirmationChannel.NONE,
            proposal_id=proposal_id,
            operator_note=note,
        )

    def supersede(self, proposal_id: str, note: str | None = None) -> VectorLedgerEvent:
        return self.append(
            kind=LedgerEventKind.SUPERSEDED,
            channel=ConfirmationChannel.NONE,
            proposal_id=proposal_id,
            operator_note=note,
        )

    def open_research_window(self, vector: MasterVectorSpec, note: str | None = None) -> VectorLedgerEvent:
        """Mark that the post-prompt audit/research window is still open (no decision yet)."""
        state = self.state()
        return self.append(
            kind=LedgerEventKind.RESEARCH_WINDOW_OPENED,
            channel=ConfirmationChannel.NONE,
            operator_note=note,
            vector_digest_after=state.ledger_head(),
        )

    def reaffirm_version(self, vector: MasterVectorSpec, note: str | None = None) -> VectorLedgerEvent:
        """Ratify the current version without implementing any mutation (`VM4`, task w/o numbers)."""
        return self.append(
            kind=LedgerEventKind.VERSION_REAFFIRMED,
            channel=ConfirmationChannel.OPERATOR_TASK,
            operator_note=note,
            vector_digest_after=vector_profile_digest(vector),
        )

    def seal(self, vector: MasterVectorSpec, *, pr_ref: str) -> VectorLedgerEvent:
        """
        Seal the live vector as the confirmed version of the last pull request (`VM5`).

        This is what makes "the current confirmed version is the version of the last PR"
        machine-checkable: applied mutations that were never sealed remain visibly unreleased.
        """
        state = self.state()
        head = state.ledger_head()
        if head != vector_profile_digest(vector):
            raise ValueError(
                "SEALED requires the live vector to equal the ledger head; "
                "apply or re-propose the outstanding mutations first."
            )
        if not pr_ref.strip():
            raise ValueError("SEALED requires a non-empty pull-request reference.")
        return self.append(
            kind=LedgerEventKind.SEALED,
            channel=ConfirmationChannel.OPERATOR_TASK,
            operator_note=pr_ref.strip(),
            vector_version=vector.version,
            vector_digest_after=head,
        )

    def ingest_operator_signal(
        self,
        signal: OperatorSignal,
        vector: MasterVectorSpec,
        *,
        note: str | None = None,
        auto_apply: bool = True,
        apply_summary: str | None = None,
    ) -> dict[str, Any]:
        """
        Apply the `VM3`/`VM4`/`VM8` decision table for one operator prompt.

        * no confirmation task -> nothing changes: the last confirmed version stays in force and
          the selection of promising mutations proceeds from it;
        * confirmation task **without** numbers -> the current version is ratified and **no**
          mutation is implemented;
        * confirmation task **with** numbers -> exactly those ordinals of the latest numbered
          batch are confirmed and (with `auto_apply`) materialised atomically in the same gate.
          Ordinals outside the batch are refused explicitly, never ignored.
        """
        state = self.state()
        result: dict[str, Any] = {
            "task_present": signal.task_present,
            "legacy_phrase_refused": signal.legacy_phrase_present,
            "version_reaffirmed": False,
            "batch_id": None,
            "selected_ordinals": [],
            "confirmed": [],
            "rejected": [],
            "applied": [],
            "apply_refusals": [],
            "deferred": [],
            "expired": [],
            "superseded": [],
            "unknown_ordinals": [],
            "stale_ordinals": [],
        }
        if not signal.task_present:
            # No confirmation task: the current (last confirmed) version simply stays in force.
            # Nothing is ratified, nothing is deferred, nothing is applied.
            return result

        batch = state.latest_batch()
        result["batch_id"] = batch.batch_id if batch else None

        if not signal.confirms_any_mutation or batch is None:
            # A confirmation task that lists no numbers ratifies the version and implements nothing.
            self.reaffirm_version(
                vector,
                note=note
                or "Explicit task without mutation numbers: the current version is confirmed; "
                "no mutation is implemented.",
            )
            result["version_reaffirmed"] = True
            result["deferred"] = self._defer_unselected(batch)
            self._sweep_deferral_decay(result)
            return result

        in_range = sorted(o for o in signal.selected_ordinals if 1 <= o <= len(batch.proposal_ids))
        result["selected_ordinals"] = in_range
        result["unknown_ordinals"] = sorted(set(signal.unknown_ordinal_tokens) | (set(signal.selected_ordinals) - set(in_range)))

        for ordinal in in_range:
            pid = batch.proposal_ids[ordinal - 1]
            fresh = self.state()
            status = fresh.status_of(pid)
            if status is None or status != ProposalStatus.PENDING:
                result["stale_ordinals"].append(ordinal)
                continue
            if batch.base_vector_digest != fresh.ledger_head():
                # The vector moved after the batch was numbered: applying an old ordinal could hit
                # a neighbouring goal, so the whole selection is refused and must be re-numbered.
                result["stale_ordinals"].append(ordinal)
                continue
            self.confirm(
                pid,
                note=note or f"Ratified as mutation {ordinal} of batch {batch.batch_id}.",
                batch_id=batch.batch_id,
                selected_ordinals=tuple(in_range),
            )
            result["confirmed"].append(pid)

        if auto_apply and result["confirmed"]:
            # One atomic ceremony for the whole numbered set: composing against a single pre-image is
            # what lets the Operator ratify several mutations of the same anchor sequence at once.
            outcome = apply_confirmed_batch(
                self.repo_root,
                tuple(result["confirmed"]),
                summary=apply_summary
                or (
                    f"Ratified as numbered mutation(s) {result['selected_ordinals']} of {batch.batch_id} "
                    f"and applied in the same gate."
                ),
            )
            if outcome.applied:
                result["applied"] = list(outcome.applied_proposal_ids)
                # Proposals the atomic apply invalidated by an anchor shift are retired in the same
                # transaction; report them so the outcome never hides a decision from the Operator.
                result["superseded"] = list(outcome.superseded)
            else:
                for pid in result["confirmed"]:
                    result["apply_refusals"].append({"proposal_id": pid, "reason": outcome.reason})
                if outcome.reason and (
                    "Stale" in outcome.reason
                    or "Invalid mutation" in outcome.reason
                    or "No-Op" in outcome.reason
                ):
                    # The Operator ratified something the ledger can no longer deliver. Retire the
                    # ratification explicitly instead of leaving an un-auditable wedge behind.
                    for pid in result["confirmed"]:
                        self.supersede(
                            pid,
                            note=(
                                f"Ratification could not be delivered ({outcome.reason}); "
                                f"re-propose against the live vector."
                            ),
                        )
                        result["superseded"].append(pid)

        result["deferred"] = self._defer_unselected(batch)
        self._sweep_deferral_decay(result)
        return result

    def _defer_unselected(self, batch: VectorMutationBatch | None) -> list[str]:
        """
        Defer the offered-but-not-numbered mutations by one window (`VM5`).

        A mutation the Operator was shown and did not number is *not* silently retained: it
        survives one more window and then expires, so the next request must carry fresh evidence.
        Proposals that were never offered (no batch) are untouched.
        """
        if batch is None:
            return []
        deferred: list[str] = []
        state = self.state()
        for pid in batch.proposal_ids:
            if state.status_of(pid) == ProposalStatus.PENDING:
                self.defer(pid, note="Offered in a numbered batch but not selected by the Operator (VM5).")
                deferred.append(pid)
        return deferred

    def _sweep_deferral_decay(self, result: dict[str, Any]) -> None:
        """Expire pending proposals that exhausted `MAX_DEFERRALS` (VM5)."""
        state = self.state()
        for proposal in state.pending():
            if state.deferrals.get(proposal.proposal_id, 0) >= MAX_DEFERRALS:
                self.expire(proposal.proposal_id, note="Deferral decay exceeded (VM5).")
                result["expired"].append(proposal.proposal_id)


# ---------------------------------------------------------------------------
# Deterministic mutation materialisation (the "strategy" of VM4)
# ---------------------------------------------------------------------------


class MutationApplicationError(ValueError):
    """Raised when a proposal cannot be materialised onto the live vector."""


def bump_patch_version(version: str) -> str:
    """Increment the trailing numeric component of a version string deterministically."""
    parts = version.split(".")
    for idx in range(len(parts) - 1, -1, -1):
        if parts[idx].isdigit():
            parts[idx] = str(int(parts[idx]) + 1)
            return ".".join(parts)
    return f"{version}.1"


def apply_mutation_to_vector(
    vector: MasterVectorSpec,
    proposal: VectorMutationProposal,
    *,
    auto_bump_version: bool = True,
) -> MasterVectorSpec:
    """
    Materialise one mutation onto a vector spec, purely and deterministically.

    Guarantees:
      * ADD targets the append sentinel (`index == len(sequence)`) or any free index;
      * EDIT/REMOVE require an in-range index and never silently no-op;
      * the version is bumped exactly once per applied mutation unless the mutation itself
        sets it, so every ratified revision is traceable (VM4/VM6).
    """
    kind = proposal.anchor_kind
    index = proposal.anchor_index
    text = proposal.proposed_text

    def _seq_values() -> list[str]:
        return _anchor_sequence(vector, kind)

    def _build(new_values: list[str]) -> MasterVectorSpec:
        data = vector.model_dump()
        if kind == VectorAnchorKind.NORTH_STAR:
            data["north_star_statement"] = new_values[0]
        elif kind == VectorAnchorKind.VERSION:
            data["version"] = new_values[0]
        elif kind == VectorAnchorKind.CORE_OBJECTIVE:
            data["core_objectives"] = tuple(new_values)
        elif kind == VectorAnchorKind.ANTI_GOAL:
            data["anti_goals"] = tuple(new_values)
        elif kind == VectorAnchorKind.PILLAR:
            raise MutationApplicationError(
                "PILLAR mutations must be supplied as complete pillar records, not free text."
            )
        elif kind == VectorAnchorKind.HORIZON:
            raise MutationApplicationError(
                "HORIZON mutations must be supplied as complete horizon records, not free text."
            )
        return MasterVectorSpec.model_validate(data)

    if kind == VectorAnchorKind.PILLAR or kind == VectorAnchorKind.HORIZON:
        values = _seq_values()
        if proposal.mutation_kind == MutationKind.ADD:
            if index != len(values):
                raise MutationApplicationError(f"ADD to '{kind.value}' must target the append sentinel.")
            values.append(json.loads(text))
        elif proposal.mutation_kind == MutationKind.EDIT:
            if not 0 <= index < len(values):
                raise MutationApplicationError(f"EDIT index {index} out of range for '{kind.value}'.")
            values[index] = json.loads(text)
        else:
            if not 0 <= index < len(values):
                raise MutationApplicationError(f"REMOVE index {index} out of range for '{kind.value}'.")
            values.pop(index)
        data = vector.model_dump()
        if kind == VectorAnchorKind.PILLAR:
            data["architectural_pillars"] = tuple(values)
        else:
            data["evolution_horizons"] = tuple(values)
        result = MasterVectorSpec.model_validate(data)
        return result if kind == VectorAnchorKind.VERSION or not auto_bump_version else (
            result.model_copy(update={"version": bump_patch_version(result.version)})
        )

    values = _seq_values()
    singular = kind in (VectorAnchorKind.NORTH_STAR, VectorAnchorKind.VERSION)
    if proposal.mutation_kind == MutationKind.ADD:
        if singular:
            if index != 0:
                raise MutationApplicationError(f"'{kind.value}' is singular; ADD targets index 0.")
            values = [text]
        elif index == len(values):
            values.append(text)
        elif 0 <= index <= len(values):
            values.insert(index, text)
        else:
            raise MutationApplicationError(f"ADD index {index} out of range for '{kind.value}'.")
    elif proposal.mutation_kind == MutationKind.EDIT:
        if singular:
            if index != 0:
                raise MutationApplicationError(f"'{kind.value}' is singular; EDIT targets index 0.")
            values = [text]
        else:
            if not 0 <= index < len(values):
                raise MutationApplicationError(f"EDIT index {index} out of range for '{kind.value}'.")
            values[index] = text
    else:
        if singular:
            raise MutationApplicationError(f"'{kind.value}' is a mandatory anchor and cannot be removed.")
        if not 0 <= index < len(values):
            raise MutationApplicationError(f"REMOVE index {index} out of range for '{kind.value}'.")
        values.pop(index)

    result = _build(values)
    if auto_bump_version and kind != VectorAnchorKind.VERSION:
        result = result.model_copy(update={"version": bump_patch_version(result.version)})
    return result


def render_vector_module(vector: MasterVectorSpec) -> str:
    """Render a deterministic `.isai/vector.py` module carrying exactly this spec (pure AST data)."""
    data = vector.model_dump(mode="json")
    lines = [
        '"""Canonical Master Goal & Orientation Vector of ISyncAI (ISAI v' + vector.version + ')."""',
        "",
        "from __future__ import annotations",
        "",
        "from isai.domain_models import MasterVectorHorizon, MasterVectorPillar, MasterVectorSpec",
        "",
        "MASTER_VECTOR = MasterVectorSpec(",
        f"    version={data['version']!r},",
        f"    mutability_policy=({data['mutability_policy']!r}),",
        f"    north_star_statement=({data['north_star_statement']!r}),",
        "    core_objectives=(",
    ]
    for item in data["core_objectives"]:
        lines.append(f"        {item!r},")
    lines.append("    ),")
    lines.append("    architectural_pillars=(")
    for pillar in data["architectural_pillars"]:
        lines.append("        MasterVectorPillar(")
        for key in ("pillar_id", "title", "essence"):
            lines.append(f"            {key}={pillar[key]!r},")
        lines.append("            governing_axioms=(")
        for ax in pillar["governing_axioms"]:
            lines.append(f"                {ax!r},")
        lines.append("            ),")
        lines.append("            mechanisms=(")
        for mech in pillar["mechanisms"]:
            lines.append(f"                {mech!r},")
        lines.append("            ),")
        lines.append("        ),")
    lines.append("    ),")
    lines.append("    evolution_horizons=(")
    for horizon in data["evolution_horizons"]:
        lines.append("        MasterVectorHorizon(")
        for key in ("stage", "focus", "exit_condition"):
            lines.append(f"            {key}={horizon[key]!r},")
        lines.append("        ),")
    lines.append("    ),")
    lines.append("    anti_goals=(")
    for item in data["anti_goals"]:
        lines.append(f"        {item!r},")
    lines.append("    ),")
    lines.append(")")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# VM4 apply ceremony
# ---------------------------------------------------------------------------


class ApplyResult(BaseModel):
    """Outcome of a confirm -> mutate -> chronicle -> apply ceremony."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    proposal_id: str
    applied: bool
    chronicle_tx_id: str | None = None
    revision: int | None = None
    digest_before: str | None = None
    digest_after: str | None = None
    reason: str | None = None
    superseded: tuple[str, ...] = ()
    applied_proposal_ids: tuple[str, ...] = ()


def _check_candidate(
    live_vector: MasterVectorSpec,
    state: VectorLedgerState,
    proposal: VectorMutationProposal,
) -> str | None:
    """Return a typed refusal reason when a proposal can no longer be delivered, else None."""
    status = state.status_of(proposal.proposal_id)
    if status is None:
        return f"Unknown proposal '{proposal.proposal_id}'."
    if status != ProposalStatus.CONFIRMED:
        return f"Apply-Without-Confirm (VM4): proposal is in status {status.value}."
    if proposal.base_vector_digest != state.ledger_head():
        return (
            "Stale proposal (VM2/VM6): another mutation was applied after this proposal was "
            "raised, so its anchor indices may have shifted; re-propose against the live vector."
        )
    if (
        anchor_fingerprint(live_vector, proposal.anchor_kind, proposal.anchor_index)
        != proposal.anchor_fingerprint
    ):
        return (
            "Stale anchor (VM2): the addressed vector anchor changed after the proposal was "
            "raised; re-propose against the live vector before applying."
        )
    return None


def apply_confirmed_proposal(
    repo_root: Path,
    proposal_id: str,
    vector: MasterVectorSpec | None = None,
    *,
    summary: str,
    actor: str = "ISAI-Vector-Chronitect",
    auto_bump_version: bool = True,
) -> ApplyResult:
    """Execute the VM4 apply ceremony for a single confirmed proposal."""
    return apply_confirmed_batch(
        repo_root,
        (proposal_id,),
        vector,
        summary=summary,
        actor=actor,
        auto_bump_version=auto_bump_version,
    )


def _compose_ratification_set(
    live_vector: MasterVectorSpec,
    ordered: list[VectorMutationProposal],
) -> tuple[MasterVectorSpec, list[tuple[VectorMutationProposal, str, str]]]:
    """
    Fold a numbered ratification set onto one pre-image, order-independently (`VM4`).

    Why not "apply them one by one in ordinal order": every proposal was numbered against the
    *live* pre-image, so a mutation that inserts or removes at index `i` shifts every anchor from
    `i` onwards for the next member. A naive loop would then either refuse the second member as
    stale or — worse — land it on a neighbouring anchor. Two rules make the composition faithful:

      * **tail-first** — fold from the end of each anchor sequence backwards, so a member is always
        composed onto a prefix that no later member can move;
      * **the sentinel stays a sentinel** — an ADD numbered at `len(sequence)` means "append", so it
        is re-resolved to the current length each time instead of being pinned to a stale index.

    Returns the composed vector and one `(proposal, digest_before, digest_after)` step per member in
    the order the fold actually happened, which is the contiguous digest chain the ledger records.
    """
    anchor_rank = {
        VectorAnchorKind.CORE_OBJECTIVE: 0,
        VectorAnchorKind.ANTI_GOAL: 0,
        VectorAnchorKind.PILLAR: 0,
        VectorAnchorKind.HORIZON: 0,
        VectorAnchorKind.NORTH_STAR: 1,
        VectorAnchorKind.VERSION: 1,
    }
    composition_order = sorted(
        enumerate(ordered),
        key=lambda item: (anchor_rank.get(item[1].anchor_kind, 0), -item[1].anchor_index, item[0]),
    )
    baseline_lengths = {
        kind: len(_anchor_sequence(live_vector, kind))
        for kind in (
            VectorAnchorKind.CORE_OBJECTIVE,
            VectorAnchorKind.ANTI_GOAL,
            VectorAnchorKind.PILLAR,
            VectorAnchorKind.HORIZON,
        )
    }

    composed = live_vector
    steps: list[tuple[VectorMutationProposal, str, str]] = []
    for _, proposal in composition_order:
        target = proposal
        if (
            proposal.mutation_kind == MutationKind.ADD
            and baseline_lengths.get(proposal.anchor_kind) == proposal.anchor_index
        ):
            live_length = len(_anchor_sequence(composed, proposal.anchor_kind))
            if live_length != proposal.anchor_index:
                target = proposal.model_copy(update={"anchor_index": live_length})
        before = vector_profile_digest(composed)
        composed = apply_mutation_to_vector(composed, target, auto_bump_version=False)
        steps.append((proposal, before, vector_profile_digest(composed)))
    return composed, steps


def apply_confirmed_batch(
    repo_root: Path,
    proposal_ids: tuple[str, ...],
    vector: MasterVectorSpec | None = None,
    *,
    summary: str,
    actor: str = "ISAI-Vector-Chronitect",
    auto_bump_version: bool = True,
) -> ApplyResult:
    """
    Execute the VM4 apply ceremony for an *ordered* ratification set — atomically.

    Why a batch rather than a loop: a numbered request may ratify several mutations of the same
    sequence (say ADD at the append sentinel and EDIT at index 2). Applying them one by one would
    shift the anchor of the next one and honestly refuse it as stale, which would silently drop a
    mutation the Operator explicitly numbered. The set is therefore *composed* against a single
    pre-image and committed as one atomic transaction:

      1. **Preflight** — every member must be CONFIRMED, bound to the current ledger head and to a
         still-matching anchor fingerprint. Any violation refuses the *whole* set, never a prefix.
      2. **Compose** — mutations are folded in ordinal order onto an in-memory vector; a member that
         becomes a no-op after composition is refused (VM4 forbids empty mutations).
      3. **Commit** — `.isai/vector.py`, `VISION.md`, one Chronicle `MUTATE_VECTOR` event, the
         refreshed `state_snapshot.json`, the `APPLIED` events and the auto-supersessions of
         invalidated proposals are written as one batch; any failure rolls everything back.
    """
    from isai.engine import build_clean_snapshot, read_chronicle
    from isai.protocol import ChronicleEvent as _ChronicleEvent

    root = repo_root.resolve()
    ledger = VectorMutationLedger(root)
    state = ledger.state()

    ordered: list[VectorMutationProposal] = []
    for pid in proposal_ids:
        if pid in {p.proposal_id for p in ordered}:
            return ApplyResult(
                proposal_id=pid,
                applied=False,
                reason=f"Duplicate proposal '{pid}' in one ratification set (Redundancy=FATAL).",
            )
        proposal = state.proposals.get(pid)
        if proposal is None:
            return ApplyResult(proposal_id=pid, applied=False, reason=f"Unknown proposal '{pid}'.")
        refusal = _check_candidate(vector if vector is not None else load_repo_master_vector(root), state, proposal)
        if refusal is not None:
            return ApplyResult(proposal_id=pid, applied=False, reason=refusal)
        ordered.append(proposal)

    live_vector = vector if vector is not None else load_repo_master_vector(root)
    digest_before = vector_profile_digest(live_vector)

    composed, steps = _compose_ratification_set(live_vector, ordered)
    mutated = (
        composed.model_copy(update={"version": bump_patch_version(composed.version)})
        if auto_bump_version and ordered
        else composed
    )
    digest_after = vector_profile_digest(mutated)
    if digest_after == digest_before:
        return ApplyResult(
            proposal_id=ordered[0].proposal_id,
            applied=False,
            reason="No-Op ratification set (VM4): the vector would not change.",
        )

    events = read_chronicle(root)
    revision = (events[-1].revision + 1) if events else 1
    tx_id = f"TX-{revision:04d}"
    chronicle_event = _ChronicleEvent(
        tx_id=tx_id,
        revision=revision,
        timestamp_utc=utc_now_iso(),
        actor=actor,
        phase_ref="isai://root#MasterVector",
        operation="MUTATE_VECTOR",
        touched_refs=("isai://root#MasterVector", "isai://root#VectorMutationLedger"),
        interface_changed=False,
        operator_approved=True,
        summary=summary,
    )
    ledger_events = ledger.read_events()
    fold_events(ledger_events)

    next_seq = (ledger_events[-1].seq + 1) if ledger_events else 1
    # Walk the composition again to build a contiguous digest chain: every APPLIED event records
    # the exact pre-image it was materialised from and the digest the next one continues from.
    applied_events: list[VectorLedgerEvent] = []
    for proposal, before, after in steps:
        seq = next_seq + len(applied_events)
        applied_events.append(
            VectorLedgerEvent(
                seq=seq,
                event_id=f"VL-{seq:05d}",
                timestamp_utc=utc_now_iso(),
                kind=LedgerEventKind.APPLIED,
                channel=ConfirmationChannel.OPERATOR_TASK,
                proposal_id=proposal.proposal_id,
                vector_digest_before=before,
                vector_digest_after=after,
                chronicle_tx_id=tx_id,
            )
        )
    if auto_bump_version and ordered:
        # The committed spec is the composition plus exactly one patch bump; nothing else may differ.
        assert vector_profile_digest(
            composed.model_copy(update={"version": mutated.version})
        ) == digest_after, "composition diverged from the committed vector"  # pragma: no cover
        # The bump is materialised *by the last mutation* of the set, so the chain must close on the
        # committed digest — otherwise the ledger head would not match the live vector (VM6 drift).
        applied_events[-1] = applied_events[-1].model_copy(update={"vector_digest_after": digest_after})

    snapshot_path = root / "tasks" / ".isai" / "state_snapshot.json"
    previous_snapshot = (
        SystemStateSnapshot.model_validate_json(snapshot_path.read_text(encoding="utf-8"))
        if snapshot_path.is_file()
        else None
    )
    carried_tasks = previous_snapshot.active_tasks if previous_snapshot else ()
    carried_handles = previous_snapshot.open_handles if previous_snapshot else ()
    snapshot = build_clean_snapshot(
        root,
        revision=revision,
        active_tasks=carried_tasks,
        open_handles=carried_handles,
        audit_status="STAGING" if carried_tasks else "VALID",
    )
    # `build_clean_snapshot` re-reads `.isai/vector.py` from disk, which still holds the *pre-apply*
    # spec at this point (the batch has not been committed yet). Pin the projected fields to the
    # materialised spec so snapshot, VISION.md and vector.py never disagree inside one transaction.
    snapshot = snapshot.model_copy(
        update={
            "master_vector_version": mutated.version,
            "master_vector_digest": digest_after,
        }
    )
    chronicle_payload = "".join(
        json.dumps(ev.model_dump(mode="json"), ensure_ascii=False, sort_keys=True) + "\n"
        for ev in [*events, chronicle_event]
    )
    # Auto-supersede pending proposals invalidated by this apply: an index shift must never leave
    # an orphaned, un-appliable proposal behind (VM5/VM6 hygiene), and must never auto-apply.
    superseded_events: list[VectorLedgerEvent] = []
    applied_ids = {p.proposal_id for p in ordered}
    for other in state.pending() + state.confirmed():
        if other.proposal_id in applied_ids:
            continue
        if (
            anchor_fingerprint(mutated, other.anchor_kind, other.anchor_index)
            != other.anchor_fingerprint
        ):
            seq = next_seq + len(applied_events) + len(superseded_events)
            superseded_events.append(
                VectorLedgerEvent(
                    seq=seq,
                    event_id=f"VL-{seq:05d}",
                    timestamp_utc=utc_now_iso(),
                    kind=LedgerEventKind.SUPERSEDED,
                    channel=ConfirmationChannel.NONE,
                    proposal_id=other.proposal_id,
                    operator_note=(
                        f"Superseded by applied mutation batch ({', '.join(sorted(applied_ids))}) — anchor shift."
                    ),
                )
            )
    final_events = [*ledger_events, *applied_events, *superseded_events]
    fold_events(final_events)

    # Re-probe the materialised module: it must parse and round-trip to the exact same digest.
    rendered_module = render_vector_module(mutated)
    probe_namespace: dict[str, Any] = {}
    exec(compile(rendered_module, "<vector_projection>", "exec"), probe_namespace)  # noqa: S102
    if probe_namespace["MASTER_VECTOR"].spec_digest() != digest_after:
        return ApplyResult(
            proposal_id=ordered[0].proposal_id,
            applied=False,
            reason="Projection round-trip failure: rendered vector.py does not reproduce the mutated digest.",
        )

    atomic_transaction_batch(
        writes={
            root / ".isai" / "vector.py": rendered_module.encode("utf-8"),
            root / "VISION.md": mutated.render_markdown().encode("utf-8"),
            root / ".isai" / "chronicle.jsonl": chronicle_payload.encode("utf-8"),
            ledger.path: ledger._serialize(final_events).encode("utf-8"),
            snapshot_path: (snapshot.model_dump_json(indent=2) + "\n").encode("utf-8"),
        },
        lock_root=root,
    )
    return ApplyResult(
        proposal_id=ordered[0].proposal_id,
        applied=True,
        chronicle_tx_id=tx_id,
        revision=revision,
        digest_before=digest_before,
        digest_after=digest_after,
        superseded=tuple(ev.proposal_id for ev in superseded_events if ev.proposal_id),
        applied_proposal_ids=tuple(p.proposal_id for p in ordered),
    )


# ---------------------------------------------------------------------------
# VM5 / VM6 derived deviations
# ---------------------------------------------------------------------------


class LedgerDeviation(BaseModel):
    """A derived governance deviation of the vector ledger."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    severity: Literal["CRITICAL", "WARNING"]
    message: str


def render_numbered_mutations(
    proposals: tuple[VectorMutationProposal, ...],
    *,
    batch: VectorMutationBatch | None = None,
    header: str = "### Запрос на реализацию мутаций вектора системы (`isai://root#MasterVector`)",
    footer: str | None = None,
) -> str:
    """
    Render the numbered implementation request (`VM4`).

    Each entry is a *number* the Operator can cite back, its anchor, the exact new text, its
    justification, its evidence and its blast radius — informed consent, never a blind pick.
    The block carries no checkbox: consent exists only as the separate explicit task
    `подтвердить мутации вектора системы` with the selected numbers.
    """
    if not proposals:
        return ""
    batch_label = f" `{batch.batch_id}`" if batch is not None else ""
    version_note = (
        f"`base={batch.base_vector_digest[:12]}…`" if batch is not None else ""
    )
    lines = [f"{header}{batch_label}", ""]
    for ordinal, proposal in enumerate(proposals, start=1):
        lines.append(
            f"{ordinal}. **{proposal.proposal_id}** `{proposal.mutation_kind.value}` "
            f"{proposal.anchor_kind.value}[{proposal.anchor_index}] — {proposal.anchor_label}"
        )
        lines.append(f"   - **Обоснование:** {proposal.rationale}")
        lines.append(
            f"   - **Предлагаемый текст:** {proposal.proposed_text} "
            f"*(эффект: {proposal.expected_benefit}; риск: {proposal.risk_level.value})*"
        )
        lines.append(
            f"   - **Доказательства:** {', '.join(proposal.evidence_refs)} | "
            f"`anchor={proposal.anchor_fingerprint[:12]}…`"
        )
    lines.append("")
    confirm_example = ", ".join(str(i) for i in range(1, min(2, len(proposals)) + 1))
    lines.append(
        f"> Подтверждение — отдельная явная задача `подтвердить мутации вектора системы: {confirm_example}` "
        f"с номерами реализуемых мутаций. Задача без номеров подтверждает текущую версию без реализации; "
        f"при отсутствии задачи остаётся последняя подтверждённая версия (версия последнего PR)."
    )
    if version_note:
        lines.append(f"> Нумерация привязана к `{batch_label.strip()}` {version_note}.")
    if footer:
        lines.append("")
        lines.append(footer)
    return "\n".join(lines) + "\n"


def evaluate_ledger_deviations(
    state: VectorLedgerState,
    vector: MasterVectorSpec,
) -> list[LedgerDeviation]:
    """Derive governance deviations from the folded ledger against the live vector."""
    deviations: list[LedgerDeviation] = []
    if state.baseline_digest is None:
        return [
            LedgerDeviation(
                code="LEDGER_NOT_INITIALIZED",
                severity="CRITICAL",
                message="Vector mutation ledger has no BASELINE genesis event.",
            )
        ]

    for proposal in state.confirmed():
        deviations.append(
            LedgerDeviation(
                code="CONFIRMED_MUTATION_UNAPPLIED",
                severity="CRITICAL",
                message=(
                    f"Proposal '{proposal.proposal_id}' was confirmed by the Operator but never "
                    f"applied to `.isai/vector.py` (VM4): the ratified goal vector is not live."
                ),
            )
        )

    unreleased = state.unreleased_mutations()
    if unreleased:
        pending_ids = ", ".join(item["proposal_id"] for item in unreleased)
        deviations.append(
            LedgerDeviation(
                code="UNRELEASED_RATIFIED_MUTATION",
                severity="CRITICAL",
                message=(
                    f"{len(unreleased)} ratified mutation(s) [{pending_ids}] are applied but not sealed "
                    f"into a pull request: the confirmed version must be the version of the last PR "
                    f"(VM5). Seal it with `isai vector seal --pr <ref>` once the PR is open."
                ),
            )
        )

    latest_batch = state.latest_batch()
    if latest_batch is not None and latest_batch.base_vector_digest != state.ledger_head():
        # A consumed batch (every member terminal) is history, not a pending request: only a batch
        # that still offers a live mutation against a shifted vector is worth a warning.
        still_offerable = any(
            state.status_of(pid) in (ProposalStatus.PENDING, ProposalStatus.CONFIRMED)
            for pid in latest_batch.proposal_ids
        )
        if still_offerable:
            deviations.append(
                LedgerDeviation(
                    code="STALE_NUMBERED_BATCH",
                    severity="WARNING",
                    message=(
                        f"Batch '{latest_batch.batch_id}' is numbered against "
                        f"{latest_batch.base_vector_digest[:12]}… but the ledger head moved to "
                        f"{str(state.ledger_head())[:12]}…: re-number before asking for ratification."
                    ),
                )
            )

    for proposal in state.pending() + state.confirmed():
        if anchor_fingerprint(vector, proposal.anchor_kind, proposal.anchor_index) != proposal.anchor_fingerprint:
            deviations.append(
                LedgerDeviation(
                    code="STALE_PROPOSAL_ANCHOR",
                    # A *confirmed* yet stale proposal is a wedged ratification: the Operator approved
                    # something that can no longer be delivered. A stale PENDING proposal is normal
                    # churn and is reported as an advisory window event.
                    severity=(
                        "CRITICAL"
                        if state.status_of(proposal.proposal_id) == ProposalStatus.CONFIRMED
                        else "WARNING"
                    ),
                    message=(
                        f"Proposal '{proposal.proposal_id}' addresses "
                        f"{proposal.anchor_kind.value}[{proposal.anchor_index}] whose content changed "
                        f"after the proposal was raised; applying it blindly would mutate a "
                        f"neighbouring goal. Re-propose against the live vector."
                    ),
                )
            )

    for proposal in state.pending():
        count = state.deferrals.get(proposal.proposal_id, 0)
        if count >= MAX_DEFERRALS:
            deviations.append(
                LedgerDeviation(
                    code="ORPHAN_PENDING_PROPOSAL",
                    severity="CRITICAL",
                    message=(
                        f"Proposal '{proposal.proposal_id}' survived {count} deferral windows "
                        f"without a decision (VM5); it must be expired and re-proposed."
                    ),
                )
            )
        elif count > 0:
            deviations.append(
                LedgerDeviation(
                    code="DEFERRED_PENDING_PROPOSAL",
                    severity="WARNING",
                    message=(
                        f"Proposal '{proposal.proposal_id}' was deferred {count}x; "
                        f"re-surface it in the next response window."
                    ),
                )
            )

    live_head = vector_profile_digest(vector)
    ledger_head = state.applied[-1]["after"] if state.applied else state.baseline_digest
    if live_head != ledger_head:
        applied_kinds = {item["anchor_kind"] for item in state.applied}
        live_profile = anchor_digest_profile(vector)
        drifted = [
            kind
            for kind, digest in sorted(live_profile.items())
            if state.baseline_anchor_digests.get(kind) != digest
        ]
        unexplained = [kind for kind in drifted if kind not in applied_kinds]
        if unexplained:
            deviations.append(
                LedgerDeviation(
                    code="UNCONFIRMED_VECTOR_DRIFT",
                    severity="CRITICAL",
                    message=(
                        f"Vector anchors {unexplained} changed without a confirmed and applied "
                        f"proposal (VM6): silent goal mutation detected."
                    ),
                )
            )
        elif not drifted:
            deviations.append(
                LedgerDeviation(
                    code="VECTOR_DIGEST_MISMATCH",
                    severity="CRITICAL",
                    message=(
                        "Live vector profile digest diverges from the ledger head although no anchor "
                        "content changed: vector serialisation/metadata drift outside the ceremony."
                    ),
                )
            )

    version_changed = vector.version != state.baseline_version
    if state.applied and not version_changed:
        deviations.append(
            LedgerDeviation(
                code="VERSION_NOT_BUMPED",
                severity="CRITICAL",
                message=(
                    f"Vector mutations were applied but `version` is still {vector.version}: "
                    f"the ratified revision is untraceable."
                ),
            )
        )
    if version_changed and not state.applied:
        deviations.append(
            LedgerDeviation(
                code="UNCONFIRMED_VERSION_BUMP",
                severity="CRITICAL",
                message=(
                    f"Vector version changed {state.baseline_version} -> {vector.version} without any "
                    f"confirmed and applied mutation."
                ),
            )
        )

    return deviations
