"""LLM-Native Text Engineering (`isai://root#TextEngineering`) — the machine enforcement of the
`[TEXT-ENGINEERING]` circuit of the IL-1C fundamental (`TE0..TE7`, `ISAI-NVF/1.2`).

Why this module exists
----------------------
Every system folder and file is read by exactly two kinds of consumers, and they fail differently:

* a **deterministic machine** (parser, scanner, sync engine, audit) fails *structurally* — a phantom
  CLI command, a hand-edited projection, an unbound symbol;
* a **language model** fails *saliently* — a "lost in the middle" rule, a diluted instruction, a
  tokenizer-hostile neologism, a hedged event that hides what actually happened.

Text level (`TE0`) is therefore not a stylistic label but the *contract* a text signs with its
reader: it fixes the admissible syntax, the salience order and the verification duty. `TE7` makes
those duties executable: :func:`validate_text` is a pure, offline, deterministic reader.

The level table (`TE0.LevelLaw`)
--------------------------------
=================  ==============================  =========================================
Signature          Carrier                         Reader contract
=================  ==============================  =========================================
`L0_GENOME`        `README.md[0:586]` (IL-0)       both; byte-immutable
`L1_CANON`         str constants of `.isai/*.py`   machine; declarative, composed
`L2_TRANSCRIPT`    SYNC-block of `README.md`       human; *derived*, never authored
`L3_PROSE`         authored markdown               human + LLM; explanatory only
`L4_RECORD`        `*.jsonl`, `*.json`             machine; append-only evidence
`L5_CEREMONY`      ranked operator-facing blocks   human; DECIDE first, then EXECUTE
=================  ==============================  =========================================
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field

from isai.constitution import DEFAULT_BOUNDARY_IGNORE
from isai.contracts import EntityRef

# ---------------------------------------------------------------------------
# TE0: the level law
# ---------------------------------------------------------------------------

#: Byte length of the immutable IL-0 Genesis header (first 14 lines of `README.md`).
L0_GENOME_BYTE_LENGTH: int = 586

#: File families the reader visits; anything else is out of scope by construction.
TEXT_FILE_SUFFIXES: tuple[str, ...] = (".md", ".py", ".jsonl", ".json", ".toml")


class TextLevel(StrEnum):
    """
    `TE0`: the reader contract a text signs.

    Levels `L0..L4` are *carrier levels*: every file on disk signs exactly one of them by its
    physical shape, so the inventory is a partition and emptiness is a legitimate state. `L5` is a
    *delivery level*: it exists only inside a compiled RSoC packet (the ranked operator-facing
    block), never as a file, so it is reported separately and never demanded by the inventory.
    """

    L0_GENOME = "L0_GENOME"
    L1_CANON = "L1_CANON"
    L2_TRANSCRIPT = "L2_TRANSCRIPT"
    L3_PROSE = "L3_PROSE"
    L4_RECORD = "L4_RECORD"
    L5_CEREMONY = "L5_CEREMONY"


#: Levels that must be materialised on disk (a file partition).
CARRIER_LEVELS: tuple[TextLevel, ...] = (
    TextLevel.L0_GENOME,
    TextLevel.L1_CANON,
    TextLevel.L2_TRANSCRIPT,
    TextLevel.L3_PROSE,
    TextLevel.L4_RECORD,
)


#: Stable salience order of the levels: earlier levels outrank later ones on conflict (`TE5`).
LEVEL_PRECEDENCE: tuple[TextLevel, ...] = (
    TextLevel.L0_GENOME,
    TextLevel.L1_CANON,
    TextLevel.L4_RECORD,
    TextLevel.L2_TRANSCRIPT,
    TextLevel.L3_PROSE,
    TextLevel.L5_CEREMONY,
)

#: Section role a normative document must declare before it may state anything normative (`TE4`).
SECTION_ROLES: tuple[str, ...] = ("DECIDE", "EXECUTE", "EXPLAIN")

#: Closed taxonomy of hedges: an event or a rule may not hedge its own truth value (`TE6`).
HEDGE_MARKERS: tuple[str, ...] = (
    "возможно",
    "наверное",
    "вероятно",
    "кажется",
    "по-видимому",
    # `может быть` is deliberately absent: standing alone it is a hedge, but it is orthographically
    # identical to `может` + `быть` ("may be"), which is plain modality in a normative sentence such
    # as "the constitution cannot be required...". Flagging the substring would punish correct
    # grammar, and a hedge that has to be distinguished from a homograph by a regex is not a
    # reliable signal. `возможно` covers the same intent unambiguously.
    "maybe",
    "probably",
    "perhaps",
    "might be",
    "kind of",
    "sort of",
)

#: `TE2` — closed verdict vocabulary of the DSL grammar (`[MUTABILITY-LAW]`, `[RECENCY-TRIPWIRES]`).
#: These are grammar words, not symbols: they are defined once by the Genesis frame and may never
#: be extended ad hoc, which is exactly why they are a *closed* set rather than a free lexicon.
DSL_VERDICT_TOKENS: tuple[str, ...] = (
    "ABORT",
    "CONDITIONALLY_LOCKED",
    "CONSTRUCT",
    "DECIDE",
    "EXECUTE",
    "EXPLAIN",
    "FATAL",
    "FORBIDDEN",
    "HALT",
    "REQUIRED",
    "REFUSED",
    "WARNING",
)

#: `TE6` — the typed summary a chronicle/ledger event must carry to be auditable.
EVENT_SUMMARY_FIELDS: tuple[str, ...] = ("summary", "evidence", "blast_radius", "next_action")

#: Domains whose acronyms form the closed `DomainAcronym` set of `TE2.DLT-BPE`.
DOMAIN_ACRONYM_SET: tuple[str, ...] = (
    "AST",
    "BDCT",
    "BPE",
    "CLI",
    "DRY",
    "EAVT",
    "HKCC",
    "IL",
    "LLM",
    "MCP",
    "MVCC",
    "NVF",
    "PR",
    "PEP",
    "RSoC",
    "SHA",
    "TTL",
    "URI",
    "VAET",
    "VM",
    "VMP",
    "VMB",
    "VSM",
    "YAML",
    "JSON",
    "TE",
    "UTF",
)

#: `TE2` — closed registry of deliberate design names used by text before they bind to a symbol.
#: Each entry names where it is defined, so the lexicon can never grow into a private vocabulary.
DESIGN_LEXICON: dict[str, str] = {
    "FiduSys": "user/.isai/profile.py (operator archetype)",
    "Novator": "user/.isai/profile.py (operator archetype)",
    "Chronitect": "user/.isai/profile.py (operator archetype; see also `Graph-Chronitect`)",
    "AdmissionCheck": ".isai/atomic_io.py#atomic_transaction_batch (pre-commit admission gate)",
    "AttributionIndex": "knowledge/.isai/catalog.py#PAT_AUDIT_VS_RECOMMENDATION_SEPARATION",
    "BimodalPacket": "isai://root#NeuroVascularFundamental (primacy + recency slices)",
    "CarrierPurity": "isai://root#TextEngineering (TE1)",
    "ChronicleRegister": "isai://root#TextEngineering (TE6)",
    "CommandTruth": "isai://root#TextEngineering (TE3)",
    "ConfirmationTask": "isai://root#VectorMutationLedger (VM3)",
    "DiscoveryDelta": "knowledge/.isai/catalog.py#PAT_AUDIT_VS_RECOMMENDATION_SEPARATION",
    "DistillRecord": "isai://knowledge#EmpiricalCatalog (Chronicle DISTILL operation)",
    "EnzymeCheck": "isai://root#NeuroVascularFundamental (ATP-gated enzyme metaphor, P2)",
    "FrameLaw": "isai://root#TextEngineering (TE4)",
    "ImplementationRequest": "isai://root#VectorMutationLedger (VM4)",
    "LevelLaw": "isai://root#TextEngineering (TE0)",
    "MutationBatch": ".isai/vector_ledger.py#VectorMutationBatch",
    "NumberedRatification": "isai://root#VectorMutationLedger (VM4)",
    "OwnershipDelta": "knowledge/.isai/catalog.py#PAT_PRE_PR_GATE_V_AND_ATOMIC_VECTOR_APPLY",
    "PromoteRecord": "isai://root#ChronicleLedger (PROMOTE operation)",
    "SalienceOrder": "isai://root#TextEngineering (TE5)",
    "Signature": "isai://root#TextEngineering (TE0 signature of a text)",
    # -- TE2's own vocabulary: the theory must be able to name its own atoms --
    "CamelComposite": "isai://root#TextEngineering (TE2: UpperCamel token, e.g. VectorMutationLedger)",
    "SeparatedComposite": "isai://root#TextEngineering (TE2: hyphen/snake token, e.g. zero-orphan-nodes)",
    "DomainAcronym": "isai://root#TextEngineering (TE2: closed ALL-CAPS set of DOMAIN_ACRONYM_SET)",
    "SystemicCorpus": "isai://root#TextEngineering (the set of system folders and files)",
    "TextEngineering": "isai://root#TextEngineering",
    "VerifyCompile": "isai://root#TextEngineering (TE7)",
    "ZeroRedundancy": "isai://root#GenesisKernel (ZERO-Redundancy axiom)",
    # -- VM3 signal shielding: each name is one refusal rule of `parse_operator_signal` --
    "BlockQuote": ".isai/vector_ledger.py#parse_operator_signal (quoted operator text is not a task)",
    "CheckboxConsent": ".isai/vector_ledger.py (retired channel; TE3-era consent surface)",
    "EmbeddedProse": ".isai/vector_ledger.py#parse_operator_signal (a task must be a control line)",
    "FencedCode": ".isai/vector_ledger.py#_FENCE_RE (documentation can never ratify)",
    "InlineCode": ".isai/vector_ledger.py#_INLINE_CODE_RE (quoted protocol is not a signal)",
    "ISyncAI": "README.md[0:586] (the system's own name, IL-0)",
    "LegacyPhrase": ".isai/vector_ledger.py#LEGACY_PHRASE_FORMS (parsed only to be refused)",
    "SelfConfirmation": ".isai/vector_ledger.py#parse_operator_signal (agent output is never consent)",
    "SignalLine": ".isai/vector_ledger.py#parse_operator_signal (the only consent-bearing line shape)",
    "SignalSource": "isai://root#VectorMutationLedger (VM3)",
}

#: `TE5`: leading tokens that reveal the *role* of a machine-readable rule string.
_SALIENCE_PREFIXES: tuple[tuple[str, str], ...] = (
    ("STOP-", "DECIDE"),
    ("FATAL", "DECIDE"),
    ("FORBIDDEN", "DECIDE"),
    ("MUST", "DECIDE"),
    ("TE0.", "DECIDE"),
    ("TE1.", "DECIDE"),
    ("TE2.", "DECIDE"),
    ("TE3.", "DECIDE"),
    ("TE4.", "DECIDE"),
    ("TE5.", "DECIDE"),
    ("TE6.", "DECIDE"),
    ("TE7.", "DECIDE"),
    ("VM1.", "DECIDE"),
    ("VM2.", "DECIDE"),
    ("VM3.", "DECIDE"),
    ("VM4.", "DECIDE"),
    ("VM5.", "DECIDE"),
    ("VM6.", "DECIDE"),
    ("VM7.", "DECIDE"),
    ("VM8.", "DECIDE"),
    ("N1.", "DECIDE"),
    ("N2.", "DECIDE"),
    ("N3.", "DECIDE"),
    ("N4.", "DECIDE"),
    ("N5.", "DECIDE"),
    ("N6.", "DECIDE"),
    ("N7.", "DECIDE"),
    ("N8.", "DECIDE"),
    ("V1.", "DECIDE"),
    ("V2.", "DECIDE"),
    ("V3.", "DECIDE"),
    ("V4.", "DECIDE"),
    ("V5.", "DECIDE"),
    ("RUN", "EXECUTE"),
    ("=>", "EXECUTE"),
    ("Note", "EXPLAIN"),
)

#: Structured-token alphabet of `TE2.DLT-BPE`: CamelComposite | SeparatedComposite | ACRONYM.
_STRUCTURED_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9])("
    r"[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+"          # CamelComposite
    r"|[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)+"         # SeparatedComposite
    r"|[A-Z]{2,}"                                  # AcronymCandidate (ALLCAPS)
    r"|[A-Z]+[a-z]+[A-Za-z0-9]*"                   # MixedCase acronym (RSoC, MoE)
    r")(?![A-Za-z0-9])"
)

#: A token fragment with no alphanumeric content (opaque glyph soup) — `TE2` forbids it.
_OPAQUE_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9])(?:[^\w\s.,:;!?()\[\]{}\"'`*|<>=+/%$#@~^\\|-]{2,})")

#: Modules whose `L1` strings are *text* addressed to a reader and therefore carry `TE1..TE5`.
#: A structural carrier (AST, CLI plumbing, regex tables) carries code, not text, and is exempt:
#: enforcing prose rules there would flag the machine's own grammar — a category error, not a duty.
TEXT_BEARING_CARRIERS: tuple[str, ...] = (
    ".isai/neuro_vascular.py",
    ".isai/vector.py",
    ".isai/vector_ledger.py",
    ".isai/text_engineering.py",
    ".isai/node.py",
    ".isai/engine.py",
    ".isai/health_checks.py",
    ".isai/contracts.py",
    ".isai/protocol.py",
    ".isai/constitution.py",
    ".isai/domain_models.py",
    ".isai/__main__.py",
    ".isai/graph_index.py",
    ".isai/link_mutator.py",
    "tasks/.isai/node.py",
    "tasks/.isai/watchdog.py",
    "knowledge/.isai/node.py",
    "knowledge/.isai/catalog.py",
    "tests/.isai/node.py",
    "user/.isai/node.py",
    "user/.isai/profile.py",
)

#: Neo-Latin prefixes/suffixes that mark a shape as a *bound symbol* (they are real code shapes).
_BOUND_SHAPE_SUFFIXES: tuple[str, ...] = (
    "Spec",
    "Model",
    "Ledger",
    "Service",
    "Gate",
    "Kernel",
    "Vector",
    "Node",
    "Index",
    "Compiler",
    "Mutator",
    "Protocol",
    "Catalog",
    "Snapshot",
    "Report",
    "Checker",
    "Guard",
    "Registry",
    "Carrier",
    "Record",
)

_FENCE_RE = re.compile(r"^[ \t]*```[\s\S]*?^[ \t]*```", re.MULTILINE)
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
_SYNC_BLOCK_RE = re.compile(
    r"<!-- ISAI:(?:NVF_|VECTOR_)?SYNC:BEGIN -->[\s\S]*?<!-- ISAI:(?:NVF_|VECTOR_)?SYNC:END -->"
)
_CMD_RE = re.compile(r"\bisai\s+([a-z][a-z0-9-]*)(?:\s+([a-z][a-z0-9-]*))?")


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------


class TextFinding(BaseModel):
    """One `TE` deviation, always tagged with the contract that was violated."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    check: str
    level: TextLevel | None = None
    location: str
    message: str
    severity: str = "CRITICAL"


class TextReport(BaseModel):
    """Deterministic verdict of the offline text reader (`TE7`)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: str
    findings: tuple[TextFinding, ...] = ()
    levels_seen: tuple[str, ...] = ()
    files_checked: int = 0
    text_bytes: int = 0
    evidence_digest: str = ""

    @property
    def valid(self) -> bool:
        return not any(f.severity == "CRITICAL" for f in self.findings)

    def by_check(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for finding in self.findings:
            counts[finding.check] = counts.get(finding.check, 0) + 1
        return counts


# ---------------------------------------------------------------------------
# TE2: lexicon machinery
# ---------------------------------------------------------------------------


def is_balanced_fragment(text: str) -> bool:
    """True when every bracket/quote family opened in `text` is closed (`TE4` well-formedness)."""
    pairs = {")": "(", "]": "[", "}": "{", "»": "«"}
    stack: list[str] = []
    in_backtick = False
    for char in text:
        if char == "`":
            in_backtick = not in_backtick
            continue
        if in_backtick:
            continue
        if char in "([{«":
            stack.append(char)
        elif char in pairs:
            if not stack or stack.pop() != pairs[char]:
                return False
    return not stack and not in_backtick


def structured_tokens(text: str) -> list[str]:
    """Every composite/acronym token of a text — the `TE2` lexicon surface."""
    return _STRUCTURED_TOKEN_RE.findall(text)


def build_bound_vocabulary(repo_root: Path) -> set[str]:
    """
    The live symbol surface every structured token must resolve into (`TE2.DLT-BPE`).

    A token binds when it is (a) a declared symbol of `.isai/*.py`, (b) a declared CLI command,
    (c) a file name of the repository, (d) a member of the closed domain acronym set, or
    (e) a bound shape ending in a canonical artifact suffix (`...Ledger`, `...Spec`, ...).
    """
    bound: set[str] = set()
    isai_dir = repo_root / ".isai"
    # Every node owns a `.isai/` package of its own (`tasks/.isai/watchdog.py`,
    # `knowledge/.isai/catalog.py`, ...). Collecting symbols from the root kernel alone would
    # report a perfectly real component — `TaskWatchdog` — as a phantom, which is exactly the
    # kind of false positive that teaches a reader to ignore the check.
    module_files: list[Path] = []
    for pkg in sorted(repo_root.rglob(".isai")):
        if not pkg.is_dir() or DEFAULT_BOUNDARY_IGNORE.is_ignored(pkg.relative_to(repo_root)):
            continue
        module_files.extend(sorted(pkg.glob("*.py")))
        # A node owns more than its manifest: `research/lab` declares `universe.py` and
        # `e7_plasmid.py` in `owned_files`, so the classes they define are live system symbols.
        # Scanning only `.isai/*.py` reported `EpochUniverse` as a phantom even though the node
        # manifest names its file — the check was blind to everything a node owns but does not
        # keep inside its `.isai` package. A declaration is the system's own statement of what is
        # real, so it has to feed the vocabulary.
        manifest = pkg / "node.py"
        if manifest.is_file():
            try:
                tree = ast.parse(manifest.read_text(encoding="utf-8"), filename=str(manifest))
            except SyntaxError:  # pragma: no cover - audit reports manifest syntax errors
                tree = None
            if tree is not None:
                for node in ast.walk(tree):
                    if (
                        isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Name)
                        and node.func.id == "ISAINodeSpec"
                    ):
                        for kw in node.keywords:
                            if kw.arg != "owned_files" or not isinstance(kw.value, ast.Tuple):
                                continue
                            for elt in kw.value.elts:
                                if not (
                                    isinstance(elt, ast.Constant)
                                    and isinstance(elt.value, str)
                                    and elt.value.endswith(".py")
                                ):
                                    continue
                                owned = pkg.parent / elt.value
                                if owned.is_file() and owned not in module_files:
                                    module_files.append(owned)
    for py_file in module_files:
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except SyntaxError:  # pragma: no cover - the audit reports syntax errors itself
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                bound.add(node.name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        bound.add(target.id)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                bound.add(node.target.id)
            elif isinstance(node, ast.arg) and node.arg:
                bound.add(node.arg)
            elif isinstance(node, ast.keyword) and node.arg:
                # Declared symbol names travel as keyword arguments in the node manifests
                # (`SymbolBindingSpec(symbol='LinkInjector', ...)`), so an AST walk that only
                # collected class/function/assignment names would miss every bound symbol.
                bound.add(node.arg)
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    bound.add(node.value.value)
            elif isinstance(node, ast.ClassDef):
                for member in node.body:
                    if isinstance(member, (ast.ClassDef, ast.FunctionDef)):
                        bound.add(member.name)
    main_py = isai_dir / "__main__.py"
    if main_py.is_file():
        try:
            tree = ast.parse(main_py.read_text(encoding="utf-8"), filename=str(main_py))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "add_parser"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                ):
                    bound.add(node.args[0].value)
                    bound.add(node.args[0].value.replace("-", ""))
        except SyntaxError:  # pragma: no cover
            pass
    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(repo_root)
        if DEFAULT_BOUNDARY_IGNORE.is_ignored(rel):
            continue
        bound.add(path.stem)
        bound.add(path.name)
        bound.add(path.stem.replace("_", ""))
        bound.add(path.stem.replace("test_", ""))
    # Every `isai://<scope>#<Symbol>` address in the repository names a live node or symbol: the
    # address itself is the reference, so a document that cites `isai://root#NeuroVascularFundamental`
    # is naming something real even when the Python identifier differs in case or shape.
    uri_re = re.compile(r"isai://[A-Za-z0-9_./-]+(?:#([A-Za-z0-9_]+))?")
    for path in repo_root.rglob("*"):
        if not path.is_file() or path.suffix not in TEXT_FILE_SUFFIXES:
            continue
        rel = path.relative_to(repo_root)
        if DEFAULT_BOUNDARY_IGNORE.is_ignored(rel):
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):  # pragma: no cover
            continue
        for match in uri_re.finditer(content):
            symbol = match.group(1)
            if symbol:
                bound.add(symbol)
    bound.update(DOMAIN_ACRONYM_SET)
    bound.update(DSL_VERDICT_TOKENS)
    return bound


def _is_camel_composite(token: str) -> bool:
    """
    True for a multi-hump CamelComposite (`VectorMutationLedger`, `SignalSource`).

    An ALL-CAPS token is a verdict or an acronym (`FATAL`, `FORBIDDEN`, `EAVT`), never a
    CamelComposite: it belongs to the closed DSL vocabulary, and flagging it would punish the
    very discipline words the fundamental is written in.
    """
    if not token or not token[0].isupper() or "-" in token or "_" in token or token.isupper():
        return False
    return len(re.findall(r"[A-Z][a-z0-9]*", token)) >= 2


#: A definition site inside the fundamental DSL: `Term := ...` or `Term -> ...` at a word boundary.
_DEFINITION_RE = re.compile(r"(?<![A-Za-z0-9])([A-Z][A-Za-z0-9]*(?:[-_][A-Za-z0-9]+)*)\s*(?::=|=|->)")


def fundamental_definitions(repo_root: Path) -> set[str]:
    """
    Terms the IL-1C fundamental itself *defines* (`Term := ...`).

    The fundamental is the definition site of the system's vocabulary: `[LEXICON-ANCHORS]` and the
    rule bodies bind composite names (`GateA`, `ByteRollback`, `RoutineEdit`) exactly the way code
    binds symbols. A text lexicon is therefore closed over two origins — the live code surface and
    the constitutional definitions — and a term that appears in neither is a phantom.
    """
    definitions: set[str] = set()
    nvf_py = repo_root / ".isai" / "neuro_vascular.py"
    if not nvf_py.is_file():  # pragma: no cover - a broken kernel is reported elsewhere
        return definitions
    try:
        tree = ast.parse(nvf_py.read_text(encoding="utf-8"), filename=str(nvf_py))
    except SyntaxError:  # pragma: no cover
        return definitions
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            definitions.update(_DEFINITION_RE.findall(node.value))
    return definitions


def _binds(token: str, vocabulary: set[str]) -> bool:
    if token in DESIGN_LEXICON:
        # A documented design name is legitimate *text* even before it is bound to code: the
        # lexicon registers it exactly once, next to its definition, so it cannot drift silently.
        return True
    flat = token.replace("-", "").replace("_", "")
    if token in vocabulary or flat in vocabulary:
        return True
    lowered = {v.lower() for v in vocabulary}
    if token.lower() in lowered or flat.lower() in lowered:
        return True
    return False


# ---------------------------------------------------------------------------
# TE0: level classification
# ---------------------------------------------------------------------------


def classify_text(rel_path: Path, text: str) -> TextLevel:
    """
    Sign the text with its reader contract (`TE0`).

    The classification is purely structural, so it can never drift from the content it labels:
    `.jsonl`/`.json` records are evidence (`L4`), python string carriers are canon (`L1`), authored
    markdown is prose (`L3`), and a synchronised passport block inside markdown is a *transcript*
    of a machine source (`L2`) that no author may edit.
    """
    suffix = rel_path.suffix
    if suffix in (".jsonl", ".json", ".toml"):
        return TextLevel.L4_RECORD
    if suffix == ".py":
        return TextLevel.L1_CANON
    if suffix == ".md":
        if _SYNC_BLOCK_RE.search(text):
            return TextLevel.L2_TRANSCRIPT
        return TextLevel.L3_PROSE
    return TextLevel.L3_PROSE


def level_inventory(repo_root: Path) -> dict[str, list[str]]:
    """Map every in-scope text file to the level it declares; the `TE0` inventory."""
    inventory: dict[str, list[str]] = {level.value: [] for level in CARRIER_LEVELS}
    for path in sorted(repo_root.rglob("*")):
        if not path.is_file() or path.suffix not in TEXT_FILE_SUFFIXES:
            continue
        rel = path.relative_to(repo_root)
        if DEFAULT_BOUNDARY_IGNORE.is_ignored(rel):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:  # pragma: no cover - binary masquerading as text
            continue
        if rel.as_posix() == "README.md":
            inventory[TextLevel.L0_GENOME.value].append(rel.as_posix())
            continue
        inventory[classify_text(rel, text).value].append(rel.as_posix())
    return inventory


# ---------------------------------------------------------------------------
# TE1: carrier purity & projection identity
# ---------------------------------------------------------------------------


def canon_strings(py_file: Path) -> list[tuple[int, str]]:
    """
    Every *complete* normative string constant of a python module with its line number.

    Fragments of f-strings are excluded: the AST splits `f"a {b} c"` into three constants, and a
    reader that checked the fragments would report unbalanced brackets that the *runtime* text
    never has. A reader must judge the text a consumer actually sees, never the compiler's view.
    """
    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    fragments: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            for part in node.values:
                if isinstance(part, ast.Constant):
                    fragments.add(id(part))
    return [
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in fragments
    ]


def _is_rule_carrier(text: str) -> bool:
    """
    True for a *normative rule* rather than prose, help text or a message template.

    A rule states an obligation with a machine-checkable connector (`:=`, `=>`, `|`, `FATAL`,
    `FORBIDDEN`, `∨`, `∧`) and carries no sentence-level narrative flow. Help strings, field
    descriptions and error templates are `L3`-grade prose inside an `L1` carrier and are exempt.
    """
    stripped = text.strip()
    if stripped.endswith((".", "!", "?")) and " := " not in stripped and " => " not in stripped:
        return False
    connectors = sum(marker in stripped for marker in (":=", "=>", "|", "FATAL", "FORBIDDEN", ">="))
    return connectors >= 2 and len(stripped) >= 60


def _clauses(text: str) -> int:
    return len([part for part in re.split(r"[.;!?]\s", text) if part.strip()])


# ---------------------------------------------------------------------------
# TE3: command truth
# ---------------------------------------------------------------------------


def cli_surface(repo_root: Path) -> dict[str, set[str]]:
    """
    Declared commands and their subcommands, read statically from `.isai/__main__.py` (`TE3`).

    Subcommands are folded onto the *command* they belong to (`isai text check` -> `text: {check}`),
    so the surface is addressed exactly the way an Operator names it.
    """
    main_py = repo_root / ".isai" / "__main__.py"
    surface: dict[str, set[str]] = {}
    if not main_py.is_file():  # pragma: no cover - a broken kernel has no CLI at all
        return surface
    tree = ast.parse(main_py.read_text(encoding="utf-8"), filename=str(main_py))

    # Discover, in source order, which parser each `add_subparsers()` result controls. The owner is
    # resolved through the *variable* that received the parser, so `vec_p -> vector` must be learned
    # from the assignment `add_parser("vector")` before `vec_sub = vec_p.add_subparsers(...)` runs.
    var_command: dict[str, str] = {}
    subparser_owner: dict[str, str] = {}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and node.value.func.attr == "add_parser"
            and node.value.args
            and isinstance(node.value.args[0], ast.Constant)
            and isinstance(node.value.args[0].value, str)
        ):
            var_command[node.targets[0].id] = node.value.args[0].value
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and node.value.func.attr == "add_subparsers"
            and isinstance(node.value.func.value, ast.Name)
        ):
            owner_var = node.value.func.value.id
            subparser_owner[node.targets[0].id] = var_command.get(owner_var, "")
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_parser"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            continue
        name = node.args[0].value
        surface.setdefault(name, set())
        owner = node.func.value
        if isinstance(owner, ast.Name):
            parent = subparser_owner.get(owner.id)
            if parent:
                surface.setdefault(parent, set()).add(name)
    return surface


#: A command mention is a whole word: `isai systemic review` is prose, not a CLI call.
_CMD_TOKEN_RE = re.compile(r"\bisai ([a-z][a-z0-9]*(?:-[a-z0-9]+)*)(?![a-z0-9-])(?: ([a-z][a-z0-9]*(?:-[a-z0-9]+)*)(?![a-z0-9-]))?")


def _command_mentions(text: str) -> Iterable[tuple[str, str | None]]:
    for match in _CMD_TOKEN_RE.finditer(text):
        yield match.group(1), match.group(2)


# ---------------------------------------------------------------------------
# The reader
# ---------------------------------------------------------------------------


def _finding(check: str, location: str, message: str, *, level: TextLevel | None = None,
             severity: str = "CRITICAL") -> TextFinding:
    return TextFinding(
        check=check, level=level, location=location, message=message, severity=severity
    )


_HEDGE_DECLARATION_MARKERS: tuple[str, ...] = (
    "HEDGE_MARKERS",
    "hedge_roster",
    "TEXT_ENGINEERING_ROSTER",
)


def _declares_hedge_roster(rel: str, text: str) -> bool:
    """True when the file is the hedge roster, its test fixture or a documented baseline."""
    if rel in (".isai/text_engineering.py", ".isai/vector_ledger.py"):
        return True
    if "tests/" in rel:
        return True
    return any(marker in text for marker in _HEDGE_DECLARATION_MARKERS)


def _check_text_sample(
    rel: str,
    level: TextLevel,
    text: str,
    *,
    vocabulary: set[str],
    surface: dict[str, set[str]],
) -> list[TextFinding]:
    findings: list[TextFinding] = []
    is_machine_text = level in (TextLevel.L1_CANON, TextLevel.L4_RECORD)
    role = section_role(text[:160])

    # -- TE2.DLT-BPE (surface): glyph soup and mocked code spans are forbidden --------
    opaque = [m.group(0) for m in _OPAQUE_TOKEN_RE.finditer(text if is_machine_text else _INLINE_CODE_RE.sub(" ", text))]
    if opaque:
        findings.append(
            _finding(
                "TE2.DLT-BPE",
                rel,
                f"opaque non-token glyphs cannot survive BPE: {sorted(set(opaque))[:4]}",
                level=level,
            )
        )

    # -- TE3.CommandTruth: every mentioned command must exist ------------------------
    # Command truth is a property of the text *an Operator reads*: authored prose (`L3`) and the
    # normative carriers of the text circuits (`L1` strings of `TEXT-BEARING-CARRIERS`). Python
    # source is code — its identifiers and docstrings are not instructions to the Operator.
    referenced = (
        list(_command_mentions(text))
        if level == TextLevel.L3_PROSE
        else []
    )
    if referenced:
        for command, sub in referenced:
            if command not in surface:
                findings.append(
                    _finding(
                        "TE3.CommandTruth",
                        rel,
                        f"phantom command 'isai {command}' is not declared by the CLI",
                        level=level,
                    )
                )
                continue
            known = surface.get(command) or set()
            if sub and known and sub not in known and not sub.startswith("-"):
                findings.append(
                    _finding(
                        "TE3.CommandTruth",
                        rel,
                        f"phantom subcommand 'isai {command} {sub}' "
                        f"(declared: {sorted(known)})",
                        level=level,
                    )
                )

    # -- TE6.ChronicleRegister: no hedging in normative carriers --------------------
    # The roster itself, its tests and the audit baseline legitimately *contain* the markers; a
    # scanner that flags its own dictionary would be useless, so declaration surfaces are exempt.
    if (is_machine_text or level == TextLevel.L3_PROSE) and not _declares_hedge_roster(rel, text):
        lowered = text.lower()
        for hedge in HEDGE_MARKERS:
            if re.search(rf"(?<!\w){re.escape(hedge)}(?!\w)", lowered):
                findings.append(
                    _finding(
                        "TE6.ChronicleRegister",
                        rel,
                        f"hedge '{hedge}' dilutes a normative statement; state the fact or drop it",
                        level=level,
                    )
                )
    return findings


def _check_prose_lexicon(
    rel: str,
    location: str,
    text: str,
    vocabulary: set[str],
    findings: list[TextFinding],
) -> None:
    """
    `TE2.DLT-BPE` over human-language prose: every CamelComposite must resolve to something.

    Inline code spans are removed first. A name in backticks is *mentioned*, not *used* — the
    Markdown contract the whole repository already relies on, and the same one `TE3` honours when
    it strips code spans before reading a command. Without this, a document could not discuss a
    phantom name at all, which would make the very defect report that motivates the check
    unwritable.
    """
    prose = _INLINE_CODE_RE.sub(" ", text)
    for token in sorted(set(structured_tokens(prose))):
        if not _is_camel_composite(token) or _binds(token, vocabulary):
            continue
        findings.append(
            _finding(
                "TE2.DLT-BPE",
                location,
                f"phantom CamelComposite '{token}' binds to no live symbol, command, file, "
                f"domain acronym or fundamental term",
                level=TextLevel.L1_CANON,
            )
        )


def _check_l1_canon(
    rel: str, text: str, repo_root: Path, vocabulary: set[str]
) -> list[TextFinding]:
    """`TE1.CarrierPurity` + `TE2`/`TE4`/`TE5` over the declarative string carriers of one module."""
    findings: list[TextFinding] = []
    surface = cli_surface(repo_root)
    if rel not in TEXT_BEARING_CARRIERS:
        return findings
    py_path = repo_root / rel
    for lineno, value in canon_strings(py_path):
        if len(value) < 40:
            continue
        human_language = bool(re.search(r"[\u0400-\u04FF]", value))
        if human_language and not is_balanced_fragment(value):
            findings.append(
                _finding(
                    "TE4.FrameLaw",
                    f"{rel}:{lineno}",
                    "unbalanced bracket/quote family in a normative carrier string",
                    level=TextLevel.L1_CANON,
                )
            )
        if "\n" not in value and len(value) > 400 and _clauses(value) > 6:
            findings.append(
                _finding(
                    "TE1.CarrierPurity",
                    f"{rel}:{lineno}",
                    f"narrative run of {_clauses(value)} clauses inside a machine carrier "
                    f"({len(value)} chars); section it or move it to L3 prose",
                    level=TextLevel.L1_CANON,
                )
            )
        if value.strip().startswith(("TE3.CommandTruth:", "TE7.VerifyCompile:")):
            # The command-truth duty itself names its own example; it is a rule, not a call.
            continue
        if not _is_rule_carrier(value):
            continue
        if not human_language:
            # The formal DSL body is the *definition site* of the vocabulary: `GateA`, `ByteRollback`
            # and `CamelComposite` are introduced by the rule that names them. Demanding that the
            # fundamental bind to code would invert the design — the constitution defines the code.
            # Its guard is the glyph-soup check above, not symbol binding.
            continue
        # -- TE2.DLT-BPE: a CamelComposite in human-language prose must bind ----------------
        # Prose is where an invented neologism actually hurts: a reader (or a tokenizer) meets a
        # name that resolves to nothing — no symbol, no command, no file, no acronym, no DSL term.
        _check_prose_lexicon(rel, f"{rel}:{lineno}", value, vocabulary, findings)
        if "GENESIS" in value or value.strip().startswith(("# ISyncAI", "[USER-IDENTITY")):
            # The IL-0 genome is byte-frozen (`L0`): its salience order is itself constitutional and
            # may never be re-ranked by a text rule, so the reader does not judge it.
            continue
        head = value.strip()[:24].upper()
        for prefix, _role in _SALIENCE_PREFIXES:
            if head.startswith(prefix.upper()):
                break
        else:
            findings.append(
                _finding(
                    "TE5.SalienceOrder",
                    f"{rel}:{lineno}",
                    "normative rule carries no salience prefix (FATAL/RUN/TE<n>.) and no execution "
                    "arrow, so a reader cannot rank its role",
                    level=TextLevel.L1_CANON,
                    severity="WARNING",
                )
            )
    return findings


#: Projections that are the byte-exact render of a live object, mapped to their source of truth.
_PROJECTION_SOURCES: dict[str, str] = {
    "FUNDAMENTAL.md": "isai://root#NeuroVascularFundamental",
    "VISION.md": "isai://root#MasterVector",
}


def _check_l2_transcript(rel: str, text: str, repo_root: Path) -> list[TextFinding]:
    """
    `TE1.CarrierPurity`: a synchronised transcript must be the projection of its source of truth.

    Two flavours exist, and both are read *offline* by re-rendering the source they claim to
    transcribe: an object projection (`FUNDAMENTAL.md`, `VISION.md`) whose whole body is rendered,
    and a passport block inside a node `README.md` whose SYNC section is spliced into authored prose.
    """
    from isai.engine import _upsert_sync_section  # local import: engine imports this module

    findings: list[TextFinding] = []
    name = Path(rel).name

    if name in _PROJECTION_SOURCES:
        from isai.graph_index import load_repo_master_vector, load_repo_nvf

        try:
            if name == "FUNDAMENTAL.md":
                projected = load_repo_nvf(repo_root).render_markdown()
            else:
                projected = load_repo_master_vector(repo_root).render_markdown()
        except Exception as exc:  # pragma: no cover - a broken source is reported by audit
            findings.append(
                _finding(
                    "TE1.CarrierPurity",
                    rel,
                    f"projection source unreachable: {exc}",
                    level=TextLevel.L2_TRANSCRIPT,
                )
            )
            return findings
        if projected != text:
            findings.append(
                _finding(
                    "TE1.CarrierPurity",
                    rel,
                    f"{rel} is not the byte-exact projection of {_PROJECTION_SOURCES[name]} "
                    f"(hand-edited transcript); run `isai sync`",
                    level=TextLevel.L2_TRANSCRIPT,
                )
            )
        return findings

    directory = (repo_root / rel).parent
    node_py = directory / ".isai" / "node.py"
    if not node_py.is_file():
        findings.append(
            _finding(
                "TE1.CarrierPurity",
                rel,
                "a synchronised passport exists without a node manifest that could project it",
                level=TextLevel.L2_TRANSCRIPT,
            )
        )
        return findings
    try:
        from isai.engine import load_node_from_dir

        node = load_node_from_dir(repo_root, directory)
        projected = _upsert_sync_section(text, node.render_sync_block(), node.render_sync_block())
    except Exception as exc:  # pragma: no cover - the audit reports loader errors itself
        findings.append(
            _finding(
                "TE1.CarrierPurity",
                rel,
                f"passport projection is not reproducible: {exc}",
                level=TextLevel.L2_TRANSCRIPT,
            )
        )
        return findings
    if projected != text:
        findings.append(
            _finding(
                "TE1.CarrierPurity",
                rel,
                "README.md is not the byte-exact projection of its .isai/node.py manifest "
                "(hand-edited transcript); run `isai sync`",
                level=TextLevel.L2_TRANSCRIPT,
            )
        )
    return findings


def _check_l4_record(rel: str, text: str, repo_root: Path) -> list[TextFinding]:
    """`TE6.ChronicleRegister`: every event must carry typed, hedge-free, parseable evidence."""
    findings: list[TextFinding] = []
    if not rel.endswith(".jsonl"):
        return findings
    for index, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as exc:
            findings.append(
                _finding("TE6.ChronicleRegister", f"{rel}:{index}", f"unparseable record: {exc}",
                         level=TextLevel.L4_RECORD)
            )
            continue
        summary = payload.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            # Machine ledgers (`.isai/vector_ledger.jsonl`) record their narrative in `kind` +
            # `operator_note` instead of a `summary`; both registers are accepted, absence is not.
            ledger_narrative = payload.get("kind") or payload.get("operator_note")
            if ledger_narrative:
                continue
            findings.append(
                _finding("TE6.ChronicleRegister", f"{rel}:{index}", "event carries no summary",
                         level=TextLevel.L4_RECORD)
            )
            continue
        lowered = summary.lower()
        for hedge in HEDGE_MARKERS:
            if re.search(rf"(?<!\w){re.escape(hedge)}(?!\w)", lowered):
                findings.append(
                    _finding(
                        "TE6.ChronicleRegister",
                        f"{rel}:{index}",
                        f"event summary hedges with '{hedge}'",
                        level=TextLevel.L4_RECORD,
                    )
                )
    return findings


def _check_l3_prose(rel: str, text: str, vocabulary: set[str]) -> list[TextFinding]:
    """
    Authored prose: `TE2.DLT-BPE` lexical binding + `TE4.FrameLaw` framing.

    Prose is precisely where a phantom name does the most damage: code that names a symbol it
    never defines fails at import, while a paragraph that names a component nobody implemented
    reads as fact. The lexicon check is therefore enforced here, not only in the DSL bodies.
    """
    findings: list[TextFinding] = []
    _check_prose_lexicon(rel, rel, text, vocabulary, findings)
    if len(text) > 1200 and not re.search(r"^#{1,6}\s", text, flags=re.MULTILINE):
        findings.append(
            _finding(
                "TE4.FrameLaw",
                rel,
                f"{len(text)}-char prose with no section headings: the mid-window rules "
                f"lose salience",
                level=TextLevel.L3_PROSE,
                severity="WARNING",
            )
        )
    if text.count("```") % 2 != 0:
        findings.append(
            _finding("TE4.FrameLaw", rel, "unbalanced code fence", level=TextLevel.L3_PROSE)
        )
    return findings


def validate_text(repo_root: Path, *, strict_domain_lexicon: bool = False) -> TextReport:
    """
    Read every system text offline and emit the deterministic `TE0..TE7` verdict (`TE7`).

    The reader is *pure*: it never mutates the repository, never shells out and never depends on a
    language model, so it can be replayed in the Pure-LLM fallback and in Crash Recovery alike.
    `strict_domain_lexicon` upgrades the closed-acronym rule from "must bind" to "must be a member
    of the closed set" for machine carriers, which is the form Gate V enforces on `.isai` text.
    """
    root = repo_root.resolve()
    vocabulary = build_bound_vocabulary(root) | fundamental_definitions(root)
    surface = cli_surface(root)
    findings: list[TextFinding] = []
    levels_seen: set[str] = set()
    files_checked = 0
    text_bytes = 0

    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in TEXT_FILE_SUFFIXES:
            continue
        rel_path = path.relative_to(root)
        if DEFAULT_BOUNDARY_IGNORE.is_ignored(rel_path):
            continue
        rel = rel_path.as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:  # pragma: no cover
            continue
        files_checked += 1
        text_bytes += len(text.encode("utf-8"))
        level = classify_text(rel_path, text)
        levels_seen.add(level.value)

        findings.extend(
            _check_text_sample(rel, level, text, vocabulary=vocabulary, surface=surface)
        )
        if level == TextLevel.L1_CANON:
            findings.extend(_check_l1_canon(rel, text, root, vocabulary))
        elif level == TextLevel.L2_TRANSCRIPT:
            findings.extend(_check_l2_transcript(rel, text, root))
        elif level == TextLevel.L4_RECORD:
            findings.extend(_check_l4_record(rel, text, root))
        elif level == TextLevel.L3_PROSE:
            findings.extend(_check_l3_prose(rel, text, vocabulary))
        if strict_domain_lexicon and level in (TextLevel.L1_CANON, TextLevel.L3_PROSE):
            for token in set(structured_tokens(text)):
                if token.isupper() and len(token) >= 2 and token not in DOMAIN_ACRONYM_SET:
                    if not _binds(token, vocabulary):
                        findings.append(
                            _finding(
                                "TE2.DLT-BPE",
                                rel,
                                f"acronym '{token}' is outside the closed domain acronym set",
                                level=level,
                            )
                        )

    ordered = tuple(
        sorted(findings, key=lambda f: (f.check, f.location, f.message))
    )
    payload = json.dumps(
        [f.model_dump(mode="json") for f in ordered], ensure_ascii=False, sort_keys=True
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    critical = [f for f in ordered if f.severity == "CRITICAL"]
    return TextReport(
        status="TEXT_VALID" if not critical else "TEXT_DEVIATION_DETECTED",
        findings=ordered,
        levels_seen=tuple(sorted(levels_seen)),
        files_checked=files_checked,
        text_bytes=text_bytes,
        evidence_digest=digest,
    )


# ---------------------------------------------------------------------------
# TE5: salience instrumentation for the RSoC packet
# ---------------------------------------------------------------------------


def section_role(text: str) -> str:
    """Declare the role of one rule-shaped string: `DECIDE`, `EXECUTE` or `EXPLAIN` (`TE5`)."""
    head = text.strip()[:24].upper()
    for prefix, role in _SALIENCE_PREFIXES:
        if head.startswith(prefix.upper()):
            return role
    if "=>" in text or re.match(r"^(?:RUN|STOP)\b", text.strip()):
        return "EXECUTE"
    if ":" in text and "=" in text:
        return "DECIDE"
    return "EXPLAIN"


def salience_profile(lines: Iterable[str]) -> dict[str, int]:
    """Count the role mix of a normative block; a `DECIDE`-free block cannot gate anything."""
    profile = {role: 0 for role in SECTION_ROLES}
    for line in lines:
        profile[section_role(line)] += 1
    return profile


def text_engineering_packet() -> dict[str, Any]:
    """
    The compact RSoC slice of the fundamental: level law, duties and the recency guard.

    It is delivered at *both* attention peaks — the primacy head (so the level law is never
    re-derived) and the terminal guard (so the last token before generation is the verification
    duty, not an aspiration).
    """
    return {
        "circuit": "[TEXT-ENGINEERING]",
        "level_law": [
            {"level": level.value, "precedence": index + 1}
            for index, level in enumerate(LEVEL_PRECEDENCE)
        ],
        "carrier_levels": [level.value for level in CARRIER_LEVELS],
        "duties": ["TE0", "TE1", "TE2", "TE3", "TE4", "TE5", "TE6", "TE7"],
        "verify": "isai text check",
        "status_token": "текст системных папок и файлов нативен",
        "recency_guard": [
            "TE1: never hand-edit an L2 transcript; project it (`isai sync`).",
            "TE3: never name a command the CLI does not declare.",
            "TE7: `isai text check` before every PR; deviation => neutralize and re-run.",
        ],
    }


__all__ = [
    "DOMAIN_ACRONYM_SET",
    "EVENT_SUMMARY_FIELDS",
    "HEDGE_MARKERS",
    "L0_GENOME_BYTE_LENGTH",
    "LEVEL_PRECEDENCE",
    "SECTION_ROLES",
    "TEXT_FILE_SUFFIXES",
    "TextFinding",
    "TextLevel",
    "TextReport",
    "build_bound_vocabulary",
    "canon_strings",
    "classify_text",
    "cli_surface",
    "is_balanced_fragment",
    "level_inventory",
    "salience_profile",
    "section_role",
    "structured_tokens",
    "text_engineering_packet",
    "validate_text",
]
