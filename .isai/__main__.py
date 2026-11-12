"""CLI Entrypoint for ISyncAI (ISAI v0.2.5): audit | sync | recover | rsoc | nv | graph | link."""

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
from isai.graph_index import build_hypergraph_index, load_repo_nvf
from isai.link_mutator import LinkMutator


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

    sub.add_parser("audit", help="Run full 360° Ring 0..3 contract, IL-1C ratification, wiring & link audit")
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
