# Контур самоверификации и кросс-тестов (`tests/`)

Трёхуровневый автоматизированный набор модульных, контрактных и генеративных тестов системы **ISAI** (`isai://tests#SelfVerificationSuite` и `isai://tests#HypergraphCrossTestSuite`), исполняющий роль внешнего детерминированного оракула (`Gate A`) для протокола `ISAI-PEP v1` и транзакционного инжектора связей `isai://root#LinkInjector`.

<!-- ISAI:SYNC:BEGIN -->
<!-- isai:node_id=isai://tests -->
<!-- isai:spec_digest=fccf34f89fa29b8109ca9af08e44dcf2b31f4ee4219fc9904205fdef6aac6dde -->
<!-- isai:interface_digest=50e85c805ff4b9af3bec4865dbcb8cf67e7062997dbbf5bc1dae1ad341502865 -->

## Паспорт узла `isai://tests` — Контур самоверификации, контрактных кросс-тестов и генеративного фаззинга связей (Gate A Suite)

- **Уровень целостности:** `IL_2_CANONICAL` | **Видимость:** `PUBLIC`
- **Родительский узел:** `isai://root`
- **Цель (`Goal`):** Гарантировать трёхуровневую детерминированную проверяемость всех инвариантов ISAI (контрактная совместимость портов и колец видимости, транзакционная инъекция/рефакторинг связей и генеративный Stateful фаззинг последовательностей мутаций гиперграфа) через pytest и Hypothesis.

### Критерии успеха (`Success Criteria`)
- 100% модульных, кросс-контрактных и генеративных Hypothesis-тестов проходят с кодом 0.
- Любое нарушение совместимости портов, видимости колец, чистоты AST node.py или прозы перехватывается профильным AuditIssue.

### Функционал (`Capabilities`)
- Проверка живого состояния репозитория и матрицы PortWiringSpec ('audit_repository').
- Кросс-тестирование транзакционного инжектора LinkMutator (add, wire-port, refactor, scaffold, decommission + rollback).
- Генеративный автомат Hypothesis RuleBasedStateMachine для проверки произвольных цепочек мутаций графа.

### Локальные инварианты (`Invariants`)
- Тесты никогда не мутируют живой корень репозитория — негативные и генеративные сценарии работают только в tmp_path без кэша .hypothesis на диске.

### Адаптер и Связывание Портов (`Adapter & Port Wirings`)
- **Входы (`Inputs`):**
  - `live_state_snapshot` (`SystemStateSnapshot`, обязательный) [схемы: `isai.protocol:SystemStateSnapshot`] — Актуальный снимок состояния и дескрипторов Watchdog.
  - `rsoc_context_packet` (`dict[str, Any]`, обязательный) [схемы: `builtins:dict`] — Скомпилированный графовый пакет контекста RSoC со стабами соседей.
- **Выходы (`Outputs`):**
  - `pytest_gate_verdict` (`bool`, гарантированный) [схемы: `builtins:bool`] — Детерминированный сигнал прохождения Gate A (exit_code == 0).
- **Контрактная коммутация портов (`port_wirings`):**
  - вход `live_state_snapshot` ← `isai://tasks#StateSnapshot` (выход `state_snapshot`) — Кросс-проверка синхронности снимка Watchdog с живой топологией.
  - вход `rsoc_context_packet` ← `isai://root#RSoCCompiler` (выход `rsoc_packet`) — Кросс-тестирование графовой доставки linked_interface_stubs.

### Реестр владения и верифицируемых символов (`Ownership & Symbol Bindings`)
- **Файлы узла (`owned_files`):** `README.md`, `test_isai_kernel.py`, `test_hypergraph_cross_links.py`, `test_neuro_vascular_fundamental.py`
- **Служебные файлы (`system_files`):** `.isai/node.py`
- **Экспортируемые сущности (`symbol_bindings`):**
  - `isai://tests#SelfVerificationSuite` (`owned_artifact` → `test_isai_kernel.py`, видимость: `PUBLIC`)
  - `isai://tests#HypergraphCrossTestSuite` (`owned_artifact` → `test_hypergraph_cross_links.py`, видимость: `PUBLIC`)
  - `isai://tests#NeuroVascularTestSuite` (`owned_artifact` → `test_neuro_vascular_fundamental.py`, видимость: `PUBLIC`)

### Типизированные связи и Маршрутизация (`Typed Links & Router`)
- **Типизированные связи (`links`):**
  - `isai://root#GenesisKernel` [`GOVERNED_BY` | RSoC: `NONE`]
  - `isai://root#HypergraphIndex` [`VERIFIES` | RSoC: `INTERFACE_STUB`] — Верификация двунаправленного индекса EAVT/VAET.
  - `isai://root#LinkInjector` [`VERIFIES` | RSoC: `INTERFACE_STUB`] — Верификация транзакционного инжектора и рефактора связей.
  - `isai://tasks#CrashRecoveryService` [`VERIFIES` | RSoC: `INTERFACE_STUB`] — Инъекция аварийных сбоев и проверка идемпотентности восстановления.
  - `isai://root#NeuroVascularFundamental` [`GOVERNED_BY` | RSoC: `NONE`] — Подчинение субгенетическому нервно-сосудистому фундаменталу IL-1C.
  - `isai://root#AlgedonicProtocol` [`VERIFIES` | RSoC: `INTERFACE_STUB`] — Генеративный фаззинг 6-шагового Алгедонического автомата и блокировки аренды.
- **Допустимые переходы (`transitions`):**
  - При `report_gate_a_to_tasks` → `isai://tasks#WatchdogService` [режим: `FAST_READ`] — Передача результата автотестов в шлюз промоушена фазы.

<!-- ISAI:SYNC:END -->
