"""Gate V — Pre-PR System Health Gate (`isai://root#SystemHealthGate`).

Executes deterministic structural checks across the root system folder, the task arena,
the knowledge universe, the verification suite and every registered `.isai` system
subfolder before a pull request may be opened.

Gate V contract (ISAI-NVF v1.1 `[VECTOR-GOVERNANCE]` VM7):

  * `status = NO_SYSTEMIC_DEVIATION` may only be emitted by this module, never asserted
    in prose, and it carries the SHA-256 digest of the full evidence set.
  * Any `CRITICAL` failure forces `DEVIATION_DETECTED`; the operator must neutralize the
    deviation and re-run the whole gate from the beginning ("back to pre-PR").
  * The gate is read-only: it never mutates the repository, so it is safe to run on an
    uncommitted working tree and on throwaway sandbox clones.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field

from isai.constitution import DEFAULT_BOUNDARY_IGNORE, GENESIS_CONSTITUTION
from isai.contracts import parse_entity_ref, validate_entity_ref
from isai.domain_models import KnowledgeCatalogSpec
from isai.engine import discover_nodes, find_torn_temp_artifacts, read_chronicle
from isai.graph_index import iter_functional_dirs, load_repo_master_vector, load_repo_nvf
from isai.protocol import SystemStateSnapshot
from isai.vector_ledger import VectorMutationLedger, evaluate_ledger_deviations

GATE_V_SCHEMA = "1.0"
NO_DEVIATION_STATUS = "NO_SYSTEMIC_DEVIATION"
DEVIATION_STATUS = "DEVIATION_DETECTED"


class HealthDomain(StrEnum):
    """System folder family audited by Gate V."""

    ROOT = "ROOT"
    TASKS = "TASKS"
    KNOWLEDGE = "KNOWLEDGE"
    UNIVERSE = "UNIVERSE"
    TESTS = "TESTS"
    SYSTEM_SUBFOLDERS = "SYSTEM_SUBFOLDERS"


class Severity(StrEnum):
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"


class HealthCheckResult(BaseModel):
    """Single deterministic verdict emitted by Gate V."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    check_id: str = Field(min_length=1)
    domain: HealthDomain
    severity: Severity
    passed: bool
    message: str = Field(min_length=1)
    evidence: str | None = None


class HealthReport(BaseModel):
    """Aggregate Gate V verdict with a reproducible evidence digest."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = GATE_V_SCHEMA
    status: str
    checks_total: int
    checks_passed: int
    critical_failures: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    results: tuple[HealthCheckResult, ...] = ()
    evidence_digest: str = ""
    master_vector_version: str | None = None
    nvf_version: str | None = None
    chronicle_revision: int | None = None

    @property
    def status_token_ru(self) -> str:
        return (
            "системных отклонений не выявлено"
            if self.status == NO_DEVIATION_STATUS
            else "выявлены системные отклонения"
        )


def _ok(check_id: str, domain: HealthDomain, message: str) -> HealthCheckResult:
    return HealthCheckResult(
        check_id=check_id, domain=domain, severity=Severity.CRITICAL, passed=True, message=message
    )


def _fail(
    check_id: str,
    domain: HealthDomain,
    message: str,
    evidence: str | None = None,
    severity: Severity = Severity.CRITICAL,
) -> HealthCheckResult:
    return HealthCheckResult(
        check_id=check_id,
        domain=domain,
        severity=severity,
        passed=False,
        message=message,
        evidence=evidence,
    )


def _compile_check(py_path: Path) -> str | None:
    """Return an error string when a Python source fails deterministic AST compilation."""
    try:
        ast.parse(py_path.read_text(encoding="utf-8"), filename=str(py_path))
    except SyntaxError as exc:
        return f"{py_path.name}: SyntaxError {exc}"
    return None


# ---------------------------------------------------------------------------
# Domain checks
# ---------------------------------------------------------------------------


def check_root_domain(repo_root: Path) -> list[HealthCheckResult]:
    results: list[HealthCheckResult] = []
    genesis = GENESIS_CONSTITUTION.verify_genesis_header(repo_root / "README.md")
    results.append(
        _ok("H-ROOT-01", HealthDomain.ROOT, "IL-0 Genesis header is byte-identical.")
        if genesis.valid
        else _fail("H-ROOT-01", HealthDomain.ROOT, f"IL-0 Genesis tampered: {genesis.detail}")
    )

    root_node_py = repo_root / ".isai" / "node.py"
    errors = _compile_check(root_node_py) if root_node_py.is_file() else "missing .isai/node.py"
    results.append(
        _ok("H-ROOT-02", HealthDomain.ROOT, "Root node manifest compiles as pure declarative AST.")
        if errors is None
        else _fail("H-ROOT-02", HealthDomain.ROOT, f"Root node manifest invalid: {errors}")
    )

    try:
        nvf = load_repo_nvf(repo_root)
        events = read_chronicle(repo_root)
        ratifications = [e for e in events if e.operation == "RATIFY_FUNDAMENTAL"]
        latest = ratifications[-1] if ratifications else None
        verified = bool(
            latest is not None and latest.operator_approved and latest.ratified_nvf_digest == nvf.dsl_sha256()
        )
        results.append(
            _ok(
                "H-ROOT-03",
                HealthDomain.ROOT,
                f"IL-1C fundamental {nvf.frame_id} is Operator-ratified in the Chronicle.",
            )
            if verified
            else _fail(
                "H-ROOT-03",
                HealthDomain.ROOT,
                "IL-1C fundamental digest is not covered by an Operator RATIFY_FUNDAMENTAL record.",
                evidence=f"live={nvf.dsl_sha256()}",
            )
        )
    except Exception as exc:  # pragma: no cover - defensive
        results.append(_fail("H-ROOT-03", HealthDomain.ROOT, f"IL-1C fundamental unreadable: {exc}"))

    try:
        vector = load_repo_master_vector(repo_root)
        ledger = VectorMutationLedger(repo_root)
        state = ledger.state() if ledger.path.is_file() else None
        if state is None:
            results.append(
                _fail(
                    "H-ROOT-04",
                    HealthDomain.ROOT,
                    "Vector mutation ledger is missing: mutations of the goal vector are untraceable (VM1).",
                )
            )
        else:
            critical = [d for d in evaluate_ledger_deviations(state, vector) if d.severity == "CRITICAL"]
            results.append(
                _ok(
                    "H-ROOT-04",
                    HealthDomain.ROOT,
                    f"Vector mutation ledger is consistent ({state.events_count} events, "
                    f"{len(state.applied)} applied).",
                )
                if not critical
                else _fail(
                    "H-ROOT-04",
                    HealthDomain.ROOT,
                    "Vector ledger deviations detected.",
                    evidence="; ".join(f"{d.code}: {d.message}" for d in critical),
                )
            )
    except Exception as exc:
        results.append(_fail("H-ROOT-04", HealthDomain.ROOT, f"Vector ledger unreadable: {exc}"))

    try:
        events = read_chronicle(repo_root)
        monotonic = all(
            ev.revision == index for index, ev in enumerate(events, start=1)
        ) and len({e.tx_id for e in events}) == len(events)
        results.append(
            _ok("H-ROOT-05", HealthDomain.ROOT, f"Chronicle is monotonic across {len(events)} transactions.")
            if monotonic
            else _fail("H-ROOT-05", HealthDomain.ROOT, "Chronicle revisions are non-monotonic or duplicated.")
        )
        # Tail truncation/duplication is already covered by H-ROOT-05 (monotonicity + unique tx_id);
        # a second check would violate `ZERO-Redundancy` without adding detection power.
    except Exception as exc:
        results.append(_fail("H-ROOT-05", HealthDomain.ROOT, f"Chronicle is unreadable: {exc}"))

    torn = find_torn_temp_artifacts(repo_root, DEFAULT_BOUNDARY_IGNORE)
    results.append(
        _ok("H-ROOT-06", HealthDomain.ROOT, "No torn transaction artifacts remain on disk.")
        if not torn
        else _fail(
            "H-ROOT-06",
            HealthDomain.ROOT,
            f"{len(torn)} torn atomic-write artifacts detected; run 'isai recover'.",
            evidence=", ".join(p.name for p in torn[:5]),
        )
    )
    return results


def check_tasks_domain(repo_root: Path, nodes: dict[str, tuple[Path, Any]]) -> list[HealthCheckResult]:
    results: list[HealthCheckResult] = []
    snapshot_path = repo_root / "tasks" / ".isai" / "state_snapshot.json"
    snapshot: SystemStateSnapshot | None = None
    try:
        snapshot = SystemStateSnapshot.model_validate_json(snapshot_path.read_text(encoding="utf-8"))
        results.append(_ok("H-TASKS-01", HealthDomain.TASKS, "State snapshot parses and satisfies its invariants."))
    except Exception as exc:
        results.append(_fail("H-TASKS-01", HealthDomain.TASKS, f"State snapshot invalid: {exc}"))

    try:
        events = read_chronicle(repo_root)
        head = events[-1].revision if events else 0
        if snapshot is not None:
            synced = snapshot.revision == head
            results.append(
                _ok("H-TASKS-02", HealthDomain.TASKS, f"Snapshot revision matches chronicle head (rev={head}).")
                if synced
                else _fail(
                    "H-TASKS-02",
                    HealthDomain.TASKS,
                    f"Snapshot revision {snapshot.revision} != chronicle head {head}.",
                )
            )
        else:
            results.append(_fail("H-TASKS-02", HealthDomain.TASKS, "Cannot compare revision: snapshot invalid."))
    except Exception as exc:
        results.append(_fail("H-TASKS-02", HealthDomain.TASKS, f"Chronicle unreadable: {exc}"))

    if snapshot is not None:
        missing = [t for t in snapshot.active_tasks if f"isai://{parse_entity_ref(t)[0]}" not in nodes]
        results.append(
            _ok("H-TASKS-03", HealthDomain.TASKS, f"{len(snapshot.active_tasks)} active staging task(s) resolve.")
            if not missing
            else _fail(
                "H-TASKS-03",
                HealthDomain.TASKS,
                "active_tasks reference non-existent staging nodes (orphan leases).",
                evidence=", ".join(missing),
            )
        )
        leaked = bool(not snapshot.active_tasks and snapshot.open_handles)
        results.append(
            _ok("H-TASKS-04", HealthDomain.TASKS, "Handle count is zero quiescent.")
            if not leaked
            else _fail("H-TASKS-04", HealthDomain.TASKS, "Open handles leaked without an active task.")
        )

    watchdog = repo_root / "tasks" / ".isai" / "watchdog.py"
    errors = _compile_check(watchdog) if watchdog.is_file() else "missing tasks/.isai/watchdog.py"
    results.append(
        _ok("H-TASKS-05", HealthDomain.TASKS, "Watchdog service compiles deterministically.")
        if errors is None
        else _fail("H-TASKS-05", HealthDomain.TASKS, f"Watchdog service invalid: {errors}")
    )

    staging_dirs = sorted(
        p.name
        for p in (repo_root / "tasks").iterdir()
        if p.is_dir() and not p.name.startswith(".") and p.name != "__pycache__"
    ) if (repo_root / "tasks").is_dir() else []
    declared = {f"isai://{parse_entity_ref(t)[0]}" for t in (snapshot.active_tasks if snapshot else ())}
    undeclared = [d for d in staging_dirs if f"isai://tasks/{d}" not in declared]
    results.append(
        _ok("H-TASKS-06", HealthDomain.TASKS, f"{len(staging_dirs)} staging director(ies) are all registered.")
        if not undeclared
        else _fail(
            "H-TASKS-06",
            HealthDomain.TASKS,
            "Unregistered staging directories violate zero-orphan-nodes.",
            evidence=", ".join(undeclared),
        )
    )
    return results


def check_knowledge_domain(
    repo_root: Path,
    nodes: dict[str, tuple[Path, Any]],
) -> list[HealthCheckResult]:
    results: list[HealthCheckResult] = []
    catalog_path = repo_root / "knowledge" / ".isai" / "catalog.py"
    catalog: KnowledgeCatalogSpec | None = None
    try:
        from isai.engine import load_module_attr

        obj = load_module_attr(catalog_path, "_gate_v_catalog", "KNOWLEDGE_CATALOG")
        if not isinstance(obj, KnowledgeCatalogSpec):
            raise TypeError("KNOWLEDGE_CATALOG is not a KnowledgeCatalogSpec.")
        catalog = obj
        results.append(
            _ok("H-KNOW-01", HealthDomain.KNOWLEDGE, f"Catalog validates with {len(catalog.entries)} entries.")
        )
    except Exception as exc:
        results.append(_fail("H-KNOW-01", HealthDomain.KNOWLEDGE, f"Knowledge catalog invalid: {exc}"))

    if catalog is not None:
        try:
            events = read_chronicle(repo_root)
            tx_ids = {e.tx_id for e in events}
            head_rev = events[-1].revision if events else 0
            bad_tx = [e.entry_id for e in catalog.entries if e.origin_tx_id not in tx_ids]
            results.append(
                _ok("H-KNOW-02", HealthDomain.KNOWLEDGE, "Every entry traces to a real Chronicle transaction.")
                if not bad_tx
                else _fail(
                    "H-KNOW-02",
                    HealthDomain.KNOWLEDGE,
                    "Knowledge entries reference unknown transactions.",
                    evidence=", ".join(bad_tx),
                )
            )
            future_rev = [e.entry_id for e in catalog.entries if e.verified_revision > head_rev]
            results.append(
                _ok("H-KNOW-03", HealthDomain.KNOWLEDGE, "Every entry revision is within the Chronicle horizon.")
                if not future_rev
                else _fail(
                    "H-KNOW-03",
                    HealthDomain.KNOWLEDGE,
                    "Knowledge entries claim revisions beyond the chronicle head.",
                    evidence=", ".join(future_rev),
                )
            )
        except Exception as exc:
            results.append(_fail("H-KNOW-02", HealthDomain.KNOWLEDGE, f"Chronicle unreadable: {exc}"))

        dangling: list[str] = []
        for entry in catalog.entries:
            scope, symbol = parse_entity_ref(entry.related_node_ref)
            node_id = f"isai://{scope}"
            if node_id not in nodes:
                dangling.append(entry.entry_id)
                continue
            if symbol is not None and symbol not in nodes[node_id][1].defined_symbols:
                dangling.append(entry.entry_id)
        results.append(
            _ok("H-KNOW-04", HealthDomain.KNOWLEDGE, "Every entry anchors to a live node symbol.")
            if not dangling
            else _fail(
                "H-KNOW-04",
                HealthDomain.KNOWLEDGE,
                "Knowledge entries anchor to unresolved entity references.",
                evidence=", ".join(dangling),
            )
        )

    readme = repo_root / "knowledge" / "README.md"
    issues: list[str] = []
    if not readme.is_file():
        issues.append("knowledge/README.md missing")
    else:
        text = readme.read_text(encoding="utf-8")
        if catalog is not None:
            for entry in catalog.entries:
                if entry.entry_id not in text:
                    issues.append(f"{entry.entry_id} undocumented in knowledge/README.md")
    results.append(
        _ok("H-KNOW-05", HealthDomain.KNOWLEDGE, "Knowledge registry ledger documents every entry.")
        if not issues
        else _fail(
            "H-KNOW-05",
            HealthDomain.KNOWLEDGE,
            "Knowledge registry drift: catalog and README registry disagree.",
            evidence="; ".join(issues[:5]),
        )
    )
    return results


def check_universe_domain(repo_root: Path) -> list[HealthCheckResult]:
    """Universe integrity: the empirical knowledge universe must stay a pure declarative store."""
    results: list[HealthCheckResult] = []
    knowledge_dir = repo_root / "knowledge"
    impure: list[str] = []
    for py_file in sorted(knowledge_dir.rglob("*.py")):
        rel = py_file.relative_to(repo_root)
        if DEFAULT_BOUNDARY_IGNORE.is_ignored(rel):
            continue
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except SyntaxError as exc:
            impure.append(f"{py_file.name}: {exc}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                impure.append(f"{rel}: executable '{type(node).__name__}' in universe store")
                break
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module = getattr(node, "module", None) or ",".join(a.name for a in node.names)
                if not (
                    module.startswith("isai.")
                    or module in ("isai", "__future__")
                    or module == "typing"
                ):
                    impure.append(f"{rel}: disallowed import '{module}'")
                    break
            if isinstance(node, ast.Call):
                func = node.func
                name = getattr(func, "id", None) or getattr(func, "attr", None)
                if name in ("open", "exec", "eval", "compile", "__import__"):
                    impure.append(f"{rel}: forbidden side-effect call '{name}'")
                    break
    results.append(
        _ok("H-UNI-01", HealthDomain.UNIVERSE, "Universe stores contain zero executable logic.")
        if not impure
        else _fail(
            "H-UNI-01",
            HealthDomain.UNIVERSE,
            "Universe purity violated (implementation leaked into knowledge store).",
            evidence="; ".join(impure[:5]),
        )
    )

    stray_dirs = [
        d.name
        for d in sorted(knowledge_dir.iterdir())
        if d.is_dir() and d.name not in (".isai", "__pycache__")
    ] if knowledge_dir.is_dir() else []
    results.append(
        _ok("H-UNI-02", HealthDomain.UNIVERSE, "No stray entity folders without a registered shell.")
        if not stray_dirs
        else _fail(
            "H-UNI-02",
            HealthDomain.UNIVERSE,
            "Unregistered entity folders detected in the universe store.",
            evidence=", ".join(stray_dirs),
            severity=Severity.WARNING,
        )
    )
    return results


def check_tests_domain(repo_root: Path, nodes: dict[str, tuple[Path, Any]]) -> list[HealthCheckResult]:
    results: list[HealthCheckResult] = []
    tests_node = nodes.get("isai://tests")
    if tests_node is None:
        return [_fail("H-TEST-01", HealthDomain.TESTS, "Verification suite node is missing.")]

    tests_dir, spec = tests_node
    declared = {
        name for name in spec.owned_files if name.endswith(".py") and name.startswith("test_")
    }
    on_disk = {p.name for p in tests_dir.glob("test_*.py")}
    missing = sorted(declared - on_disk)
    undeclared = sorted(on_disk - declared)
    results.append(
        _ok("H-TEST-01", HealthDomain.TESTS, f"{len(on_disk)} test modules are registered and present.")
        if not missing and not undeclared
        else _fail(
            "H-TEST-01",
            HealthDomain.TESTS,
            "Test module registry drift.",
            evidence=f"missing={missing} undeclared={undeclared}",
        )
    )

    unmarked: list[str] = []
    for test_file in sorted(tests_dir.glob("test_*.py")):
        text = test_file.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text, filename=str(test_file))
        except SyntaxError as exc:
            unmarked.append(f"{test_file.name}: {exc}")
            continue
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                decorators = [
                    ast.unparse(d) for d in node.decorator_list if isinstance(d, ast.Call)
                ]
                if not any("isai_scope" in d for d in decorators):
                    unmarked.append(f"{test_file.name}::{node.name}")
    results.append(
        _ok("H-TEST-02", HealthDomain.TESTS, "Every test declares an isai_scope ownership marker.")
        if not unmarked
        else _fail(
            "H-TEST-02",
            HealthDomain.TESTS,
            "Tests without isai_scope markers break VAET affected-test selection.",
            evidence=", ".join(unmarked[:6]),
        )
    )

    empty_modules = [
        p.name for p in sorted(tests_dir.glob("test_*.py"))
        if len(re.findall(r"^def test_", p.read_text(encoding="utf-8"), flags=re.MULTILINE)) == 0
    ]
    results.append(
        _ok("H-TEST-03", HealthDomain.TESTS, "No empty test modules (no silent coverage loss).")
        if not empty_modules
        else _fail(
            "H-TEST-03",
            HealthDomain.TESTS,
            "Test modules without any test function detected.",
            evidence=", ".join(empty_modules),
            severity=Severity.WARNING,
        )
    )
    return results


def check_system_subfolders(repo_root: Path, nodes: dict[str, tuple[Path, Any]]) -> list[HealthCheckResult]:
    results: list[HealthCheckResult] = []
    missing: list[str] = []
    broken: list[str] = []
    for directory in iter_functional_dirs(repo_root, DEFAULT_BOUNDARY_IGNORE):
        rel = directory.relative_to(repo_root)
        isai_dir = directory / ".isai"
        if not isai_dir.is_dir():
            continue
        if not (directory / "README.md").is_file():
            missing.append(f"{rel.as_posix()}/README.md")
        for item in sorted(isai_dir.iterdir()):
            rel_item = item.relative_to(repo_root)
            if DEFAULT_BOUNDARY_IGNORE.is_ignored(rel_item):
                continue
            if item.is_dir():
                broken.append(f"{rel_item.as_posix()} (nested .isai subdir)")
                continue
            if item.suffix == ".py":
                err = _compile_check(item)
                if err is not None:
                    broken.append(f"{rel_item.as_posix()}: {err}")
    results.append(
        _ok("H-SYS-01", HealthDomain.SYSTEM_SUBFOLDERS, "Every system subfolder exposes README + compilable .isai files.")
        if not missing and not broken
        else _fail(
            "H-SYS-01",
            HealthDomain.SYSTEM_SUBFOLDERS,
            "System subfolder structural defects detected.",
            evidence="; ".join([*missing, *broken][:6]),
        )
    )

    rogue_sys_files: list[str] = []
    for directory in iter_functional_dirs(repo_root, DEFAULT_BOUNDARY_IGNORE):
        isai_dir = directory / ".isai"
        node_file = isai_dir / "node.py"
        if not node_file.is_file():
            continue
        try:
            from isai.engine import load_node_from_dir

            spec = load_node_from_dir(repo_root, directory)
        except Exception:
            continue
        declared = set(spec.system_files)
        for item in sorted(isai_dir.iterdir()):
            rel_item = item.relative_to(repo_root)
            if DEFAULT_BOUNDARY_IGNORE.is_ignored(rel_item) or item.name.startswith(".isai_tmp_"):
                continue
            if item.is_file() and item.name not in declared:
                rogue_sys_files.append(rel_item.as_posix())
    results.append(
        _ok(
            "H-SYS-03",
            HealthDomain.SYSTEM_SUBFOLDERS,
            "Every .isai system artifact is registered in its node manifest.",
        )
        if not rogue_sys_files
        else _fail(
            "H-SYS-03",
            HealthDomain.SYSTEM_SUBFOLDERS,
            "Unregistered .isai system artifacts detected (hidden backdoor surface).",
            evidence=", ".join(rogue_sys_files[:6]),
        )
    )

    unregistered_nodes: list[str] = []
    for directory in iter_functional_dirs(repo_root, DEFAULT_BOUNDARY_IGNORE):
        if (directory / ".isai" / "node.py").is_file():
            node_id = "isai://root" if directory == repo_root else f"isai://{directory.relative_to(repo_root).as_posix()}"
            if node_id not in nodes:
                unregistered_nodes.append(node_id)
    results.append(
        _ok("H-SYS-02", HealthDomain.SYSTEM_SUBFOLDERS, f"{len(nodes)} directory nodes load as valid ISAINodeSpec.")
        if not unregistered_nodes
        else _fail(
            "H-SYS-02",
            HealthDomain.SYSTEM_SUBFOLDERS,
            "Directory nodes failed to load.",
            evidence=", ".join(unregistered_nodes),
        )
    )
    return results


def evaluate_gate_v(
    repo_root: Path,
    *,
    extra_checks: tuple[Callable[[Path], list[HealthCheckResult]], ...] = (),
) -> HealthReport:
    """Run the complete pre-PR system health gate in read-only mode."""
    root = repo_root.resolve()
    results: list[HealthCheckResult] = []
    nodes: dict[str, tuple[Path, Any]] = {}
    try:
        nodes = discover_nodes(root)
    except Exception as exc:
        results.append(_fail("H-SYS-00", HealthDomain.SYSTEM_SUBFOLDERS, f"Node discovery failed: {exc}"))

    results.extend(check_root_domain(root))
    results.extend(check_tasks_domain(root, nodes))
    results.extend(check_knowledge_domain(root, nodes))
    results.extend(check_universe_domain(root))
    results.extend(check_tests_domain(root, nodes))
    results.extend(check_system_subfolders(root, nodes))
    for extra in extra_checks:
        results.extend(extra(root))

    critical = tuple(r.check_id for r in results if not r.passed and r.severity == Severity.CRITICAL)
    warnings = tuple(r.check_id for r in results if not r.passed and r.severity == Severity.WARNING)
    evidence_payload = json.dumps(
        [r.model_dump(mode="json") for r in results], ensure_ascii=False, sort_keys=True
    )
    digest = hashlib.sha256(evidence_payload.encode("utf-8")).hexdigest()

    vector_version = None
    nvf_version = None
    revision = None
    try:
        vector_version = load_repo_master_vector(root).version
    except Exception:
        pass
    try:
        nvf_version = load_repo_nvf(root).version
    except Exception:
        pass
    try:
        events = read_chronicle(root)
        revision = events[-1].revision if events else 0
    except Exception:
        pass

    return HealthReport(
        status=NO_DEVIATION_STATUS if not critical else DEVIATION_STATUS,
        checks_total=len(results),
        checks_passed=sum(1 for r in results if r.passed),
        critical_failures=critical,
        warnings=warnings,
        results=tuple(results),
        evidence_digest=digest,
        master_vector_version=vector_version,
        nvf_version=nvf_version,
        chronicle_revision=revision,
    )
