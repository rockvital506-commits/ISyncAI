"""Three-Tier Hypergraph Cross-Tests for ISAI v0.2.0:
- Tier 1: Bidirectional Contract Compatibility (BDCT), Structural Schema Digests, Ring Visibility & AST Purity.
- Tier 2: Transactional LinkMutator Lifecycle, Symbol Refactoring, Dry-Run & Atomic Batch Rollback.
- Tier 3: Generative Stateful Property-Based Fuzzing (Hypothesis RuleBasedStateMachine).
"""

from __future__ import annotations

import hashlib
import shutil
import tempfile
from pathlib import Path

import pytest
from hypothesis import settings, strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule
from pydantic import BaseModel, ConfigDict

from isai.__main__ import main as isai_cli_main
from isai.atomic_io import TEMP_ARTIFACT_PREFIX, atomic_transaction_batch
from isai.constitution import DEFAULT_BOUNDARY_IGNORE, GENESIS_CONSTITUTION, IntegrityLevel
from isai.contracts import (
    EdgeKind,
    EdgeLinkSpec,
    IOPortSpec,
    ISAINodeSpec,
    PortWiringSpec,
    RSoCDeliveryPolicy,
    SymbolBindingKind,
    SymbolBindingSpec,
    SymbolVisibility,
    VisibilityScope,
    compute_type_structural_digest,
)
from isai.engine import audit_repository, load_module_attr, sync_repository
from isai.graph_index import build_hypergraph_index
from isai.link_mutator import LinkMutationError, LinkMutator, render_node_module
from isai.protocol import PhaseNodeSpec

REPO_ROOT = Path(__file__).resolve().parent.parent


def _clone_repo(dest_parent: Path) -> Path:
    dest = dest_parent / "repo"

    def _ignore(src: str, names: list[str]) -> set[str]:
        src_path = Path(src)
        return {
            name
            for name in names
            if DEFAULT_BOUNDARY_IGNORE.is_ignored((src_path / name).relative_to(REPO_ROOT))
        }

    shutil.copytree(REPO_ROOT, dest, ignore=_ignore)
    return dest


def _snapshot_tree_hashes(root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if DEFAULT_BOUNDARY_IGNORE.is_ignored(rel) or p.is_dir():
            continue
        hashes[rel.as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return hashes


# ---------------------------------------------------------------------------
# TIER 1: Bidirectional Contract Testing, Visibility Rings & AST Purity
# ---------------------------------------------------------------------------


@pytest.mark.isai_scope("isai://root#HypergraphIndex", "isai://tests#HypergraphCrossTestSuite")
def test_eavt_and_vaet_index_symmetry_and_can_mutate_preflight() -> None:
    """Every forward EAVT edge must appear identically in VAET, and can_mutate must identify blockers and scoped tests."""
    idx = build_hypergraph_index(REPO_ROOT)
    assert not idx.ast_violations
    assert len(idx.edges) >= 30

    eavt_count = sum(len(v) for v in idx.forward_edges.values())
    assert eavt_count == len(idx.edges)
    for edge in idx.edges:
        assert edge in idx.inbound_to(edge.target_ref)
        assert edge in idx.inbound_to(edge.target_node_id)

    report = idx.can_mutate("isai://tasks", operation="decommission")
    assert report.safe_without_cascade is False
    assert "isai://knowledge" in report.transitive_dependents
    assert "isai://tests" in report.transitive_dependents
    assert any("PORT_WIRING" in s for s in report.external_inbound_sources)
    assert any("DOMAIN_MODEL_REF" in s for s in report.external_inbound_sources)

    selected = idx.select_affected_tests(("isai://root#LinkInjector",))["selected_tests"]
    assert any("test_hypergraph_cross_links.py" in t for t in selected)


@pytest.mark.isai_scope("isai://root", "isai://tasks", "isai://tests")
def test_port_wiring_type_compatibility_and_structural_schema_digest(tmp_path: Path) -> None:
    """Verify BDCT port subtype compatibility (producer <= consumer), broken schema detection, and structural Pydantic digests."""
    # 1. Structural digest changes when a Pydantic field's type or requiredness changes
    class _SchemaV1(BaseModel):
        model_config = ConfigDict(frozen=True)
        count: int

    class _SchemaV2(BaseModel):
        model_config = ConfigDict(frozen=True)
        count: str

    assert compute_type_structural_digest(_SchemaV1) != compute_type_structural_digest(_SchemaV2)

    # 2. Subtype widening (builtins:str -> TaskManifest | str) is valid, while incompatible wiring fails
    sandbox = _clone_repo(tmp_path)
    tests_node_path = sandbox / "tests" / ".isai" / "node.py"
    _, tests_spec = build_hypergraph_index(sandbox).nodes["isai://tests"]

    # Incompatible wiring: wire live_state_snapshot (expects SystemStateSnapshot) to rsoc_packet (produces builtins:dict)
    bad_spec = tests_spec.model_copy(
        update={
            "port_wirings": (
                PortWiringSpec(
                    consumer_input_port="live_state_snapshot",
                    producer_ref="isai://root#RSoCCompiler",
                    producer_output_port="rsoc_packet",
                ),
            )
        }
    )
    tests_node_path.write_text(render_node_module(bad_spec), encoding="utf-8")
    sync_repository(sandbox)

    rep = audit_repository(sandbox, require_clean_snapshot=False)
    assert rep.valid is False
    codes = {i.code for i in rep.issues}
    assert "INCOMPATIBLE_PORT_WIRING" in codes

    # Broken schema_refs import path -> BROKEN_PORT_SCHEMA
    broken_port_spec = tests_spec.model_copy(
        update={
            "outputs": (
                IOPortSpec(
                    name="pytest_gate_verdict",
                    contract_type="MissingModel",
                    schema_refs=("isai.protocol:NonExistentModelXYZ",),
                    description="Broken schema target",
                ),
            )
        }
    )
    tests_node_path.write_text(render_node_module(broken_port_spec), encoding="utf-8")
    sync_repository(sandbox)
    rep2 = audit_repository(sandbox, require_clean_snapshot=False)
    assert any(i.code == "BROKEN_PORT_SCHEMA" for i in rep2.issues)


@pytest.mark.isai_scope("isai://root#GenesisKernel", "isai://tasks#WatchdogService")
def test_ring_visibility_and_il0_immutability_gates(tmp_path: Path) -> None:
    """Canonical IL-1/IL-2 nodes must never depend on EPHEMERAL_STAGING, NODE_PRIVATE symbols, or mutate IL-0."""
    sandbox = _clone_repo(tmp_path)

    # Create an ephemeral staging node in tasks/TASK-TEMP
    ephemeral_dir = sandbox / "tasks" / "TASK-TEMP"
    (ephemeral_dir / ".isai").mkdir(parents=True)
    (ephemeral_dir / "README.md").write_text("# Temp\n", encoding="utf-8")
    ephemeral_spec = ISAINodeSpec(
        node_id="isai://tasks/TASK-TEMP",
        title="Temp staging",
        integrity_level=IntegrityLevel.IL_3_STAGING,
        visibility=VisibilityScope.EPHEMERAL_STAGING,
        parent_ref="isai://tasks",
        goal="Ephemeral work",
        success_criteria=("Isolated",),
        capabilities=("Staging",),
        owned_files=("README.md",),
        system_files=("node.py",),
    )
    (ephemeral_dir / ".isai" / "node.py").write_text(
        render_node_module(ephemeral_spec), encoding="utf-8"
    )

    # Also mark OperatorProfile as INTERNAL and have canonical 'knowledge' link to TASK-TEMP, INTERNAL, and MUTATES_TARGET on IL-0
    idx = build_hypergraph_index(sandbox)
    _, user_spec = idx.nodes["isai://user"]
    private_user_spec = user_spec.model_copy(
        update={
            "symbol_bindings": (
                SymbolBindingSpec(
                    symbol="OperatorProfile",
                    kind=SymbolBindingKind.PYTHON_ATTR,
                    target="profile.py:USER_PROFILE",
                    visibility=SymbolVisibility.INTERNAL,
                ),
            )
        }
    )
    (sandbox / "user" / ".isai" / "node.py").write_text(
        render_node_module(private_user_spec), encoding="utf-8"
    )

    _, know_spec = idx.nodes["isai://knowledge"]
    violating_know = know_spec.model_copy(
        update={
            "links": know_spec.links
            + (
                EdgeLinkSpec(
                    target_ref="isai://tasks/TASK-TEMP",
                    kind=EdgeKind.CONSUMES_CONTRACT,
                ),
                EdgeLinkSpec(
                    target_ref="isai://user#OperatorProfile",
                    kind=EdgeKind.CONSUMES_CONTRACT,
                ),
                EdgeLinkSpec(
                    target_ref="isai://root#GenesisKernel",
                    kind=EdgeKind.MUTATES_TARGET,
                ),
            )
        }
    )
    (sandbox / "knowledge" / ".isai" / "node.py").write_text(
        render_node_module(violating_know), encoding="utf-8"
    )
    sync_repository(sandbox)

    rep = audit_repository(sandbox, require_clean_snapshot=False)
    assert rep.valid is False
    vis_msgs = [i.message for i in rep.issues if i.code == "VISIBILITY_VIOLATION"]
    imm_msgs = [i.message for i in rep.issues if i.code == "IMMUTABLE_TARGET_VIOLATION"]
    assert any("ephemeral staging" in m.lower() for m in vis_msgs)
    assert any("INTERNAL" in m for m in vis_msgs)
    assert any("GenesisKernel" in m for m in imm_msgs)

    # Watchdog must also refuse WRITE_LEASE on IL-0 GenesisKernel
    wd_cls = load_module_attr(sandbox / "tasks" / ".isai" / "watchdog.py", "_wd_il0", "TaskWatchdog")
    wd = wd_cls(sandbox)
    with pytest.raises(ValueError, match="IL-0 Constitutional violation"):
        wd.register_phase_handles(
            wd.load_snapshot(),
            "isai://tasks#BadTask",
            PhaseNodeSpec(
                phase_id="P-BAD",
                title="Illegal Genesis write",
                target_node_ref="isai://root",
                write_set=("isai://root#GenesisKernel",),
            ),
        )


@pytest.mark.isai_scope("isai://root#HypergraphIndex")
def test_ast_purity_gate_rejects_impure_node_py_before_import(tmp_path: Path) -> None:
    """AST purity gate must block unauthorized imports, function defs, and side-effect calls without executing them."""
    sandbox = _clone_repo(tmp_path)
    marker_file = tmp_path / "should_never_exist.txt"
    impure_code = (
        "import os\n"
        f"os. pathlib = open({str(marker_file)!r}, 'w')\n"
        "def forbidden_helper():\n"
        "    return 1\n"
    )
    user_node = sandbox / "user" / ".isai" / "node.py"
    user_node.write_text(
        impure_code + "\n" + user_node.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    rep = audit_repository(sandbox, require_clean_snapshot=False)
    assert rep.valid is False
    assert any(i.code == "IMPURE_NODE_AST" for i in rep.issues)
    assert not marker_file.exists(), "Impure node.py must NEVER be executed before AST gate!"


# ---------------------------------------------------------------------------
# TIER 2: Transactional LinkMutator Lifecycle, Refactoring & Atomic Rollback
# ---------------------------------------------------------------------------


@pytest.mark.isai_scope("isai://root#LinkInjector")
def test_link_mutator_full_lifecycle_cli_and_dry_run_isolation(tmp_path: Path) -> None:
    """LinkMutator must support dry-run preview, scaffold, add_link, wire_port, VAET-guarded decommission, and CLI."""
    sandbox = _clone_repo(tmp_path)
    mut = LinkMutator(sandbox)

    before_hashes = _snapshot_tree_hashes(sandbox)
    dry_plan = mut.scaffold_node(
        "knowledge/sub_patterns",
        title="Подкаталог верифицированных графовых схем",
        goal="Тестирование транзакционного создания дочернего узла.",
        dry_run=True,
    )
    assert dry_plan.dry_run is True
    assert _snapshot_tree_hashes(sandbox) == before_hashes

    # Execute real scaffold + add input port on new node + wire_port from isai://knowledge
    mut.scaffold_node(
        "knowledge/sub_patterns",
        title="Подкаталог верифицированных графовых схем",
        goal="Тестирование транзакционного создания дочернего узла.",
    )
    assert audit_repository(sandbox, require_clean_snapshot=False).valid is True

    # Add an input port to knowledge/sub_patterns so we can test wire_port & unwire_port
    idx = build_hypergraph_index(sandbox)
    sub_dir, sub_spec = idx.nodes["isai://knowledge/sub_patterns"]
    sub_with_port = sub_spec.model_copy(
        update={
            "inputs": (
                IOPortSpec(
                    name="upstream_slice",
                    contract_type="dict[str, Any]",
                    schema_refs=("builtins:dict",),
                    description="Срез знаний родительского улья.",
                    required=False,
                ),
            )
        }
    )
    (sub_dir / ".isai" / "node.py").write_text(
        render_node_module(sub_with_port), encoding="utf-8"
    )
    sync_repository(sandbox)

    mut.wire_port(
        "isai://knowledge/sub_patterns",
        "upstream_slice",
        "isai://knowledge",
        "filtered_knowledge_slice",
        rationale="Тестовая коммутация совместимого порта.",
    )
    # Add external inbound link from tests -> knowledge/sub_patterns
    mut.add_link(
        "isai://tests",
        "isai://knowledge/sub_patterns#SubPatternsDoc",
        kind=EdgeKind.VERIFIES,
        rsoc_delivery=RSoCDeliveryPolicy.INTERFACE_STUB,
    )
    assert audit_repository(sandbox, require_clean_snapshot=False).valid is True

    # Decommissioning while 'isai://tests' still links to it MUST be rejected (both API and CLI)
    with pytest.raises(LinkMutationError, match="inbound external references"):
        mut.decommission_node("isai://knowledge/sub_patterns")
    assert (
        isai_cli_main(
            ["--root", str(sandbox), "link", "decommission-node", "isai://knowledge/sub_patterns"]
        )
        == 1
    )

    # Remove inbound link from tests, unwire port, then decommission cleanly!
    mut.remove_link(
        "isai://tests",
        "isai://knowledge/sub_patterns#SubPatternsDoc",
        kind=EdgeKind.VERIFIES,
    )
    mut.unwire_port("isai://knowledge/sub_patterns", "upstream_slice")
    mut.decommission_node("isai://knowledge/sub_patterns")

    assert not (sandbox / "knowledge" / "sub_patterns").exists()
    final_rep = audit_repository(sandbox, require_clean_snapshot=False)
    assert final_rep.valid is True, f"Issues after decommission: {final_rep.issues}"


@pytest.mark.isai_scope("isai://root#LinkInjector", "isai://user#OperatorProfile")
def test_transactional_refactor_renames_symbol_across_code_prose_and_preserves_genesis(
    tmp_path: Path,
) -> None:
    """refactor_entity_ref must update Python ASTs and Markdown prose atomically without touching Genesis bytes 0..586."""
    sandbox = _clone_repo(tmp_path)
    # Add a custom prose mention outside SYNC markers plus a fenced code block that must NOT be altered
    user_readme = sandbox / "user" / "README.md"
    original_md = user_readme.read_text(encoding="utf-8")
    marker = "<!-- ISAI:SYNC:BEGIN -->"
    injected = (
        "\nАктивный контракт профиля: `isai://user#OperatorProfile`.\n"
        "```python\n"
        "# Исторический пример в code-блоке не трогаем: isai://user#OperatorProfile\n"
        "```\n\n"
    )
    user_readme.write_text(original_md.replace(marker, injected + marker, 1), encoding="utf-8")

    mut = LinkMutator(sandbox)
    plan = mut.refactor_entity_ref(
        "isai://user#OperatorProfile",
        "isai://user#CognitiveTwin",
    )
    assert plan.applied is True
    assert GENESIS_CONSTITUTION.verify_genesis_header(sandbox / "README.md").valid is True

    updated_md = user_readme.read_text(encoding="utf-8")
    assert "Активный контракт профиля: `isai://user#CognitiveTwin`." in updated_md
    assert "# Исторический пример в code-блоке не трогаем: isai://user#OperatorProfile" in updated_md

    rep = audit_repository(sandbox, require_clean_snapshot=False)
    assert rep.valid is True, f"Post-refactor audit issues: {rep.issues}"


@pytest.mark.isai_scope("isai://root#AtomicPersistence", "isai://root#LinkInjector")
def test_atomic_transaction_batch_rolls_back_all_files_on_post_commit_failure(
    tmp_path: Path,
) -> None:
    """Any failure in post_commit_hook or Gate A admission must restore every touched/deleted file byte-for-byte."""
    sandbox = _clone_repo(tmp_path)
    before = _snapshot_tree_hashes(sandbox)

    # 1. Direct atomic_transaction_batch multi-file write + delete with forced post_commit_hook error
    new_file = sandbox / "user" / "transient.md"
    with pytest.raises(RuntimeError, match="Simulated Gate A failure"):
        atomic_transaction_batch(
            writes={
                sandbox / "AGENTS.md": b"# Corrupted temporary content\n",
                new_file: b"# Should be deleted on rollback\n",
            },
            deletes=(sandbox / "VISION.md",),
            post_commit_hook=lambda: (_ for _ in ()).throw(
                RuntimeError("Simulated Gate A failure")
            ),
        )

    assert not new_file.exists()
    assert _snapshot_tree_hashes(sandbox) == before
    assert list(sandbox.rglob(f"{TEMP_ARTIFACT_PREFIX}*")) == []

    # 2. LinkMutator invalid port wiring rolls back cleanly with zero residue
    mut = LinkMutator(sandbox)
    with pytest.raises(LinkMutationError):
        mut.wire_port(
            "isai://tests",
            "live_state_snapshot",
            "isai://root#RSoCCompiler",
            "rsoc_packet",
        )
    assert _snapshot_tree_hashes(sandbox) == before


# ---------------------------------------------------------------------------
# TIER 3: Generative Stateful Property-Based Fuzzing (Hypothesis)
# ---------------------------------------------------------------------------


@settings(
    max_examples=12,
    stateful_step_count=8,
    database=None,
    derandomize=True,
    deadline=None,
)
class HypergraphLifecycleMachine(RuleBasedStateMachine):
    """
    Stateful property-based fuzzer exercising arbitrary sequences of:
      scaffold_node -> add_link -> remove_link -> refactor_entity_ref -> decommission_node
    and asserting 100% Genesis + 360° Gate A invariants after EVERY step.
    """

    def __init__(self) -> None:
        super().__init__()
        self._tmpdir = tempfile.TemporaryDirectory(prefix="isai_hyp_")
        self.sandbox = _clone_repo(Path(self._tmpdir.name))
        self.mutator = LinkMutator(self.sandbox)
        self.subnodes: list[str] = []
        self.subnode_doc_symbol: dict[str, str] = {}
        self.external_links: set[tuple[str, str, EdgeKind]] = set()
        self._counter = 0

    def teardown(self) -> None:
        self._tmpdir.cleanup()

    @rule()
    def scaffold_subnode(self) -> None:
        if len(self.subnodes) >= 3:
            return
        self._counter += 1
        slug = f"mod_{self._counter}"
        uri = f"isai://knowledge/{slug}"
        self.mutator.scaffold_node(
            f"knowledge/{slug}",
            title=f"Генеративный подузел {slug}",
            goal="Проверка инвариантов графа на случайных траекториях.",
        )
        # Compute initial doc symbol generated by scaffold_node
        doc_sym = "".join(p.capitalize() for p in slug.split("_")) + "Doc"
        self.subnodes.append(uri)
        self.subnode_doc_symbol[uri] = doc_sym

    @rule(idx=st.integers(min_value=0, max_value=10))
    def add_verified_link_from_tests(self, idx: int) -> None:
        if not self.subnodes:
            return
        target_node = self.subnodes[idx % len(self.subnodes)]
        sym = self.subnode_doc_symbol[target_node]
        target_uri = f"{target_node}#{sym}"
        key = ("isai://tests", target_uri, EdgeKind.VERIFIES)
        if key in self.external_links:
            with pytest.raises(Exception):
                self.mutator.add_link(
                    "isai://tests",
                    target_uri,
                    kind=EdgeKind.VERIFIES,
                    rsoc_delivery=RSoCDeliveryPolicy.INTERFACE_STUB,
                )
            return
        self.mutator.add_link(
            "isai://tests",
            target_uri,
            kind=EdgeKind.VERIFIES,
            rsoc_delivery=RSoCDeliveryPolicy.INTERFACE_STUB,
        )
        self.external_links.add(key)

    @rule()
    def attempt_illegal_mutation_rejected(self) -> None:
        before = _snapshot_tree_hashes(self.sandbox)
        with pytest.raises(LinkMutationError):
            self.mutator.add_link(
                "isai://user",
                "isai://root#GenesisKernel",
                kind=EdgeKind.MUTATES_TARGET,
            )
        assert _snapshot_tree_hashes(self.sandbox) == before

    @rule(idx=st.integers(min_value=0, max_value=10))
    def rename_subnode_symbol(self, idx: int) -> None:
        if not self.subnodes:
            return
        target_node = self.subnodes[idx % len(self.subnodes)]
        old_sym = self.subnode_doc_symbol[target_node]
        self._counter += 1
        new_sym = f"DocSymV{self._counter}"
        old_uri = f"{target_node}#{old_sym}"
        new_uri = f"{target_node}#{new_sym}"
        self.mutator.refactor_entity_ref(old_uri, new_uri)
        self.subnode_doc_symbol[target_node] = new_sym
        updated_links: set[tuple[str, str, EdgeKind]] = set()
        for src, tgt, kind in self.external_links:
            updated_links.add((src, new_uri if tgt == old_uri else tgt, kind))
        self.external_links = updated_links

    @rule(idx=st.integers(min_value=0, max_value=10))
    def remove_link_or_decommission(self, idx: int) -> None:
        if not self.subnodes:
            return
        target_node = self.subnodes[idx % len(self.subnodes)]
        sym = self.subnode_doc_symbol[target_node]
        target_uri = f"{target_node}#{sym}"
        inbound_matching = [
            (src, tgt, kind)
            for (src, tgt, kind) in self.external_links
            if tgt == target_uri or tgt == target_node
        ]
        if inbound_matching:
            # First verify VAET finalizer blocks premature deletion!
            with pytest.raises(LinkMutationError):
                self.mutator.decommission_node(target_node)
            # Now remove one inbound link cleanly
            src, tgt, kind = sorted(inbound_matching)[0]
            self.mutator.remove_link(src, tgt, kind=kind)
            self.external_links.remove((src, tgt, kind))
        else:
            self.mutator.decommission_node(target_node)
            self.subnodes.remove(target_node)
            self.subnode_doc_symbol.pop(target_node, None)

    @invariant()
    def repo_satisfies_all_genesis_and_360_hypergraph_invariants(self) -> None:
        assert GENESIS_CONSTITUTION.verify_genesis_header(self.sandbox / "README.md").valid is True
        rep = audit_repository(self.sandbox, require_clean_snapshot=False)
        assert rep.valid is True, f"Stateful fuzzing invariant broken: {rep.issues}"
        idx = build_hypergraph_index(self.sandbox)
        for uri in self.subnodes:
            assert uri in idx.nodes
            expected_sym = self.subnode_doc_symbol[uri]
            assert any(b.symbol == expected_sym for b in idx.nodes[uri][1].symbol_bindings)


TestHypergraphStatefulLifecycle = pytest.mark.isai_scope(
    "isai://root#LinkInjector",
    "isai://root#HypergraphIndex",
    "isai://tests#HypergraphCrossTestSuite",
)(HypergraphLifecycleMachine.TestCase)
