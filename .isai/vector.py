"""Canonical Master Goal & Orientation Vector of ISyncAI (ISAI v1.0.0)."""

from __future__ import annotations

from isai.domain_models import MasterVectorHorizon, MasterVectorPillar, MasterVectorSpec

MASTER_VECTOR = MasterVectorSpec(
    version="1.0.0",
    north_star_statement=(
        "Построить портативную, самодостаточную, коэволюционную мета-операционную систему "
        "симбиоза Пользователя и любого ИИ-агента/модели (ISAI), превращающую репозиторий в "
        "строго типизированный, самоверифицируемый фрактальный граф объектов. В этой среде "
        "модель получает только предвычисленный релевантный контекст без шума (RSoC), любые "
        "исследования и разработки исполняются фазово и транзакционно под контролем детерминированного "
        "Watchdog, а подтверждённый практический опыт непрерывно дистиллируется в развивающиеся "
        "хранилища знаний и профиля оператора при 100% неприкосновенности конституционного "
        "Genesis-фрейма."
    ),
    core_objectives=(
        "Минимизация и хирургическая точность данных в контекстном окне модели (Resultant Set of Context — RSoC) с изоляцией служебных метаданных графа в детерминированном слое.",
        "Строгий транзакционный контроль мутаций через кольца целостности (IL-0..IL-3), стейджинг в /tasks/, счётчики дескрипторов (HandleCount) и инкрементальную оценку каскадного влияния (Salsa Early-Cutoff).",
        "Управляемое двухконтурное исполнение любых пользовательских задач: пофазовый макро-граф (Task DAG с локальным перепланированием при сбоях) + микро-цикл ISAI-PEP v1 с двухступенчатой верификацией (Deterministic Gate A + Semantic Gate B).",
        "Непрерывная коэволюция симбиоза без информационного ожирения: дистилляция закрытых тасков в атомарные единицы /knowledge/ и актуализация компетенций /user/ с полной трассировкой в неизменяемом журнале Chrono-Graph.",
        "Универсальная портативность и развёртываемость: способность подключать любую внешнюю или локальную модель через драйвер корня (/.isai/ + AGENTS.md) и инициализировать чистую систему ISAI в новых репозиториях.",
    ),
    architectural_pillars=(
        MasterVectorPillar(
            pillar_id="P1_GENESIS_IMMUTABILITY",
            title="Конституционный абсолютизм (Ring 0 Genesis Kernel)",
            essence="Первые 14 строк начального README.md (586 байт) образуют вечный аксиоматический геном системы, проверяемый криптографически при каждом аудите.",
            governing_axioms=("THIS-FRAME >> ALL-SUBSEQUENT", "ZERO-Redundancy", "Redundancy=FATAL"),
            mechanisms=(
                "Побайтовая SHA-256 верификация заголовка /README.md в службе isai audit.",
                "Четыре кольца целостности (IL_0_GENESIS, IL_1_KERNEL, IL_2_CANONICAL, IL_3_STAGING).",
            ),
        ),
        MasterVectorPillar(
            pillar_id="P2_FRACTAL_ISOMORPHISM",
            title="Фрактальный дуализм папок-объектов (Human README <-> Agent .isai)",
            essence="Корень и каждая функциональная директория являются типизированными ООП-узлами с синхронизированным интерфейсом для человека (README.md) и формальной Pydantic-моделью для агента (.isai/node.py).",
            governing_axioms=("DRY-Fidelity[atomic | DRY | modular | reusable]", "Hierar-Logic[top-down-topology | explicit-mapping | zero-orphan-nodes]"),
            mechanisms=(
                "Четырёхкомпонентная схема ISAINodeSpec: Logic + Adapter + Sync + Router.",
                "Автоматическая проекция паспорта узла в README.md и сверка spec_digest без ручного дублирования.",
                "Сквозная типизированная адресация EntityRef (isai://<scope>[#<symbol>]) и запрет файлов-сирот.",
            ),
        ),
        MasterVectorPillar(
            pillar_id="P3_HIVE_TOPOLOGY_AND_RSOC",
            title="Ульевая макро-топология и компиляция контекста (Windows NT Hives & GPO RSoC)",
            essence="Разделение системного ядра (/.isai/), профиля оператора (/user/), эмпирической базы знаний (/knowledge/) и операционной арены (/tasks/) с предвычислением минимального рабочего набора для каждой фазы.",
            governing_axioms=("ZERO-Redundancy", "Hierar-Logic[explicit-mapping]"),
            mechanisms=(
                "Служба RSoC (Resultant Set of Context): сборка Enforced-инвариантов, контракта целевого узла и целевых выборок из /user/ и /knowledge/.",
                "Изоляция Control Plane (графы ссылок, хеши, дескрипторы удерживаются в Watchdog вне промпта модели).",
            ),
        ),
        MasterVectorPillar(
            pillar_id="P4_PHASED_TRANSACTIONAL_RUNTIME",
            title="Двухконтурный фазовый рантайм и событийный Watchdog",
            essence="Все разработки и исследования проходят через изолированный стейджинг /tasks/, микро-протокол ISAI-PEP v1 (до 3 итераций) и атомарный промоушен только после зелёного вердикта детерминированного валидатора.",
            governing_axioms=("AUDIT → CONSTRUCT → CHRONICLE", "Order=Absolute | Logic=Linear"),
            mechanisms=(
                "Градуированные режимы фаз: FAST_READ (без мутаций) и STAGED_TRANSACTION (полный CBS-стейджинг).",
                "Таблица дескрипторов Watchdog (READ / WRITE_LEASE) с автоочисткой при HandleCount == 0.",
                "Инкрементальное отсечение ложных каскадов по публичному дайджесту контракта (Salsa interface_digest).",
            ),
        ),
        MasterVectorPillar(
            pillar_id="P5_COEVOLUTIONARY_CHRONICLE",
            title="Коэволюционная память и дистилляция опыта (Chrono-Graph + Upsert Knowledge)",
            essence="Завершённые таски не захламляют систему сырыми логами, а переплавляются в переиспользуемые паттерны знаний и обновления профиля пользователя с неизменяемой историей переходов.",
            governing_axioms=("Chrono-Graph[versioning | immutable-log | state-tracking]", "DRY-Fidelity"),
            mechanisms=(
                "Append-only журнал транзакций .isai/chronicle.jsonl + мгновенный срез tasks/.isai/state_snapshot.json.",
                "Дедуплицирующий Upsert-каталог практических знаний /knowledge/ и калибровочных компетенций /user/.",
            ),
        ),
    ),
    evolution_horizons=(
        MasterVectorHorizon(
            stage="Horizon 1 — Self-Hosting Bootstrap (v0.1, TASK-000)",
            focus="Ядро Pydantic v2, 4 корневых улья, верификатор Genesis/Topology/Sync, компилятор RSoC и первая запись хроники.",
            exit_condition="100% прохождение 'python -m isai audit' и автотестов самоверификации на ревизии rev=1.",
        ),
        MasterVectorHorizon(
            stage="Horizon 2 — Active Task & Watchdog Orchestration (v0.2)",
            focus="Автоматизированные CLI-команды жизненного цикла тасков (start-task, run-phase, promote, replan) и каскадные планы адаптации.",
            exit_condition="Полный цикл создания нового доменного узла через CLI стейджинга /tasks/ с проверкой Early-Cutoff.",
        ),
        MasterVectorHorizon(
            stage="Horizon 3 — Portable Seed & Multi-Agent Driver (v0.3)",
            focus="Генератор 'isai init' для чистых репозиториев, экспорт/линковка профиля /user/ и локальный MCP-шлюз поверх движка ISAI.",
            exit_condition="Инициализация внешнего пустого репозитория одной командой с переносом калибровки оператора.",
        ),
    ),
    anti_goals=(
        "Никаких фоновых LLM-демонов с постоянным поллингом — все системные службы строго событийные (Trigger-Start) и детерминированные.",
        "Никакого ручного дублирования одних и тех же правил в нескольких файлах (AGENTS.md остаётся тонким загрузчиком-указателем).",
        "Никакого хранения сырых черновиков закрытых задач в /tasks/ или /knowledge/ после дистилляции и фиксации в хронике.",
        "Никакого дробления /user/ и /knowledge/ до тысяч микро-папок на каждый единичный факт — группировка только осмысленными доменными узлами.",
    ),
)
