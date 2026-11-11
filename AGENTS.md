# ISAI Agent Bootloader (`AGENTS.md`)

> **Role:** Thin cross-platform discovery pointer (`ZERO-Redundancy`). Do NOT duplicate rules here.

1. **Constitutional Priority (`IL-0`):** Read the first 14 lines of [`README.md`](README.md) (`THIS-FRAME >> ALL-SUBSEQUENT`) and [`VISION.md`](VISION.md) (`isai://root#MasterVector`). Never alter bytes `0..586` of `README.md`.
2. **Context Compilation (`RSoC`):** Before acting on any scope, compile the minimal working set instead of loading all files:
   - With Python runtime: `.venv/bin/python -m isai rsoc <target_uri>` (e.g., `isai://root`, `isai://tasks`).
   - Without Python runtime (Pure-LLM Fallback): read `tasks/.isai/state_snapshot.json` and the `.isai/node.py` of your target folder.
3. **Execution Pipeline (`AUDIT -> CONSTRUCT -> CHRONICLE`):**
   - Stage multi-step work and research in `tasks/` using the `ISAI-PEP v1` loop (`isai.protocol.PhaseExecutionState`, max 3 iterations, Dual-Gate verification).
   - Every directory must maintain semantic parity between `README.md` (Human) and `.isai/node.py` (Agent).
   - After changes, run `.venv/bin/python -m isai sync` and `.venv/bin/python -m isai audit` (must exit `0` with `0` issues).
