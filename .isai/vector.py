"""Canonical Master Goal & Orientation Vector of ISyncAI (ISAI v1.2.5)."""

from __future__ import annotations

from isai.domain_models import MasterVectorHorizon, MasterVectorPillar, MasterVectorSpec

MASTER_VECTOR = MasterVectorSpec(
    version="1.2.5",
    mutability_policy=(
        "GOVERNED_MUTABLE: Эволюционирует строго через цикл AUDIT -> CONSTRUCT -> CHRONICLE "
        "под верховенством неизменяемого IL-0 Genesis Frame; при выявлении критических отклонений "
        "активирует 6-шаговый Алгедонический контур эскалации к Оператору."
    ),
    north_star_statement=(
        "Построить портативную, самодостаточную, коэволюционную мета-операционную систему "
        "симбиоза Пользователя и любого ИИ-агента/модели (ISAI), в которой репозиторий функционирует "
        "как единый типизированный фрактальный организм с несущей нервно-сосудистой системой. "
        "Нервный контур обеспечивает двунаправленную проприоцепцию гиперграфа (EAVT/VAET), "
        "детерминированные спинальные рефлексы допуска (AST/BDCT/Rings) и транзакционную пластичность связей, "
        "а сосудистый контур доставляет в окно модели хирургически точный графовый контекст (RSoC) "
        "через гематоэнцефалический барьер видимости, дистиллируя практический опыт и прецеденты в живую память "
        "при 100% неприкосновенности конституционного ядра IL-0 и суверенном контроле Оператора над "
        "условно-мутируемыми субконституционными фундаменталами (IL-1C)."
    ),
    core_objectives=(
        "Многоуровневый конституционализм и суверенитет Оператора: абсолютная неизменяемость базового фрейма IL-0 (README.md[0:586]) в сочетании с условно-мутируемым субгенетическим слоем IL-1C (сжатыми символическими мета-промптами калибровки ISAI-LNTE), изменяемым исключительно через 6-шаговый Алгедонический протокол с явной ратификацией Оператором.",
        "Когнитивная пред-калибровка агента (ISAI-LNTE v2.0): бимодальная компоновка правил под U-образную кривую внимания трансформера (Primacy Sink + Recency Tripwires), BPE-целостные морфемные якоря со строгой привязкой к исполняемым символам кода и нулевая терпимость к смысловой избыточности (ZERO-Redundancy).",
        "Замкнутая нервная система репозитория: однократная декларация связей на источнике с однопроходной индексацией EAVT/VAET ('isai graph'), предзагрузочный AST-фильтр чистоты манифестов, префлайт 'can-mutate', Finalizer-блокировка удаления и атомарная AST-хирургия связей/портов/символов ('isai link') с побайтовым откатом.",
        "Замкнутая сосудистая система контекста и гомеостаза: артериальная подача графового пакета RSoC с 1-hop интерфейсными стабами соседей, барьер колец видимости (PUBLIC / SUBTREE / EPHEMERAL_STAGING), капиллярная совместимость портов BDCT со структурными JSON-дайджестами схем (Salsa Early-Cutoff) и коагуляционное восстановление после сбоев ('isai recover').",
        "Иммунная память прецедентов и трёхуровневая верификация: закрепление всех обнаруженных ловушек среды и рантайма в реестре эмпирических паттернов (/knowledge/), сопровождаемое контрактной матрицей, тестами полного отката дерева и генеративным Stateful фаззингом (Hypothesis RuleBasedStateMachine).",
    ),
    architectural_pillars=(
        MasterVectorPillar(
            pillar_id="P1_TIERED_CONSTITUTION_AND_ALGEDONIC_GOVERNANCE",
            title="Эшелонированный конституционализм (IL-0 -> IL-1C -> IL-1..3) и Алгедонический шлюз",
            essence="Разделение вечного генома IL-0, условно-мутируемого нервно-сосудистого фундаментала IL-1C и рабочих колец IL-1..IL-3 по кибернетической модели жизнеспособной системы (VSM S1..S5).",
            governing_axioms=("THIS-FRAME >> ALL-SUBSEQUENT", "ZERO-Redundancy", "Order=Absolute | Logic=Linear"),
            mechanisms=(
                "Криптографический замок SHA-256 на первых 586 байтах /README.md (IL_0_GENESIS) и запрет любых WRITE_LEASE к нему.",
                "Двухрежимная маршрутизация отклонений: автономное поглощение рутинных сбоев гомеостазом (ISAI-PEP v1, до 3 итераций) против прямой Алгедонической эскалации к Оператору при критическом расхождении с целями.",
                "Строгая 6-шаговая процедура изменения фундаменталов IL-1C: подтверждение отклонения -> предупреждение Оператора -> масштабное исследование -> рекомендация механизмов -> пофазовый таск -> запуск строго после согласия Оператора.",
            ),
        ),
        MasterVectorPillar(
            pillar_id="P2_LNTE_COGNITIVE_CALIBRATION_DSL",
            title="Символическая калибровка трансформера (ISAI-LNTE v2.0 & Bimodal Attention)",
            essence="Формализация системных правил в виде компактного символического мета-языка спецификаций, согласованного с механикой BPE-токенизации, Attention Sinks и RoPE-затухания.",
            governing_axioms=("DRY-Fidelity[atomic | DRY | modular | reusable]", "Redundancy=FATAL"),
            mechanisms=(
                "Бимодальная сэндвич-топология промпт-фреймов: якорная шапка приоритетов (Primacy Head), секционированное ядро (Bracket-YAML + TOON) и хвостовые стоп-предохранители (Recency Tripwires).",
                "Двухслойный лексикон без BPE-фрагментации: дефисные композиты из высокочастотных корней, алгебраически связанные (:=) с точными CLI-командами и классами ядра.",
                "Полная совместимость текста калибровочных фреймов со сканером Markdown-прозы и запрет неэкранированных артефактов.",
            ),
        ),
        MasterVectorPillar(
            pillar_id="P3_NERVOUS_HYPERGRAPH_AND_ATOMIC_ACTUATION",
            title="Нервная система: EAVT/VAET проприоцепция, спинальные рефлексы и AST-инжектор",
            essence="Единый контур восприятия, рефлекторной защиты и транзакционной перестройки всех связей, ссылок, символов и переходов репозитория.",
            governing_axioms=("Hierar-Logic[top-down-topology | explicit-mapping | zero-orphan-nodes]", "ZERO-Redundancy"),
            mechanisms=(
                "Однопроходный индекс HypergraphIndex ('isai graph query | can-mutate | affected-tests') без ручных обратных ссылок и без двойной индексации SYNC-блоков.",
                "Предзагрузочный AST-контроль чистоты .isai/node.py и прямая компиляция UTF-8 исходников без коллизий .pyc-кэша PEP 3147 (int(mtime), size).",
                "Транзакционный инжектор LinkMutator ('isai link') поверх atomic_transaction_batch с полным pre-image откатом всех затрагиваемых и синхронизируемых файлов.",
            ),
        ),
        MasterVectorPillar(
            pillar_id="P4_VASCULAR_RSOC_BBB_AND_HEMOSTASIS",
            title="Сосудистая система: артерия RSoC, барьер колец видимости, порты BDCT и коагуляция",
            essence="Бесшумное кровоснабжение модели релевантным контекстом, строгая фильтрация межслойных взаимодействий и мгновенная остановка кровотечений при сбоях среды.",
            governing_axioms=("AUDIT → CONSTRUCT → CHRONICLE", "Order=Absolute | Logic=Linear"),
            mechanisms=(
                "Компилятор 'isai rsoc' v0.2.0: поставка контракта активного узла, инвариантов предков, 1-hop стабов соседей и теговых срезов /user/ и /knowledge/ без дампов Control Plane.",
                "Гематоэнцефалический барьер колец видимости (VisibilityScope, SymbolVisibility) и проверка подтипов портов BDCT со структурным JSON-хешем Pydantic-схем.",
                "Служба TaskWatchdog и 'isai recover': TTL-аренды MVCC, чистка оборванных транзакций и регламент реанимации виртуального окружения (.venv) либо перехода в Pure-LLM режим.",
            ),
        ),
        MasterVectorPillar(
            pillar_id="P5_IMMUNE_PRECEDENTS_AND_COEVOLUTION",
            title="Иммунная память прецедентов, дистилляция знаний и трёхуровневый оракул",
            essence="Превращение каждого сбоя, исследования и закрытого таска в постоянный иммунитет системы без накопления информационного шлака.",
            governing_axioms=("Chrono-Graph[versioning | immutable-log | state-tracking]", "DRY-Fidelity"),
            mechanisms=(
                "Неизменяемый журнал .isai/chronicle.jsonl + дедуплицирующий каталог практических паттернов и прецедентов /knowledge/ + профиль калибровки /user/.",
                "Трёхуровневый контур самоверификации /tests/: матрица контрактов и видимости (T1) + проверка побайтового отката и dry-run (T2) + генеративный автомат Hypothesis RuleBasedStateMachine (T3).",
            ),
        ),
    ),
    evolution_horizons=(
        MasterVectorHorizon(
            stage="Horizon 1 — Self-Hosting Bootstrap & Crash Immunity (v0.1..v0.1.5, TASK-000..001) [COMPLETED]",
            focus="Ядро Pydantic v2, 5 канонических ульев, физическая верификация символов, 360°-сканер графа и прозы, атомарный I/O и Crash Recovery.",
            exit_condition="100% прохождение 'isai audit' и идемпотентного 'isai recover' на ревизии rev=2.",
        ),
        MasterVectorHorizon(
            stage="Horizon 2 — Bidirectional Hypergraph, Link Injector & Stateful Fuzzing (v0.2.0, TASK-002) [COMPLETED]",
            focus="Типизированные связи EdgeLinkSpec, коммутация портов PortWiringSpec (BDCT), индекс EAVT/VAET ('isai graph'), транзакционный LinkMutator ('isai link'), графовый RSoC v0.2.0 и Hypothesis-фаззинг.",
            exit_condition="Полное прохождение трёхуровневых кросс-тестов (20/20) и 360°-аудита на ревизии rev=3.",
        ),
        MasterVectorHorizon(
            stage="Horizon 3 — Sub-Genesis Neuro-Vascular Fundamental Integration & Runtime Hardening (v0.2.5, TASK-003) [COMPLETED]",
            focus="Бесшовное внедрение условно-мутируемого кольца IL-1C (ISAI-NVF v1.0, .isai/neuro_vascular.py <-> FUNDAMENTAL.md) без потери смыслов, сверка SHA-256 по RATIFY_FUNDAMENTAL в хронике, 6-шаговый Алгедонический автомат AlgedonicDeviationCase, бимодальный RSoC v0.2.5 (Primacy Head + Terminal Recency Guard) и реентерабельная OS-блокировка записи (fcntl.flock).",
            exit_condition="100% прохождение трёхуровневых тестов (28/28, включая Hypothesis AlgedonicGovernanceMachine), 'isai nv verify' и 360°-аудита на ревизии rev=6.",
        ),
        MasterVectorHorizon(
            stage="Horizon 4 — Sharded Hypergraph, Atomic Subtree Move, Portable Seed & MCP Gateway (v0.3+, Next)",
            focus="Инкрементальное шардирование индекса для сотен узлов, композитный атомарный перенос поддеревьев (move-node), бюджетируемый многошаговый RSoC, генератор 'isai init' для чистых репозиториев и локальный MCP-сервер поверх 'isai rsoc / nv / graph / link'.",
            exit_condition="Мгновенное развёртывание ISAI во внешнем репозитории и суб-миллисекундная индексация при масштабировании.",
        ),
    ),
    anti_goals=(
        "Никаких фоновых LLM-демонов с постоянным поллингом — все системные рефлексы и службы строго событийные и детерминированные.",
        "Никаких несанкционированных или молчаливых изменений субгенетических фундаменталов IL-1C в обход 6-шагового Алгедонического протокола и явного подтверждения Оператора.",
        "Никаких несвязанных с кодом эзотерических неологизмов, ломающих BPE-токенизацию или провоцирующих галлюцинацию несуществующих CLI-команд.",
        "Никаких ручных обратных ссылок (referenced_by), ручных правок SYNC-блоков и хранения временного кэша (.hypothesis/, .venv/) в индексе Git.",
    ),
)
