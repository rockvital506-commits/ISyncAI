# И‑119 — Подпись и исключение не заменяют целостность

`arena/4e000a5e-isyncai` · Ф4. Пакет, целостность, доверие · P2

## П0–П2. Сверка, замысел и RED

[Границы](DESIGN.md) · v1.20 · `de5ca5b92f396ec4effc7d47e01c4aaca73aee3a`. Согласованный fetch совпал, [печать И‑118](../118/REPLAY.json) прошла без записи. Рабочий порт не менялся.

[RED](RED.json): rc 1, 0 pass / 51 fail / 0 not run; чистый снимок Git дал те же строки. До реализации контроль проверил публичный вектор Ed25519 RFC 8032 §7.1, две настоящие учебные подписи, четыре отрицательных сравнения, целостность обоих ZIP и отсутствие рабочих операций.

OpenSSL 3.0.20 7 Apr 2026 (Library: OpenSSL 3.0.20 7 Apr 2026) · [корпус](CASES.json) `66475c0cc9bb84575d2fb600ab1f6190ec68287865703869e81a2b461240c9c7` · [оракул](test_bundle_trust.py) `9e1ba5c37a6d5916629b2e89b20bad64b93296f1d9955a5be721136adc70b698`. В корпусе только открытые входы. Одноразовый учебный закрытый ключ создан при подготовке, остался в памяти и каналах процессов и не нужен для повтора.

## П3–П5. Два независимых прогона

`python3 -B -I -S -X utf8 research/119/test_bundle_trust.py` · Linux, Python 3.11.2. В чистой копии только 9 входов.

| Процесс | Проверки | rc | basis |
| --- | --- | --- | --- |
| П3 · рабочая копия | 51 pass / 0 fail / 0 not run | 0 | [CHECKOUT.json](CHECKOUT.json) |
| П4 · чистая копия | 51 pass / 0 fail / 0 not run | 0 | [CLEANROOM.json](CLEANROOM.json) |

[ACCEPTANCE.json](ACCEPTANCE.json): **accepted** · 12 pass / 0 fail / 4 not run по воротам и отложенным группам.

| Ворота | Статус | basis | criterion |
| --- | --- | --- | --- |
| frozen_red | pass | CASES.json; RED.json; ITERATION.json | Открытые векторы закреплены до продукта; RED 0/51/0 подтверждён из Git-снимка. |
| checkout | pass | CHECKOUT.json; CASES.json | Все строки, порядок и диагностики совпали с независимым оракулом; rc0 без stderr. |
| cleanroom | pass | CLEANROOM.json; CASES.json | Все строки, порядок и диагностики совпали с независимым оракулом; rc0 без stderr. |
| integrity_first | pass | I01–I05; неизменная И‑118 | Подмена/неполнота возвращается раньше политики; ни подпись, ни исключение их не отменяют. |
| unsigned_is_separate | pass | U01/U02; P9 стратегии; I01/I02 | Нет подписи не означает ошибку хеша и блокирует только согласно переданной политике. |
| exception_scope_time_authority | pass | U03–U11; N10–N18 | Действуют только точный SHA ZIP, разрешённый approver и now < expiry; digest манифеста не заменяет SHA ZIP. |
| real_signature_binding | pass | S01/S02/S04–S06/S17; контроль RFC 8032 §7.1 | OpenSSL принимает две подписи, но не их изменение, обмен ZIP или другого ключа. |
| fail_closed | pass | S03/S07–S17 | Чужой ключ и неисправный проверяющий не дают доверия и не становятся unsigned. |
| config_exact | pass | N01–N18 | Некорректная политика, время и реестр исключений отклоняются без подбора значений. |
| no_effects | pass | Monitor; оба прогона | Только 8 явных вызовов проверяющего; нет побочного I/O модуля, вывода, изменений входов или частичного допуска. |
| fresh_copy | pass | ITERATION.json; CLEANROOM.json | В новой копии только девять входов, без рабочего профиля, Git и закрытого ключа. |
| repeat | pass | CHECKOUT.json; CLEANROOM.json | Байты входов и все наблюдения совпадают в двух процессах. |

## П6. Наблюдения и предел вывода

На прогон: 28 оценок политики (22 блокировок, два `optional`, два `exception` и два `satisfied`), 23 отказа до решения (2 `digest_mismatch`, 3 `bundle_incomplete`, 18 `bundle_trust_invalid`). Из 8 вызовов явно переданного проверяющего шесть — реальный OpenSSL, два — контроль сбоя/не-булева ответа. В самом модуле 0 попыток I/O; входы и вывод не изменялись.

| Свидетельство | Ревизия L1 | Digest манифеста | SHA‑256 ZIP |
| --- | --- | --- | --- |
| [И‑117/P01](../117/Synthetic-Bundle-117.zip) | 7 | `300af66638088f51fc2e079d2cbf75bc30144f62f2e0c5ef8a12b6a7fc54bee5` | `5c95478a90f6328c21068527d44ed35462f1a5f36b8120835b49ef85f86494d3` |
| И‑118/P03 · вариант с пересчитанным манифестом | 7 | `1f79bb9e6a59fc829403a5c3fed9eb9998f4d3cb2452191d4911500e2e4e9430` | `aeb8d8224efe9dc606193d159f3b405ad780e64cdee85a4d7591ce4afd740c4f` |
| [Исследовательская печать](SEAL.json) | — | — | Отдельный SHA‑256, см. SEAL.json и HTML |

Отпечаток учебного **открытого ключа**, не пакета: `6b86b41461678ccd19ee73c5475fd00e3f98b14df209ade4986d17c521444a57`.

| Факт | basis | criterion / предел |
| --- | --- | --- |
| Целостность первая. | I01–I05; И‑118 | Подмена и неполнота отвергаются до проверки; даже совпавшее исключение их не отменяет. |
| `unsigned` — состояние, не ошибка SHA‑256. | U01/U02/U09 | Одни и те же целостные байты получают разное решение только по явно выбранной политике; для личного сценария решение не навязывается. |
| Исключение узкое и временное. | U03–U11; N10–N18 | Только для unsigned, одного SHA‑256 ZIP, разрешённого approver и now < expiry. Ровно в expiry уже отказ. |
| Подпись привязана к точному ZIP и выбранному ключу. | S01/S02/S04–S06/S17 | Два отдельно подписанных ZIP приняты; перенести подпись между ними нельзя даже при совпавшей revision и согласованных внутренних хешах. |
| Сбой проверки не выдаёт доверия. | S03/S07–S16 | Ключ вне списка, неверная запись, недоступный проверяющий и не-булев ответ блокируются отдельно. Нет понижения до unsigned. |

### Корпус

| ID | basis | criterion | Наблюдалось |
| --- | --- | --- | --- |
| U01 | И‑118/P01,P03; DESIGN.md; optional | Без подписи и без требования: unsigned, не ошибка целостности. | unsigned · optional / signature_optional |
| U02 | И‑118/P01,P03; DESIGN.md; required | Целостный пакет без подписи заблокирован явным требованием. | unsigned · blocked / signature_required |
| U03 | И‑118/P01,P03; DESIGN.md; active | Точное исключение доверенного утверждающего до срока действует; unsigned сохраняется. | unsigned · exception / exception_active |
| U04 | И‑118/P01,P03; DESIGN.md; equal_expiry | Ровно expiry — исключение уже недействительно. | unsigned · blocked / exception_expired |
| U05 | И‑118/P01,P03; DESIGN.md; past_expiry | Истёкшее исключение не продлевается. | unsigned · blocked / exception_expired |
| U06 | И‑118/P01,P03; DESIGN.md; foreign_approver | Формально корректный, но не разрешённый approver не даёт исключения. | unsigned · blocked / exception_approver |
| U07 | И‑118/P01,P03; DESIGN.md; wrong_zip | Та же revision и другое тело не наследуют решение для исходного ZIP. | unsigned · blocked / signature_required |
| U08 | И‑118/P01,P03; DESIGN.md; manifest_is_not_zip | Digest манифеста не используется как SHA‑256 ZIP. | unsigned · blocked / signature_required |
| U09 | И‑118/P01,P03; DESIGN.md; optional_with_exception | Опциональная политика не использует даже активное исключение. | unsigned · optional / signature_optional |
| U10 | И‑118/P01,P03; DESIGN.md; revoked_approver | После исключения утверждающего из явно переданной политики допуск не сохраняется. | unsigned · blocked / exception_approver |
| U11 | И‑118/P01,P03; DESIGN.md; active_alternate | Точная запись для другого целостного ZIP действует только для него. | unsigned · exception / exception_active |
| S01 | И‑118/P01,P03; DESIGN.md; trusted | Настоящая Ed25519-подпись заранее одобренного ключа проходит. | trusted_signature · satisfied / signature_verified |
| S02 | И‑118/P01,P03; DESIGN.md; trusted | Отдельно подписанный пересогласованный пакет принят с другим отпечатком. | trusted_signature · satisfied / signature_verified |
| S03 | И‑118/P01,P03; DESIGN.md; unknown_optional | Действительная подпись неизвестного ключа не становится доверенной при optional или исключении. | untrusted_signer · blocked / key_not_approved |
| S04 | И‑118/P01,P03; DESIGN.md; bad_bits | Изменение бита подписи остаётся отказом, активное исключение не применяется. | signature_invalid · blocked / mismatch |
| S05 | И‑118/P01,P03; DESIGN.md; signed_reused | Старая подпись не подходит к изменённому ZIP с пересчитанным манифестом. | signature_invalid · blocked / mismatch |
| S06 | И‑118/P01,P03; DESIGN.md; signed_reused | Обратный перенос подписи также отвергается. | signature_invalid · blocked / mismatch |
| S07 | И‑118/P01,P03; DESIGN.md; algorithm | Чужой алгоритм не запускает обходной проверяющий. | signature_invalid · blocked / algorithm |
| S08 | И‑118/P01,P03; DESIGN.md; empty_signature | Предъявленные пустые байты не отсутствие подписи. | signature_invalid · blocked / shape |
| S09 | И‑118/P01,P03; DESIGN.md; bool_format | true не номер формата. | signature_invalid · blocked / shape |
| S10 | И‑118/P01,P03; DESIGN.md; bad_envelope | Пустой словарь не unsigned. | signature_invalid · blocked / shape |
| S11 | И‑118/P01,P03; DESIGN.md; embedded_key | Ключ, вложенный отправителем, не импортируется. | signature_invalid · blocked / shape |
| S12 | И‑118/P01,P03; DESIGN.md; unknown_id | Допустимый формат ID не доказывает одобрение ключа. | untrusted_signer · blocked / key_not_approved |
| S13 | И‑118/P01,P03; DESIGN.md; unavailable | Отсутствующий проверяющий не выдаёт доверие и не включает исключение. | signature_unchecked · blocked / verifier_unavailable |
| S14 | И‑118/P01,P03; DESIGN.md; verifier_error | Сбой проверяющего не объявляется подделкой, тело исключения скрыто. | signature_unchecked · blocked / verifier_error |
| S15 | И‑118/P01,P03; DESIGN.md; truthy | Число 1 не явный True. | signature_unchecked · blocked / verifier_result |
| S16 | И‑118/P01,P03; DESIGN.md; bad_key_id | Ключевой ID строго нижнерегистровый SHA‑256. | signature_invalid · blocked / shape |
| S17 | И‑118/P01,P03; DESIGN.md; substituted_approved_key | Другой одобренный ключ не равен ключу, к которому привязана подпись. | signature_invalid · blocked / mismatch |
| I01 | И‑118/P01,P03; DESIGN.md; tampered_unsigned | Подмена с правильным CRC остаётся digest_mismatch даже при точном исключении. | digest_mismatch · files / sha256 |
| I02 | И‑118/P01,P03; DESIGN.md; tampered_signed | Подпись и неверная политика не заслоняют digest_mismatch. | digest_mismatch · files / sha256 |
| I03 | И‑118/P01,P03; DESIGN.md; no_manifest | Даже точное исключение не принимает неполный пакет. | bundle_incomplete · archive / members |
| I04 | И‑118/P01,P03; DESIGN.md; path_input | И‑118 отвергает путь без открытия. | bundle_incomplete · archive / bytes |
| I05 | И‑118/P01,P03; DESIGN.md; live | Выход за стенд остаётся отказом И‑118. | bundle_incomplete · target / stand_only |
| N01 | И‑118/P01,P03; DESIGN.md; require_type | Требование подписи — точный bool. | bundle_trust_invalid · policy / shape |
| N02 | И‑118/P01,P03; DESIGN.md; policy_extra | Чужое поле не меняет политику и не отражается в диагностике. | bundle_trust_invalid · policy / shape |
| N03 | И‑118/P01,P03; DESIGN.md; keys_duplicate | Дубликат ключа недопустим. | bundle_trust_invalid · policy / duplicate |
| N04 | И‑118/P01,P03; DESIGN.md; public_length | Ключ строго 32 байта. | bundle_trust_invalid · policy / shape |
| N05 | И‑118/P01,P03; DESIGN.md; approver_id | Неверный ID утверждающего не нормализуется. | bundle_trust_invalid · policy / shape |
| N06 | И‑118/P01,P03; DESIGN.md; approver_duplicate | Дубликат утверждающего недопустим. | bundle_trust_invalid · policy / duplicate |
| N07 | И‑118/P01,P03; DESIGN.md; too_many_keys | Число ключей ограничено. | bundle_trust_invalid · policy / limit |
| N08 | И‑118/P01,P03; DESIGN.md; now_offset | Произвольное смещение не канонический UTC. | bundle_trust_invalid · clock / utc |
| N09 | И‑118/P01,P03; DESIGN.md; invalid_now | Несуществующая дата now отвергается. | bundle_trust_invalid · clock / utc |
| N10 | И‑118/P01,P03; DESIGN.md; missing_expiry | Запись без expiry не бессрочная по умолчанию. | bundle_trust_invalid · exceptions / shape |
| N11 | И‑118/P01,P03; DESIGN.md; missing_approver | Без approver исключение не засчитывается. | bundle_trust_invalid · exceptions / shape |
| N12 | И‑118/P01,P03; DESIGN.md; duplicate_exception | Не выбираем из нескольких записей для одного ZIP. | bundle_trust_invalid · exceptions / duplicate |
| N13 | И‑118/P01,P03; DESIGN.md; upper_hash | Неканонический SHA‑256 отвергнут. | bundle_trust_invalid · exceptions / shape |
| N14 | И‑118/P01,P03; DESIGN.md; expiry_offset | Допустим только строгий UTC с Z. | bundle_trust_invalid · exceptions / expiry |
| N15 | И‑118/P01,P03; DESIGN.md; invalid_expiry | Несуществующая дата expiry отвергнута. | bundle_trust_invalid · exceptions / expiry |
| N16 | И‑118/P01,P03; DESIGN.md; exception_extra | Непредусмотренное поле не ослабляет требования. | bundle_trust_invalid · exceptions / shape |
| N17 | И‑118/P01,P03; DESIGN.md; too_many_exceptions | Ограничение реестра проверяется целиком. | bundle_trust_invalid · exceptions / limit |
| N18 | И‑118/P01,P03; DESIGN.md; exceptions_list | Неверная форма контейнера исключений отвергнута. | bundle_trust_invalid · exceptions / shape |

### Отдельно: not run

| Что | Почему |
| --- | --- |
| Реальные ключи, подписание и выпуск пакета, ротация и отзыв. | Только открытые учебные векторы на повторе, нет хранилища или подключения поставщика ключей. |
| Происхождение политики, аутентификация approver и защищённые часы в эксплуатации. | Отдельные доверенные входы стенда; утверждающий, время и исключения не берутся из ZIP. |
| Рабочий перенос, установка, отказоустойчивое восстановление и откат (И‑120). | Результат только диагностика политики; нет активации и записи. |
| Реальные данные, рабочий порт, адаптеры/CI и иные среды. | Нет регистрации операции; повтор требует наличия OpenSSL с Ed25519 на согласованном стенде. |

## П7–П9. Печать и сверка

`python3 -B research/119/run.py` воспроизводит исследование на согласованном стенде: нужен доступный OpenSSL с Ed25519, а не закрытый ключ. `python3 -B research/119/run.py --verify-seal` только сверяет сохранённые данные, [печать](SEAL.json), [повтор](REPLAY.json), отчёт и HTML без записи. Страница и записи о печати не входят в её состав.

[Стратегия v1.21](../STRATEGY.md) · [сверка №29](../strategy/SYNC-LOG.md). A1–A4, P0, порядок, вехи, критерии и пригодность прежние. Commit/push только 20 путей И‑119 разрешены отдельно ([основание](DESIGN.md)). П9 подтверждается по SHA в `origin/arena/4e000a5e-isyncai` и побайтным повтором из снимка коммита на открытых данных. И‑120 не начата; Ф4 открыта, М2 остаётся стендовой.
