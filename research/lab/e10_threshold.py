"""
E10 — Есть ли вообще порог? Разложение по типам сущностей.

E9 показал: мезо-гены эффективнее нано всего в 1.06x — прецедент 3 SLOC не работает как
универсальный закон. Но это может быть следствием **смешения типов**: символ-заглушка
(«name only») и символ-функция в 1 SLOC — разные вещи с одинаковым SLOC=1.

Гипотеза: порог не является свойством размера. Он является свойством **типа**:
  * `symbol` с телом-заглушкой (pass/...) — плох при любом размере;
  * `symbol` с телом-выражением — хорош при любом размере;
  * `document`/`passport_symbol` — SLOC не применим вовсе.

Проверка: внутри каждого типа — есть ли монотонность эффективности по SLOC. Если внутри типа
монотонности нет, то порог 3 SLOC — это ложная закономерность, полученная смешением
популяций (классическая ошибка Симпсона).
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from universe import load_universe, tokenize

REPO = Path(__file__).resolve().parents[2]
CHARS_PER_TOKEN = 3.4


def tokens(text: str) -> int:
    return max(1, round(len(text) / CHARS_PER_TOKEN))


def is_stub(body: str) -> bool:
    """Тело-заглушка: только объявление без исполняемой логики."""
    stripped = " ".join(body.split())
    return any(
        stripped.endswith(marker)
        for marker in ("pass", "...", "raise NotImplementedError", "return None", "None:", ":")
    ) or len(stripped) < 40


def main() -> int:
    universe = load_universe(REPO)
    df: dict[str, int] = {}
    recs = []
    for e in universe:
        terms = set(tokenize(e.text or ""))
        recs.append((e, terms))
        for t in terms:
            df[t] = df.get(t, 0) + 1

    by_kind: dict[str, list[dict]] = {}
    for e, terms in recs:
        body = (e.text or "").strip()
        sloc = len([ln for ln in body.splitlines() if ln.strip()])
        info = sum(1.0 / df[t] for t in terms) if terms else 0.0
        cost = tokens(str(e.uri)) + tokens(body)
        rec = {
            "sloc": sloc,
            "eff": info / cost if cost else 0.0,
            "stub": is_stub(body),
            "tokens": cost,
        }
        by_kind.setdefault(getattr(e, "kind", "?"), []).append(rec)

    out_rows = []
    for kind, group in sorted(by_kind.items(), key=lambda kv: -len(kv[1])):
        stubs = [r for r in group if r["stub"]]
        real = [r for r in group if not r["stub"]]
        row = {
            "kind": kind,
            "count": len(group),
            "stubs": len(stubs),
            "stub_share": round(len(stubs) / len(group), 4),
            "eff_all_median": round(statistics.median([r["eff"] for r in group]), 6),
            "eff_stub_median": round(statistics.median([r["eff"] for r in stubs]), 6) if stubs else None,
            "eff_real_median": round(statistics.median([r["eff"] for r in real]), 6) if real else None,
            "sloc_median": int(statistics.median([r["sloc"] for r in group])),
        }
        # Монотонность внутри типа: корреляция SLOC vs efficiency
        if len(group) >= 8:
            xs = [r["sloc"] for r in group]
            ys = [r["eff"] for r in group]
            mx, my = statistics.fmean(xs), statistics.fmean(ys)
            num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
            den = (sum((x - mx) ** 2 for x in xs) ** 0.5) * (sum((y - my) ** 2 for y in ys) ** 0.5)
            row["sloc_eff_corr"] = round(num / den, 3) if den else 0.0
        out_rows.append(row)

    # Симпсон: сравнить stub vs real без учёта размера
    all_stub = [r for g in by_kind.values() for r in g if r["stub"]]
    all_real = [r for g in by_kind.values() for r in g if not r["stub"]]
    simpson = {
        "stub_count": len(all_stub),
        "real_count": len(all_real),
        "stub_eff": round(statistics.median([r["eff"] for r in all_stub]), 6) if all_stub else None,
        "real_eff": round(statistics.median([r["eff"] for r in all_real]), 6) if all_real else None,
        "stub_sloc_median": int(statistics.median([r["sloc"] for r in all_stub])) if all_stub else None,
        "real_sloc_median": int(statistics.median([r["sloc"] for r in all_real])) if all_real else None,
    }
    if all_stub and all_real:
        simpson["ratio"] = round(simpson["real_eff"] / max(simpson["stub_eff"], 1e-12), 3)

    result = {
        "by_kind": out_rows,
        "stub_vs_real": simpson,
        "conclusion": (
            "SLOC-порог смешивает заглушки и реальный код; различение по признаку stub "
            "объясняет эффективность лучше, чем по размеру"
            if simpson.get("ratio", 0) > 1.3
            else "признак stub не объясняет эффективность лучше размера"
        ),
    }
    out = REPO / "research" / "results" / "e10_threshold.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"{'kind':18s} {'n':>5s} {'stub%':>6s} {'eff_all':>9s} {'eff_stub':>9s} {'eff_real':>9s} {'corr':>7s}")
    for r in out_rows:
        print(
            f"{r['kind']:18s} {r['count']:5d} {r['stub_share']:6.1%} {r['eff_all_median']:9.4f} "
            f"{str(r['eff_stub_median']):>9s} {str(r['eff_real_median']):>9s} "
            f"{str(r.get('sloc_eff_corr', '-')):>7s}"
        )
    print()
    print(f"stub vs real: {simpson.get('stub_eff')} vs {simpson.get('real_eff')} = {simpson.get('ratio')}x")
    print(f"-> {out.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
