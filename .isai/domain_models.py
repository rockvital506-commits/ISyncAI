"""Structured Domain Schemas: Mutable Master Vector (VISION.md), User Twin (/user), Knowledge Store (/knowledge)."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from isai.contracts import EntityRef

VECTOR_SYNC_BEGIN = "<!-- ISAI:VECTOR_SYNC:BEGIN -->"
VECTOR_SYNC_END = "<!-- ISAI:VECTOR_SYNC:END -->"


class MasterVectorPillar(BaseModel):
    """Architectural pillar of the ISAI Ultimate Goal & Orientation Vector."""

    model_config = ConfigDict(frozen=True)

    pillar_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    essence: str = Field(min_length=1)
    mechanisms: tuple[str, ...] = Field(min_length=1)
    governing_axioms: tuple[str, ...] = Field(min_length=1)


class MasterVectorHorizon(BaseModel):
    """Evolutionary stage along the ISAI development trajectory."""

    model_config = ConfigDict(frozen=True)

    stage: str = Field(min_length=1)
    focus: str = Field(min_length=1)
    exit_condition: str = Field(min_length=1)


class MasterVectorSpec(BaseModel):
    """
    Canonical, Chrono-tracked Master Goal & Orientation Vector of ISyncAI (ISAI).
    Unlike the IL-0 Genesis Frame (which never changes), the Master Vector MAY evolve
    via audited transactions as empirical insights accumulate.
    """

    model_config = ConfigDict(frozen=True)

    schema_version: str = "0.1.0"
    vector_id: EntityRef = "isai://root#MasterVector"
    version: str = Field(min_length=1)
    mutability_policy: str = (
        "GOVERNED_MUTABLE: Может уточняться и эволюционировать по мере роста ISAI "
        "строго через фазовый цикл AUDIT -> CONSTRUCT -> CHRONICLE без нарушения IL-0 Genesis Frame."
    )
    north_star_statement: str = Field(min_length=1)
    core_objectives: tuple[str, ...] = Field(min_length=1)
    architectural_pillars: tuple[MasterVectorPillar, ...] = Field(min_length=1)
    evolution_horizons: tuple[MasterVectorHorizon, ...] = Field(min_length=1)
    anti_goals: tuple[str, ...] = Field(min_length=1)

    def spec_digest(self) -> str:
        raw = json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def render_markdown(self) -> str:
        """Render the complete human-readable VISION.md document with embedded verification digest."""
        digest = self.spec_digest()
        lines: list[str] = [
            VECTOR_SYNC_BEGIN,
            f"<!-- isai:vector_id={self.vector_id} -->",
            f"<!-- isai:vector_version={self.version} -->",
            f"<!-- isai:vector_digest={digest} -->",
            "",
            f"# Итоговая цель и Вектор развития ISyncAI (`ISAI Master Vector v{self.version}`)",
            "",
            f"> **Статус документа:** Действующий стратегический вектор-ориентир (`{self.vector_id}`).",
            f"> **Политика изменяемости:** {self.mutability_policy}",
            "> **Конституционная опора:** Подчинён неизменяемому ядру `isai://root#GenesisKernel` (`IL_0_GENESIS`).",
            "",
            "---",
            "",
            "## 1. Главная смысло-цель (`North Star`)",
            "",
            self.north_star_statement,
            "",
            "## 2. Целевые контуры оптимизации симбиоза",
            "",
        ]
        for obj in self.core_objectives:
            lines.append(f"- {obj}")

        lines.extend(["", "## 3. Архитектурные столпы системы `ISAI`", ""])
        for idx, p in enumerate(self.architectural_pillars, start=1):
            lines.append(f"### 3.{idx}. `{p.pillar_id}` — {p.title}")
            lines.append(f"- **Суть:** {p.essence}")
            lines.append(f"- **Аксиоматическая база:** {', '.join(f'`{a}`' for a in p.governing_axioms)}")
            lines.append("- **Ключевые механизмы:**")
            for m in p.mechanisms:
                lines.append(f"  - {m}")
            lines.append("")

        lines.extend(["## 4. Горизонты эволюции (`Roadmap Vector`)", ""])
        for h in self.evolution_horizons:
            lines.append(f"- **{h.stage}:** {h.focus} *(Критерий зрелости: {h.exit_condition})*")

        lines.extend(["", "## 5. Осознанные анти-цели (защита от деградации)", ""])
        for ag in self.anti_goals:
            lines.append(f"- {ag}")

        lines.extend(["", VECTOR_SYNC_END, ""])
        return "\n".join(lines)


class CompetencyRecord(BaseModel):
    """Verified operator domain competency/preference entry in /user."""

    model_config = ConfigDict(frozen=True)

    competency_id: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    level: Literal["architect", "advanced", "practitioner", "exploring"]
    calibration_hint: str = Field(min_length=1)
    tags: tuple[str, ...] = ()


class CognitiveDirective(BaseModel):
    """Behavioral alignment rule calibrating any connected model to the user's cognitive style."""

    model_config = ConfigDict(frozen=True)

    directive_id: str = Field(min_length=1)
    rule: str = Field(min_length=1)
    rationale: str = Field(min_length=1)


class UserProfileSpec(BaseModel):
    """Structured HKCU-equivalent User Cognitive & Competency Hive model."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "0.1.0"
    profile_ref: EntityRef = "isai://user#OperatorProfile"
    archetype: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    directives: tuple[CognitiveDirective, ...] = Field(min_length=1)
    competencies: tuple[CompetencyRecord, ...] = Field(min_length=1)


class KnowledgeEntry(BaseModel):
    """Distilled, reusable empirical unit stored in /knowledge (patterns, findings, guardrails)."""

    model_config = ConfigDict(frozen=True)

    entry_id: str = Field(min_length=1)
    category: Literal["pattern", "architecture_decision", "anti_pattern", "environment_fact"]
    title: str = Field(min_length=1)
    distilled_insight: str = Field(min_length=1)
    applicability_tags: tuple[str, ...] = Field(min_length=1)
    related_node_ref: EntityRef
    origin_tx_id: str = Field(min_length=1)
    #: Chronicle revision in which this entry was **written**, not proof that it was checked.
    #: The two were conflated until the embedding study showed the cost: `PAT_BIO_UNIVERSE` carried
    #: revision 8 while having zero executable symbols, and `3.18x` in the same entry turned out to
    #: be the *worst* of four correct cache strategies. Conflating "recorded" with "verified" is how
    #: a catalog manufactures confidence, so the two now have separate fields.
    verified_revision: int = Field(ge=1)
    #: How far the mechanism described here has actually been built. `PROSE` means the entry is a
    #: design, never a claim that code exists; `MEASURED` means a reproducible artifact backs the
    #: numbers; `IMPLEMENTED` means an executable symbol exists in the kernel.
    maturity: Literal["PROSE", "MEASURED", "IMPLEMENTED"] = "PROSE"
    #: Repository-relative path to the artifact that reproduces this entry's numbers, if any.
    #: Empty means "no evidence was recorded" — which is honest, and now visible.
    evidence_ref: str = ""
    #: The one live symbol that *is* this mechanism, named explicitly rather than inferred.
    #:
    #: `maturity=IMPLEMENTED` used to be an honour-system claim: nothing checked that the entry
    #: described code rather than a design. A keyword scan over the prose was tried first and
    #: produced false passes — `spec_digest` is a parameter name, not a mechanism — so the binding
    #: is declared here and verified by `H-KNOW-08`. An entry cannot buy `IMPLEMENTED` with wording.
    primary_symbol: str = ""


class KnowledgeCatalogSpec(BaseModel):
    """Deduplicated empirical knowledge store enforcing ZERO-Redundancy via upsert semantics."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "0.1.0"
    catalog_ref: EntityRef = "isai://knowledge#EmpiricalCatalog"
    entries: tuple[KnowledgeEntry, ...] = ()

    @model_validator(mode="after")
    def _ensure_unique_ids(self) -> KnowledgeCatalogSpec:
        ids = [e.entry_id for e in self.entries]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate entry_id in KnowledgeCatalogSpec (Redundancy=FATAL).")
        return self

    def upsert(self, entry: KnowledgeEntry) -> KnowledgeCatalogSpec:
        """Insert or replace a knowledge entry by entry_id without creating duplicates."""
        updated: list[KnowledgeEntry] = []
        replaced = False
        for item in self.entries:
            if item.entry_id == entry.entry_id:
                updated.append(entry)
                replaced = True
            else:
                updated.append(item)
        if not replaced:
            updated.append(entry)
        return KnowledgeCatalogSpec(
            schema_version=self.schema_version,
            catalog_ref=self.catalog_ref,
            entries=tuple(updated),
        )
