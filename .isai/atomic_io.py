"""Crash-safe Atomic File Persistence, Advisory OS Write Locking & Rollback-Safe Multi-File Transactions."""

from __future__ import annotations

import os
import shutil
import tempfile
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]

TEMP_ARTIFACT_PREFIX: str = ".isai_tmp_"
WRITE_LOCK_FILENAME: str = ".isai_write.lock"

_PROCESS_LOCK_STATE = threading.local()


@contextmanager
def repository_write_lock(repo_root: Path) -> Iterator[Path]:
    """
    Re-entrant intra-process + POSIX advisory inter-process mutex (fcntl.flock) on `<repo_root>/.isai/.isai_write.lock`.
    Closes multi-process TOCTOU lost-update windows on state_snapshot.json and multi-file batches (BN-01)
    without ever deadlocking nested hooks inside the same process/thread.
    """
    isai_dir = repo_root.resolve() / ".isai"
    isai_dir.mkdir(parents=True, exist_ok=True)
    lock_path = (isai_dir / WRITE_LOCK_FILENAME).resolve()

    held: dict[Path, tuple[int, int]] = getattr(_PROCESS_LOCK_STATE, "held", None) or {}
    _PROCESS_LOCK_STATE.held = held

    if lock_path in held:
        fd, depth = held[lock_path]
        held[lock_path] = (fd, depth + 1)
        try:
            yield lock_path
        finally:
            cur_fd, cur_depth = held[lock_path]
            held[lock_path] = (cur_fd, cur_depth - 1)
        return

    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        if fcntl is not None:
            fcntl.flock(fd, fcntl.LOCK_EX)
        held[lock_path] = (fd, 1)
        yield lock_path
    finally:
        held.pop(lock_path, None)
        try:
            if fcntl is not None:
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _fsync_directory(dir_path: Path) -> None:
    """Flush directory entry metadata on POSIX filesystems where supported."""
    flags = getattr(os, "O_RDONLY", 0)
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    try:
        dir_fd = os.open(str(dir_path), flags)
    except OSError:
        return
    try:
        os.fsync(dir_fd)
    except OSError:
        pass
    finally:
        os.close(dir_fd)


def atomic_write_bytes(target_path: Path, payload: bytes) -> None:
    """
    Atomically write bytes to target_path via sibling temp file + fsync + os.replace + dir fsync.
    Guarantees target_path never observes a half-written or zero-truncated payload on crash.
    """
    parent = target_path.parent
    parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f"{TEMP_ARTIFACT_PREFIX}{os.getpid()}_",
        dir=str(parent),
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(tmp_path), str(target_path))
        _fsync_directory(parent)
    except BaseException:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


def atomic_write_text(target_path: Path, text: str, encoding: str = "utf-8") -> None:
    """Atomically write UTF-8 text to target_path."""
    atomic_write_bytes(target_path, text.encode(encoding))


def _snapshot_tree_files(path: Path) -> dict[Path, bytes]:
    """Capture all file bytes under a file or directory prior to deletion."""
    saved: dict[Path, bytes] = {}
    if path.is_file():
        saved[path] = path.read_bytes()
    elif path.is_dir():
        for item in path.rglob("*"):
            if item.is_file():
                saved[item] = item.read_bytes()
    return saved


def atomic_transaction_batch(
    writes: dict[Path, bytes],
    deletes: tuple[Path, ...] = (),
    post_commit_hook: Callable[[], None] | None = None,
    extra_backup_paths: tuple[Path, ...] = (),
    lock_root: Path | None = None,
) -> None:
    """
    Execute a multi-file write/delete batch with full in-memory pre-image capture.
    If lock_root is provided, acquires the re-entrant POSIX advisory lock first.
    If any write, delete, or post_commit_hook raises, every modified or deleted file
    is restored byte-for-byte and newly created files/directories are removed.
    """

    def _run_unlocked() -> None:
        resolved_writes = {p.resolve(): data for p, data in writes.items()}
        resolved_deletes = tuple(p.resolve() for p in deletes)
        resolved_extras = tuple(p.resolve() for p in extra_backup_paths)

        pre_existing: dict[Path, bytes] = {}
        newly_created_files: set[Path] = set()
        newly_created_dirs: list[Path] = []

        for w_path in resolved_writes:
            if w_path.is_file():
                pre_existing[w_path] = w_path.read_bytes()
            else:
                newly_created_files.add(w_path)
                cursor = w_path.parent
                missing_ancestors: list[Path] = []
                while not cursor.exists() and cursor != cursor.parent:
                    missing_ancestors.append(cursor)
                    cursor = cursor.parent
                for anc in reversed(missing_ancestors):
                    if anc not in newly_created_dirs:
                        newly_created_dirs.append(anc)

        for d_path in resolved_deletes:
            for f_path, f_bytes in _snapshot_tree_files(d_path).items():
                pre_existing.setdefault(f_path, f_bytes)

        for e_path in resolved_extras:
            if e_path.is_file():
                pre_existing.setdefault(e_path, e_path.read_bytes())
            elif not e_path.exists():
                newly_created_files.add(e_path)

        try:
            for w_path, payload in resolved_writes.items():
                atomic_write_bytes(w_path, payload)
            for d_path in resolved_deletes:
                if d_path.is_dir():
                    shutil.rmtree(d_path)
                elif d_path.exists():
                    d_path.unlink()
            if post_commit_hook is not None:
                post_commit_hook()
        except BaseException:
            for new_f in newly_created_files:
                if new_f.exists():
                    try:
                        new_f.unlink()
                    except OSError:
                        pass
            for new_d in reversed(newly_created_dirs):
                if new_d.is_dir():
                    try:
                        shutil.rmtree(new_d)
                    except OSError:
                        pass
            for orig_path, orig_bytes in pre_existing.items():
                atomic_write_bytes(orig_path, orig_bytes)
            raise

    if lock_root is not None:
        with repository_write_lock(lock_root):
            _run_unlocked()
    else:
        _run_unlocked()
