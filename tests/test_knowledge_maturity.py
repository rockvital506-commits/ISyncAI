"""
`IMPLEMENTED` must be a claim about code, not about wording.

The catalog carried `PAT_DUAL_ZONE_..._DEMATERIALIZATION_BARRIER` at `IMPLEMENTED` while the
repository contained no `materialize`/`dematerialize` symbol at all — only prose about them. That
is the failure mode these tests exist to prevent: a maturity label that cannot fail is decoration.

Three ways a claim could cheat, each pinned below:

1. declare `IMPLEMENTED` with no `primary_symbol` at all;
2. name a symbol that does not exist (`QuantumLinkDaemon`);
3. name a *file* that resembles the symbol (`link_mutator` for `LinkMutator`).

Case (3) is the subtle one and it caught a real defect: the first version of this check reused
`build_bound_vocabulary`, which admits file stems and folds case for pronounceability. The phantom
`QuantumLinkDaemon` passed because `link_mutator` is a file stem. That is why H-KNOW-08 rebuilds a
strict, case-sensitive surface from AST declarations instead.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from isai.graph_index import build_hypergraph_index
from isai.health_checks import _declared_symbol_surface, check_knowledge_domain

REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOG_REL = Path("knowledge") / ".isai" / "catalog.py"


def _h08(root: Path):
    index = build_hypergraph_index(root)
    for result in check_knowledge_domain(root, index.nodes):
        if result.check_id == "H-KNOW-08":
            return result
    raise AssertionError("H-KNOW-08 is not wired into the knowledge domain")


def _repo_copy(tmp_path: Path) -> Path:
    """A writable copy of just what the check reads: the catalog and the `.isai` packages."""
    root = tmp_path / "repo"
    (root / "knowledge" / ".isai").mkdir(parents=True)
    shutil.copy2(REPO_ROOT / CATALOG_REL, root / CATALOG_REL)
    for pkg in REPO_ROOT.rglob(".isai"):
        if not pkg.is_dir():
            continue
        rel = pkg.relative_to(REPO_ROOT)
        target = root / rel
        target.mkdir(parents=True, exist_ok=True)
        for py in pkg.glob("*.py"):
            shutil.copy2(py, target / py.name)
    return root


def _rewrite(root: Path, old: str, new: str) -> None:
    path = root / CATALOG_REL
    text = path.read_text(encoding="utf-8")
    assert old in text, f"fixture drifted: {old!r} not in catalog"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


@pytest.mark.isai_scope("isai://knowledge#EmpiricalCatalog", "isai://tests#KnowledgeMaturitySuite")
def test_live_catalog_passes_every_maturity_check() -> None:
    index = build_hypergraph_index(REPO_ROOT)
    results = {r.check_id: r for r in check_knowledge_domain(REPO_ROOT, index.nodes)}
    for check_id in ("H-KNOW-06", "H-KNOW-07", "H-KNOW-08"):
        assert check_id in results, f"{check_id} is not wired into the audit"
        assert results[check_id].passed, (check_id, results[check_id].evidence)


@pytest.mark.isai_scope("isai://knowledge#EmpiricalCatalog", "isai://tests#KnowledgeMaturitySuite")
def test_implemented_without_a_symbol_fails(tmp_path: Path) -> None:
    root = _repo_copy(tmp_path)
    _rewrite(root, 'primary_symbol="LinkMutator",', 'primary_symbol="",')
    result = _h08(root)
    assert result.passed is False
    assert "no symbol" in (result.evidence or "")


@pytest.mark.isai_scope("isai://knowledge#EmpiricalCatalog", "isai://tests#KnowledgeMaturitySuite")
def test_phantom_symbol_fails(tmp_path: Path) -> None:
    """The exact cheat the first implementation of this check let through."""
    root = _repo_copy(tmp_path)
    _rewrite(root, 'primary_symbol="LinkMutator",', 'primary_symbol="QuantumLinkDaemon",')
    result = _h08(root)
    assert result.passed is False
    assert "unbound" in (result.evidence or "")


@pytest.mark.isai_scope("isai://knowledge#EmpiricalCatalog", "isai://tests#KnowledgeMaturitySuite")
def test_filename_is_not_a_symbol(tmp_path: Path) -> None:
    """`link_mutator` names a file; `LinkMutator` names the mechanism. Only one is code."""
    root = _repo_copy(tmp_path)
    _rewrite(root, 'primary_symbol="LinkMutator",', 'primary_symbol="link_mutator",')
    result = _h08(root)
    assert result.passed is False


@pytest.mark.isai_scope("isai://knowledge#EmpiricalCatalog", "isai://tests#KnowledgeMaturitySuite")
def test_symbol_surface_is_case_sensitive_and_stem_free() -> None:
    surface = _declared_symbol_surface(REPO_ROOT)
    assert "LinkMutator" in surface
    # A file stem must never satisfy a symbol claim.
    assert "link_mutator" not in surface
    # Case folding must never satisfy it either.
    assert "linkmutator" not in surface


@pytest.mark.isai_scope("isai://knowledge#EmpiricalCatalog", "isai://tests#KnowledgeMaturitySuite")
def test_prose_entries_carry_no_symbol() -> None:
    """A PROSE entry claiming a symbol would be a maturity claim by the back door."""
    from isai.graph_index import load_module_attr_isolated

    catalog = load_module_attr_isolated(REPO_ROOT / CATALOG_REL, "kc_test", "KNOWLEDGE_CATALOG")
    for entry in catalog.entries:
        if entry.maturity == "PROSE":
            assert entry.primary_symbol == "", entry.entry_id
