"""
E11 — Апоптоз и переживание мутаций: отделить устойчивость от эффективности очистки.

N-11: метрика `recovery` в E6 измеряла не устойчивость, а эффективность апоптоза — мутация
была вычищена до замера. Здесь вводится корректная метрика и три стратегии очистки
сравниваются на одинаковом наборе мутаций.

Стратегии:
  A. NO_APOPTOSIS   — мутация остаётся; падение функциональности видно сразу.
  B. EAGER          — апоптоз удаляет всё, что не исполняется в пробной среде (как в E6 v1).
  C. DISCRIMINATING — апоптоз различает «сломан» и «нужен вход» (как в E6 v3).

Правильные метрики — мусор вредит не исполнению, а **адресации**:

  SURVIVAL      — доля живых генов, оставшихся после штурма.
  FUNCTION      — доля задач, решаемых после штурма.
  FALSE_KILL    — сколько живых генов удалено ошибочно. Ноль = хорошо.
  NOISE@5       — доля мусорных генов в топ-5 выдачи векторного резолва. Ноль = хорошо.
  CONTEXT_B     — размер каталога, который агент обязан держать в контексте.

Почему прежняя версия не различала стратегии: она вызывала гены **напрямую по имени**, минуя
резолв, — и мусор не мог помешать. Это ошибка постановки, а не свойство стратегий: реальный
вред зомби-генов в том, что они занимают место в адресном пространстве и в контекстном окне.
"""

from __future__ import annotations

import json
import random
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from e6_mini import BioMini, Gene, Universe, build_universe, translate, RibosomeError

REPO = Path(__file__).resolve().parents[2]

DATA = [3, 1, 4, 1, 5, 9, 2, 6]
N_TASKS = 8


@dataclass
class Outcome:
    survival: float
    function: float
    false_kill: int
    lag: int


def run_tasks(universe: Universe) -> int:
    """Сколько задач решается вселенной прямо сейчас (без векторного резолва — прямой вызов)."""
    solved = 0
    mapping = {
        "G_SIZE": len(DATA),
        "G_SUM": sum(DATA),
        "G_MEAN": sum(DATA) / len(DATA),
        "G_RANGE": max(DATA) - min(DATA),
        "G_SORTED": sorted(DATA),
        "G_UNIQUE": sorted(set(DATA)),
        "G_MAX": max(DATA),
        "G_REVERSED": sorted(DATA)[::-1],
    }
    for gid, expected in mapping.items():
        gene = universe.genes.get(gid)
        if gene is None or not gene.alive:
            continue
        try:
            if translate(gene, {"DATA": DATA, "DATA_ABS": [abs(x) for x in DATA]}) == expected:
                solved += 1
        except RibosomeError:
            pass
    return solved


def apoptosis_eager(universe: Universe) -> list[str]:
    """B: удаляет всё, что не исполнилось в пробной среде (дефект E6 v1)."""
    dead: list[str] = []
    for g in list(universe.genes.values()):
        if not g.alive:
            continue
        try:
            translate(g, {"DATA": [1, 2, 3]})  # среда БЕЗ DATA_ABS
        except RibosomeError:
            universe.genes[g.gene_id] = Gene(g.gene_id, g.body, g.tags, g.strand, alive=False)
            dead.append(g.gene_id)
    return dead


def apoptosis_discriminating(universe: Universe) -> list[str]:
    """C: различает «сломан» и «нужен вход» — среда полная."""
    dead: list[str] = []
    for g in list(universe.genes.values()):
        if not g.alive:
            continue
        if g.sloc < 1:
            universe.genes[g.gene_id] = Gene(g.gene_id, g.body, g.tags, g.strand, alive=False)
            dead.append(g.gene_id)
            continue
        try:
            translate(g, {"DATA": [1, 2, 3], "DATA_ABS": [1, 2, 3]})
        except RibosomeError:
            universe.genes[g.gene_id] = Gene(g.gene_id, g.body, g.tags, g.strand, alive=False)
            dead.append(g.gene_id)
    return dead


#: Гены, которые обязаны выжить: они исполняются. Их потеря — false kill.
LIVE_GENES = {
    "G_SIZE", "G_SUM", "G_MAX", "G_MIN", "G_MEAN", "G_SORTED",
    "G_REVERSED", "G_ABS_SUM", "G_UNIQUE", "G_RANGE",
}


def noise_at_5(universe: Universe, mini: BioMini) -> tuple[float, int]:
    """Доля мусорных генов в топ-5 выдачи и размер каталога."""
    from universe import cosine

    alive = universe.alive()
    if not alive:
        return 0.0, 0
    qv = mini.embedder.embed("сумма значений списка")
    scored = sorted(
        ((cosine(qv, mini.vectors[i]), g.gene_id) for i, g in enumerate(alive)),
        key=lambda x: -x[0],
    )[:5]
    garbage = sum(1 for _, gid in scored if universe.genes[gid].strand == "fault")
    catalog_bytes = len(",".join(g.gene_id for g in alive))
    return round(garbage / max(len(scored), 1), 4), catalog_bytes


def simulate(strategy: str, mutations: int, seed: int = 7) -> Outcome:
    universe = build_universe()
    base_solved = run_tasks(universe)
    rng = random.Random(seed)
    false_kill = 0

    for i in range(mutations):
        # Две мутации-поломки на каждую полезную: каталог говорит, что форки плодят мусор.
        kind = rng.choice(["break", "break", "add_live"])
        if kind == "break":
            gid = f"G_BROKEN_{i}"
            universe.add(Gene(gid, "DATA.missing_attr()", ("сломано",), "fault"))
        else:
            gid = f"G_EXTRA_{i}"
            universe.add(Gene(gid, "sum(DATA)", ("сумма", "дополнительная"), "metrics"))

    if strategy == "EAGER":
        dead = apoptosis_eager(universe)
    elif strategy == "DISCRIMINATING":
        dead = apoptosis_discriminating(universe)
    else:
        dead = []

    false_kill = sum(1 for gid in dead if gid in LIVE_GENES)
    alive_live = sum(1 for gid in LIVE_GENES if universe.genes.get(gid) and universe.genes[gid].alive)
    solved = run_tasks(universe)
    mini = BioMini(universe)
    noise, catalog_bytes = noise_at_5(universe, mini)
    return Outcome(
        survival=round(alive_live / len(LIVE_GENES), 4),
        function=round(solved / N_TASKS, 4),
        false_kill=false_kill,
        lag=max(0, N_TASKS - solved),
    ), noise, catalog_bytes


def main() -> int:
    rows = []
    for strategy in ("NO_APOPTOSIS", "EAGER", "DISCRIMINATING"):
        for m in (0, 30, 60, 120):
            o, noise, catalog_bytes = simulate(strategy, m)
            rows.append(
                {
                    "strategy": strategy,
                    "mutations": m,
                    "survival": o.survival,
                    "function": o.function,
                    "false_kill": o.false_kill,
                    "noise_at_5": noise,
                    "context_bytes": catalog_bytes,
                    "garbage_retained": max(0, m - (m - sum(1 for g in [] ))),
                }
            )

    # Сводка: средняя функциональность и суммарные false_kill
    summary = {}
    for strategy in ("NO_APOPTOSIS", "EAGER", "DISCRIMINATING"):
        group = [r for r in rows if r["strategy"] == strategy]
        summary[strategy] = {
            "mean_function": round(sum(r["function"] for r in group) / len(group), 4),
            "total_false_kill": sum(r["false_kill"] for r in group),
            "worst_function": min(r["function"] for r in group),
            "worst_noise_at_5": max(r["noise_at_5"] for r in group),
            "max_context_bytes": max(r["context_bytes"] for r in group),
        }

    ranking = sorted(
        summary.items(),
        key=lambda kv: (
            -kv[1]["mean_function"],
            kv[1]["worst_noise_at_5"],
            kv[1]["total_false_kill"],
        ),
    )
    result = {
        "rows": rows,
        "summary": summary,
        "ranking": [{"strategy": s, **v} for s, v in ranking],
        "verdict": (
            "DISCRIMINATING выигрывает: сохраняет функцию и не убивает живые гены"
            if summary["DISCRIMINATING"]["mean_function"] >= summary["EAGER"]["mean_function"]
            and summary["DISCRIMINATING"]["total_false_kill"] < summary["EAGER"]["total_false_kill"]
            else "различение не даёт выигрыша на этом наборе"
        ),
    }
    out = REPO / "research" / "results" / "e11_apoptosis.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"{'strategy':16s} {'mut':>5s} {'surv':>6s} {'func':>6s} {'kill':>5s} {'noise@5':>8s} {'ctx_B':>7s}")
    for r in rows:
        print(
            f"{r['strategy']:16s} {r['mutations']:5d} {r['survival']:6.0%} "
            f"{r['function']:6.0%} {r['false_kill']:5d} {r['noise_at_5']:8.0%} {r['context_bytes']:7d}"
        )
    print()
    for s_, v in summary.items():
        print(
            f"  {s_:16s} func={v['mean_function']:.0%} kill={v['total_false_kill']} "
            f"noise={v['worst_noise_at_5']:.0%} ctx={v['max_context_bytes']}B"
        )
    print(f"verdict: {result['verdict']}")
    print(f"-> {out.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
