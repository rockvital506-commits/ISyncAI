"""
`isai bio validate` must be a barrier, not a report.

`BIO-LEXICON.md` listed which bio terms were real, and nothing checked it. A document cannot fail,
so it could not stop a term from entering prose before the symbol existed — which is how
`барьер дематериализации` and `материализация плазмиды` became writeable.

These tests pin the three ways the gate must be able to fail:

1. a term whose symbol was renamed away (BIO-02);
2. a bench symbol promoted to kernel maturity (BIO-03) — the one that keeps "proved in the lab"
   from being read as "the system does it";
3. a term marked FORBIDDEN that quietly names a symbol (rejected by the spec itself).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
LEXICON_DIR = REPO_ROOT / "research" / ".isai"
if str(LEXICON_DIR) not in sys.path:
    sys.path.insert(0, str(LEXICON_DIR))

from bio_lexicon import (  # noqa: E402
    BIO_LEXICON,
    BioLexiconSpec,
    LexiconEntry,
    _resolve_symbol,
    render_lexicon_markdown,
    validate_lexicon,
)


@pytest.mark.isai_scope("isai://research#BioLexicon", "isai://tests#BioLexiconGateSuite")
def test_live_lexicon_is_valid() -> None:
    findings = validate_lexicon(REPO_ROOT, BIO_LEXICON)
    failures = [f for f in findings if not f.passed]
    assert not failures, [(f.check, f.term, f.message) for f in failures]


@pytest.mark.isai_scope("isai://research#BioLexicon", "isai://tests#BioLexiconGateSuite")
def test_renamed_symbol_fails_bio02() -> None:
    entry = LexiconEntry(
        term="Ген",
        english="Gene",
        symbol="GeneThatWasRenamed",
        symbol_file="research/lab/e6_mini.py",
        maturity="MEASURED",
        rationale="fixture",
    )
    findings = validate_lexicon(REPO_ROOT, BioLexiconSpec(entries=(entry,)))
    bio02 = [f for f in findings if f.check == "BIO-02"]
    assert bio02 and not bio02[0].passed
    assert "not declared" in bio02[0].message


@pytest.mark.isai_scope("isai://research#BioLexicon", "isai://tests#BioLexiconGateSuite")
def test_bench_symbol_cannot_claim_kernel_maturity() -> None:
    """The defect this gate exists for: a lab mechanism presented as a system mechanism."""
    entry = LexiconEntry(
        term="Ген",
        english="Gene",
        symbol="Gene",
        symbol_file="research/lab/e6_mini.py",
        maturity="IMPLEMENTED",
        rationale="fixture pretending the bench is the kernel",
    )
    findings = validate_lexicon(REPO_ROOT, BioLexiconSpec(entries=(entry,)))
    bio03 = [f for f in findings if f.check == "BIO-03"]
    assert bio03 and not bio03[0].passed
    assert "outside the kernel" in bio03[0].message


@pytest.mark.isai_scope("isai://research#BioLexicon", "isai://tests#BioLexiconGateSuite")
def test_kernel_symbol_may_claim_implemented() -> None:
    """The gate must not be a blanket ban — a real kernel symbol has to be able to pass."""
    entry = LexiconEntry(
        term="Гиперграф",
        english="HypergraphIndex",
        symbol="HypergraphIndex",
        symbol_file=".isai/graph_index.py",
        maturity="IMPLEMENTED",
        rationale="fixture over a genuine kernel symbol",
    )
    findings = validate_lexicon(REPO_ROOT, BioLexiconSpec(entries=(entry,)))
    assert all(f.passed for f in findings), [(f.check, f.message) for f in findings]


@pytest.mark.isai_scope("isai://research#BioLexicon", "isai://tests#BioLexiconGateSuite")
def test_forbidden_entry_cannot_name_a_symbol() -> None:
    """`FORBIDDEN` means no symbol; naming one would make the state self-contradictory."""
    with pytest.raises(ValueError):
        LexiconEntry(
            term="Хромосома",
            english="Chromosome",
            symbol="Chromosome",
            symbol_file="research/lab/e7_plasmid.py",
            maturity="FORBIDDEN",
            rationale="contradiction",
        )


@pytest.mark.isai_scope("isai://research#BioLexicon", "isai://tests#BioLexiconGateSuite")
def test_symbol_resolution_is_exact_and_case_sensitive() -> None:
    """`link_mutator` is a file; `LinkMutator` is the mechanism."""
    ok, _ = _resolve_symbol(REPO_ROOT, ".isai/link_mutator.py", "LinkMutator")
    assert ok
    ok, reason = _resolve_symbol(REPO_ROOT, ".isai/link_mutator.py", "linkmutator")
    assert not ok and "not declared" in reason


@pytest.mark.isai_scope("isai://research#BioLexicon", "isai://tests#BioLexiconGateSuite")
def test_markdown_projection_covers_every_entry() -> None:
    """The document is a projection: a term missing from it is a term nobody can read about."""
    rendered = render_lexicon_markdown(BIO_LEXICON)
    for entry in BIO_LEXICON.entries:
        assert entry.term in rendered
