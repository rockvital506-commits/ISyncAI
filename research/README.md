# Лаборатория эмбеддинг-исследований (Embedding Research Lab)

<!-- ISAI:SYNC:BEGIN -->
<!-- isai:node_id=isai://research -->
<!-- isai:spec_digest=2d78e9716779f0a2c209524060dc863472e628cb9b3b261a2689812bdfa8ef63 -->
<!-- isai:interface_digest=18f22396dab0fa9600c72213e30e8b6f0f5c1b8defc0882663a407eb30bcc249 -->

## Паспорт узла `isai://research` — Лаборатория эмбеддинг-исследований (Embedding Research Lab)

- **Уровень целостности:** `IL_2_CANONICAL` | **Видимость:** `PUBLIC`
- **Родительский узел:** `isai://root`
- **Цель (`Goal`):** Эмпирически измерять перспективность векторной (эмбеддинговой) логики связей в ISAI: метрики попадания, скорости, чистоты контекста, экономичности — на собственном корпусе системы, без внешних зависимостей в рантайме.

### Критерии успеха (`Success Criteria`)
- Контракт узла isai://research синхронизирован и проходит 'isai audit'.

### Функционал (`Capabilities`)
- Инкапсуляция логики и артефактов домена 'research'.

### Адаптер и Связывание Портов (`Adapter & Port Wirings`)
- **Входы (`Inputs`):** `нет внешних входов`
- **Выходы (`Outputs`):** `нет внешних выходов`

### Реестр владения и верифицируемых символов (`Ownership & Symbol Bindings`)
- **Файлы узла (`owned_files`):** `README.md`, `FINDINGS.md`, `BIO-INVENTORY.md`, `BIO-CRITIQUE.md`, `CATALOG-CONTRADICTIONS.md`, `BIO-LEXICON.md`, `BIO-STRATEGY.md`
- **Служебные файлы (`system_files`):** `.isai/node.py`, `.isai/bio_lexicon.py`
- **Экспортируемые сущности (`symbol_bindings`):**
  - `isai://research#ResearchDoc` (`owned_artifact` → `README.md`, видимость: `PUBLIC`)

### Типизированные связи и Маршрутизация (`Typed Links & Router`)
- **Типизированные связи (`links`):**
  - `isai://root#GenesisKernel` [`GOVERNED_BY` | RSoC: `NONE`]
  - `isai://root#NeuroVascularFundamental` [`GOVERNED_BY` | RSoC: `NONE`]
- **Допустимые переходы (`transitions`):**
  - При `route_lab` → `isai://research/lab` [режим: `STAGED_TRANSACTION`] — Маршрутизация в дочерний узел isai://research/lab.
  - При `route_results` → `isai://research/results` [режим: `STAGED_TRANSACTION`] — Маршрутизация в дочерний узел isai://research/results.

<!-- ISAI:SYNC:END -->
