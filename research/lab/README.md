# Измерительный стенд (Embedding Lab Harness)

<!-- ISAI:SYNC:BEGIN -->
<!-- isai:node_id=isai://research/lab -->
<!-- isai:spec_digest=eb4ec4bef390a40546a289267f60c9fd333832b31dd529d16dd9cbd380a9e9bf -->
<!-- isai:interface_digest=687f66477a709687e11d218e295bec23e0e850733b28fc54f1593467076b09b5 -->

## Паспорт узла `isai://research/lab` — Измерительный стенд (Embedding Lab Harness)

- **Уровень целостности:** `IL_2_CANONICAL` | **Видимость:** `PUBLIC`
- **Родительский узел:** `isai://research`
- **Цель (`Goal`):** Содержать исполняемые эксперименты E1..E7 по векторной логике связей: загрузчик вселенной, корпусный эмбеддер, метрики попадания, чистоты контекста, экономичности и масштабируемости.

### Критерии успеха (`Success Criteria`)
- Каждый эксперимент воспроизводим при повторном запуске.

### Функционал (`Capabilities`)
- Независимый замер системы снаружи: стенд не импортирует isai в измерительном ядре.

### Локальные инварианты (`Invariants`)
- Детерминизм индекса: blake2b вместо hash(), без PYTHONHASHSEED.

### Адаптер и Связывание Портов (`Adapter & Port Wirings`)
- **Входы (`Inputs`):** `нет внешних входов`
- **Выходы (`Outputs`):** `нет внешних выходов`

### Реестр владения и верифицируемых символов (`Ownership & Symbol Bindings`)
- **Файлы узла (`owned_files`):** `README.md`, `universe.py`, `e1_link_hit.py`, `e2_cost.py`, `e3_context.py`, `e5_scale.py`, `e6_mini.py`, `e7_plasmid.py`, `e0_summary.py`
- **Служебные файлы (`system_files`):** `.isai/node.py`
- **Экспортируемые сущности (`symbol_bindings`):**
  - `isai://research/lab#UniverseLoader` (`owned_artifact` → `universe.py`, видимость: `PUBLIC`)
  - `isai://research/lab#CorpusEmbedder` (`owned_artifact` → `universe.py`, видимость: `PUBLIC`)

### Типизированные связи и Маршрутизация (`Typed Links & Router`)
- **Типизированные связи (`links`):**
  - `isai://root#GenesisKernel` [`GOVERNED_BY` | RSoC: `NONE`]
- **Допустимые переходы (`transitions`):** `терминальный узел`

<!-- ISAI:SYNC:END -->

## Воспроизведённые метрики TASK-005 (E7)

| depth×width | плазмид | наивных узлов | мемоизированных | раздутие |
|---|---|---|---|---|
| 3×3 | 9 | 126 | 18 | 7.0x |
| 4×4 | 16 | 360 | 24 | 15.0x |
| 5×4 | 20 | 744 | 24 | 31.0x |
| 6×5 | 30 | 1890 | 30 | 63.0x |
| 7×5 | 35 | 3810 | 30 | 127.0x |

Заявленные в каталоге 110.7x — точка на этой кривой (depth≈7). Метрика верна, но зависит
от формы DAG; переносить её как константу нельзя.
