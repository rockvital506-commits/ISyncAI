# Улей оператора (`user/`)

Данная директория представляет собой аналог улья `HKCU` в архитектуре **ISAI**: структурированное хранилище когнитивного профиля, директив взаимодействия и матрицы компетенций пользователя (`isai://user#OperatorProfile`).

<!-- ISAI:SYNC:BEGIN -->
<!-- isai:node_id=isai://user -->
<!-- isai:spec_digest=9d3a7be81298d5776efd9d11ccadca9c1ecd33919e844c7858ede12863066a7d -->
<!-- isai:interface_digest=116cf18fdfe073301accb2b8e7261b3632e3ed7c13b9630148313b827ed6d191 -->

## Паспорт узла `isai://user` — Улей когнитивного профиля и компетенций оператора (User Twin / HKCU)

- **Уровень целостности:** `IL_2_CANONICAL` | **Видимость:** `PUBLIC`
- **Родительский узел:** `isai://root`
- **Цель (`Goal`):** Хранить и развивать верифицированную модель оператора (когнитивный стиль, инженерные директивы и матрицу компетенций) для точной калибровки любой подключаемой модели без пересказа очевидных базовых концепций.

### Критерии успеха (`Success Criteria`)
- Профиль содержит только подтверждённые директивы и компетенции без домыслов.
- Компилятор 'isai rsoc' выбирает из профиля релевантные задаче теги компетенций.
- Любое обновление профиля проходит через фазовый CRUD и фиксируется в хронике.

### Функционал (`Capabilities`)
- Хранение типизированного объекта USER_PROFILE (UserProfileSpec) в user/.isai/profile.py.
- Фильтрация компетенций по доменным тегам при сборке контекста фазы (RSoC).
- Переносимая калибровка глубины, строгости и формата коммуникации модели.

### Локальные инварианты (`Invariants`)
- Запрет на галлюцинацию неподтверждённых биографических или технических фактов об операторе.
- Соответствие архетипу Genesis-ядра: FiduSys-Novator & Chronitect.

### Адаптер и Связывание Портов (`Adapter & Port Wirings`)
- **Входы (`Inputs`):**
  - `verified_skill_or_preference_delta` (`CompetencyRecord | CognitiveDirective`, опциональный) [схемы: `isai.domain_models:CompetencyRecord`, `isai.domain_models:CognitiveDirective`] — Подтверждённое в ходе совместных тасков обновление навыков или предпочтений оператора.
- **Выходы (`Outputs`):**
  - `operator_calibration_slice` (`dict[str, Any]`, гарантированный) [схемы: `builtins:dict`] — Компактный срез директив и релевантных компетенций для включения в RSoC.

### Реестр владения и верифицируемых символов (`Ownership & Symbol Bindings`)
- **Файлы узла (`owned_files`):** `README.md`
- **Служебные файлы (`system_files`):** `.isai/node.py`, `.isai/profile.py`
- **Экспортируемые сущности (`symbol_bindings`):**
  - `isai://user#OperatorProfile` (`python_attr` → `profile.py:USER_PROFILE`, видимость: `PUBLIC`)

### Типизированные связи и Маршрутизация (`Typed Links & Router`)
- **Типизированные связи (`links`):**
  - `isai://root#GenesisKernel` [`GOVERNED_BY` | RSoC: `NONE`]
  - `isai://root#RSoCCompiler` [`CALIBRATES` | RSoC: `INTERFACE_STUB`] — Подача калибровочного среза в компилятор RSoC.
  - `isai://tasks#WatchdogService` [`CONSUMES_CONTRACT` | RSoC: `INTERFACE_STUB`] — Транзакционный контроль мутаций профиля.
  - `isai://root#NeuroVascularFundamental` [`GOVERNED_BY` | RSoC: `NONE`] — Подчинение субгенетическому нервно-сосудистому фундаменталу IL-1C.
- **Допустимые переходы (`transitions`):**
  - При `inject_into_rsoc` → `isai://root#RSoCCompiler` [режим: `FAST_READ`] — Передача релевантного среза профиля в компилятор контекста фазы.
  - При `evolve_operator_profile` → `isai://tasks` [режим: `STAGED_TRANSACTION`] — Инициация транзакционной фазы обновления компетенций по итогам практической работы.

<!-- ISAI:SYNC:END -->
