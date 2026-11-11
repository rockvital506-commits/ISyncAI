"""CLI Entrypoint for ISyncAI (ISAI) Kernel: audit | sync | rsoc | status."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from isai.engine import audit_repository, compile_rsoc, sync_repository


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="isai",
        description="ISyncAI (ISAI v0.1) Deterministic Gatekeeper & Context Compiler",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="Repository root directory (default: current directory)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("audit", help="Run full Ring 0..3 topological, digest, and orphan verification")
    sub.add_parser("sync", help="Deterministically project .isai/ contracts into README.md and VISION.md")

    rsoc_p = sub.add_parser("rsoc", help="Compile Resultant Set of Context (RSoC) for a target EntityRef")
    rsoc_p.add_argument("uri", type=str, help="Target EntityRef URI (e.g., isai://root or isai://tasks)")
    rsoc_p.add_argument(
        "--tag",
        action="append",
        default=[],
        help="Optional domain tag filter for /user and /knowledge slicing",
    )

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

    if args.command == "rsoc":
        packet = compile_rsoc(repo_root, args.uri, focus_tags=tuple(args.tag))
        print(json.dumps(packet, ensure_ascii=False, indent=2))
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
