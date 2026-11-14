"""
Bio-universe lexicon as an executable gate (`isai bio validate`).

`BIO-LEXICON.md` was a document: it listed which bio terms are real and which are borrowed, and
nothing checked it. A document cannot fail, so it cannot stop a term from entering prose before the
symbol exists — which is exactly how `материализация плазмиды` and `барьер дематериализации`
became writeable in the first place. This module turns the table into a verdict.

Two directions are checked, and the second is the one that matters:

* **Declared term without a live symbol** — the entry is a promise dressed as a mechanism.
  A term must either resolve to a declared symbol or be marked `FORBIDDEN` with a reason.
* **Symbol in `research/` claiming to be a system entity** — a mechanism that lives only on the
  bench is `MEASURED`, never `IMPLEMENTED`. This is what keeps "we proved it in the lab" from
  being read as "the system does it".

The lexicon is deliberately *not* derived from the code. Deriving it would make every symbol real
by construction and the check would always pass — a gate that cannot fail is decoration, which is
the defect this whole module exists to remove.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

#: How far a bio term has actually got.
#:   IMPLEMENTED — a symbol exists under `.isai/` and runs in the system.
#:   MEASURED    — a symbol exists only on the bench (`research/lab/`); numbers, not integration.
#:   FORBIDDEN   — no symbol, and prose use of the term is a defect.
Maturity = Literal["IMPLEMENTED", "MEASURED", "FORBIDDEN"]


class LexiconEntry(BaseModel):
    """One bio term and the executable symbol that makes it real, if any."""

    model_config = ConfigDict(frozen=True)

    term: str = Field(min_length=1)
    english: str = Field(min_length=1)
    symbol: str = ""
    symbol_file: str = ""
    maturity: Maturity
    #: Why the term is in this state. Required for FORBIDDEN: "no symbol yet" is not a reason,
    #: it is the absence of one, and a forbidden term must say what would un-forbid it.
    rationale: str = Field(min_length=1)

    @model_validator(mode="after")
    def _maturity_matches_symbol(self) -> LexiconEntry:
        if self.maturity == "FORBIDDEN" and self.symbol:
            raise ValueError(f"{self.term}: FORBIDDEN entries cannot name a symbol")
        if self.maturity in ("IMPLEMENTED", "MEASURED") and not (self.symbol and self.symbol_file):
            raise ValueError(f"{self.term}: {self.maturity} requires both symbol and symbol_file")
        return self


class BioLexiconSpec(BaseModel):
    """The whole lexicon: the machine-readable source of truth for bio naming."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "0.1.0"
    lexicon_ref: str = "isai://research#BioLexicon"
    entries: tuple[LexiconEntry, ...] = ()

    @model_validator(mode="after")
    def _unique_terms(self) -> BioLexiconSpec:
        terms = [e.term for e in self.entries]
        if len(terms) != len(set(terms)):
            dupes = sorted({t for t in terms if terms.count(t) > 1})
            raise ValueError(f"duplicate lexicon terms: {dupes}")
        return self


@dataclass(frozen=True)
class BioFinding:
    """One verified statement about the lexicon."""

    check: str
    severity: str
    passed: bool
    term: str
    message: str


def _resolve_symbol(repo_root: Path, file_rel: str, symbol: str) -> tuple[bool, str]:
    """
    Resolve `symbol` in `file_rel`: a class/function/constant declaration, or `Class.member`.

    Exact and case-sensitive. `link_mutator` must not satisfy `LinkMutator`, and a docstring mention
    must not satisfy anything — the failure that once let `QuantumLinkDaemon` pass a maturity check.
    """
    import ast

    path = repo_root / file_rel
    if not path.is_file():
        return False, f"file not found: {file_rel}"
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        return False, f"cannot parse {file_rel}: {exc}"

    head, _, member = symbol.partition(".")
    declared: set[str] = set()
    members: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            declared.add(node.name)
            if isinstance(node, ast.ClassDef):
                inner = {
                    m.name
                    for m in node.body
                    if isinstance(m, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                }
                inner |= {
                    t.id
                    for m in node.body
                    if isinstance(m, ast.AnnAssign) and isinstance(m.target, ast.Name)
                    for t in (m.target,)
                }
                members[node.name] = inner
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    declared.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            declared.add(node.target.id)

    if head not in declared:
        return False, f"'{head}' is not declared in {file_rel}"
    if member:
        if member not in members.get(head, set()):
            return False, f"'{symbol}' — '{head}' declares no member '{member}' in {file_rel}"
    return True, ""


def validate_lexicon(repo_root: Path, lexicon: BioLexiconSpec) -> tuple[BioFinding, ...]:
    """
    Verify every entry against the repository and report both directions of the claim.

    Severities are CRITICAL for a term that cannot resolve, WARNING for a bench-only maturity that
    is honestly labelled. A FORBIDDEN term is never a finding by itself: forbidding a term with a
    written reason is the honest state, and punishing it would push the author to delete the entries
    that make the problem visible.
    """
    findings: list[BioFinding] = []

    for entry in lexicon.entries:
        if entry.maturity == "FORBIDDEN":
            findings.append(
                BioFinding(
                    "BIO-01",
                    "INFO",
                    True,
                    entry.term,
                    f"forbidden until implemented: {entry.rationale}",
                )
            )
            continue

        ok, reason = _resolve_symbol(repo_root, entry.symbol_file, entry.symbol)
        findings.append(
            BioFinding(
                "BIO-02",
                "CRITICAL",
                ok,
                entry.term,
                f"resolves to {entry.symbol} in {entry.symbol_file}"
                if ok
                else f"declared {entry.maturity} but does not resolve: {reason}",
            )
        )

        # A term is only IMPLEMENTED if its symbol lives in the kernel. Bench symbols are real code
        # and real measurements, but they are not the system, and conflating the two is how
        # "measured in the lab" becomes "implemented" without anyone deciding it.
        if entry.maturity == "IMPLEMENTED":
            in_kernel = entry.symbol_file.startswith(".isai/") or "/.isai/" in entry.symbol_file
            findings.append(
                BioFinding(
                    "BIO-03",
                    "CRITICAL",
                    in_kernel,
                    entry.term,
                    f"kernel symbol in {entry.symbol_file}"
                    if in_kernel
                    else (
                        f"claims IMPLEMENTED but {entry.symbol_file} is outside the kernel; "
                        f"bench-only mechanisms are MEASURED"
                    ),
                )
            )

    return tuple(findings)


def render_lexicon_markdown(lexicon: BioLexiconSpec) -> str:
    """Project the lexicon into the human table, so the document cannot drift from the spec."""
    lines = [
        "# Био-лексикон ISAI: имя → символ (BIO-LEXICON)",
        "",
        "> Этот файл — проекция `research/.isai/bio_lexicon.py`. Править руками нельзя:",
        "> `isai bio validate` сверяет каждый термин с живым символом и падает, если символ",
        "> исчез. Источник истины — спецификация, а не таблица.",
        "",
        "## Термины",
        "",
        "| Термин | English | Символ | Файл | Зрелость |",
        "|---|---|---|---|---|",
    ]
    for e in lexicon.entries:
        symbol = f"`{e.symbol}`" if e.symbol else "—"
        file_rel = f"`{e.symbol_file}`" if e.symbol_file else "—"
        lines.append(f"| **{e.term}** | {e.english} | {symbol} | {file_rel} | {e.maturity} |")
    lines.extend(["", "## Обоснования", ""])
    for e in lexicon.entries:
        lines.append(f"- **{e.term}** ({e.maturity}): {e.rationale}")
    lines.append("")
    return "\n".join(lines)


#: The live lexicon. Every entry states how far the term actually got, and the gate verifies it
#: against the code rather than trusting this table.
BIO_LEXICON = BioLexiconSpec(
    entries=(
        LexiconEntry(
            term="Ген",
            english="Gene",
            symbol="Gene",
            symbol_file="research/lab/e6_mini.py",
            maturity="MEASURED",
            rationale="Единица наследственности: тело и теги. Работает на стенде (E6), в ядре символа нет.",
        ),
        LexiconEntry(
            term="Вселенная",
            english="Universe",
            symbol="Universe",
            symbol_file="research/lab/e6_mini.py",
            maturity="MEASURED",
            rationale="Множество генов с историей. Стенд держит 12 синтетических; живые 298 сущностей не загружались.",
        ),
        LexiconEntry(
            term="Рибосома",
            english="Ribosome",
            symbol="translate",
            symbol_file="research/lab/e6_mini.py",
            maturity="MEASURED",
            rationale="Исполнение по контракту с песочницей. В ядре роль играет load_module_attr_isolated, но это отдельный символ с другим поведением (нет эпохи).",
        ),
        LexiconEntry(
            term="Апоптоз",
            english="Apoptosis",
            symbol="apoptosis",
            symbol_file="research/lab/e6_mini.py",
            maturity="MEASURED",
            rationale="Смерть с различением «сломан / нужен вход». E11: FALSE_KILL 0, контекст 1502->556 Б.",
        ),
        LexiconEntry(
            term="Плазмида",
            english="Plasmid",
            symbol="Plasmid",
            symbol_file="research/lab/e7_plasmid.py",
            maturity="MEASURED",
            rationale="Мемоизированная группа генов. E7: раздутие DAG 7x..1023x снимается в константу.",
        ),
        LexiconEntry(
            term="Холон",
            english="Holon",
            symbol="Holon",
            symbol_file="research/lab/e7_plasmid.py",
            maturity="MEASURED",
            rationale="Держатель URI-кодонов к плазмидам. Имя заимствовано у Кёстлера, значение иное: это указатель, а не уровень иерархии.",
        ),
        LexiconEntry(
            term="Эпоха",
            english="Epoch",
            symbol="EpochUniverse.epoch",
            symbol_file="research/lab/e7_plasmid.py",
            maturity="MEASURED",
            rationale="Версия вселенной для инвалидации кэша. E12: глобальная эпоха даёт hit 0.11 против 0.88 у версии на плазмиду.",
        ),
        LexiconEntry(
            term="Хромосома",
            english="Chromosome",
            symbol="",
            symbol_file="",
            maturity="FORBIDDEN",
            rationale="Нет символа. Упаковка генов для I/O не реализована; упоминание в прозе — дефект до появления символа.",
        ),
        LexiconEntry(
            term="Атом",
            english="Atom",
            symbol="",
            symbol_file="",
            maturity="FORBIDDEN",
            rationale="Нет символа. Неизменяемость в ISAI выражается frozen=True у Pydantic, а не отдельной сущностью.",
        ),
        LexiconEntry(
            term="Крио-архив",
            english="CryoArchive",
            symbol="",
            symbol_file="",
            maturity="FORBIDDEN",
            rationale="Нет символа. Откат есть у isai recover, но он не по генам и не криогенный; заявлять архив нельзя.",
        ),
        LexiconEntry(
            term="AST-гомология",
            english="AstHomology",
            symbol="",
            symbol_file="",
            maturity="FORBIDDEN",
            rationale="Нет символа. Утверждение о -59.2% раздутия пула не воспроизводимо: сначала символ, потом число.",
        ),
    )
)
