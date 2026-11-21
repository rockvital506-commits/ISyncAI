# И‑110 — Семь действий в L1 и L2: точный дифф и история

`arena/4e000a5e-isyncai` · Ф2. Промпт-компилятор и диалог · P0 · 2026-11-21

## П0–П2. Сверка и замысел

До начала: `57d7021 · v1.11`. [И‑109](../109/ACCEPTANCE.json) доказала план для чернового правила L1. [DESIGN.md](DESIGN.md) расширяет исполнение до 7×2 и описывает журнал, в котором редактирование или purge не ломают раннее решение `create`. A1–A4, порядок фаз и критерий стратегии не изменились.

[П2](CASES.json): 29 положительных и 33 отрицательных случаев. До правок Kit [RED.json](RED.json): 6 pass / 56 fail / 0 not run, rc 1. SHA‑256 корпуса `87c24f449f957f7734a143a877af1ad8fd0f835759d0c56ef0a35bbe3af4d002`, SHA‑256 [пробы](test_actions.py) `8392a00fe820d060d94985771b573afa69f7348d63d33fef7ee0c0e3e68914eb`. Ожидаемые диагностики, дифф и будущие файлы построены по фикстурам, а не по ответам Kit.

## П3–П5. Два целевых процесса

`python3 -B research/110/run.py` из корня. Проба: `python3 -B -I -S -X utf8 research/110/test_actions.py`.

| Процесс | Обязательные случаи | rc | basis |
| --- | --- | --- | --- |
| П3 · checkout | 62 pass / 0 fail / 0 not run | 0 | [CHECKOUT.json](CHECKOUT.json) |
| П4 · чистая копия | 62 pass / 0 fail / 0 not run | 0 | [CLEANROOM.json](CLEANROOM.json) |

ОС: `Linux`. П4 содержит только 13 входов из [ITERATION.json](ITERATION.json). В обоих процессах используются временные рабочие деревья с тремя файлами реестров, один писатель, синтетическое согласие. Сравниваются байты, состав дерева, метки обычных файлов, вызовы замены и аудируемые попытки записи. Преднамеренный дрейф, установка фикстуры и первая запись перед тестом повтора не входят в замер отказа.

[ACCEPTANCE.json](ACCEPTANCE.json): **accepted**, 7 pass / 0 fail / 4 not run. Это счётчик ворот и отложенных групп, не число случаев.

| Ворота | Статус | basis | criterion |
| --- | --- | --- | --- |
| frozen_cases | pass | DESIGN.md; CASES.json; test_actions.py; ITERATION.json; RED.json | Хеши обязательного П2 совпали; контроль до изменения Kit завершился отказами при том же списке ячеек. |
| checkout | pass | CHECKOUT.json; CASES.json | Каждый ID ровно один раз: точные исход, диагностика, JSON-типы, байты, статус, решения и физические эффекты. |
| cleanroom | pass | CLEANROOM.json; CASES.json | Каждый ID ровно один раз: точные исход, диагностика, JSON-типы, байты, статус, решения и физические эффекты. |
| execution_matrix | pass | CASES.json (M-*); CHECKOUT.json; CLEANROOM.json | 7×2: чтение без диффа, билета и записи; все 12 мутационных ячеек с точным планом и одной заменой, не только допуск. |
| masked_witnesses | pass | CHECKOUT.json; CLEANROOM.json: M-create-L1 и M-delete-L2 | Показаны точные диффы регистрации и purge с привязкой к SHA-256, ревизиям и файлам, без опубликованных билетов. |
| isolated | pass | ITERATION.json; CLEANROOM.json | В чистой копии ровно указанные входы, без Git/ISAI/донора, все побайтно прежние. |
| repeat | pass | CHECKOUT.json; CLEANROOM.json | Два изолированных процесса дали равные обязательные наблюдения и входные хеши. |

## П6. Что подтверждено

**7 действий × 2 области.** Каждой ячейке соответствует обязательный случай `M-<действие>-<область>` и исполненный вызов через карточку. [ACTIONS.json](ACTIONS.json) — наблюдавшаяся матрица, два диффа без билетов и две цепочки.

| Действие | L1 | L2 |
| --- | --- | --- |
| Регистрация · create | 4 → 5 · draft | 7 → 8 · draft |
| Просмотр · list | прочитан каталог, 0 замен | прочитан каталог, 0 замен |
| Правка текста · edit | 4 → 5 · active | 7 → 8 · active |
| Приостановка · suspend | 4 → 5 · suspended | 7 → 8 · suspended |
| Возобновление · resume | 4 → 5 · active | 7 → 8 · active |
| Отмена · revoke | 4 → 5 · revoked | 7 → 8 · revoked |
| Удаление · delete | 4 → 5 · запись удалена | 7 → 8 · запись удалена |

Записей без подтверждения: **0**. В измеренных вызовах — 27 успешных замен, 4 чтения `list`, 5 точных повторов, 32 отказа до попытки записи и 1 отказ замены без изменения реестра и истории. Положительные случаи цепочек включают несколько отдельных согласований; один шаг всегда равен одной замене.

| Факт | basis (ID в CHECKOUT/CLEANROOM) | criterion / предел |
| --- | --- | --- |
| Фраза и просмотр не пишут. | M-list-L1/L2; P-text-L1/L2; P-missing; P-repeat-*; M-edit-L1/L2 | Каталог не содержит тел, явный ID допускает просмотр одного текста. Родитель в приостановке исключает активного ребёнка из фильтра. Уточнение — до чтения, 3 вопроса при 8 пропусках. Глагол в теле правки остаётся текстом. |
| Отмена не удаляет запись. Purge — самостоятельное согласие. | M-revoke-L1/L2; M-delete-L1/L2; N03–N06; N28–N29 | Отмена сохраняет текст. Запись удаляется из текущего файла только из revoked, по билету и точному allow_delete=True; дети не удаляются каскадом. История содержит ID и отпечатки, не прежнее тело; Git/копии не стираются. |
| Журнал и реестр меняются вместе; прежние решения не исчезают. | P-legacy-edit; P-chain-L1/L2; N21–N23; N30 | Известный create формата 1 сохранён, неизвестная история голого v2 не выдумана. L1 4→8, L2 7→13 в разных деревьях. Итог и цепочка проверены независимо. Повреждённая история и заново предъявленный удалённый ID отклонены. |
| Допуски и свежесть проверяются независимо от реквизитов. | N01–N02; N11–N20; N25–N27; N31–N33 | Перечитаны L0/L1/L2, SHA и ревизия цели. Соседний ID/родитель не разрешается, L0 не меняется. При конфликте будущего resume видны обе стороны. Согласие не удостоверяет владельца и не выдаёт прав ОС. |

### Все обязательные случаи

| ID | basis · фикстура | Наблюдение | criterion · изменённые файлы |
| --- | --- | --- | --- |
| M-create-L1 | Регистрация черновика с локальным контрактом. | `applied` | profiles/pilot/registry.json |
| M-list-L1 | Каталог действующих записей без тела и скрытой записи. | `listed` | — |
| M-edit-L1 | Изменяется только явно заданный текст. | `applied` | profiles/pilot/registry.json |
| M-suspend-L1 | active → suspended, запись и текст сохранены. | `applied` | profiles/pilot/registry.json |
| M-resume-L1 | suspended → active, активный родитель. | `applied` | profiles/pilot/registry.json |
| M-revoke-L1 | active → revoked, содержание не удалено. | `applied` | profiles/pilot/registry.json |
| M-delete-L1 | revoked и отдельное согласие: тело ушло из реестра, след остался. | `applied` | profiles/pilot/registry.json |
| P-text-L1 | По явному ID запрошен только текст, а не корпус. | `listed` | — |
| M-create-L2 | Регистрация черновика с локальным контрактом. | `applied` | .agent-contract/project/registry.json |
| M-list-L2 | Каталог действующих записей без тела и скрытой записи. | `listed` | — |
| M-edit-L2 | Изменяется только явно заданный текст. | `applied` | .agent-contract/project/registry.json |
| M-suspend-L2 | active → suspended, запись и текст сохранены. | `applied` | .agent-contract/project/registry.json |
| M-resume-L2 | suspended → active, активный родитель. | `applied` | .agent-contract/project/registry.json |
| M-revoke-L2 | active → revoked, содержание не удалено. | `applied` | .agent-contract/project/registry.json |
| M-delete-L2 | revoked и отдельное согласие: тело ушло из реестра, след остался. | `applied` | .agent-contract/project/registry.json |
| P-text-L2 | По явному ID запрошен только текст, а не корпус. | `listed` | — |
| P-repeat-edit | Точный повтор не пишет и не получает билет. | `no_change` | — |
| P-repeat-revoke | Точный повтор не пишет и не получает билет. | `no_change` | — |
| P-legacy-edit | Редактирование черновика из profile_format:1 сохраняет ранее принятый create. | `applied` | profiles/pilot/registry.json |
| P-register-contract | Другой вид v2; родитель только у дочернего вида, запись остаётся draft. | `applied` | profiles/pilot/registry.json |
| P-register-constraint | Другой вид v2; родитель только у дочернего вида, запись остаётся draft. | `applied` | profiles/pilot/registry.json |
| P-register-protocol | Другой вид v2; родитель только у дочернего вида, запись остаётся draft. | `applied` | .agent-contract/project/registry.json |
| P-register-preference | Другой вид v2; родитель только у дочернего вида, запись остаётся draft. | `applied` | .agent-contract/project/registry.json |
| N01-no-ticket-L1 | Без отдельного билета новая мутация L1 не начинает запись. | `confirmation_required` · `confirmed_ticket` | — |
| N02-no-ticket-L2 | Та же защита для новой мутации L2. | `confirmation_required` · `confirmed_ticket` | — |
| N03-delete-active | Наличие согласия не заменяет предшествующую отмену. | `invalid_transition` · `profiles/pilot/registry.json` | — |
| N04-delete-no-consent | Билет сам по себе не согласие на физическое удаление. | `delete_confirmation_required` · `allow_delete` | — |
| N05-delete-int-consent | Число 1 не отдельное согласие на удаление. | `delete_confirmation_required` · `allow_delete` | — |
| N06-delete-contract | A4: удаление не каскадирует на детей и не оставляет сирот. | `parent` · `.agent-contract/project/registry.json` | — |
| N07-resume-draft | Возобновление не скрытая активация черновика. | `invalid_transition` · `profiles/pilot/registry.json` | — |
| N08-resume-revoked | Отмена необратима через resume. | `invalid_transition` · `.agent-contract/project/registry.json` | — |
| N09-suspend-draft | Черновик не считается действующим. | `invalid_transition` · `.agent-contract/project/registry.json` | — |
| N10-edit-revoked | Не правим текст отменённой записи. | `invalid_transition` · `profiles/pilot/registry.json` | — |
| N11-resume-parent | Возобновление дочерней записи под приостановленным родителем отклонено. | `parent` · `.agent-contract/project/registry.json` | — |
| N12-kind | Явно указанный вид не подменяем фактическим по ID. | `entry_kind_mismatch` · `profiles/pilot/registry.json` | — |
| N13-foreign | Та же строка ID в другой области не цель. | `entry_not_found` · `.agent-contract/project/registry.json` | — |
| N14-parent | A4: родитель только в L2 не локальный. | `parent` · `profiles/pilot/registry.json` · `parent_missing` | — |
| N15-scope | A4: docs2/guide не потомок docs. | `parent` · `.agent-contract/project/registry.json` · `scope_outside` | — |
| N16-system | A2: удаление в L0 не открывается. | `system_immutable` · `L0` | — |
| N17-list-system | Пользовательский список L0 здесь не реализован, это не запрет чтения. | `operation_unavailable` · `operation` | — |
| N18-stale | Даже неизменная целевая ревизия не скрывает дрейф прочитанного L2. | `stale_plan` · `inputs/L2` | — |
| N19-tampered | Подмена цели диффа с тем же билетом не допускается. | `plan_mismatch` · `plan` | — |
| N20-prospective-conflict | A3: конфликт появляется в планируемом состоянии. | `rule_conflict` · `entries` | — |
| N21-write-failed | Отказ замены после согласия: ни второго файла, ни нового журнала. | `write_failed` · `.agent-contract/project/registry.json` | — |
| N22-history | Указанный в новом журнале результат не равен байтам реестра. | `invalid_history` · `.agent-contract/project/registry.json` · `final_entries` | — |
| N23-retired | Не создаём под ID удалённой записи другую сущность. | `entry_retired` · `.agent-contract/project/registry.json` | — |
| N24-occupied | Занятый ID с другим телом не заменяется регистрацией. | `entry_exists` · `profiles/pilot/registry.json` | — |
| P-chain-L1 | Последовательные согласования на одном файле; каждое решение перечитано, удалённое тело не возвращается. | `applied_chain` | profiles/pilot/registry.json |
| P-chain-L2 | Последовательные согласования на одном файле; каждое решение перечитано, удалённое тело не возвращается. | `applied_chain` | .agent-contract/project/registry.json |
| P-repeat-create | Точный повтор не пишет и не получает билет. | `no_change` | — |
| P-repeat-suspend | Точный повтор не пишет и не получает билет. | `no_change` | — |
| P-repeat-resume | Точный повтор не пишет и не получает билет. | `no_change` | — |
| P-missing | Неполная фраза X04 — уточнение до чтения/записи, а не догадка о родителе. | `missing_params` | — |
| N25-target-revision | Подтверждение из предыдущей ревизии L2 устарело. | `stale_revision` · `revision/from` | — |
| N26-L0-drift | Дрейф байтов прочитанного L0 обнаружен и при неизменном L2. | `stale_plan` · `inputs/L0` | — |
| N27-foreign-session | Подтверждение существует только в выдавшей его сессии. | `ticket_unknown` · `ticket` | — |
| N28-replay-delete | Применённое согласие на удаление не исполняется второй раз. | `ticket_unknown` · `ticket` | — |
| N29-only-allow-delete | allow_delete не заменяет билет на точный дифф. | `confirmation_required` · `confirmed_ticket` | — |
| N30-chain-tampered | Совпавший итоговый SHA не скрывает разрыв цепочки решений. | `invalid_history` · `.agent-contract/project/registry.json` · `entry_chain` | — |
| N31-layout | A1: даже проектная запись не обходит конфликт привязки L1. | `profile_root_conflict` · `kit/pilot` | — |
| N32-profile-binding | ID профиля из фразы не меняет доверенную цель. | `profile_mismatch` · `card/params/profile` | — |
| N33-forged-authority | Карточка с внедрённым authority не прошла повторную компиляцию. | `card_mismatch` · `card` | — |

### Не выполнялось

| Что | Почему |
| --- | --- |
| Неоднозначность постоянного, временного, предложения и гипотезы; bootstrap. | И-111–И-112. И-110 принимает текущую узкую карточку. |
| Выдача прав, аутентификация владельца, живые среды, несколько писателей, ACL/NTFS, авария питания. | Linux, временные фикстуры и один писатель. Согласия синтетические, отказ замены моделируется. |
| Активация черновика, полное разрешение конфликтов (X07/X08), R-2, перенос, миграция, внешний purge. | Не выводятся из переходов одного файла, проверок A1–A4 и хешей сохранённых решений. |
| Свежая приёмка доноров 0.1.36 и ISAI. | Не входят в чистую копию; историческая приёмка остаётся в исходных снимках. |

## П7–П9. Печать, страница и сверка

[SEAL.json](SEAL.json) — размер и SHA‑256 сборки, не подпись. [REPLAY.json](REPLAY.json) — сравнение с сохранённым ZIP. `python3 -B research/110/run.py --verify-seal` проверяет их и страницу без перезаписи. Старые печати не обновляются вслед за изменением Kit; И‑109 проверяется на `57d7021`.

[Стратегия v1.12](../STRATEGY.md) · [сверка №20](../strategy/SYNC-LOG.md). Ф2 остаётся открытой. Исполненные операции над реестром не доказывают соблюдение правил моделью или пригодность Kit в живой среде.

## Дальше

И-111 — неоднозначность постоянного / временного / предложения / гипотезы, 20 фраз; не начата.
