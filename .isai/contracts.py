"""Core Pydantic v2 Contracts (v0.2.0): Typed Edges, Port Schemas, Visibility & 4-in-1 ISAINodeSpec."""

from __future__ import annotations

import hashlib
import importlib
import json
import re
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from isai.constitution import IntegrityLevel

SYNC_BEGIN_MARKER = "<!-- ISAI:SYNC:BEGIN -->"
SYNC_END_MARKER = "<!-- ISAI:SYNC:END -->"

_ENTITY_REF_RE = re.compile(
    r"^isai://(?P<scope>[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*)(?:#(?P<symbol>[A-Za-z0-9_.-]+))?$"
)
_PY_ATTR_TARGET_RE = re.compile(r"^(?P<file>[A-Za-z0-9_.-]+\.py):(?P<attr>[A-Za-z_][A-Za-z0-9_]*)$")
_SCHEMA_REF_RE = re.compile(
    r"^(?P<module>[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*):(?P<attr>[A-Za-z_][A-Za-z0-9_]*)$"
)


def validate_entity_ref(value: str) -> str:
    """Validate an ISAI URI of the form isai://<scope_path>[#<symbol>]."""
    match = _ENTITY_REF_RE.match(value)
    if not match:
        raise ValueError(
            f"Invalid EntityRef '{value}'. Expected 'isai://<scope>[#<symbol>]'."
        )
    scope = match.group("scope")
    if ".." in scope.split("/"):
        raise ValueError(f"Parent traversal '..' is forbidden in EntityRef '{value}'.")
    return value


EntityRef = Annotated[str, AfterValidator(validate_entity_ref)]


def parse_entity_ref(ref: str) -> tuple[str, str | None]:
    """Split validated EntityRef into (scope_path, optional_symbol)."""
    validate_entity_ref(ref)
    body = ref[len("isai://") :]
    if "#" in body:
        scope, symbol = body.split("#", 1)
        return scope, symbol
    return body, None


def scope_to_rel_path(scope: str) -> Path:
    """Map an ISAI scope ('root' or 'user/competencies') to a repository-relative Path."""
    if scope == "root":
        return Path(".")
    if scope.startswith("root/"):
        raise ValueError(
            f"Child nodes must use 'isai://<rel_path>', not 'isai://root/...' (got '{scope}')."
        )
    return Path(scope)


def rel_path_to_node_id(rel_path: Path) -> str:
    """Map a repository-relative directory Path to its canonical node_id URI."""
    if rel_path == Path(".") or str(rel_path) == "":
        return "isai://root"
    return f"isai://{rel_path.as_posix()}"


def resolve_schema_ref_type(schema_ref: str) -> Any:
    """Resolve '<module>:<TypeName>' into its live Python type or Pydantic model class."""
    m = _SCHEMA_REF_RE.match(schema_ref)
    if not m:
        raise ValueError(
            f"Invalid schema_ref '{schema_ref}'. Expected '<module.path>:<TypeName>'."
        )
    mod_name = m.group("module")
    attr_name = m.group("attr")
    mod = importlib.import_module(mod_name)
    if not hasattr(mod, attr_name):
        raise AttributeError(f"Module '{mod_name}' has no attribute '{attr_name}'.")
    return getattr(mod, attr_name)


def compute_type_structural_digest(schema_ref_or_type: str | type) -> str:
    """
    Compute a deterministic, process-invariant structural fingerprint of a bound Python/Pydantic schema.
    If a Pydantic BaseModel changes fields, field types, or required flags, this digest
    mutates immediately — preventing false Salsa Early-Cutoff in Watchdog cascades.
    """
    if isinstance(schema_ref_or_type, str):
        schema_ref = schema_ref_or_type
        try:
            target = resolve_schema_ref_type(schema_ref)
        except Exception:
            return f"UNRESOLVED:{schema_ref}"
    else:
        target = schema_ref_or_type
        schema_ref = f"{getattr(target, '__module__', 'builtins')}:{getattr(target, '__qualname__', repr(target))}"

    if isinstance(target, type) and issubclass(target, BaseModel):
        schema_dict = dict(target.model_json_schema())
        schema_dict.pop("title", None)
        schema_dict.pop("description", None)
        payload: dict[str, Any] = {
            "kind": "pydantic_model",
            "ref": schema_ref,
            "json_schema": schema_dict,
        }
    elif isinstance(target, type) and issubclass(target, StrEnum):
        payload = {
            "kind": "str_enum",
            "ref": schema_ref,
            "members": sorted(member.value for member in target),
        }
    else:
        qual = getattr(target, "__qualname__", repr(target))
        payload = {"kind": "python_type", "ref": schema_ref, "qualname": str(qual)}

    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class PhaseMode(StrEnum):
    """Graduated phase execution path (Fast-Read vs CBS Staged Transaction)."""

    FAST_READ = "FAST_READ"
    STAGED_TRANSACTION = "STAGED_TRANSACTION"


class VisibilityScope(StrEnum):
    """Bazel-inspired node visibility boundary governing which scopes may link to this node."""

    PUBLIC = "PUBLIC"                        # Reachable from any node in the repository
    SUBTREE = "SUBTREE"                      # Reachable only from parent, self, or descendants
    EPHEMERAL_STAGING = "EPHEMERAL_STAGING"  # Volatile staging scope; forbidden from IL-1/IL-2 static edges


class SymbolVisibility(StrEnum):
    """Export boundary for an individual symbol bound inside a node."""

    PUBLIC = "PUBLIC"      # Consumable across hives
    INTERNAL = "INTERNAL"  # Consumable only within the declaring node and its subtree


class EdgeKind(StrEnum):
    """Explicit semantic role of a directed hypergraph link."""

    GOVERNED_BY = "GOVERNED_BY"              # Enforces upstream constitutional or invariant authority
    CONSUMES_CONTRACT = "CONSUMES_CONTRACT"  # Uses exported schema, service, or artifact contract
    DELEGATES_TO = "DELEGATES_TO"            # Delegates operational execution to target service
    VERIFIES = "VERIFIES"                    # Exercises and cross-tests target entity invariants
    CALIBRATES = "CALIBRATES"                # Supplies operator or empirical context slice
    MUTATES_TARGET = "MUTATES_TARGET"        # Declares controlled transactional mutation of target


class RSoCDeliveryPolicy(StrEnum):
    """Controls how a linked neighbor's contract is projected into the RSoC context window."""

    NONE = "NONE"                    # Control-plane edge only; omit neighbor stub from RSoC
    INTERFACE_STUB = "INTERFACE_STUB"  # Deliver compact 1-hop signature, ports & invariants
    FULL_CONTRACT = "FULL_CONTRACT"  # Deliver complete neighbor public contract


class SymbolBindingKind(StrEnum):
    """Physical carrier category for an exported node symbol."""

    PYTHON_ATTR = "python_attr"          # "<file.py>:<attr_name>" in system_files or owned_files
    SYSTEM_ARTIFACT = "system_artifact"  # "<filename>" registered in system_files (.isai/)
    OWNED_ARTIFACT = "owned_artifact"    # "<filename>" registered in owned_files (<dir>/)


class SymbolBindingSpec(BaseModel):
    """Verifiable binding mapping a logical symbol (#Symbol) to a physical code object or file."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_.-]+$")
    kind: SymbolBindingKind
    target: str = Field(min_length=1)
    visibility: SymbolVisibility = SymbolVisibility.PUBLIC

    @model_validator(mode="after")
    def _validate_target_syntax(self) -> SymbolBindingSpec:
        if self.kind == SymbolBindingKind.PYTHON_ATTR:
            if not _PY_ATTR_TARGET_RE.match(self.target):
                raise ValueError(
                    f"SymbolBindingSpec '{self.symbol}' with kind='python_attr' requires "
                    f"target='<file.py>:<attr_name>', got '{self.target}'."
                )
        else:
            if "/" in self.target or ":" in self.target or ".." in self.target:
                raise ValueError(
                    f"SymbolBindingSpec '{self.symbol}' artifact target must be a direct filename, "
                    f"got '{self.target}'."
                )
        return self


class EdgeLinkSpec(BaseModel):
    """Typed, RSoC-aware directed link from the declaring node to another EntityRef."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    target_ref: EntityRef
    kind: EdgeKind = EdgeKind.CONSUMES_CONTRACT
    rsoc_delivery: RSoCDeliveryPolicy = RSoCDeliveryPolicy.INTERFACE_STUB
    rationale: str | None = None


class IOPortSpec(BaseModel):
    """Typed OOP Adapter contract port (Input or Output) with physical schema references."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    contract_type: str = Field(min_length=1)
    schema_refs: tuple[str, ...] = ()
    description: str = Field(min_length=1)
    required: bool = True

    @model_validator(mode="after")
    def _validate_schema_refs(self) -> IOPortSpec:
        if len(set(self.schema_refs)) != len(self.schema_refs):
            raise ValueError(
                f"Duplicate schema_refs in IOPortSpec '{self.name}' (Redundancy=FATAL)."
            )
        for sref in self.schema_refs:
            if not _SCHEMA_REF_RE.match(sref):
                raise ValueError(
                    f"Invalid schema_ref '{sref}' in IOPortSpec '{self.name}'. "
                    "Expected '<module.path>:<TypeName>'."
                )
        return self


class PortWiringSpec(BaseModel):
    """Explicit Bi-Directional Contract wiring binding a local input port to a producer output port."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    consumer_input_port: str = Field(min_length=1)
    producer_ref: EntityRef
    producer_output_port: str = Field(min_length=1)
    rationale: str | None = None


class TransitionRule(BaseModel):
    """Explicit state/focus router edge from the current node to a target EntityRef."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    trigger: str = Field(min_length=1)
    target_ref: EntityRef
    phase_mode: PhaseMode = PhaseMode.STAGED_TRANSACTION
    description: str = Field(min_length=1)


class ISAINodeSpec(BaseModel):
    """
    Canonical 4-in-1 System Folder Object (.isai/node.py, Schema v0.2.0):
      1. Logic:   goal, success_criteria, capabilities, invariants, visibility
      2. Adapter: inputs, outputs, port_wirings
      3. Sync:    owned_files, system_files, symbol_bindings, spec_digest(), render_sync_block()
      4. Router:  parent_ref, links (derived related_refs), transitions
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "0.2.0"
    node_id: EntityRef
    title: str = Field(min_length=1)
    integrity_level: IntegrityLevel
    visibility: VisibilityScope = VisibilityScope.PUBLIC
    parent_ref: EntityRef | None = None

    # 1. Logic
    goal: str = Field(min_length=1)
    success_criteria: tuple[str, ...] = Field(min_length=1)
    capabilities: tuple[str, ...] = Field(min_length=1)
    invariants: tuple[str, ...] = ()

    # 2. Adapter
    inputs: tuple[IOPortSpec, ...] = ()
    outputs: tuple[IOPortSpec, ...] = ()
    port_wirings: tuple[PortWiringSpec, ...] = ()

    # 3. Sync & Ownership
    owned_files: tuple[str, ...] = ("README.md",)
    system_files: tuple[str, ...] = ("node.py",)
    symbol_bindings: tuple[SymbolBindingSpec, ...] = ()

    # 4. Router & Typed Hypergraph Links
    links: tuple[EdgeLinkSpec, ...] = ()
    transitions: tuple[TransitionRule, ...] = ()

    @property
    def defined_symbols(self) -> tuple[str, ...]:
        """Derived tuple of symbol names (single source of truth is symbol_bindings)."""
        return tuple(b.symbol for b in self.symbol_bindings)

    @property
    def related_refs(self) -> tuple[str, ...]:
        """Derived deduplicated tuple of linked EntityRefs (single source of truth is links)."""
        return tuple(dict.fromkeys(l.target_ref for l in self.links))

    @model_validator(mode="after")
    def _validate_node_invariants(self) -> ISAINodeSpec:
        scope, symbol = parse_entity_ref(self.node_id)
        if symbol is not None:
            raise ValueError(f"node_id cannot contain '#symbol': {self.node_id}")
        scope_to_rel_path(scope)

        if self.node_id == "isai://root":
            if self.parent_ref is not None:
                raise ValueError("Root node 'isai://root' must have parent_ref=None.")
        else:
            if self.parent_ref is None:
                raise ValueError(f"Non-root node '{self.node_id}' must declare parent_ref.")
            if self.parent_ref == self.node_id:
                raise ValueError(f"Node '{self.node_id}' cannot be its own parent.")

        # Child staging directories under tasks/ must be IL_3_STAGING & EPHEMERAL_STAGING
        if scope.startswith("tasks/"):
            if self.integrity_level != IntegrityLevel.IL_3_STAGING:
                raise ValueError(
                    f"Child task node '{self.node_id}' must have integrity_level=IL_3_STAGING."
                )
            if self.visibility != VisibilityScope.EPHEMERAL_STAGING:
                raise ValueError(
                    f"Child task node '{self.node_id}' must have visibility=EPHEMERAL_STAGING."
                )

        if "README.md" not in self.owned_files:
            raise ValueError(f"Node '{self.node_id}' must include 'README.md' in owned_files.")
        if "node.py" not in self.system_files:
            raise ValueError(f"Node '{self.node_id}' must include 'node.py' in system_files.")
        if len(set(self.owned_files)) != len(self.owned_files):
            raise ValueError(f"Duplicate entries in owned_files of '{self.node_id}' (Redundancy=FATAL).")
        if len(set(self.system_files)) != len(self.system_files):
            raise ValueError(f"Duplicate entries in system_files of '{self.node_id}' (Redundancy=FATAL).")

        in_names = [p.name for p in self.inputs]
        if len(set(in_names)) != len(in_names):
            raise ValueError(f"Duplicate input port name in '{self.node_id}' (Redundancy=FATAL).")
        out_names = [p.name for p in self.outputs]
        if len(set(out_names)) != len(out_names):
            raise ValueError(f"Duplicate output port name in '{self.node_id}' (Redundancy=FATAL).")

        in_set = set(in_names)
        pw_keys = [
            (pw.consumer_input_port, pw.producer_ref, pw.producer_output_port)
            for pw in self.port_wirings
        ]
        if len(set(pw_keys)) != len(pw_keys):
            raise ValueError(f"Duplicate port_wiring in '{self.node_id}' (Redundancy=FATAL).")
        for pw in self.port_wirings:
            if pw.consumer_input_port not in in_set:
                raise ValueError(
                    f"PortWiring in '{self.node_id}' references unknown local input port "
                    f"'{pw.consumer_input_port}'."
                )

        link_keys = [(l.target_ref, l.kind) for l in self.links]
        if len(set(link_keys)) != len(link_keys):
            raise ValueError(
                f"Duplicate (target_ref, kind) link in '{self.node_id}' (Redundancy=FATAL)."
            )

        sym_names = [b.symbol for b in self.symbol_bindings]
        if len(set(sym_names)) != len(sym_names):
            raise ValueError(f"Duplicate symbol in symbol_bindings of '{self.node_id}' (Redundancy=FATAL).")

        owned_set = set(self.owned_files)
        sys_set = set(self.system_files)
        for b in self.symbol_bindings:
            if b.kind == SymbolBindingKind.PYTHON_ATTR:
                py_file, _ = b.target.split(":", 1)
                if py_file not in sys_set and py_file not in owned_set:
                    raise ValueError(
                        f"Symbol '{b.symbol}' in '{self.node_id}' targets '{py_file}', "
                        "which is registered in neither system_files nor owned_files."
                    )
            elif b.kind == SymbolBindingKind.SYSTEM_ARTIFACT:
                if b.target not in sys_set:
                    raise ValueError(
                        f"Symbol '{b.symbol}' in '{self.node_id}' targets '{b.target}', "
                        "which is not listed in system_files."
                    )
            elif b.kind == SymbolBindingKind.OWNED_ARTIFACT:
                if b.target not in owned_set:
                    raise ValueError(
                        f"Symbol '{b.symbol}' in '{self.node_id}' targets '{b.target}', "
                        "which is not listed in owned_files."
                    )
        return self

    def canonical_dict(self) -> dict[str, Any]:
        """Return deterministic dictionary representation of the full node specification."""
        return self.model_dump(mode="json")

    def spec_digest(self) -> str:
        """Compute canonical SHA-256 digest of the complete node specification (Sync checksum)."""
        raw = json.dumps(self.canonical_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def interface_digest(self) -> str:
        """
        Compute Salsa Early-Cutoff public contract digest (v0.2.0).
        Includes structural fingerprints of bound Pydantic/Python port schemas so breaking
        field edits in underlying models immediately trigger downstream cascade checks.
        """
        def _port_sig(p: IOPortSpec) -> dict[str, Any]:
            return {
                **p.model_dump(mode="json"),
                "schema_fingerprints": {
                    sref: compute_type_structural_digest(sref) for sref in p.schema_refs
                },
            }

        public_contract = {
            "node_id": self.node_id,
            "integrity_level": self.integrity_level.value,
            "visibility": self.visibility.value,
            "parent_ref": self.parent_ref,
            "invariants": list(self.invariants),
            "inputs": [_port_sig(p) for p in self.inputs],
            "outputs": [_port_sig(p) for p in self.outputs],
            "port_wirings": [pw.model_dump(mode="json") for pw in self.port_wirings],
            "exported_symbols": [
                {"symbol": b.symbol, "visibility": b.visibility.value}
                for b in self.symbol_bindings
            ],
            "transitions": [t.model_dump(mode="json") for t in self.transitions],
        }
        raw = json.dumps(public_contract, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def all_outbound_refs(self) -> tuple[str, ...]:
        """Collect deduplicated ordered outbound EntityRefs across parent, links, wirings, and transitions."""
        refs: list[str] = []
        if self.parent_ref is not None:
            refs.append(self.parent_ref)
        refs.extend(l.target_ref for l in self.links)
        refs.extend(pw.producer_ref for pw in self.port_wirings)
        refs.extend(t.target_ref for t in self.transitions)
        return tuple(dict.fromkeys(refs))

    def render_sync_block(self) -> str:
        """Deterministically project the node contract into a human-readable Markdown section."""
        s_digest = self.spec_digest()
        i_digest = self.interface_digest()
        parent_display = f"`{self.parent_ref}`" if self.parent_ref else "`None (Root Node)`"

        lines: list[str] = [
            SYNC_BEGIN_MARKER,
            f"<!-- isai:node_id={self.node_id} -->",
            f"<!-- isai:spec_digest={s_digest} -->",
            f"<!-- isai:interface_digest={i_digest} -->",
            "",
            f"## Паспорт узла `{self.node_id}` — {self.title}",
            "",
            f"- **Уровень целостности:** `{self.integrity_level.value}` | **Видимость:** `{self.visibility.value}`",
            f"- **Родительский узел:** {parent_display}",
            f"- **Цель (`Goal`):** {self.goal}",
            "",
            "### Критерии успеха (`Success Criteria`)",
        ]
        for item in self.success_criteria:
            lines.append(f"- {item}")

        lines.extend(["", "### Функционал (`Capabilities`)"])
        for cap in self.capabilities:
            lines.append(f"- {cap}")

        if self.invariants:
            lines.extend(["", "### Локальные инварианты (`Invariants`)"])
            for inv in self.invariants:
                lines.append(f"- {inv}")

        lines.extend(["", "### Адаптер и Связывание Портов (`Adapter & Port Wirings`)"])
        if self.inputs:
            lines.append("- **Входы (`Inputs`):**")
            for port in self.inputs:
                req = "обязательный" if port.required else "опциональный"
                s_info = f" [схемы: {', '.join(f'`{s}`' for s in port.schema_refs)}]" if port.schema_refs else ""
                lines.append(f"  - `{port.name}` (`{port.contract_type}`, {req}){s_info} — {port.description}")
        else:
            lines.append("- **Входы (`Inputs`):** `нет внешних входов`")

        if self.outputs:
            lines.append("- **Выходы (`Outputs`):**")
            for port in self.outputs:
                req = "гарантированный" if port.required else "опциональный"
                s_info = f" [схемы: {', '.join(f'`{s}`' for s in port.schema_refs)}]" if port.schema_refs else ""
                lines.append(f"  - `{port.name}` (`{port.contract_type}`, {req}){s_info} — {port.description}")
        else:
            lines.append("- **Выходы (`Outputs`):** `нет внешних выходов`")

        if self.port_wirings:
            lines.append("- **Контрактная коммутация портов (`port_wirings`):**")
            for pw in self.port_wirings:
                rat = f" — {pw.rationale}" if pw.rationale else ""
                lines.append(
                    f"  - вход `{pw.consumer_input_port}` ← `{pw.producer_ref}` (выход `{pw.producer_output_port}`){rat}"
                )

        lines.extend(["", "### Реестр владения и верифицируемых символов (`Ownership & Symbol Bindings`)"])
        owned_str = ", ".join(f"`{f}`" for f in self.owned_files)
        sys_str = ", ".join(f"`.isai/{f}`" for f in self.system_files)
        lines.append(f"- **Файлы узла (`owned_files`):** {owned_str}")
        lines.append(f"- **Служебные файлы (`system_files`):** {sys_str}")
        if self.symbol_bindings:
            lines.append("- **Экспортируемые сущности (`symbol_bindings`):**")
            for b in self.symbol_bindings:
                lines.append(
                    f"  - `{self.node_id}#{b.symbol}` (`{b.kind.value}` → `{b.target}`, видимость: `{b.visibility.value}`)"
                )

        lines.extend(["", "### Типизированные связи и Маршрутизация (`Typed Links & Router`)"])
        if self.links:
            lines.append("- **Типизированные связи (`links`):**")
            for l in self.links:
                rat = f" — {l.rationale}" if l.rationale else ""
                lines.append(
                    f"  - `{l.target_ref}` [`{l.kind.value}` | RSoC: `{l.rsoc_delivery.value}`]{rat}"
                )
        else:
            lines.append("- **Типизированные связи (`links`):** `нет дополнительных ссылок`")

        if self.transitions:
            lines.append("- **Допустимые переходы (`transitions`):**")
            for tr in self.transitions:
                lines.append(
                    f"  - При `{tr.trigger}` → `{tr.target_ref}` "
                    f"[режим: `{tr.phase_mode.value}`] — {tr.description}"
                )
        else:
            lines.append("- **Допустимые переходы (`transitions`):** `терминальный узел`")

        lines.extend(["", SYNC_END_MARKER])
        return "\n".join(lines)
