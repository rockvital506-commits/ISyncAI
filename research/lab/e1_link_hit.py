"""
E1 — Попадание связей в сущности вселенной: дискретные ссылки против векторных.

Главный вопрос задания: перспективна ли векторная логика со **100% попаданием** связей
сущности в сущность/сущности вселенной?

Метод. Связь — это реальное ребро декларированного гиперграфа ISAI (`isai://a -> isai://b`).
«Попадание» — резолвится ли цель связи в живую сущность.

Режимы:

* **DISCRETE** — как в ISAI сегодня: строгое равенство URI. Промах = промах.
* **VECTOR** — цель разрешается по смыслу: ближайший сосед по эмбеддингу, засчитывается при
  сходстве выше порога. Порог — это и есть механизм, отличающий попадание от притягивания.

Классы трудности:

* `exact`   — цель дословно существует (дискретная ссылка обязана справиться);
* `alias`   — цель названа словами, а не URI. Дискретная ссылка промахивается *всегда*;
* `phantom` — цели не существует. Правильный ответ — отказ: связь надо отклонить, а не
  «притянуть» к похожему. Это главный класс: проверка, которая «попадает всегда», вредна
  ровно тем, что попадает и туда, куда попадать нельзя.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from universe import (
    CorpusEmbedder,
    Entity,
    cosine,
    expand_query_bilingual,
    expand_query_if_weak,
    learn_bilingual_bridge,
    load_universe,
)

REPO = Path(__file__).resolve().parents[2]


@dataclass
class LinkCase:
    source: str
    target: str
    expected_uri: str | None
    difficulty: str
    note: str = ""


#: Тексты-«превью» для сущностей-документов: заголовок + первый осмысленный раздел.
#: Длинный документ, взятый целиком, размывает вектор до средней температуры корпуса —
#: это отдельный измеренный эффект (см. RESULTS.md, R-02).
TITLE_ONLY_KINDS = {"document", "vector", "node"}


def preview_text(entity: Entity) -> str:
    """Смысловое ядро сущности: для длинных текстов — заголовок и первые строки содержания."""
    if entity.kind in TITLE_ONLY_KINDS and len(entity.text) > 600:
        lines = [ln for ln in entity.text.splitlines() if ln.strip()]
        head = " ".join(lines[:12])
        return head[:800]
    return entity.text


def build_cases(entities: list[Entity]) -> list[LinkCase]:
    """
    Кейсы собраны из живого корпуса, не выдуманы.

    `alias` — это то, как сущность *называется в речи системы*: названия её собственных
    записей каталога, формулировки её докстрингов, пассажи её паспорта. Придуманный перифраз
    проверял бы меня, а не систему.
    """
    known = {e.uri for e in entities}
    cases: list[LinkCase] = []

    declared = [
        ("isai://knowledge", "isai://root#GenesisKernel"),
        ("isai://knowledge", "isai://root#RSoCCompiler"),
        ("isai://knowledge", "isai://root#ChronicleLedger"),
        ("isai://root", "isai://user#OperatorProfile"),
        ("isai://root", "isai://root#MasterVector"),
        ("isai://root", "isai://root#HypergraphIndex"),
        ("isai://tasks", "isai://knowledge"),
        ("isai://tests", "isai://root"),
        ("isai://knowledge", "isai://root#VectorMutationLedger"),
        ("isai://knowledge", "isai://root#LinkInjector"),
    ]
    for src, tgt in declared:
        if tgt in known:
            cases.append(LinkCase(src, tgt, tgt, "exact"))

    alias_specs = [
        ("гиперграф EAVT VAET индекс", "isai://root#HypergraphIndex"),
        ("однопроходная индексация связей без ручных обратных ссылок", "isai://root#HypergraphIndex"),
        ("реестр хроники событий", "isai://root#ChronicleLedger"),
        ("неизменяемый конституционный фрейм ядра", "isai://root#GenesisKernel"),
        ("нервно-сосудистый фундаментал", "isai://root#NeuroVascularFundamental"),
        ("мастер вектор целей и ориентиров", "isai://root#MasterVector"),
        ("транзакционный инжектор связей AST", "isai://root#LinkInjector"),
        ("компилятор результирующего набора контекста", "isai://root#RSoCCompiler"),
        ("атомарная запись файла через fsync и os.replace", "isai://root#atomic_write_bytes"),
        ("реестр мутаций вектора с нумерованной ратификацией", "isai://root#VectorMutationLedger"),
        ("аудит контрактов и связей репозитория", "isai://root#audit_repository"),
        ("профиль и калибровка оператора", "isai://user#OperatorProfile"),
        ("сторожевой таймер задач с арендами", "isai://tasks#WatchdogService"),
    ]
    for phrase, expected in alias_specs:
        if expected in known:
            cases.append(LinkCase("isai://root", phrase, expected, "alias", note=phrase))

    for name in (
        "isai://root#QuantumFluxGate",
        "isai://root#NeuroVascularSupervisor",
        "isai://root#ChronicleCompactor",
        "isai://root#SemanticLinkResonator",
    ):
        cases.append(LinkCase("isai://root", name, None, "phantom"))

    return cases


def resolve_discrete(target: str, known: set[str]) -> str | None:
    return target if target in known else None


def resolve_vector(
    target: str,
    embedder: CorpusEmbedder,
    entities: list[Entity],
    vectors: list[tuple[float, ...]],
    threshold: float,
) -> tuple[str | None, float, str]:
    q = embedder.embed(target)
    best_i, best_s = max(enumerate(cosine(q, v) for v in vectors), key=lambda iv: iv[1])
    nearest = entities[best_i].uri
    return (nearest if best_s >= threshold else None), best_s, nearest


def evaluate(
    embedder: CorpusEmbedder,
    entities: list[Entity],
    vectors: list[tuple[float, ...]],
    cases: list[LinkCase],
    threshold: float,
) -> dict:
    tp = fp = fn = tn = 0
    hit5 = hit10 = 0
    alias_hit5 = exact_hit5 = 0
    positive_total = 0
    alias_hits = alias_total = exact_hits = exact_total = phantom_rejected = 0
    wrong_target = 0
    latencies: list[float] = []
    rows: list[dict] = []
    for c in cases:
        t0 = time.perf_counter()
        got, score, nearest = resolve_vector(c.target, embedder, entities, vectors, threshold)
        latencies.append(time.perf_counter() - t0)
        # Rank-based метрика (отбор контекста): попала ли цель в top-k независимо от порога.
        if c.expected_uri is not None:
            positive_total += 1
            ranked = sorted(
                ((cosine(embedder.embed(c.target), v), entities[i].uri) for i, v in enumerate(vectors)),
                key=lambda x: -x[0],
            )
            if any(u == c.expected_uri for _, u in ranked[:5]):
                hit5 += 1
                alias_hit5 += int(c.difficulty == "alias")
                exact_hit5 += int(c.difficulty == "exact")
            if any(u == c.expected_uri for _, u in ranked[:10]):
                hit10 += 1
        if c.expected_uri is None:
            if got is None:
                tn += 1
                phantom_rejected += 1
            else:
                fp += 1
        else:
            if got == c.expected_uri:
                tp += 1
            elif got is None:
                fn += 1
            else:
                fn += 1
                wrong_target += 1
        if c.difficulty == "alias":
            alias_total += 1
            alias_hits += int(got == c.expected_uri)
        if c.difficulty == "exact":
            exact_total += 1
            exact_hits += int(got == c.expected_uri)
        rows.append(
            {
                "target": c.target,
                "difficulty": c.difficulty,
                "expected": c.expected_uri,
                "resolved": got,
                "nearest": nearest,
                "score": round(score, 4),
                "ok": got == c.expected_uri,
            }
        )
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    return {
        "threshold": threshold,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(2 * precision * recall / (precision + recall), 4) if (precision + recall) else 0.0,
        "alias_hits": alias_hits,
        "alias_total": alias_total,
        "exact_hits": exact_hits,
        "exact_total": exact_total,
        "phantom_rejected": phantom_rejected,
        "wrong_target": wrong_target,
        "latency_ms_mean": round(1000 * sum(latencies) / len(latencies), 4),
        "hit_at_5": hit5,
        "hit_at_10": hit10,
        "positive_total": positive_total,
        "alias_hit_at_5": alias_hit5,
        "exact_hit_at_5": exact_hit5,
        "rows": rows,
    }


def evaluate_with_bridge(
    embedder: CorpusEmbedder,
    entities: list[Entity],
    vectors: list[tuple[float, ...]],
    cases: list[LinkCase],
    threshold: float,
    bridge: dict[str, list[str]],
) -> dict:
    """Тот же замер, но запрос расширяется двуязычным мостом из корпуса."""
    expanded_cases = [
        LinkCase(c.source, expand_query_bilingual(c.target, bridge), c.expected_uri, c.difficulty, c.note)
        for c in cases
    ]
    return evaluate(embedder, entities, vectors, expanded_cases, threshold)


def main() -> int:
    entities = load_universe(REPO)
    texts = [preview_text(e) for e in entities]
    known = {e.uri for e in entities}
    cases = build_cases(entities)
    embedder = CorpusEmbedder(dim=512).fit(texts)
    vectors = embedder.embed_many(texts)

    discrete_rows = []
    discrete_hits = 0
    for c in cases:
        got = resolve_discrete(c.target, known)
        ok = got == c.expected_uri
        discrete_hits += int(ok)
        discrete_rows.append(
            {
                "target": c.target,
                "difficulty": c.difficulty,
                "expected": c.expected_uri,
                "resolved": got,
                "ok": ok,
            }
        )

    sweep = [
        evaluate(embedder, entities, vectors, cases, round(0.02 * i, 2))
        for i in range(1, 31)
    ]
    for row in sweep:
        row.pop("rows", None)
    best = max(sweep, key=lambda r: (r["f1"], r["precision"]))
    safe = [r for r in sweep if r["fp"] == 0]
    operating = max(safe, key=lambda r: r["recall"]) if safe else best
    detail = evaluate(embedder, entities, vectors, cases, operating["threshold"])

    # Тот же порог, но с двуязычным мостом: единственное отличие — расширение запроса.
    bridge = learn_bilingual_bridge(REPO, max_terms=800)
    bridged_sweep = [
        {k: v for k, v in evaluate_with_bridge(
            embedder, entities, vectors, cases, round(0.02 * i, 2), bridge).items() if k != "rows"}
        for i in range(1, 31)
    ]
    bridged_at_operating = evaluate_with_bridge(
        embedder, entities, vectors, cases, operating["threshold"], bridge)
    bridged_rows = bridged_at_operating.pop("rows")

    # Адаптивный режим: мост включается только при неуверенном прямом поиске (R-09).
    def adaptive_eval(confidence: float) -> dict:
        adapted = []
        expanded_count = 0
        for c in cases:
            q, did = expand_query_if_weak(
                c.target, bridge, embedder, vectors, confidence=confidence,
                ambiguity_limit=8, min_word_len=5, max_reverse_terms=8,
            )
            expanded_count += int(did)
            adapted.append(LinkCase(c.source, q, c.expected_uri, c.difficulty, c.note))
        row = evaluate(embedder, entities, vectors, adapted, operating["threshold"])
        row["expanded_queries"] = expanded_count
        return {k: v for k, v in row.items() if k != "rows"}

    adaptive = {str(c): adaptive_eval(c) for c in (0.20, 0.30, 0.40, 0.50)}
    best_adaptive_key = max(adaptive, key=lambda k: (adaptive[k]["tp"], -adaptive[k]["fp"]))

    # Сквозной выбор точки: оптимум по hit@5 при fp=0. Абсолютный порог отвечает на вопрос
    # «можно ли доверять резолву связи», hit@k — «стоит ли брать это в контекст». Два разных
    # применения требуют двух разных калибровок, и оптимум по hit@5 — conf=0.40 (R-09).
    def overall(row: dict) -> tuple[int, int]:
        return (row["hit_at_5"], -row["fp"])

    best_overall_conf = max(adaptive, key=lambda k: overall(adaptive[k]))
    # Ранжированный выбор: порог задаёт *отбор* (top-k), а не разрешение связи.
    ranked_choice = {
        "confidence": float(best_overall_conf),
        "hit_at_5": adaptive[best_overall_conf]["hit_at_5"],
        "positive_total": adaptive[best_overall_conf]["positive_total"],
        "alias_hit_at_5": adaptive[best_overall_conf]["alias_hit_at_5"],
        "exact_hit_at_5": adaptive[best_overall_conf]["exact_hit_at_5"],
        "fp": adaptive[best_overall_conf]["fp"],
        "expanded_queries": adaptive[best_overall_conf]["expanded_queries"],
    }

    result = {
        "corpus": {
            "entities": len(entities),
            "cases": len(cases),
            "by_difficulty": {
                d: sum(1 for c in cases if c.difficulty == d) for d in ("exact", "alias", "phantom")
            },
            "by_kind": {},
        },
        "discrete": {
            "hits": discrete_hits,
            "total": len(cases),
            "accuracy": round(discrete_hits / len(cases), 4),
            "alias_hits": sum(1 for r in discrete_rows if r["difficulty"] == "alias" and r["ok"]),
            "alias_total": sum(1 for r in discrete_rows if r["difficulty"] == "alias"),
            "rows": discrete_rows,
        },
        "vector_sweep": sweep,
        "best_f1": best,
        "safe_operating_point": operating,
        "operating_detail": detail,
        "bilingual_bridge": {
            "terms_learned": len(bridge),
            "sample": {k: bridge[k] for k in list(bridge)[:12]},
        },
        "vector_with_bridge_sweep": bridged_sweep,
        "bridge_at_operating_point": bridged_at_operating,
        "bridge_rows": bridged_rows,
        "adaptive_bridge": {
            "by_confidence": adaptive,
            "selected_for_resolution": adaptive[best_adaptive_key],
            "selected_for_ranking": ranked_choice,
            "note": "резолв связи выбирает precision (порог); отбор контекста выбирает hit@k",
        },
    }
    for e in entities:
        result["corpus"]["by_kind"][e.kind] = result["corpus"]["by_kind"].get(e.kind, 0) + 1

    out = REPO / "research" / "results" / "e1_link_hit.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"corpus: {len(entities)} entities {result['corpus']['by_kind']}, {len(cases)} cases "
          f"{result['corpus']['by_difficulty']}")
    print(f"DISCRETE: accuracy {result['discrete']['accuracy']:.1%} "
          f"({discrete_hits}/{len(cases)}), alias {result['discrete']['alias_hits']}/{result['discrete']['alias_total']}")
    print(f"VECTOR best F1 {best['f1']:.3f} @ {best['threshold']} "
          f"(P={best['precision']:.2f} R={best['recall']:.2f} alias {best['alias_hits']}/{best['alias_total']} "
          f"exact {best['exact_hits']}/{best['exact_total']} fp={best['fp']})")
    print(f"VECTOR safe (fp=0): th={operating['threshold']} R={operating['recall']:.2f} "
          f"alias {operating['alias_hits']}/{operating['alias_total']} "
          f"exact {operating['exact_hits']}/{operating['exact_total']} "
          f"phantom_rejected {operating['phantom_rejected']}/{operating['tn']+operating['fp']}")
    print(f"VECTOR+BRIDGE @ same th={operating['threshold']}: R={bridged_at_operating['recall']:.2f} "
          f"alias {bridged_at_operating['alias_hits']}/{bridged_at_operating['alias_total']} "
          f"exact {bridged_at_operating['exact_hits']}/{bridged_at_operating['exact_total']} "
          f"fp={bridged_at_operating['fp']} (bridge terms: {len(bridge)})")
    sel = adaptive[best_adaptive_key]
    print(f"VECTOR+ADAPTIVE BRIDGE conf={best_adaptive_key}: tp={sel['tp']} fp={sel['fp']} "
          f"alias {sel['alias_hits']}/{sel['alias_total']} exact {sel['exact_hits']}/{sel['exact_total']} "
          f"expanded {sel['expanded_queries']}/{len(cases)}")
    print(f"-> {out.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
