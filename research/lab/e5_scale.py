"""
E5 — Масштабируемость: где векторная логика перестаёт быть дешёвой.

Реальная система мала (5 узлов, 121 ребро, 298 сущностей). Вопрос задания — «скорость поиска»
и «скорость связи со вселенной» — имеет смысл только на будущих масштабах: биовселенная,
разрабатываемые сущности, десятки тысяч узлов.

Строим синтетические вселенные геометрически растущего размера и замеряем:

* построение индекса (fit + embed) — оффлайн, полный проход;
* разрешение одной связи — онлайн, O(N) по числу сущностей (сканирование);
* разрешение через инвертированный индекс термов — O(df) вместо O(N), то есть то, что
  делает поиск «векторно-дешёвым».

Проверяется не скорость Python, а **форма кривой**: если линейный скан упирается, а
инвертированный — нет, то ответ на «перспективно ли» зависит от того, какой механизм внедрять.
"""

from __future__ import annotations

import json
import math
import random
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from universe import CorpusEmbedder, cosine, tokenize

REPO = Path(__file__).resolve().parents[2]


VOCAB = [
    "конституц", "ядр", "вектор", "мутац", "хроник", "гиперграф", "индекс", "порт", "схем",
    "узел", "аудит", "шлюз", "контекст", "пакет", "аренд", "задач", "знани", "паттерн",
    "нейрон", "сосуд", "ткань", "ген", "плазмид", "рибосом", "эпох", "холон", "апоптоз",
    "связ", "ребро", "вершин", "поиск", "эмбеддинг", "косинус", "порог", "сходств",
    "структур", "дифф", "дайджест", "сигнатур", "роль", "уровен", "текст", "читател",
    "модель", "агент", "токен", "лексем", "смысл", "цель", "инвариант", "критерий",
]


def synth_entity(rng: random.Random, idx: int, vocab_size: int) -> tuple[str, str]:
    """
    Синтетическая сущность: 6-24 слова из словаря размера `vocab_size`.

    Размер словаря — управляющий параметр, и он оказался решающим: при 51 слове (первая версия)
    почти каждая сущность содержит почти каждый терм, инвертированный индекс выбирает 87%
    корпуса как кандидатов и не даёт никакого ускорения. Реальный корпус ведёт себя иначе —
    терминов тысячи, а постинги короткие. Поэтому словарь строится из слогов и растёт с N.
    """
    n = rng.randint(6, 24)
    if vocab_size <= len(VOCAB):
        words = [rng.choice(VOCAB) for _ in range(n)]
    else:
        syllables = ("ka", "ro", "mi", "tan", "vel", "zor", "lin", "qua", "pre", "sto", "nav", "hel")
        words = []
        for _ in range(n):
            if rng.random() < 0.5:
                words.append(rng.choice(VOCAB))
            else:
                words.append("".join(rng.choice(syllables) for _ in range(rng.randint(2, 4))))
    return f"isai://synth#Node{idx:06d}", " ".join(words)


def build(n: int, seed: int = 7, vocab_size: int = 0) -> tuple[list[str], list[str], CorpusEmbedder, list[tuple[float, ...]]]:
    rng = random.Random(seed)
    vocab_size = vocab_size or n * 4  # растёт с корпусом: как в реальной системе
    uris, texts = [], []
    for i in range(n):
        u, t = synth_entity(rng, i, vocab_size)
        uris.append(u)
        texts.append(t)
    t0 = time.perf_counter()
    embedder = CorpusEmbedder(dim=512).fit(texts)
    vectors = embedder.embed_many(texts)
    return uris, texts, embedder, vectors


def inverted_index(texts: list[str]) -> dict[str, list[int]]:
    inv: dict[str, list[int]] = defaultdict(list)
    for i, t in enumerate(texts):
        for tok in set(tokenize(t)):
            inv[tok].append(i)
    return inv


def scan_query(query: str, embedder, vectors) -> int:
    qv = embedder.embed(query)
    best = -1.0
    for v in vectors:
        s = cosine(qv, v)
        if s > best:
            best = s
    return 0


def inverted_query(query: str, inv: dict[str, list[int]], vectors) -> int:
    """
    Поиск через инвертированный индекс: кандидаты = объединение постингов термов запроса.
    Сканируются только они, а не вся вселенная.
    """
    from universe import _hash_bucket  # noqa: PLC0415

    candidates: set[int] = set()
    for tok in tokenize(query):
        candidates.update(inv.get(tok, ()))
    qv_hash = tokenize(query)
    acc = [0.0] * 512
    for tok in qv_hash:
        b, sign = _hash_bucket(tok, 512)
        acc[b] += sign
    norm = math.sqrt(sum(x * x for x in acc)) or 1.0
    qv = [x / norm for x in acc]
    best = -1.0
    for i in candidates:
        s = cosine(qv, vectors[i])
        if s > best:
            best = s
    return len(candidates)


def main() -> int:
    sizes = [100, 500, 1000, 2500, 5000]
    rows = []
    for n in sizes:
        uris, texts, embedder, vectors = build(n)
        t0 = time.perf_counter()
        inv = inverted_index(texts)
        inv_build_ms = (time.perf_counter() - t0) * 1000
        queries = [texts[i][:60] for i in range(0, n, max(1, n // 20))][:20]

        t0 = time.perf_counter()
        for q in queries:
            scan_query(q, embedder, vectors)
        scan_ms = (time.perf_counter() - t0) * 1000 / len(queries)

        t0 = time.perf_counter()
        cand_total = 0
        for q in queries:
            cand_total += inverted_query(q, inv, vectors)
        inv_ms = (time.perf_counter() - t0) * 1000 / len(queries)

        rows.append(
            {
                "entities": n,
                "index_bytes_est": n * 512 * 4,
                "inverted_terms": len(inv),
                "inverted_build_ms": round(inv_build_ms, 2),
                "scan_query_ms": round(scan_ms, 3),
                "inverted_query_ms": round(inv_ms, 3),
                "speedup": round(scan_ms / max(inv_ms, 1e-9), 2),
                "mean_candidates": round(cand_total / len(queries), 1),
                "candidate_ratio": round(cand_total / len(queries) / n, 4),
            }
        )
        print(
            f"N={n:5d}  scan {scan_ms:8.3f} ms  inverted {inv_ms:7.3f} ms "
            f"x{rows[-1]['speedup']:6.1f}  candidates {rows[-1]['mean_candidates']:6.1f} "
            f"({rows[-1]['candidate_ratio']:.2%})  inv_build {inv_build_ms:7.1f} ms"
        )

    # Экстраполяция: линейный скан на 100k сущностей.
    if len([r for r in rows if "scan_query_ms" in r]) >= 2:
        last = [r for r in rows if "scan_query_ms" in r][-1]
        per_entity_ms = last["scan_query_ms"] / last["entities"]
        rows.append(
            {
                "entities": 100_000,
                "extrapolated_scan_query_ms": round(per_entity_ms * 100_000, 1),
                "extrapolated_inverted_query_ms": round(
                    last["inverted_query_ms"] * (last["candidate_ratio"] or 1e-9), 3
                ),
                "note": "candidates grow with document frequency; the inverted index wins only if df << N",
            }
        )
        print(
            f"extrapolated N=100000: scan ~{per_entity_ms*100000:.0f} ms, "
            f"inverted ~{last['inverted_query_ms']:.1f} ms (candidates grow with df)"
        )

    out = REPO / "research" / "results" / "e5_scale.json"
    out.write_text(json.dumps({"rows": rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"-> {out.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
