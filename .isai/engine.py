"""ISAI Deterministic Services (v0.2.5): 360° Contract & Visibility Auditor, IL-1C Lock, Sync & Bimodal RSoC."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from isai.atomic_io import TEMP_ARTIFACT_PREFIX, atomic_write_text, repository_write_lock
from isai.constitution import (
    BoundaryIgnoreSpec,
    DEFAULT_BOUNDARY_IGNORE,
    GENESIS_BYTE_LENGTH,
    GENESIS_CONSTITUTION,
    GENESIS_SHA256,
    IntegrityLevel,
)
from isai.contracts import (
    EdgeKind,
    ISAINodeSpec,
    PhaseMode,
    RSoCDeliveryPolicy,
    SYNC_BEGIN_MARKER,
    SYNC_END_MARKER,
    SymbolBindingKind,
    SymbolVisibility,
    VisibilityScope,
    parse_entity_ref,
    rel_path_to_node_id,
    resolve_schema_ref_type,
)
from isai.domain_models import KnowledgeCatalogSpec, UserProfileSpec
from isai.graph_index import (
    build_hypergraph_index,
    iter_functional_dirs,
    load_module_attr_isolated,
    load_repo_master_vector,
    load_repo_nvf,
    verify_node_py_ast_purity,
)
from isai.neuro_vascular import NeuroVascularFundamentalSpec
from isai.protocol import (
    AuditIssue,
    AuditReport,
    ChronicleEvent,
    HandleAccess,
    ImpactAssessment,
    SystemStateSnapshot,
    utc_now_iso,
)

__all__ = [
    "AuditIssue",
    "AuditReport",
    "SyncReport",
    "append_chronicle",
    "audit_repository",
    "build_clean_snapshot",
    "compile_rsoc",
    "compute_reachable_nodes",
    "discover_nodes",
    "evaluate_interface_cascade",
    "find_torn_temp_artifacts",
    "load_module_attr",
    "load_node_from_dir",
    "read_chronicle",
    "salvage_chronicle",
    "sync_repository",
    "write_chronicle_atomic",
]

_SPEC_DIGEST_RE = re.compile(r"<!--\s*isai:spec_digest=([0-9a-f]{64})\s*-->")
_NODE_ID_RE = re.compile(r"<!--\s*isai:node_id=([^\s>]+)\s*-->")
_VECTOR_DIGEST_RE = re.compile(r"<!--\s*isai:vector_digest=([0-9a-f]{64})\s*-->")
_NVF_DIGEST_RE = re.compile(r"<!--\s*isai:nvf_digest=([0-9a-f]{64})\s*-->")
_NVF_DSL_SHA256_RE = re.compile(r"<!--\s*isai:nvf_dsl_sha256=([0-9a-f]{64})\s*-->")

_FENCED_CODE_RE = re.compile(r"```[\s\S]*?```")
_HTML_COMMENT_RE = re.compile(r"<!--[\s\S]*?-->")
_MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
_PROSE_ISAI_URI_RE = re.compile(r"isai://([A-Za-z0-9_./#<>\[\]-]+)")
_PROSE_TX_RE = re.compile(r"\b(TX-[0-9]{4,})\b")
_PROSE_PAT_RE = re.compile(r"\b(PAT_[A-Z0-9_]+)\b")


class SyncReport(BaseModel):
    """Result of deterministic atomic README.md and VISION.md projection."""

    model_config = ConfigDict(frozen=True)

    updated_files: tuple[str, ...] = ()
    unchanged_files: tuple[str, ...] = ()


def load_module_attr(py_path: Path, module_namespace: str, attr_name: str) -> Any:
    """Dynamically load an attribute from a Python file using an isolated module namespace."""
    return load_module_attr_isolated(py_path, module_namespace, attr_name)


def load_node_from_dir(repo_root: Path, dir_path: Path) -> ISAINodeSpec:
    """AST-screen, load, and validate .isai/node.py -> NODE: ISAINodeSpec."""
    rel_dir = dir_path.relative_to(repo_root)
    slug = "root" if rel_dir == Path(".") else "_".join(rel_dir.parts)
    slug = re.sub(r"[^A-Za-z0-9_]", "_", slug)
    node_file = dir_path / ".isai" / "node.py"
    purity_errors = verify_node_py_ast_purity(node_file)
    if purity_errors:
        raise ValueError(f"Impure node manifest '{node_file}': {'; '.join(purity_errors)}")
    obj = load_module_attr(node_file, f"_isai_node_{slug}", "NODE")
    if not isinstance(obj, ISAINodeSpec):
        raise TypeError(
            f"'{node_file}' exported NODE of type {type(obj).__name__}, expected ISAINodeSpec."
        )
    return obj


def find_torn_temp_artifacts(
    repo_root: Path,
    boundary: BoundaryIgnoreSpec = DEFAULT_BOUNDARY_IGNORE,
) -> list[Path]:
    """Scan all non-ignored directories (including .isai/) for leftover .isai_tmp_* artifacts."""
    torn: list[Path] = []

    def _scan(directory: Path) -> None:
        for entry in sorted(directory.iterdir(), key=lambda p: p.name):
            rel = entry.relative_to(repo_root)
            if boundary.is_ignored(rel):
                continue
            if entry.name.startswith(TEMP_ARTIFACT_PREFIX):
                torn.append(entry)
                continue
            if entry.is_dir():
                _scan(entry)

    _scan(repo_root)
    return torn


def discover_nodes(
    repo_root: Path,
    boundary: BoundaryIgnoreSpec = DEFAULT_BOUNDARY_IGNORE,
) -> dict[str, tuple[Path, ISAINodeSpec]]:
    """Discover all valid ISAI directory nodes mapped by node_id -> (dir_path, ISAINodeSpec)."""
    nodes: dict[str, tuple[Path, ISAINodeSpec]] = {}
    for d in iter_functional_dirs(repo_root, boundary):
        node_py = d / ".isai" / "node.py"
        if node_py.is_file():
            node = load_node_from_dir(repo_root, d)
            nodes[node.node_id] = (d, node)
    return nodes


def _upsert_sync_section(existing_text: str, sync_block: str, default_header: str) -> str:
    """Insert or replace the ISAI sync block while preserving human prose outside markers."""
    if SYNC_BEGIN_MARKER in existing_text and SYNC_END_MARKER in existing_text:
        start_idx = existing_text.index(SYNC_BEGIN_MARKER)
        end_idx = existing_text.index(SYNC_END_MARKER) + len(SYNC_END_MARKER)
        before = existing_text[:start_idx]
        after = existing_text[end_idx:]
        if not after.endswith("\n"):
            after = after + "\n"
        return before + sync_block + after
    if existing_text:
        sep = "" if existing_text.endswith("\n\n") else ("\n" if existing_text.endswith("\n") else "\n\n")
        return f"{existing_text}{sep}{sync_block}\n"
    return f"{default_header}\n\n{sync_block}\n"


def sync_repository(
    repo_root: Path,
    boundary: BoundaryIgnoreSpec = DEFAULT_BOUNDARY_IGNORE,
) -> SyncReport:
    """
    Atomically project deterministic sync passports from .isai/node.py into paired README.md files,
    project MASTER_VECTOR into VISION.md, and project NEURO_VASCULAR_FUNDAMENTAL into FUNDAMENTAL.md
    without ever mutating the 586-byte Genesis header.
    """
    repo_root = repo_root.resolve()
    with repository_write_lock(repo_root):
        updated: list[str] = []
        unchanged: list[str] = []

        root_readme = repo_root / "README.md"
        genesis_check = GENESIS_CONSTITUTION.verify_genesis_header(root_readme)
        if not genesis_check.valid:
            raise RuntimeError(f"Refusing sync: {genesis_check.detail}")

        repo_vec = load_repo_master_vector(repo_root)
        vision_path = repo_root / "VISION.md"
        rendered_vision = repo_vec.render_markdown()
        if not vision_path.is_file() or vision_path.read_text(encoding="utf-8") != rendered_vision:
            atomic_write_text(vision_path, rendered_vision)
            updated.append("VISION.md")
        else:
            unchanged.append("VISION.md")

        repo_nvf = load_repo_nvf(repo_root)
        nvf_md_path = repo_root / "FUNDAMENTAL.md"
        rendered_nvf = repo_nvf.render_markdown()
        if not nvf_md_path.is_file() or nvf_md_path.read_text(encoding="utf-8") != rendered_nvf:
            atomic_write_text(nvf_md_path, rendered_nvf)
            updated.append("FUNDAMENTAL.md")
        else:
            unchanged.append("FUNDAMENTAL.md")

        nodes = discover_nodes(repo_root, boundary)
        for node_id, (dir_path, node) in sorted(nodes.items()):
            readme_path = dir_path / "README.md"
            rel_readme = readme_path.relative_to(repo_root).as_posix()
            sync_block = node.render_sync_block()

            if node_id == "isai://root":
                raw = readme_path.read_bytes()
                immutable_prefix = raw[:GENESIS_BYTE_LENGTH].decode("utf-8")
                tail = raw[GENESIS_BYTE_LENGTH:].decode("utf-8")
                new_tail = _upsert_sync_section(tail, sync_block, "")
                if not new_tail.startswith("\n"):
                    new_tail = "\n" + new_tail
                new_content = immutable_prefix + new_tail
            else:
                existing = readme_path.read_text(encoding="utf-8") if readme_path.is_file() else ""
                new_content = _upsert_sync_section(existing, sync_block, f"# {node.title}")

            old_content = readme_path.read_text(encoding="utf-8") if readme_path.is_file() else None
            if old_content != new_content:
                atomic_write_text(readme_path, new_content)
                updated.append(rel_readme)
            else:
                unchanged.append(rel_readme)

        post_check = GENESIS_CONSTITUTION.verify_genesis_header(root_readme)
        if not post_check.valid:
            raise RuntimeError(f"Post-sync IL-0 assertion failed: {post_check.detail}")

        return SyncReport(updated_files=tuple(updated), unchanged_files=tuple(unchanged))


def read_chronicle(repo_root: Path) -> list[ChronicleEvent]:
    """Read and validate all append-only ChronicleEvent lines from .isai/chronicle.jsonl."""
    ledger_path = repo_root / ".isai" / "chronicle.jsonl"
    if not ledger_path.is_file():
        return []
    events: list[ChronicleEvent] = []
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        data = json.loads(stripped)
        events.append(ChronicleEvent.model_validate(data))
    return events


def salvage_chronicle(repo_root: Path) -> tuple[list[ChronicleEvent], bool]:
    """Parse valid monotonic ChronicleEvents from .isai/chronicle.jsonl and flag torn trailing lines."""
    ledger_path = repo_root / ".isai" / "chronicle.jsonl"
    if not ledger_path.is_file():
        return [], False
    events: list[ChronicleEvent] = []
    had_corruption = False
    seen_tx: set[str] = set()
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            ev = ChronicleEvent.model_validate_json(stripped)
            expected_rev = len(events) + 1
            if ev.revision != expected_rev or ev.tx_id in seen_tx:
                had_corruption = True
                break
            events.append(ev)
            seen_tx.add(ev.tx_id)
        except Exception:
            had_corruption = True
            break
    return events, had_corruption


def write_chronicle_atomic(repo_root: Path, events: list[ChronicleEvent]) -> None:
    """Atomically write the complete validated ChronicleEvent list to .isai/chronicle.jsonl."""
    ledger_path = repo_root / ".isai" / "chronicle.jsonl"
    payload = "".join(
        json.dumps(ev.model_dump(mode="json"), ensure_ascii=False, sort_keys=True) + "\n"
        for ev in events
    )
    atomic_write_text(ledger_path, payload)


def append_chronicle(repo_root: Path, event: ChronicleEvent) -> None:
    """Append a validated ChronicleEvent to .isai/chronicle.jsonl via atomic file replacement."""
    existing = read_chronicle(repo_root)
    expected_rev = (existing[-1].revision + 1) if existing else 1
    if event.revision != expected_rev:
        raise ValueError(
            f"Non-monotonic chronicle revision: expected {expected_rev}, got {event.revision}."
        )
    if any(e.tx_id == event.tx_id for e in existing):
        raise ValueError(f"Duplicate tx_id '{event.tx_id}' in chronicle (Redundancy=FATAL).")
    write_chronicle_atomic(repo_root, [*existing, event])


def compute_reachable_nodes(
    nodes: dict[str, tuple[Path, ISAINodeSpec]],
    active_task_refs: tuple[str, ...] = (),
) -> set[str]:
    """Compute top-down reachable node_ids starting from 'isai://root' via Router transitions."""
    if "isai://root" not in nodes:
        return set()

    visited: set[str] = {"isai://root"}
    frontier: list[str] = ["isai://root"]
    active_task_nodes = {f"isai://{parse_entity_ref(r)[0]}" for r in active_task_refs}

    while frontier:
        current_id = frontier.pop(0)
        _, current_node = nodes[current_id]
        targets: list[str] = [
            f"isai://{parse_entity_ref(tr.target_ref)[0]}"
            for tr in current_node.transitions
        ]
        if current_id == "isai://tasks":
            targets.extend(sorted(active_task_nodes))

        for target_id in targets:
            if target_id in nodes and target_id not in visited:
                visited.add(target_id)
                frontier.append(target_id)

    return visited


def evaluate_interface_cascade(
    nodes: dict[str, tuple[Path, ISAINodeSpec]],
    mutated_node_ref: str,
    previous_interface_digest: str,
) -> ImpactAssessment:
    """Salsa Early-Cutoff + Transitive N-hop BFS Cascade Analyzer over VAET reverse edges."""
    if mutated_node_ref not in nodes:
        raise KeyError(f"Unknown node '{mutated_node_ref}'")
    _, mutated_node = nodes[mutated_node_ref]
    new_digest = mutated_node.interface_digest()
    if new_digest == previous_interface_digest:
        return ImpactAssessment(
            mutated_node_ref=mutated_node_ref,
            previous_interface_digest=previous_interface_digest,
            new_interface_digest=new_digest,
            early_cutoff=True,
            impacted_dependents=(),
            max_hop_depth=0,
        )

    reverse_adj: dict[str, set[str]] = {nid: set() for nid in nodes}
    for candidate_id, (_, candidate) in sorted(nodes.items()):
        for outbound in candidate.all_outbound_refs():
            scope, _ = parse_entity_ref(outbound)
            target_node = f"isai://{scope}"
            if target_node in reverse_adj and target_node != candidate_id:
                reverse_adj[target_node].add(candidate_id)

    visited: set[str] = {mutated_node_ref}
    frontier: list[str] = [mutated_node_ref]
    ordered_dependents: list[str] = []
    max_depth = 0
    depth = 0

    while frontier:
        next_level = sorted(
            {
                dep
                for curr in frontier
                for dep in reverse_adj.get(curr, ())
                if dep not in visited
            }
        )
        if not next_level:
            break
        depth += 1
        max_depth = depth
        visited.update(next_level)
        ordered_dependents.extend(next_level)
        frontier = next_level

    return ImpactAssessment(
        mutated_node_ref=mutated_node_ref,
        previous_interface_digest=previous_interface_digest,
        new_interface_digest=new_digest,
        early_cutoff=False,
        impacted_dependents=tuple(ordered_dependents),
        max_hop_depth=max_depth,
    )


def _is_in_subtree(caller_nid: str, owner_nid: str) -> bool:
    if owner_nid == "isai://root":
        return True
    caller_scope, _ = parse_entity_ref(caller_nid)
    owner_scope, _ = parse_entity_ref(owner_nid)
    return caller_scope == owner_scope or caller_scope.startswith(owner_scope + "/")


def _verify_node_symbol_bindings(
    repo_root: Path,
    dir_path: Path,
    node: ISAINodeSpec,
    issues: list[AuditIssue],
) -> int:
    """Physically verify every SymbolBindingSpec in a node against actual Python objects or files."""
    verified = 0
    rel_dir = dir_path.relative_to(repo_root)
    loc_prefix = "." if rel_dir == Path(".") else rel_dir.as_posix()
    slug_base = re.sub(r"[^A-Za-z0-9_]", "_", "root" if loc_prefix == "." else loc_prefix)

    for idx, binding in enumerate(node.symbol_bindings):
        b_loc = (
            f"{loc_prefix}/.isai/node.py#{binding.symbol}"
            if loc_prefix != "."
            else f".isai/node.py#{binding.symbol}"
        )
        if binding.kind == SymbolBindingKind.SYSTEM_ARTIFACT:
            target_file = dir_path / ".isai" / binding.target
            if not target_file.is_file():
                issues.append(
                    AuditIssue(
                        code="BROKEN_SYMBOL_BINDING",
                        location=b_loc,
                        message=f"System artifact '{binding.target}' for symbol '{binding.symbol}' is missing.",
                    )
                )
            else:
                verified += 1
        elif binding.kind == SymbolBindingKind.OWNED_ARTIFACT:
            target_file = dir_path / binding.target
            if not target_file.is_file():
                issues.append(
                    AuditIssue(
                        code="BROKEN_SYMBOL_BINDING",
                        location=b_loc,
                        message=f"Owned artifact '{binding.target}' for symbol '{binding.symbol}' is missing.",
                    )
                )
            else:
                verified += 1
        elif binding.kind == SymbolBindingKind.PYTHON_ATTR:
            py_rel, attr_name = binding.target.split(":", 1)
            candidate_sys = dir_path / ".isai" / py_rel
            candidate_owned = dir_path / py_rel
            py_path = candidate_sys if py_rel in node.system_files else candidate_owned
            if not py_path.is_file():
                issues.append(
                    AuditIssue(
                        code="BROKEN_SYMBOL_BINDING",
                        location=b_loc,
                        message=f"Python module '{py_rel}' for symbol '{binding.symbol}' does not exist.",
                    )
                )
                continue
            try:
                load_module_attr(py_path, f"_isai_sym_{slug_base}_{idx}_{binding.symbol}", attr_name)
                verified += 1
            except Exception as exc:
                issues.append(
                    AuditIssue(
                        code="BROKEN_SYMBOL_BINDING",
                        location=b_loc,
                        message=f"Symbol '{binding.symbol}' failed binding '{binding.target}': {exc}",
                    )
                )
    return verified


def _verify_contracts_wirings_and_visibility(
    repo_root: Path,
    nodes: dict[str, tuple[Path, ISAINodeSpec]],
    issues: list[AuditIssue],
) -> int:
    """
    Verify:
      1. Physical resolution of all IOPortSpec.schema_refs -> BROKEN_PORT_SCHEMA
      2. Bi-directional PortWiringSpec compatibility -> INCOMPATIBLE_PORT_WIRING
      3. VisibilityScope & SymbolVisibility boundaries -> VISIBILITY_VIOLATION
      4. IL-0 Genesis mutation protection -> IMMUTABLE_TARGET_VIOLATION
    """
    verified_wirings = 0

    for nid, (dir_path, node) in sorted(nodes.items()):
        src_loc = (dir_path / ".isai" / "node.py").relative_to(repo_root).as_posix()

        # 1. Verify IOPortSpec schema_refs resolve physically
        for port in (*node.inputs, *node.outputs):
            for sref in port.schema_refs:
                try:
                    resolve_schema_ref_type(sref)
                except Exception as exc:
                    issues.append(
                        AuditIssue(
                            code="BROKEN_PORT_SCHEMA",
                            location=f"{src_loc}#{port.name}",
                            message=f"Port '{port.name}' failed resolving schema_ref '{sref}': {exc}",
                        )
                    )

        # 2. Verify PortWiringSpec producer-consumer compatibility
        in_map = {p.name: p for p in node.inputs}
        for pw in node.port_wirings:
            prod_scope, _ = parse_entity_ref(pw.producer_ref)
            prod_nid = f"isai://{prod_scope}"
            if prod_nid not in nodes:
                continue  # Caught by UNRESOLVED_ENTITY_REF
            _, prod_node = nodes[prod_nid]
            out_map = {p.name: p for p in prod_node.outputs}
            if pw.producer_output_port not in out_map:
                issues.append(
                    AuditIssue(
                        code="INCOMPATIBLE_PORT_WIRING",
                        location=f"{src_loc}#{pw.consumer_input_port}",
                        message=(
                            f"Producer '{prod_nid}' has no output port '{pw.producer_output_port}' "
                            f"(wired to '{nid}:{pw.consumer_input_port}')."
                        ),
                    )
                )
                continue

            in_port = in_map[pw.consumer_input_port]
            out_port = out_map[pw.producer_output_port]
            if not out_port.schema_refs or not in_port.schema_refs:
                issues.append(
                    AuditIssue(
                        code="INCOMPATIBLE_PORT_WIRING",
                        location=f"{src_loc}#{pw.consumer_input_port}",
                        message=(
                            f"Port wiring '{nid}:{in_port.name}' <- '{prod_nid}:{out_port.name}' "
                            "requires explicit schema_refs on both producer and consumer ports."
                        ),
                    )
                )
                continue

            compatible = True
            try:
                in_types = tuple(
                    t
                    for t in (resolve_schema_ref_type(sr) for sr in in_port.schema_refs)
                    if isinstance(t, type)
                )
                for psr in out_port.schema_refs:
                    if psr in in_port.schema_refs:
                        continue
                    pt = resolve_schema_ref_type(psr)
                    if not (isinstance(pt, type) and in_types and issubclass(pt, in_types)):
                        compatible = False
                        break
            except Exception:
                compatible = False

            if not compatible:
                issues.append(
                    AuditIssue(
                        code="INCOMPATIBLE_PORT_WIRING",
                        location=f"{src_loc}#{pw.consumer_input_port}",
                        message=(
                            f"Type mismatch in port wiring: producer '{prod_nid}:{out_port.name}' "
                            f"({out_port.schema_refs}) is not assignable to consumer "
                            f"'{nid}:{in_port.name}' ({in_port.schema_refs})."
                        ),
                    )
                )
            else:
                verified_wirings += 1

        # 3 & 4. Check Visibility & IL-0 Immutability across all outbound edges
        outbound_specs: list[tuple[str, bool]] = []
        if node.parent_ref is not None:
            outbound_specs.append((node.parent_ref, False))
        for link in node.links:
            outbound_specs.append((link.target_ref, link.kind == EdgeKind.MUTATES_TARGET))
        for pw in node.port_wirings:
            outbound_specs.append((pw.producer_ref, False))
        for tr in node.transitions:
            outbound_specs.append((tr.target_ref, tr.phase_mode == PhaseMode.STAGED_TRANSACTION))

        for t_ref, is_mutating in outbound_specs:
            if t_ref in ("isai://root#GenesisKernel", "isai://root#NeuroVascularFundamental") and is_mutating:
                issues.append(
                    AuditIssue(
                        code="IMMUTABLE_TARGET_VIOLATION",
                        location=src_loc,
                        message=(
                            f"Node '{nid}' declares a static mutating edge/transition "
                            f"targeting protected constitutional target '{t_ref}'."
                        ),
                    )
                )

            t_scope, t_sym = parse_entity_ref(t_ref)
            t_nid = f"isai://{t_scope}"
            if t_nid not in nodes:
                continue
            _, target_node = nodes[t_nid]

            # Node visibility enforcement
            if target_node.visibility == VisibilityScope.EPHEMERAL_STAGING:
                if (
                    node.integrity_level
                    in (
                        IntegrityLevel.IL_1C_FUNDAMENTAL,
                        IntegrityLevel.IL_1_KERNEL,
                        IntegrityLevel.IL_2_CANONICAL,
                    )
                    or node.node_id == "isai://tasks"
                ):
                    issues.append(
                        AuditIssue(
                            code="VISIBILITY_VIOLATION",
                            location=src_loc,
                            message=(
                                f"Node '{nid}' ({node.integrity_level.value}) cannot declare a static "
                                f"edge to ephemeral staging node '{t_nid}'."
                            ),
                        )
                    )
            elif target_node.visibility == VisibilityScope.SUBTREE:
                if not (_is_in_subtree(nid, t_nid) or nid == target_node.parent_ref):
                    issues.append(
                        AuditIssue(
                            code="VISIBILITY_VIOLATION",
                            location=src_loc,
                            message=(
                                f"Node '{nid}' violates SUBTREE visibility of '{t_nid}'."
                            ),
                        )
                    )

            # Symbol visibility enforcement
            if t_sym is not None:
                sym_map = {b.symbol: b for b in target_node.symbol_bindings}
                b_spec = sym_map.get(t_sym)
                if (
                    b_spec is not None
                    and b_spec.visibility == SymbolVisibility.INTERNAL
                    and not _is_in_subtree(nid, t_nid)
                ):
                    issues.append(
                        AuditIssue(
                            code="VISIBILITY_VIOLATION",
                            location=src_loc,
                            message=(
                                f"Node '{nid}' references INTERNAL symbol '{t_ref}' outside subtree '{t_nid}'."
                            ),
                        )
                    )

    return verified_wirings


def _audit_markdown_cross_links(
    repo_root: Path,
    md_files: list[Path],
    valid_targets: set[str],
    known_tx_ids: set[str],
    known_pat_ids: set[str],
    issues: list[AuditIssue],
) -> tuple[int, int]:
    """Scan all repository Markdown documents for broken relative file links and inline prose citations."""
    checked_md = 0
    resolved_prose_refs = 0

    for md_path in sorted(set(md_files)):
        if not md_path.is_file():
            continue
        checked_md += 1
        rel_md = md_path.relative_to(repo_root).as_posix()
        raw_text = md_path.read_text(encoding="utf-8")
        clean_text = _FENCED_CODE_RE.sub("", raw_text)
        clean_text = _HTML_COMMENT_RE.sub("", clean_text)

        for m_link in _MD_LINK_RE.finditer(clean_text):
            raw_target = m_link.group(1).strip()
            if not raw_target:
                continue
            target_token = raw_target.split()[0]
            if (
                target_token.startswith(("http://", "https://", "mailto:", "#"))
                or "://" in target_token
                or "<" in target_token
                or ">" in target_token
            ):
                continue
            path_part = target_token.split("#", 1)[0]
            if not path_part:
                continue
            resolved_path = (md_path.parent / path_part).resolve()
            try:
                resolved_path.relative_to(repo_root)
                in_repo = True
            except ValueError:
                in_repo = False
            if not in_repo or not resolved_path.exists():
                issues.append(
                    AuditIssue(
                        code="BROKEN_MARKDOWN_LINK",
                        location=rel_md,
                        message=f"Broken relative Markdown link '{target_token}' in '{rel_md}'.",
                    )
                )
            else:
                resolved_prose_refs += 1

        for m_uri in _PROSE_ISAI_URI_RE.finditer(clean_text):
            raw_unstripped = m_uri.group(1)
            if "..." in raw_unstripped:
                continue
            raw_body = raw_unstripped.rstrip(".,;:")
            if not raw_body or any(ch in raw_body for ch in ("<", ">", "[", "]")):
                continue
            candidate_uri = f"isai://{raw_body}"
            if candidate_uri not in valid_targets:
                issues.append(
                    AuditIssue(
                        code="BROKEN_PROSE_REF",
                        location=rel_md,
                        message=f"Unresolved inline EntityRef '{candidate_uri}' in '{rel_md}'.",
                    )
                )
            else:
                resolved_prose_refs += 1

        for m_tx in _PROSE_TX_RE.finditer(clean_text):
            tx_id = m_tx.group(1)
            if tx_id not in known_tx_ids:
                issues.append(
                    AuditIssue(
                        code="BROKEN_PROSE_REF",
                        location=rel_md,
                        message=f"Unverified Chronicle transaction reference '{tx_id}' in '{rel_md}'.",
                    )
                )
            else:
                resolved_prose_refs += 1

        for m_pat in _PROSE_PAT_RE.finditer(clean_text):
            pat_id = m_pat.group(1)
            if pat_id not in known_pat_ids:
                issues.append(
                    AuditIssue(
                        code="BROKEN_PROSE_REF",
                        location=rel_md,
                        message=f"Unknown KnowledgeEntry reference '{pat_id}' in '{rel_md}'.",
                    )
                )
            else:
                resolved_prose_refs += 1

    return checked_md, resolved_prose_refs


def audit_repository(
    repo_root: Path,
    boundary: BoundaryIgnoreSpec = DEFAULT_BOUNDARY_IGNORE,
    require_clean_snapshot: bool = True,
    now_utc: datetime | None = None,
) -> AuditReport:
    """Execute complete deterministic Gate A 360° verification of the ISAI v0.2.0 repository."""
    repo_root = repo_root.resolve()
    issues: list[AuditIssue] = []

    for torn in find_torn_temp_artifacts(repo_root, boundary):
        issues.append(
            AuditIssue(
                code="TORN_TEMP_ARTIFACT",
                location=torn.relative_to(repo_root).as_posix(),
                message=f"Leftover crash artifact '{torn.name}' detected; run 'isai recover'.",
            )
        )

    genesis_res = GENESIS_CONSTITUTION.verify_genesis_header(repo_root / "README.md")
    if not genesis_res.valid:
        issues.append(
            AuditIssue(code="GENESIS_TAMPERED", location="README.md", message=genesis_res.detail)
        )

    repo_vec = None
    try:
        repo_vec = load_repo_master_vector(repo_root)
    except Exception as exc:
        issues.append(
            AuditIssue(
                code="INVALID_MASTER_VECTOR",
                location=".isai/vector.py",
                message=str(exc),
            )
        )

    vision_path = repo_root / "VISION.md"
    if not vision_path.is_file():
        issues.append(
            AuditIssue(code="VISION_MISSING", location="VISION.md", message="VISION.md is missing.")
        )
    elif repo_vec is not None:
        v_text = vision_path.read_text(encoding="utf-8")
        m = _VECTOR_DIGEST_RE.search(v_text)
        expected_v_digest = repo_vec.spec_digest()
        if m is None or m.group(1) != expected_v_digest:
            issues.append(
                AuditIssue(
                    code="VISION_OUT_OF_SYNC",
                    location="VISION.md",
                    message="VISION.md vector_digest does not match MASTER_VECTOR.spec_digest().",
                )
            )

    repo_nvf: NeuroVascularFundamentalSpec | None = None
    nvf_py_path = repo_root / ".isai" / "neuro_vascular.py"
    if not nvf_py_path.is_file():
        issues.append(
            AuditIssue(
                code="NVF_SPEC_MISSING",
                location=".isai/neuro_vascular.py",
                message="Sub-Genesis carrier '.isai/neuro_vascular.py' is missing.",
            )
        )
    else:
        try:
            repo_nvf = load_repo_nvf(repo_root)
        except Exception as exc:
            issues.append(
                AuditIssue(
                    code="INVALID_NVF_SPEC",
                    location=".isai/neuro_vascular.py",
                    message=str(exc),
                )
            )

    fundamental_md_path = repo_root / "FUNDAMENTAL.md"
    if not fundamental_md_path.is_file():
        issues.append(
            AuditIssue(
                code="NVF_MISSING",
                location="FUNDAMENTAL.md",
                message="Root Sub-Genesis projection 'FUNDAMENTAL.md' is missing.",
            )
        )
    elif repo_nvf is not None:
        nvf_md_text = fundamental_md_path.read_text(encoding="utf-8")
        m_spec = _NVF_DIGEST_RE.search(nvf_md_text)
        m_dsl = _NVF_DSL_SHA256_RE.search(nvf_md_text)
        if (
            m_spec is None
            or m_dsl is None
            or m_spec.group(1) != repo_nvf.spec_digest()
            or m_dsl.group(1) != repo_nvf.dsl_sha256()
        ):
            issues.append(
                AuditIssue(
                    code="NVF_OUT_OF_SYNC",
                    location="FUNDAMENTAL.md",
                    message="FUNDAMENTAL.md digests do not match NEURO_VASCULAR_FUNDAMENTAL.",
                )
            )

    functional_dirs = iter_functional_dirs(repo_root, boundary)
    nodes: dict[str, tuple[Path, ISAINodeSpec]] = {}
    verified_symbols_count = 0
    md_files_to_scan: list[Path] = []

    for d in functional_dirs:
        rel_d = d.relative_to(repo_root)
        loc = "." if rel_d == Path(".") else rel_d.as_posix()
        expected_node_id = rel_path_to_node_id(rel_d)

        readme_file = d / "README.md"
        isai_dir = d / ".isai"
        node_py = isai_dir / "node.py"
        node_loc = ".isai/node.py" if loc == "." else f"{loc}/.isai/node.py"

        if not readme_file.is_file():
            issues.append(
                AuditIssue(
                    code="MISSING_README",
                    location=loc,
                    message=f"Directory '{loc}' lacks required human interface README.md.",
                )
            )
        if not node_py.is_file():
            issues.append(
                AuditIssue(
                    code="MISSING_SYSTEM_NODE",
                    location=loc,
                    message=f"Directory '{loc}' lacks required agent interface .isai/node.py.",
                )
            )
            continue

        purity_errors = verify_node_py_ast_purity(node_py)
        if purity_errors:
            issues.append(
                AuditIssue(
                    code="IMPURE_NODE_AST",
                    location=node_loc,
                    message="; ".join(purity_errors),
                )
            )
            continue

        try:
            node = load_node_from_dir(repo_root, d)
        except Exception as exc:
            issues.append(
                AuditIssue(
                    code="INVALID_NODE_SPEC",
                    location=node_loc,
                    message=f"Failed to load/validate ISAINodeSpec: {exc}",
                )
            )
            continue

        if node.node_id != expected_node_id:
            issues.append(
                AuditIssue(
                    code="POSITIONAL_ID_MISMATCH",
                    location=node_loc,
                    message=f"Expected node_id '{expected_node_id}' for path '{loc}', got '{node.node_id}'.",
                )
            )

        if rel_d != Path("."):
            expected_parent = rel_path_to_node_id(rel_d.parent)
            if node.parent_ref != expected_parent:
                issues.append(
                    AuditIssue(
                        code="PARENT_TOPOLOGY_MISMATCH",
                        location=node_loc,
                        message=(
                            f"Node '{node.node_id}' declares parent_ref='{node.parent_ref}', "
                            f"expected positional parent '{expected_parent}'."
                        ),
                    )
                )

        nodes[node.node_id] = (d, node)

        actual_files = {
            f.name
            for f in d.iterdir()
            if f.is_file()
            and not f.name.startswith(TEMP_ARTIFACT_PREFIX)
            and not boundary.is_ignored(f.relative_to(repo_root))
        }
        declared_owned = set(node.owned_files)
        for orphan in sorted(actual_files - declared_owned):
            issues.append(
                AuditIssue(
                    code="ORPHAN_FILE",
                    location=f"{loc}/{orphan}" if loc != "." else orphan,
                    message=f"Unregistered file '{orphan}' violates zero-orphan-nodes in '{node.node_id}'.",
                )
            )
        for missing in sorted(declared_owned - actual_files):
            issues.append(
                AuditIssue(
                    code="MISSING_OWNED_FILE",
                    location=f"{loc}/{missing}" if loc != "." else missing,
                    message=f"Declared owned_file '{missing}' does not exist in '{node.node_id}'.",
                )
            )

        for owned_name in node.owned_files:
            if owned_name.endswith(".md"):
                md_files_to_scan.append(d / owned_name)

        actual_sys_files: set[str] = set()
        for item in isai_dir.iterdir():
            rel_item = item.relative_to(repo_root)
            if boundary.is_ignored(rel_item) or item.name.startswith(TEMP_ARTIFACT_PREFIX):
                continue
            if item.is_dir():
                issues.append(
                    AuditIssue(
                        code="UNEXPECTED_ISAI_SUBDIR",
                        location=rel_item.as_posix(),
                        message=f"Unexpected subdirectory '{item.name}' inside '{loc}/.isai/'.",
                    )
                )
            elif item.is_file():
                actual_sys_files.add(item.name)

        declared_sys = set(node.system_files)
        for orphan_sys in sorted(actual_sys_files - declared_sys):
            issues.append(
                AuditIssue(
                    code="ORPHAN_SYSTEM_FILE",
                    location=f"{loc}/.isai/{orphan_sys}" if loc != "." else f".isai/{orphan_sys}",
                    message=f"Unregistered system file '{orphan_sys}' inside .isai/ of '{node.node_id}'.",
                )
            )
        for missing_sys in sorted(declared_sys - actual_sys_files):
            issues.append(
                AuditIssue(
                    code="MISSING_SYSTEM_FILE",
                    location=f"{loc}/.isai/{missing_sys}" if loc != "." else f".isai/{missing_sys}",
                    message=f"Declared system_file '{missing_sys}' does not exist in .isai/ of '{node.node_id}'.",
                )
            )

        verified_symbols_count += _verify_node_symbol_bindings(repo_root, d, node, issues)

        if readme_file.is_file():
            r_text = readme_file.read_text(encoding="utf-8")
            if SYNC_BEGIN_MARKER not in r_text or SYNC_END_MARKER not in r_text:
                issues.append(
                    AuditIssue(
                        code="README_SYNC_MARKERS_MISSING",
                        location=readme_file.relative_to(repo_root).as_posix(),
                        message=f"README.md for '{node.node_id}' lacks ISAI sync markers.",
                    )
                )
            else:
                d_match = _SPEC_DIGEST_RE.search(r_text)
                n_match = _NODE_ID_RE.search(r_text)
                expected_digest = node.spec_digest()
                if d_match is None or d_match.group(1) != expected_digest:
                    issues.append(
                        AuditIssue(
                            code="README_DIGEST_MISMATCH",
                            location=readme_file.relative_to(repo_root).as_posix(),
                            message=(
                                f"README.md spec_digest out of sync with .isai/node.py for '{node.node_id}'."
                            ),
                        )
                    )
                if n_match is None or n_match.group(1) != node.node_id:
                    issues.append(
                        AuditIssue(
                            code="README_NODE_ID_MISMATCH",
                            location=readme_file.relative_to(repo_root).as_posix(),
                            message=f"README.md node_id marker does not match '{node.node_id}'.",
                        )
                    )

    valid_targets: set[str] = set()
    for node_id, (_, node) in nodes.items():
        valid_targets.add(node_id)
        for sym in node.defined_symbols:
            valid_targets.add(f"{node_id}#{sym}")

    resolved_refs_count = 0

    def _check_ref(ref: str, source_loc: str) -> None:
        nonlocal resolved_refs_count
        if ref not in valid_targets:
            issues.append(
                AuditIssue(
                    code="UNRESOLVED_ENTITY_REF",
                    location=source_loc,
                    message=f"Dangling EntityRef '{ref}' does not resolve to any registered node or symbol.",
                )
            )
        else:
            resolved_refs_count += 1

    if repo_vec is not None:
        _check_ref(repo_vec.vector_id, ".isai/vector.py")
    if repo_nvf is not None:
        _check_ref(repo_nvf.fundamental_id, ".isai/neuro_vascular.py")
        _check_ref(repo_nvf.governed_by, ".isai/neuro_vascular.py")
        for anc_ref in repo_nvf.anchored_entity_refs:
            _check_ref(anc_ref, ".isai/neuro_vascular.py")

    for node_id, (d, node) in sorted(nodes.items()):
        src = (d / ".isai" / "node.py").relative_to(repo_root).as_posix()
        for ref in node.all_outbound_refs():
            _check_ref(ref, src)

    # Verify port schemas, bi-directional wirings, visibility rings, and IL-0 protection
    verified_wirings_count = _verify_contracts_wirings_and_visibility(repo_root, nodes, issues)

    user_profile_py = repo_root / "user" / ".isai" / "profile.py"
    if user_profile_py.is_file():
        try:
            u_profile = load_module_attr(user_profile_py, "_isai_user_profile", "USER_PROFILE")
            if not isinstance(u_profile, UserProfileSpec):
                raise TypeError("USER_PROFILE must be UserProfileSpec")
            _check_ref(u_profile.profile_ref, "user/.isai/profile.py")
        except Exception as exc:
            issues.append(
                AuditIssue(
                    code="INVALID_USER_PROFILE",
                    location="user/.isai/profile.py",
                    message=str(exc),
                )
            )

    chronicle_events: list[ChronicleEvent] = []
    chronicle_path = repo_root / ".isai" / "chronicle.jsonl"
    if not chronicle_path.is_file():
        issues.append(
            AuditIssue(
                code="MISSING_CHRONICLE",
                location=".isai/chronicle.jsonl",
                message="Chrono-Graph ledger '.isai/chronicle.jsonl' is missing.",
            )
        )
    else:
        try:
            chronicle_events = read_chronicle(repo_root)
            seen_tx: set[str] = set()
            for expected_rev, ev in enumerate(chronicle_events, start=1):
                if ev.revision != expected_rev:
                    issues.append(
                        AuditIssue(
                            code="CHRONICLE_NON_MONOTONIC",
                            location=".isai/chronicle.jsonl",
                            message=f"Expected revision {expected_rev}, got {ev.revision}.",
                        )
                    )
                if ev.tx_id in seen_tx:
                    issues.append(
                        AuditIssue(
                            code="CHRONICLE_DUPLICATE_TX",
                            location=".isai/chronicle.jsonl",
                            message=f"Duplicate tx_id '{ev.tx_id}'.",
                        )
                    )
                seen_tx.add(ev.tx_id)
        except Exception as exc:
            issues.append(
                AuditIssue(
                    code="INVALID_CHRONICLE",
                    location=".isai/chronicle.jsonl",
                    message=f"Failed parsing chronicle.jsonl: {exc}",
                )
            )

    # Enforce IL-1C Conditional-Mutability Lock against Chronicle RATIFY_FUNDAMENTAL record
    if repo_nvf is not None and chronicle_events:
        ratify_events = [
            ev for ev in chronicle_events if ev.operation == "RATIFY_FUNDAMENTAL"
        ]
        if not ratify_events:
            issues.append(
                AuditIssue(
                    code="UNRATIFIED_FUNDAMENTAL_MUTATION",
                    location=".isai/neuro_vascular.py",
                    message=(
                        "IL-1C NeuroVascularFundamental has no RATIFY_FUNDAMENTAL record in "
                        "chronicle.jsonl (Operator ratification required)."
                    ),
                )
            )
        else:
            latest_ratify = ratify_events[-1]
            live_nvf_sha = repo_nvf.dsl_sha256()
            if (
                not latest_ratify.operator_approved
                or latest_ratify.ratified_nvf_digest != live_nvf_sha
            ):
                issues.append(
                    AuditIssue(
                        code="UNRATIFIED_FUNDAMENTAL_MUTATION",
                        location=".isai/neuro_vascular.py",
                        message=(
                            f"IL-1C NeuroVascularFundamental digest ({live_nvf_sha}) does not match "
                            f"latest Operator-ratified Chronicle record '{latest_ratify.tx_id}' "
                            f"({latest_ratify.ratified_nvf_digest}). Amend via 6-Step Algedonic Protocol only."
                        ),
                    )
                )

    # Enforce Vector-Mutation-Ledger traceability (ISAI-NVF v1.1 VM1..VM6)
    ledger_deviations: tuple[object, ...] = ()
    if repo_vec is not None:
        try:
            from isai.vector_ledger import (
                VectorMutationLedger,
                evaluate_ledger_deviations,
            )

            ledger = VectorMutationLedger(repo_root)
            if not ledger.path.is_file():
                issues.append(
                    AuditIssue(
                        code="VECTOR_LEDGER_MISSING",
                        location=".isai/vector_ledger.jsonl",
                        message=(
                            "Vector mutation ledger is missing: mutations of the goal vector are "
                            "untraceable (VM1). Initialise it with 'isai vector init'."
                        ),
                    )
                )
            else:
                ledger_state = ledger.state()
                ledger_deviations = tuple(
                    evaluate_ledger_deviations(ledger_state, repo_vec)
                )
                code_map = {
                    "ORPHAN_PENDING_PROPOSAL": "VECTOR_MUTATION_ORPHANED",
                    "CONFIRMED_MUTATION_UNAPPLIED": "VECTOR_MUTATION_UNAPPLIED",
                    "UNCONFIRMED_VECTOR_DRIFT": "VECTOR_DRIFT_UNCONFIRMED",
                    "VECTOR_DIGEST_MISMATCH": "VECTOR_DRIFT_UNCONFIRMED",
                    "STALE_PROPOSAL_ANCHOR": "VECTOR_PROPOSAL_STALE",
                    "UNCONFIRMED_VERSION_BUMP": "VECTOR_DRIFT_UNCONFIRMED",
                    "VERSION_NOT_BUMPED": "VECTOR_DRIFT_UNCONFIRMED",
                    "LEDGER_NOT_INITIALIZED": "VECTOR_LEDGER_MISSING",
                }
                for deviation in ledger_deviations:
                    if deviation.severity != "CRITICAL":
                        continue
                    issues.append(
                        AuditIssue(
                            code=code_map.get(deviation.code, "VECTOR_LEDGER_INVALID"),
                            location=".isai/vector_ledger.jsonl",
                            message=f"[{deviation.code}] {deviation.message}",
                        )
                    )
        except Exception as exc:
            issues.append(
                AuditIssue(
                    code="VECTOR_LEDGER_INVALID",
                    location=".isai/vector_ledger.jsonl",
                    message=f"Vector mutation ledger failed validation: {exc}",
                )
            )

    known_tx_ids = {e.tx_id for e in chronicle_events}
    known_pat_ids: set[str] = set()

    knowledge_catalog_py = repo_root / "knowledge" / ".isai" / "catalog.py"
    if knowledge_catalog_py.is_file():
        try:
            k_cat = load_module_attr(knowledge_catalog_py, "_isai_knowledge_catalog", "KNOWLEDGE_CATALOG")
            if not isinstance(k_cat, KnowledgeCatalogSpec):
                raise TypeError("KNOWLEDGE_CATALOG must be KnowledgeCatalogSpec")
            _check_ref(k_cat.catalog_ref, "knowledge/.isai/catalog.py")
            for entry in k_cat.entries:
                known_pat_ids.add(entry.entry_id)
                _check_ref(entry.related_node_ref, f"knowledge/.isai/catalog.py#{entry.entry_id}")
                if entry.origin_tx_id not in known_tx_ids:
                    issues.append(
                        AuditIssue(
                            code="UNVERIFIED_KNOWLEDGE_TX",
                            location=f"knowledge/.isai/catalog.py#{entry.entry_id}",
                            message=f"origin_tx_id '{entry.origin_tx_id}' not found in chronicle.jsonl.",
                        )
                    )
        except Exception as exc:
            issues.append(
                AuditIssue(
                    code="INVALID_KNOWLEDGE_CATALOG",
                    location="knowledge/.isai/catalog.py",
                    message=str(exc),
                )
            )

    snapshot_path = repo_root / "tasks" / ".isai" / "state_snapshot.json"
    current_rev = chronicle_events[-1].revision if chronicle_events else 0
    active_tasks_tuple: tuple[str, ...] = ()

    if not snapshot_path.is_file():
        issues.append(
            AuditIssue(
                code="MISSING_STATE_SNAPSHOT",
                location="tasks/.isai/state_snapshot.json",
                message="System state snapshot 'tasks/.isai/state_snapshot.json' is missing.",
            )
        )
    else:
        try:
            snap = SystemStateSnapshot.model_validate_json(
                snapshot_path.read_text(encoding="utf-8")
            )
            active_tasks_tuple = snap.active_tasks
            if snap.genesis_sha256 != GENESIS_SHA256:
                issues.append(
                    AuditIssue(
                        code="SNAPSHOT_GENESIS_MISMATCH",
                        location="tasks/.isai/state_snapshot.json",
                        message="Snapshot genesis_sha256 does not match Ring 0 GENESIS_SHA256.",
                    )
                )
            for t_ref in snap.active_tasks:
                _check_ref(t_ref, "tasks/.isai/state_snapshot.json#active_tasks")
            for h_rec in snap.open_handles:
                _check_ref(h_rec.target_ref, f"tasks/.isai/state_snapshot.json#{h_rec.handle_id}")
                if (
                    h_rec.target_ref == "isai://root#GenesisKernel"
                    and h_rec.access == HandleAccess.WRITE_LEASE
                ):
                    issues.append(
                        AuditIssue(
                            code="IMMUTABLE_TARGET_VIOLATION",
                            location=f"tasks/.isai/state_snapshot.json#{h_rec.handle_id}",
                            message="WRITE_LEASE is forbidden on immutable IL-0 'isai://root#GenesisKernel'.",
                        )
                    )
                if h_rec.is_expired(now_utc):
                    issues.append(
                        AuditIssue(
                            code="EXPIRED_HANDLE_LEASE",
                            location=f"tasks/.isai/state_snapshot.json#{h_rec.handle_id}",
                            message=(
                                f"Lease '{h_rec.handle_id}' owned by '{h_rec.owner_task_ref}' "
                                "has expired; run 'isai recover'."
                            ),
                        )
                    )

            if require_clean_snapshot and snap.audit_status == "VALID":
                if snap.revision != current_rev:
                    issues.append(
                        AuditIssue(
                            code="SNAPSHOT_REVISION_DRIFT",
                            location="tasks/.isai/state_snapshot.json",
                            message=(
                                f"Snapshot revision ({snap.revision}) != latest chronicle revision ({current_rev})."
                            ),
                        )
                    )
                if repo_vec is not None and snap.master_vector_digest != repo_vec.spec_digest():
                    issues.append(
                        AuditIssue(
                            code="SNAPSHOT_VECTOR_DRIFT",
                            location="tasks/.isai/state_snapshot.json",
                            message="Snapshot master_vector_digest is stale.",
                        )
                    )
                if repo_nvf is not None and snap.nvf_digest != repo_nvf.dsl_sha256():
                    issues.append(
                        AuditIssue(
                            code="SNAPSHOT_NVF_DRIFT",
                            location="tasks/.isai/state_snapshot.json",
                            message="Snapshot nvf_digest does not match live NEURO_VASCULAR_FUNDAMENTAL.",
                        )
                    )
                actual_spec_map = {nid: n.spec_digest() for nid, (_, n) in sorted(nodes.items())}
                actual_iface_map = {nid: n.interface_digest() for nid, (_, n) in sorted(nodes.items())}
                if snap.node_spec_digests != actual_spec_map:
                    issues.append(
                        AuditIssue(
                            code="SNAPSHOT_SPEC_DIGEST_DRIFT",
                            location="tasks/.isai/state_snapshot.json",
                            message="Snapshot node_spec_digests out of sync with live topology.",
                        )
                    )
                if snap.node_interface_digests != actual_iface_map:
                    issues.append(
                        AuditIssue(
                            code="SNAPSHOT_INTERFACE_DIGEST_DRIFT",
                            location="tasks/.isai/state_snapshot.json",
                            message="Snapshot node_interface_digests out of sync with live topology.",
                        )
                    )
        except Exception as exc:
            issues.append(
                AuditIssue(
                    code="INVALID_STATE_SNAPSHOT",
                    location="tasks/.isai/state_snapshot.json",
                    message=f"Invalid SystemStateSnapshot: {exc}",
                )
            )

    if "isai://root" in nodes:
        reachable = compute_reachable_nodes(nodes, active_tasks_tuple)
        for nid in sorted(set(nodes.keys()) - reachable):
            d_unreachable, _ = nodes[nid]
            rel_un = d_unreachable.relative_to(repo_root).as_posix()
            issues.append(
                AuditIssue(
                    code="UNREACHABLE_NODE",
                    location=f"{rel_un}/.isai/node.py",
                    message=(
                        f"Node '{nid}' is an unreachable island from 'isai://root' "
                        "(missing incoming Router transition or active_tasks registration)."
                    ),
                )
            )

    checked_md_count, prose_refs = _audit_markdown_cross_links(
        repo_root=repo_root,
        md_files=md_files_to_scan,
        valid_targets=valid_targets,
        known_tx_ids=known_tx_ids,
        known_pat_ids=known_pat_ids,
        issues=issues,
    )
    resolved_refs_count += prose_refs

    return AuditReport(
        valid=(len(issues) == 0),
        checked_nodes=tuple(sorted(nodes.keys())),
        verified_symbols_count=verified_symbols_count,
        verified_port_wirings_count=verified_wirings_count,
        resolved_refs_count=resolved_refs_count,
        checked_markdown_files_count=checked_md_count,
        chronicle_events_count=len(chronicle_events),
        current_revision=current_rev,
        issues=tuple(issues),
    )


def build_clean_snapshot(
    repo_root: Path,
    revision: int,
    active_tasks: tuple[str, ...] = (),
    open_handles: tuple[Any, ...] = (),
    audit_status: str = "VALID",
) -> SystemStateSnapshot:
    """Compute an authoritative SystemStateSnapshot from the current live repository topology."""
    resolved_root = repo_root.resolve()
    nodes = discover_nodes(resolved_root)
    repo_vec = load_repo_master_vector(resolved_root)
    repo_nvf = load_repo_nvf(resolved_root)
    return SystemStateSnapshot(
        revision=revision,
        timestamp_utc=utc_now_iso(),
        genesis_sha256=GENESIS_SHA256,
        nvf_version=repo_nvf.version,
        nvf_digest=repo_nvf.dsl_sha256(),
        master_vector_version=repo_vec.version,
        master_vector_digest=repo_vec.spec_digest(),
        active_tasks=active_tasks,
        open_handles=open_handles,
        node_spec_digests={nid: n.spec_digest() for nid, (_, n) in sorted(nodes.items())},
        node_interface_digests={nid: n.interface_digest() for nid, (_, n) in sorted(nodes.items())},
        audit_status=audit_status,  # type: ignore[arg-type]
    )


def _build_linked_interface_stubs(
    target_node: ISAINodeSpec,
    nodes: dict[str, tuple[Path, ISAINodeSpec]],
) -> list[dict[str, Any]]:
    """
    HippoRAG 2-inspired 1-hop typed edge projection for RSoC Data Delivery.
    Projects compact public interface stubs for linked neighbors according to RSoCDeliveryPolicy
    without leaking internal implementation files or Control Plane digest maps.
    """
    # Group edge roles & highest delivery policy per neighbor node_id
    neighbor_meta: dict[str, dict[str, Any]] = {}

    def _register(
        ref: str,
        role: str,
        policy: RSoCDeliveryPolicy,
        wired_output_port: str | None = None,
    ) -> None:
        scope, sym = parse_entity_ref(ref)
        nid = f"isai://{scope}"
        if nid == target_node.node_id or nid not in nodes or policy == RSoCDeliveryPolicy.NONE:
            return
        entry = neighbor_meta.setdefault(
            nid,
            {
                "roles": [],
                "symbols": [],
                "wired_outputs": [],
                "full_contract": False,
            },
        )
        if role not in entry["roles"]:
            entry["roles"].append(role)
        if sym and sym not in entry["symbols"]:
            entry["symbols"].append(sym)
        if wired_output_port and wired_output_port not in entry["wired_outputs"]:
            entry["wired_outputs"].append(wired_output_port)
        if policy == RSoCDeliveryPolicy.FULL_CONTRACT:
            entry["full_contract"] = True

    for link in target_node.links:
        _register(link.target_ref, f"LINK:{link.kind.value}", link.rsoc_delivery)
    for pw in target_node.port_wirings:
        _register(
            pw.producer_ref,
            f"PORT_WIRING:{pw.consumer_input_port}<-{pw.producer_output_port}",
            RSoCDeliveryPolicy.INTERFACE_STUB,
            wired_output_port=pw.producer_output_port,
        )
    for tr in target_node.transitions:
        _register(
            tr.target_ref,
            f"TRANSITION:{tr.trigger}[{tr.phase_mode.value}]",
            RSoCDeliveryPolicy.INTERFACE_STUB,
        )

    stubs: list[dict[str, Any]] = []
    for nid in sorted(neighbor_meta.keys()):
        meta = neighbor_meta[nid]
        _, n_spec = nodes[nid]
        public_syms = [
            {"symbol": b.symbol, "kind": b.kind.value}
            for b in n_spec.symbol_bindings
            if b.visibility == SymbolVisibility.PUBLIC
            and (not meta["symbols"] or b.symbol in meta["symbols"] or meta["full_contract"])
        ]
        if meta["full_contract"]:
            ports_out = [p.model_dump(mode="json") for p in n_spec.outputs]
            ports_in = [p.model_dump(mode="json") for p in n_spec.inputs]
        else:
            ports_out = [
                p.model_dump(mode="json")
                for p in n_spec.outputs
                if not meta["wired_outputs"] or p.name in meta["wired_outputs"]
            ]
            ports_in = [p.model_dump(mode="json") for p in n_spec.inputs if p.required]

        stub: dict[str, Any] = {
            "node_id": n_spec.node_id,
            "title": n_spec.title,
            "integrity_level": n_spec.integrity_level.value,
            "visibility": n_spec.visibility.value,
            "edge_roles": meta["roles"],
            "goal": n_spec.goal,
            "invariants": list(n_spec.invariants),
            "public_symbols": public_syms,
            "relevant_inputs": ports_in,
            "relevant_outputs": ports_out,
        }
        if meta["full_contract"]:
            stub["transitions"] = [t.model_dump(mode="json") for t in n_spec.transitions]
        stubs.append(stub)

    return stubs


def compile_rsoc(
    repo_root: Path,
    target_uri: str,
    focus_tags: tuple[str, ...] = (),
) -> dict[str, Any]:
    """
    Windows GPO RSoP + HippoRAG 2 + Bimodal U-Curve Resultant Set of Context (RSoC v0.2.5) Compiler.
    Injects IL-0 Genesis + IL-1C Neuro-Vascular Primacy Head at the top, minimal 1-hop Data Plane
    contract/stubs in the partitioned middle, and IL-1C Terminal Execution Guard (Algedonic + STOP-1..4)
    at the final key of the packet (Recency Peak), withholding Control Plane digests.
    """
    repo_root = repo_root.resolve()
    repo_vec = load_repo_master_vector(repo_root)
    repo_nvf = load_repo_nvf(repo_root)
    scope, symbol = parse_entity_ref(target_uri)
    target_node_id = f"isai://{scope}"
    index = build_hypergraph_index(repo_root)
    nodes = index.nodes
    if target_node_id not in nodes:
        raise KeyError(f"Target node '{target_node_id}' not found in repository topology.")

    _, target_node = nodes[target_node_id]

    ancestors: list[ISAINodeSpec] = []
    cursor = target_node.parent_ref
    while cursor is not None and cursor in nodes:
        _, parent_node = nodes[cursor]
        ancestors.append(parent_node)
        cursor = parent_node.parent_ref
    ancestors.reverse()

    linked_stubs = _build_linked_interface_stubs(target_node, nodes)

    operator_slice: dict[str, Any] = {}
    user_profile_py = repo_root / "user" / ".isai" / "profile.py"
    if user_profile_py.is_file():
        u_prof: UserProfileSpec = load_module_attr(
            user_profile_py, "_isai_user_profile_rsoc", "USER_PROFILE"
        )
        tag_filter = set(focus_tags)
        matched_comp = [
            {
                "domain": c.domain,
                "level": c.level,
                "calibration_hint": c.calibration_hint,
            }
            for c in u_prof.competencies
            if not tag_filter or bool(tag_filter.intersection(c.tags))
        ]
        operator_slice = {
            "archetype": u_prof.archetype,
            "directives": [d.rule for d in u_prof.directives],
            "competencies": matched_comp,
        }

    knowledge_slice: list[dict[str, Any]] = []
    knowledge_py = repo_root / "knowledge" / ".isai" / "catalog.py"
    if knowledge_py.is_file():
        k_cat: KnowledgeCatalogSpec = load_module_attr(
            knowledge_py, "_isai_knowledge_rsoc", "KNOWLEDGE_CATALOG"
        )
        tag_filter = set(focus_tags)
        linked_neighbor_ids = {s["node_id"] for s in linked_stubs}
        for entry in k_cat.entries:
            node_match = entry.related_node_ref in (
                target_node_id,
                "isai://root",
                *linked_neighbor_ids,
            )
            tag_match = bool(tag_filter and tag_filter.intersection(entry.applicability_tags))
            if node_match or tag_match or not tag_filter:
                knowledge_slice.append(
                    {
                        "entry_id": entry.entry_id,
                        "category": entry.category,
                        "title": entry.title,
                        "insight": entry.distilled_insight,
                    }
                )

    return {
        "rsoc_schema": "0.2.5",
        "requested_uri": target_uri,
        "focused_symbol": symbol,
        "enforced_genesis": {
            "priority": GENESIS_CONSTITUTION.meta_priority,
            "mandate": GENESIS_CONSTITUTION.core_mandate,
            "axioms": list(GENESIS_CONSTITUTION.axioms),
            "pipeline": " -> ".join(GENESIS_CONSTITUTION.operational_pipeline),
            "policy": " | ".join(GENESIS_CONSTITUTION.execution_policy),
        },
        "enforced_neuro_vascular_frame": repo_nvf.primacy_head_packet(),
        "master_vector_anchor": {
            "version": repo_vec.version,
            "north_star": repo_vec.north_star_statement,
        },
        "inherited_scope_invariants": [
            {
                "node_id": anc.node_id,
                "integrity_level": anc.integrity_level.value,
                "invariants": list(anc.invariants),
            }
            for anc in ancestors
        ],
        "active_node_contract": {
            "node_id": target_node.node_id,
            "title": target_node.title,
            "integrity_level": target_node.integrity_level.value,
            "visibility": target_node.visibility.value,
            "goal": target_node.goal,
            "success_criteria": list(target_node.success_criteria),
            "capabilities": list(target_node.capabilities),
            "invariants": list(target_node.invariants),
            "inputs": [p.model_dump(mode="json") for p in target_node.inputs],
            "outputs": [p.model_dump(mode="json") for p in target_node.outputs],
            "port_wirings": [pw.model_dump(mode="json") for pw in target_node.port_wirings],
            "owned_files": list(target_node.owned_files),
            "symbol_bindings": [b.model_dump(mode="json") for b in target_node.symbol_bindings],
            "links": [l.model_dump(mode="json") for l in target_node.links],
            "transitions": [t.model_dump(mode="json") for t in target_node.transitions],
        },
        "linked_interface_stubs": linked_stubs,
        "operator_calibration": operator_slice,
        "distilled_knowledge": knowledge_slice,
        "terminal_execution_guard": repo_nvf.recency_tail_packet(),
    }
