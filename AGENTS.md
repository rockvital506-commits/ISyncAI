# ISAI Agent Bootloader (`AGENTS.md`)

> **Role:** Thin cross-platform discovery pointer (`ZERO-Redundancy`). Do NOT duplicate rules here.

1. **Tiered Constitutional Stack (`IL-0 >> IL-1C >> IL-1`):**
   - **`IL-0` (Immutable Genesis):** Read lines `1..14` (`586` bytes) of [`README.md`](README.md) (`isai://root#GenesisKernel`). Never alter a single byte.
   - **`IL-1C` (Conditionally-Locked Neuro-Vascular Fundamental):** Read [`FUNDAMENTAL.md`](FUNDAMENTAL.md) or run `.venv/bin/python -m isai nv show` (`isai://root#NeuroVascularFundamental`, `ISAI-NVF/1.2`). Routine edits are `FATAL`; amendments require the strict 6-Step Algedonic Protocol (`isai://root#AlgedonicProtocol`) + explicit Operator confirmation (`RATIFY_FUNDAMENTAL` in `isai://root#ChronicleLedger`).
   - **`IL-1` (Master Vector):** Read [`VISION.md`](VISION.md) (`isai://root#MasterVector`).
2. **Bimodal Graph-Aware Context Compilation (`RSoC v0.2.5`):**
   - With Python runtime: `.venv/bin/python -m isai rsoc <target_uri>` (injects `IL-0` + `IL-1C` Primacy Head, 1-hop `linked_interface_stubs`, and `terminal_execution_guard` Recency Tail).
   - Without Python runtime (Pure-LLM Fallback; if `.venv` is absent, rehydrate via `python3 -m venv .venv && .venv/bin/pip install -q -e ".[dev]"` when permitted): read `README.md`, `FUNDAMENTAL.md`, `VISION.md`, `tasks/.isai/state_snapshot.json`, and target `.isai/node.py`.
3. **Hypergraph Inspection & Motor Surgery (`isai graph` / `isai link`):**
   - Inspect `EAVT/VAET` before mutating: `.venv/bin/python -m isai graph query <uri>`, `can-mutate <uri>`, `affected-tests <uri>`.
   - Mutate links, ports, symbols, and nodes ONLY via `isai://root#LinkInjector`: `.venv/bin/python -m isai link <add|remove|wire-port|unwire-port|refactor|scaffold-node|decommission-node> ... [--dry-run]`.
4. **Master Vector Governance (`[VECTOR-GOVERNANCE]` VM1..VM8, `ISAI-NVF v1.2`):**
   - The goal vector is never hand-edited: `.venv/bin/python -m isai vector audit` (state), `vector propose` (one structured, justified mutation), `vector batch` (register the **numbered** implementation request), `vector seal --pr <ref>` (pin the confirmed version to the last PR).
   - **Implementation request:** a *numbered* list of at most `5` promising mutations, each with anchor, exact text, justification and evidence. There are no checkboxes: numbering is the only consent surface.
   - **Before every prompt:** read the previous response for the *separate explicit task* `подтвердить мутации вектора системы`. No such task -> the last confirmed version stands and selection proceeds from it. Task without numbers -> the current version is confirmed and **no** mutation is implemented. Task with numbers -> `isai vector signal "<prompt text>"` applies exactly those mutations atomically.
   - **After every prompt:** audit the vector and the research since the last applied mutation, then offer the next numbered batch from the confirmed version.
5. **Pre-PR Gate V (`isai://root#SystemHealthGate`):**
   - `.venv/bin/python -m isai gate verify` must report `NO_SYSTEMIC_DEVIATION`. The status is produced only by the tool (with an evidence `SHA-256`), never asserted in prose.
   - On `DEVIATION_DETECTED`: design a neutralisation strategy, implement it, then restart the whole pre-PR sequence from the beginning.
6. **Text Engineering (`[TEXT-ENGINEERING]` TE0..TE7, `ISAI-NVF v1.2`):**
   - Every text of every system folder and file is signed by an `L0..L5` level (`isai text levels`) and must pass `.venv/bin/python -m isai text check`.
   - Never hand-edit a synchronised projection (`FUNDAMENTAL.md`, `VISION.md`, a `README.md` passport): it is an `L2` transcript, so project it with `isai sync`.
   - Never name a CLI command the tool does not declare (`TE3`), never invent a CamelComposite token in a rule (`TE2`), never hedge an event summary (`TE6`).
7. **Execution, Verification & Recovery (`AUDIT -> CONSTRUCT -> CHRONICLE`):**
   - On session boot after any crash/interruption, run `.venv/bin/python -m isai recover` (`isai://tasks#CrashRecoveryService`).
   - Stage multi-step work in `tasks/` (`EPHEMERAL_STAGING`, `ISAI-PEP v1` max 3 iterations, `Gate A` before `Gate B`).
   - Before promoting (`HandleCount == 0`): `isai gate verify` (clean), `isai sync`, `isai audit`, and `pytest -q` must all exit `0` with `0` issues.
