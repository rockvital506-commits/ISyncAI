"""Shared sandbox helper: clone the live repository into a quiescent, byte-clean test workspace."""

from __future__ import annotations

import shutil
from pathlib import Path

from isai.constitution import DEFAULT_BOUNDARY_IGNORE


def is_staging_task_dir(name: str) -> bool:
    """Return True for an ephemeral staging task directory (`tasks/TASK-<id>`)."""
    return name.startswith("TASK-")


def quiesce_staging(dest: Path) -> None:
    """
    Detach in-flight staging tasks from a cloned sandbox.

    The live repository may legitimately carry an in-flight `tasks/TASK-<id>` node registered in
    `active_tasks`. A sandbox must start from the canonical five-hive topology so that every audit,
    recovery and mutation test observes exactly one variable: the fault it injects.
    """
    tasks_dir = dest / "tasks"
    if tasks_dir.is_dir():
        for child in sorted(tasks_dir.iterdir()):
            if child.is_dir() and is_staging_task_dir(child.name):
                shutil.rmtree(child, ignore_errors=True)
    snapshot_path = tasks_dir / ".isai" / "state_snapshot.json"
    if not snapshot_path.is_file():
        return
    from isai.atomic_io import atomic_write_text
    from isai.engine import build_clean_snapshot, read_chronicle

    events = read_chronicle(dest)
    revision = events[-1].revision if events else 0
    snapshot = build_clean_snapshot(dest, revision=revision, audit_status="VALID")
    atomic_write_text(snapshot_path, snapshot.model_dump_json(indent=2) + "\n")


def clone_repository(repo_root: Path, dest: Path) -> Path:
    """Copy the live repository (minus runtime artifacts) into `dest` and quiesce staging."""

    def _ignore(dir_str: str, names: list[str]) -> set[str]:
        rel_dir = Path(dir_str).resolve().relative_to(repo_root)
        ignored: set[str] = set()
        for name in names:
            cand = Path(name) if rel_dir == Path(".") else rel_dir / name
            if DEFAULT_BOUNDARY_IGNORE.is_ignored(cand):
                ignored.add(name)
        return ignored

    shutil.copytree(repo_root, dest, ignore=_ignore)
    quiesce_staging(dest)
    return dest
