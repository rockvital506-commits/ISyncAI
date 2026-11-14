"""
E9 — Порог гранулярности: проверить, верны ли 3 SLOC и «нано-гены хуже мезо-генов».

Прецедент `PAT_GENE_GRANULARITY_CROSSOVER_AND_VAET_APOPTOSIS` утверждает:
  нано-гены 1 SLOC: −26.7..−57.5% токенов
  мезо-гены 3..25 SLOC: −70.8..−96.2% токенов
и порог >=3 SLOC как закон.

Замер E8 показал: 77.6% сущностей живой вселенной — 1 SLOC. Если прецедент верен, система
на 3/4 состоит из неэффективных гранул. Если прецедент неверен — мы применяем ложный закон
и режем систему по неверной линии. Обе возможности серьёзны, поэтому порог надо проверить,
а не принять.

Что измеряется. Для каждой сущности считается:
  * стоимость адресации — сколько токенов нужно, чтобы **найти** её (имя + путь);
  * стоимость тела — сколько токенов нужно, чтобы её **исполнить** (тело целиком);
  * полезность — сколько уникальных термов она вносит в корпус.

Ключевая гипотеза порога: нано-ген плох не сам по себе, а потому что **дорог относительно
своей полезности**. Проверяется как отношение (адресация + тело) / уникальные термы.

Если у нано-гена это отношение не хуже, чем у мезо-гена, — порог 3 SLOC неверен как
универсальный закон. Он может быть верен для конкретного сценария (сборка конвейера), но не
для вселенной в целом. Это и надо установить.
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from universe import tokenize

REPO = Path(__file__).resolve().parents[2]

#: Грубая оценка токенов для смешанного кода и русского текста.
#: Не BPE-точность, а монотонная мера: важно соотношение, а не абсолют.
CHARS_PER_TOKEN = 3.4


def tokens(text: str) -> int:
    return max(1, round(len(text) / CHARS_PER_TOKEN))


def bucket_of(sloc: int) -> str:
    if sloc <= 1:
        return "nano(1)"
    if sloc <= 2:
        return "micro(2)"
    if sloc <= 25:
        return "meso(3..25)"
    return "macro(>25)"


def main() -> int:
    from universe import load_universe

    universe = load_universe(REPO)
    rows = []
    corpus_terms: dict[str, set[str]] = {}

    for e in universe:
        body = (e.text or "").strip()
        sloc = len([ln for ln in body.splitlines() if ln.strip()])
        terms = set(tokenize(body))
        corpus_terms[e.uri] = terms
        rows.append(
            {
                "uri": e.uri,
                "kind": getattr(e, "kind", "?"),
                "sloc": sloc,
                "addr_tokens": tokens(str(e.uri)),
                "body_tokens": tokens(body),
                "unique_terms": len(terms),
            }
        )

    # Уникальность терма: в скольких сущностях он встречается. Терм в 200 сущностях
    # различает плохо, терм в одной — различает идеально.
    df: dict[str, int] = {}
    for terms in corpus_terms.values():
        for t in terms:
            df[t] = df.get(t, 0) + 1

    for r in rows:
        terms = corpus_terms[r["uri"]]
        # Информативность: сумма IDF уникальных для этой сущности термов.
        r["info"] = round(sum(1.0 / df[t] for t in terms), 3) if terms else 0.0
        cost = r["addr_tokens"] + r["body_tokens"]
        r["total_tokens"] = cost
        # Эффективность: сколько информативности на токен.
        r["efficiency"] = round(r["info"] / cost, 6) if cost else 0.0

    buckets: dict[str, list[dict]] = {}
    for r in rows:
        buckets.setdefault(bucket_of(r["sloc"]), []).append(r)

    summary = []
    for name in ("nano(1)", "micro(2)", "meso(3..25)", "macro(>25)"):
        group = buckets.get(name, [])
        if not group:
            continue
        summary.append(
            {
                "bucket": name,
                "count": len(group),
                "share": round(len(group) / len(rows), 4),
                "tokens_median": int(statistics.median([r["total_tokens"] for r in group])),
                "info_median": round(statistics.median([r["info"] for r in group]), 3),
                "efficiency_median": round(statistics.median([r["efficiency"] for r in group]), 6),
            }
        )

    # Проверка самого прецедента: действительно ли мезо эффективнее нано?
    nano = next((s for s in summary if s["bucket"] == "nano(1)"), None)
    meso = next((s for s in summary if s["bucket"] == "meso(3..25)"), None)
    verdict = None
    if nano and meso:
        ratio = meso["efficiency_median"] / max(nano["efficiency_median"], 1e-12)
        verdict = {
            "nano_efficiency": nano["efficiency_median"],
            "meso_efficiency": meso["efficiency_median"],
            "meso_over_nano": round(ratio, 3),
            "precedent_holds": ratio > 1.5,
            "interpretation": (
                "прецедент подтверждён: мезо-гранулы эффективнее"
                if ratio > 1.5
                else "прецедент НЕ подтверждён как универсальный закон"
            ),
        }

    # Отдельно — только по коду (symbol), где SLOC осмыслен.
    code_rows = [r for r in rows if r["kind"] == "symbol"]
    code_summary = []
    for name in ("nano(1)", "micro(2)", "meso(3..25)", "macro(>25)"):
        group = [r for r in code_rows if bucket_of(r["sloc"]) == name]
        if group:
            code_summary.append(
                {
                    "bucket": name,
                    "count": len(group),
                    "efficiency_median": round(statistics.median([r["efficiency"] for r in group]), 6),
                    "tokens_median": int(statistics.median([r["total_tokens"] for r in group])),
                }
            )

    result = {
        "entities": len(rows),
        "threshold_claim_sloc": 3,
        "buckets": summary,
        "code_only_buckets": code_summary,
        "precedent_test": verdict,
        "share_below_3_sloc": round(sum(1 for r in rows if r["sloc"] < 3) / len(rows), 4),
    }
    out = REPO / "research" / "results" / "e9_granularity.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"{'bucket':12s} {'count':>6s} {'share':>7s} {'tok':>6s} {'info':>8s} {'eff':>10s}")
    for s in summary:
        print(
            f"{s['bucket']:12s} {s['count']:6d} {s['share']:7.2%} {s['tokens_median']:6d} "
            f"{s['info_median']:8.2f} {s['efficiency_median']:10.2e}"
        )
    if verdict:
        print(f"\nmeso/nano efficiency = {verdict['meso_over_nano']}x  -> {verdict['interpretation']}")
    print(f"-> {out.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
