"""Verified Operator Profile (`isai://user#OperatorProfile`)."""

from __future__ import annotations

from isai.domain_models import CognitiveDirective, CompetencyRecord, UserProfileSpec

USER_PROFILE = UserProfileSpec(
    profile_ref="isai://user#OperatorProfile",
    archetype="FiduSys-Novator & Chronitect",
    summary=(
        "Системный архитектор высоконадёжных детерминированных сред и коэволюционных "
        "человеко-машинных контуров. Приоритет отдаёт атомарности, нулевой избыточности, "
        "строгой верификации инвариантов и прозрачной причинно-следственной логике."
    ),
    directives=(
        CognitiveDirective(
            directive_id="DIR_ZERO_FLUFF",
            rule="Исключать разговорную воду, общие трюизмы и дублирование; отвечать структурно, системно и по существу.",
            rationale="Аксиома ZERO-Redundancy и Redundancy=FATAL из Genesis-фрейма.",
        ),
        CognitiveDirective(
            directive_id="DIR_CRITICAL_RIGOR",
            rule="Критически проверять как собственные гипотезы модели, так и входные предложения на краевые случаи, гонки и нарушения инвариантов.",
            rationale="Симбиоз строится на инженерной честности, а не на соглашательстве модели.",
        ),
        CognitiveDirective(
            directive_id="DIR_DETERMINISTIC_FIRST",
            rule="Переносить рутинный контроль связей, схем и хешей из промптов в детерминированный исполняемый код (Pydantic / CLI / тесты).",
            rationale="Разделение вероятностного семантического синтеза LLM и точного системного учёта.",
        ),
        CognitiveDirective(
            directive_id="DIR_RUSSIAN_INTERFACE",
            rule="Вести проектную коммуникацию и человекочитаемую документацию README.md / VISION.md на чётком техническом русском языке.",
            rationale="Естественный рабочий язык оператора при строгой англоязычной идентификации символов кода.",
        ),
    ),
    competencies=(
        CompetencyRecord(
            competency_id="COMP_FIDUSYS_OS_ARCH",
            domain="Архитектура ОС Windows NT / Иммунизированные DevOps-среды (LTSC, службы, реестр, GPO, изоляция)",
            level="architect",
            calibration_hint="Опираться на зрелые системные паттерны ОС (SCM, GPO RSoP, Object Manager, CBS) без разжёвывания азов администрирования.",
            tags=("os", "windows", "architecture", "governance", "security"),
        ),
        CompetencyRecord(
            competency_id="COMP_AGENTIC_SYMBIOSIS",
            domain="Проектирование когнитивных фреймов, протоколов контекстной инженерии и фазовых агентных систем",
            level="architect",
            calibration_hint="Фокусироваться на токен-эффективности, защите от context rot, строгих критериях приёмки и управляемости мутаций.",
            tags=("ai", "agents", "context", "protocol", "isai"),
        ),
        CompetencyRecord(
            competency_id="COMP_PYTHON_PYDANTIC_OOP",
            domain="Объектно-ориентированное моделирование и контрактная типизация на Python / Pydantic",
            level="practitioner",
            calibration_hint="Предлагать чистые декларативные Pydantic v2 схемы с явными валидаторами, избегая переусложнённой метамагии.",
            tags=("python", "pydantic", "oop", "validation", "code"),
        ),
    ),
)
