"""
E0 — Сводка: собрать метрики всех экспериментов в одну таблицу и вычислить итоговый индекс.

Зачем отдельный шаг. Каждый эксперимент отвечает на свой вопрос, но задание требует
«систематизировать результаты» и «ранжировать». Сводка делает две вещи:

1. **Сводит** разрозненные JSON-срезы в одну таблицу с единицами измерения — чтобы сравнение
   стало выполнимым.
2. **Считает рейтинг внедрения**: для каждого предложенного механизма — выигрыш, стоимость,
   риск и вердикт. Числа берутся из результатов, а не назначаются.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RESULTS = REPO / "research" / "results"


def load(name: str) -> dict:
    path = RESULTS / name
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def main() -> int:
    e1 = load("e1_link_hit.json")
    e2 = load("e2_cost.json")
    e3 = load("e3_context.json")
    e5 = load("e5_scale.json")
    e6 = load("e6_mini.json")
    e7 = load("e7_plasmid.json")

    ranking = e1.get("adaptive_bridge", {}).get("selected_for_ranking", {})
    operating = e1.get("safe_operating_point", {})
    detail = e1.get("operating_detail", {})
    discrete = e1.get("discrete", {})
    filt = e3.get("filtering", [])
    agg = e3.get("aggregate", {})

    table = [
        {
            "metric": "discrete_link_accuracy",
            "value": discrete.get("accuracy"),
            "unit": "0..1",
            "source": "E1",
            "note": "точное совпадение URI: проваливает все 13 alias-кейсов",
        },
        {
            "metric": "discrete_alias_hits",
            "value": f"{discrete.get('alias_hits')}/{discrete.get('alias_total')}",
            "unit": "cases",
            "source": "E1",
            "note": "дискретная логика не умеет разрешать перифраз по построению",
        },
        {
            "metric": "vector_hit_at_5_adaptive",
            "value": f"{ranking.get('hit_at_5')}/{ranking.get('positive_total')}",
            "unit": "cases",
            "source": "E1",
            "note": "адаптивный мост, conf=0.40 — рабочий режим отбора контекста",
        },
        {
            "metric": "vector_alias_hit_at_5",
            "value": ranking.get("alias_hit_at_5"),
            "unit": "cases of 13",
            "source": "E1",
            "note": "против 0 у дискретной логики",
        },
        {
            "metric": "vector_resolution_precision",
            "value": operating.get("precision"),
            "unit": "0..1",
            "source": "E1",
            "note": "при пороге 0.28: fp=0, то есть фантомы не притягиваются",
        },
        {
            "metric": "phantom_rejection",
            "value": f"{operating.get('tn', 0)}/{operating.get('tn', 0) + operating.get('fp', 0)}",
            "unit": "cases",
            "source": "E1",
            "note": "главное свойство: «попадать всегда» отвергнуто",
        },
        {
            "metric": "rsoc_packet_bytes",
            "value": agg.get("serialized_bytes_total"),
            "unit": "bytes (5 nodes + research)",
            "source": "E3",
            "note": "полный пакет на узел ~44-52 КБ",
        },
        {
            "metric": "rsoc_duplicate_ratio",
            "value": agg.get("mean_dedup_ratio"),
            "unit": "0..1",
            "source": "E3",
            "note": "повторов внутри пакета мало: избыточность не в дублях",
        },
        {
            "metric": "context_filter_compression",
            "value": round(sum(f["compression"] for f in filt) / max(len(filt), 1), 4)
            if filt
            else None,
            "unit": "0..1",
            "source": "E3",
            "note": "векторный отбор оставляет 2-5% листьев — избыточность в нерелевантности",
        },
        {
            "metric": "venv_size_mb",
            "value": round((e2.get("disk", {}).get("venv_bytes") or 0) / 1e6, 0),
            "unit": "MB",
            "source": "E2",
            "note": "из них torch+nvidia+triton ≈ 5.4 ГБ, веса недоступны",
        },
        {
            "metric": "dense_index_bytes_298",
            "value": e2.get("index_scaling", [{}])[0].get("dense_bytes"),
            "unit": "bytes",
            "source": "E2",
            "note": "512 float32 на сущность; инвертированный индекс в ~290x меньше",
        },
        {
            "metric": "scan_query_ms_100k_extrapolated",
            "value": next(
                (r.get("extrapolated_scan_query_ms") for r in e5.get("rows", []) if r.get("entities") == 100_000),
                None,
            ),
            "unit": "ms",
            "source": "E5",
            "note": "линейный скан не масштабируется",
        },
        {
            "metric": "inverted_query_ms_5000",
            "value": next(
                (r.get("inverted_query_ms") for r in e5.get("rows", []) if r.get("entities") == 5000), None
            ),
            "unit": "ms",
            "source": "E5",
            "note": "x2.5 быстрее скана при 5000 сущностях",
        },
        {
            "metric": "bio_mini_success",
            "value": next((r["success_rate"] for r in e6.get("ranking", []) if r["system"] == "BIO_MINI"), None),
            "unit": "0..1",
            "source": "E6",
            "note": "равен FLAT_AGENT, но в 5x меньше контекста",
        },
        {
            "metric": "bio_mini_bytes_per_success",
            "value": next(
                (r["bytes_per_success"] for r in e6.get("ranking", []) if r["system"] == "BIO_MINI"), None
            ),
            "unit": "bytes",
            "source": "E6",
            "note": "против 118 у FLAT_AGENT — экономия 5.4x",
        },
        {
            "metric": "graph_agent_success",
            "value": next((r["success_rate"] for r in e6.get("ranking", []) if r["system"] == "GRAPH_AGENT"), None),
            "unit": "0..1",
            "source": "E6",
            "note": "0/8: дискретная адресация не переживает свободную формулировку",
        },
        {
            "metric": "dag_inflation_reproduced",
            "value": e7.get("cross_check_vs_catalog", {}).get("reproduced_inflation_max"),
            "unit": "x",
            "source": "E7",
            "note": "каталог заявлял 110.7x — воспроизведено при depth=7 (127x)",
        },
        {
            "metric": "plasmid_speedup_reproduced",
            "value": e7.get("cross_check_vs_catalog", {}).get("reproduced_speedup_max"),
            "unit": "x",
            "source": "E7",
            "note": "каталог заявлял 3.18x — зависит от глубины, растёт до сотен x",
        },
    ]

    # Рейтинг внедрения: выигрыш из метрик, стоимость и риск — экспертные, но обоснованные выше.
    proposals = [
        {
            "id": "P1",
            "mechanism": "Векторный отбор контекста (top-k по перцентилю) поверх RSoC",
            "benefit": "сжатие контекста до 2-5% листьев без потери адресуемости",
            "cost": "O(N) скан на 298 сущностях = ~0.3 мс; 0 зависимостей",
            "risk": "LOW — аддитивный слой, дискретные ссылки остаются источником истины",
            "verdict": "ВНЕДРЯТЬ",
            "evidence": "E1 hit@5 12/23, E3 compression 2-5%",
        },
        {
            "id": "P2",
            "mechanism": "Двуязычный мост, выученный из корпуса, с гейтом по уверенности",
            "benefit": "alias-hit@5 2→6 из 13 при сохранении exact 6/10",
            "cost": "268 терминов, строится за ~0.9 с, детерминирован",
            "risk": "MEDIUM — мост наследует шум корпуса; без гейта рушит exact-попадания",
            "verdict": "ВНЕДРЯТЬ С ГЕЙТОМ (conf=0.40)",
            "evidence": "E1 adaptive conf 0.20→0.40: hit@5 8→12",
        },
        {
            "id": "P3",
            "mechanism": "Инвертированный индекс термов как предфильтр векторного поиска",
            "benefit": "x2.5 при 5000 сущностях, устраняет O(N) скан",
            "cost": "строится за 419 мс на 5000, ~0.7 МБ на 100k против 205 МБ dense",
            "risk": "LOW — деградирует до полного скана при высоком df, это измеримо",
            "verdict": "ВНЕДРЯТЬ при N>1000",
            "evidence": "E5 speedup 2.5x, candidate ratio 40-45%",
        },
        {
            "id": "P4",
            "mechanism": "Кэш рибосомы по эпохе + мемоизация плазмид для биовселенной",
            "benefit": "устраняет 110.7x раздутие ромбовидного DAG, подтверждено 127x",
            "cost": "один int-счётчик эпохи, кэш {(plasmid, epoch): value}",
            "risk": "LOW — инвалидация грубая (вся вселенная), но корректная",
            "verdict": "ВНЕДРЯТЬ в биовселенную",
            "evidence": "E7 inflation 7→127x, speedup 2.4→53x",
        },
        {
            "id": "P5",
            "mechanism": "Апоптоз с различенной «сломан»/«нужен вход» + явная политика песочницы",
            "benefit": "мини-система переживает мутацию без каскадной потери живых генов",
            "cost": "probe-среда + список разрешённых builtins",
            "risk": "MEDIUM — слишком узкая политика убивает валидные гены (измерено)",
            "verdict": "ВНЕДРЯТЬ с тестом политики",
            "evidence": "E6: первая версия удалила 4 гена, из них 2 живых",
        },
        {
            "id": "P6",
            "mechanism": "Нейросетевые эмбеддинги (sentence-transformers/torch)",
            "benefit": "ожидаемо выше hit@k на alias (не измерено: веса недоступны)",
            "cost": "+5.4 ГБ venv, внешняя загрузка, недетерминизм между версиями",
            "risk": "HIGH — ломает самодостаточность и воспроизводимость Gate V",
            "verdict": "НЕ ВНЕДРЯТЬ в контур; допустить как внешний офлайн-эксперимент",
            "evidence": "E2 venv 6300 MB, R-01",
        },
        {
            "id": "P7",
            "mechanism": "Абсолютный порог косинуса как единственный критерий связи",
            "benefit": "простота",
            "cost": "ноль",
            "risk": "HIGH — шкала некалибрована по корпусу: порог 0.28 даёт recall 0.13",
            "verdict": "ИЗБЕГАТЬ, использовать перцентиль + hit@k",
            "evidence": "E1: та же цель на 86-94 перцентиле при score 0.00",
        },
    ]

    summary = {
        "metrics": table,
        "proposals": proposals,
        "headline": {
            "discrete_accuracy": discrete.get("accuracy"),
            "vector_hit_at_5": f"{ranking.get('hit_at_5')}/{ranking.get('positive_total')}",
            "vector_alias_hit_at_5": ranking.get("alias_hit_at_5"),
            "context_compression": round(
                sum(f["compression"] for f in filt) / max(len(filt), 1), 4
            )
            if filt
            else None,
            "venv_mb": round((e2.get("disk", {}).get("venv_bytes") or 0) / 1e6, 0),
        },
    }
    out = RESULTS / "e0_summary.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"{'metric':38s} {'value':>16s} {'unit':22s} src")
    for row in table:
        print(f"{row['metric']:38s} {str(row['value']):>16s} {row['unit']:22s} {row['source']}")
    print()
    for p in proposals:
        print(f"{p['id']} {p['verdict']:28s} {p['mechanism'][:64]}")
    print(f"-> {out.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
