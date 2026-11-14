"""
E3 — Чистота контекстного окна: сколько байт RSoC действительно нужно агенту.

Задание спрашивает про «чистоту контекстного окна» и «скорость фильтрации». Это измеримо без
модели: пакет RSoC — детерминированный JSON фиксированной структуры, и у него есть
измеримый избыток.

Измеряем три величины для каждого узла:

* `serialized` — байты `compile_rsoc(uri)`, как сейчас отдаётся агенту;
* `informative` — минимальный объём, несущий все *различные* смысловые единицы (уникальные
  строки, дедуплицированные по нормализованной форме);
* `dedup_ratio` — какая доля пакета является повтором уже сказанного.

Отдельно: **избыточность между слоями**. В RSoC бимодальная компоновка кладёт одно и то же
правило в primacy-head и в recency-tail намеренно (это заявленный дизайн, LNTE). Вопрос не
«убрать ли», а «сколько это стоит в байтах» — чтобы решение было числом, а не мнением.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / ".isai"))

from isai.engine import compile_rsoc  # noqa: E402


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def walk_strings(obj, path: str = "") -> list[tuple[str, str]]:
    """Все строковые листья пакета с их путями — смысловые единицы контекста."""
    out: list[tuple[str, str]] = []
    if isinstance(obj, str):
        out.append((path, obj))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            out.extend(walk_strings(v, f"{path}.{k}" if path else str(k)))
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            out.extend(walk_strings(v, f"{path}[{i}]"))
    return out


def leaf_bytes(strings: list[tuple[str, str]]) -> int:
    return sum(len(v.encode("utf-8")) for _, v in strings)


def dedup(strings: list[tuple[str, str]]) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Разделить листья на уникальные и повторные по нормализованной форме."""
    seen: dict[str, tuple[str, str]] = {}
    unique: list[tuple[str, str]] = []
    dupes: list[tuple[str, str]] = []
    for path, value in strings:
        key = normalize(value)
        if not key:
            continue
        if key in seen:
            dupes.append((path, value))
        else:
            seen[key] = (path, value)
            unique.append((path, value))
    return unique, dupes


def primacy_recency_overlap(packet: dict) -> dict:
    """
    Явный замер бимодального дублирования: что из primacy-head повторено в recency-tail.

    Дизайн LNTE этого и требует, поэтому «избыточность» здесь — не дефект, а *цена*: её надо
    знать, чтобы сравнивать с альтернативой (только recency, только head).
    """
    head = packet.get("enforced_neuro_vascular_frame", {})
    tail = packet.get("terminal_execution_guard", {})
    head_text = json.dumps(head, ensure_ascii=False, sort_keys=True)
    tail_text = json.dumps(tail, ensure_ascii=False, sort_keys=True)
    head_norm = set(re.findall(r"[а-яёa-z_]{6,}", head_text.lower()))
    tail_norm = set(re.findall(r"[а-яёa-z_]{6,}", tail_text.lower()))
    shared = head_norm & tail_norm
    return {
        "head_bytes": len(head_text.encode("utf-8")),
        "tail_bytes": len(tail_text.encode("utf-8")),
        "shared_terms": len(shared),
        "head_terms": len(head_norm),
        "tail_terms": len(tail_norm),
        "overlap_ratio": round(len(shared) / max(len(head_norm | tail_norm), 1), 4),
        "sample_shared": sorted(shared)[:12],
    }


def main() -> int:
    from isai.graph_index import build_hypergraph_index

    index = build_hypergraph_index(REPO)
    uris = sorted(index.nodes) if index.nodes else ["isai://root"]

    rows = []
    for uri in uris:
        t0 = time.perf_counter()
        packet = compile_rsoc(REPO, uri)
        compile_ms = (time.perf_counter() - t0) * 1000
        serialized = len(json.dumps(packet, ensure_ascii=False).encode("utf-8"))
        strings = walk_strings(packet)
        unique, dupes = dedup(strings)
        rows.append(
            {
                "uri": uri,
                "serialized_bytes": serialized,
                "compile_ms": round(compile_ms, 3),
                "leaves": len(strings),
                "unique_leaves": len(unique),
                "duplicate_leaves": len(dupes),
                "informative_bytes": leaf_bytes(unique),
                "duplicate_bytes": leaf_bytes(dupes),
                "dedup_ratio": round(leaf_bytes(dupes) / max(leaf_bytes(strings), 1), 4),
                "section_overhead_bytes": serialized - leaf_bytes(strings),
                "bimodal": primacy_recency_overlap(packet),
                "sections": {k: len(json.dumps(v, ensure_ascii=False).encode("utf-8")) for k, v in packet.items()},
            }
        )

    # Замер фильтрации: сколько стоит выбрать релевантное подмножество из пакета.
    root_packet = compile_rsoc(REPO, "isai://root")
    root_strings = walk_strings(root_packet)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from universe import CorpusEmbedder, cosine

    embedder = CorpusEmbedder(dim=512).fit([v for _, v in root_strings])
    vectors = embedder.embed_many([v for _, v in root_strings])

    queries = [
        "гиперграф индекс связей",
        "реестр хроники событий",
        "результат набора контекста RSoC",
        "конституционный фрейм",
        "мутации вектора",
    ]
    filter_rows = []
    for q in queries:
        t0 = time.perf_counter()
        qv = embedder.embed(q)
        scored = sorted(((cosine(qv, v), i) for i, v in enumerate(vectors)), key=lambda x: -x[0])
        elapsed = (time.perf_counter() - t0) * 1000
        keep = scored[:8]
        kept_bytes = sum(len(root_strings[i][1].encode("utf-8")) for _, i in keep)
        total_bytes = leaf_bytes(root_strings)
        filter_rows.append(
            {
                "query": q,
                "total_leaf_bytes": total_bytes,
                "kept_leaf_bytes": kept_bytes,
                "compression": round(kept_bytes / max(total_bytes, 1), 4),
                "filter_ms": round(elapsed, 3),
                "top": [{"path": root_strings[i][0], "score": round(s, 4)} for s, i in keep[:3]],
            }
        )

    result = {
        "nodes": rows,
        "aggregate": {
            "serialized_bytes_total": sum(r["serialized_bytes"] for r in rows),
            "informative_bytes_total": sum(r["informative_bytes"] for r in rows),
            "mean_dedup_ratio": round(sum(r["dedup_ratio"] for r in rows) / max(len(rows), 1), 4),
            "mean_compile_ms": round(sum(r["compile_ms"] for r in rows) / max(len(rows), 1), 3),
        },
        "filtering": filter_rows,
    }
    out = REPO / "research" / "results" / "e3_context.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for r in rows:
        print(
            f"{r['uri']:22s} {r['serialized_bytes']:7d} B  unique {r['unique_leaves']:3d}/{r['leaves']:3d} "
            f"({r['dedup_ratio']:.0%} dup)  compile {r['compile_ms']:6.2f} ms  "
            f"bimodal overlap {r['bimodal']['overlap_ratio']:.0%}"
        )
    for f in filter_rows:
        print(f"filter {f['query'][:34]:36s} keeps {f['compression']:.1%} of leaves in {f['filter_ms']:.1f} ms")
    print(f"-> {out.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
