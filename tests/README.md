# Контур самоверификации (`tests/`)

Автоматизированный набор модульных и адверсариальных тестов системы **ISAI** (`isai://tests#SelfVerificationSuite`), исполняющий роль внешнего детерминированного оракула (`Gate A`) для протокола `ISAI-PEP v1`.

<!-- ISAI:SYNC:BEGIN -->
<!-- isai:node_id=isai://tests -->
<!-- isai:spec_digest=4a10c9efcd3f431b53d4875132a0b86d516f4273092f901f6bb826b873fffdbb -->
<!-- isai:interface_digest=8adc0f23a99e3a25ba4ac96bd04a47913f63f3e34bbb07bc79a73946e42cc2b5 -->

## Паспорт узла `isai://tests` — Контур самоверификации и модульных автотестов ядра ISAI (Gate A Test Suite)

- **Уровень целостности:** `IL_2_CANONICAL`
- **Родительский узел:** `isai://root`
- **Цель (`Goal`):** Гарантировать детерминированную проверяемость всех инвариантов ISAI (неизменность Genesis-фрейма, zero-orphan-nodes, синхронизацию README, работу протокола ISAI-PEP v1, блокировки Watchdog, Salsa Early-Cutoff и компиляцию RSoC) через автоматические тесты.

### Критерии успеха (`Success Criteria`)
- 100% тестов pytest проходят без ошибок на живом репозитории и изолированных мутационных фикстурах.
- Проверены как позитивные сценарии, так и перехват каждого класса фатальных нарушений.

### Функционал (`Capabilities`)
- Проверка живого состояния репозитория через Gate A ('audit_repository').
- Адверсариальное тестирование детекторов взлома IL-0, сирот, битых EntityRef и гонок MVCC.
- Проверка конечного автомата фаз PhaseExecutionState и каскадного анализатора Salsa Early-Cutoff.

### Локальные инварианты (`Invariants`)
- Тесты никогда не мутируют живой корень репозитория — негативные сценарии выполняются только во временных копиях tmp_path.

### Адаптер (`Inputs / Outputs`)
- **Входы (`Inputs`):**
  - `live_repo_and_kernel_modules` (`Path`, обязательный) — Текущее состояние репозитория и модули пакета isai.
- **Выходы (`Outputs`):**
  - `pytest_gate_verdict` (`bool`, гарантированный) — Детерминированный сигнал прохождения Gate A (exit_code == 0).

### Реестр владения и символов (`Ownership & Symbols`)
- **Файлы узла (`owned_files`):** `README.md`, `test_isai_kernel.py`
- **Служебные файлы (`system_files`):** `.isai/node.py`
- **Экспортируемые сущности (`defined_symbols`):** `isai://tests#SelfVerificationSuite`

### Связи и Маршрутизация (`Router & Transitions`)
- **Связанные сущности (`related_refs`):** `isai://root#GenesisKernel`, `isai://root#ISAINodeSpec`, `isai://root#PhaseExecutionProtocol`, `isai://tasks#WatchdogService`
- **Допустимые переходы (`transitions`):**
  - При `report_gate_a_to_tasks` → `isai://tasks#WatchdogService` [режим: `FAST_READ`] — Передача результата автотестов в шлюз промоушена фазы.

<!-- ISAI:SYNC:END -->
