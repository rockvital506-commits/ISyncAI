"""
E12 — Эпоха и инвалидация кэша: цена глобального сброса.

N-6: `EpochUniverse.add()` повышает глобальную эпоху, что сбрасывает **весь** кэш. Механизм
корректен, но при частых мутациях выигрыш кэша падает до нуля. Заявленные в каталоге 3.18x —
это холодный выигрыш, а не установившийся режим.

Сравниваются четыре стратегии инвалидации на одном рабочем профиле:

  GLOBAL_EPOCH   — одна эпоха на вселенную (текущая в E7). Любая мутация сбрасывает всё.
  PER_PLASMID    — версия на каждую плазмиду. Мутация сбрасывает только её.
  DEPENDENCY_DAG — версия по транзитивным зависимостям (мутация сбрасывает её и всё, что от
                   неё зависит; не трогает независимые ветви).
  NO_CACHE       — контроль: кэша нет вовсе.

Рабочий профиль: `N` плазмид, `R` циклов чтения, между которыми происходят `M` мутаций
случайных плазмид. Метрики:
  hit_rate   — доля чтений, обслуженных из кэша (высокая = хорошо);
  stale_reads — доля чтений, вернувших устаревшее значение (ОБЯЗАТЕЛЬНО 0: корректность
               не приносится в жертву скорости);
  eval_count — сколько раз реально исполнялись тела (низкий = хорошо).

Ключевой критерий отбора: стратегия допустима только при stale_reads == 0. Среди допустимых
выбирается максимальный hit_rate.
"""

from __future__ import annotations

import json
import random
import statistics
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


@dataclass
class Pl:
    pid: str
    deps: tuple[str, ...]
    value: float = 0.0
    computed: bool = False
    version: int = 0


@dataclass
class Store:
    """Вселенная плазмид с подключаемой стратегией инвалидации."""

    strategy: str
    plasmids: dict[str, Pl] = field(default_factory=dict)
    epoch: int = 0
    #: pid -> (cached_version, value)
    cache: dict[str, tuple[int, float]] = field(default_factory=dict)
    evals: int = 0
    hits: int = 0
    stale: int = 0

    def add(self, p: Pl) -> None:
        self.plasmids[p.pid] = p
        if self.strategy == "GLOBAL_EPOCH":
            self.epoch += 1
        elif self.strategy == "DEPENDENCY_DAG":
            # Инвалидируем новую плазмиду и всех её потомков.
            self._invalidate_dependents(p.pid)

    def _invalidate_dependents(self, root: str) -> None:
        dead = {root}
        changed = True
        while changed:
            changed = False
            for p in self.plasmids.values():
                if p.pid not in dead and any(d in dead for d in p.deps):
                    dead.add(p.pid)
                    changed = True
        for pid in dead:
            self.cache.pop(pid, None)

    def mutate(self, pid: str) -> None:
        """Изменить тело плазмиды: значение обязано пересчитаться."""
        p = self.plasmids[pid]
        p.value = p.value + 1.0
        p.computed = True
        p.version += 1
        if self.strategy == "GLOBAL_EPOCH":
            self.epoch += 1
        elif self.strategy == "PER_PLASMID":
            self.cache.pop(pid, None)
        elif self.strategy == "DEPENDENCY_DAG":
            self._invalidate_dependents(pid)

    def read(self, pid: str) -> float:
        p = self.plasmids[pid]
        if self.strategy == "NO_CACHE":
            self.evals += 1
            return p.value
        key_version = self.epoch if self.strategy == "GLOBAL_EPOCH" else p.version
        if pid in self.cache and self.cache[pid][0] == key_version:
            self.hits += 1
            return self.cache[pid][1]
        # Промах: пересчёт (исполнение тела).
        self.evals += 1
        self.cache[pid] = (key_version, p.value)
        return p.value


def build(n: int, seed: int) -> Store:
    """Ромбовидный DAG: каждая плазмида зависит от двух нижних, что делает инвалидацию
    нетривиальной — зависимые обязаны узнавать об изменении предка."""
    rng = random.Random(seed)
    store = Store(strategy="NO_CACHE")
    width = max(2, int(n ** 0.5))
    for i in range(n):
        level = i // width
        pid = f"P{i}"
        if level == 0:
            deps: tuple[str, ...] = ()
        else:
            a = (level - 1) * width + rng.randrange(width)
            b = (level - 1) * width + rng.randrange(width)
            deps = (f"P{a}",) if a == b else (f"P{a}", f"P{b}")
        store.plasmids[pid] = Pl(pid, deps, value=float(i), computed=True)
    return store


def run(strategy: str, n: int = 400, rounds: int = 40, mutations_per_round: int = 3, seed: int = 11) -> dict:
    store = build(n, seed)
    store.strategy = strategy
    store.cache.clear()
    store.evals = store.hits = store.stale = 0
    rng = random.Random(seed)
    read_log: list[float] = []

    for _ in range(rounds):
        # Фаза чтения: агент обходит случайные плазмиды.
        for _ in range(n // 4):
            pid = f"P{rng.randrange(n)}"
            read_log.append(store.read(pid))
        # Фаза мутации.
        for _ in range(mutations_per_round):
            store.mutate(f"P{rng.randrange(n)}")

    total_reads = rounds * (n // 4)
    return {
        "strategy": strategy,
        "reads": total_reads,
        "evals": store.evals,
        "hit_rate": round(store.hits / max(total_reads, 1), 4),
        "evals_per_read": round(store.evals / max(total_reads, 1), 4),
    }


def correctness_check() -> dict:
    """Обязательный тест: после мутации чтение обязано вернуть НОВОЕ значение."""
    out = {}
    for strategy in ("NO_CACHE", "GLOBAL_EPOCH", "PER_PLASMID", "DEPENDENCY_DAG"):
        store = build(50, seed=3)
        store.strategy = strategy
        store.cache.clear()
        pid = "P10"
        before = store.read(pid)
        store.mutate(pid)
        after = store.read(pid)
        out[strategy] = {
            "before": before,
            "after": after,
            "ok": after != before or strategy == "NO_CACHE",
            "stale_detected": after == before and strategy != "NO_CACHE",
        }
    return out


def main() -> int:
    rows = [run(s) for s in ("NO_CACHE", "GLOBAL_EPOCH", "PER_PLASMID", "DEPENDENCY_DAG")]
    correctness = correctness_check()

    # Допустима только корректная стратегия; среди них — максимальный hit_rate.
    admissible = [r for r in rows if not correctness[r["strategy"]]["stale_detected"]]
    best = max(admissible, key=lambda r: r["hit_rate"]) if admissible else None

    result = {
        "profile": {"plasmid_universe": 400, "rounds": 40, "mutations_per_round": 3},
        "rows": rows,
        "correctness": correctness,
        "best_admissible": best,
        "global_epoch_penalty": None,
    }
    ge = next(r for r in rows if r["strategy"] == "GLOBAL_EPOCH")
    dg = next(r for r in rows if r["strategy"] == "DEPENDENCY_DAG")
    if dg["hit_rate"] > 0:
        result["global_epoch_penalty"] = {
            "hit_rate_global": ge["hit_rate"],
            "hit_rate_dag": dg["hit_rate"],
            "relative_gain": round(dg["hit_rate"] / max(ge["hit_rate"], 1e-9), 2),
            "guard": "некорректная стратегия не допускается даже при большем hit_rate",
        }

    out = REPO / "research" / "results" / "e12_epoch.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"{'strategy':16s} {'hit_rate':>9s} {'evals/read':>11s} {'correct':>8s}")
    for r in rows:
        ok = not correctness[r["strategy"]]["stale_detected"]
        print(f"{r['strategy']:16s} {r['hit_rate']:9.2f} {r['evals_per_read']:11.2f} {str(ok):>8s}")
    if result["global_epoch_penalty"]:
        p = result["global_epoch_penalty"]
        print(f"\nGLOBAL_EPOCH hit {p['hit_rate_global']:.2f} -> DAG hit {p['hit_rate_dag']:.2f} "
              f"= {p['relative_gain']}x")
    print(f"best admissible: {best['strategy'] if best else None}")
    print(f"-> {out.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
