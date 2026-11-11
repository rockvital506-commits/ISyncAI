"""Core Pydantic v2 Contracts: EntityRef URI, Transition Rules, and 4-in-1 ISAINodeSpec."""

from __future__ import annotations

import hashlib
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


class PhaseMode(StrEnum):
    """Graduated phase execution path (Fast-Read vs CBS Staged Transaction)."""

    FAST_READ = "FAST_READ"
    STAGED_TRANSACTION = "STAGED_TRANSACTION"


class IOPortSpec(BaseModel):
    """Typed OOP Adapter contract port (Input or Output) for a directory-object node."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    contract_type: str = Field(min_length=1)
    description: str = Field(min_length=1)
    required: bool = True


class TransitionRule(BaseModel):
    """Explicit state/focus router edge from the current node to a target EntityRef."""

    model_config = ConfigDict(frozen=True)

    trigger: str = Field(min_length=1)
    target_ref: EntityRef
    phase_mode: PhaseMode = PhaseMode.STAGED_TRANSACTION
    description: str = Field(min_length=1)


class ISAINodeSpec(BaseModel):
    """
    Canonical 4-in-1 System Folder Object (.isai/node.py):
      1. Logic:   goal, success_criteria, capabilities, invariants
      2. Adapter: inputs, outputs
      3. Sync:    owned_files, system_files, defined_symbols, spec_digest(), render_sync_block()
      4. Router:  parent_ref, related_refs, transitions
    """

    model_config = ConfigDict(frozen=True)

    schema_version: str = "0.1.0"
    node_id: EntityRef
    title: str = Field(min_length=1)
    integrity_level: IntegrityLevel
    parent_ref: EntityRef | None = None

    # 1. Logic
    goal: str = Field(min_length=1)
    success_criteria: tuple[str, ...] = Field(min_length=1)
    capabilities: tuple[str, ...] = Field(min_length=1)
    invariants: tuple[str, ...] = ()

    # 2. Adapter
    inputs: tuple[IOPortSpec, ...] = ()
    outputs: tuple[IOPortSpec, ...] = ()

    # 3. Sync & Ownership
    owned_files: tuple[str, ...] = ("README.md",)
    system_files: tuple[str, ...] = ("node.py",)
    defined_symbols: tuple[str, ...] = ()

    # 4. Router & Hypergraph Links
    related_refs: tuple[EntityRef, ...] = ()
    transitions: tuple[TransitionRule, ...] = ()

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

        if "README.md" not in self.owned_files:
            raise ValueError(f"Node '{self.node_id}' must include 'README.md' in owned_files.")
        if "node.py" not in self.system_files:
            raise ValueError(f"Node '{self.node_id}' must include 'node.py' in system_files.")
        if len(set(self.owned_files)) != len(self.owned_files):
            raise ValueError(f"Duplicate entries in owned_files of '{self.node_id}' (Redundancy=FATAL).")
        if len(set(self.system_files)) != len(self.system_files):
            raise ValueError(f"Duplicate entries in system_files of '{self.node_id}' (Redundancy=FATAL).")
        if len(set(self.defined_symbols)) != len(self.defined_symbols):
            raise ValueError(f"Duplicate entries in defined_symbols of '{self.node_id}' (Redundancy=FATAL).")
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
        Compute Salsa Early-Cutoff public contract digest.
        Changes ONLY when the external contract (identity, level, invariants, I/O, symbols, transitions) mutates.
        """
        public_contract = {
            "node_id": self.node_id,
            "integrity_level": self.integrity_level.value,
            "parent_ref": self.parent_ref,
            "invariants": list(self.invariants),
            "inputs": [p.model_dump(mode="json") for p in self.inputs],
            "outputs": [p.model_dump(mode="json") for p in self.outputs],
            "defined_symbols": list(self.defined_symbols),
            "transitions": [t.model_dump(mode="json") for t in self.transitions],
        }
        raw = json.dumps(public_contract, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def all_outbound_refs(self) -> tuple[str, ...]:
        """Collect all outbound EntityRefs declared by this node for graph validation."""
        refs: list[str] = []
        if self.parent_ref is not None:
            refs.append(self.parent_ref)
        refs.extend(self.related_refs)
        refs.extend(t.target_ref for t in self.transitions)
        return tuple(refs)

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
            f"- **Уровень целостности:** `{self.integrity_level.value}`",
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

        lines.extend(["", "### Адаптер (`Inputs / Outputs`)"])
        if self.inputs:
            lines.append("- **Входы (`Inputs`):**")
            for port in self.inputs:
                req = "обязательный" if port.required else "опциональный"
                lines.append(f"  - `{port.name}` (`{port.contract_type}`, {req}) — {port.description}")
        else:
            lines.append("- **Входы (`Inputs`):** `нет внешних входов`")

        if self.outputs:
            lines.append("- **Выходы (`Outputs`):**")
            for port in self.outputs:
                req = "гарантированный" if port.required else "опциональный"
                lines.append(f"  - `{port.name}` (`{port.contract_type}`, {req}) — {port.description}")
        else:
            lines.append("- **Выходы (`Outputs`):** `нет внешних выходов`")

        lines.extend(["", "### Реестр владения и символов (`Ownership & Symbols`)"])
        owned_str = ", ".join(f"`{f}`" for f in self.owned_files)
        sys_str = ", ".join(f"`.isai/{f}`" for f in self.system_files)
        lines.append(f"- **Файлы узла (`owned_files`):** {owned_str}")
        lines.append(f"- **Служебные файлы (`system_files`):** {sys_str}")
        if self.defined_symbols:
            sym_str = ", ".join(f"`{self.node_id}#{s}`" for s in self.defined_symbols)
            lines.append(f"- **Экспортируемые сущности (`defined_symbols`):** {sym_str}")

        lines.extend(["", "### Связи и Маршрутизация (`Router & Transitions`)"])
        if self.related_refs:
            rel_str = ", ".join(f"`{r}`" for r in self.related_refs)
            lines.append(f"- **Связанные сущности (`related_refs`):** {rel_str}")
        else:
            lines.append("- **Связанные сущности (`related_refs`):** `нет дополнительных ссылок`")

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
