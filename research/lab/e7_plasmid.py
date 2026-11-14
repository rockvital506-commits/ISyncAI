"""
E7 — Плазмиды, эпохи и ромбовидный DAG: воспроизведение метрик TASK-005 на мини-вселенной.

Каталог (`PAT_BIO_UNIVERSE_PYDANTIC_HOLON_EPOCH_RIBOSOME`) утверждает три эффекта:

* мемоизация Плазмид снимает **110.7x** раздутие ромбовидного DAG;
* кэш Рибосомы с проверкой эпохи ускоряет диспетчеризацию в **3.18x**;
* Pydantic `model_validate(context={'universe': u})` ловит **100%** структурных ошибок.

Эти числа получены на R&D-стенде, не на живой системе. Здесь они **воспроизводятся
независимо** на мини-вселенной, чтобы проверить: это свойство архитектуры или артефакт
конкретного стенда. Если воспроизводятся — числа можно переносить в решения. Если нет —
в каталоге записано то, что верно только для одной конфигурации.

Строится ромбовидный DAG: Ген -> Плазмида -> ... -> один общий узел, с пересечением путей
на каждом уровне (классический источник комбинаторного взрыва при наивном обходе).
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


@dataclass
class Plasmid:
    """Плазмида: переносимая группа генов с вычисленным значением (мемоизированная)."""

    plasmid_id: str
    genes: tuple[str, ...]
    value: float = 0.0
    computed: bool = False


@dataclass
class Holon:
    """Холон: объект, ссылающийся на Плазмиды по URI-кодонам, а не содержащий их копии."""

    holon_id: str
    codons: tuple[str, ...]


@dataclass
class EpochUniverse:
    plasmids: dict[str, Plasmid] = field(default_factory=dict)
    epoch: int = 1
    cache: dict[tuple[str, int], float] = field(default_factory=dict)
    eval_count: int = 0

    def add(self, plasmid: Plasmid) -> None:
        self.plasmids[plasmid.plasmid_id] = plasmid
        self.epoch += 1

    def resolve(self, plasmid_id: str) -> float:
        """Резолв Плазмиды с мемоизацией и проверкой эпохи (как кэш Рибосомы)."""
        key = (plasmid_id, self.epoch)
        if key in self.cache:
            return self.cache[key]
        p = self.plasmids[plasmid_id]
        if not p.computed:
            self.eval_count += 1
            # «Исполнение генов»: детерминированная функция от содержимого.
            p.value = sum(len(g) for g in p.genes) + p.genes.__len__()
            p.computed = True
        self.cache[key] = p.value
        return p.value


def build_rhombus(depth: int, width: int) -> tuple[EpochUniverse, list[Holon]]:
    """
    Ромбовидный DAG: `depth` уровней, `width` плазмид на уровень, все Холоны верхнего уровня
    ссылаются на *пересекающиеся* наборы нижних Плазмид (общий предок в каждом ромбе).
    """
    u = EpochUniverse()
    for level in range(depth):
        for i in range(width):
            pid = f"P{level}_{i}"
            # Каждая плазмида зависит от двух нижних — классический ромб.
            genes = (f"g{level}_{i}_a", f"g{level}_{i}_b")
            if level > 0:
                genes += (f"P{level-1}_{i % width}", f"P{level-1}_{(i + 1) % width}")
            u.add(Plasmid(pid, genes))
    holons = [Holon(f"H{i}", tuple(f"P{depth-1}_{i % width}" for _ in range(3))) for i in range(width * 2)]
    return u, holons


def naive_expansion(holons: list[Holon], universe: EpochUniverse) -> int:
    """
    Наивный обход: Холон раскрывается в полное дерево генов без мемоизации.

    Возвращает число раскрытых узлов — это и есть «раздутие DAG».
    """
    nodes = 0

    def walk(pid: str, depth: int = 0) -> None:
        nonlocal nodes
        if depth > 40:  # защита от бесконечности на циклах
            return
        nodes += 1
        p = universe.plasmids[pid]
        for g in p.genes:
            if g.startswith("P"):
                walk(g, depth + 1)

    for h in holons:
        for c in h.codons:
            walk(c)
    return nodes


def main() -> int:
    rows = []
    for depth, width in ((3, 3), (4, 4), (5, 4), (6, 5)):
        u, holons = build_rhombus(depth, width)

        t0 = time.perf_counter()
        naive_nodes = naive_expansion(holons, u)
        naive_ms = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        resolved = 0
        for h in holons:
            for c in h.codons:
                u.resolve(c)
                resolved += 1
        memo_ms = (time.perf_counter() - t0) * 1000

        inflated = naive_nodes / max(resolved, 1)
        rows.append(
            {
                "depth": depth,
                "width": width,
                "plasmids": len(u.plasmids),
                "holons": len(holons),
                "naive_nodes": naive_nodes,
                "memoized_resolutions": resolved,
                "inflation_ratio": round(inflated, 2),
                "naive_ms": round(naive_ms, 3),
                "memo_ms": round(memo_ms, 3),
                "speedup": round(naive_ms / max(memo_ms, 1e-9), 2),
                "gene_evaluations": u.eval_count,
            }
        )
        print(
            f"depth={depth} width={width}: {len(u.plasmids):3d} plasmids, naive {naive_nodes:6d} nodes "
            f"vs {resolved:3d} memoized ({inflated:6.1f}x inflation), "
            f"{naive_ms:7.2f} ms vs {memo_ms:6.2f} ms ({rows[-1]['speedup']:6.1f}x)"
        )

    # Эпоха: сколько стоит один refresh кэша после мутации одной плазмиды.
    u, holons = build_rhombus(5, 4)
    for h in holons:
        for c in h.codons:
            u.resolve(c)
    t0 = time.perf_counter()
    u.add(Plasmid("P_new", ("gnew",)))
    for h in holons:
        for c in h.codons:
            u.resolve(c)
    epoch_refresh_ms = (time.perf_counter() - t0) * 1000

    result = {
        "rhombus": rows,
        "epoch": {
            "refresh_after_one_mutation_ms": round(epoch_refresh_ms, 3),
            "note": "epoch bump invalidates the whole cache; a per-plasmid epoch would be finer",
        },
        "cross_check_vs_catalog": {
            "catalog_claims": {"dag_inflation_x": 110.7, "ribosome_cache_speedup_x": 3.18},
            "reproduced_inflation_max": max(r["inflation_ratio"] for r in rows),
            "reproduced_speedup_max": max(r["speedup"] for r in rows),
        },
    }
    out = REPO / "research" / "results" / "e7_plasmid.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"epoch refresh after 1 mutation: {epoch_refresh_ms:.2f} ms")
    print(f"-> {out.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
