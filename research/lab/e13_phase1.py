"""
E13 — Приёмочный тест Фазы 1: один прогон, одна таблица решений.

Стратегия (`BIO-STRATEGY.md`) утверждает, что каждая фаза заканчивается прогоном мини-системы,
а не самооценкой. Этот файл и есть такой прогон для Фазы 1: он исполняет четыре проверки,
сравнивает результат с заранее объявленными порогами и выносит вердикт по каждой развилке.

Ценность в том, что пороги объявлены **до** измерения и лежат в коде. Если завтра механизм
сломается, тест скажет об этом без перечитывания стратегии.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

REPO = Path(__file__).resolve().parents[2]
RESULTS = REPO / "research" / "results"

#: Пороги объявлены здесь, а не в момент интерпретации (`BIO-STRATEGY.md` §1 P3).
THRESHOLDS = {
    "cache_hit_rate_min": 0.80,
    "cache_stale_allowed": 0,
    "apoptosis_false_kill_max": 0,
    "apoptosis_context_bytes_max": 600,
    "catalog_dangling_max": 0,
    "granularity_law_ratio_min": 1.50,
}


def load(name: str) -> dict:
    p = RESULTS / name
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


def check_cache(e12: dict) -> dict:
    """Развилка 1-B: корректность обязательна, затем максимальный hit_rate."""
    rows = {r["strategy"]: r for r in e12.get("rows", [])}
    correctness = e12.get("correctness", {})
    admissible = {
        name: row
        for name, row in rows.items()
        if not correctness.get(name, {}).get("stale_detected", True)
    }
    if not admissible:
        return {"branch": "1-B", "verdict": "BLOCKED", "reason": "нет корректной стратегии"}
    best = max(admissible, key=lambda n: admissible[n]["hit_rate"])
    ok = admissible[best]["hit_rate"] >= THRESHOLDS["cache_hit_rate_min"]
    return {
        "branch": "1-B",
        "question": "какая стратегия инвалидации кэша допустима",
        "chosen": best,
        "hit_rate": admissible[best]["hit_rate"],
        "threshold": THRESHOLDS["cache_hit_rate_min"],
        "verdict": "PASS" if ok else "FAIL",
        "global_epoch_rank": sorted(
            (n for n in admissible), key=lambda n: -admissible[n]["hit_rate"]
        ).index("GLOBAL_EPOCH")
        + 1
        if "GLOBAL_EPOCH" in admissible
        else None,
        "admissible_count": len(admissible),
    }


def check_apoptosis(e11: dict) -> dict:
    """Развилка 1-C: различение не должно убивать живые гены."""
    summary = e11.get("summary", {})
    disc = summary.get("DISCRIMINATING", {})
    eager = summary.get("EAGER", {})
    if not disc:
        return {"branch": "1-C", "verdict": "BLOCKED", "reason": "нет данных E11"}
    ok = (
        disc["total_false_kill"] <= THRESHOLDS["apoptosis_false_kill_max"]
        and disc["max_context_bytes"] <= THRESHOLDS["apoptosis_context_bytes_max"]
    )
    return {
        "branch": "1-C",
        "question": "убивает ли различающий апоптоз живое",
        "false_kill": disc["total_false_kill"],
        "context_bytes": disc["max_context_bytes"],
        "eager_false_kill": eager.get("total_false_kill"),
        "threshold_false_kill": THRESHOLDS["apoptosis_false_kill_max"],
        "threshold_context_bytes": THRESHOLDS["apoptosis_context_bytes_max"],
        "verdict": "PASS" if ok else "FAIL",
    }


def check_catalog() -> dict:
    """Развилка 1-D: ссылки каталога не битые."""
    from isai.graph_index import build_hypergraph_index, load_module_attr_isolated

    try:
        cat = load_module_attr_isolated(REPO / "knowledge/.isai/catalog.py", "kc", "KNOWLEDGE_CATALOG")
        idx = build_hypergraph_index(REPO)
    except Exception as exc:  # noqa: BLE001 - провал загрузки и есть провал проверки
        return {"branch": "1-D", "verdict": "BLOCKED", "reason": str(exc)[:200]}
    dangling = []
    for e in cat.entries:
        ref = str(e.related_node_ref)
        base = ref.split("#")[0]
        if base not in idx.nodes or (("#" in ref) and ref not in idx.valid_targets):
            dangling.append(e.entry_id)
    ok = len(dangling) <= THRESHOLDS["catalog_dangling_max"]
    return {
        "branch": "1-D",
        "question": "есть ли зомби-записи в каталоге",
        "entries": len(cat.entries),
        "dangling": len(dangling),
        "dangling_ids": dangling[:5],
        "verdict": "PASS" if ok else "FAIL",
    }


def check_granularity(e9: dict) -> dict:
    """Развилка 1-A: подтверждается ли порог 3 SLOC."""
    test = e9.get("precedent_test", {})
    ratio = test.get("meso_over_nano")
    if ratio is None:
        return {"branch": "1-A", "verdict": "BLOCKED", "reason": "нет данных E9"}
    holds = ratio >= THRESHOLDS["granularity_law_ratio_min"]
    return {
        "branch": "1-A",
        "question": "подтверждается ли закон порога 3 SLOC",
        "meso_over_nano": ratio,
        "threshold": THRESHOLDS["granularity_law_ratio_min"],
        "verdict": "PASS" if holds else "REVOKE",
        "action": "применить порог как закон" if holds else "отозвать порог; заменить на признак stub",
    }


def main() -> int:
    decisions = [
        check_granularity(load("e9_granularity.json")),
        check_cache(load("e12_epoch.json")),
        check_apoptosis(load("e11_apoptosis.json")),
        check_catalog(),
    ]
    passed = sum(1 for d in decisions if d["verdict"] in ("PASS", "REVOKE"))
    blocked = [d for d in decisions if d["verdict"] == "BLOCKED"]
    result = {
        "phase": 1,
        "thresholds": THRESHOLDS,
        "decisions": decisions,
        "summary": {
            "branches": len(decisions),
            "resolved": passed,
            "blocked": len(blocked),
            "phase_status": "COMPLETE" if not blocked else "INCOMPLETE",
        },
    }
    out = RESULTS / "e13_phase1_acceptance.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for d in decisions:
        print(f"[{d['verdict']:7s}] {d['branch']}  {d['question']}")
        for key in ("chosen", "hit_rate", "false_kill", "context_bytes", "dangling", "meso_over_nano", "action"):
            if key in d:
                print(f"           {key}: {d[key]}")
    print(f"\nphase status: {result['summary']['phase_status']} "
          f"({passed}/{len(decisions)} resolved, {len(blocked)} blocked)")
    print(f"-> {out.relative_to(REPO)}")
    return 0 if not blocked else 1


if __name__ == "__main__":
    raise SystemExit(main())
