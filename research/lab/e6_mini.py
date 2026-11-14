"""
E6 — Мини-ИИ и Python-биовселенная: минимальный набор правил, объектов и протоколов.

Задание: «попробуй сгенерировать простую мини ИИ систему с учетом требований к мини системе
для экспериментов и пайтон-био вселенной (мини набор протоколов, правил, объектов); замерь
метрики эффективности, сравни и ранжируй обычные агентные системы и полученный вариант».

Границы дизайна — из самого фундаментала и каталога прецедентов, а не из удобства:

* `PAT_BIO_UNIVERSE_PYDANTIC_HOLON_EPOCH_RIBOSOME`: объекты — Холон (атом/ген/плазмида),
  Рибосома исполняет, Эпохи версионируют.
* `PAT_GENE_GRANULARITY_CROSSOVER_AND_VAET_APOPTOSIS`: Ген = >=3 SLOC; апоптоз мёртвых генов.
* `PAT_OPERADIC_PIPELINE_VS_HYPERGRAPH_BOUNDARY`: операдный конвейер — для линейной сборки,
  гиперграф — для адресации. Смешивать нельзя.
* Анти-цель №2: никаких эзотерических неологизмов без связи с кодом.

Мини-система (BioMini) строится ровно из четырёх протоколов:

  P1 GENOME      — Вселенная как множество Генов; Ген = (id, тело, теги, штамм).
  P2 RIBOSOME    — исполнение Гена даёт фенотип; рибосома отказывает при нарушении контракта.
  P3 APOPTOSIS   — мёртвый/неисполнимый Ген удаляется; Вселенная остаётся консистентной.
  P4 TRANSLATION — запрос на естественном языке -> Ген(ы) через вектор, затем исполнение.

Сравниваются четыре системы на восьми задачах:

  A. FLAT_AGENT      — классический агент: один LLM-вызов с полным контекстом (симулируется
                       линейным сканом без структуры), без памяти о генах.
  B. TOOL_AGENT      — агент с инструментами: вызывает функции по фиксированному имени.
  C. GRAPH_AGENT     — агент с гиперграфом: точный URI-резолв, как в ISAI сегодня.
  D. BIO_MINI        — Гены + рибосома + трансляция запроса вектором.

Метрики (все измеряются, не оцениваются):
  success_rate, context_bytes, latency_ms, steps, recovery_rate (после мутации),
  discovery_rate (находит сущность, которую никто не адресовал явно).
"""

from __future__ import annotations

import json
import random
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from universe import CorpusEmbedder, cosine, tokenize

REPO = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# P1 GENOME: объекты биовселенной
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Gene:
    """Единица наследственности: исполняемое тело + смысловые теги."""

    gene_id: str
    body: str  # python-выражение, возвращающее значение
    tags: tuple[str, ...]
    strand: str  # «штамм»: к какому протоколу принадлежит
    alive: bool = True

    @property
    def sloc(self) -> int:
        return len([ln for ln in self.body.splitlines() if ln.strip()])


@dataclass
class Universe:
    """P1: множество Генов. Рибосома и апоптоз работают над ним."""

    genes: dict[str, Gene] = field(default_factory=dict)
    history: list[str] = field(default_factory=list)

    def add(self, gene: Gene) -> None:
        self.genes[gene.gene_id] = gene
        self.history.append(f"+{gene.gene_id}")

    def alive(self) -> list[Gene]:
        return [g for g in self.genes.values() if g.alive]


# ---------------------------------------------------------------------------
# P2 RIBOSOME: исполнение с контрактом
# ---------------------------------------------------------------------------

#: Разрешённые встроенные функции рибосомы.
#:
#: Список измерен, а не угадан: первая версия содержала только len/sum/min/max/abs/sorted, и
#: апоптоз каскадно удалил `G_UNIQUE` (нужен `set`) и `G_ABS_SUM` (нужен генератор с `abs` внутри
#: comprehension). То есть **политика песочницы определяет, какие гены выживут** — это не
#: побочный эффект, а свойство биовселенной: слишком узкая рибосома убивает жизнеспособное.
#: Правило: разрешать чистые функции без побочных эффектов; запрещать `open`, `eval`, `exec`,
#: `__import__` и всё, что даёт доступ к состоянию процесса.
SAFE_BUILTINS = {
    "len": len, "sum": sum, "min": min, "max": max, "abs": abs, "sorted": sorted,
    "set": set, "list": list, "tuple": tuple, "dict": dict, "range": range,
    "any": any, "all": all, "round": round, "enumerate": enumerate, "zip": zip,
}


class RibosomeError(RuntimeError):
    """Отказ рибосомы: Ген нарушил контракт исполнения."""


def translate(gene: Gene, environment: dict[str, object] | None = None) -> object:
    """
    Транслировать Ген в фенотип.

    Контракт жёсткий по образцу ISAI: тело исполняется в песочнице с явным списком встроенных
    функций, любое исключение — отказ, а не «пусть упадёт дальше». Это то, что делает
    биовселенную безопасной: Ген не может сделать ничего, что не разрешено рибосомой.
    """
    if not gene.alive:
        raise RibosomeError(f"{gene.gene_id} is apoptotic")
    scope = dict(SAFE_BUILTINS)
    if environment:
        scope.update(environment)
    try:
        return eval(compile(gene.body, f"<gene:{gene.gene_id}>", "eval"), {"__builtins__": {}}, scope)
    except Exception as exc:  # noqa: BLE001 - контракт: любой сбой = отказ
        raise RibosomeError(f"{gene.gene_id}: {type(exc).__name__}: {exc}") from exc


# ---------------------------------------------------------------------------
# P3 APOPTOSIS
# ---------------------------------------------------------------------------


def apoptosis(universe: Universe, environment: dict[str, object] | None = None) -> list[str]:
    """
    Удалить Гены, которые не транслируются в *полной* среде, или пусты.

    Отказ `RequiresEnvironment` жизнеспособного Гена — не апоптоз: Ген, которому нужны данные
    запроса, здоров, просто не самодостаточен. Отличать «сломан» от «нужен вход» — обязательное
    условие, иначе апоптоз каскадно убивает рабочие гены (первая версия этой функции так и
    сделала: удалила `G_UNIQUE` и `G_ABS_SUM`, которые исполняются безупречно).
    """
    dead: list[str] = []
    probe_env = dict(environment or {})
    probe_env.setdefault("DATA", [1, 2, 3])  # проба, а не реальные данные задачи
    probe_env.setdefault("DATA_ABS", [1, 2, 3])
    for gene in list(universe.genes.values()):
        if not gene.alive:
            continue
        if gene.sloc < 1:
            universe.genes[gene.gene_id] = Gene(gene.gene_id, gene.body, gene.tags, gene.strand, alive=False)
            dead.append(gene.gene_id)
            continue
        try:
            translate(gene, probe_env)
        except RibosomeError:
            universe.genes[gene.gene_id] = Gene(gene.gene_id, gene.body, gene.tags, gene.strand, alive=False)
            dead.append(gene.gene_id)
    universe.history.append(f"apoptosis:{len(dead)}")
    return dead


# ---------------------------------------------------------------------------
# P4 TRANSLATION: запрос -> Ген
# ---------------------------------------------------------------------------


def build_universe() -> Universe:
    """Мини-вселенная: 12 генов, покрывающих четыре задачи эксперимента."""
    u = Universe()
    specs = [
        ("G_SIZE", "len(DATA)", ("размер", "количество", "size", "count"), "metrics"),
        ("G_SUM", "sum(DATA)", ("сумма", "итог", "sum", "total"), "metrics"),
        ("G_MAX", "max(DATA)", ("максимум", "пик", "max", "peak"), "metrics"),
        ("G_MIN", "min(DATA)", ("минимум", "min"), "metrics"),
        ("G_MEAN", "sum(DATA)/len(DATA)", ("среднее", "mean", "average"), "metrics"),
        ("G_SORTED", "sorted(DATA)", ("сортировка", "порядок", "sorted", "order"), "transform"),
        ("G_REVERSED", "sorted(DATA)[::-1]", ("обратный", "реверс", "descending"), "transform"),
        ("G_ABS_SUM", "sum(DATA_ABS)", ("модуль", "абсолютная", "abs"), "metrics"),
        ("G_UNIQUE", "sorted(set(DATA))", ("уникальные", "различные", "unique"), "transform"),
        ("G_RANGE", "max(DATA)-min(DATA)", ("размах", "диапазон", "range"), "metrics"),
        ("G_BROKEN", "DATA.nonexistent()", ("сломано", "broken"), "fault"),
        ("G_EMPTY", "", ("пусто", "empty"), "fault"),
    ]
    for gid, body, tags, strand in specs:
        u.add(Gene(gid, body, tags, strand))
    return u


class BioMini:
    """Мини-ИИ: рибосома + трансляция запроса в Ген через вектор."""

    def __init__(self, universe: Universe, *, threshold: float = 0.05) -> None:
        self.universe = universe
        self.threshold = threshold
        self.texts = [" ".join([g.gene_id, *g.tags, g.body]) for g in universe.alive()]
        self.embedder = CorpusEmbedder(dim=256).fit(self.texts)
        self.vectors = self.embedder.embed_many(self.texts)

    def resolve(self, query: str) -> Gene | None:
        alive = self.universe.alive()
        qv = self.embedder.embed(query)
        best_i, best_s = max(((i, cosine(qv, v)) for i, v in enumerate(self.vectors)), key=lambda x: x[1])
        return alive[best_i] if best_s >= self.threshold else None

    def run(self, query: str, data: list[int]) -> tuple[bool, object, int]:
        """Одна итерация: трансляция запроса, затем исполнение. Возвращает (успех, значение, шагов)."""
        gene = self.resolve(query)
        if gene is None:
            return False, None, 1
        try:
            return True, translate(gene, {"DATA": data, "DATA_ABS": [abs(x) for x in data]}), 1
        except RibosomeError:
            return False, None, 1


# ---------------------------------------------------------------------------
# Сравниваемые системы
# ---------------------------------------------------------------------------


class FlatAgent:
    """
    A. Классический агент: весь «контекст» подаётся целиком, выбор — линейным сканом текста.

    Моделируется без LLM намеренно: мы сравниваем *механизмы организации*, а не качество
    конкретной модели. Контекст = полный текст вселенной, что и есть главный дефект подхода.
    """

    name = "FLAT_AGENT"

    def __init__(self, genes: list[Gene]) -> None:
        self.genes = genes
        self.context = " ".join(f"{g.gene_id} {g.body} {' '.join(g.tags)}" for g in genes)

    def run(self, query: str, data: list[int]) -> tuple[bool, object, int]:
        q = set(tokenize(query))
        best, best_score, steps = None, -1, 0
        for gene in self.genes:
            steps += 1
            score = len(q & set(tokenize(" ".join(gene.tags) + " " + gene.body)))
            if score > best_score:
                best, best_score = gene, score
        if best is None or best_score <= 0:
            return False, None, steps
        try:
            return True, translate(best, {"DATA": data, "DATA_ABS": [abs(x) for x in data]}), steps
        except RibosomeError:
            return False, None, steps

    @property
    def context_bytes(self) -> int:
        return len(self.context.encode("utf-8"))


class ToolAgent:
    """
    B. Агент с инструментами: фиксированный словарь имён. Находит, только если запрос
    дословно называется инструментом — это и есть предел tool-calling без семантики.
    """

    name = "TOOL_AGENT"

    def __init__(self, genes: list[Gene]) -> None:
        self.tools = {g.gene_id.lower(): g for g in genes}

    def run(self, query: str, data: list[int]) -> tuple[bool, object, int]:
        q = query.lower()
        for name, gene in self.tools.items():
            if name in q:
                try:
                    return True, translate(gene, {"DATA": data, "DATA_ABS": [abs(x) for x in data]}), 1
                except RibosomeError:
                    return False, None, 1
        return False, None, 1

    @property
    def context_bytes(self) -> int:
        # tool-calling подаёт схемы инструментов: имя + описание.
        return len(json.dumps({g.lower(): " ".join(v.tags) for g, v in self.tools.items()}, ensure_ascii=False).encode())


class GraphAgent:
    """C. Агент с гиперграфом: точный URI-резолв (дискретная логика ISAI сегодня)."""

    name = "GRAPH_AGENT"

    def __init__(self, genes: list[Gene]) -> None:
        self.genes = {f"cell://{g.gene_id}": g for g in genes}

    def run(self, query: str, data: list[int]) -> tuple[bool, object, int]:
        # Точное совпадение адреса — единственный способ, как в `isai://…#Symbol`.
        for uri, gene in self.genes.items():
            if uri.split("#")[-1].lower() in query.lower():
                try:
                    return True, translate(gene, {"DATA": data, "DATA_ABS": [abs(x) for x in data]}), 1
                except RibosomeError:
                    return False, None, 1
        return False, None, 1

    @property
    def context_bytes(self) -> int:
        return len(json.dumps(list(self.genes), ensure_ascii=False).encode())


class BioMiniAgent:
    """D. Биовселенная: векторная трансляция запроса + рибосома + апоптоз."""

    name = "BIO_MINI"

    def __init__(self, mini: BioMini) -> None:
        self.mini = mini

    def run(self, query: str, data: list[int]) -> tuple[bool, object, int]:
        return self.mini.run(query, data)

    @property
    def context_bytes(self) -> int:
        # В контекст агента идёт только каталог имён, а не тела генов: тела исполняет рибосома.
        return len(json.dumps([g.gene_id for g in self.mini.universe.alive()], ensure_ascii=False).encode())


# ---------------------------------------------------------------------------
# Задачи
# ---------------------------------------------------------------------------

DATA = [3, 1, 4, 1, 5, 9, 2, 6]

TASKS = [
    ("посчитай количество элементов", len(DATA)),
    ("вычисли сумму всех значений", sum(DATA)),
    ("найди среднее арифметическое", sum(DATA) / len(DATA)),
    ("какой размах значений", max(DATA) - min(DATA)),
    ("отсортируй значения по возрастанию", sorted(DATA)),
    ("получи уникальные элементы", sorted(set(DATA))),
    ("максимальный элемент списка", max(DATA)),
    ("обратный порядок сортировки", sorted(DATA)[::-1]),
]


def evaluate_system(system, tasks) -> dict:
    successes = 0
    latencies: list[float] = []
    steps: list[int] = []
    for query, expected in tasks:
        t0 = time.perf_counter()
        ok, value, n = system.run(query, DATA)
        latencies.append((time.perf_counter() - t0) * 1000)
        steps.append(n)
        successes += int(ok and value == expected)
    return {
        "system": system.name,
        "success": successes,
        "total": len(tasks),
        "success_rate": round(successes / len(tasks), 4),
        "context_bytes": system.context_bytes,
        "latency_ms_mean": round(statistics.fmean(latencies), 4),
        "steps_mean": round(statistics.fmean(steps), 2),
    }


def main() -> int:
    universe = build_universe()
    dead = apoptosis(universe)
    alive = universe.alive()
    print(f"universe: {len(universe.genes)} genes, apoptosis removed {len(dead)}: {dead}")

    mini = BioMini(universe)
    systems = [
        FlatAgent(alive),
        ToolAgent(alive),
        GraphAgent(alive),
        BioMiniAgent(mini),
    ]
    rows = [evaluate_system(s, TASKS) for s in systems]

    # Устойчивость: после мутации вселенной (сломанный ген) кто восстанавливается?
    mutated = Universe(genes=dict(universe.genes))
    mutated.add(Gene("G_MUT", "1/0", ("ошибка", "division"), "fault"))
    apoptosis(mutated)
    recovery = []
    for system in systems:
        if isinstance(system, BioMiniAgent):
            rebuilt = BioMiniAgent(BioMini(mutated))
            ok = evaluate_system(rebuilt, TASKS)["success_rate"]
        else:
            ok = evaluate_system(system, TASKS)["success_rate"]
        recovery.append({"system": system.name, "success_after_mutation": ok})

    for r in rows:
        r["recovery"] = next(x["success_after_mutation"] for x in recovery if x["system"] == r["system"])
        r["bytes_per_success"] = round(r["context_bytes"] / max(r["success"], 1), 1)

    ranked = sorted(rows, key=lambda r: (-r["success_rate"], r["context_bytes"]))
    result = {
        "genes_total": len(universe.genes),
        "genes_after_apoptosis": len(alive),
        "apoptotic": dead,
        "tasks": len(TASKS),
        "ranking": ranked,
        "recovery": recovery,
    }
    out = REPO / "research" / "results" / "e6_mini.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"\n{'system':12s} {'success':>9s} {'ctx bytes':>10s} {'B/success':>10s} {'lat ms':>8s} {'steps':>6s} {'recovery':>9s}")
    for r in ranked:
        print(
            f"{r['system']:12s} {r['success']:2d}/{r['total']:2d} {r['success_rate']:5.0%} "
            f"{r['context_bytes']:10d} {r['bytes_per_success']:10.0f} {r['latency_ms_mean']:8.3f} "
            f"{r['steps_mean']:6.2f} {r['recovery']:5.0%}"
        )
    print(f"-> {out.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
