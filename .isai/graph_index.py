"""Bidirectional Hypergraph Index (Datomic EAVT + VAET), AST Purity Gate & Affected Test Selector."""

from __future__ import annotations

import ast
import re
import sys
import types
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from isai.atomic_io import TEMP_ARTIFACT_PREFIX
from isai.constitution import BoundaryIgnoreSpec, DEFAULT_BOUNDARY_IGNORE, IntegrityLevel
from isai.contracts import ISAINodeSpec, parse_entity_ref, validate_entity_ref
from isai.domain_models import KnowledgeCatalogSpec, MasterVectorSpec, UserProfileSpec
from isai.neuro_vascular import NEURO_VASCULAR_FUNDAMENTAL, NeuroVascularFundamentalSpec
from isai.protocol import CanMutateReport, SystemStateSnapshot
from isai.vector import MASTER_VECTOR

_FENCED_CODE_RE = re.compile(r"```[\s\S]*?```")
_HTML_COMMENT_RE = re.compile(r"<!--[\s\S]*?-->")
_PROSE_ISAI_URI_RE = re.compile(r"isai://([A-Za-z0-9_./#<>\[\]-]+)")

_ALLOWED_NODE_IMPORTS = {"__future__", "isai.constitution", "isai.contracts"}
_ALLOWED_EXPR_NODES = (
    ast.Call,
    ast.Name,
    ast.Load,
    ast.Attribute,
    ast.Constant,
    ast.Tuple,
    ast.keyword,
)


class HypergraphEdgeKind(StrEnum):
    """Physical carrier category of an indexed directed edge in the repository hypergraph."""

    PARENT_TOPOLOGY = "PARENT_TOPOLOGY"
    TYPED_LINK = "TYPED_LINK"
    PORT_WIRING = "PORT_WIRING"
    ROUTER_TRANSITION = "ROUTER_TRANSITION"
    DOMAIN_MODEL_REF = "DOMAIN_MODEL_REF"
    STATE_SNAPSHOT_REF = "STATE_SNAPSHOT_REF"
    PROSE_ENTITY_REF = "PROSE_ENTITY_REF"


class IndexedEdge(BaseModel):
    """Immutable indexed hypergraph datom supporting both forward (EAVT) and reverse (VAET) queries."""

    model_config = ConfigDict(frozen=True)

    source_id: str
    target_ref: str
    target_node_id: str
    edge_category: HypergraphEdgeKind
    semantic_detail: str
    source_location: str


def verify_node_py_ast_purity(py_path: Path) -> list[str]:
    """
    Verify before exec_module that a .isai/node.py file is a pure declarative manifest:
      - Optional module docstring
      - Imports restricted to __future__, isai.constitution, isai.contracts
      - Exactly one assignment `NODE = ISAINodeSpec(...)` built from pure literal/constructor AST nodes
    """
    try:
        source = py_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(py_path))
    except SyntaxError as exc:
        return [f"SyntaxError in '{py_path}': {exc}"]

    violations: list[str] = []
    node_assigned = False

    for idx, stmt in enumerate(tree.body):
        if (
            idx == 0
            and isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Constant)
            and isinstance(stmt.value.value, str)
        ):
            continue
        if isinstance(stmt, ast.ImportFrom):
            if stmt.module not in _ALLOWED_NODE_IMPORTS:
                violations.append(
                    f"Disallowed import from '{stmt.module}' in declarative node manifest."
                )
            continue
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
            if stmt.targets[0].id != "NODE":
                violations.append(
                    f"Only 'NODE' assignment is permitted in node.py, got '{stmt.targets[0].id}'."
                )
                continue
            if node_assigned:
                violations.append("Duplicate 'NODE' assignment in node.py (Redundancy=FATAL).")
                continue
            node_assigned = True
            for sub in ast.walk(stmt.value):
                if not isinstance(sub, _ALLOWED_EXPR_NODES):
                    violations.append(
                        f"Impure AST expression '{type(sub).__name__}' inside NODE specification."
                    )
                    break
            continue

        violations.append(f"Disallowed top-level statement '{type(stmt).__name__}' in node.py.")

    if not node_assigned:
        violations.append("Missing required 'NODE = ISAINodeSpec(...)' assignment in node.py.")
    return violations


def load_module_attr_isolated(py_path: Path, module_namespace: str, attr_name: str) -> Any:
    """
    Dynamically load an attribute from py_path directly from live UTF-8 source.
    Bypasses SourceFileLoader .pyc (int(mtime), size) cache collisions when sub-second
    transactional AST mutations preserve identical file byte length.
    """
    source = py_path.read_text(encoding="utf-8")
    code = compile(source, str(py_path), "exec")
    module = types.ModuleType(module_namespace)
    module.__file__ = str(py_path)
    module.__package__ = ""
    prev = sys.modules.get(module_namespace)
    sys.modules[module_namespace] = module
    try:
        exec(code, module.__dict__)
    finally:
        if prev is None:
            sys.modules.pop(module_namespace, None)
        else:
            sys.modules[module_namespace] = prev
    if not hasattr(module, attr_name):
        raise AttributeError(f"File '{py_path}' does not export required symbol '{attr_name}'.")
    return getattr(module, attr_name)


def load_repo_master_vector(repo_root: Path) -> MasterVectorSpec:
    """Load MASTER_VECTOR directly from `<repo_root>/.isai/vector.py` (sandbox-isolated)."""
    vec_py = repo_root.resolve() / ".isai" / "vector.py"
    if vec_py.is_file():
        obj = load_module_attr_isolated(vec_py, "_isai_repo_vector", "MASTER_VECTOR")
        if not isinstance(obj, MasterVectorSpec):
            raise TypeError("MASTER_VECTOR must be an instance of MasterVectorSpec.")
        return obj
    return MASTER_VECTOR


def load_repo_nvf(repo_root: Path) -> NeuroVascularFundamentalSpec:
    """Load NEURO_VASCULAR_FUNDAMENTAL directly from `<repo_root>/.isai/neuro_vascular.py` (sandbox-isolated)."""
    nvf_py = repo_root.resolve() / ".isai" / "neuro_vascular.py"
    if nvf_py.is_file():
        obj = load_module_attr_isolated(
            nvf_py, "_isai_repo_nvf", "NEURO_VASCULAR_FUNDAMENTAL"
        )
        if isinstance(obj, NeuroVascularFundamentalSpec):
            return obj
        if type(obj).__name__ == "NeuroVascularFundamentalSpec" and hasattr(obj, "model_dump"):
            return NeuroVascularFundamentalSpec.model_validate(obj.model_dump())
        raise TypeError(
            "NEURO_VASCULAR_FUNDAMENTAL must be an instance of NeuroVascularFundamentalSpec."
        )
    return NEURO_VASCULAR_FUNDAMENTAL


def iter_functional_dirs(
    repo_root: Path,
    boundary: BoundaryIgnoreSpec = DEFAULT_BOUNDARY_IGNORE,
) -> list[Path]:
    """Return sorted list of all non-ignored functional directories (excluding .isai and temp dirs)."""
    result: list[Path] = [repo_root]

    def _walk(current: Path) -> None:
        for entry in sorted(current.iterdir(), key=lambda p: p.name):
            if not entry.is_dir():
                continue
            rel = entry.relative_to(repo_root)
            if boundary.is_ignored(rel):
                continue
            if entry.name == ".isai" or entry.name.startswith(TEMP_ARTIFACT_PREFIX):
                continue
            result.append(entry)
            _walk(entry)

    _walk(repo_root)
    return result


class HypergraphIndex:
    """
    Single-pass bidirectional repository hypergraph index (Datomic EAVT + VAET).
    Provides O(1) outbound and inbound edge queries across nodes, symbols, ports,
    domain catalogs, Watchdog snapshots, and Markdown prose.
    """

    def __init__(
        self,
        repo_root: Path,
        nodes: dict[str, tuple[Path, ISAINodeSpec]],
        edges: list[IndexedEdge],
        ast_violations: dict[str, list[str]] | None = None,
        load_errors: dict[str, str] | None = None,
    ) -> None:
        self.repo_root = repo_root
        self.nodes = nodes
        self.edges = tuple(edges)
        self.ast_violations = ast_violations or {}
        self.load_errors = load_errors or {}

        self.valid_targets: set[str] = set()
        for nid, (_, nspec) in nodes.items():
            self.valid_targets.add(nid)
            for sym in nspec.defined_symbols:
                self.valid_targets.add(f"{nid}#{sym}")

        fwd: dict[str, list[IndexedEdge]] = {}
        rev: dict[str, list[IndexedEdge]] = {}
        for edge in self.edges:
            fwd.setdefault(edge.source_id, []).append(edge)
            rev.setdefault(edge.target_ref, []).append(edge)
            if edge.target_node_id != edge.target_ref:
                rev.setdefault(edge.target_node_id, []).append(edge)

        self.forward_edges: dict[str, tuple[IndexedEdge, ...]] = {
            k: tuple(v) for k, v in fwd.items()
        }
        self.reverse_edges: dict[str, tuple[IndexedEdge, ...]] = {
            k: tuple(dict.fromkeys(v)) for k, v in rev.items()
        }

    def outbound_of(self, source_id: str) -> tuple[IndexedEdge, ...]:
        """O(1) EAVT query: return all edges originating from source_id."""
        return self.forward_edges.get(source_id, ())

    def inbound_to(self, target_uri: str) -> tuple[IndexedEdge, ...]:
        """O(1) VAET query: return all edges pointing to target_uri (node or #Symbol)."""
        return self.reverse_edges.get(target_uri, ())

    def reverse_node_closure(self, start_uri: str) -> tuple[tuple[str, ...], int]:
        """
        Cycle-safe N-hop BFS over reverse structural node edges (VAET).
        Returns (topologically_ordered_dependent_node_ids, max_hop_depth).
        """
        scope, _ = parse_entity_ref(start_uri)
        root_nid = f"isai://{scope}"
        structural_kinds = {
            HypergraphEdgeKind.PARENT_TOPOLOGY,
            HypergraphEdgeKind.TYPED_LINK,
            HypergraphEdgeKind.PORT_WIRING,
            HypergraphEdgeKind.ROUTER_TRANSITION,
        }

        visited: set[str] = {root_nid}
        frontier: list[str] = [root_nid]
        ordered: list[str] = []
        max_depth = 0
        depth = 0

        while frontier:
            next_level: set[str] = set()
            for cur in frontier:
                for edge in self.inbound_to(cur):
                    if (
                        edge.edge_category in structural_kinds
                        and edge.source_id in self.nodes
                        and edge.source_id not in visited
                    ):
                        next_level.add(edge.source_id)
            if not next_level:
                break
            depth += 1
            max_depth = depth
            sorted_next = sorted(next_level)
            visited.update(sorted_next)
            ordered.extend(sorted_next)
            frontier = sorted_next

        return tuple(ordered), max_depth

    def select_affected_tests(self, mutated_uris: tuple[str, ...]) -> dict[str, Any]:
        """
        Compute affected pytest cross-tests for a set of mutated EntityRefs using VAET closure
        and @pytest.mark.isai_scope(...) AST inspection, failing closed to full suite on IL-1 edits.
        """
        impacted_scopes: set[str] = set()
        fail_closed_full = False

        for uri in mutated_uris:
            scope, _ = parse_entity_ref(uri)
            nid = f"isai://{scope}"
            impacted_scopes.add(nid)
            impacted_scopes.add(uri)
            if uri == "isai://root#NeuroVascularFundamental":
                fail_closed_full = True
            if nid in self.nodes and self.nodes[nid][1].integrity_level in (
                IntegrityLevel.IL_0_GENESIS,
                IntegrityLevel.IL_1C_FUNDAMENTAL,
                IntegrityLevel.IL_1_KERNEL,
            ):
                fail_closed_full = True
            deps, _ = self.reverse_node_closure(nid)
            for d in deps:
                impacted_scopes.add(d)
                if d in self.nodes and self.nodes[d][1].integrity_level in (
                    IntegrityLevel.IL_1C_FUNDAMENTAL,
                    IntegrityLevel.IL_1_KERNEL,
                ):
                    fail_closed_full = True

        tests_dir = self.repo_root / "tests"
        all_tests: list[str] = []
        matched_tests: list[str] = []

        if tests_dir.is_dir():
            for py_file in sorted(tests_dir.glob("test_*.py")):
                rel_py = py_file.relative_to(self.repo_root).as_posix()
                try:
                    tree = ast.parse(py_file.read_text(encoding="utf-8"))
                except SyntaxError:
                    continue
                for item in tree.body:
                    if isinstance(item, (ast.FunctionDef, ast.ClassDef)) and item.name.startswith(
                        ("test_", "Test")
                    ):
                        nodeid = f"{rel_py}::{item.name}"
                        all_tests.append(nodeid)
                        scopes_in_mark = _extract_isai_scope_marks(item)
                        if not scopes_in_mark or bool(impacted_scopes.intersection(scopes_in_mark)):
                            matched_tests.append(nodeid)

        selected = all_tests if fail_closed_full else matched_tests
        return {
            "mode": "FULL_SUITE_FAIL_CLOSED" if fail_closed_full else "SELECTIVE_VAET",
            "impacted_scopes": sorted(impacted_scopes),
            "selected_tests": selected,
        }

    def can_mutate(
        self,
        target_uri: str,
        operation: Literal["decommission", "remove_symbol", "mutate_interface"] = "decommission",
    ) -> CanMutateReport:
        """
        Preflight reverse-reference safety check (Pact 'can-i-deploy' + K8s Finalizer equivalent).
        Blocks decommissioning or symbol removal while external VAET consumers still point to target_uri.
        """
        validate_entity_ref(target_uri)
        scope, sym = parse_entity_ref(target_uri)
        owner_nid = f"isai://{scope}"
        reasons: list[str] = []

        if target_uri == "isai://root" or target_uri == "isai://root#GenesisKernel":
            reasons.append(f"Target '{target_uri}' is protected by constitutional ring IL-0/IL-1.")
        if target_uri == "isai://root#NeuroVascularFundamental":
            reasons.append(
                f"Target '{target_uri}' is protected by conditionally-locked ring IL-1C "
                "(amendable only via 6-Step Algedonic Protocol + Operator confirmation)."
            )

        inbound = self.inbound_to(target_uri)
        # Exclude self-owned README sync references of the node being decommissioned
        self_readme = "README.md" if scope == "root" else f"{scope}/README.md"
        external_sources: list[str] = []
        for edge in inbound:
            if edge.source_id == owner_nid and sym is None:
                continue
            if edge.source_location == self_readme and sym is None:
                continue
            external_sources.append(f"{edge.source_id} ({edge.edge_category.value} @ {edge.source_location})")

        external_unique = tuple(dict.fromkeys(external_sources))
        if operation in ("decommission", "remove_symbol") and external_unique:
            reasons.append(
                f"Target '{target_uri}' has {len(external_unique)} active external inbound reference(s)."
            )

        trans_deps, _ = self.reverse_node_closure(owner_nid)
        affected_info = self.select_affected_tests((target_uri,))

        return CanMutateReport(
            target_uri=target_uri,
            operation=operation,
            safe_without_cascade=(len(reasons) == 0),
            blocking_reasons=tuple(reasons),
            external_inbound_sources=external_unique,
            transitive_dependents=trans_deps,
            affected_tests=tuple(affected_info["selected_tests"]),
        )


def _extract_isai_scope_marks(defn: ast.FunctionDef | ast.ClassDef) -> set[str]:
    """Extract string arguments from @pytest.mark.isai_scope(...) decorators."""
    marks: set[str] = set()
    for dec in defn.decorator_list:
        if not isinstance(dec, ast.Call):
            continue
        func = dec.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "isai_scope"
            and isinstance(func.value, ast.Attribute)
            and func.value.attr == "mark"
        ):
            for arg in dec.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    marks.add(arg.value)
    return marks


def build_hypergraph_index(
    repo_root: Path,
    boundary: BoundaryIgnoreSpec = DEFAULT_BOUNDARY_IGNORE,
    override_nodes: dict[str, tuple[Path, ISAINodeSpec]] | None = None,
) -> HypergraphIndex:
    """
    Compile the complete forward (EAVT) and reverse (VAET) hypergraph index in a single pass.
    Supports `override_nodes` for in-memory shadow graph Admission validation prior to disk writes.
    """
    repo_root = repo_root.resolve()
    nodes: dict[str, tuple[Path, ISAINodeSpec]] = {}
    ast_violations: dict[str, list[str]] = {}
    load_errors: dict[str, str] = {}
    edges: list[IndexedEdge] = []

    if override_nodes is not None:
        nodes = dict(override_nodes)
    else:
        for d in iter_functional_dirs(repo_root, boundary):
            node_py = d / ".isai" / "node.py"
            if not node_py.is_file():
                continue
            rel_py = node_py.relative_to(repo_root).as_posix()
            purity_errs = verify_node_py_ast_purity(node_py)
            if purity_errs:
                ast_violations[rel_py] = purity_errs
                continue
            rel_dir = d.relative_to(repo_root)
            slug = re.sub(
                r"[^A-Za-z0-9_]",
                "_",
                "root" if rel_dir == Path(".") else "_".join(rel_dir.parts),
            )
            try:
                obj = load_module_attr_isolated(node_py, f"_isai_idx_{slug}", "NODE")
                if not isinstance(obj, ISAINodeSpec):
                    raise TypeError(f"Expected ISAINodeSpec, got {type(obj).__name__}")
                nodes[obj.node_id] = (d, obj)
            except Exception as exc:
                load_errors[rel_py] = str(exc)

    def _add_entity_edge(
        src_id: str,
        target_ref: str,
        cat: HypergraphEdgeKind,
        detail: str,
        loc: str,
    ) -> None:
        try:
            scope, _ = parse_entity_ref(target_ref)
            t_node = f"isai://{scope}"
        except Exception:
            t_node = target_ref
        edges.append(
            IndexedEdge(
                source_id=src_id,
                target_ref=target_ref,
                target_node_id=t_node,
                edge_category=cat,
                semantic_detail=detail,
                source_location=loc,
            )
        )

    md_files: list[Path] = []
    for nid, (d, node) in sorted(nodes.items()):
        loc = (d / ".isai" / "node.py").relative_to(repo_root).as_posix()
        if node.parent_ref is not None:
            _add_entity_edge(
                nid, node.parent_ref, HypergraphEdgeKind.PARENT_TOPOLOGY, "parent_ref", loc
            )
        for link in node.links:
            _add_entity_edge(
                nid,
                link.target_ref,
                HypergraphEdgeKind.TYPED_LINK,
                f"{link.kind.value}:rsoc={link.rsoc_delivery.value}",
                loc,
            )
        for pw in node.port_wirings:
            _add_entity_edge(
                nid,
                pw.producer_ref,
                HypergraphEdgeKind.PORT_WIRING,
                f"{pw.consumer_input_port}<-{pw.producer_output_port}",
                loc,
            )
        for tr in node.transitions:
            _add_entity_edge(
                nid,
                tr.target_ref,
                HypergraphEdgeKind.ROUTER_TRANSITION,
                f"{tr.trigger}[{tr.phase_mode.value}]",
                loc,
            )
        for owned in node.owned_files:
            if owned.endswith(".md"):
                md_files.append(d / owned)

    # Index domain models (MASTER_VECTOR, NEURO_VASCULAR_FUNDAMENTAL, USER_PROFILE, KNOWLEDGE_CATALOG)
    try:
        m_vec = load_repo_master_vector(repo_root)
        _add_entity_edge(
            "domain:MASTER_VECTOR",
            m_vec.vector_id,
            HypergraphEdgeKind.DOMAIN_MODEL_REF,
            "vector_id",
            ".isai/vector.py",
        )
    except Exception:
        pass

    nvf_py = repo_root / ".isai" / "neuro_vascular.py"
    if nvf_py.is_file():
        try:
            nvf_spec = load_repo_nvf(repo_root)
            _add_entity_edge(
                "isai://root#NeuroVascularFundamental",
                nvf_spec.governed_by,
                HypergraphEdgeKind.DOMAIN_MODEL_REF,
                "governed_by",
                ".isai/neuro_vascular.py",
            )
            for anc_ref in nvf_spec.anchored_entity_refs:
                _add_entity_edge(
                    "isai://root#NeuroVascularFundamental",
                    anc_ref,
                    HypergraphEdgeKind.DOMAIN_MODEL_REF,
                    "anchored_entity_ref",
                    ".isai/neuro_vascular.py",
                )
        except Exception:
            pass

    u_py = repo_root / "user" / ".isai" / "profile.py"
    if u_py.is_file():
        try:
            u_prof = load_module_attr_isolated(u_py, "_isai_idx_uprof", "USER_PROFILE")
            if isinstance(u_prof, UserProfileSpec):
                _add_entity_edge(
                    "isai://user#OperatorProfile",
                    u_prof.profile_ref,
                    HypergraphEdgeKind.DOMAIN_MODEL_REF,
                    "profile_ref",
                    "user/.isai/profile.py",
                )
        except Exception:
            pass

    k_py = repo_root / "knowledge" / ".isai" / "catalog.py"
    if k_py.is_file():
        try:
            k_cat = load_module_attr_isolated(k_py, "_isai_idx_kcat", "KNOWLEDGE_CATALOG")
            if isinstance(k_cat, KnowledgeCatalogSpec):
                _add_entity_edge(
                    "isai://knowledge#EmpiricalCatalog",
                    k_cat.catalog_ref,
                    HypergraphEdgeKind.DOMAIN_MODEL_REF,
                    "catalog_ref",
                    "knowledge/.isai/catalog.py",
                )
                for entry in k_cat.entries:
                    _add_entity_edge(
                        f"knowledge:{entry.entry_id}",
                        entry.related_node_ref,
                        HypergraphEdgeKind.DOMAIN_MODEL_REF,
                        f"KnowledgeEntry:{entry.entry_id}",
                        f"knowledge/.isai/catalog.py#{entry.entry_id}",
                    )
        except Exception:
            pass

    snap_path = repo_root / "tasks" / ".isai" / "state_snapshot.json"
    if snap_path.is_file():
        try:
            snap = SystemStateSnapshot.model_validate_json(
                snap_path.read_text(encoding="utf-8")
            )
            for t_ref in snap.active_tasks:
                _add_entity_edge(
                    "state_snapshot:active_tasks",
                    t_ref,
                    HypergraphEdgeKind.STATE_SNAPSHOT_REF,
                    "active_task",
                    "tasks/.isai/state_snapshot.json#active_tasks",
                )
            for h_rec in snap.open_handles:
                _add_entity_edge(
                    f"handle:{h_rec.handle_id}",
                    h_rec.target_ref,
                    HypergraphEdgeKind.STATE_SNAPSHOT_REF,
                    f"handle:{h_rec.access.value}",
                    f"tasks/.isai/state_snapshot.json#{h_rec.handle_id}",
                )
        except Exception:
            pass

    # Index concrete human-prose EntityRefs in Markdown files (excluding auto-projected SYNC blocks)
    sync_block_re = re.compile(r"<!--\s*ISAI:SYNC:BEGIN\s*-->[\s\S]*?<!--\s*ISAI:SYNC:END\s*-->")
    for md_path in sorted(set(md_files)):
        if not md_path.is_file():
            continue
        rel_md = md_path.relative_to(repo_root).as_posix()
        no_sync = sync_block_re.sub("", md_path.read_text(encoding="utf-8"))
        clean = _HTML_COMMENT_RE.sub("", _FENCED_CODE_RE.sub("", no_sync))
        for m_uri in _PROSE_ISAI_URI_RE.finditer(clean):
            raw_unstripped = m_uri.group(1)
            if "..." in raw_unstripped:
                continue
            raw_body = raw_unstripped.rstrip(".,;:")
            if not raw_body or any(ch in raw_body for ch in ("<", ">", "[", "]")):
                continue
            cand = f"isai://{raw_body}"
            _add_entity_edge(
                f"prose:{rel_md}",
                cand,
                HypergraphEdgeKind.PROSE_ENTITY_REF,
                "markdown_inline_ref",
                rel_md,
            )

    return HypergraphIndex(
        repo_root=repo_root,
        nodes=nodes,
        edges=edges,
        ast_violations=ast_violations,
        load_errors=load_errors,
    )
