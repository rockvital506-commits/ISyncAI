"""Ring IL-1C Sub-Genesis Neuro-Vascular Fundamental (`isai://root#NeuroVascularFundamental`)
and the 6-Step Algedonic Constitutional Escalation & Ratification State Machine.
"""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from isai.constitution import IntegrityLevel
from isai.contracts import EntityRef
from isai.protocol import TaskManifest

NVF_SYNC_BEGIN = "<!-- ISAI:NVF_SYNC:BEGIN -->"
NVF_SYNC_END = "<!-- ISAI:NVF_SYNC:END -->"


class AlgedonicStepId(StrEnum):
    """Strict 6-step sequence required to neutralize critical goal drift or amend IL-1C."""

    STEP_1_CONFIRM_DEVIATION = "1.CONFIRM_DEVIATION"
    STEP_2_WARN_OPERATOR = "2.WARN_OPERATOR"
    STEP_3_CONDUCT_DEEP_RESEARCH = "3.CONDUCT_DEEP_RESEARCH"
    STEP_4_RECOMMEND_NEUTRALIZATION = "4.RECOMMEND_NEUTRALIZATION"
    STEP_5_SYNTHESIZE_PHASED_TASK = "5.SYNTHESIZE_PHASED_TASK"
    STEP_6_AWAIT_OPERATOR_CONFIRMATION = "6.AWAIT_OPERATOR_CONFIRMATION"


ALGEDONIC_STEP_ORDER: tuple[AlgedonicStepId, ...] = (
    AlgedonicStepId.STEP_1_CONFIRM_DEVIATION,
    AlgedonicStepId.STEP_2_WARN_OPERATOR,
    AlgedonicStepId.STEP_3_CONDUCT_DEEP_RESEARCH,
    AlgedonicStepId.STEP_4_RECOMMEND_NEUTRALIZATION,
    AlgedonicStepId.STEP_5_SYNTHESIZE_PHASED_TASK,
    AlgedonicStepId.STEP_6_AWAIT_OPERATOR_CONFIRMATION,
)


class AlgedonicDeviationCase(BaseModel):
    """
    Executable Beer-VSM Algedonic Channel & Clause-Bound Constitutional Amendment Gate.
    Enforces 'Order=Absolute | SkipStep=FATAL': no step N+1 artifact may be populated
    while any prerequisite step 1..N is empty, and execution/IL-1C write lease is forbidden
    until all 6 steps are complete AND operator_confirmed is True.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str = Field(min_length=1)
    violated_goal_ref: EntityRef = "isai://root#MasterVector"
    # Step 1: Confirm & quantify critical deviation
    confirmed_deviation_evidence: str | None = None
    # Step 2: Warn Operator immediately
    operator_warning_alert: str | None = None
    # Step 3: Conduct broad scientific & codebase research
    deep_research_findings: tuple[str, ...] = ()
    # Step 4: Recommend neutralization mechanisms & patterns
    recommended_mechanisms: tuple[str, ...] = ()
    # Step 5: Synthesize phased TaskManifest
    proposed_task: TaskManifest | None = None
    # Step 6: Explicit human-in-the-loop confirmation
    operator_confirmed: bool = False
    operator_confirmation_note: str | None = None

    @model_validator(mode="after")
    def _enforce_linear_step_progression(self) -> AlgedonicDeviationCase:
        populated = [
            bool(self.confirmed_deviation_evidence and self.confirmed_deviation_evidence.strip()),
            bool(self.operator_warning_alert and self.operator_warning_alert.strip()),
            len(self.deep_research_findings) > 0,
            len(self.recommended_mechanisms) > 0,
            self.proposed_task is not None,
            bool(self.operator_confirmed),
        ]
        seen_gap = False
        for idx, is_present in enumerate(populated):
            if not is_present:
                seen_gap = True
            elif seen_gap:
                step_name = ALGEDONIC_STEP_ORDER[idx].value
                raise ValueError(
                    f"SkipStep=FATAL in AlgedonicDeviationCase '{self.case_id}': "
                    f"cannot populate '{step_name}' before completing all preceding Algedonic steps."
                )
        if self.operator_confirmed and not (
            self.operator_confirmation_note and self.operator_confirmation_note.strip()
        ):
            raise ValueError(
                "Step 6 operator_confirmed=True requires a non-empty operator_confirmation_note."
            )
        return self

    @property
    def completed_steps(self) -> tuple[AlgedonicStepId, ...]:
        flags = (
            bool(self.confirmed_deviation_evidence and self.confirmed_deviation_evidence.strip()),
            bool(self.operator_warning_alert and self.operator_warning_alert.strip()),
            len(self.deep_research_findings) > 0,
            len(self.recommended_mechanisms) > 0,
            self.proposed_task is not None,
            bool(self.operator_confirmed),
        )
        res: list[AlgedonicStepId] = []
        for step_id, ok in zip(ALGEDONIC_STEP_ORDER, flags):
            if ok:
                res.append(step_id)
            else:
                break
        return tuple(res)

    def is_ratified_for_execution(self) -> bool:
        """Return True iff all 6 Algedonic steps are complete and explicitly ratified by Operator."""
        return len(self.completed_steps) == 6 and self.operator_confirmed is True


class NeuroVascularFundamentalSpec(BaseModel):
    """
    Canonical, Zero-Redundancy Pydantic model of the ISAI-NVF Sub-Genesis Fundamental (IL-1C).
    Deterministically projects:
      1. Exact 53-line symbolic DSL meta-prompt (`render_dsl()`) with 0% semantic loss.
      2. Synchronized human/Pure-LLM root document `FUNDAMENTAL.md` (`render_markdown()`).
      3. Bimodal U-curve RSoC slices (`primacy_head_packet()` + `recency_tail_packet()`).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    fundamental_id: EntityRef = "isai://root#NeuroVascularFundamental"
    frame_id: str = "ISAI-NVF/1.1"
    version: str = "1.1"
    tier: IntegrityLevel = IntegrityLevel.IL_1C_FUNDAMENTAL
    tier_token: str = "IL-1C_SUB_GENESIS"
    governed_by: EntityRef = "isai://root#GenesisKernel"
    priority_order: str = "IL-0_GENESIS >> IL-1C_NVF >> IL-1_KERNEL >> IL-2_CANONICAL >> IL-3_STAGING"
    agent_calibration: str = (
        "FiduSys-Novator & Graph-Chronitect | Mandate: Deterministic-Reflex >> LLM-Guess"
    )
    mutability_law: str = (
        "CONDITIONALLY_LOCKED[RoutineEdit=FATAL | AmendVia=ALGEDONIC_6STEP_ONLY | "
        "VectorMutation=CHECKBOX_RATIFIED_LEDGER_ONLY]"
    )

    lexicon_anchors: tuple[str, ...]
    nervous_rules: tuple[str, ...]
    spinal_reflexes: tuple[str, ...]
    nervous_tritier_rule: str
    vascular_rules: tuple[str, ...]
    vector_governance_rules: tuple[str, ...]
    precedents_summary: str
    bottleneck_guards_summary: str
    homeostasis_mode: str
    algedonic_mode_header: str
    algedonic_sequence: tuple[str, ...]
    recency_tripwires: tuple[str, ...]
    anchored_entity_refs: tuple[EntityRef, ...]

    def render_dsl(self) -> str:
        """Render the exact ISAI-LNTE v2.0 symbolic cognitive frame (ISAI-NVF v1.0) losslessly."""
        lines: list[str] = [
            "# ISAI-NVF :: NEURO-VASCULAR FUNDAMENTAL",
            f"[FRAME-ID]: {self.frame_id} | TIER: {self.tier_token} | GOVERNED-BY: {self.governed_by}",
            f"[PRIORITY-ORDER]: {self.priority_order}",
            f"[AGENT-CALIBRATION]: {self.agent_calibration}",
            f"[MUTABILITY-LAW]: {self.mutability_law}",
            "",
            "[LEXICON-ANCHORS]:",
        ]
        for item in self.lexicon_anchors:
            lines.append(f"  - {item}")

        lines.extend(
            [
                "",
                "[NERVOUS-CIRCUIT :: TOPOLOGY, REGISTRATION, INDEXING, TRANSITIONS & MUTATION]:",
            ]
        )
        for rule in self.nervous_rules:
            lines.append(f"  - {rule}")
        lines.append("  - N7.Spinal-Reflexes:")
        for reflex in self.spinal_reflexes:
            lines.append(f"      {reflex}")
        lines.append(f"  - {self.nervous_tritier_rule}")

        lines.extend(
            [
                "",
                "[VASCULAR-CIRCUIT :: RSoC DELIVERY, PORT CAPILLARIES, HOMEOSTASIS & COAGULATION]:",
            ]
        )
        for vrule in self.vascular_rules:
            lines.append(f"  - {vrule}")

        lines.extend(["", "[VECTOR-GOVERNANCE :: GOAL-VECTOR MUTATION LEDGER & LIFECYCLE GATES]:"])
        for vrule in self.vector_governance_rules:
            lines.append(f"  - {vrule}")

        lines.extend(
            [
                "",
                "[IMMUNE-MEMORY :: PRECEDENTS & BOTTLENECK WATCH]:",
                f"  - {self.precedents_summary}",
                f"  - {self.bottleneck_guards_summary}",
                "",
                "[GOVERNANCE-ROUTING :: HOMEOSTATIC ABSORPTION VS ALGEDONIC AMENDMENT]:",
                f"  - {self.homeostasis_mode}",
                f"  - {self.algedonic_mode_header}",
            ]
        )
        for idx, step_line in enumerate(self.algedonic_sequence):
            prefix = "      " if idx == 0 else "      -> "
            lines.append(f"{prefix}{step_line}")

        lines.extend(["", "[RECENCY-TRIPWIRES :: HARD EXECUTION GUARD]:"])
        for tw in self.recency_tripwires:
            lines.append(f"  - {tw}")

        return "\n".join(lines) + "\n"

    def dsl_sha256(self) -> str:
        """Cryptographic SHA-256 digest of the exact rendered ISAI-NVF symbolic DSL text."""
        return hashlib.sha256(self.render_dsl().encode("utf-8")).hexdigest()

    def spec_digest(self) -> str:
        """Deterministic structural digest of the complete NeuroVascularFundamentalSpec."""
        raw = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def primacy_head_packet(self) -> dict[str, Any]:
        """
        Top-of-window RSoC Primacy Anchor slice: locks Attention Sinks with priority order,
        mutability lock, lexicon bindings, and core neuro-vascular & immune invariants.
        """
        return {
            "fundamental_id": self.fundamental_id,
            "frame_id": self.frame_id,
            "version": self.version,
            "tier": self.tier.value,
            "dsl_sha256": self.dsl_sha256(),
            "priority_order": self.priority_order,
            "agent_calibration": self.agent_calibration,
            "mutability_law": self.mutability_law,
            "lexicon_anchors": list(self.lexicon_anchors),
            "nervous_circuit": [
                *self.nervous_rules,
                *(f"N7.{r}" for r in self.spinal_reflexes),
                self.nervous_tritier_rule,
            ],
            "vascular_circuit": list(self.vascular_rules),
            "vector_governance": list(self.vector_governance_rules),
            "immune_memory": [self.precedents_summary, self.bottleneck_guards_summary],
        }

    def recency_tail_packet(self) -> dict[str, Any]:
        """
        End-of-window RSoC Recency Anchor slice: placed at the very end of compiled RSoC packets
        so RoPE locality enforces Algedonic routing & STOP-1..4 tripwires right before generation.
        """
        return {
            "frame_id": self.frame_id,
            "dsl_sha256": self.dsl_sha256(),
            "vector_mutation_law": self.mutability_law,
            "governance_routing": {
                "homeostasis": self.homeostasis_mode,
                "algedonic_escalation": self.algedonic_mode_header,
                "algedonic_6step_sequence": list(self.algedonic_sequence),
            },
            "recency_tripwires": list(self.recency_tripwires),
        }

    def render_markdown(self) -> str:
        """Render root FUNDAMENTAL.md synchronized projection for Human & Pure-LLM fallback."""
        s_digest = self.spec_digest()
        d_sha = self.dsl_sha256()
        return "\n".join(
            [
                NVF_SYNC_BEGIN,
                f"<!-- isai:nvf_id={self.fundamental_id} -->",
                f"<!-- isai:nvf_version={self.version} -->",
                f"<!-- isai:nvf_digest={s_digest} -->",
                f"<!-- isai:nvf_dsl_sha256={d_sha} -->",
                "",
                f"# Субконституционный Нервно-Сосудистый Фундаментал (`{self.frame_id}`)",
                "",
                f"> **Кольцо целостности:** `{self.tier.value}` (`{self.tier_token}`) — подчинён исключительно `isai://root#GenesisKernel` (`IL_0_GENESIS`).",
                f"> **Режим мутируемости:** `{self.mutability_law}` (любая правка без ратифицированного Оператором события `RATIFY_FUNDAMENTAL` в `.isai/chronicle.jsonl` блокируется `isai audit`).",
                f"> **Отпечаток DSL (`SHA-256`):** `{d_sha}`",
                "",
                "```yaml",
                self.render_dsl().rstrip("\n"),
                "```",
                "",
                NVF_SYNC_END,
                "",
            ]
        )


NEURO_VASCULAR_FUNDAMENTAL = NeuroVascularFundamentalSpec(
    lexicon_anchors=(
        "Nervous-Circuit := FractalTopology + EAVT_VAET_Index + SpinalReflexes + AST_LinkMutator + TriTier_GateA",
        "Vascular-Circuit := RSoC_Artery + Ring_BBB + BDCT_Capillaries + Watchdog_VenousGC + ChronoKnowledge_Distill",
        "Ring-BBB := VisibilityScope[PUBLIC | SUBTREE | EPHEMERAL_STAGING] + SymbolVisibility[PUBLIC | INTERNAL] + ControlData_Split",
        "BDCT-Contract := ∀PortWiring(P->C): schema_refs(P)!=∅ & schema_refs(C)!=∅ & types(P)<=types(C)",
        "Shadow-Tx := AdmissionCheck -> atomic_transaction_batch(+extra_backup_paths) -> isai_sync -> GateA | OnFail=>ByteRollback",
    ),
    nervous_rules=(
        "N1.Addressing: EntityRef := isai://<scope>[#<symbol>] | Root := isai://root | Child := isai://<rel_posix_path> (¬isai://root/<child>)",
        "N2.Registration: ∀Dir: (.isai/node.py [Pure-AST ISAINodeSpec] <-> README.md [Prose + SYNC_Block]) & ∀File: RegisterIn[owned_files | system_files] & ∀Export: BindPhysical[SymbolBindingSpec -> python_attr | system_artifact | owned_artifact] | OrphanOrBrokenSymbol=FATAL",
        "N3.Single-Edge-Index: DeclareAtSourceOnly[parent_ref | EdgeLinkSpec | PortWiringSpec | TransitionRule | SymbolBindingSpec] -> SinglePass_AutoIndex[EAVT_out + VAET_in] | ManualBacklinks=FATAL(ZERO-Redundancy)",
        "N4.Router-Transitions: ReachableFrom(isai://root + active_tasks)==100% | TransitionRule[FAST_READ(0_Handles,ReadOnly) | STAGED_TRANSACTION(MVCC_WriteLease+TTL,DisjointWriteSet)]",
        "N5.Sense-Before-Act: PreMutate(URI) => RUN `isai graph query <URI>` -> `isai graph can-mutate <URI>` -> `isai graph affected-tests <URI>`",
        "N6.Motor-Surgery: ∀LinkPortSymbolNode_Edit => RUN `isai link <add|remove|wire-port|unwire-port|refactor|scaffold-node|decommission-node> [--dry-run]` -> `isai sync` | RawHandEdit(node.py_edges | SYNC_Block)=FORBIDDEN",
    ),
    spinal_reflexes=(
        "IMPURE_NODE_AST: Pre-import AST whitelist on node.py (imports ∈ {__future__, isai.constitution, isai.contracts}; single NODE=ISAINodeSpec)",
        "IMMUTABLE_TARGET_VIOLATION: ¬(MUTATES_TARGET | STAGED_TRANSACTION | WRITE_LEASE) -> isai://root#GenesisKernel",
        "VAET-Finalizer: Block `decommission-node(X)` while ExternalInbound(VAET,X)!=∅ | Children(X)!=∅",
        "Prose-Scanner: ∀RefInMarkdown(¬FencedCode, ¬SYNC_Block): Resolve[RelPath | isai://<uri> | TX-<dddd> | PAT_<NAME>] => else BROKEN_MARKDOWN_LINK | BROKEN_PROSE_REF",
    ),
    nervous_tritier_rule=(
        "N8.TriTier-GateA: CertifyGraphMechanics via [T1:BDCT_And_VisibilityMatrix | T2:FullTreeSHA256_Rollback_And_DryRun | T3:Hypothesis_RuleBasedStateMachine(database=None,derandomize=True)]"
    ),
    vascular_rules=(
        "V1.RSoC-Artery: ContextBoot(URI) => RUN `isai rsoc <URI>` -> Inject[IL-0 + MasterVector + AncestorInvariants + ActiveContract + 1Hop_InterfaceStubs + TagSliced(isai://user, isai://knowledge)] | RawControlPlaneDumpsInPrompt=FORBIDDEN",
        "V2.BBB-Visibility: ¬StaticEdge(IL-1|IL-2|isai://tasks -> EPHEMERAL_STAGING) & ¬CrossScopeRef(SUBTREE | INTERNAL) => VISIBILITY_VIOLATION",
        "V3.Capillary-Salsa: VerifyPortSchemas[BROKEN_PORT_SCHEMA | INCOMPATIBLE_PORT_WIRING] | interface_digest := SHA256(ports + canonical_model_json_schema(schema_refs) + public_symbols + invariants + transitions) | Unchanged=>Salsa_EarlyCutoff; Changed=>CycleSafe_NHop_BFS",
        "V4.Venous-Lifecycle: MultiStepWork => Stage(tasks/TASK-<id>, EPHEMERAL_STAGING) + ISAI-PEP_v1[MaxIter=3, ConditionalResearch, GateA_Before_GateB] -> Promote[KnowledgeCatalogSpec.upsert + Calibrate(isai://user) + Append(isai://root#ChronicleLedger) + HandleCount==0]",
        "V5.Hemostasis-Recovery: Writes := .isai_tmp_* + fsync(file) + os.replace + fsync(dir) | CrashOrTornState => RUN `isai recover` (Idempotent: 0_Tx_On_Clean) | MissingVenv => Rehydrate(.venv) or PureLLM_Read(state_snapshot.json + node.py)",
    ),
    vector_governance_rules=(
        "VM1.SingleSource: VectorState := deterministic_fold(.isai/vector_ledger.jsonl) | "
        "SourceOfTruth := .isai/vector.py -> VISION.md:=projection | "
        "SilentProposalDrop=FATAL | AppendOnlyTamper=FATAL",
        "VM2.ProposalBinding: ∀Proposal: id + Anchor[kind,index] + anchor_fingerprint(SHA256) + "
        "base_vector_digest + rationale(>=60ch) + evidence[>=1] + expected_benefit + risk | "
        "StaleAnchorApply=FATAL | UnjustifiedCheckbox=FATAL",
        "VM3.SignalSource: ConfirmationChannel := OperatorPromptOnly (¬self-output) & "
        "∀SignalLine: ¬FencedCode ∧ ¬InlineCode ∧ ¬QuotedProse | "
        "Phrase := standalone_control_line[подтвердить вектор системы] | "
        "Phrase=RatifyCurrentVectorOnly(¬blanket_mutation_consent) | SelfConfirmation=FATAL",
        "VM4.ApplyCeremony: CONFIRMED => mutate(.isai/vector.py) -> `isai vector apply` -> "
        "atomic[MUTATE_VECTOR + APPLIED + state_snapshot + VISION.md] | "
        "ApplyWithoutConfirm=FATAL | ApplyWithoutLiveDigestChange=FATAL | VersionBump=REQUIRED",
        "VM5.DeferralDecay: DeferWindow=1_prompt | Deferrals>=2 => EXPIRED => ReProposeWithFreshEvidence | "
        "OrphanPendingProposal=FATAL | ProposalBatch<=5_ranked",
        "VM6.DriftDetect: ∀ChangedAnchor: ∃APPLIED(anchor) ∧ contiguous_digest_chain | "
        "else UNCONFIRMED_VECTOR_DRIFT=FATAL | RawHandEdit(vector.py)=FORBIDDEN",
        "VM7.GateV-PrePR: PrePR => `isai gate verify` over "
        "[ROOT | TASKS | KNOWLEDGE | UNIVERSE | TESTS | .isai_Subfolders] | "
        "CriticalDeviation => Neutralize -> Return_PrePR -> FullRerun(no_partial) | "
        "StatusAssertedInProse=FATAL | Status:=NO_SYSTEMIC_DEVIATION only_by_tool_with_evidence_digest",
        "VM8.TurnBoundary: PrePromptGate:=read(prev_checkboxes ∪ phrase) -> "
        "[phrase∧¬boxes => RatifyVector + DeferPending] ∨ [boxes => Strategy -> Apply] -> ApplyGate | "
        "PostPromptGate:=AuditVector -> AuditResearchWindow(since_last_APPLIED|BASELINE) -> "
        "RankProposals(<=5) -> CheckboxRequest | GateSkipped=FATAL",
    ),
    precedents_summary=(
        "Precedents[PREC-01..09]: Prefix586_HashSplit | LiveUTF8_CompileExec_NoPycCollision(PEP3147_mtime_size) | Physical_SymbolBinding | FenceSafe_ProseScan | ModelJsonSchema_CrossProcDeterminism | StripSYNC_FromProseVAET | ExtraBackupPaths_FullRollback | PreImport_ASTGate | VenvRehydrate_Or_SnapshotFallback"
    ),
    bottleneck_guards_summary=(
        "Bottleneck-Guards[BN-01..06]: SingleWriterDiscipline(Until_OS_Flock) | IncrementalizeIndexAtScale | AtomicSubtreeMoveViaCompose(Scaffold->Migrate->Refactor->Decommission) | BoundHighFanoutRSoC | PreemptRawFileEditsViaThisFrame | AlgedonicCircuitForIL1C"
    ),
    homeostasis_mode=(
        "Mode-1.Homeostasis(Autonomous): Standard bugs, local retries (iter<=3), and lawful IL-2/IL-3/LinkMutator evolutions -> resolve autonomously via ISAI-PEP_v1 + GateA(`isai audit` & `pytest`)."
    ),
    algedonic_mode_header=(
        "Mode-2.Algedonic-Escalation(Operator-Gated): Confirmed critical deviation from isai://root#GenesisKernel or isai://root#MasterVector, systemic bottleneck breach, 3/3 ISAI-PEP architectural deadlock, or required mutation of IL-1C_NVF -> EXECUTE STRICT 6-STEP SEQUENCE (SkipStep=FATAL):"
    ),
    algedonic_sequence=(
        "1.CONFIRM_DEVIATION[Reproduce + Quantify_Drift_Against_MasterVector_And_Invariants]",
        "2.WARN_OPERATOR[Surface_Algedonic_Alert: Evidence | ViolatedGoal | BlastRadius]",
        "3.CONDUCT_DEEP_RESEARCH[Run_MultiSource_Scientific_And_Repository_Investigation]",
        "4.RECOMMEND_NEUTRALIZATION[Deliver_Ranked_Mechanisms_Patterns_And_Tradeoffs]",
        "5.SYNTHESIZE_PHASED_TASK[Build_TaskManifest_DAG + ISAI-PEP_v1_TriTier_Gates + RollbackPlan]",
        "6.AWAIT_OPERATOR_CONFIRMATION[Launch_Task_IFF_Explicit_Operator_Approval==TRUE; else_Hold_IL-1C]",
    ),
    recency_tripwires=(
        "STOP-1[IL-0]: Any byte edit in README.md[0:586] or WRITE_LEASE on GenesisKernel => ABORT_EXECUTION.",
        "STOP-2[LINKS]: Any manual edit to node.py links/ports/transitions or README SYNC_Block => FREEZE; route via `isai graph` -> `isai link` -> `isai sync`.",
        "STOP-3[PROMOTE]: Any task promotion with `isai audit`!=0, `pytest`!=0, or HandleCount!=0 => BLOCK_PROMOTE.",
        "STOP-4[AMEND]: Any unapproved mutation of IL-1C_NVF or silent suppression of critical goal drift => HALT; fire Algedonic Step 1->2 immediately.",
    ),
    anchored_entity_refs=(
        "isai://root#GenesisKernel",
        "isai://root#MasterVector",
        "isai://root#ChronicleLedger",
        "isai://user",
        "isai://knowledge",
        "isai://tasks",
    ),
)
