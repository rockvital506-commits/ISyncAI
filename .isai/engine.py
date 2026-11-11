"""ISAI Deterministic Services: Topology Loader, Audit Gatekeeper, Sync Projector, Chronicle & RSoC Compiler."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from isai.constitution import (
    BoundaryIgnoreSpec,
    DEFAULT_BOUNDARY_IGNORE,
    GENESIS_BYTE_LENGTH,
    GENESIS_CONSTITUTION,
    GENESIS_SHA256,
)
from isai.contracts import (
    ISAINodeSpec,
    SYNC_BEGIN_MARKER,
    SYNC_END_MARKER,
    parse_entity_ref,
    rel_path_to_node_id,
)
from isai.domain_models import KnowledgeCatalogSpec, UserProfileSpec
from isai.protocol import (
    ChronicleEvent,
    ImpactAssessment,
    SystemStateSnapshot,
)
from isai.vector import MASTER_VECTOR

_SPEC_DIGEST_RE = re.compile(r"<!--\s*isai:spec_digest=([0-9a-f]{64})\s*-->")
_NODE_ID_RE = re.compile(r"<!--\s*isai:node_id=([^\s>]+)\s*-->")
_VECTOR_DIGEST_RE = re.compile(r"<!--\s*isai:vector_digest=([0-9a-f]{64})\s*-->")


class AuditIssue(BaseModel):
    """Single structural, cryptographic, or referential violation detected during AUDIT."""

    model_config = ConfigDict(frozen=True)

    code: str
    location: str
    message: str


class AuditReport(BaseModel):
    """Comprehensive deterministic Gate A verification report."""

    model_config = ConfigDict(frozen=True)

    valid: bool
    checked_nodes: tuple[str, ...] = ()
    resolved_refs_count: int = 0
    chronicle_events_count: int = 0
    current_revision: int = 0
    issues: tuple[AuditIssue, ...] = ()


class SyncReport(BaseModel):
    """Result of deterministic README.md and VISION.md projection."""

    model_config = ConfigDict(frozen=True)

    updated_files: tuple[str, ...] = ()
    unchanged_files: tuple[str, ...] = ()


def load_module_attr(py_path: Path, module_namespace: str, attr_name: str) -> Any:
    """Dynamically load an attribute from a Python file using an isolated module namespace."""
    spec = importlib.util.spec_from_file_location(module_namespace, py_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to create module spec for {py_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, attr_name):
        raise AttributeError(f"File '{py_path}' does not export required symbol '{attr_name}'.")
    return getattr(module, attr_name)


def load_node_from_dir(repo_root: Path, dir_path: Path) -> ISAINodeSpec:
    """Load and validate .isai/node.py -> NODE: ISAINodeSpec for a repository directory."""
    rel_dir = dir_path.relative_to(repo_root)
    slug = "root" if rel_dir == Path(".") else "_".join(rel_dir.parts)
    slug = re.sub(r"[^A-Za-z0-9_]", "_", slug)
    node_file = dir_path / ".isai" / "node.py"
    obj = load_module_attr(node_file, f"_isai_node_{slug}", "NODE")
    if not isinstance(obj, ISAINodeSpec):
        raise TypeError(
            f"'{node_file}' exported NODE of type {type(obj).__name__}, expected ISAINodeSpec."
        )
    return obj


def _iter_functional_dirs(
    repo_root: Path,
    boundary: BoundaryIgnoreSpec = DEFAULT_BOUNDARY_IGNORE,
) -> list[Path]:
    """Return sorted list of all non-ignored functional directories (excluding .isai dirs themselves)."""
    result: list[Path] = [repo_root]

    def _walk(current: Path) -> None:
        for entry in sorted(current.iterdir(), key=lambda p: p.name):
            if not entry.is_dir():
                continue
            rel = entry.relative_to(repo_root)
            if boundary.is_ignored(rel):
                continue
            if entry.name == ".isai":
                continue
            result.append(entry)
            _walk(entry)

    _walk(repo_root)
    return result


def discover_nodes(
    repo_root: Path,
    boundary: BoundaryIgnoreSpec = DEFAULT_BOUNDARY_IGNORE,
) -> dict[str, tuple[Path, ISAINodeSpec]]:
    """Discover all valid ISAI directory nodes mapped by node_id -> (dir_path, ISAINodeSpec)."""
    nodes: dict[str, tuple[Path, ISAINodeSpec]] = {}
    for d in _iter_functional_dirs(repo_root, boundary):
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
    Project deterministic sync passports from .isai/node.py into paired README.md files
    and project MASTER_VECTOR into VISION.md without ever mutating the 586-byte Genesis header.
    """
    repo_root = repo_root.resolve()
    updated: list[str] = []
    unchanged: list[str] = []

    # 1. Verify IL-0 Genesis header BEFORE touching root README.md
    root_readme = repo_root / "README.md"
    genesis_check = GENESIS_CONSTITUTION.verify_genesis_header(root_readme)
    if not genesis_check.valid:
        raise RuntimeError(f"Refusing sync: {genesis_check.detail}")

    # 2. Sync VISION.md from MASTER_VECTOR
    vision_path = repo_root / "VISION.md"
    rendered_vision = MASTER_VECTOR.render_markdown()
    if not vision_path.is_file() or vision_path.read_text(encoding="utf-8") != rendered_vision:
        vision_path.write_text(rendered_vision, encoding="utf-8")
        updated.append("VISION.md")
    else:
        unchanged.append("VISION.md")

    # 3. Sync every functional node's README.md
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
            readme_path.write_text(new_content, encoding="utf-8")
            updated.append(rel_readme)
        else:
            unchanged.append(rel_readme)

    # 4. Post-sync IL-0 sanity check
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
    for idx, line in enumerate(ledger_path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        data = json.loads(stripped)
        events.append(ChronicleEvent.model_validate(data))
    return events


def append_chronicle(repo_root: Path, event: ChronicleEvent) -> None:
    """Append a validated ChronicleEvent to .isai/chronicle.jsonl enforcing monotonic revision."""
    existing = read_chronicle(repo_root)
    expected_rev = (existing[-1].revision + 1) if existing else 1
    if event.revision != expected_rev:
        raise ValueError(
            f"Non-monotonic chronicle revision: expected {expected_rev}, got {event.revision}."
        )
    if any(e.tx_id == event.tx_id for e in existing):
        raise ValueError(f"Duplicate tx_id '{event.tx_id}' in chronicle (Redundancy=FATAL).")
    ledger_path = repo_root / ".isai" / "chronicle.jsonl"
    line = json.dumps(event.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
    with ledger_path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def evaluate_interface_cascade(
    nodes: dict[str, tuple[Path, ISAINodeSpec]],
    mutated_node_ref: str,
    previous_interface_digest: str,
) -> ImpactAssessment:
    """
    Salsa Early-Cutoff Cascade Analyzer:
    If the mutated node's public interface_digest is unchanged, halt cascade immediately (early_cutoff=True).
    Otherwise, compute all nodes holding direct references/transitions/inheritance to mutated_node_ref.
    """
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
        )

    dependents: list[str] = []
    for candidate_id, (_, candidate) in sorted(nodes.items()):
        if candidate_id == mutated_node_ref:
            continue
        for outbound in candidate.all_outbound_refs():
            scope, _ = parse_entity_ref(outbound)
            target_node = f"isai://{scope}"
            if target_node == mutated_node_ref:
                dependents.append(candidate_id)
                break

    return ImpactAssessment(
        mutated_node_ref=mutated_node_ref,
        previous_interface_digest=previous_interface_digest,
        new_interface_digest=new_digest,
        early_cutoff=False,
        impacted_dependents=tuple(dependents),
    )


def audit_repository(
    repo_root: Path,
    boundary: BoundaryIgnoreSpec = DEFAULT_BOUNDARY_IGNORE,
    require_clean_snapshot: bool = True,
) -> AuditReport:
    """
    Execute complete deterministic Gate A verification of the ISAI repository:
      1. IL-0 Genesis byte-exact SHA-256 check
      2. Master Vector <-> VISION.md digest parity
      3. Fractal directory isomorphism (every dir has README.md + .isai/node.py)
      4. Zero-orphan-files across both functional directories and .isai/ system directories
      5. README.md <-> .isai/node.py spec_digest synchronization
      6. 100% EntityRef hypergraph & symbol resolution + acyclic parent hierarchy
      7. Chronicle monotonicity & Watchdog state_snapshot.json consistency
    """
    repo_root = repo_root.resolve()
    issues: list[AuditIssue] = []

    # 1. IL-0 Genesis check
    genesis_res = GENESIS_CONSTITUTION.verify_genesis_header(repo_root / "README.md")
    if not genesis_res.valid:
        issues.append(
            AuditIssue(code="GENESIS_TAMPERED", location="README.md", message=genesis_res.detail)
        )

    # 2. Master Vector check
    vision_path = repo_root / "VISION.md"
    if not vision_path.is_file():
        issues.append(
            AuditIssue(code="VISION_MISSING", location="VISION.md", message="VISION.md is missing.")
        )
    else:
        v_text = vision_path.read_text(encoding="utf-8")
        m = _VECTOR_DIGEST_RE.search(v_text)
        expected_v_digest = MASTER_VECTOR.spec_digest()
        if m is None or m.group(1) != expected_v_digest:
            issues.append(
                AuditIssue(
                    code="VISION_OUT_OF_SYNC",
                    location="VISION.md",
                    message="VISION.md vector_digest does not match MASTER_VECTOR.spec_digest().",
                )
            )

    # 3 & 4. Fractal directory discovery, ownership & zero-orphan checks
    functional_dirs = _iter_functional_dirs(repo_root, boundary)
    nodes: dict[str, tuple[Path, ISAINodeSpec]] = {}

    for d in functional_dirs:
        rel_d = d.relative_to(repo_root)
        loc = "." if rel_d == Path(".") else rel_d.as_posix()
        expected_node_id = rel_path_to_node_id(rel_d)

        readme_file = d / "README.md"
        isai_dir = d / ".isai"
        node_py = isai_dir / "node.py"

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

        try:
            node = load_node_from_dir(repo_root, d)
        except Exception as exc:
            issues.append(
                AuditIssue(
                    code="INVALID_NODE_SPEC",
                    location=f"{loc}/.isai/node.py",
                    message=f"Failed to load/validate ISAINodeSpec: {exc}",
                )
            )
            continue

        if node.node_id != expected_node_id:
            issues.append(
                AuditIssue(
                    code="POSITIONAL_ID_MISMATCH",
                    location=f"{loc}/.isai/node.py",
                    message=f"Expected node_id '{expected_node_id}' for path '{loc}', got '{node.node_id}'.",
                )
            )

        if rel_d != Path("."):
            expected_parent = rel_path_to_node_id(rel_d.parent)
            if node.parent_ref != expected_parent:
                issues.append(
                    AuditIssue(
                        code="PARENT_TOPOLOGY_MISMATCH",
                        location=f"{loc}/.isai/node.py",
                        message=(
                            f"Node '{node.node_id}' declares parent_ref='{node.parent_ref}', "
                            f"expected positional parent '{expected_parent}'."
                        ),
                    )
                )

        nodes[node.node_id] = (d, node)

        # Check owned_files in functional directory
        actual_files = {
            f.name
            for f in d.iterdir()
            if f.is_file() and not boundary.is_ignored(f.relative_to(repo_root))
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

        # Check system_files inside .isai/
        actual_sys_files: set[str] = set()
        for item in isai_dir.iterdir():
            rel_item = item.relative_to(repo_root)
            if boundary.is_ignored(rel_item):
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

        # 5. Check README.md sync digest
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

    # 6. Build symbol table & resolve all EntityRefs
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

    _check_ref(MASTER_VECTOR.vector_id, ".isai/vector.py")
    for node_id, (d, node) in sorted(nodes.items()):
        src = (d / ".isai" / "node.py").relative_to(repo_root).as_posix()
        for ref in node.all_outbound_refs():
            _check_ref(ref, src)

    # Validate /user/.isai/profile.py if present
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

    # 7. Validate Chronicle & Knowledge Catalog & Watchdog Snapshot
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

    known_tx_ids = {e.tx_id for e in chronicle_events}

    knowledge_catalog_py = repo_root / "knowledge" / ".isai" / "catalog.py"
    if knowledge_catalog_py.is_file():
        try:
            k_cat = load_module_attr(knowledge_catalog_py, "_isai_knowledge_catalog", "KNOWLEDGE_CATALOG")
            if not isinstance(k_cat, KnowledgeCatalogSpec):
                raise TypeError("KNOWLEDGE_CATALOG must be KnowledgeCatalogSpec")
            _check_ref(k_cat.catalog_ref, "knowledge/.isai/catalog.py")
            for entry in k_cat.entries:
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
                if snap.master_vector_digest != MASTER_VECTOR.spec_digest():
                    issues.append(
                        AuditIssue(
                            code="SNAPSHOT_VECTOR_DRIFT",
                            location="tasks/.isai/state_snapshot.json",
                            message="Snapshot master_vector_digest is stale.",
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

    return AuditReport(
        valid=(len(issues) == 0),
        checked_nodes=tuple(sorted(nodes.keys())),
        resolved_refs_count=resolved_refs_count,
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
    nodes = discover_nodes(repo_root.resolve())
    return SystemStateSnapshot(
        revision=revision,
        timestamp_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        genesis_sha256=GENESIS_SHA256,
        master_vector_version=MASTER_VECTOR.version,
        master_vector_digest=MASTER_VECTOR.spec_digest(),
        active_tasks=active_tasks,
        open_handles=open_handles,
        node_spec_digests={nid: n.spec_digest() for nid, (_, n) in sorted(nodes.items())},
        node_interface_digests={nid: n.interface_digest() for nid, (_, n) in sorted(nodes.items())},
        audit_status=audit_status,  # type: ignore[arg-type]
    )


def compile_rsoc(
    repo_root: Path,
    target_uri: str,
    focus_tags: tuple[str, ...] = (),
) -> dict[str, Any]:
    """
    Windows GPO RSoP-inspired Resultant Set of Context (RSoC) Compiler.
    Produces a minimal, conflict-free Data Plane context packet for an LLM/agent
    while withholding internal Watchdog digests and irrelevant sibling branches.
    """
    repo_root = repo_root.resolve()
    scope, symbol = parse_entity_ref(target_uri)
    target_node_id = f"isai://{scope}"
    nodes = discover_nodes(repo_root)
    if target_node_id not in nodes:
        raise KeyError(f"Target node '{target_node_id}' not found in repository topology.")

    _, target_node = nodes[target_node_id]

    # Walk ancestor chain from root down to parent (LSDOU accumulation)
    ancestors: list[ISAINodeSpec] = []
    cursor = target_node.parent_ref
    while cursor is not None and cursor in nodes:
        _, parent_node = nodes[cursor]
        ancestors.append(parent_node)
        cursor = parent_node.parent_ref
    ancestors.reverse()

    # Select relevant operator profile directives & competencies
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

    # Select relevant empirical knowledge entries (matching node or tags)
    knowledge_slice: list[dict[str, Any]] = []
    knowledge_py = repo_root / "knowledge" / ".isai" / "catalog.py"
    if knowledge_py.is_file():
        k_cat: KnowledgeCatalogSpec = load_module_attr(
            knowledge_py, "_isai_knowledge_rsoc", "KNOWLEDGE_CATALOG"
        )
        tag_filter = set(focus_tags)
        for entry in k_cat.entries:
            node_match = entry.related_node_ref in (target_node_id, "isai://root")
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
        "rsoc_schema": "0.1.0",
        "requested_uri": target_uri,
        "focused_symbol": symbol,
        "enforced_genesis": {
            "priority": GENESIS_CONSTITUTION.meta_priority,
            "mandate": GENESIS_CONSTITUTION.core_mandate,
            "axioms": list(GENESIS_CONSTITUTION.axioms),
            "pipeline": " -> ".join(GENESIS_CONSTITUTION.operational_pipeline),
            "policy": " | ".join(GENESIS_CONSTITUTION.execution_policy),
        },
        "master_vector_anchor": {
            "version": MASTER_VECTOR.version,
            "north_star": MASTER_VECTOR.north_star_statement,
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
            "goal": target_node.goal,
            "success_criteria": list(target_node.success_criteria),
            "capabilities": list(target_node.capabilities),
            "invariants": list(target_node.invariants),
            "inputs": [p.model_dump(mode="json") for p in target_node.inputs],
            "outputs": [p.model_dump(mode="json") for p in target_node.outputs],
            "owned_files": list(target_node.owned_files),
            "transitions": [t.model_dump(mode="json") for t in target_node.transitions],
        },
        "operator_calibration": operator_slice,
        "distilled_knowledge": knowledge_slice,
    }
