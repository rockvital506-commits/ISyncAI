"""
Загрузчик «вселенной» ISAI для лаборатории эмбеддинг-исследований.

Ключевое решение (и оно оказалось решающим для всех результатов): **смысл сущности берётся
из её исполняемой спецификации, а не из места, где она упомянута**. Первая версия этого модуля
читала `node.py` как текст и получала для `ChronicleLedger` строку `"ChronicleLedger
chronicle.jsonl"` — имя и путь, без единого слова о том, что это *реестр событий*. Векторная
логика на таком тексте не могла попасть в цель ни при каком пороге, и это не недостаток
эмбеддингов, а недостаток источника смысла.

Поэтому здесь три слоя:

1. **Паспорт** (`node.py`) — что существует и как называется.
2. **Реализация** (`docstring` + сигнатура + тело) — что это *значит*.
3. **Смысловая единица** (`KnowledgeEntry`, элементы MasterVector) — зачем это нужно.

Вектор строится по слоям 2–3; слой 1 даёт адрес.
"""

from __future__ import annotations

import ast
import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

# ---------------------------------------------------------------------------
# Корпусный эмбеддер (offline, deterministic, dependency-free)
# ---------------------------------------------------------------------------

_SUFFIXES = (
    "иями", "ями", "ами", "ого", "ему", "ому", "ыми", "ими", "ей", "ой", "ый", "ий", "ая",
    "ое", "ые", "ие", "ов", "ев", "ам", "ям", "ах", "ях", "ом", "ем", "ы", "и", "а", "я",
    "о", "е", "у", "ю", "ь", "s", "es", "ed", "ing",
)

STOPWORDS = {
    "и", "в", "во", "не", "что", "он", "на", "я", "с", "со", "как", "а", "то", "все", "она",
    "так", "его", "но", "да", "ты", "к", "у", "же", "вы", "за", "бы", "по", "только", "ее",
    "мне", "было", "вот", "от", "меня", "еще", "нет", "о", "из", "ему", "теперь", "когда",
    "даже", "ну", "вдруг", "ли", "если", "уже", "или", "ни", "быть", "был", "него", "до",
    "вас", "нибудь", "опять", "уж", "вам", "ведь", "там", "потом", "себя", "ничего", "ей",
    "может", "они", "тут", "где", "есть", "надо", "ней", "для", "мы", "тебя", "их", "чем",
    "была", "сам", "чтоб", "без", "будто", "чего", "раз", "тоже", "себе", "под", "будет",
    "ж", "тогда", "кто", "этот", "того", "потому", "этого", "какой", "совсем", "ним",
    "здесь", "этом", "один", "почти", "мой", "тем", "чтобы", "нее", "сейчас", "были", "куда",
    "зачем", "всех", "никогда", "можно", "при", "наконец", "два", "об", "другой", "хоть",
    "после", "над", "больше", "тот", "через", "эти", "нас", "про", "всего", "них", "какая",
    "много", "разве", "три", "эту", "моя", "впрочем", "хорошо", "свою", "этой", "перед",
    "иногда", "лучше", "чуть", "том", "нельзя", "такой", "им", "более", "всегда", "конечно",
    "всю", "между", "the", "a", "an", "and", "or", "of", "to", "in", "is", "are", "for",
    "on", "with", "as", "by", "at", "be", "this", "that", "it", "from", "not", "but", "its",
}


def tokenize(text: str) -> list[str]:
    """Токены без разметки, с грубым детерминированным стеммингом и без стоп-слов."""
    text = text.lower().replace("ё", "е")
    out: list[str] = []
    for w in re.findall(r"[a-z0-9_]+|[а-я0-9_]+", text):
        for suf in _SUFFIXES:
            if len(w) > len(suf) + 2 and w.endswith(suf):
                w = w[: -len(suf)]
                break
        if len(w) >= 2 and w not in STOPWORDS:
            out.append(w)
    return out


def _hash_bucket(token: str, dim: int) -> tuple[int, int]:
    h = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
    v = int.from_bytes(h, "big")
    return v % dim, 1 if (v >> 63) & 1 else -1


@dataclass(frozen=True)
class CorpusEmbedder:
    """
    Хеширующий эмбеддер с сублинейным TF и IDF — «нижняя граница» векторной логики.

    Он не требует обучения, детерминирован (blake2b, не `hash()`), работает на смешанном
    русско-английском корпусе и даёт вектор за O(len(text)). Если даже он обыгрывает
    дискретные ссылки, выигрыш даёт сама векторная логика, а не качество модели.
    """

    dim: int = 512
    idf: dict[str, float] = field(default_factory=dict)
    _fitted: bool = False

    def fit(self, documents: Iterable[str]) -> "CorpusEmbedder":
        docs = list(documents)
        df: Counter[str] = Counter()
        for d in docs:
            df.update(set(tokenize(d)))
        n = max(len(docs), 1)
        object.__setattr__(self, "idf", {t: math.log((1 + n) / (1 + c)) + 1.0 for t, c in df.items()})
        object.__setattr__(self, "_fitted", True)
        return self

    def embed(self, text: str) -> tuple[float, ...]:
        if not self._fitted:
            raise RuntimeError("CorpusEmbedder.fit() must be called before embed()")
        vec = [0.0] * self.dim
        counts = Counter(tokenize(text))
        if not counts:
            return tuple(vec)
        for token, tf in counts.items():
            weight = (1.0 + math.log(tf)) * self.idf.get(token, 1.0)
            bucket, sign = _hash_bucket(token, self.dim)
            vec[bucket] += sign * weight
        norm = math.sqrt(sum(v * v for v in vec))
        return tuple(v / norm for v in vec) if norm > 0 else tuple(vec)

    def embed_many(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        return [self.embed(t) for t in texts]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """
    Настоящий косинус, а не скалярное произведение.

    Соблазн считать dot-продуктом («векторы уже нормированы») стоил мне часа отладки: как
    только векторы приходят из *разных* фитов (или из ненормированного источника), dot молча
    даёт нули вместо отрицательных и малых значений. Функция имени `cosine` обязана считать
    косинус независимо от того, что о нормах думает вызывающий код.
    """
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na > 0 and nb > 0 else 0.0


def top_k(query: Sequence[float], vectors: Sequence[Sequence[float]], k: int = 5) -> list[tuple[int, float]]:
    scores = [(i, cosine(query, v)) for i, v in enumerate(vectors)]
    scores.sort(key=lambda iv: (-iv[1], iv[0]))
    return scores[:k]


# ---------------------------------------------------------------------------
# Сущности
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Entity:
    uri: str
    kind: str
    text: str
    meta: dict[str, str] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.uri.rsplit("#", 1)[-1].rsplit("/", 1)[-1]


def rel_path_to_scope(rel: Path) -> str:
    posix = rel.as_posix()
    return "isai://root" if posix in (".", "") else f"isai://{posix}"


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return ""


IGNORE_PARTS = {".venv", ".git", ".hypothesis", "__pycache__", ".pytest_cache", "research"}


def _skipped(path: Path) -> bool:
    return any(part in IGNORE_PARTS for part in path.parts)


def load_module_spec(path: Path, attr: str):
    """Загрузить Pydantic-спецификацию из файла, не полагаясь на `.pyc`-кеш."""
    import sys as _sys
    import types

    src = _read(path)
    if not src:
        return None
    module = types.ModuleType(f"_lab_{attr}_{abs(hash(str(path))) % 100000}")
    module.__file__ = str(path)
    _sys.modules[module.__name__] = module
    try:
        exec(compile(src, str(path), "exec"), module.__dict__)  # noqa: S102
        return getattr(module, attr, None)
    except Exception:
        return None
    finally:
        _sys.modules.pop(module.__name__, None)


def load_universe(repo_root: Path) -> list[Entity]:
    """
    Собрать вселенную: узлы, их паспортные символы, Python-символы, знания, вектор, документы.

    Смысловой текст каждой сущности — то, что о ней *сказано в её спецификации*: docstring,
    сигнатура, distilled_insight, goal/invariants паспорта, north_star и цели вектора.
    """
    root = Path(repo_root).resolve()
    entities: list[Entity] = []

    # --- 1. Python-символы ядра и узловых пакетов --------------------------------
    for pkg in sorted(root.rglob(".isai")):
        if not pkg.is_dir() or _skipped(pkg.relative_to(root)):
            continue
        scope = rel_path_to_scope(pkg.parent.relative_to(root))
        for py in sorted(pkg.glob("*.py")):
            src = _read(py)
            try:
                tree = ast.parse(src)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if node.name.startswith("_"):
                    continue
                doc = ast.get_docstring(node) or ""
                if isinstance(node, ast.ClassDef):
                    sig = f"class {node.name}(" + ", ".join(ast.unparse(b) for b in node.bases) + ")"
                else:
                    sig = f"def {node.name}({ast.unparse(node.args)})"
                entities.append(
                    Entity(
                        f"{scope}#{node.name}",
                        "symbol",
                        f"{sig} {doc}",
                        {"path": str(py.relative_to(root)), "declared_in": py.name},
                    )
                )

    # --- 2. Паспорта узлов: имя, цель, инварианты, объявленные символы -----------
    for node_py in sorted(root.rglob(".isai/node.py")):
        if _skipped(node_py.relative_to(root)):
            continue
        src = _read(node_py)
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        node_id = ""
        fields: dict[str, object] = {}
        declared: list[tuple[str, str]] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and isinstance(node.value, ast.Constant):
                if node.arg in {"node_id", "goal", "title"}:
                    fields[node.arg] = str(node.value.value)
                if node.arg == "node_id":
                    node_id = str(node.value.value)
            if isinstance(node, ast.keyword) and node.arg in {"success_criteria", "invariants", "capabilities"}:
                if isinstance(node.value, (ast.Tuple, ast.List)):
                    fields[node.arg] = [
                        str(el.value) for el in node.value.elts if isinstance(el, ast.Constant)
                    ]
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") in {
                "SymbolBindingSpec",
                "IOPortSpec",
                "TransitionRule",
            }:
                kv = {
                    kw.arg: str(kw.value.value)
                    for kw in node.keywords
                    if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str)
                }
                ident = (
                    kv.get("symbol")
                    or kv.get("port_name")
                    or kv.get("input_port")
                    or kv.get("output_port")
                    or kv.get("transition_id")
                    or ""
                )
                if ident:
                    declared.append((ident, kv.get("target", "")))
        readme = _read(node_py.parent.parent / "README.md")[:2500]
        parts: list[str] = [
            str(fields.get("title", "")),
            str(fields.get("goal", "")),
        ]
        for key in ("success_criteria", "invariants", "capabilities"):
            value = fields.get(key)
            if isinstance(value, list):
                parts.extend(value)
        parts.append(readme)
        entities.append(Entity(node_id, "node", " ".join(parts), {"path": str(node_py)}))

        for ident, target in declared:
            meaning = _symbol_meaning(root, target)
            entities.append(
                Entity(
                    f"{node_id}#{ident}",
                    "passport_symbol",
                    f"{ident} {target} {meaning}",
                    {"path": str(node_py), "declared_in": "node.py", "bound_target": target},
                )
            )

    # --- 3. Каталог знаний: смысловая единица с обоснованием ---------------------
    for catalog in sorted(root.rglob(".isai/catalog.py")):
        if _skipped(catalog.relative_to(root)):
            continue
        spec = load_module_spec(catalog, "KNOWLEDGE_CATALOG")
        entries = getattr(spec, "entries", ()) if spec is not None else ()
        if entries:
            for entry in entries:
                entities.append(
                    Entity(
                        f"isai://knowledge#{entry.entry_id}",
                        "knowledge",
                        f"{entry.title} {entry.distilled_insight} {' '.join(entry.applicability_tags)}",
                        {"category": entry.category, "origin": entry.origin_tx_id},
                    )
                )
        else:  # fallback: статический разбор, если спецификация не загрузилась
            tree = ast.parse(_read(catalog) or "pass")
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "KnowledgeEntry":
                    kv = {
                        kw.arg: str(kw.value.value)
                        for kw in node.keywords
                        if isinstance(kw.value, ast.Constant)
                    }
                    if kv.get("entry_id"):
                        entities.append(
                            Entity(
                                f"isai://knowledge#{kv['entry_id']}",
                                "knowledge",
                                " ".join([kv.get("title", ""), kv.get("distilled_insight", "")]),
                            )
                        )

    # --- 4. Master Vector: цели, анти-цели, столпы, горизонты --------------------
    mv_path = root / ".isai" / "vector.py"
    mv = load_module_spec(mv_path, "MASTER_VECTOR") if mv_path.is_file() else None
    if mv is not None:
        entities.append(
            Entity(
                "isai://root#MasterVector#north_star",
                "vector_element",
                mv.north_star_statement,
                {"version": mv.version},
            )
        )
        for i, obj in enumerate(mv.core_objectives):
            entities.append(Entity(f"isai://root#MasterVector#objective[{i}]", "vector_element", obj))
        for i, anti in enumerate(mv.anti_goals):
            entities.append(Entity(f"isai://root#MasterVector#anti_goal[{i}]", "vector_element", anti))
        for i, pillar in enumerate(mv.architectural_pillars):
            text = " ".join(
                str(getattr(pillar, f, ""))
                for f in ("pillar_id", "name", "title", "description", "invariants", "mechanisms")
                if getattr(pillar, f, None)
            )
            entities.append(Entity(f"isai://root#MasterVector#pillar[{i}]", "vector_element", text))
        for i, h in enumerate(mv.evolution_horizons):
            text = " ".join(
                str(getattr(h, f, "")) for f in ("horizon_id", "name", "description") if getattr(h, f, None)
            )
            entities.append(Entity(f"isai://root#MasterVector#horizon[{i}]", "vector_element", text))

    # --- 5. Документы: смысловые единицы для задач чистоты контекста -------------
    for md in sorted(root.rglob("*.md")):
        if _skipped(md.relative_to(root)):
            continue
        rel = md.relative_to(root).as_posix()
        entities.append(Entity(f"isai://{rel}", "document", _read(md), {"path": rel}))

    return entities


def _symbol_meaning(root: Path, target: str) -> str:
    """
    Смысл физической привязки `file.py:Symbol` — транзитивная связь, которой нет у дискретной
    логики: адрес -> реализация -> docstring. Без неё `ChronicleLedger` остаётся тремя
    слогами, и никакой эмбеддинг в него не попадёт.
    """
    if not target or ":" not in target:
        return ""
    file_part, _, symbol = target.partition(":")
    candidates = [root / ".isai" / file_part, *sorted(root.rglob(f".isai/{file_part}"))]
    for cand in candidates:
        if not cand.is_file():
            continue
        try:
            tree = ast.parse(_read(cand))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if getattr(node, "name", None) == symbol and isinstance(
                node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
            ):
                return f"{symbol} {ast.get_docstring(node) or ''} {ast.unparse(node)[:500]}"
    return ""


def universe_digest(entities: Sequence[Entity]) -> str:
    """Детерминизм индекса: проверяется, а не предполагается."""
    h = hashlib.sha256()
    for e in sorted(entities, key=lambda x: x.uri):
        h.update(e.uri.encode("utf-8"))
        h.update(b"\x00")
        h.update(e.text.encode("utf-8"))
        h.update(b"\x01")
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Двуязычный мост, выученный из корпуса (R-05)
# ---------------------------------------------------------------------------


def learn_bilingual_bridge(repo_root: Path, max_terms: int = 400) -> dict[str, list[str]]:
    """
    Выучить соответствия «латинский идентификатор <-> русские слова» из самого корпуса.

    Почему это работает. Система двуязычна по конструкции: идентификаторы — латиница,
    объяснения — русский, и они стоят **рядом** в одном предложении. Анти-цель №2 прямо
    требует «связи текста с кодом», и это единственное требование, которое одновременно
    является и ограничением, и подарком: корпус уже содержит перевод, разметенный вручную
    авторами документации.

    Мост строится без обучения и без внешних словарей: co-occurrence латинского токена и
    русской леммы в одной строке/предложении. Это дешёвая, детерминированная и полностью
    оффлайн-аппроксимация того, что делает мультиязычная нейросетевая модель.

    Ограничение известно и измеряется: мост наследует шум корпуса (в контекст попадают
    служебные слова вроде «каждой»), поэтому он расширяет запрос, а не заменяет его.
    """
    bridge: dict[str, Counter[str]] = {}
    for path in sorted(repo_root.rglob("*")):
        if not path.is_file() or path.suffix not in {".md", ".py", ".json"}:
            continue
        rel = path.relative_to(repo_root)
        if _skipped(rel):
            continue
        text = _read(path)
        if not text:
            continue
        for sentence in re.split(r"[.!?\n]", text):
            latin = set(re.findall(r"\b[A-Z][A-Za-z0-9]{2,}\b", sentence))
            if not latin:
                continue
            cyrillic = set(re.findall(r"\b[а-яё]{4,}\b", sentence.lower()))
            if not cyrillic:
                continue
            for term in latin:
                bridge.setdefault(term, Counter()).update(cyrillic)
    ordered = sorted(bridge.items(), key=lambda kv: (-sum(kv[1].values()), kv[0]))[:max_terms]
    return {term: [w for w, _ in counter.most_common(8)] for term, counter in ordered}


def expand_query_bilingual(
    query: str,
    bridge: dict[str, list[str]],
    *,
    weight: int = 2,
    ambiguity_limit: int = 3,
    min_word_len: int = 6,
    max_reverse_terms: int = 3,
) -> str:
    """
    Дополнить запрос русскими словами его латинских терминов (и наоборот).

    `HypergraphIndex` -> `HypergraphIndex индекс ссылок гиперграфа`. Вес — повторение
    мостового слова, чтобы оно конкурировало с исходным токеном, но не перебивало его.
    """
    expansions: list[str] = []
    lowered = query.lower()

    # Направление 1 (надёжное): латинский термин в запросе -> его русские спутники.
    # Корпус даёт это направление явно, потому что русский текст *объясняет* английский символ.
    for latin, russian in bridge.items():
        if latin.lower() in lowered:
            expansions.extend(russian[:5] * max(1, weight))

    # Направление 2 (шумное): русское слово -> латинский термин. Оно срабатывает на общих
    # словах («индекс», «система») и тянет мусор вроде `TASK`/`GPO`. Поэтому здесь берётся
    # только *редкий* русский спутник (встречается у <= 3 терминов) и не более трёх терминов.
    russian_terms: dict[str, list[str]] = {}
    for latin, russian in bridge.items():
        for r in russian:
            russian_terms.setdefault(r, []).append(latin)
    added = 0
    for russian, latins in russian_terms.items():
        if added >= max_reverse_terms:
            break
        if len(latins) > ambiguity_limit:  # общее слово: мост неоднозначен, пропускаем
            continue
        if len(russian) >= min_word_len and russian in lowered:
            expansions.extend(latins[:2] * max(1, weight))
            added += 1

    return query + " " + " ".join(expansions) if expansions else query


def expand_query_if_weak(
    query: str,
    bridge: dict[str, list[str]],
    embedder: "CorpusEmbedder",
    vectors: Sequence[Sequence[float]],
    *,
    confidence: float = 0.30,
    **kwargs,
) -> tuple[str, bool]:
    """
    Расширять запрос **только если прямой поиск неуверен** (R-09).

    Измерено: мост поднимает попадание в top-5 на alias-запросах с 1/13 до 6/13, но роняет
    exact-попадания с 3/10 до 1/10 — расширение разбавляет уже хороший запрос. Гейт по
    уверенности сохраняет оба эффекта: сильный запрос идёт как есть, слабый — через мост.

    Возвращает (запрос, был_ли_расширен).
    """
    best = max((cosine(embedder.embed(query), v) for v in vectors), default=0.0)
    if best >= confidence:
        return query, False
    return expand_query_bilingual(query, bridge, **kwargs), True
