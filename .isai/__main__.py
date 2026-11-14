"""CLI Entrypoint for ISyncAI (ISAI v0.3.0): audit | sync | recover | rsoc | nv | vector | text | gate | graph | link."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from isai.contracts import EdgeKind, RSoCDeliveryPolicy
from isai.engine import (
    audit_repository,
    compile_rsoc,
    load_module_attr,
    read_chronicle,
    sync_repository,
)
from isai.graph_index import build_hypergraph_index, load_repo_master_vector, load_repo_nvf
from isai.health_checks import evaluate_gate_v
from isai.link_mutator import LinkMutator
from isai.protocol import utc_now_iso
from isai.vector_ledger import (
    CONFIRM_TASK_ANCHOR_FORMS,
    VectorMutationLedger,
    VectorMutationProposal,
    apply_confirmed_proposal,
    evaluate_ledger_deviations,
    parse_operator_signal,
    render_numbered_mutations,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="isai",
        description="ISyncAI (ISAI v0.2.5) Hypergraph Gatekeeper, IL-1C NVF, Link Injector, RSoC & Crash Recovery",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="Repository root directory (default: current directory)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("audit", help="Run full 360° Ring 0..3 contract, IL-1C ratification, vector ledger, wiring & link audit")
    sub.add_parser("sync", help="Atomically project .isai/ contracts into README.md, FUNDAMENTAL.md, and VISION.md")

    rec_p = sub.add_parser("recover", help="Run deterministic Watchdog Crash Recovery")
    rec_p.add_argument(
        "--abort-active",
        action="store_true",
        help="Force-abort even non-expired active tasks during recovery",
    )

    rsoc_p = sub.add_parser("rsoc", help="Compile bimodal Resultant Set of Context (RSoC v0.2.5)")
    rsoc_p.add_argument("uri", type=str, help="Target EntityRef URI (e.g., isai://root or isai://tests)")
    rsoc_p.add_argument(
        "--tag",
        action="append",
        default=[],
        help="Optional domain tag filter for /user and /knowledge slicing",
    )

    # 'isai nv' subcommands
    nv_p = sub.add_parser("nv", help="Inspect or verify Ring IL-1C Neuro-Vascular Fundamental (ISAI-NVF)")
    nv_sub = nv_p.add_subparsers(dest="nv_cmd", required=True)
    nv_sub.add_parser("show", help="Emit exact lossless symbolic ISAI-NVF DSL frame")
    nv_sub.add_parser("verify", help="Verify IL-1C digest against FUNDAMENTAL.md and Chronicle ratification")

    # 'isai vector' subcommands (ISAI-NVF v1.1 [VECTOR-GOVERNANCE])
    vec_p = sub.add_parser("vector", help="Audit, propose, ratify and apply Master Vector mutations")
    vec_sub = vec_p.add_subparsers(dest="vector_cmd", required=True)

    vec_sub.add_parser("init", help="Anchor the append-only vector mutation ledger (idempotent)")
    vec_sub.add_parser("audit", help="Audit vector ledger chain, drift, numbered batches and confirmations")
    vec_sub.add_parser("pending", help="Render the numbered implementation request for pending proposals")

    vbt = vec_sub.add_parser("batch", help="Register (or refresh) the numbered implementation request over pending proposals")
    vbt.add_argument(
        "--id",
        dest="proposal_ids",
        action="append",
        default=[],
        help="Proposal id to include; the n-th --id becomes mutation number n (default: all pending, ranked by risk)",
    )

    vseal = vec_sub.add_parser("seal", help="Seal the live vector as the confirmed version of the last pull request")
    vseal.add_argument("--pr", required=True, type=str, help="Pull-request reference (e.g. #3 or a PR URL)")
    vseal.add_argument("--note", default=None, type=str)

    vpr = vec_sub.add_parser("propose", help="Register a structured vector mutation proposal")
    vpr.add_argument("--anchor-kind", required=True, type=str)
    vpr.add_argument("--anchor-index", default=0, type=int)
    vpr.add_argument("--anchor-label", required=True, type=str)
    vpr.add_argument("--mutation-kind", required=True, choices=("ADD", "EDIT", "REMOVE"))
    vpr.add_argument("--proposed-text", required=True, type=str)
    vpr.add_argument("--rationale", required=True, type=str)
    vpr.add_argument("--evidence", action="append", default=[], type=str)
    vpr.add_argument("--expected-benefit", required=True, type=str)
    vpr.add_argument("--risk", default="LOW", choices=("LOW", "MEDIUM", "HIGH"))

    vsig = vec_sub.add_parser("signal", help="Ingest one operator prompt and apply the VM3/VM4 decision table")
    vsig.add_argument("prompt_text", nargs="+", type=str)
    vsig.add_argument("--note", default=None, type=str)

    vap = vec_sub.add_parser("apply", help="Record a confirmed, already-materialised vector mutation")
    vap.add_argument("proposal_id", type=str)
    vap.add_argument("--summary", required=True, type=str)

    vec_sub.add_parser("expire", help="Expire pending proposals that exhausted their deferral window")

    vrev = vec_sub.add_parser(
        "review",
        help="Execute the VM8 PostPromptGate: audit vector, open the research window, rank proposals",
    )
    vrev.add_argument(
        "--since",
        default=None,
        type=str,
        help="Research window start (ISO-8601 or 'baseline'). Default: last APPLIED mutation or baseline.",
    )
    vrev.add_argument("--max-proposals", default=5, type=int, help="VM4 caps the batch at 5.")
    vrev.add_argument("--json", action="store_true", help="Emit machine-readable output only.")

    # 'isai bio' subcommands (bio-universe lexicon gate)
    bio_p = sub.add_parser("bio", help="Verify the bio-universe lexicon against live symbols")
    bio_sub = bio_p.add_subparsers(dest="bio_cmd", required=True)
    bv = bio_sub.add_parser(
        "validate",
        help="Fail when a bio term names no live symbol or claims kernel maturity from the bench",
    )
    bv.add_argument("--json", action="store_true", help="Emit machine-readable output only.")
    bio_sub.add_parser("lexicon", help="Render the lexicon from its spec (the .md is a projection)")

    # 'isai text' subcommands (ISAI-NVF v1.2 [TEXT-ENGINEERING] TE0..TE7)
    text_p = sub.add_parser("text", help="Read every system text offline and verify LLM-native engineering")
    text_sub = text_p.add_subparsers(dest="text_cmd", required=True)
    text_sub.add_parser("check", help="Verify TE0..TE6 duties across every system folder and file")
    text_sub.add_parser("levels", help="Emit the TE0 level inventory (signature -> files)")
    text_sub.add_parser("packet", help="Emit the compact [TEXT-ENGINEERING] RSoC slice")

    # 'isai gate' subcommands (Pre-PR Gate V system health)
    gate_p = sub.add_parser("gate", help="Run the pre-PR Gate V system health verification")
    gate_sub = gate_p.add_subparsers(dest="gate_cmd", required=True)
    gate_sub.add_parser("verify", help="Execute Gate V across root, tasks, knowledge, universe, tests & .isai subfolders")

    # 'isai graph' subcommands
    graph_p = sub.add_parser("graph", help="Query EAVT/VAET bidirectional hypergraph index")
    graph_sub = graph_p.add_subparsers(dest="graph_cmd", required=True)

    gq_p = graph_sub.add_parser("query", help="Query forward (EAVT) and/or reverse (VAET) edges")
    gq_p.add_argument("uri", type=str, help="EntityRef URI to inspect")
    gq_p.add_argument(
        "--direction",
        choices=("forward", "reverse", "both"),
        default="both",
        help="Edge traversal direction (default: both)",
    )

    gcm_p = graph_sub.add_parser("can-mutate", help="Run preflight VAET reverse-dependency safety check")
    gcm_p.add_argument("uri", type=str, help="Target EntityRef URI")
    gcm_p.add_argument(
        "--op",
        choices=("decommission", "remove_symbol", "mutate_interface"),
        default="decommission",
    )

    gat_p = graph_sub.add_parser("affected-tests", help="Select affected cross-tests via VAET closure")
    gat_p.add_argument("uris", nargs="+", type=str, help="One or more mutated EntityRef URIs")

    # 'isai link' subcommands
    link_p = sub.add_parser("link", help="Transactional AST link injector, port wirer & refactorer")
    link_sub = link_p.add_subparsers(dest="link_cmd", required=True)

    la_p = link_sub.add_parser("add", help="Inject a typed EdgeLinkSpec")
    la_p.add_argument("source_uri", type=str)
    la_p.add_argument("target_uri", type=str)
    la_p.add_argument("--kind", choices=[e.value for e in EdgeKind], default=EdgeKind.CONSUMES_CONTRACT.value)
    la_p.add_argument(
        "--rsoc",
        choices=[p.value for p in RSoCDeliveryPolicy],
        default=RSoCDeliveryPolicy.INTERFACE_STUB.value,
    )
    la_p.add_argument("--rationale", type=str, default=None)
    la_p.add_argument("--dry-run", action="store_true")

    lr_p = link_sub.add_parser("remove", help="Remove an EdgeLinkSpec")
    lr_p.add_argument("source_uri", type=str)
    lr_p.add_argument("target_uri", type=str)
    lr_p.add_argument("--kind", choices=[e.value for e in EdgeKind], default=None)
    lr_p.add_argument("--dry-run", action="store_true")

    lwp_p = link_sub.add_parser("wire-port", help="Bind a consumer input port to a producer output port")
    lwp_p.add_argument("consumer_uri", type=str)
    lwp_p.add_argument("input_port", type=str)
    lwp_p.add_argument("producer_uri", type=str)
    lwp_p.add_argument("output_port", type=str)
    lwp_p.add_argument("--rationale", type=str, default=None)
    lwp_p.add_argument("--dry-run", action="store_true")

    luw_p = link_sub.add_parser("unwire-port", help="Disconnect a PortWiringSpec")
    luw_p.add_argument("consumer_uri", type=str)
    luw_p.add_argument("input_port", type=str)
    luw_p.add_argument("--producer", type=str, default=None)
    luw_p.add_argument("--dry-run", action="store_true")

    lref_p = link_sub.add_parser("refactor", help="Atomically rename #Symbol or retarget EntityRef")
    lref_p.add_argument("old_uri", type=str)
    lref_p.add_argument("new_uri", type=str)
    lref_p.add_argument("--dry-run", action="store_true")

    lsc_p = link_sub.add_parser("scaffold-node", help="Create a synchronized Fractal Directory Object")
    lsc_p.add_argument("rel_path", type=str)
    lsc_p.add_argument("--title", required=True, type=str)
    lsc_p.add_argument("--goal", required=True, type=str)
    lsc_p.add_argument("--dry-run", action="store_true")

    ldec_p = link_sub.add_parser("decommission-node", help="Safely remove a leaf node if VAET is clear")
    ldec_p.add_argument("node_uri", type=str)
    ldec_p.add_argument("--dry-run", action="store_true")

    args = parser.parse_args(argv)
    repo_root = args.root.resolve()

    if args.command == "sync":
        report = sync_repository(repo_root)
        print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
        return 0

    if args.command == "audit":
        report = audit_repository(repo_root)
        print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
        return 0 if report.valid else 1

    if args.command == "recover":
        recover_fn = load_module_attr(
            repo_root / "tasks" / ".isai" / "watchdog.py",
            "_isai_cli_watchdog",
            "recover_repository",
        )
        rec_report = recover_fn(repo_root, abort_all_active=bool(args.abort_active))
        print(json.dumps(rec_report.model_dump(mode="json"), ensure_ascii=False, indent=2))
        return 0

    if args.command == "rsoc":
        packet = compile_rsoc(repo_root, args.uri, focus_tags=tuple(args.tag))
        print(json.dumps(packet, ensure_ascii=False, indent=2))
        return 0

    if args.command == "nv":
        nvf = load_repo_nvf(repo_root)
        if args.nv_cmd == "show":
            sys.stdout.write(nvf.render_dsl())
            return 0
        if args.nv_cmd == "verify":
            events = read_chronicle(repo_root)
            ratify = [e for e in events if e.operation == "RATIFY_FUNDAMENTAL"]
            latest = ratify[-1] if ratify else None
            live_sha = nvf.dsl_sha256()
            ratified_ok = bool(
                latest is not None
                and latest.operator_approved
                and latest.ratified_nvf_digest == live_sha
            )
            payload = {
                "fundamental_id": nvf.fundamental_id,
                "frame_id": nvf.frame_id,
                "tier": nvf.tier.value,
                "dsl_sha256": live_sha,
                "spec_digest": nvf.spec_digest(),
                "ratified_in_chronicle": ratified_ok,
                "latest_ratification_tx": latest.tx_id if latest else None,
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0 if ratified_ok else 1

    if args.command == "vector":
        vector = load_repo_master_vector(repo_root)
        ledger = VectorMutationLedger(repo_root)
        if args.vector_cmd == "init":
            if ledger.is_initialized():
                print(json.dumps({"initialized": False, "reason": "ledger already anchored"}, indent=2))
                return 0
            event = ledger.initialize(vector, note="Genesis anchor of the vector mutation ledger.")
            print(json.dumps(event.model_dump(mode="json"), ensure_ascii=False, indent=2))
            return 0
        if args.vector_cmd == "audit":
            state = ledger.state() if ledger.path.is_file() else None
            payload: dict[str, object] = {
                "ledger_initialized": bool(state and state.baseline_digest),
                "events_count": state.events_count if state else 0,
                "applied_mutations": [dict(item) for item in (state.applied if state else ())],
                "pending": [p.proposal_id for p in (state.pending() if state else ())],
                "confirmed": [p.proposal_id for p in (state.confirmed() if state else ())],
                "deviations": [
                    d.model_dump(mode="json")
                    for d in (evaluate_ledger_deviations(state, vector) if state else ())
                ],
                "master_vector_version": vector.version,
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0
        if args.vector_cmd == "pending":
            from isai.vector_ledger import render_numbered_mutations as _render

            state = ledger.state()
            batch = state.latest_batch()
            members = state.batch_members(batch.batch_id) if batch else state.pending()
            print(_render(members, batch=batch) if members else "")
            if state.confirmed_version_digest() is not None:
                print(
                    json.dumps(
                        {
                            "confirmed_version": vector.version
                            if state.confirmed_version_digest() == vector.spec_digest()
                            else state.last_sealed_version or state.baseline_version,
                            "sealed_pr_ref": state.last_sealed_pr_ref,
                            "unreleased_mutations": [i["proposal_id"] for i in state.unreleased_mutations()],
                            "confirmation_task_anchor": CONFIRM_TASK_ANCHOR_FORMS[0],
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
            return 0

        if args.vector_cmd == "batch":
            from isai.vector_ledger import MAX_BATCH_SIZE

            state = ledger.state()
            head = state.ledger_head()
            if args.proposal_ids:
                chosen = tuple(args.proposal_ids)
            else:
                ranking = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
                chosen = tuple(
                    p.proposal_id
                    for p in sorted(
                        state.pending(),
                        key=lambda p: (ranking[p.risk_level.value], p.proposal_id),
                    )[:MAX_BATCH_SIZE]
                )
            if not chosen:
                print(json.dumps({"batch": None, "reason": "no pending proposals"}, ensure_ascii=False, indent=2))
                return 0
            event = ledger.open_batch(chosen, base_vector_digest=head or "")
            print(json.dumps(event.model_dump(mode="json"), ensure_ascii=False, indent=2))
            print(render_numbered_mutations(state.batch_members(event.batch.batch_id), batch=event.batch))
            return 0

        if args.vector_cmd == "seal":
            event = ledger.seal(vector, pr_ref=args.pr)
            print(json.dumps(event.model_dump(mode="json"), ensure_ascii=False, indent=2))
            return 0
        if args.vector_cmd == "propose":
            from isai.vector_ledger import VectorAnchorKind, anchor_fingerprint, MutationKind

            state = ledger.state()
            kind = VectorAnchorKind(args.anchor_kind)
            head = state.applied[-1]["after"] if state.applied else state.baseline_digest
            proposal = VectorMutationProposal(
                proposal_id=state.next_proposal_id(),
                anchor_kind=kind,
                anchor_index=args.anchor_index,
                anchor_label=args.anchor_label,
                mutation_kind=MutationKind(args.mutation_kind),
                proposed_text=args.proposed_text,
                rationale=args.rationale,
                evidence_refs=tuple(args.evidence),
                expected_benefit=args.expected_benefit,
                risk_level=args.risk,
                anchor_fingerprint=anchor_fingerprint(vector, kind, args.anchor_index),
                base_vector_digest=head or "",
                created_at_utc=utc_now_iso(),
            )
            ledger.propose(proposal)
            print(json.dumps(proposal.model_dump(mode="json"), ensure_ascii=False, indent=2))
            return 0
        if args.vector_cmd == "signal":
            signal = parse_operator_signal(" ".join(args.prompt_text))
            result = ledger.ingest_operator_signal(signal, vector, note=args.note)
            print(json.dumps({"signal": signal.model_dump(mode="json"), **result}, ensure_ascii=False, indent=2))
            return 0
        if args.vector_cmd == "apply":
            outcome = apply_confirmed_proposal(repo_root, args.proposal_id, vector, summary=args.summary)
            print(json.dumps(outcome.model_dump(mode="json"), ensure_ascii=False, indent=2))
            return 0 if outcome.applied else 1
        if args.vector_cmd == "review":
            from isai.vector_ledger import run_post_prompt_gate

            state = ledger.state()
            gate = run_post_prompt_gate(
                repo_root=repo_root,
                ledger=ledger,
                vector=vector,
                state=state,
                since=args.since,
                max_proposals=args.max_proposals,
            )
            print(json.dumps(gate, ensure_ascii=False, indent=2))
            return 0 if gate["gate_status"] == "PASS" else 1
        if args.vector_cmd == "expire":
            state = ledger.state()
            expired = [
                p.proposal_id
                for p in state.pending()
                if (state.deferrals or {}).get(p.proposal_id, 0) >= 2
            ]
            for pid in expired:
                ledger.expire(pid, note="Deferral decay exceeded (VM5).")
            print(json.dumps({"expired": expired}, ensure_ascii=False, indent=2))
            return 0

    if args.command == "bio":
        lexicon_dir = repo_root / "research" / ".isai"
        if str(lexicon_dir) not in sys.path:
            sys.path.insert(0, str(lexicon_dir))
        from bio_lexicon import BIO_LEXICON, render_lexicon_markdown, validate_lexicon
        if args.bio_cmd == "lexicon":
            print(render_lexicon_markdown(BIO_LEXICON))
            return 0
        findings = validate_lexicon(repo_root, BIO_LEXICON)
        failures = [f for f in findings if not f.passed]
        payload = {
            "lexicon_ref": BIO_LEXICON.lexicon_ref,
            "terms": len(BIO_LEXICON.entries),
            "checks": len(findings),
            "failures": len(failures),
            "status": "BIO_VALID" if not failures else "BIO_DEVIATION_DETECTED",
            "findings": [
                {
                    "check": f.check,
                    "severity": f.severity,
                    "passed": f.passed,
                    "term": f.term,
                    "message": f.message,
                }
                for f in findings
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if not failures else 1
    if args.command == "text":
        from isai.text_engineering import level_inventory, text_engineering_packet, validate_text

        if args.text_cmd == "check":
            report = validate_text(repo_root)
            print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
            return 0 if report.valid else 1
        if args.text_cmd == "levels":
            print(json.dumps(level_inventory(repo_root), ensure_ascii=False, indent=2))
            return 0
        if args.text_cmd == "packet":
            print(json.dumps(text_engineering_packet(), ensure_ascii=False, indent=2))
            return 0

    if args.command == "gate":
        report = evaluate_gate_v(repo_root)
        print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
        return 0 if report.status == "NO_SYSTEMIC_DEVIATION" else 1

    if args.command == "graph":
        idx = build_hypergraph_index(repo_root)
        if args.graph_cmd == "query":
            payload: dict[str, object] = {"uri": args.uri}
            if args.direction in ("forward", "both"):
                payload["forward_eavt"] = [e.model_dump(mode="json") for e in idx.outbound_of(args.uri)]
            if args.direction in ("reverse", "both"):
                payload["reverse_vaet"] = [e.model_dump(mode="json") for e in idx.inbound_to(args.uri)]
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0
        if args.graph_cmd == "can-mutate":
            rep = idx.can_mutate(args.uri, operation=args.op)
            print(json.dumps(rep.model_dump(mode="json"), ensure_ascii=False, indent=2))
            return 0 if rep.safe_without_cascade else 1
        if args.graph_cmd == "affected-tests":
            res = idx.select_affected_tests(tuple(args.uris))
            print(json.dumps(res, ensure_ascii=False, indent=2))
            return 0

    if args.command == "link":
        mutator = LinkMutator(repo_root)
        try:
            if args.link_cmd == "add":
                plan = mutator.add_link(
                    args.source_uri,
                    args.target_uri,
                    kind=EdgeKind(args.kind),
                    rsoc_delivery=RSoCDeliveryPolicy(args.rsoc),
                    rationale=args.rationale,
                    dry_run=bool(args.dry_run),
                )
            elif args.link_cmd == "remove":
                plan = mutator.remove_link(
                    args.source_uri,
                    args.target_uri,
                    kind=EdgeKind(args.kind) if args.kind else None,
                    dry_run=bool(args.dry_run),
                )
            elif args.link_cmd == "wire-port":
                plan = mutator.wire_port(
                    args.consumer_uri,
                    args.input_port,
                    args.producer_uri,
                    args.output_port,
                    rationale=args.rationale,
                    dry_run=bool(args.dry_run),
                )
            elif args.link_cmd == "unwire-port":
                plan = mutator.unwire_port(
                    args.consumer_uri,
                    args.input_port,
                    producer_uri=args.producer,
                    dry_run=bool(args.dry_run),
                )
            elif args.link_cmd == "refactor":
                plan = mutator.refactor_entity_ref(
                    args.old_uri,
                    args.new_uri,
                    dry_run=bool(args.dry_run),
                )
            elif args.link_cmd == "scaffold-node":
                plan = mutator.scaffold_node(
                    args.rel_path,
                    title=args.title,
                    goal=args.goal,
                    dry_run=bool(args.dry_run),
                )
            elif args.link_cmd == "decommission-node":
                plan = mutator.decommission_node(
                    args.node_uri,
                    dry_run=bool(args.dry_run),
                )
            else:
                return 2
            print(json.dumps(plan.model_dump(mode="json"), ensure_ascii=False, indent=2))
            return 0
        except Exception as exc:
            print(
                json.dumps({"accepted": False, "error": str(exc)}, ensure_ascii=False, indent=2)
            )
            return 1

    return 2


if __name__ == "__main__":
    sys.exit(main())
