"""Ring 0 Genesis Constitution, Integrity Rings, and Filesystem Boundary Rules."""

from __future__ import annotations

import hashlib
from enum import StrEnum
from pathlib import Path
from pydantic import BaseModel, ConfigDict

GENESIS_TEXT: str = (
    "# ISyncAI\n"
    "Синхронизация пользователя и ИИ агента\n"
    "\n"
    "[USER-IDENTITY→MODEL-SYNC]: FiduSys-Novator & Chronitect\n"
    "[META-PRIORITY]: THIS-FRAME >> ALL-SUBSEQUENT\n"
    "[CORE-MANDATE]: High-Fiduciary Architecture Engine | ZERO-Redundancy\n"
    "\n"
    "[AXIOMS]:\n"
    "  - DRY-Fidelity[atomic | DRY | modular | reusable]\n"
    "  - Chrono-Graph[versioning | immutable-log | state-tracking]\n"
    "  - Hierar-Logic[top-down-topology | explicit-mapping | zero-orphan-nodes]\n"
    "\n"
    "[OPERATIONAL-PIPELINE]: AUDIT → CONSTRUCT → CHRONICLE\n"
    "[EXECUTION-POLICY]: Order=Absolute | Logic=Linear | Redundancy=FATAL\n"
)

GENESIS_BYTE_LENGTH: int = 586
GENESIS_LINE_COUNT: int = 14
GENESIS_SHA256: str = "4ba8961ae9426294f5b967ade6f5dadf0f648698591317859e8998a5d98482b9"


class IntegrityLevel(StrEnum):
    """Windows MIC-inspired integrity rings protecting ISAI from unauthorized mutation."""

    IL_0_GENESIS = "IL_0_GENESIS"           # Byte-immutable Genesis Frame (never mutates)
    IL_1C_FUNDAMENTAL = "IL_1C_FUNDAMENTAL" # Conditionally-mutable Sub-Genesis Fundamental (6-Step Algedonic + Operator ratification only)
    IL_1_KERNEL = "IL_1_KERNEL"             # Core .isai/ engine & Master Vector (governed evolution)
    IL_2_CANONICAL = "IL_2_CANONICAL"       # Promoted hives (/user, /knowledge, domains) via Watchdog gate
    IL_3_STAGING = "IL_3_STAGING"           # Runtime task arena (/tasks) for active execution & staging


class BoundaryIgnoreSpec(BaseModel):
    """Single source of truth for technical runtime artifacts excluded from topology orphan checks."""

    model_config = ConfigDict(frozen=True)

    ignored_dir_names: tuple[str, ...] = (
        ".git",
        ".venv",
        "__pycache__",
        ".pytest_cache",
        ".hypothesis",
        ".mypy_cache",
        ".ruff_cache",
        "build",
        "dist",
    )
    ignored_dir_suffixes: tuple[str, ...] = (".egg-info",)
    ignored_file_names: tuple[str, ...] = (".isai_write.lock",)
    ignored_file_suffixes: tuple[str, ...] = (".pyc", ".pyo", ".pyd")

    def is_ignored(self, rel_path: Path) -> bool:
        """Return True if any path segment matches an excluded technical boundary."""
        for part in rel_path.parts:
            if part in self.ignored_dir_names:
                return True
            if any(part.endswith(sfx) for sfx in self.ignored_dir_suffixes):
                return True
        if rel_path.name in self.ignored_file_names:
            return True
        if any(rel_path.name.endswith(sfx) for sfx in self.ignored_file_suffixes):
            return True
        return False


DEFAULT_BOUNDARY_IGNORE = BoundaryIgnoreSpec()


class GenesisVerificationResult(BaseModel):
    """Verification outcome for the Ring 0 Genesis header in root README.md."""

    model_config = ConfigDict(frozen=True)

    valid: bool
    actual_sha256: str
    expected_sha256: str = GENESIS_SHA256
    actual_byte_length: int
    detail: str


class GenesisConstitution(BaseModel):
    """Formal representation of the immutable Ring 0 Genesis Frame."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "0.1.0"
    identity_sync: str = "FiduSys-Novator & Chronitect"
    meta_priority: str = "THIS-FRAME >> ALL-SUBSEQUENT"
    core_mandate: str = "High-Fiduciary Architecture Engine | ZERO-Redundancy"
    axioms: tuple[str, ...] = (
        "DRY-Fidelity[atomic | DRY | modular | reusable]",
        "Chrono-Graph[versioning | immutable-log | state-tracking]",
        "Hierar-Logic[top-down-topology | explicit-mapping | zero-orphan-nodes]",
    )
    operational_pipeline: tuple[str, str, str] = ("AUDIT", "CONSTRUCT", "CHRONICLE")
    execution_policy: tuple[str, ...] = (
        "Order=Absolute",
        "Logic=Linear",
        "Redundancy=FATAL",
    )
    expected_sha256: str = GENESIS_SHA256
    expected_byte_length: int = GENESIS_BYTE_LENGTH

    def verify_genesis_header(self, readme_path: Path) -> GenesisVerificationResult:
        """Verify that the first 14 lines (586 bytes) of root README.md are byte-for-byte intact."""
        if not readme_path.is_file():
            return GenesisVerificationResult(
                valid=False,
                actual_sha256="",
                actual_byte_length=0,
                detail=f"Root README.md missing at {readme_path}",
            )
        raw = readme_path.read_bytes()
        prefix = raw[: self.expected_byte_length]
        digest = hashlib.sha256(prefix).hexdigest()
        if len(raw) < self.expected_byte_length:
            return GenesisVerificationResult(
                valid=False,
                actual_sha256=digest,
                actual_byte_length=len(raw),
                detail=(
                    f"README.md shorter than {self.expected_byte_length} bytes "
                    f"(got {len(raw)} bytes)"
                ),
            )
        if digest != self.expected_sha256:
            return GenesisVerificationResult(
                valid=False,
                actual_sha256=digest,
                actual_byte_length=len(prefix),
                detail=(
                    "FATAL IL-0 violation: Genesis header SHA-256 mismatch "
                    f"(expected {self.expected_sha256}, got {digest})"
                ),
            )
        # Ensure line 14 ends cleanly and is not glued to trailing characters on the same line
        lines = prefix.decode("utf-8").splitlines(keepends=True)
        if len(lines) != GENESIS_LINE_COUNT:
            return GenesisVerificationResult(
                valid=False,
                actual_sha256=digest,
                actual_byte_length=len(prefix),
                detail=f"Expected {GENESIS_LINE_COUNT} Genesis lines, got {len(lines)}",
            )
        return GenesisVerificationResult(
            valid=True,
            actual_sha256=digest,
            actual_byte_length=len(prefix),
            detail="Genesis IL-0 frame verified byte-for-byte.",
        )


GENESIS_CONSTITUTION = GenesisConstitution()
