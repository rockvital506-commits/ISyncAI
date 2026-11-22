# И‑118 — Полученный пакет сверяется в обе стороны

`arena/4e000a5e-isyncai` · Ф4. Пакет, целостность, доверие · P1

## П0–П2. Сверка, границы, RED

[Границы](DESIGN.md) · стратегия `v1.19` · HEAD `3ce8a27653be0fd917e7244c461d4c84e2373c52`. Согласованный fetch подтвердил И‑117; 301 рабочий файл был побайтно равен опубликованному снимку, локальный HEAD выровнен без перезаписи рабочих файлов. [Печать И‑117](../117/REPLAY.json) прошла без записи.

[RED.json](RED.json): rc 1, 0 pass / 116 fail / 0 not run; вывод архивной базы совпал. Контроль до продукта принял оба голых v2 и два штатных формата истории; рабочий порт вернул `unknown_operation` для обеих операций.

[Корпус](CASES.json) `b6d3f07715ff2b3d1bc1a79d4199c4b69ce807ca4f6e054d691f2316382dec9a` · [оракул](test_bundle_verify.py) `7024fe2e0472894b20b1ec147cc84a3101e4267a4e05e2ac25c2b0f365dc8c8c`. Векторы ZIP и ответы закреплены до реализации. Генератор не вызывает сборщик или проверяющий модуль.

## П3–П5. Два независимых прогона

`python3 -B -I -S -X utf8 research/118/test_bundle_verify.py` · Linux, Python 3.11.2. В чистой копии только 9 объявленных входов.

| Процесс | Проверки | rc | basis |
| --- | --- | --- | --- |
| П3 · рабочая копия | 116 pass / 0 fail / 0 not run | 0 | [CHECKOUT.json](CHECKOUT.json) |
| П4 · чистая копия | 116 pass / 0 fail / 0 not run | 0 | [CLEANROOM.json](CLEANROOM.json) |

[ACCEPTANCE.json](ACCEPTANCE.json): **accepted** · 12 pass / 0 fail / 4 not run по воротам и отложенным группам.

| Ворота | Статус | basis | criterion |
| --- | --- | --- | --- |
| frozen_red | pass | ITERATION.json; CASES.json; RED.json | Оракул, исходный пример и эталоны закреплены до продукта; RED 0/116/0 совпал с Git-снимком. |
| checkout | pass | CHECKOUT.json; CASES.json; test_bundle_verify.py | Каждая обязательная строка сопоставлена по ID, статусу, выводу и эффектам; rc0, без stderr. |
| cleanroom | pass | CLEANROOM.json; CASES.json; test_bundle_verify.py | Каждая обязательная строка сопоставлена по ID, статусу, выводу и эффектам; rc0, без stderr. |
| valid_bundles_and_source | pass | P01/P02/P04–P06; Synthetic-Bundle-117.zip; закреплённые векторы | Приняты исходный пример, пустой L1, иные байты JSON, новая ревизия и точная граница 1/4 МиБ. |
| tamper_each_file | pass | T01–T16; CASES.json; N33–N35 | Один байт каждого файла при правильном CRC и старой заявке — отказ SHA-256; размер и digest проверяются отдельно. |
| both_directions | pass | A01–A16/M01–M16/B01–B16; N09–N14 | 48 пропусков: из ZIP, манифеста и обоих. Лишнее или повторённое имя не покрывается digest. |
| bounds_before_payload | pass | N01–N08/N15–N23/N44–N46; Monitor | Ограничиваем части до чтения; не извлекаем ссылки, не декомпрессируем, не открываем вход-путь. |
| registry_binding | pass | N36–N42; положительный контроль истории; v2 | Самосогласованный ZIP не заменяет проверку двух реестров, корней, A4 и соответствия revision. |
| not_a_trust_claim | pass | P01/P03; T01–T16 | Изменение файла и пересчёт всего манифеста может пройти как целостность, не подлинность. |
| no_effects_or_partial_result | pass | Оба прогона; Monitor; VERIFICATION.json | Нет попыток I/O, запуска, записи ZIP или вывода; отказ не выдаёт полезные байты и частичный результат. |
| fresh_copy | pass | ITERATION.json; CLEANROOM.json | В новой копии ровно девять входов; Git, донор и рабочие профили отсутствуют. |
| repeat | pass | CHECKOUT.json; CLEANROOM.json | Повтор из заявленных байтов дал те же значения всех наблюдений. |

## П6. Что доказано

На прогон: 6 успехов, 110 ожидаемых отказов (`bundle_incomplete`: 91; `digest_mismatch`: 19). 9 отказов до открытия ZIP, 56 — до чтения любого члена. 107 открытий буфера, 412 попыток чтения, 0 попыток I/O или записи ZIP. Входы неизменны, вывод и частичные результаты отсутствуют.

| Вход | Ревизия L1 | Digest манифеста | SHA‑256 ZIP |
| --- | --- | --- | --- |
| [И‑117/P01](../117/Synthetic-Bundle-117.zip) | 7 | `300af66638088f51fc2e079d2cbf75bc30144f62f2e0c5ef8a12b6a7fc54bee5` | `5c95478a90f6328c21068527d44ed35462f1a5f36b8120835b49ef85f86494d3` |
| P03 · синтетические байты с заново пересчитанным манифестом | 7 | `1f79bb9e6a59fc829403a5c3fed9eb9998f4d3cb2452191d4911500e2e4e9430` | `aeb8d8224efe9dc606193d159f3b405ad780e64cdee85a4d7591ce4afd740c4f` |
| [Печать И‑118](SEAL.json), не пакет формата И‑117 | — | — | См. SEAL.json и HTML |

| Находка | basis | criterion / предел |
| --- | --- | --- |
| Одно изменение обнаруживается даже при правильном CRC ZIP. | T01–T16; N20, N33–N35 | Все 16 подмен одного байта с прежним манифестом → digest_mismatch. Сбой CRC — bundle_incomplete; размер, digest и хеш файла сверяются отдельно. |
| Обе стороны должны перечислить один и тот же полный набор. | A01–A16/M01–M16/B01–B16; N09–N14 | 48 одиночных пропусков отклонены. Равенство неполных списков, лишняя строка и повтор имени не принимаются. |
| Недопустимый контейнер не читается как набор файлов. | N01–N08/N15–N19/N21–N23/N44–N46; P06 | Ограничения проверяются до чтения; правильная граница 1/4 МиБ проходит. |
| Согласованные хеши не проверяют пригодность реестра. | P02/P04/P05; N36–N42; контроль | Пустой голый L1 валиден; чужой корень, новая ложная ревизия, неверный A4 и целая локальная история отвергаются. |
| Внутренняя целостность не доказывает источник. | P01/P03; T01–T16 | Замена с пересчётом связей проходит при тех же корнях и revision; не подпись, pin, отсутствие секретов или разрешение на установку. |

### Обязательные строки

| ID | basis | criterion | Наблюдалось | Чтений |
| --- | --- | --- | --- | --- |
| P01 | И‑117/P01; SEAL и эталонный Synthetic-Bundle-117.zip | Точный принятый пакет, digest и SHA-256 ZIP верны и различны, L1 revision=7. | verified · revision 7 | 17 |
| P02 | И‑117/P03; валидный v2 L1 с entries=[] | Полный пакет с пустым L1 принят, revision=0. | verified · revision 0 | 17 |
| P03 | Независимая замена байта START и пересчёт всех связей | Та же revision=7, но другой digest и ZIP, результат принят только как целостный, не как подлинный. | verified · revision 7 | 17 |
| P04 | И‑117/P05; другое JSON-представление голого L1 | Новые сырые байты дают иной digest, реестр валиден и принят без нормализации. | verified · revision 7 | 17 |
| P05 | И‑117/P06; явная смена ревизии в L1 | Ревизия 8 совпадает с манифестом; совпадение значений не создаёт разрешение. | verified · revision 8 | 17 |
| P06 | Границы И‑117; независимая перекладка 1/4 МиБ | Точно 1 МиБ хотя бы в одном файле и 4 МиБ суммарно принимаются. | verified · revision 7 | 17 |
| T01 | И‑117/P01; CRC пересчитан, заявка прежняя: kit/base/OPERATION-CARD.md | Один байт заменён без изменения длины; несовпадение SHA-256 не выдаёт результата. | digest_mismatch · files / sha256 | 2 |
| T02 | И‑117/P01; CRC пересчитан, заявка прежняя: kit/base/OPERATION-PLAN.md | Один байт заменён без изменения длины; несовпадение SHA-256 не выдаёт результата. | digest_mismatch · files / sha256 | 3 |
| T03 | И‑117/P01; CRC пересчитан, заявка прежняя: kit/base/SCHEMA-V2.md | Один байт заменён без изменения длины; несовпадение SHA-256 не выдаёт результата. | digest_mismatch · files / sha256 | 4 |
| T04 | И‑117/P01; CRC пересчитан, заявка прежняя: kit/base/START.md | Один байт заменён без изменения длины; несовпадение SHA-256 не выдаёт результата. | digest_mismatch · files / sha256 | 5 |
| T05 | И‑117/P01; CRC пересчитан, заявка прежняя: kit/base/STORAGE-V2.md | Один байт заменён без изменения длины; несовпадение SHA-256 не выдаёт результата. | digest_mismatch · files / sha256 | 6 |
| T06 | И‑117/P01; CRC пересчитан, заявка прежняя: kit/base/bootstrap.py | Один байт заменён без изменения длины; несовпадение SHA-256 не выдаёт результата. | digest_mismatch · files / sha256 | 7 |
| T07 | И‑117/P01; CRC пересчитан, заявка прежняя: kit/base/entry.txt | Один байт заменён без изменения длины; несовпадение SHA-256 не выдаёт результата. | digest_mismatch · files / sha256 | 8 |
| T08 | И‑117/P01; CRC пересчитан, заявка прежняя: kit/base/operation_card.py | Один байт заменён без изменения длины; несовпадение SHA-256 не выдаёт результата. | digest_mismatch · files / sha256 | 9 |
| T09 | И‑117/P01; CRC пересчитан, заявка прежняя: kit/base/operation_plan.py | Один байт заменён без изменения длины; несовпадение SHA-256 не выдаёт результата. | digest_mismatch · files / sha256 | 10 |
| T10 | И‑117/P01; CRC пересчитан, заявка прежняя: kit/base/profile_journal.py | Один байт заменён без изменения длины; несовпадение SHA-256 не выдаёт результата. | digest_mismatch · files / sha256 | 11 |
| T11 | И‑117/P01; CRC пересчитан, заявка прежняя: kit/base/registry.json | Один байт заменён без изменения длины; несовпадение SHA-256 не выдаёт результата. | digest_mismatch · files / sha256 | 12 |
| T12 | И‑117/P01; CRC пересчитан, заявка прежняя: kit/base/registry_journal.py | Один байт заменён без изменения длины; несовпадение SHA-256 не выдаёт результата. | digest_mismatch · files / sha256 | 13 |
| T13 | И‑117/P01; CRC пересчитан, заявка прежняя: kit/base/registry_policy.py | Один байт заменён без изменения длины; несовпадение SHA-256 не выдаёт результата. | digest_mismatch · files / sha256 | 14 |
| T14 | И‑117/P01; CRC пересчитан, заявка прежняя: kit/base/registry_store.py | Один байт заменён без изменения длины; несовпадение SHA-256 не выдаёт результата. | digest_mismatch · files / sha256 | 15 |
| T15 | И‑117/P01; CRC пересчитан, заявка прежняя: kit/base/schema_v2.py | Один байт заменён без изменения длины; несовпадение SHA-256 не выдаёт результата. | digest_mismatch · files / sha256 | 16 |
| T16 | И‑117/P01; CRC пересчитан, заявка прежняя: profiles/staged/registry.json | Один байт заменён без изменения длины; несовпадение SHA-256 не выдаёт результата. | digest_mismatch · files / sha256 | 17 |
| A01 | И‑117/P01; закрытый состав: kit/base/OPERATION-CARD.md | Файл исчез только из ZIP, манифест прежний. | bundle_incomplete · archive / members | 0 |
| A02 | И‑117/P01; закрытый состав: kit/base/OPERATION-PLAN.md | Файл исчез только из ZIP, манифест прежний. | bundle_incomplete · archive / members | 0 |
| A03 | И‑117/P01; закрытый состав: kit/base/SCHEMA-V2.md | Файл исчез только из ZIP, манифест прежний. | bundle_incomplete · archive / members | 0 |
| A04 | И‑117/P01; закрытый состав: kit/base/START.md | Файл исчез только из ZIP, манифест прежний. | bundle_incomplete · archive / members | 0 |
| A05 | И‑117/P01; закрытый состав: kit/base/STORAGE-V2.md | Файл исчез только из ZIP, манифест прежний. | bundle_incomplete · archive / members | 0 |
| A06 | И‑117/P01; закрытый состав: kit/base/bootstrap.py | Файл исчез только из ZIP, манифест прежний. | bundle_incomplete · archive / members | 0 |
| A07 | И‑117/P01; закрытый состав: kit/base/entry.txt | Файл исчез только из ZIP, манифест прежний. | bundle_incomplete · archive / members | 0 |
| A08 | И‑117/P01; закрытый состав: kit/base/operation_card.py | Файл исчез только из ZIP, манифест прежний. | bundle_incomplete · archive / members | 0 |
| A09 | И‑117/P01; закрытый состав: kit/base/operation_plan.py | Файл исчез только из ZIP, манифест прежний. | bundle_incomplete · archive / members | 0 |
| A10 | И‑117/P01; закрытый состав: kit/base/profile_journal.py | Файл исчез только из ZIP, манифест прежний. | bundle_incomplete · archive / members | 0 |
| A11 | И‑117/P01; закрытый состав: kit/base/registry.json | Файл исчез только из ZIP, манифест прежний. | bundle_incomplete · archive / members | 0 |
| A12 | И‑117/P01; закрытый состав: kit/base/registry_journal.py | Файл исчез только из ZIP, манифест прежний. | bundle_incomplete · archive / members | 0 |
| A13 | И‑117/P01; закрытый состав: kit/base/registry_policy.py | Файл исчез только из ZIP, манифест прежний. | bundle_incomplete · archive / members | 0 |
| A14 | И‑117/P01; закрытый состав: kit/base/registry_store.py | Файл исчез только из ZIP, манифест прежний. | bundle_incomplete · archive / members | 0 |
| A15 | И‑117/P01; закрытый состав: kit/base/schema_v2.py | Файл исчез только из ZIP, манифест прежний. | bundle_incomplete · archive / members | 0 |
| A16 | И‑117/P01; закрытый состав: profiles/staged/registry.json | Файл исчез только из ZIP, манифест прежний. | bundle_incomplete · archive / members | 0 |
| M01 | И‑117/P01; закрытый состав: kit/base/OPERATION-CARD.md | Строка исчезла только из манифеста; digest согласован с неполным списком. | bundle_incomplete · manifest / members | 1 |
| M02 | И‑117/P01; закрытый состав: kit/base/OPERATION-PLAN.md | Строка исчезла только из манифеста; digest согласован с неполным списком. | bundle_incomplete · manifest / members | 1 |
| M03 | И‑117/P01; закрытый состав: kit/base/SCHEMA-V2.md | Строка исчезла только из манифеста; digest согласован с неполным списком. | bundle_incomplete · manifest / members | 1 |
| M04 | И‑117/P01; закрытый состав: kit/base/START.md | Строка исчезла только из манифеста; digest согласован с неполным списком. | bundle_incomplete · manifest / members | 1 |
| M05 | И‑117/P01; закрытый состав: kit/base/STORAGE-V2.md | Строка исчезла только из манифеста; digest согласован с неполным списком. | bundle_incomplete · manifest / members | 1 |
| M06 | И‑117/P01; закрытый состав: kit/base/bootstrap.py | Строка исчезла только из манифеста; digest согласован с неполным списком. | bundle_incomplete · manifest / members | 1 |
| M07 | И‑117/P01; закрытый состав: kit/base/entry.txt | Строка исчезла только из манифеста; digest согласован с неполным списком. | bundle_incomplete · manifest / members | 1 |
| M08 | И‑117/P01; закрытый состав: kit/base/operation_card.py | Строка исчезла только из манифеста; digest согласован с неполным списком. | bundle_incomplete · manifest / members | 1 |
| M09 | И‑117/P01; закрытый состав: kit/base/operation_plan.py | Строка исчезла только из манифеста; digest согласован с неполным списком. | bundle_incomplete · manifest / members | 1 |
| M10 | И‑117/P01; закрытый состав: kit/base/profile_journal.py | Строка исчезла только из манифеста; digest согласован с неполным списком. | bundle_incomplete · manifest / members | 1 |
| M11 | И‑117/P01; закрытый состав: kit/base/registry.json | Строка исчезла только из манифеста; digest согласован с неполным списком. | bundle_incomplete · manifest / members | 1 |
| M12 | И‑117/P01; закрытый состав: kit/base/registry_journal.py | Строка исчезла только из манифеста; digest согласован с неполным списком. | bundle_incomplete · manifest / members | 1 |
| M13 | И‑117/P01; закрытый состав: kit/base/registry_policy.py | Строка исчезла только из манифеста; digest согласован с неполным списком. | bundle_incomplete · manifest / members | 1 |
| M14 | И‑117/P01; закрытый состав: kit/base/registry_store.py | Строка исчезла только из манифеста; digest согласован с неполным списком. | bundle_incomplete · manifest / members | 1 |
| M15 | И‑117/P01; закрытый состав: kit/base/schema_v2.py | Строка исчезла только из манифеста; digest согласован с неполным списком. | bundle_incomplete · manifest / members | 1 |
| M16 | И‑117/P01; закрытый состав: profiles/staged/registry.json | Строка исчезла только из манифеста; digest согласован с неполным списком. | bundle_incomplete · manifest / members | 1 |
| B01 | И‑117/P01; закрытый состав: kit/base/OPERATION-CARD.md | Имя исчезло с обеих сторон, digest пересчитан; равные неполные наборы не принимаются. | bundle_incomplete · archive / members | 0 |
| B02 | И‑117/P01; закрытый состав: kit/base/OPERATION-PLAN.md | Имя исчезло с обеих сторон, digest пересчитан; равные неполные наборы не принимаются. | bundle_incomplete · archive / members | 0 |
| B03 | И‑117/P01; закрытый состав: kit/base/SCHEMA-V2.md | Имя исчезло с обеих сторон, digest пересчитан; равные неполные наборы не принимаются. | bundle_incomplete · archive / members | 0 |
| B04 | И‑117/P01; закрытый состав: kit/base/START.md | Имя исчезло с обеих сторон, digest пересчитан; равные неполные наборы не принимаются. | bundle_incomplete · archive / members | 0 |
| B05 | И‑117/P01; закрытый состав: kit/base/STORAGE-V2.md | Имя исчезло с обеих сторон, digest пересчитан; равные неполные наборы не принимаются. | bundle_incomplete · archive / members | 0 |
| B06 | И‑117/P01; закрытый состав: kit/base/bootstrap.py | Имя исчезло с обеих сторон, digest пересчитан; равные неполные наборы не принимаются. | bundle_incomplete · archive / members | 0 |
| B07 | И‑117/P01; закрытый состав: kit/base/entry.txt | Имя исчезло с обеих сторон, digest пересчитан; равные неполные наборы не принимаются. | bundle_incomplete · archive / members | 0 |
| B08 | И‑117/P01; закрытый состав: kit/base/operation_card.py | Имя исчезло с обеих сторон, digest пересчитан; равные неполные наборы не принимаются. | bundle_incomplete · archive / members | 0 |
| B09 | И‑117/P01; закрытый состав: kit/base/operation_plan.py | Имя исчезло с обеих сторон, digest пересчитан; равные неполные наборы не принимаются. | bundle_incomplete · archive / members | 0 |
| B10 | И‑117/P01; закрытый состав: kit/base/profile_journal.py | Имя исчезло с обеих сторон, digest пересчитан; равные неполные наборы не принимаются. | bundle_incomplete · archive / members | 0 |
| B11 | И‑117/P01; закрытый состав: kit/base/registry.json | Имя исчезло с обеих сторон, digest пересчитан; равные неполные наборы не принимаются. | bundle_incomplete · archive / members | 0 |
| B12 | И‑117/P01; закрытый состав: kit/base/registry_journal.py | Имя исчезло с обеих сторон, digest пересчитан; равные неполные наборы не принимаются. | bundle_incomplete · archive / members | 0 |
| B13 | И‑117/P01; закрытый состав: kit/base/registry_policy.py | Имя исчезло с обеих сторон, digest пересчитан; равные неполные наборы не принимаются. | bundle_incomplete · archive / members | 0 |
| B14 | И‑117/P01; закрытый состав: kit/base/registry_store.py | Имя исчезло с обеих сторон, digest пересчитан; равные неполные наборы не принимаются. | bundle_incomplete · archive / members | 0 |
| B15 | И‑117/P01; закрытый состав: kit/base/schema_v2.py | Имя исчезло с обеих сторон, digest пересчитан; равные неполные наборы не принимаются. | bundle_incomplete · archive / members | 0 |
| B16 | И‑117/P01; закрытый состав: profiles/staged/registry.json | Имя исчезло с обеих сторон, digest пересчитан; равные неполные наборы не принимаются. | bundle_incomplete · archive / members | 0 |
| N01 | И‑117/P01; DESIGN.md; изолированное изменение live | Даже правильный ZIP за пределами стенда отвергается до разбора. | bundle_incomplete · target / stand_only | 0 |
| N02 | И‑117/P01; DESIGN.md; изолированное изменение path | Путь не открывается и не повторяется в отказе. | bundle_incomplete · archive / bytes | 0 |
| N03 | И‑117/P01; DESIGN.md; изолированное изменение bytearray | Изменяемый объект не приводится к bytes. | bundle_incomplete · archive / bytes | 0 |
| N04 | И‑117/P01; DESIGN.md; изолированное изменение empty | Отсутствие входа не считается пустым валидным L1. | bundle_incomplete · archive / bytes | 0 |
| N05 | И‑117/P01; DESIGN.md; изолированное изменение archive_limit | ZIP больше предела отвергается до разбора. | bundle_incomplete · archive / limit | 0 |
| N06 | И‑117/P01; DESIGN.md; изолированное изменение truncated | Обрезанная запись конца ZIP отвергается. | bundle_incomplete · archive / zip | 0 |
| N07 | И‑117/P01; DESIGN.md; изолированное изменение prefix | Нет неучтённого префикса перед ZIP. | bundle_incomplete · archive / layout | 0 |
| N08 | И‑117/P01; DESIGN.md; изолированное изменение tail | Нет добавленных данных после ZIP. | bundle_incomplete · archive / zip | 0 |
| N09 | И‑117/P01; DESIGN.md; изолированное изменение no_manifest | Полезные файлы без manifest.json не принимаются. | bundle_incomplete · archive / members | 0 |
| N10 | И‑117/P01; DESIGN.md; изолированное изменение duplicate_zip | Повтор имени в центральном списке не скрывается поиском по словарю. | bundle_incomplete · archive / duplicate_member | 0 |
| N11 | И‑117/P01; DESIGN.md; изолированное изменение extra_zip | L2 дополнительно к полному набору отвергается. | bundle_incomplete · archive / members | 0 |
| N12 | И‑117/P01; DESIGN.md; изолированное изменение extra_manifest | Строка без архивного члена даже с правильным digest отклоняется. | bundle_incomplete · manifest / members | 1 |
| N13 | И‑117/P01; DESIGN.md; изолированное изменение extra_both | Согласованный лишний локальный журнал не допускается. | bundle_incomplete · archive / members | 0 |
| N14 | И‑117/P01; DESIGN.md; изолированное изменение case_alias | Похожее имя в другом регистре не нормализуется. | bundle_incomplete · archive / members | 0 |
| N15 | И‑117/P01; DESIGN.md; изолированное изменение zip_order | Архивные члены одного набора в обратном порядке не формат И‑117. | bundle_incomplete · archive / layout | 0 |
| N16 | И‑117/P01; DESIGN.md; изолированное изменение symlink | Запись с атрибутом символьной ссылки не обычный член. | bundle_incomplete · archive / format | 0 |
| N17 | И‑117/P01; DESIGN.md; изолированное изменение compressed | Сжатый член отклонён до декомпрессии. | bundle_incomplete · archive / format | 0 |
| N18 | И‑117/P01; DESIGN.md; изолированное изменение local_header | Флаги локального заголовка должны точно совпадать с допустимым каталогом. | bundle_incomplete · archive / layout | 0 |
| N19 | И‑117/P01; DESIGN.md; изолированное изменение encrypted_flag | Флаг шифрования не разрешён; читаемости содержимого не проверяем. | bundle_incomplete · archive / format | 0 |
| N20 | И‑117/P01; DESIGN.md; изолированное изменение data_crc | Тот же заголовок, повреждённое тело: ошибка CRC остаётся ошибкой контейнера. | bundle_incomplete · archive / read | 5 |
| N21 | И‑117/P01; DESIGN.md; изолированное изменение file_limit | 1 МиБ + 1 байт в одном полезном члене — отказ до чтения. | bundle_incomplete · archive / limit | 0 |
| N22 | И‑117/P01; DESIGN.md; изолированное изменение total_limit | 4 МиБ + 1 байт суммарно при допустимых размерах отдельных членов — отказ. | bundle_incomplete · archive / limit | 0 |
| N23 | И‑117/P01; DESIGN.md; изолированное изменение manifest_limit | Отдельная граница манифеста проверяется до чтения его тела. | bundle_incomplete · archive / limit | 0 |
| N24 | И‑117/P01; DESIGN.md; изолированное изменение duplicate_json | Повтор JSON-ключа не допускается. | bundle_incomplete · manifest / json | 1 |
| N25 | И‑117/P01; DESIGN.md; изолированное изменение bad_utf8 | Некорректный UTF-8 не допускается. | bundle_incomplete · manifest / json | 1 |
| N26 | И‑117/P01; DESIGN.md; изолированное изменение unknown_field | Лишнее поле манифеста отклоняется без эха значения. | bundle_incomplete · manifest / shape | 1 |
| N27 | И‑117/P01; DESIGN.md; изолированное изменение bool_size | Булево значение не целый размер. | bundle_incomplete · manifest / shape | 1 |
| N28 | И‑117/P01; DESIGN.md; изолированное изменение bool_revision | Булево значение не ревизия. | bundle_incomplete · manifest / shape | 1 |
| N29 | И‑117/P01; DESIGN.md; изолированное изменение bad_sha | SHA-256 строки — ровно 64 нижнерегистровых hex знака. | bundle_incomplete · manifest / shape | 1 |
| N30 | И‑117/P01; DESIGN.md; изолированное изменение duplicate_row | Две строки на одно имя отвергаются. | bundle_incomplete · manifest / duplicate_member | 1 |
| N31 | И‑117/P01; DESIGN.md; изолированное изменение wrong_roots | Порядок и значения корней фиксированы независимо от digest. | bundle_incomplete · manifest / roots | 1 |
| N32 | И‑117/P01; DESIGN.md; изолированное изменение manifest_whitespace | Дополнительный LF не каноническая запись манифеста. | bundle_incomplete · manifest / encoding | 1 |
| N33 | И‑117/P01; DESIGN.md; изолированное изменение wrong_digest | Корректная форма, но digest не равен хешу остальных полей. | digest_mismatch · manifest / digest | 1 |
| N34 | И‑117/P01; DESIGN.md; изолированное изменение wrong_file_hash | Digest манифеста правильный, но его SHA-256 для START неверный. | digest_mismatch · files / sha256 | 5 |
| N35 | И‑117/P01; DESIGN.md; изолированное изменение wrong_size | Digest манифеста правильный, но заявленная длина не совпадает с ZIP. | digest_mismatch · files / size | 1 |
| N36 | И‑117/P01; DESIGN.md; изолированное изменение wrong_revision | Обе хеш-сверки успешны, но ревизия манифеста не равна L1. | bundle_incomplete · profile / revision | 17 |
| N37 | И‑117/P01; DESIGN.md; изолированное изменение bad_l0 | Согласованные хеши не заменяют проверку v2 и SemVer L0. | bundle_incomplete · system / registry | 17 |
| N38 | И‑117/P01; DESIGN.md; изолированное изменение wrong_l0_root | L0 с допустимым, но чужим корнем не согласован с манифестом. | bundle_incomplete · system / roots | 17 |
| N39 | И‑117/P01; DESIGN.md; изолированное изменение history_one | Штатный локальный формат 1 с валидным L1 целиком вне пакета. | bundle_incomplete · profile / local_history | 17 |
| N40 | И‑117/P01; DESIGN.md; изолированное изменение history_two | Штатный локальный формат 2 с валидным L1 целиком вне пакета. | bundle_incomplete · profile / local_history | 17 |
| N41 | И‑117/P01; DESIGN.md; изолированное изменение bad_parent | Хеши не спасают запись без существующего родителя по A4. | bundle_incomplete · profile / registry | 17 |
| N42 | И‑117/P01; DESIGN.md; изолированное изменение wrong_l1_root | Голый профиль с другим корнем не соответствует манифесту. | bundle_incomplete · profile / roots | 17 |
| N43 | И‑117/P01; DESIGN.md; изолированное изменение manifest_order | Тот же набор строк в обратном порядке с пересчитанным digest не каноничен. | bundle_incomplete · manifest / encoding | 1 |
| N44 | И‑117/P01; DESIGN.md; изолированное изменение traversal | Имя с .. отвергнуто; ни один путь не разрешается на диске. | bundle_incomplete · archive / members | 0 |
| N45 | И‑117/P01; DESIGN.md; изолированное изменение directory_limit | 33 строки каталога отвергнуты до создания объекта ZIP. | bundle_incomplete · archive / limit | 0 |
| N46 | И‑117/P01; DESIGN.md; изолированное изменение empty_payload | Нулевой размер обязательного полезного файла недопустим. | bundle_incomplete · archive / limit | 0 |

### Отдельно: not run

| Что | Почему |
| --- | --- |
| Подпись, происхождение, доверие, pin выпуска и исключения (И‑119). | Внутренняя согласованность может быть заново рассчитана отправителем; внешнее основание доверия не задано. |
| Установка, рабочий перенос, откат и живой агент (И‑120 и последующие). | Нет выдачи полезных байтов, распаковки, исполнения или записи рабочего состояния. |
| Порт, адаптеры, guard и CI. | Стендовая функция не зарегистрирована; сценарии И‑127/И‑128 не запускались. |
| Реальные пакеты, секреты/PII, иные ОС/ACL и произвольный ZIP. | Корпус ограничен синтетикой и форматом И‑117, повтор проведён в доступной Linux-среде. |

## П7–П9. Печать, страница и сверка

`python3 -B research/118/run.py` воспроизводит исследование. `python3 -B research/118/run.py --verify-seal` сверяет [печать](SEAL.json), [повтор](REPLAY.json), результаты, отчёт и HTML без записи. Исходный пример входит в печать как закреплённые байты. HTML и записи о самой печати не входят в её состав.

[Стратегия v1.20](../STRATEGY.md) · [сверка №28](../strategy/SYNC-LOG.md). A1–A4, P0, порядок, вехи, критерии и пригодность прежние. Commit/push только 20 путей И‑118 разрешены отдельно ([основание](DESIGN.md)). П9 подтверждается совпадением SHA с `origin/arena/4e000a5e-isyncai` и побайтным повтором из снимка коммита. М2 учитывается только в стендовом объёме по этому подтверждению; рабочего переноса и установки не было. И‑119 не начата, Ф4 открыта.
