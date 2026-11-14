"""
E2 — Экономичность и самодостаточность: сколько стоит векторная логика.

Три вопроса, каждый — измерение, а не оценка:

1. **Зависимости.** Что нужно, чтобы логика заработала: сколько пакетов и байт. В песочнице
   huggingface недоступен, поэтому нейросетевые веса физически недостижимы — это первый и самый
   жёсткий результат (R-01). Здесь он квантифицируется.

2. **Диск.** Сколько стоит хранимый индекс: 512-мерный float32 на сущность против инвертированного
   словаря термов. Второй вариант дешевле на порядки, но теряет часть семантики.

3. **CPU.** Стоимость построения и запроса на реальном корпусе — в миллисекундах и в отношении
   к бюджету одного хода агента.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from universe import CorpusEmbedder, cosine, tokenize

REPO = Path(__file__).resolve().parents[2]


def disk_footprint(repo_root: Path) -> dict:
    """Размер `.venv` и его разложение: что уже стоит на диске ради самого ядра."""
    venv = repo_root / ".venv"
    if not venv.is_dir():
        return {"present": False}

    def size_of(path: Path) -> int:
        total = 0
        for p in path.rglob("*"):
            if p.is_file():
                try:
                    total += p.stat().st_size
                except OSError:
                    pass
        return total

    site = venv / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"
    packages = {}
    if site.is_dir():
        for entry in sorted(site.iterdir()):
            if entry.is_dir() and not entry.name.endswith((".dist-info", ".egg-info")):
                packages[entry.name] = size_of(entry)
    heavy = dict(sorted(packages.items(), key=lambda kv: -kv[1])[:12])
    return {
        "present": True,
        "venv_bytes": size_of(venv),
        "site_packages_count": len(packages),
        "heaviest": {k: v for k, v in heavy.items()},
        "torch_present": (site / "torch").is_dir(),
        "torch_bytes": packages.get("torch", 0),
        "numpy_bytes": packages.get("numpy", 0),
        "sklearn_bytes": packages.get("sklearn", 0),
    }


def index_disk_cost(entities: int, dim: int = 512, terms: int = 0) -> dict:
    """Аналитическая стоимость хранения: float32-матрица против постингов термов."""
    dense = entities * dim * 4
    # Постинг: 4 байта на запись + ~9 байт накладных на терм (длина + смещение).
    inverted = terms * (4 * max(1, entities // max(terms, 1))) + terms * 9 if terms else 0
    return {
        "entities": entities,
        "dim": dim,
        "dense_bytes": dense,
        "dense_mb": round(dense / 1e6, 2),
        "inverted_bytes_est": inverted,
        "inverted_mb": round(inverted / 1e6, 2),
        "ratio": round(dense / inverted, 2) if inverted else None,
    }


def cpu_cost() -> dict:
    """Стоимость на реальном корпусе: fit, embed, запрос, разрешение связи."""
    from universe import load_universe

    t0 = time.perf_counter()
    entities = load_universe(REPO)
    load_ms = (time.perf_counter() - t0) * 1000
    texts = [e.text for e in entities]

    t0 = time.perf_counter()
    embedder = CorpusEmbedder(dim=512).fit(texts)
    fit_ms = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    vectors = embedder.embed_many(texts)
    embed_ms = (time.perf_counter() - t0) * 1000

    queries = [e.text[:80] for e in entities[:40]]
    t0 = time.perf_counter()
    for q in queries:
        qv = embedder.embed(q)
        for v in vectors[:100]:
            cosine(qv, v)
    query_ms = (time.perf_counter() - t0) * 1000 / len(queries)

    terms = {t for t in embedder.idf}
    return {
        "entities": len(entities),
        "load_ms": round(load_ms, 2),
        "fit_ms": round(fit_ms, 2),
        "embed_all_ms": round(embed_ms, 2),
        "embed_per_entity_ms": round(embed_ms / max(len(entities), 1), 4),
        "resolve_100_ms": round(query_ms, 4),
        "vocabulary_terms": len(terms),
        "dense_bytes_actual": len(vectors) * 512 * 4,
    }


def main() -> int:
    disk = disk_footprint(REPO)
    cpu = cpu_cost()
    scale = [index_disk_cost(n, 512, terms=max(100, n // 3)) for n in (298, 1_000, 10_000, 100_000)]

    result = {"disk": disk, "cpu": cpu, "index_scaling": scale}
    out = REPO / "research" / "results" / "e2_cost.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"venv: {disk.get('venv_bytes', 0)/1e6:.0f} MB in {disk.get('site_packages_count')} packages")
    if disk.get("present"):
        for name, size in list(disk["heaviest"].items())[:6]:
            print(f"   {name:24s} {size/1e6:8.1f} MB")
        print(f"   torch present: {disk['torch_present']} ({disk['torch_bytes']/1e6:.0f} MB)")
    print(
        f"cpu: load {cpu['load_ms']:.0f} ms, fit {cpu['fit_ms']:.0f} ms, "
        f"embed {cpu['embed_all_ms']:.0f} ms ({cpu['embed_per_entity_ms']*1000:.0f} us/entity), "
        f"resolve-100 {cpu['resolve_100_ms']:.2f} ms"
    )
    for s in scale:
        print(
            f"  N={s['entities']:6d} dim={s['dim']} dense {s['dense_mb']:7.2f} MB vs "
            f"inverted {s['inverted_mb']:6.2f} MB (x{s['ratio']})"
        )
    print(f"-> {out.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
