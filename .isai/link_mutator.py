"""Transactional AST Link Injector & Hypergraph Refactoring Engine (Buildozer + Unison UCM Equivalent)."""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from isai.atomic_io import atomic_transaction_batch, atomic_write_text
from isai.constitution import GENESIS_BYTE_LENGTH, GENESIS_CONSTITUTION, IntegrityLevel
from isai.contracts import (
    EdgeKind,
    EdgeLinkSpec,
    IOPortSpec,
    ISAINodeSpec,
    PhaseMode,
    PortWiringSpec,
    RSoCDeliveryPolicy,
    SYNC_BEGIN_MARKER,
    SYNC_END_MARKER,
    SymbolBindingKind,
    SymbolBindingSpec,
    SymbolVisibility,
    TransitionRule,
    VisibilityScope,
    parse_entity_ref,
    rel_path_to_node_id,
    scope_to_rel_path,
    validate_entity_ref,
)
from isai.engine import audit_repository, build_clean_snapshot, sync_repository
from isai.graph_index import build_hypergraph_index, load_repo_nvf, verify_node_py_ast_purity
from isai.protocol import MutationPlan, SystemStateSnapshot, utc_now_iso


class LinkMutationError(ValueError):
    """Raised when an ISAI link, port, symbol, or node mutation violates a hypergraph invariant."""


def _extract_module_docstring(py_path: Path) -> str | None:
    if not py_path.is_file():
        return None
    try:
        tree = ast.parse(py_path.read_text(encoding="utf-8"))
        return ast.get_docstring(tree, clean=False)
    except SyntaxError:
        return None


def _fmt_str_tuple(items: tuple[str, ...], indent: int = 4) -> str:
    if not items:
        return "()"
    pad = " " * indent
    inner_pad = " " * (indent + 4)
    body = "\n".join(f"{inner_pad}{item!r}," for item in items)
    return f"(\n{body}\n{pad})"


def render_node_module(node: ISAINodeSpec, docstring: str | None = None) -> str:
    """
    Deterministically serialize an ISAINodeSpec into a pure, AST-verified Python manifest (.isai/node.py).
    Guarantees 100% round-trip semantic equivalence and passes verify_node_py_ast_purity.
    """
    doc = docstring or f"System Folder Object Manifest for `{node.node_id}`."
    imports: list[str] = ["ISAINodeSpec"]
    # `VisibilityScope` is always rendered: a node declares its own visibility explicitly, even
    # when that value is the PUBLIC default, so no reader has to infer it.
    imports.append("VisibilityScope")
    if node.inputs or node.outputs:
        imports.append("IOPortSpec")
    if node.port_wirings:
        imports.append("PortWiringSpec")
    if node.symbol_bindings:
        imports.extend(["SymbolBindingKind", "SymbolBindingSpec", "SymbolVisibility"])
    if node.links:
        imports.extend(["EdgeKind", "EdgeLinkSpec", "RSoCDeliveryPolicy"])
    if node.transitions:
        imports.extend(["PhaseMode", "TransitionRule"])

    sorted_imports = sorted(set(imports))
    imports_block = ",\n    ".join(sorted_imports)

    lines: list[str] = [
        f'"""{doc}"""',
        "",
        "from __future__ import annotations",
        "",
        "from isai.constitution import IntegrityLevel",
        f"from isai.contracts import (\n    {imports_block},\n)",
        "",
        "NODE = ISAINodeSpec(",
        f"    node_id={node.node_id!r},",
        f"    title={node.title!r},",
        f"    integrity_level=IntegrityLevel.{node.integrity_level.name},",
        f"    visibility=VisibilityScope.{node.visibility.name},",
        f"    parent_ref={node.parent_ref!r},",
        f"    goal={node.goal!r},",
        f"    success_criteria={_fmt_str_tuple(node.success_criteria, 4)},",
        f"    capabilities={_fmt_str_tuple(node.capabilities, 4)},",
    ]

    if node.invariants:
        lines.append(f"    invariants={_fmt_str_tuple(node.invariants, 4)},")

    if node.inputs:
        lines.append("    inputs=(")
        for p in node.inputs:
            lines.append("        IOPortSpec(")
            lines.append(f"            name={p.name!r},")
            lines.append(f"            contract_type={p.contract_type!r},")
            if p.schema_refs:
                lines.append(f"            schema_refs={_fmt_str_tuple(p.schema_refs, 12)},")
            lines.append(f"            description={p.description!r},")
            if not p.required:
                lines.append("            required=False,")
            lines.append("        ),")
        lines.append("    ),")

    if node.outputs:
        lines.append("    outputs=(")
        for p in node.outputs:
            lines.append("        IOPortSpec(")
            lines.append(f"            name={p.name!r},")
            lines.append(f"            contract_type={p.contract_type!r},")
            if p.schema_refs:
                lines.append(f"            schema_refs={_fmt_str_tuple(p.schema_refs, 12)},")
            lines.append(f"            description={p.description!r},")
            if not p.required:
                lines.append("            required=False,")
            lines.append("        ),")
        lines.append("    ),")

    if node.port_wirings:
        lines.append("    port_wirings=(")
        for pw in node.port_wirings:
            lines.append("        PortWiringSpec(")
            lines.append(f"            consumer_input_port={pw.consumer_input_port!r},")
            lines.append(f"            producer_ref={pw.producer_ref!r},")
            lines.append(f"            producer_output_port={pw.producer_output_port!r},")
            if pw.rationale is not None:
                lines.append(f"            rationale={pw.rationale!r},")
            lines.append("        ),")
        lines.append("    ),")

    lines.append(f"    owned_files={_fmt_str_tuple(node.owned_files, 4)},")
    lines.append(f"    system_files={_fmt_str_tuple(node.system_files, 4)},")

    if node.symbol_bindings:
        lines.append("    symbol_bindings=(")
        for b in node.symbol_bindings:
            lines.append("        SymbolBindingSpec(")
            lines.append(f"            symbol={b.symbol!r},")
            lines.append(f"            kind=SymbolBindingKind.{b.kind.name},")
            lines.append(f"            target={b.target!r},")
            if b.visibility != SymbolVisibility.PUBLIC:
                lines.append(f"            visibility=SymbolVisibility.{b.visibility.name},")
            lines.append("        ),")
        lines.append("    ),")

    if node.links:
        lines.append("    links=(")
        for l in node.links:
            lines.append("        EdgeLinkSpec(")
            lines.append(f"            target_ref={l.target_ref!r},")
            lines.append(f"            kind=EdgeKind.{l.kind.name},")
            lines.append(f"            rsoc_delivery=RSoCDeliveryPolicy.{l.rsoc_delivery.name},")
            if l.rationale is not None:
                lines.append(f"            rationale={l.rationale!r},")
            lines.append("        ),")
        lines.append("    ),")

    if node.transitions:
        lines.append("    transitions=(")
        for tr in node.transitions:
            lines.append("        TransitionRule(")
            lines.append(f"            trigger={tr.trigger!r},")
            lines.append(f"            target_ref={tr.target_ref!r},")
            lines.append(f"            phase_mode=PhaseMode.{tr.phase_mode.name},")
            lines.append(f"            description={tr.description!r},")
            lines.append("        ),")
        lines.append("    ),")

    lines.append(")")
    rendered = "\n".join(lines) + "\n"

    # Self-verify generated AST syntax
    ast.parse(rendered)
    return rendered


def _replace_python_string_constants(source: str, old_val: str, new_val: str) -> str:
    """
    AST-guided exact replacement of string literal constants equal to old_val in a Python file,
    preserving 100% of surrounding comments, whitespace, and non-matching strings.
    """
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)

    # Compute byte/char offsets per 1-based line
    line_starts: list[int] = [0]
    for ln in lines:
        line_starts.append(line_starts[-1] + len(ln))

    def _to_char_offset(lineno: int, col_offset: int) -> int:
        raw_line = lines[lineno - 1].encode("utf-8")
        char_col = len(raw_line[:col_offset].decode("utf-8"))
        return line_starts[lineno - 1] + char_col

    spans: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value == old_val
            and node.lineno is not None
            and node.end_lineno is not None
            and node.col_offset is not None
            and node.end_col_offset is not None
        ):
            start = _to_char_offset(node.lineno, node.col_offset)
            end = _to_char_offset(node.end_lineno, node.end_col_offset)
            spans.append((start, end))

    if not spans:
        return source

    out = source
    for start, end in sorted(spans, reverse=True):
        out = out[:start] + repr(new_val) + out[end:]
    ast.parse(out)
    return out


def _replace_markdown_prose_uri(
    md_text: str,
    old_uri: str,
    new_uri: str,
    *,
    is_root_readme: bool = False,
) -> str:
    """
    Replace concrete EntityRef occurrences in human prose outside fenced code blocks,
     outside ISAI sync blocks (which are regenerated by sync_repository), and strictly
    after byte 586 on root README.md.
    """
    if is_root_readme:
        raw = md_text.encode("utf-8")
        prefix = raw[:GENESIS_BYTE_LENGTH].decode("utf-8")
        body = raw[GENESIS_BYTE_LENGTH:].decode("utf-8")
    else:
        prefix = ""
        body = md_text

    # Preserve SYNC block untouched (sync_repository re-renders it deterministically)
    if SYNC_BEGIN_MARKER in body and SYNC_END_MARKER in body:
        s_idx = body.index(SYNC_BEGIN_MARKER)
        e_idx = body.index(SYNC_END_MARKER) + len(SYNC_END_MARKER)
        prose_before = body[:s_idx]
        sync_seg = body[s_idx:e_idx]
        prose_after = body[e_idx:]
    else:
        prose_before = body
        sync_seg = ""
        prose_after = ""

    pattern = re.compile(re.escape(old_uri) + r"(?![A-Za-z0-9_./#-])")

    def _rewrite_outside_fences(segment: str) -> str:
        parts = re.split(r"(```[\s\S]*?```)", segment)
        rewritten: list[str] = []
        for idx, part in enumerate(parts):
            if idx % 2 == 1:
                rewritten.append(part)
            else:
                rewritten.append(pattern.sub(new_uri, part))
        return "".join(rewritten)

    return prefix + _rewrite_outside_fences(prose_before) + sync_seg + _rewrite_outside_fences(prose_after)


class LinkMutator:
    """
    Transactional Hypergraph Link Injector & Refactoring Service (`isai://root#LinkInjector`).
    Implements Buildozer's emit-and-apply (`dry_run`), K8s Admission/Finalizer safety gates,
    and atomic multi-file rollback if post-mutation Gate A ('audit_repository') fails.
    """

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def _commit_and_verify(
        self,
        writes: dict[Path, bytes],
        deletes: tuple[Path, ...] = (),
        *,
        activate_staging_task: str | None = None,
        deactivate_staging_task: str | None = None,
    ) -> list[str]:
        """Atomically apply batch, sync README/VISION/FUNDAMENTAL, refresh snapshot, and enforce Gate A."""
        sync_touched: list[str] = []

        def _post_hook() -> None:
            sync_rep = sync_repository(self.repo_root)
            sync_touched.extend(sync_rep.updated_files)

            snap_path = self.repo_root / "tasks" / ".isai" / "state_snapshot.json"
            if snap_path.is_file():
                snap = SystemStateSnapshot.model_validate_json(
                    snap_path.read_text(encoding="utf-8")
                )
                if activate_staging_task is not None:
                    merged_tasks = tuple(dict.fromkeys([*snap.active_tasks, activate_staging_task]))
                    refreshed = build_clean_snapshot(
                        self.repo_root,
                        revision=snap.revision,
                        active_tasks=merged_tasks,
                        open_handles=snap.open_handles,
                        audit_status="STAGING",
                    )
                    atomic_write_text(snap_path, refreshed.model_dump_json(indent=2) + "\n")
                    sync_touched.append("tasks/.isai/state_snapshot.json")
                elif deactivate_staging_task is not None:
                    rem_tasks = tuple(t for t in snap.active_tasks if t != deactivate_staging_task)
                    rem_handles = tuple(
                        h for h in snap.open_handles if h.owner_task_ref != deactivate_staging_task
                    )
                    refreshed = build_clean_snapshot(
                        self.repo_root,
                        revision=snap.revision,
                        active_tasks=rem_tasks,
                        open_handles=rem_handles,
                        audit_status="STAGING" if rem_tasks else "VALID",
                    )
                    atomic_write_text(snap_path, refreshed.model_dump_json(indent=2) + "\n")
                    sync_touched.append("tasks/.isai/state_snapshot.json")
                elif snap.audit_status == "VALID" and not snap.active_tasks:
                    refreshed = build_clean_snapshot(
                        self.repo_root, revision=snap.revision, audit_status="VALID"
                    )
                    atomic_write_text(snap_path, refreshed.model_dump_json(indent=2) + "\n")

            audit_rep = audit_repository(self.repo_root)
            if not audit_rep.valid:
                summary = "; ".join(f"[{i.code} @ {i.location}] {i.message}" for i in audit_rep.issues)
                raise LinkMutationError(f"Admission Gate A rejected link mutation: {summary}")

            gen_check = GENESIS_CONSTITUTION.verify_genesis_header(self.repo_root / "README.md")
            if not gen_check.valid:
                raise RuntimeError(f"Fatal IL-0 guard triggered: {gen_check.detail}")

        extra_backups: list[Path] = [
            self.repo_root / "VISION.md",
            self.repo_root / "FUNDAMENTAL.md",
            self.repo_root / "tasks" / ".isai" / "state_snapshot.json",
        ]
        for md_cand in self.repo_root.rglob("README.md"):
            extra_backups.append(md_cand)

        atomic_transaction_batch(
            writes=writes,
            deletes=deletes,
            post_commit_hook=_post_hook,
            extra_backup_paths=tuple(extra_backups),
            lock_root=self.repo_root,
        )
        return sync_touched

    def _clone_node(self, node: ISAINodeSpec, **updates: Any) -> ISAINodeSpec:
        data = node.model_dump()
        data.update(updates)
        return ISAINodeSpec(**data)

    def add_link(
        self,
        source_uri: str,
        target_uri: str,
        kind: EdgeKind = EdgeKind.CONSUMES_CONTRACT,
        rsoc_delivery: RSoCDeliveryPolicy = RSoCDeliveryPolicy.INTERFACE_STUB,
        rationale: str | None = None,
        *,
        dry_run: bool = False,
    ) -> MutationPlan:
        """Inject a typed EdgeLinkSpec into source_uri after Admission verification."""
        validate_entity_ref(source_uri)
        validate_entity_ref(target_uri)
        index = build_hypergraph_index(self.repo_root)

        if source_uri not in index.nodes:
            raise KeyError(f"Source node '{source_uri}' does not exist.")
        if target_uri not in index.valid_targets:
            raise ValueError(f"Target '{target_uri}' does not resolve to any registered node or symbol.")

        dir_path, src_node = index.nodes[source_uri]
        new_edge = EdgeLinkSpec(
            target_ref=target_uri,
            kind=kind,
            rsoc_delivery=rsoc_delivery,
            rationale=rationale,
        )
        updated_node = self._clone_node(src_node, links=(*src_node.links, new_edge))

        node_py = dir_path / ".isai" / "node.py"
        rendered = render_node_module(updated_node, _extract_module_docstring(node_py))
        rel_py = node_py.relative_to(self.repo_root).as_posix()

        deps, _ = index.reverse_node_closure(source_uri)
        affected = index.select_affected_tests((source_uri, target_uri))["selected_tests"]

        if dry_run:
            return MutationPlan(
                operation="link:add",
                dry_run=True,
                applied=False,
                touched_files=(rel_py,),
                added_edges=(f"{source_uri} -[{kind.value}]-> {target_uri}",),
                impacted_dependents=deps,
                affected_tests=tuple(affected),
            )

        extra = self._commit_and_verify({node_py: rendered.encode("utf-8")})
        return MutationPlan(
            operation="link:add",
            dry_run=False,
            applied=True,
            touched_files=tuple(dict.fromkeys([rel_py, *extra])),
            added_edges=(f"{source_uri} -[{kind.value}]-> {target_uri}",),
            impacted_dependents=deps,
            affected_tests=tuple(affected),
        )

    def remove_link(
        self,
        source_uri: str,
        target_uri: str,
        kind: EdgeKind | None = None,
        *,
        dry_run: bool = False,
    ) -> MutationPlan:
        """Remove matching EdgeLinkSpec(s) from source_uri."""
        validate_entity_ref(source_uri)
        validate_entity_ref(target_uri)
        index = build_hypergraph_index(self.repo_root)
        if source_uri not in index.nodes:
            raise KeyError(f"Source node '{source_uri}' does not exist.")

        dir_path, src_node = index.nodes[source_uri]
        kept = tuple(
            l
            for l in src_node.links
            if not (l.target_ref == target_uri and (kind is None or l.kind == kind))
        )
        if len(kept) == len(src_node.links):
            raise ValueError(f"No matching link '{source_uri} -> {target_uri}' found to remove.")

        updated_node = self._clone_node(src_node, links=kept)
        node_py = dir_path / ".isai" / "node.py"
        rendered = render_node_module(updated_node, _extract_module_docstring(node_py))
        rel_py = node_py.relative_to(self.repo_root).as_posix()
        deps, _ = index.reverse_node_closure(source_uri)
        affected = index.select_affected_tests((source_uri, target_uri))["selected_tests"]

        if dry_run:
            return MutationPlan(
                operation="link:remove",
                dry_run=True,
                applied=False,
                touched_files=(rel_py,),
                removed_edges=(f"{source_uri} -> {target_uri}",),
                impacted_dependents=deps,
                affected_tests=tuple(affected),
            )

        extra = self._commit_and_verify({node_py: rendered.encode("utf-8")})
        return MutationPlan(
            operation="link:remove",
            dry_run=False,
            applied=True,
            touched_files=tuple(dict.fromkeys([rel_py, *extra])),
            removed_edges=(f"{source_uri} -> {target_uri}",),
            impacted_dependents=deps,
            affected_tests=tuple(affected),
        )

    def wire_port(
        self,
        consumer_uri: str,
        consumer_input_port: str,
        producer_uri: str,
        producer_output_port: str,
        rationale: str | None = None,
        *,
        dry_run: bool = False,
    ) -> MutationPlan:
        """Bind a consumer input port to a producer output port with schema compatibility enforcement."""
        validate_entity_ref(consumer_uri)
        validate_entity_ref(producer_uri)
        index = build_hypergraph_index(self.repo_root)
        if consumer_uri not in index.nodes:
            raise KeyError(f"Consumer node '{consumer_uri}' does not exist.")
        if producer_uri not in index.valid_targets:
            raise ValueError(f"Producer '{producer_uri}' does not resolve in hypergraph.")

        dir_path, c_node = index.nodes[consumer_uri]
        wiring = PortWiringSpec(
            consumer_input_port=consumer_input_port,
            producer_ref=producer_uri,
            producer_output_port=producer_output_port,
            rationale=rationale,
        )
        updated_node = self._clone_node(c_node, port_wirings=(*c_node.port_wirings, wiring))
        node_py = dir_path / ".isai" / "node.py"
        rendered = render_node_module(updated_node, _extract_module_docstring(node_py))
        rel_py = node_py.relative_to(self.repo_root).as_posix()
        edge_desc = f"{consumer_uri}:{consumer_input_port} <- {producer_uri}:{producer_output_port}"
        deps, _ = index.reverse_node_closure(consumer_uri)
        affected = index.select_affected_tests((consumer_uri, producer_uri))["selected_tests"]

        if dry_run:
            return MutationPlan(
                operation="link:wire-port",
                dry_run=True,
                applied=False,
                touched_files=(rel_py,),
                added_edges=(edge_desc,),
                impacted_dependents=deps,
                affected_tests=tuple(affected),
            )

        extra = self._commit_and_verify({node_py: rendered.encode("utf-8")})
        return MutationPlan(
            operation="link:wire-port",
            dry_run=False,
            applied=True,
            touched_files=tuple(dict.fromkeys([rel_py, *extra])),
            added_edges=(edge_desc,),
            impacted_dependents=deps,
            affected_tests=tuple(affected),
        )

    def unwire_port(
        self,
        consumer_uri: str,
        consumer_input_port: str,
        producer_uri: str | None = None,
        *,
        dry_run: bool = False,
    ) -> MutationPlan:
        """Disconnect matching PortWiringSpec(s) on consumer_uri."""
        validate_entity_ref(consumer_uri)
        index = build_hypergraph_index(self.repo_root)
        if consumer_uri not in index.nodes:
            raise KeyError(f"Consumer node '{consumer_uri}' does not exist.")

        dir_path, c_node = index.nodes[consumer_uri]
        kept = tuple(
            pw
            for pw in c_node.port_wirings
            if not (
                pw.consumer_input_port == consumer_input_port
                and (producer_uri is None or pw.producer_ref == producer_uri)
            )
        )
        if len(kept) == len(c_node.port_wirings):
            raise ValueError(
                f"No port wiring found on '{consumer_uri}:{consumer_input_port}'."
            )

        updated_node = self._clone_node(c_node, port_wirings=kept)
        node_py = dir_path / ".isai" / "node.py"
        rendered = render_node_module(updated_node, _extract_module_docstring(node_py))
        rel_py = node_py.relative_to(self.repo_root).as_posix()
        deps, _ = index.reverse_node_closure(consumer_uri)
        affected = index.select_affected_tests((consumer_uri,))["selected_tests"]

        if dry_run:
            return MutationPlan(
                operation="link:unwire-port",
                dry_run=True,
                applied=False,
                touched_files=(rel_py,),
                removed_edges=(f"{consumer_uri}:{consumer_input_port}",),
                impacted_dependents=deps,
                affected_tests=tuple(affected),
            )

        extra = self._commit_and_verify({node_py: rendered.encode("utf-8")})
        return MutationPlan(
            operation="link:unwire-port",
            dry_run=False,
            applied=True,
            touched_files=tuple(dict.fromkeys([rel_py, *extra])),
            removed_edges=(f"{consumer_uri}:{consumer_input_port}",),
            impacted_dependents=deps,
            affected_tests=tuple(affected),
        )

    def refactor_entity_ref(
        self,
        old_uri: str,
        new_uri: str,
        *,
        dry_run: bool = False,
    ) -> MutationPlan:
        """
        Atomically rename an exported #Symbol or retarget all inbound VAET references
        from old_uri -> new_uri across .isai/node.py manifests, domain Python modules
        (via AST string-constant spans), state_snapshot.json, and Markdown prose.
        """
        validate_entity_ref(old_uri)
        validate_entity_ref(new_uri)
        if old_uri == new_uri:
            raise ValueError("old_uri and new_uri are identical.")
        if old_uri in (
            "isai://root",
            "isai://root#GenesisKernel",
            "isai://root#NeuroVascularFundamental",
        ):
            raise ValueError(f"Cannot refactor constitutional anchor '{old_uri}'.")

        repo_nvf = load_repo_nvf(self.repo_root)
        if old_uri in repo_nvf.anchored_entity_refs:
            raise LinkMutationError(
                f"Cannot refactor '{old_uri}': entity is anchored inside conditionally-locked "
                "IL-1C 'isai://root#NeuroVascularFundamental' (requires 6-Step Algedonic ratification)."
            )

        index = build_hypergraph_index(self.repo_root)
        if old_uri not in index.valid_targets:
            raise ValueError(f"Source target '{old_uri}' does not exist in hypergraph.")

        old_scope, old_sym = parse_entity_ref(old_uri)
        new_scope, new_sym = parse_entity_ref(new_uri)
        old_owner_nid = f"isai://{old_scope}"

        # Case A: Renaming symbol within the same node (isai://x#Old -> isai://x#New)
        is_symbol_rename = (old_scope == new_scope) and (old_sym is not None) and (new_sym is not None)
        if not is_symbol_rename and new_uri not in index.valid_targets:
            raise ValueError(
                f"Cross-node retargeting requires '{new_uri}' to exist, or rename symbol within '{old_owner_nid}'."
            )

        writes: dict[Path, bytes] = {}
        added_edges: list[str] = []
        removed_edges: list[str] = []

        # 1. Update all .isai/node.py manifests cleanly via typed model reconstruction
        for nid, (d_path, node) in sorted(index.nodes.items()):
            changed = False
            new_bindings = list(node.symbol_bindings)
            if is_symbol_rename and nid == old_owner_nid:
                updated_b: list[SymbolBindingSpec] = []
                for b in new_bindings:
                    if b.symbol == old_sym:
                        updated_b.append(
                            SymbolBindingSpec(
                                symbol=new_sym,  # type: ignore[arg-type]
                                kind=b.kind,
                                target=b.target,
                                visibility=b.visibility,
                            )
                        )
                        changed = True
                    else:
                        updated_b.append(b)
                new_bindings = updated_b

            new_links: list[EdgeLinkSpec] = []
            for l in node.links:
                if l.target_ref == old_uri:
                    new_links.append(
                        EdgeLinkSpec(
                            target_ref=new_uri,
                            kind=l.kind,
                            rsoc_delivery=l.rsoc_delivery,
                            rationale=l.rationale,
                        )
                    )
                    removed_edges.append(f"{nid} -> {old_uri}")
                    added_edges.append(f"{nid} -> {new_uri}")
                    changed = True
                else:
                    new_links.append(l)

            new_wirings: list[PortWiringSpec] = []
            for pw in node.port_wirings:
                if pw.producer_ref == old_uri:
                    new_wirings.append(
                        PortWiringSpec(
                            consumer_input_port=pw.consumer_input_port,
                            producer_ref=new_uri,
                            producer_output_port=pw.producer_output_port,
                            rationale=pw.rationale,
                        )
                    )
                    removed_edges.append(f"{nid}:{pw.consumer_input_port} <- {old_uri}")
                    added_edges.append(f"{nid}:{pw.consumer_input_port} <- {new_uri}")
                    changed = True
                else:
                    new_wirings.append(pw)

            new_transitions: list[TransitionRule] = []
            for tr in node.transitions:
                if tr.target_ref == old_uri:
                    new_transitions.append(
                        TransitionRule(
                            trigger=tr.trigger,
                            target_ref=new_uri,
                            phase_mode=tr.phase_mode,
                            description=tr.description,
                        )
                    )
                    removed_edges.append(f"{nid} ~[{tr.trigger}]~> {old_uri}")
                    added_edges.append(f"{nid} ~[{tr.trigger}]~> {new_uri}")
                    changed = True
                else:
                    new_transitions.append(tr)

            if changed:
                rebuilt = self._clone_node(
                    node,
                    symbol_bindings=tuple(new_bindings),
                    links=tuple(new_links),
                    port_wirings=tuple(new_wirings),
                    transitions=tuple(new_transitions),
                )
                node_py = d_path / ".isai" / "node.py"
                writes[node_py] = render_node_module(
                    rebuilt, _extract_module_docstring(node_py)
                ).encode("utf-8")

        # 2. AST-guided literal replacement in domain Python files
        domain_py_candidates = [
            self.repo_root / "user" / ".isai" / "profile.py",
            self.repo_root / "knowledge" / ".isai" / "catalog.py",
            self.repo_root / ".isai" / "vector.py",
        ]
        for py_cand in domain_py_candidates:
            if not py_cand.is_file():
                continue
            orig_src = py_cand.read_text(encoding="utf-8")
            updated_src = _replace_python_string_constants(orig_src, old_uri, new_uri)
            if updated_src != orig_src:
                writes[py_cand] = updated_src.encode("utf-8")

        # 3. Markdown prose rewrite across all owned .md files (Genesis-safe & code-fence-safe)
        for nid, (d_path, node) in sorted(index.nodes.items()):
            for owned in node.owned_files:
                if not owned.endswith(".md"):
                    continue
                md_file = d_path / owned
                if not md_file.is_file():
                    continue
                orig_md = md_file.read_text(encoding="utf-8")
                is_root = md_file.resolve() == (self.repo_root / "README.md").resolve()
                new_md = _replace_markdown_prose_uri(
                    orig_md, old_uri, new_uri, is_root_readme=is_root
                )
                if new_md != orig_md:
                    writes[md_file] = new_md.encode("utf-8")

        touched_rels = tuple(
            sorted(p.relative_to(self.repo_root).as_posix() for p in writes.keys())
        )
        deps, _ = index.reverse_node_closure(old_owner_nid)
        affected = index.select_affected_tests((old_owner_nid,))["selected_tests"]

        if dry_run:
            return MutationPlan(
                operation="link:refactor",
                dry_run=True,
                applied=False,
                touched_files=touched_rels,
                added_edges=tuple(added_edges),
                removed_edges=tuple(removed_edges),
                impacted_dependents=deps,
                affected_tests=tuple(affected),
            )

        extra = self._commit_and_verify(writes)
        return MutationPlan(
            operation="link:refactor",
            dry_run=False,
            applied=True,
            touched_files=tuple(dict.fromkeys([*touched_rels, *extra])),
            added_edges=tuple(added_edges),
            removed_edges=tuple(removed_edges),
            impacted_dependents=deps,
            affected_tests=tuple(affected),
        )

    def scaffold_node(
        self,
        rel_path: str,
        title: str,
        goal: str,
        *,
        integrity_level: IntegrityLevel = IntegrityLevel.IL_2_CANONICAL,
        visibility: VisibilityScope = VisibilityScope.PUBLIC,
        route_trigger: str | None = None,
        phase_mode: PhaseMode = PhaseMode.STAGED_TRANSACTION,
        dry_run: bool = False,
    ) -> MutationPlan:
        """
        Atomically create a synchronized Fractal Directory Object (<rel_path>/README.md + .isai/node.py)
        and wire its parent's Router transition so zero-orphan-nodes & 100% reachability hold from birth.
        """
        clean_rel = Path(rel_path.strip("/"))
        if clean_rel == Path(".") or ".." in clean_rel.parts:
            raise ValueError(f"Invalid scaffold relative path '{rel_path}'.")

        node_id = rel_path_to_node_id(clean_rel)
        parent_id = rel_path_to_node_id(clean_rel.parent)

        index = build_hypergraph_index(self.repo_root)
        if node_id in index.nodes:
            raise ValueError(f"Node '{node_id}' already exists.")
        if parent_id not in index.nodes:
            raise ValueError(f"Parent node '{parent_id}' does not exist; scaffold parent first.")

        if clean_rel.parts[0] == "tasks":
            integrity_level = IntegrityLevel.IL_3_STAGING
            visibility = VisibilityScope.EPHEMERAL_STAGING

        doc_sym = (
            "".join(p.capitalize() for p in re.split(r"[^A-Za-z0-9]+", clean_rel.name) if p)
            + "Doc"
        )
        gov_links = [
            EdgeLinkSpec(
                target_ref="isai://root#GenesisKernel",
                kind=EdgeKind.GOVERNED_BY,
                rsoc_delivery=RSoCDeliveryPolicy.NONE,
            )
        ]
        if "isai://root#NeuroVascularFundamental" in index.valid_targets:
            gov_links.append(
                EdgeLinkSpec(
                    target_ref="isai://root#NeuroVascularFundamental",
                    kind=EdgeKind.GOVERNED_BY,
                    rsoc_delivery=RSoCDeliveryPolicy.NONE,
                )
            )

        new_node = ISAINodeSpec(
            node_id=node_id,
            title=title,
            integrity_level=integrity_level,
            visibility=visibility,
            parent_ref=parent_id,
            goal=goal,
            success_criteria=(f"Контракт узла {node_id} синхронизирован и проходит 'isai audit'.",),
            capabilities=(f"Инкапсуляция логики и артефактов домена '{clean_rel.as_posix()}'.",),
            owned_files=("README.md",),
            system_files=("node.py",),
            symbol_bindings=(
                SymbolBindingSpec(
                    symbol=doc_sym,
                    kind=SymbolBindingKind.OWNED_ARTIFACT,
                    target="README.md",
                ),
            ),
            links=tuple(gov_links),
        )

        target_dir = self.repo_root / clean_rel
        new_node_py = target_dir / ".isai" / "node.py"
        new_readme = target_dir / "README.md"

        writes: dict[Path, bytes] = {
            new_node_py: render_node_module(new_node).encode("utf-8"),
            new_readme: f"# {title}\n\n{new_node.render_sync_block()}\n".encode("utf-8"),
        }
        added_edges = [f"{node_id} -[PARENT_TOPOLOGY]-> {parent_id}"]

        # Wire incoming Router transition on parent (except ephemeral tasks/<ID> which forbids static canonical edges)
        parent_dir, parent_spec = index.nodes[parent_id]
        if visibility != VisibilityScope.EPHEMERAL_STAGING:
            slug = re.sub(r"[^A-Za-z0-9_]", "_", clean_rel.name.lower())
            trig = route_trigger or f"route_{slug}"
            tr = TransitionRule(
                trigger=trig,
                target_ref=node_id,
                phase_mode=phase_mode,
                description=f"Маршрутизация в дочерний узел {node_id}.",
            )
            updated_parent = self._clone_node(
                parent_spec, transitions=(*parent_spec.transitions, tr)
            )
            parent_py = parent_dir / ".isai" / "node.py"
            writes[parent_py] = render_node_module(
                updated_parent, _extract_module_docstring(parent_py)
            ).encode("utf-8")
            added_edges.append(f"{parent_id} ~[{trig}]~> {node_id}")

        touched_rels = tuple(
            sorted(p.relative_to(self.repo_root).as_posix() for p in writes.keys())
        )
        if dry_run:
            return MutationPlan(
                operation="link:scaffold-node",
                dry_run=True,
                applied=False,
                touched_files=touched_rels,
                added_edges=tuple(added_edges),
            )

        extra = self._commit_and_verify(
            writes,
            activate_staging_task=(
                node_id if visibility == VisibilityScope.EPHEMERAL_STAGING else None
            ),
        )
        return MutationPlan(
            operation="link:scaffold-node",
            dry_run=False,
            applied=True,
            touched_files=tuple(dict.fromkeys([*touched_rels, *extra])),
            added_edges=tuple(added_edges),
        )

    def decommission_node(
        self,
        node_uri: str,
        *,
        dry_run: bool = False,
    ) -> MutationPlan:
        """
        Safely decommission a leaf node using K8s Finalizer / VAET reverse-index blocking:
        refuses deletion if ANY external consumer (other than the parent's router transition)
        still references node_uri or any symbol inside node_uri.
        """
        validate_entity_ref(node_uri)
        scope, sym = parse_entity_ref(node_uri)
        if sym is not None or node_uri == "isai://root":
            raise ValueError(f"decommission_node requires a non-root node_id, got '{node_uri}'.")

        index = build_hypergraph_index(self.repo_root)
        if node_uri not in index.nodes:
            raise KeyError(f"Node '{node_uri}' does not exist.")

        # Check children first
        children = [
            nid for nid, (_, n) in index.nodes.items() if n.parent_ref == node_uri
        ]
        if children:
            raise ValueError(
                f"Cannot decommission '{node_uri}': still owns child node(s) {sorted(children)}."
            )

        node_dir, target_spec = index.nodes[node_uri]
        parent_id = target_spec.parent_ref
        assert parent_id is not None

        # Gather all inbound references to node_uri and its symbols, excluding self, parent's router transition,
        # and state_snapshot#active_tasks registration for ephemeral staging nodes.
        blocking: list[str] = []
        self_readme = f"{scope}/README.md"
        for target_cand in (node_uri, *(f"{node_uri}#{s}" for s in target_spec.defined_symbols)):
            for edge in index.inbound_to(target_cand):
                if edge.source_id == node_uri or edge.source_location == self_readme:
                    continue
                if (
                    edge.source_id == parent_id
                    and edge.target_ref == node_uri
                    and edge.edge_category.value == "ROUTER_TRANSITION"
                ):
                    continue
                if (
                    target_spec.visibility == VisibilityScope.EPHEMERAL_STAGING
                    and edge.source_id == "state_snapshot:active_tasks"
                    and edge.target_ref == node_uri
                    and edge.edge_category.value == "STATE_SNAPSHOT_REF"
                ):
                    continue
                blocking.append(
                    f"{edge.source_id} -> {edge.target_ref} ({edge.edge_category.value} @ {edge.source_location})"
                )

        if blocking:
            unique_blk = sorted(set(blocking))
            raise LinkMutationError(
                f"Blocked decommissioning '{node_uri}' due to {len(unique_blk)} active inbound external references: "
                + "; ".join(unique_blk)
            )

        writes: dict[Path, bytes] = {}
        removed_edges: list[str] = []
        parent_dir, parent_spec = index.nodes[parent_id]
        kept_tr = tuple(tr for tr in parent_spec.transitions if tr.target_ref != node_uri)
        if len(kept_tr) != len(parent_spec.transitions):
            updated_parent = self._clone_node(parent_spec, transitions=kept_tr)
            parent_py = parent_dir / ".isai" / "node.py"
            writes[parent_py] = render_node_module(
                updated_parent, _extract_module_docstring(parent_py)
            ).encode("utf-8")
            removed_edges.append(f"{parent_id} ~router~> {node_uri}")

        rel_del = scope_to_rel_path(scope).as_posix()
        touched_rels = tuple(
            sorted(p.relative_to(self.repo_root).as_posix() for p in writes.keys())
        )

        if dry_run:
            return MutationPlan(
                operation="link:decommission-node",
                dry_run=True,
                applied=False,
                touched_files=touched_rels,
                deleted_paths=(rel_del,),
                removed_edges=tuple(removed_edges),
            )

        extra = self._commit_and_verify(
            writes=writes,
            deletes=(node_dir,),
            deactivate_staging_task=(
                node_uri if target_spec.visibility == VisibilityScope.EPHEMERAL_STAGING else None
            ),
        )
        return MutationPlan(
            operation="link:decommission-node",
            dry_run=False,
            applied=True,
            touched_files=tuple(dict.fromkeys([*touched_rels, *extra])),
            deleted_paths=(rel_del,),
            removed_edges=tuple(removed_edges),
        )
