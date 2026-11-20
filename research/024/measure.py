#!/usr/bin/env python3
"""Независимое измерение на восстановленном корпусе (И-024).

Ничего из продукта не импортируется: свои нормализация, основы, меры сходства и закрытый лексикон.
Задача — воспроизвести вывод И-020 (порога по проценту похожести не существует; допустимое
отклонение задаётся составом слов) и назвать цену строгого правила. JSON в stdout.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import pathlib
import re
import sys
import unicodedata

HERE = pathlib.Path(__file__).absolute().parent
CORPUS = HERE / 'corpus.py' if (HERE / 'corpus.py').exists() else HERE.parent / '020' / 'corpus.py'
sys.path.insert(0, str(CORPUS.parent))
import corpus  # noqa: E402

PUNCT = re.compile(r'[^\w\s]+', re.UNICODE)
SPACE = re.compile(r'\s+')
WORD = re.compile(r'\w+', re.UNICODE)
IDENT = re.compile(r'[A-Za-z_][A-Za-z0-9_.]*\d*')
NUMBER = re.compile(r'\d+')
CRITICAL = ('case', 'level', 'status', 'expected', 'environment')
PROSE = ('actual', 'evidence', 'limits', 'conditions')
GUARDS = ('не ', 'нет ', 'без ', 'только ', 'исключительно ', 'по памяти', 'со слов', 'не открывался',
          'не проверял', 'предполож', 'возможно', 'вероятно', 'кажется', 'похоже')
STOP = frozenset('и в во на с со по при для от до из или это тот же как что the a of to in and'.split())
SUFFIX = ('ами', 'ями', 'ов', 'ев', 'ий', 'ый', 'ая', 'ое', 'ые', 'ой', 'ем', 'ом', 'ах', 'ях',
          'ет', 'ут', 'ют', 'ит', 'ат', 'ят', 'ся', 'сь', 'а', 'я', 'о', 'е', 'и', 'ы', 'у', 'ю')


def norm(text):
    text = unicodedata.normalize('NFKC', str(text)).lower().replace('ё', 'е')
    return SPACE.sub(' ', PUNCT.sub(' ', text)).strip()


def grams(text, n=3):
    body = ' ' + norm(text) + ' '
    return {body[i:i + n] for i in range(max(0, len(body) - n + 1))} or {body}


def dice(a, b):
    ga, gb = grams(a), grams(b)
    return 2 * len(ga & gb) / (len(ga) + len(gb)) if ga or gb else 1.0


def containment(a, b):
    ga, gb = grams(a), grams(b)
    if not ga or not gb:
        return 1.0 if ga == gb else 0.0
    return len(ga & gb) / min(len(ga), len(gb))


def jaccard(a, b):
    ta, tb = {w for w in WORD.findall(norm(a))}, {w for w in WORD.findall(norm(b))}
    return len(ta & tb) / len(ta | tb) if ta or tb else 1.0


def ratio(a, b):
    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()


def guard_bits(o):
    text = ' ' + norm(' '.join(str(o.get(k, '')) for k in PROSE + ('expected',))) + ' '
    return {p for p in GUARDS if p in text}


def fact_bits(o):
    text = ' '.join(str(o.get(k, '')) for k in PROSE) + ' ' + str(o.get('expected', '')) + ' ' + str(o.get('case', ''))
    return {m.lower() for m in IDENT.findall(text)} | set(NUMBER.findall(text))


def critical_equal(a, b):
    for key in CRITICAL:
        if key == 'environment':
            if dict(a.get(key) or {}) != dict(b.get(key) or {}):
                return False
        elif a.get(key) != b.get(key):
            return False
    return True


def stem(word):
    for suffix in SUFFIX:
        if len(word) - len(suffix) >= 4 and word.endswith(suffix):
            return word[:-len(suffix)]
    return word


def content(text):
    return {stem(w) for w in WORD.findall(norm(text)) if w not in STOP and len(w) > 1}


def word_deviation(a, b):
    left, right = content(a) - content(b), content(b) - content(a)
    if not left and not right:
        return 0, 1.0
    if not left or not right:
        return max(len(left), len(right)), 0.0
    worst = 1.0
    for x in sorted(left):
        worst = min(worst, max(difflib.SequenceMatcher(None, x, y).ratio() for y in sorted(right)))
    return max(len(left), len(right)), worst


def guarded(a, b):
    if not critical_equal(a, b):
        return False, 'critical'
    if guard_bits(a) != guard_bits(b):
        return False, 'lexicon'
    if fact_bits(a) != fact_bits(b):
        return False, 'facts'
    return True, 'prose'


def text_band(measure):
    pos, neg, blocked = [], [], {'critical': 0, 'lexicon': 0, 'facts': 0}
    for label, name, left, right in ROWS:
        ok, reason = guarded(left, right)
        if not ok:
            blocked[reason] += 1
            continue
        value = min(measure(left[k], right[k]) for k in PROSE)
        (pos if label else neg).append((round(value, 4), name))
    pos.sort()
    neg.sort(reverse=True)
    band = round(pos[0][0] - neg[0][0], 4) if pos and neg and pos[0][0] > neg[0][0] else None
    return dict(blocked=blocked, repeats=len(pos), different=len(neg),
                lowest_repeat=pos[0] if pos else None, highest_different=neg[0] if neg else None, band=band)


def added_words(a, b, chars_min=0.85):
    """Сколько слов добавлено в одной стороне, если пары с посимвольным сходством ≥ chars_min считать заменой."""
    left, right = content(a) - content(b), content(b) - content(a)
    if not left and not right:
        return 0
    pairs = []
    for x in sorted(left):
        best = max(((difflib.SequenceMatcher(None, x, y).ratio(), y) for y in sorted(right)), default=(0.0, None))
        pairs.append((best[0], x, best[1]))
    used, matched = set(), 0
    for score, _, partner in sorted(pairs, reverse=True):
        if partner is not None and score >= chars_min and partner not in used:
            used.add(partner)
            matched += 1
    return max(0, max(len(left), len(right)) - matched)


def added_rule(added_max, chars_min=0.85):
    """Правило «разрешить до added_max добавленных слов на поле»; 0 — то, что выпущено в 0.1.4."""
    found = wrong = 0
    for label, name, left, right in ROWS:
        ok, _ = guarded(left, right)
        if not ok:
            continue
        merge = all(added_words(left[k], right[k], chars_min) <= added_max for k in PROSE)
        if merge:
            found += label is True
            wrong += label is False
    return dict(added_max=added_max, chars_min=chars_min, repeats_found=found, false_merges=wrong)


ROWS = corpus.pairs()
report = dict(
    corpus=dict(pairs=len(ROWS), repeats=sum(1 for r in ROWS if r[0]), different=sum(1 for r in ROWS if not r[0]),
                cases=len(corpus.BASE), restored_in='И-024 после утраты И-020',
                sha256=hashlib.sha256(CORPUS.read_bytes()).hexdigest()),
    guards={name: sum(1 for r in ROWS if guarded(r[2], r[3])[1] == name) for name in ('critical', 'lexicon', 'facts')},
    text_bands={name: text_band(fn) for name, fn in
                (('dice', dice), ('containment', containment), ('tokens_jaccard', jaccard), ('ratio', ratio))},
    token_grid=[added_rule(k) for k in (0, 1, 2, 3)],
    conclusion=dict(
        threshold_by_similarity=False,
        zero_added_words=added_rule(0),
        two_added_words=added_rule(2),
        admissible='0 добавленных содержательных слов; одна замена на поле при посимвольном совпадении не ниже 0.85',
    ),
)
report['all_bands_absent'] = all(b['band'] is None for b in report['text_bands'].values())
sys.stdout.write(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + '\n')
