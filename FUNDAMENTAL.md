<!-- ISAI:NVF_SYNC:BEGIN -->
<!-- isai:nvf_id=isai://root#NeuroVascularFundamental -->
<!-- isai:nvf_version=1.2 -->
<!-- isai:nvf_digest=7e0250bfd7c6ea511b569fd1baba44f4ec835a387495d3cc15e479448ab40f66 -->
<!-- isai:nvf_dsl_sha256=d5e519fd2e8b77aca1fd9d4f4941d0327a49eee34331ac8e65ffd5a8253fce3a -->

# Субконституционный Нервно-Сосудистый Фундаментал (`ISAI-NVF/1.2`)

> **Кольцо целостности:** `IL_1C_FUNDAMENTAL` (`IL-1C_SUB_GENESIS`) — подчинён исключительно `isai://root#GenesisKernel` (`IL_0_GENESIS`).
> **Режим мутируемости:** `CONDITIONALLY_LOCKED[RoutineEdit=FATAL | AmendVia=ALGEDONIC_6STEP_ONLY | VectorMutation=NUMBERED_OPERATOR_TASK_LEDGER_ONLY]` (любая правка без ратифицированного Оператором события `RATIFY_FUNDAMENTAL` в `.isai/chronicle.jsonl` блокируется `isai audit`).
> **Отпечаток DSL (`SHA-256`):** `d5e519fd2e8b77aca1fd9d4f4941d0327a49eee34331ac8e65ffd5a8253fce3a`

```yaml
# ISAI-NVF :: NEURO-VASCULAR FUNDAMENTAL
[FRAME-ID]: ISAI-NVF/1.2 | TIER: IL-1C_SUB_GENESIS | GOVERNED-BY: isai://root#GenesisKernel
[PRIORITY-ORDER]: IL-0_GENESIS >> IL-1C_NVF >> IL-1_KERNEL >> IL-2_CANONICAL >> IL-3_STAGING
[AGENT-CALIBRATION]: FiduSys-Novator & Graph-Chronitect | Mandate: Deterministic-Reflex >> LLM-Guess
[MUTABILITY-LAW]: CONDITIONALLY_LOCKED[RoutineEdit=FATAL | AmendVia=ALGEDONIC_6STEP_ONLY | VectorMutation=NUMBERED_OPERATOR_TASK_LEDGER_ONLY]

[LEXICON-ANCHORS]:
  - Nervous-Circuit := FractalTopology + EAVT_VAET_Index + SpinalReflexes + AST_LinkMutator + TriTier_GateA
  - Vascular-Circuit := RSoC_Artery + Ring_BBB + BDCT_Capillaries + Watchdog_VenousGC + ChronoKnowledge_Distill
  - Ring-BBB := VisibilityScope[PUBLIC | SUBTREE | EPHEMERAL_STAGING] + SymbolVisibility[PUBLIC | INTERNAL] + ControlData_Split
  - BDCT-Contract := ∀PortWiring(P->C): schema_refs(P)!=∅ & schema_refs(C)!=∅ & types(P)<=types(C)
  - Shadow-Tx := AdmissionCheck -> atomic_transaction_batch(+extra_backup_paths) -> isai_sync -> GateA | OnFail=>ByteRollback

[NERVOUS-CIRCUIT :: TOPOLOGY, REGISTRATION, INDEXING, TRANSITIONS & MUTATION]:
  - N1.Addressing: EntityRef := isai://<scope>[#<symbol>] | Root := isai://root | Child := isai://<rel_posix_path> (¬isai://root/<child>)
  - N2.Registration: ∀Dir: (.isai/node.py [Pure-AST ISAINodeSpec] <-> README.md [Prose + SYNC_Block]) & ∀File: RegisterIn[owned_files | system_files] & ∀Export: BindPhysical[SymbolBindingSpec -> python_attr | system_artifact | owned_artifact] | OrphanOrBrokenSymbol=FATAL
  - N3.Single-Edge-Index: DeclareAtSourceOnly[parent_ref | EdgeLinkSpec | PortWiringSpec | TransitionRule | SymbolBindingSpec] -> SinglePass_AutoIndex[EAVT_out + VAET_in] | ManualBacklinks=FATAL(ZERO-Redundancy)
  - N4.Router-Transitions: ReachableFrom(isai://root + active_tasks)==100% | TransitionRule[FAST_READ(0_Handles,ReadOnly) | STAGED_TRANSACTION(MVCC_WriteLease+TTL,DisjointWriteSet)]
  - N5.Sense-Before-Act: PreMutate(URI) => RUN `isai graph query <URI>` -> `isai graph can-mutate <URI>` -> `isai graph affected-tests <URI>`
  - N6.Motor-Surgery: ∀LinkPortSymbolNode_Edit => RUN `isai link <add|remove|wire-port|unwire-port|refactor|scaffold-node|decommission-node> [--dry-run]` -> `isai sync` | RawHandEdit(node.py_edges | SYNC_Block)=FORBIDDEN
  - N7.Spinal-Reflexes:
      IMPURE_NODE_AST: Pre-import AST whitelist on node.py (imports ∈ {__future__, isai.constitution, isai.contracts}; single NODE=ISAINodeSpec)
      IMMUTABLE_TARGET_VIOLATION: ¬(MUTATES_TARGET | STAGED_TRANSACTION | WRITE_LEASE) -> isai://root#GenesisKernel
      VAET-Finalizer: Block `decommission-node(X)` while ExternalInbound(VAET,X)!=∅ | Children(X)!=∅
      Prose-Scanner: ∀RefInMarkdown(¬FencedCode, ¬SYNC_Block): Resolve[RelPath | isai://<uri> | TX-<dddd> | PAT_<NAME>] => else BROKEN_MARKDOWN_LINK | BROKEN_PROSE_REF
  - N8.TriTier-GateA: CertifyGraphMechanics via [T1:BDCT_And_VisibilityMatrix | T2:FullTreeSHA256_Rollback_And_DryRun | T3:Hypothesis_RuleBasedStateMachine(database=None,derandomize=True)]

[VASCULAR-CIRCUIT :: RSoC DELIVERY, PORT CAPILLARIES, HOMEOSTASIS & COAGULATION]:
  - V1.RSoC-Artery: ContextBoot(URI) => RUN `isai rsoc <URI>` -> Inject[IL-0 + MasterVector + AncestorInvariants + ActiveContract + 1Hop_InterfaceStubs + TagSliced(isai://user, isai://knowledge)] | RawControlPlaneDumpsInPrompt=FORBIDDEN
  - V2.BBB-Visibility: ¬StaticEdge(IL-1|IL-2|isai://tasks -> EPHEMERAL_STAGING) & ¬CrossScopeRef(SUBTREE | INTERNAL) => VISIBILITY_VIOLATION
  - V3.Capillary-Salsa: VerifyPortSchemas[BROKEN_PORT_SCHEMA | INCOMPATIBLE_PORT_WIRING] | interface_digest := SHA256(ports + canonical_model_json_schema(schema_refs) + public_symbols + invariants + transitions) | Unchanged=>Salsa_EarlyCutoff; Changed=>CycleSafe_NHop_BFS
  - V4.Venous-Lifecycle: MultiStepWork => Stage(tasks/TASK-<id>, EPHEMERAL_STAGING) + ISAI-PEP_v1[MaxIter=3, ConditionalResearch, GateA_Before_GateB] -> Promote[KnowledgeCatalogSpec.upsert + Calibrate(isai://user) + Append(isai://root#ChronicleLedger) + HandleCount==0]
  - V5.Hemostasis-Recovery: Writes := .isai_tmp_* + fsync(file) + os.replace + fsync(dir) | CrashOrTornState => RUN `isai recover` (Idempotent: 0_Tx_On_Clean) | MissingVenv => Rehydrate(.venv) or PureLLM_Read(state_snapshot.json + node.py)

[VECTOR-GOVERNANCE :: GOAL-VECTOR MUTATION LEDGER & LIFECYCLE GATES]:
  - VM1.SingleSource: VectorState := deterministic_fold(.isai/vector_ledger.jsonl) | SourceOfTruth := .isai/vector.py -> VISION.md:=projection | SilentProposalDrop=FATAL | AppendOnlyTamper=FATAL
  - VM2.ProposalBinding: ∀Proposal: id + Anchor[kind,index] + anchor_fingerprint(SHA256) + base_vector_digest + rationale(>=60ch) + evidence[>=1] + expected_benefit + risk | StaleAnchorApply=FATAL | UnjustifiedCheckbox=FATAL
  - VM3.SignalSource: ConfirmationChannel := OPERATOR_TASK_ONLY (¬self-output) & ∀SignalLine: ¬FencedCode ∧ ¬InlineCode ∧ ¬BlockQuote ∧ ¬EmbeddedProse | Task := standalone_control_line[подтвердить мутации вектора системы + numbers] | CheckboxConsent=FORBIDDEN | LegacyPhrase=REFUSED | SelfConfirmation=FATAL
  - VM4.NumberedRatification: ImplementationRequest := numbered[1..5] mutations(each: anchor + proposed_text + rationale(>=60ch) + evidence + risk) -> BATCH_PROPOSED(base=head) | Task∧numbers => APPLY_EXACTLY_those_ordinals[atomic_compose_against_one_pre-image] | Task∧¬numbers => RatifyVersion(apply_NOTHING) | UnlistedOrdinal=REFUSED | ApplyWithoutConfirm=FATAL | ApplyWithoutLiveDigestChange=FATAL | VersionBump=REQUIRED
  - VM5.ConfirmedBaseline&Decay: ConfirmedVersion := version_of_last_PR(SEALED) | ¬Task => ConfirmedVersion_unchanged ∧ SelectionStartsFromIt | Applied∧¬SEALED => UNRELEASED_RATIFIED_MUTATION=FATAL | DeferWindow=1_prompt | Deferrals>=2 => EXPIRED => ReProposeWithFreshEvidence | OrphanPendingProposal=FATAL | Batch<=5_ranked
  - VM6.DriftDetect: ∀ChangedAnchor: ∃APPLIED(anchor) ∧ contiguous_digest_chain | else UNCONFIRMED_VECTOR_DRIFT=FATAL | RawHandEdit(vector.py)=FORBIDDEN
  - VM7.GateV-PrePR: PrePR => `isai gate verify` over [ROOT | TASKS | KNOWLEDGE | UNIVERSE | TESTS | .isai_Subfolders] | CriticalDeviation => Neutralize -> Return_PrePR -> FullRerun(no_partial) | StatusAssertedInProse=FATAL | Status:=NO_SYSTEMIC_DEVIATION only_by_tool_with_evidence_digest
  - VM8.TurnBoundary: PrePromptGate:=read(operator_task) -> [¬task => HoldConfirmedVersion] ∨ [task∧¬numbers => RatifyVersion + DeferUnselected] ∨ [task∧numbers => Compose -> Apply] -> ApplyGate | PostPromptGate:=AuditVector -> AuditResearchWindow(since_last_APPLIED|BASELINE) -> RankProposals(<=5) -> CheckboxRequest | GateSkipped=FATAL

[TEXT-ENGINEERING :: LLM-NATIVE TEXT OF EVERY SYSTEM FOLDER & FILE]:
  - TE0.LevelLaw: ∀SystemText: L(text):=DecodedBy ∈ {HumanRepr, Machine, Both} -> Signature[L0|L1|L2|L3|L4|L5] | ¬Signature=TE_LEVEL_UNCLASSIFIED=FATAL
  - TE1.CarrierPurity: L1_CANON: str(py)≡DeclarativeData[¬behavioural_prose | ¬multi-clause_narrative] | L2_TRANSCRIPT: Projection≡SHA256_Render(SourceOfTruth)[¬hand-edit | ¬sync_block_drift] | HandEdit(L2)=FATAL
  - TE2.DLT-BPE: CanonLexicon[structured_tokens]: (CamelComposite ∨ SeparatedComposite ∨ DomainAcronym[closed_set]) ∧ ∀Morpheme:[a-z0-9]{2,}(?:[-_][a-z0-9]{2,})* | PhantomToken=FATAL | OpaqueUnicode=FATAL | MixedScriptToken=WARNING
  - TE3.CommandTruth: ∀`isai <cmd>` ∈ SystemText: ResolvableIn(CLI_ast) | PhantomCommand=FATAL | StatusAssertedInProse=FORBIDDEN
  - TE4.FrameLaw: ∀NormativeText(L3|canon): BimodalU[PrimacyHead=priority ∧ mutability ∧ digest | Middle=sectioned_core | RecencyPeak=STOP_tripwires] | ExplanatoryRedundancy=WARNING
  - TE5.SalienceOrder: RuleSequence := safety ∧ mutability ∧ digest ∧ refs -> operational -> explanatory | ∀Section: role∈{DECIDE|EXECUTE|EXPLAIN} | BleedRole=Misplacement
  - TE6.ChronicleRegister: EventText:=ClosedTaxonomy[summary(>=1) + typed_summary{evidence | blast_radius | next_action}] ∧ Freshness[what] + Lineage[why ∧ whence] | HedgingInEvent=FATAL
  - TE7.VerifyCompile: PrePR => `isai gate verify` over TE0..TE6 ∧ ValidateTextOffline via `isai text check` | SilentTextDrift=FATAL

[IMMUNE-MEMORY :: PRECEDENTS & BOTTLENECK WATCH]:
  - Precedents[PREC-01..09]: Prefix586_HashSplit | LiveUTF8_CompileExec_NoPycCollision(PEP3147_mtime_size) | Physical_SymbolBinding | FenceSafe_ProseScan | ModelJsonSchema_CrossProcDeterminism | StripSYNC_FromProseVAET | ExtraBackupPaths_FullRollback | PreImport_ASTGate | VenvRehydrate_Or_SnapshotFallback
  - Bottleneck-Guards[BN-01..06]: SingleWriterDiscipline(Until_OS_Flock) | IncrementalizeIndexAtScale | AtomicSubtreeMoveViaCompose(Scaffold->Migrate->Refactor->Decommission) | BoundHighFanoutRSoC | PreemptRawFileEditsViaThisFrame | AlgedonicCircuitForIL1C

[GOVERNANCE-ROUTING :: HOMEOSTATIC ABSORPTION VS ALGEDONIC AMENDMENT]:
  - Mode-1.Homeostasis(Autonomous): Standard bugs, local retries (iter<=3), and lawful IL-2/IL-3/LinkMutator evolutions -> resolve autonomously via ISAI-PEP_v1 + GateA(`isai audit` & `pytest`).
  - Mode-2.Algedonic-Escalation(Operator-Gated): Confirmed critical deviation from isai://root#GenesisKernel or isai://root#MasterVector, systemic bottleneck breach, 3/3 ISAI-PEP architectural deadlock, or required mutation of IL-1C_NVF -> EXECUTE STRICT 6-STEP SEQUENCE (SkipStep=FATAL):
      1.CONFIRM_DEVIATION[Reproduce + Quantify_Drift_Against_MasterVector_And_Invariants]
      -> 2.WARN_OPERATOR[Surface_Algedonic_Alert: Evidence | ViolatedGoal | BlastRadius]
      -> 3.CONDUCT_DEEP_RESEARCH[Run_MultiSource_Scientific_And_Repository_Investigation]
      -> 4.RECOMMEND_NEUTRALIZATION[Deliver_Ranked_Mechanisms_Patterns_And_Tradeoffs]
      -> 5.SYNTHESIZE_PHASED_TASK[Build_TaskManifest_DAG + ISAI-PEP_v1_TriTier_Gates + RollbackPlan]
      -> 6.AWAIT_OPERATOR_CONFIRMATION[Launch_Task_IFF_Explicit_Operator_Approval==TRUE; else_Hold_IL-1C]

[RECENCY-TRIPWIRES :: HARD EXECUTION GUARD]:
  - STOP-1[IL-0]: Any byte edit in README.md[0:586] or WRITE_LEASE on GenesisKernel => ABORT_EXECUTION.
  - STOP-2[LINKS]: Any manual edit to node.py links/ports/transitions or README SYNC_Block => FREEZE; route via `isai graph` -> `isai link` -> `isai sync`.
  - STOP-3[PROMOTE]: Any task promotion with `isai audit`!=0, `pytest`!=0, or HandleCount!=0 => BLOCK_PROMOTE.
  - STOP-4[AMEND]: Any unapproved mutation of IL-1C_NVF or silent suppression of critical goal drift => HALT; fire Algedonic Step 1->2 immediately.
```

<!-- ISAI:NVF_SYNC:END -->
