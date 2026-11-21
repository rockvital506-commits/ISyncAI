# И‑117 — Неполный пакет не собирается

`arena/4e000a5e-isyncai` · Ф4. Пакет, целостность, доверие · P1

## П0–П2. Сверка, замысел, контроль

[Границы согласия](DESIGN.md) · стратегия `v1.18` · HEAD `66d7cf67569dda5f75f2e2e61c0cb4a1bfb12dcd`. [Печать И‑116](../116/REPLAY.json) подтверждена до правок. Сборка полного среза отличается от проверки уже полученного пакета; рабочий порт не менялся.

[RED.json](RED.json): rc 1, 0 pass / 46 fail / 0 not run; вывод из базового `git archive` совпал. Положительный контроль отдельно принял обе формы голого v2 и два валидных контейнера истории. Сборщик ещё отсутствовал; порт вернул `unknown_operation` для обеих операций.

[Манифест эксперимента](ITERATION.json) закрепляет 14 материалов. SHA‑256 [корпуса](CASES.json) `e99f4edd7ded8267b1d094923456bd218b8858eaeb601ded4aaedbf2d450bd40`, [оракула](test_bundle.py) `96160383ce20c0554e95de88279d6967d412233259c858e6fdac7f053d25f2b3`.

Первый прогон с продуктом: 45/1/0, P05. Порядок ключей изменился при сохранении корпуса после расчёта эталона. Восстановлен исходный порядок полей фикстуры, не критерий, вектор, продукт или код теста; базовый RED повторён. Исходные отпечатки и причина: `RED.json.fixture_correction`.

## П3–П5. Два прогона и приёмка

`python3 -B -I -S -X utf8 research/117/test_bundle.py` · Linux, Python 3.11.2. В чистой копии только 18 объявленных входов.

| Процесс | Обязательные строки | rc | basis |
| --- | --- | --- | --- |
| П3 · рабочая копия | 46 pass / 0 fail / 0 not run | 0 | [CHECKOUT.json](CHECKOUT.json) |
| П4 · чистая копия | 46 pass / 0 fail / 0 not run | 0 | [CLEANROOM.json](CLEANROOM.json) |

[ACCEPTANCE.json](ACCEPTANCE.json): **accepted** · 10 pass / 0 fail / 4 not run по воротам и отложенным группам.

| Ворота | Статус | basis | criterion |
| --- | --- | --- | --- |
| frozen_red | pass | DESIGN.md; CASES.json; ITERATION.json; RED.json | Исходный RED 0/46/0 до продукта; коррекция порядка полей P05 не меняла эталоны и критерии, тот же RED из базы. |
| checkout | pass | CHECKOUT.json; CASES.json; test_bundle.py | Ровно все ID в том же порядке, rc0: байты, манифесты, отказы и счётчики совпали с независимым оракулом. |
| cleanroom | pass | CLEANROOM.json; CASES.json; test_bundle.py | Ровно все ID в том же порядке, rc0: байты, манифесты, отказы и счётчики совпали с независимым оракулом. |
| complete_package | pass | P01–P06; CASES.json: golden; test_bundle.py: inspect_known_archive | 16 точных полезных членов и один манифест; пустой валидный L1 не ошибка, digest манифеста не SHA-256 ZIP. |
| determinism_and_raw_bytes | pass | P02/P04/P05/P06; golden; BUNDLE.json | Перестановка ничего не меняет; изменение байтов меняет хеш даже при равной revision и при той же форме JSON. |
| every_missing_member | pass | M01–M16; CASES.json; Monitor | Каждый пропуск отдельно даёт bundle_incomplete до ZIP, без частичного результата. |
| source_boundaries | pass | N01–N20/N22–N24; контроль валидных журналов | Вне разрешения: L2, история, чужие корни, пути, лимиты и неверные реестры; локальный валидный контейнер не экспортируется. |
| no_effects_or_partial | pass | N21; Monitor; оба прогона | Поздняя ошибка не отдаёт буфер; побочного I/O и вывода нет, входы неизменны. |
| isolation | pass | ITERATION.json; CLEANROOM.json | Свежая копия содержит только 18 входов; нет Git, донора, установки и рабочего профиля. |
| repeat | pass | CHECKOUT.json; CLEANROOM.json | Одинаковые свидетельства и хеши входов в двух отдельных процессах. |

## П6. Что собрано и что отвергнуто

[Synthetic-Bundle-117.zip](Synthetic-Bundle-117.zip) — пример продукта P01, **не** дистрибутив и не ZIP исследования. `revision` = 7, `roots` = `kit, profiles/staged`, 16 файлов и `manifest.json`.

| Величина | Значение | basis |
| --- | --- | --- |
| Digest манифеста | `300af66638088f51fc2e079d2cbf75bc30144f62f2e0c5ef8a12b6a7fc54bee5` | P01; JSON полей revision/roots/files, без digest и LF |
| SHA‑256 ZIP продукта | `5c95478a90f6328c21068527d44ed35462f1a5f36b8120835b49ef85f86494d3` | P01; 109297 точных байт, 17 членов |
| SHA‑256 печати исследования | [SEAL.json](SEAL.json) | Другой архив: входы, отчёт, оракул и готовый пример |

| Файл P01 | Байт | SHA‑256 |
| --- | --- | --- |
| `kit/base/OPERATION-CARD.md` | 10741 | `bc813fc73b789a8e735891983277a0baf392270e045d3ce804cdfcbeb84d5ce0` |
| `kit/base/OPERATION-PLAN.md` | 8788 | `97437182f4e44cc6bf0b90fb48b2732adb87438b1e0ff597b827e522d0e57020` |
| `kit/base/SCHEMA-V2.md` | 7308 | `da724c1857f909e9f4d66f11661c3f16fae9cdba994ab2750191223e3e366907` |
| `kit/base/START.md` | 3091 | `37530109f6e2c572b2754da605ea3f6858be7606cf3297bb65805a61e7dd284d` |
| `kit/base/STORAGE-V2.md` | 6333 | `b6994db63420965242ce4c7d1bc9ba045271a4bd190beeb9723f8ceca04b75cb` |
| `kit/base/bootstrap.py` | 4103 | `de6ef1ae140d85077311a3aa97bb6350462b0ef465e91b1bb4ee8b34466f3a36` |
| `kit/base/entry.txt` | 20 | `814d05acdb697a572b3f171f27b939478d56398c3ba2ba22e1820d868fac867e` |
| `kit/base/operation_card.py` | 15714 | `fc8856f1543e91b3625001427a5cb39d2d7d39ca6838b40eb6d20101e4955e09` |
| `kit/base/operation_plan.py` | 5555 | `15c8844f4bb61f2c512d956534eca111aafbbfb4e18196d9157793df40b6002b` |
| `kit/base/profile_journal.py` | 3409 | `6868cf7a7c9a4b8f95eeb31065478c4d7f4a6321f8a73b07faab902f2ad54ce8` |
| `kit/base/registry.json` | 96 | `ed913353bbd88521670e2913c22819eb06d3287a6f716bc3d51653bb8dbea549` |
| `kit/base/registry_journal.py` | 5339 | `2c9f5b0daba2dbd4f840530ef81e049896e13e03fe2a1023688e443857419eb6` |
| `kit/base/registry_policy.py` | 4235 | `788430a67a0d456a20f5d774f768bdd9baab00041b0c51bef9f673e45e246872` |
| `kit/base/registry_store.py` | 19772 | `ed4c7877d9c2661f843e546a2e671caed5d695e99b1c4a502c74438d6af21243` |
| `kit/base/schema_v2.py` | 8814 | `0b5f2912ff01b431f6591cf2fcd2dac513a31ea62b976f1a1d1e714c56645abd` |
| `profiles/staged/registry.json` | 1756 | `db6a1cf80fc0b2c979b1a4974f999d77721962b57d44ca00ba6bcc68a1aaf0df` |

На прогон: 6 успехов и 40 отказов; 16 одиночных пропусков. 39 отказов до создания ZIP; сбой восьмой записи N21 не дал и частичного результата. Всего 7 попыток создать буфер ZIP, 110 попыток записать член, 0 попыток файлового/сетевого I/O. Входы прежние.

| Факт | basis | criterion / предел |
| --- | --- | --- |
| Полноту нельзя вывести из списка, присланного самим вызывающим. | M01–M16; N04–N07/N23/N24 | Пропуск любого из 16 даёт отказ, лишнее имя или привязка к L2 не упаковываются; разрешённый пустой профиль проходит. |
| Порядок передачи не меняет результат, но исходные байты имеют значение. | P02/P04/P05/P06 | Перестановка даёт тот же ZIP; другое тело или форматирование при revision 7 меняет digest; revision 8 берётся из L1. |
| Валидный журнал остаётся локальным. | N17/N18; положительный контроль; PROFILE-JOURNAL.md | Оба целых контейнера 1 и 2 отвергаются без скрытого извлечения. В образце голый v2; P01 И‑114–И‑116 не включён. |
| Не выполняется код из пакета и не ставится Kit. | test_bundle.py: Monitor и inspect_known_archive | Читатель сверяет только известный синтетический результат, а не произвольный полученный архив или источник доверия. |

### Корпус

| ID | basis | criterion | Наблюдалось |
| --- | --- | --- | --- |
| P01 | Ф4; v2; независимый вектор P01 | Точные 16 полезных членов, отдельно manifest.json; все размеры, хеши и байты совпали. | bundled · 17 членов |
| P02 | P01; перестановка ключей | Обратный порядок входных имён даёт побайтно тот же архив и манифест. | bundled · 17 членов |
| P03 | v2: пустые entries; Ф4 | Полная раскладка с пустым валидным L1, revision 0 — не отсутствие файла. | bundled · 17 членов |
| P04 | §3.2; P01; независимый вектор | Смена текста при той же revision меняет SHA‑256 L1, digest и итоговый ZIP, но не остальные члены. | bundled · 17 членов |
| P05 | Ф4; точные входные байты | Валидный JSON с другими пробелами не переписывается; байты, а не только смысл, связываются хешем. | bundled · 17 членов |
| P06 | §3.2; метаданные L1 | Манифест получает изменённую ревизию из профиля; L0 и прочие файлы не затронуты. | bundled · 17 членов |
| M01 | Ф4 И‑117; обязательный набор | Пропуск kit/base/OPERATION-CARD.md останавливает сборку до открытия буфера. | bundle_incomplete · files / missing |
| M02 | Ф4 И‑117; обязательный набор | Пропуск kit/base/OPERATION-PLAN.md останавливает сборку до открытия буфера. | bundle_incomplete · files / missing |
| M03 | Ф4 И‑117; обязательный набор | Пропуск kit/base/SCHEMA-V2.md останавливает сборку до открытия буфера. | bundle_incomplete · files / missing |
| M04 | Ф4 И‑117; обязательный набор | Пропуск kit/base/START.md останавливает сборку до открытия буфера. | bundle_incomplete · files / missing |
| M05 | Ф4 И‑117; обязательный набор | Пропуск kit/base/STORAGE-V2.md останавливает сборку до открытия буфера. | bundle_incomplete · files / missing |
| M06 | Ф4 И‑117; обязательный набор | Пропуск kit/base/bootstrap.py останавливает сборку до открытия буфера. | bundle_incomplete · files / missing |
| M07 | Ф4 И‑117; обязательный набор | Пропуск kit/base/entry.txt останавливает сборку до открытия буфера. | bundle_incomplete · files / missing |
| M08 | Ф4 И‑117; обязательный набор | Пропуск kit/base/operation_card.py останавливает сборку до открытия буфера. | bundle_incomplete · files / missing |
| M09 | Ф4 И‑117; обязательный набор | Пропуск kit/base/operation_plan.py останавливает сборку до открытия буфера. | bundle_incomplete · files / missing |
| M10 | Ф4 И‑117; обязательный набор | Пропуск kit/base/profile_journal.py останавливает сборку до открытия буфера. | bundle_incomplete · files / missing |
| M11 | Ф4 И‑117; обязательный набор | Пропуск kit/base/registry.json останавливает сборку до открытия буфера. | bundle_incomplete · files / missing |
| M12 | Ф4 И‑117; обязательный набор | Пропуск kit/base/registry_journal.py останавливает сборку до открытия буфера. | bundle_incomplete · files / missing |
| M13 | Ф4 И‑117; обязательный набор | Пропуск kit/base/registry_policy.py останавливает сборку до открытия буфера. | bundle_incomplete · files / missing |
| M14 | Ф4 И‑117; обязательный набор | Пропуск kit/base/registry_store.py останавливает сборку до открытия буфера. | bundle_incomplete · files / missing |
| M15 | Ф4 И‑117; обязательный набор | Пропуск kit/base/schema_v2.py останавливает сборку до открытия буфера. | bundle_incomplete · files / missing |
| M16 | Ф4 И‑117; обязательный набор | Пропуск profiles/staged/registry.json останавливает сборку до открытия буфера. | bundle_incomplete · files / missing |
| N01 | П1; границы стенда | Рабочая цель отвергнута без сборки. | bundle_incomplete · target / stand_only |
| N02 | П1; байты без путей | Объект пути не читается как набор файлов. | bundle_incomplete · files / shape |
| N03 | Замкнутая форма набора | Нестроковое имя не приводится к строке. | bundle_incomplete · files / shape |
| N04 | Раздельность L0/L1/L2; §14 | Проектный реестр не включается в комплект. | bundle_incomplete · files / unexpected |
| N05 | PROFILE-JOURNAL.md; §14 | Отдельный локальный журнал не включается. | bundle_incomplete · files / unexpected |
| N06 | Точные имена; область стенда | Имя ../ не нормализуется и не заменяет отсутствующий файл. | bundle_incomplete · files / unexpected |
| N07 | Анти-скоуп; Git policy | Лишнее имя из чужой области не упаковывается. | bundle_incomplete · files / unexpected |
| N08 | Явные bytes | Bytearray не преобразуется автоматически. | bundle_incomplete · files / bytes |
| N09 | Полнота входа | Пустой стартовый файл отличается от валидного пустого реестра. | bundle_incomplete · files / bytes |
| N10 | Лимит файла | Вход больше 1 МиБ не начинает сборку. | bundle_incomplete · files / limit |
| N11 | Лимит комплекта | Сумма больше 4 МиБ при допустимых отдельных размерах не начинает сборку. | bundle_incomplete · files / limit |
| N12 | Строгий v2 | Повтор JSON-поля отвергнут без выбора значения. | bundle_incomplete · system / registry |
| N13 | §3.2; v2 L0 | Неизвестная форма версии не подменяется версией профиля. | bundle_incomplete · system / registry |
| N14 | Явный L0; A1 | Иной допустимый лексически корень L0 не подходит набору. | bundle_incomplete · system / roots |
| N15 | Явный L1; A1 | Рабочий или пересекающийся корень не подставляется. | bundle_incomplete · profile / roots |
| N16 | Authority и область v2 | Данные L2 не маскируются именем файла L1. | bundle_incomplete · profile / registry |
| N17 | Локальный контейнер 2; §14 | Даже валидный журнальный контейнер 2 не копируется и не очищается автоматически. | bundle_incomplete · profile / local_history |
| N18 | Локальный контейнер 1; §14 | Даже валидный прежний контейнер 1 не становится переносимым. | bundle_incomplete · profile / local_history |
| N19 | A4; v2 | Сиротская запись не попадает в архив. | bundle_incomplete · profile / registry |
| N20 | v2 L1 | Булево значение не принимается за целую revision. | bundle_incomplete · profile / registry |
| N21 | П1; поздний сбой буфера | Ошибка восьмой записи не возвращает ни частичный ZIP, ни частичный результат. | bundle_incomplete · archive / build |
| N22 | Строгий UTF-8 v2 | Битый JSON нельзя упаковать по имени файла. | bundle_incomplete · profile / registry |
| N23 | Замкнутый список имён | start.md не считается START.md даже при другом регистре ФС. | bundle_incomplete · files / unexpected |
| N24 | Детерминированный манифест | Вызывающий не может навязать собственный manifest.json. | bundle_incomplete · files / unexpected |

### Не выполнялось

| Что | Почему |
| --- | --- |
| Проверка полученного или подменённого пакета (И‑118). | Зафиксированы сверка эталонного результата сборки и воспроизведение исследования, а не внешний bundle_verify. |
| Подпись, доверие, pin установленного выпуска и исключения (И‑119). | SHA‑256 связывает байты, но не подтверждает происхождение или разрешение. |
| Установка, рабочий перенос, откат и живой агент (И‑120 и последующие). | Код из ZIP не исполнялся, L2 и рабочий L1 не читались и не писались. |
| Реальные данные, секреты/PII, Windows/ACL и конкурентное восстановление. | Явная синтетика, нет обхода путей или проверки произвольного содержимого; текущее доказательство на Linux. |

## П7–П9. Печать, повтор, сверка

`python3 -B research/117/run.py` воспроизводит комплект. `python3 -B research/117/run.py --verify-seal` сверяет [печать](SEAL.json), точный пример, [запись повтора](REPLAY.json), отчёт и страницу без записи. Страница и записи о печати не являются членами исследовательского ZIP.

[Стратегия v1.19](../STRATEGY.md) · [сверка №27](../strategy/SYNC-LOG.md). A1–A4, P0, критерии, порядок, вехи и пригодность прежние. Commit/push только 21 пути И‑117 разрешены отдельно ([основание](DESIGN.md)). После сверки с `origin/arena/4e000a5e-isyncai` локальный HEAD выровнен без изменения рабочих файлов. П9 подтверждается совпадением SHA и повтором из снимка коммита. И‑118 не начата; Ф4 открыта.
