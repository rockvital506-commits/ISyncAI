# И‑120 — Откат к точному N‑1 и журнал переключений

`arena/4e000a5e-isyncai` · Ф4. Пакет, целостность, доверие · P2

## П0–П2. Сверка, замысел и RED

[Замысел](DESIGN.md) · v1.21 · `83553b045b640d69dccb476fe10ab7e04f0e9c86`. Согласованный fetch совпал; [печать И‑119](../119/REPLAY.json) проверена без записи. Рабочий порт не изменён.

[RED](RED.json): rc 1, 0 pass / 50 fail / 0 not run. Базовый Git-снимок дал те же байты вывода. Контроль до реализации уже читает три различных синтетических L1 штатным читателем; неуспех относится к отсутствующей операции И‑120.

[Корпус](CASES.json) `0803a53ad58c61c6de2a0d2dfe60961c9b43b97ea1d3da9ad52f07da78ecba76` · [оракул](test_bundle_rollback.py) `dab91cfa18c87e87ba9941d02f65ca3a01032b5f67ef16c961360671b3dafee9`. B и C собраны независимо из точного синтетического A; ни код из ZIP, ни закрытые ключи для повтора не нужны.

## П3–П5. Два полных прогона

`python3 -B -I -S -X utf8 research/120/test_bundle_rollback.py` · Linux, Python 3.11.2. В чистой копии только 13 входов.

| Процесс | Случаи | rc | basis |
| --- | --- | --- | --- |
| П3 · рабочая копия | 50 pass / 0 fail / 0 not run | 0 | [CHECKOUT.json](CHECKOUT.json) |
| П4 · чистая копия | 50 pass / 0 fail / 0 not run | 0 | [CLEANROOM.json](CLEANROOM.json) |

[ACCEPTANCE.json](ACCEPTANCE.json): **accepted** · 12 pass / 0 fail / 4 not run по воротам и отложенным группам.

| Ворота | Статус | basis | criterion |
| --- | --- | --- | --- |
| frozen_red | pass | CASES.json; RED.json; ITERATION.json | 50 случаев и оракул закреплены до продукта; RED 0/50/0 равен базовому Git-снимку. |
| checkout | pass | CHECKOUT.json; CASES.json | Все 50 наблюдений, порядок и диагностики равны независимому оракулу; rc0 без stderr. |
| cleanroom | pass | CLEANROOM.json; CASES.json | Все 50 наблюдений, порядок и диагностики равны независимому оракулу; rc0 без stderr. |
| exact_previous | pass | P01/P02/P05/P07; R01–R07/R10 | Выбран непосредственный прежний SHA; нет подбора по revision, обхода, фиктивного шага или второго отката. |
| v2_readback | pass | P01/P02; CASES.json:readbacks; штатный read_registry + status | Чтение прежнего v2 L1 снова работает и совпало с исходным B; L0/L2 прежние, revision 7 не определяет текст. |
| current_trust | pass | P03; T01–T10; R08/R09; И‑118 и И‑119 | Целостность первая, затем свежая политика; истечение на apply и неверная/непроверенная подпись блокируют, журнал не даёт исключения сам. |
| confirmation | pass | P06; C01–C08; T04 | План не пишет; чужое, повторное или устаревшее подтверждение не заменяет точный план и его входы. |
| journal_and_limits | pass | P07/R11; J01–J10; R03 | Неверная форма, связь или квитанция не исправляется; предыстория сохранена, один слот по счётчику оставлен для N‑1. |
| single_replace | pass | W01; P01–P07; снимки файла и перехват replace | До замены виден целый прежний файл, после — целый новый; при отказе нет даже частичного события. |
| stand_boundary | pass | N01–N03; снимки стендов; control.working_port | Никакой рабочей цели, операции порта или утечки пути, билета и текста ошибки в результат; стенды убраны. |
| fresh_copy | pass | ITERATION.json; CLEANROOM.json | Чистая копия — только 13 входов; без рабочих данных, Git, сервера подписи или записи в дерево входов. |
| repeat | pass | CHECKOUT.json; CLEANROOM.json | Идентичные входные байты и полный одинаковый результат в двух процессах. |

## П6. Что наблюдалось

В измеряемой части прогона (без подготовки начальных журналов): **6** переключений (2 вперёд, 4 назад), 1 план без записи, 43 отказа. У 43 отказов нет изменения состояния. Из 7 попыток замены завершились 6; W01 остановлен до смены файла.

| Снимок | revision L1 | SHA‑256 ZIP | SHA‑256 L1 |
| --- | --- | --- | --- |
| A | 7 | `5c95478a90f6328c21068527d44ed35462f1a5f36b8120835b49ef85f86494d3` | `db6a1cf80fc0b2c979b1a4974f999d77721962b57d44ca00ba6bcc68a1aaf0df` |
| B | 7 | `ee90f13eff0b192cf04115f4ace78435d32dbe1f9881462c7a4236100b101f1a` | `667377cf3b740fcf435c68947bbb51bddfd8ec57f6a0220efb2c65a58016d1af` |
| C | 7 | `c3ac4783ea1c6e96e855c19a97289c5643119b77c564ee027e1b3fd791905539` | `fbea39515e6545557c636da47b554949ed18cd46598981c7e8b63bb8fad5d877` |

**Точное восстановление B (P01/P02).** `read_registry` и `status` на свежей копии получили L1 `667377cf3b740fcf435c68947bbb51bddfd8ec57f6a0220efb2c65a58016d1af`, тот же отпечаток текста, что до перехода на C (`ac20d7bb1141277116997d79d6cf7ec09afc4c793a8b5f878c249f9bc7668d1d`). В P02 чтение текущего C сначала отказало `digest_mismatch`, однако предыстория и проверяемые байты B сохранились. L0 (`ed913353bbd88521670e2913c22819eb06d3287a6f716bc3d51653bb8dbea549`) и L2 (`5e0875fbda69e9564829844259eaf3d377ba30d75b903cb998ef0a76c5059f7d`) побайтно прежние. Это работоспособность чтения сохранённого состояния на стенде, не выполнение его правил.

| Факт | basis | criterion / предел |
| --- | --- | --- |
| История, а не revision, выбирает N‑1. | P01/P02, R01–R07 | Самосогласованный ZIP B_rebuilt и более старый A оставляют B единственным кандидатом. После отката нет автоматического второго шага. |
| Старый допуск не заменяет проверку. | P03, T01–T10, R08/R09 | И‑118 прежде политики; ровно в expiry или при недоступной проверке подписи нет перехода, в том числе после полученного плана. |
| Указатель и журнал — одна замена. | P04/P07, J01–J10, W01 | Во время попытки замены старый файл цел, новый записан рядом. Успех сохраняет весь префикс. Сбой до замены не выдаёт частичного успеха. |
| Согласие точно и одноразово. | P06, C01–C08, T04 | Старый билет не срабатывает даже при том же активном SHA и изменившейся цепочке. Билет не аутентификация владельца. |

### Корпус

| ID | basis | criterion | Наблюдалось |
| --- | --- | --- | --- |
| P01 | CASES.json:P01; DESIGN.md | Цепочка A→B→C, затем точный B: прежний результат штатного чтения возвращён, C отличался. | rollback · #4 · unsigned/optional |
| P02 | CASES.json:P02; DESIGN.md | Нечитаемый N не мешает вернуться к B: текущий ZIP даёт digest_mismatch, после отката чтение B снова работает. | rollback · #4 · unsigned/optional |
| P03 | CASES.json:P03; DESIGN.md | Точное действующее исключение на A позволяет стендовый переход; в журнале unsigned/exception. | rollback · #3 · unsigned/exception |
| P04 | CASES.json:P04; DESIGN.md | Первый подтверждённый выбор из пустого журнала даёт seq=1, from=null и SHA точного A. | rollout · #1 · unsigned/optional |
| P05 | CASES.json:P05; DESIGN.md | Новый подтверждённый rollout после отката продвигает историю, не заменяет прежние записи. | rollout · #4 · unsigned/optional |
| P06 | CASES.json:P06; DESIGN.md | Предварительный план на B показывает точные состояния до/после, но не меняет байты, inode или журнал. | planned · без записи |
| P07 | CASES.json:P07; DESIGN.md | На 31 записи остаётся шаг для N‑1; успешный откат добавляет 32-ю, без обрезки. | rollback · #32 · unsigned/optional |
| R01 | CASES.json:R01; DESIGN.md | В пустом журнале нет N‑1, даже если B проверяем. | plan: rollback_unavailable · journal / no_previous |
| R02 | CASES.json:R02; DESIGN.md | После первого выбора N‑1 ещё нет. | plan: rollback_unavailable · journal / no_previous |
| R03 | CASES.json:R03; DESIGN.md | После отката второй откат не возвращает отброшенный N и не ищет иной пакет. | plan: rollback_unavailable · journal / no_previous |
| R04 | CASES.json:R04; DESIGN.md | Более старый принятый A не заменяет непосредственный предшествующий B. | plan: rollback_unavailable · archive / not_previous |
| R05 | CASES.json:R05; DESIGN.md | Текущий C с той же ревизией не является N‑1. | plan: rollback_unavailable · archive / not_previous |
| R06 | CASES.json:R06; DESIGN.md | Самосогласованная пересборка B при той же revision не заменяет точный SHA B. | plan: rollback_unavailable · archive / not_previous |
| R07 | CASES.json:R07; DESIGN.md | Если точные байты N‑1 не предъявлены, не искать другой архив. | plan: rollback_unavailable · archive / missing |
| R08 | CASES.json:R08; DESIGN.md | Изменение содержимого при правильном CRC сохраняет исходный digest_mismatch. | plan: digest_mismatch · files / sha256 |
| R09 | CASES.json:R09; DESIGN.md | Отсутствующий манифест сохраняет исходный bundle_incomplete. | plan: bundle_incomplete · archive / members |
| R10 | CASES.json:R10; DESIGN.md | Rollout того же активного ZIP не добавляет фиктивный успешный шаг. | plan: rollout_no_change · archive / already_active |
| R11 | CASES.json:R11; DESIGN.md | Rollout не занимает последнюю позицию журнала, оставленную для N‑1. | plan: rollout_limit · journal / capacity |
| T01 | CASES.json:T01; DESIGN.md | Пережитая проверка при optional не даёт права обойти текущее требование подписи. | plan: rollout_blocked · trust / signature_required |
| T02 | CASES.json:T02; DESIGN.md | Ровно в expiry исключение для точного N‑1 уже не действует. | plan: rollout_blocked · trust / exception_expired |
| T03 | CASES.json:T03; DESIGN.md | Действующее при плане исключение проверяется в apply заново; в expiry запись запрещена. | apply: rollout_blocked · trust / exception_expired |
| T04 | CASES.json:T04; DESIGN.md | Переход optional→exception меняет согласованный дифф, даже если новая политика допустила ZIP. | apply: rollout_stale · plan / assessment |
| T05 | CASES.json:T05; DESIGN.md | Решение чужого approver не разблокирует прежний пакет. | plan: rollout_blocked · trust / exception_approver |
| T06 | CASES.json:T06; DESIGN.md | Известная открытая подпись И‑119 без явно доступного проверяющего не превращается в unsigned. | plan: rollout_blocked · trust / verifier_unavailable |
| T07 | CASES.json:T07; DESIGN.md | При повреждённом ZIP и неверной политике раньше срабатывает целостность. | plan: digest_mismatch · files / sha256 |
| T08 | CASES.json:T08; DESIGN.md | Неявный формат часов не заменяется временем из журнала или ZIP. | plan: bundle_trust_invalid · clock / utc |
| T09 | CASES.json:T09; DESIGN.md | Исключение к другому SHA не действует на B с той же revision. | plan: rollout_blocked · trust / signature_required |
| T10 | CASES.json:T10; DESIGN.md | Предъявленная подпись неправильной формы блокирует даже optional. | plan: rollout_blocked · trust / shape |
| C01 | CASES.json:C01; DESIGN.md | Предварительный план без отдельного подтверждения не применим. | apply: rollout_unconfirmed · plan / ticket |
| C02 | CASES.json:C02; DESIGN.md | Чужой билет из другой сессии для того же плана не подтверждает запись. | apply: rollout_unconfirmed · plan / ticket |
| C03 | CASES.json:C03; DESIGN.md | Подмена SHA в уже выданном плане отвергается при верном билете. | apply: rollout_unconfirmed · plan / changed |
| C04 | CASES.json:C04; DESIGN.md | Булево true в поле целого формата нельзя принять за первоначальный план. | apply: rollout_unconfirmed · plan / changed |
| C05 | CASES.json:C05; DESIGN.md | Иная связная история с тем же активным C обрывает подтверждение старого плана. | apply: rollout_stale · journal / changed |
| C06 | CASES.json:C06; DESIGN.md | Иной валидный ZIP при той же revision не проходит apply согласованного продвижения. | apply: rollout_stale · archive / changed |
| C07 | CASES.json:C07; DESIGN.md | Новая попытка плана гасит прежний билет, даже если новая цель не N‑1. | apply: rollout_unconfirmed · plan / ticket |
| C08 | CASES.json:C08; DESIGN.md | Попытка применения без согласия гасит билет; повтор с исходным билетом не проходит. | apply: rollout_unconfirmed · plan / ticket |
| J01 | CASES.json:J01; DESIGN.md | Неполный журнал отвергается, текст парсера не выводится. | plan: rollout_state_invalid · journal / json |
| J02 | CASES.json:J02; DESIGN.md | Разорванная связь from/to обнаружена до выбора пакета. | plan: rollout_state_invalid · journal / chain |
| J03 | CASES.json:J03; DESIGN.md | Активный SHA не может расходиться с последним событием. | plan: rollout_state_invalid · journal / chain |
| J04 | CASES.json:J04; DESIGN.md | Повтор поля JSON не принимается за корректный журнал. | plan: rollout_state_invalid · journal / json |
| J05 | CASES.json:J05; DESIGN.md | Булево seq не является счётчиком журнала. | plan: rollout_state_invalid · journal / shape |
| J06 | CASES.json:J06; DESIGN.md | Записанный откат мимо N‑1 делает журнал непригодным. | plan: rollout_state_invalid · journal / chain |
| J07 | CASES.json:J07; DESIGN.md | Журнал больше 64 КиБ отклоняется, не разбирается как состояние. | plan: rollout_state_invalid · journal / limit |
| J08 | CASES.json:J08; DESIGN.md | Прежняя квитанция с чужой revision не соответствует тому же ZIP. | plan: rollout_state_invalid · journal / receipt |
| J09 | CASES.json:J09; DESIGN.md | Неканоническое представление состояния не исправляется молча. | plan: rollout_state_invalid · journal / encoding |
| J10 | CASES.json:J10; DESIGN.md | Незнакомый формат журнала не мигрируется и не переписывается. | plan: rollout_state_invalid · journal / shape |
| W01 | CASES.json:W01; DESIGN.md | Сбой до единственного replace оставляет старый SHA и весь журнал; билет не переиспользуется. | apply: rollout_write_failed · state / replace |
| N01 | CASES.json:N01; DESIGN.md | Цель live отвергается до создания временного каталога. | init: rollout_invalid · target / stand_only |
| N02 | CASES.json:N02; DESIGN.md | Вызов вне открытой сессии не создаёт состояние. | plan: rollout_invalid · session / inactive |
| N03 | CASES.json:N03; DESIGN.md | Действие install не входит в стенд отката. | plan: rollout_invalid · operation / unknown |

### Отдельно: not run

| Что | Почему |
| --- | --- |
| Рабочий роллаут, установка, откат живого L1/L0 или исполнение правил. | Только выбор снимка, локальный журнал и чтение синтетики; не мерили применение и не трогали живой порт. |
| Параллельные писатели, обрыв питания, долговечность и частичные сбои реальной установки. | Один писатель и введённый сбой до одной замены; не аварийное восстановление И‑132. |
| Защищённость журнала, источника политики и часов, реальные подписи и постоянное решение Д7. | Явный доверенный стенд; подписывание не выполнялось, открытая криптопроверка относится к И‑119. |
| Миграция, слияние живых L1, адаптеры и CI. | Другие операции, данные и точки контроля; работа в них не разрешена. |

## П7–П9. Печать и сверка

`python3 -B research/120/run.py` воспроизводит исследование (Python stdlib, без сети, новых ключей и OpenSSL). `python3 -B research/120/run.py --verify-seal` сверяет [печать](SEAL.json), [повтор](REPLAY.json), отчёт и HTML без записи. Страница и записи о самой печати не входят в её состав. Исследовательская печать не является одним из пакетов A/B/C.

[Стратегия v1.22](../STRATEGY.md) · [сверка №30](../strategy/SYNC-LOG.md). A1–A4, P0, порядок, вехи, критерии и пригодность прежние. Публикация ровно 20 путей разрешена отдельно ([основание](DESIGN.md)); П9 подтверждается по SHA в `origin/arena/4e000a5e-isyncai` и побайтным повтором из снимка коммита. Печати И‑117–И‑119 сверены из их опубликованных снимков. По §6 Ф4 закрывается после подтверждения П9 только в измеренном стендовом объёме; рабочий откат и пригодность не приняты. Д7 не решён; И‑121 не начата.
