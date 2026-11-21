# И‑107 — Допуск операций и коды A1–A4

`arena/4e000a5e-isyncai` · Ф1. Модель данных · P0 · 2026-11-18

## П0–П2. Сверка и замысел

До начала: `23b320b · v1.8`. [И‑106](../106/ACCEPTANCE.json) приняла десять регистраций L1 с журналом. В И‑107 проверяем разницу между инвариантом и отсутствием обработчика, не расширяя набор мутаций. [Замысел](DESIGN.md) фиксирует ожидаемые коды, путь согласованной записи и предел проверки A3. [Контракт порта](../../kit/base/OPERATION-MATRIX.md) описывает его внутренние вызовы.

[CASES.json](CASES.json): 10 положительных и 38 отрицательных случаев, SHA‑256 `fd556ee68da3f6868fa1c1e66c522bbae307dc2c3e5258670736b758fc5972be`. SHA‑256 [пробы](test_policy.py) `154946561a0633c67e155fdfc16ee5c8f1bd545835a99f2de5399974ef779cfb`. Эталоны не считываются из кода допуска. До реализации проба остановилась на отсутствии `check_operation`.

## П3–П5. Измерение и приёмка

Из корня снимка: `python3 -B research/107/run.py`. Целевой процесс: `python3 -B -I -S -X utf8 research/107/test_policy.py`.

| Среда | Обязательные случаи | rc | Наблюдения |
| --- | --- | --- | --- |
| П3 · checkout | 48 pass / 0 fail / 0 not run | 0 | [CHECKOUT.json](CHECKOUT.json) |
| П4 · чистая копия | 48 pass / 0 fail / 0 not run | 0 | [CLEANROOM.json](CLEANROOM.json) |

ОС: `Linux`. В каждом процессе отдельные физические фикстуры. В П4 только 11 входов из [ITERATION.json](ITERATION.json), без Git, 0.1.36 и ISAI. Не используются рабочие профили или данные `R-2`.

[ACCEPTANCE.json](ACCEPTANCE.json): **accepted** (6 pass / 0 fail / 4 not run; это ворота и группы отложенных работ).

| Ворота | Статус | basis | criterion |
| --- | --- | --- | --- |
| frozen_cases | pass | DESIGN.md; CASES.json; test_policy.py; ITERATION.json | Хеши замороженных ожиданий и теста, уникальность ID, количество случаев и полнота ячеек совпали. |
| checkout | pass | CHECKOUT.json; CASES.json | Все обязательные ID ровно один раз. Точные исход, причина, путь, тип, состав и байты. |
| cleanroom | pass | CLEANROOM.json; CASES.json | Все обязательные ID ровно один раз. Точные исход, причина, путь, тип, состав и байты. |
| operation_matrix | pass | CHECKOUT.json; CLEANROOM.json: result.matrix; CASES.json: cell | Исполняемая матрица совпала со всеми независимыми ожиданиями: нет подмены available, planned и forbidden. |
| isolated | pass | ITERATION.json; CLEANROOM.json | Только указанные входы; нет донора, ISAI, Git и остатков записи в копии. |
| repeat | pass | CHECKOUT.json; CLEANROOM.json | Хеши исходных входов, матрица и все наблюдения двух процессов совпали. |

## П6. Наблюдения

[Машинная матрица](MATRIX.json) из `operation_matrix()`: **4 доступны**, **14 ещё не реализованы**, **6 запрещены**. Проверены реальные внутренние чтения, маршрут `create` при плане и применении и общий ответ на каждую ячейку. Для `planned` не засчитан обработчик. Диагностические `status` / `profile_history` / `report_conflicts` не имеют цели записи.

| Операция | L0 | L1 | L2 |
| --- | --- | --- | --- |
| `read` | `available` | `available` | `available` |
| `create` | `system_immutable` | `available: rule / draft` | `operation_unavailable` |
| `list` | `operation_unavailable` | `operation_unavailable` | `operation_unavailable` |
| `delete` | `system_immutable` | `operation_unavailable` | `operation_unavailable` |
| `edit` | `system_immutable` | `operation_unavailable` | `operation_unavailable` |
| `resume` | `system_immutable` | `operation_unavailable` | `operation_unavailable` |
| `revoke` | `system_immutable` | `operation_unavailable` | `operation_unavailable` |
| `suspend` | `system_immutable` | `operation_unavailable` | `operation_unavailable` |

| Инвариант | Код | basis · ID в двух прогонах | criterion |
| --- | --- | --- | --- |
| A1 | `profile_root_conflict` | A1-equal, A1-system-nested, A1-project-nested | Совпадение и вложенность корней отвергнуты, исходные файлы без изменений. |
| A2 | `system_immutable` | Шесть мутаций M-…-L0; A2-claim-L0, A2-apply-L0, N-claim-L1 | Мутации L0 запрещены; объявление authority и билет от другой цели не меняют маршрут. |
| A3 | `rule_conflict` | P-A3-report, P-A3-same-area, A3-plan, A3-apply-drift; контроли P-A3-* | Обе записи на каждое пересечение с разными значениями; при конфликте новая запись не сохраняется. |
| A4 | `parent` | A4-no-field, A4-null, A4-dangling, A4-wrong-kind, A4-foreign, A4-scope, A4-contract-parent | Причина входа или связи сохранена в schema.stage/code/path. Внешний ID и ложный префикс не подходят. |

**Положительный путь (`M-create-L1`, `P-A3-draft-write`).** Меняется только `profiles/pilot/registry.json`. Ревизия L1 0 → 1 и одно согласованное решение; L2 7 → 7. У L0 прежние SemVer и хеши дерева и тестового манифеста. Остальные случаи не оставляют изменённых путей или замены файла профиля.

**Пример A3 (`P-A3-report`).** Ключ `workflow.evidence`, пересечение `docs`. В этом случае обнаружены две пары; ниже первая. Строки не обозначают старшинство.

| Область | ID | scope | Значение | Формулировка |
| --- | --- | --- | --- | --- |
| L0 | S-key | . | required | Синтетическая формулировка S-key: required. |
| L1 | T-key | docs | skip | Синтетическая формулировка T-key: skip. |

### Находки и предел

| Факт или опровержение | basis | criterion / следствие |
| --- | --- | --- |
| Нет записи L2 сейчас ≠ L2 неизменяем по модели. | M-create-L2; N-apply-L2; M-create-L0; A2-apply-L0 | operation_unavailable различим с system_immutable; L2 не получает обработчик только от известного имени. |
| Корректный JSON не гарантирует допустимый дифф. | N-claim-L1; A4-foreign; A4-scope | Чужое полномочие и неверная связь дают разные причины, сохраняющие путь проверки v2. |
| Актуальный L1 не гарантирует, что не появилось противоречие в другой области. | A3-apply-drift; P-A3-draft-write | После плана поменялась только входная фикстура L2; apply не меняет ни одного файла. Черновик без действующего конфликта сохраняется; не доказаны активация, смысловое сравнение и И‑116. |

### Диагностики вне ячеек

| ID | basis | Результат |
| --- | --- | --- |
| A1-equal | A1; X01 | `profile_root_conflict` · `kit` |
| A1-system-nested | A1; X01 | `profile_root_conflict` · `kit/pilot` |
| A1-project-nested | A1; X01 | `profile_root_conflict` · `.agent-contract/pilot` |
| A2-claim-L0 | A2; X09, цель важнее декларации | `system_immutable` · `L0` |
| N-claim-L1 | X09, ошибочная декларация не равна операции L0 | `invalid_entry` · `profiles/pilot/registry.json` · `shape:authority_area` на `/entries/2/authority` |
| A2-apply-L0 | A2; X02, чужая цель в сохранённом плане | `system_immutable` · `L0` |
| N-apply-L2 | Ф2; возможное в модели, не реализованное сейчас | `operation_unavailable` · `operation` |
| N-unknown-operation | Строгий реестр операций | `unknown_operation` · `operation` |
| N-unknown-area | Строгая область | `unknown_area` · `target` |
| A4-no-field | A4; N07/N08 | `parent` · `profiles/pilot/registry.json` · `shape:missing_field` на `/entries/2/parent` |
| A4-null | A4; N07/N08 | `parent` · `profiles/pilot/registry.json` · `shape:type` на `/entries/2/parent` |
| A4-dangling | A4; N07/N08 | `parent` · `profiles/pilot/registry.json` · `links:parent_missing` на `/entries/2/parent` |
| A4-wrong-kind | A4; N07/N08 | `parent` · `profiles/pilot/registry.json` · `links:parent_kind` на `/entries/2/parent` |
| A4-foreign | A4; N07/N08 | `parent` · `profiles/pilot/registry.json` · `links:parent_missing` на `/entries/2/parent` |
| A4-scope | A4; N07/N08 | `parent` · `profiles/pilot/registry.json` · `links:scope_outside` на `/entries/2/scope` |
| A4-contract-parent | A4; N07/N08 | `parent` · `profiles/pilot/registry.json` · `shape:parent_forbidden` на `/entries/2/parent` |
| A3-plan | A3; существующий конфликт L0↔L1 | `rule_conflict` · `entries` · пар: 1 |
| A3-apply-drift | A3; конфликт L1↔L2 после плана | `rule_conflict` · `entries` · пар: 1 |
| P-A3-report | A3; все пары, не эффективный реестр | пар: 2; чтение без записи |
| P-A3-equal | A3; одинаковые значения | пар: 0; чтение без записи |
| P-A3-siblings | A3; docs и docs2 — соседние области | пар: 0; чтение без записи |
| P-A3-inactive | A3; неактивные записи и родитель | пар: 0; чтение без записи |
| P-A3-draft-write | A3; черновик не применяется | сохранён `rule/draft` `T-new`, ревизия 0 → 1 |
| P-A3-same-area | A3; конфликт не зависит от старшинства слоя | пар: 1; чтение без записи |

### Не выполнялось

| Что | Почему |
| --- | --- |
| Пользовательские операции list/edit/suspend/resume/revoke/delete, запись L2, карточка, общий plan/apply и CLI. | Ф2 (И-108–И-112). Для planned проверен только явный отказ, не обработчик. |
| Применение правил, разрешение конфликтов, declared priorities, промоушен, перенос и регистрация R-2. | Ф3 / Ф8. Принят только структурный отчёт о противоречии по явным key/value и стоп записи. |
| Права пользователя и среды, ACL/NTFS, параллельная запись, сбой питания, миграция и живые адаптеры. | Проверен текущий порт Kit на временных Linux-деревьях, не ограничения ОС и не установка. |
| Новый запуск нативных 0.1.36 и ISAI. | Исторический контроль отдельно; нет зависимости целевой матрицы. |

## П7–П9. Печать, страница и сверка

[SEAL.json](SEAL.json) фиксирует архив с финальными приёмкой, матрицей и отчётом. [REPLAY.json](REPLAY.json) фиксирует совпадение с повторной сборкой. `python3 -B research/107/run.py --verify-seal` проверяет архив, запись повтора и страницу без перезаписи. Печать — проверка байтов, не подпись или свидетельство предоставленных прав.

[Стратегия v1.9](../STRATEGY.md) и [сверка №17](../strategy/SYNC-LOG.md) ограничивают результат моделью и внутренним портом Ф1. A1–A4, P0, порядок фаз и определение пригодности не изменены. X07/X08 не приняты этой итерацией. Исторические печати И‑105 и И‑106 сверяются из снимков `8e03563` и `23b320b`: теперь A4 в порте даёт `parent` вместо общего `invalid_entry`, а прежние ожидания не переписываются.

## Дальше

И-108 — карточка операции и дозапрос missing[] на 12 формулировках; И-108 ещё не начата.
