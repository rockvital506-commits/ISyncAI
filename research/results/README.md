# Результаты измерений (Measurement Results)

<!-- ISAI:SYNC:BEGIN -->
<!-- isai:node_id=isai://research/results -->
<!-- isai:spec_digest=bd531c440adbb683443e536ce4bd050abe65209f4c5c77f0e1979beeda405089 -->
<!-- isai:interface_digest=1f7d923f701016d5ff0ea1c1789f65eecf74e827256c2fe7cd04f7eba9a24d5e -->

## Паспорт узла `isai://research/results` — Результаты измерений (Measurement Results)

- **Уровень целостности:** `IL_2_CANONICAL` | **Видимость:** `PUBLIC`
- **Родительский узел:** `isai://research`
- **Цель (`Goal`):** Хранить машинно-читаемые артефакты экспериментов: JSON-срезы метрик, достаточные для перепроверки выводов без повторного прогона.

### Критерии успеха (`Success Criteria`)
- Каждый JSON-срез содержит достаточно метрик для независимой проверки вывода.

### Функционал (`Capabilities`)
- Машинно-читаемая фиксация результатов всех экспериментов стенда.

### Адаптер и Связывание Портов (`Adapter & Port Wirings`)
- **Входы (`Inputs`):** `нет внешних входов`
- **Выходы (`Outputs`):** `нет внешних выходов`

### Реестр владения и верифицируемых символов (`Ownership & Symbol Bindings`)
- **Файлы узла (`owned_files`):** `README.md`, `e1_link_hit.json`, `e2_cost.json`, `e3_context.json`, `e5_scale.json`, `e6_mini.json`, `e7_plasmid.json`, `e0_summary.json`
- **Служебные файлы (`system_files`):** `.isai/node.py`
- **Экспортируемые сущности (`symbol_bindings`):**
  - `isai://research/results#MetricsArtifact` (`owned_artifact` → `e1_link_hit.json`, видимость: `PUBLIC`)

### Типизированные связи и Маршрутизация (`Typed Links & Router`)
- **Типизированные связи (`links`):**
  - `isai://root#GenesisKernel` [`GOVERNED_BY` | RSoC: `NONE`]
- **Допустимые переходы (`transitions`):** `терминальный узел`

<!-- ISAI:SYNC:END -->
