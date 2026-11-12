# ISAI Agent Bootloader (`AGENTS.md`)

> **Role:** Thin cross-platform discovery pointer (`ZERO-Redundancy`). Do NOT duplicate rules here.

1. **Tiered Constitutional Stack (`IL-0 >> IL-1C >> IL-1`):**
   - **`IL-0` (Immutable Genesis):** Read lines `1..14` (`586` bytes) of [`README.md`](README.md) (`isai://root#GenesisKernel`). Never alter a single byte.
   - **`IL-1C` (Conditionally-Locked Neuro-Vascular Fundamental):** Read [`FUNDAMENTAL.md`](FUNDAMENTAL.md) or run `.venv/bin/python -m isai nv show` (`isai://root#NeuroVascularFundamental`, `ISAI-NVF/1.0`). Routine edits are `FATAL`; amendments require the strict 6-Step Algedonic Protocol (`isai://root#AlgedonicProtocol`) + explicit Operator confirmation (`RATIFY_FUNDAMENTAL` in `isai://root#ChronicleLedger`).
   - **`IL-1` (Master Vector):** Read [`VISION.md`](VISION.md) (`isai://root#MasterVector`).
2. **Bimodal Graph-Aware Context Compilation (`RSoC v0.2.5`):**
   - With Python runtime: `.venv/bin/python -m isai rsoc <target_uri>` (injects `IL-0` + `IL-1C` Primacy Head, 1-hop `linked_interface_stubs`, and `terminal_execution_guard` Recency Tail).
   - Without Python runtime (Pure-LLM Fallback; if `.venv` is absent, rehydrate via `python3 -m venv .venv && .venv/bin/pip install -q -e ".[dev]"` when permitted): read `README.md`, `FUNDAMENTAL.md`, `VISION.md`, `tasks/.isai/state_snapshot.json`, and target `.isai/node.py`.
3. **Hypergraph Inspection & Motor Surgery (`isai graph` / `isai link`):**
   - Inspect `EAVT/VAET` before mutating: `.venv/bin/python -m isai graph query <uri>`, `can-mutate <uri>`, `affected-tests <uri>`.
   - Mutate links, ports, symbols, and nodes ONLY via `isai://root#LinkInjector`: `.venv/bin/python -m isai link <add|remove|wire-port|unwire-port|refactor|scaffold-node|decommission-node> ... [--dry-run]`.
4. **Execution, Verification & Recovery (`AUDIT -> CONSTRUCT -> CHRONICLE`):**
   - On session boot after any crash/interruption, run `.venv/bin/python -m isai recover` (`isai://tasks#CrashRecoveryService`).
   - Stage multi-step work in `tasks/` (`EPHEMERAL_STAGING`, `ISAI-PEP v1` max 3 iterations, `Gate A` before `Gate B`).
   - Before promoting (`HandleCount == 0`), `.venv/bin/python -m isai sync`, `.venv/bin/python -m isai audit`, and `.venv/bin/pytest -q` must exit `0` with `0` issues.
