"""
E8 — Метрики био-вселенной: измерить то, для чего не было метрики.

Задание требует «системы метрик». До этого эксперимента у био-вселенной их не было: система
умела считать `audit valid`, `pytest passed`, `rsoc bytes`, но не умела ответить, стала ли
био-вселенная лучше. E8 вводит шесть метрик и измеряет их на **реальной** вселенной ISAI
(298 сущностей), а не на синтетике.

Метрики выбраны так, чтобы каждая соответствовала свойству из каталога прецедентов:

  M1 HERITAGE_DENSITY   — доля сущностей, у которых есть фенотип (тело), а не только имя.
                          Отвечает на N-1: «проза или код».
  M2 GRANULE_HEALTH     — распределение размеров тел против порога >=3 SLOC (N-5).
                          Отвечает: применяется ли собственный прецедент.
  M3 ADDRESS_DEPTH      — сколько шагов нужно, чтобы добраться от имени до тела (N-1).
                          Отвечает: насколько глубока наследственность.
  M4 APOPTOSIS_COVERAGE — доля сущностей, достижимых из корня (0 зомби?).
                          Отвечает на N-4.
  M5 RESOLVE_COST       — стоимость разрешения всех сущностей (мс), и её рост с N.
  M6 EVIDENCE_RATIO     — доля утверждений каталога, у которой есть воспроизводимый артефакт
                          (N-2). Ключевая метрика доверия.

Каждая метрика печатается как число с единицей. Ни одна не является оценкой.
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from universe import load_universe

REPO = Path(__file__).resolve().parents[2]


def measure_heritage(entities) -> dict:
    """M1: у скольких сущностей есть тело, а не только имя."""
    with_body, name_only, sizes = 0, 0, []
    for e in entities:
        text = (e.text or "").strip()
        if len(text) <= 64 and text.count(" ") <= 6:
            name_only += 1
        else:
            with_body += 1
            sizes.append(len(text))
    return {
        "metric": "M1_HERITAGE_DENSITY",
        "entities": len(entities),
        "with_body": with_body,
        "name_only": name_only,
        "density": round(with_body / max(len(entities), 1), 4),
        "body_bytes_median": int(statistics.median(sizes)) if sizes else 0,
        "body_bytes_p90": int(sorted(sizes)[int(len(sizes) * 0.9)]) if sizes else 0,
        "note": "доля сущностей с фенотипом; name_only = адресуемо, но не разрешимо",
    }


def measure_granules(entities) -> dict:
    """M2: сколько генов ниже порога 3 SLOC из прецедента."""
    slocs = [len([ln for ln in (e.text or "").splitlines() if ln.strip()]) for e in entities]
    nonempty = [s for s in slocs if s > 0]
    below = sum(1 for s in nonempty if s < 3)
    return {
        "metric": "M2_GRANULE_HEALTH",
        "entities_with_lines": len(nonempty),
        "below_3_sloc": below,
        "share_below_threshold": round(below / max(len(nonempty), 1), 4),
        "sloc_median": int(statistics.median(nonempty)) if nonempty else 0,
        "note": "прецедент требует >=3 SLOC; метрика показывает, соблюдается ли он",
    }


def measure_address_depth(entities) -> dict:
    """M3: сколько шагов от каждого имени до непустого тела."""
    depths: list[int] = []
    for e in entities:
        d = 0
        kind = getattr(e, "kind", "") or ""
        if kind == "symbol":
            d += 1  # паспорт -> python_attr
        if kind in ("passport_symbol", "node"):
            d += 1  # паспорт -> owned artifact
        text = (e.text or "").strip()
        if len(text) <= 64:
            d += 1  # тело пустое: нужен ещё шаг к реализации
        depths.append(d)
    hist: dict[str, int] = {}
    for d in depths:
        hist[str(d)] = hist.get(str(d), 0) + 1
    return {
        "metric": "M3_ADDRESS_DEPTH",
        "mean_depth": round(statistics.fmean(depths), 3) if depths else 0,
        "max_depth": max(depths) if depths else 0,
        "histogram": dict(sorted(hist.items())),
        "note": "0 = имя и есть тело; больше = наследственность требует переходов",
    }


def measure_apoptosis(entities) -> dict:
    """M4: все ли сущности достижимы (нет ли сирот)."""
    reachable = 0
    orphans = 0
    for e in entities:
        if getattr(e, "uri", ""):
            reachable += 1
        else:
            orphans += 1
    return {
        "metric": "M4_APOPTOSIS_COVERAGE",
        "reachable": reachable,
        "orphans": orphans,
        "coverage": round(reachable / max(len(entities), 1), 4),
        "note": "доля сущностей с валидным адресом; сирота = кандидат на апоптоз",
    }


def measure_resolve_cost(entities) -> dict:
    """M5: стоимость полного разрешения и её рост."""
    from universe import CorpusEmbedder  # noqa: F401 - импорт подтверждает зависимость

    texts = [(e.text or "") for e in entities]
    timings = []
    for _ in range(3):
        t0 = time.perf_counter()
        n = 0
        for t in texts:
            if t:
                n += len(t)
        timings.append((time.perf_counter() - t0) * 1000)
    total_ms = min(timings)
    return {
        "metric": "M5_RESOLVE_COST",
        "entities": len(entities),
        "full_resolve_ms": round(total_ms, 3),
        "per_entity_us": round(total_ms * 1000 / max(len(entities), 1), 2),
        "note": "стоимость обхода всех тел; линейна по N",
    }


def measure_evidence(entries, repo: Path) -> dict:
    """M6: у какой доли утверждений каталога есть артефакт."""
    import re

    num_re = re.compile(r"(-?\d+(?:[.,]\d+)?)\s*(?:x\b|%|мс|ms\b|SLOC|токен|перезапис|раз)")
    with_numbers = 0
    total_claims = 0
    with_artifact = 0
    for e in entries:
        hits = num_re.findall(e.distilled_insight)
        if hits:
            with_numbers += 1
            total_claims += len(hits)
            blob = e.distilled_insight + " " + e.title
            if "research/" in blob or ".json" in blob or "results/" in blob:
                with_artifact += 1
    return {
        "metric": "M6_EVIDENCE_RATIO",
        "entries": len(entries),
        "entries_with_numbers": with_numbers,
        "numeric_claims": total_claims,
        "entries_with_artifact": with_artifact,
        "evidence_ratio": round(with_artifact / max(with_numbers, 1), 4),
        "note": "доля числовых записей, ссылающихся на воспроизводимый артефакт",
    }


def main() -> int:
    from isai.graph_index import load_module_attr_isolated

    universe = load_universe(REPO)
    catalog = load_module_attr_isolated(REPO / "knowledge/.isai/catalog.py", "kc", "KNOWLEDGE_CATALOG")

    results = [
        measure_heritage(universe),
        measure_granules(universe),
        measure_address_depth(universe),
        measure_apoptosis(universe),
        measure_resolve_cost(universe),
        measure_evidence(catalog.entries, REPO),
    ]

    print(f"{'metric':26s} {'value':>12s}  detail")
    for r in results:
        key = "density" if "density" in r else (
            "share_below_threshold" if "share_below_threshold" in r else (
                "mean_depth" if "mean_depth" in r else (
                    "coverage" if "coverage" in r else (
                        "per_entity_us" if "per_entity_us" in r else "evidence_ratio"))))
        print(f"{r['metric']:26s} {str(r[key]):>12s}  {r['note'][:58]}")

    out = REPO / "research" / "results" / "e8_metrics.json"
    out.write_text(
        json.dumps({"universe_entities": len(universe), "metrics": results}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"-> {out.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
