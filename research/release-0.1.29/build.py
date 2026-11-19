#!/usr/bin/env python3
"""Выпуск AgentContractKit 0.1.29: права — кто читает и кто пишет (И-049, §11).

Итерация И-042. Линия выводится от 0.1.0 теми же правками, что дали 0.1.4–0.1.21. §9 закрыт целиком;
теперь §10.1 — кто вправе менять правило. У записи появляется необязательный владелец (owner), правка
идёт от его имени (actor), иначе отказ not_owner, а передача владения требует отдельного согласия
allow_owner. Правило без владельца остаётся общим и правится любым; данные 0.1.21 без owner читаются.

Запуск: python3 build.py [--line base|edition]
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import patch_016 as p16  # noqa: E402
import patch_017 as p17  # noqa: E402
import patch_018 as p18  # noqa: E402
import patch_019 as p19  # noqa: E402
import patch_020 as p20  # noqa: E402
import patch_021 as p21  # noqa: E402
import patch_022 as p22  # noqa: E402
import patch_023 as p23  # noqa: E402
import patch_024 as p24  # noqa: E402
import patch_025 as p25  # noqa: E402
import patch_026 as p26  # noqa: E402
import patch_027 as p27  # noqa: E402
import patch_028 as p28  # noqa: E402
import patch_029 as p29  # noqa: E402
import patch_030 as p30  # noqa: E402
import patch_031 as p31  # noqa: E402
import patch_032 as p32  # noqa: E402
import patch_033 as p33  # noqa: E402
import patch_034 as p34  # noqa: E402
import patch_035 as p35  # noqa: E402
import patch_036 as p36  # noqa: E402
import patch_037 as p37  # noqa: E402
import patch_038 as p38  # noqa: E402
import patch_039 as p39  # noqa: E402
REPO = ROOT.parents[1]
DIST = REPO / 'dist'
SOURCE = DIST / 'AgentContractKit-0.1.0.zip'
VERSION = '0.1.29'
PREV_RELEASE = '0.1.28'


def newer(limit: str) -> bool:
    """Сравнение версий по числам: строкой 0.1.10 оказалось бы меньше 0.1.9."""
    return tuple(map(int, VERSION.split('.'))) > tuple(map(int, limit.split('.')))
PREV = '0.1.0'
LINES = {
    'base': ('AgentContractKit', 'local:AgentContractKit', ''),
    'edition': ('AgentContractKitISAIEdition', 'local:AgentContractKitISAIEdition', '+docs.1'),
}


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def enc(o) -> bytes:
    return (json.dumps(o, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode()


TOOL_OLD = """    elif op == 'record_check':
        exact(r, 'op observation')
        observation(r['observation'])
        checks['checks'].append({'at': p.at, 'revision': s['revision'], 'base_version': s['base']['version'],
                                 'adapter_version': (s['adapter'] or {}).get('version'), 'observation': r['observation']})
        p.change(CHECKS, encode(checks))"""

TOOL_NEW = """    elif op == 'record_check':
        exact(r, 'op observation')
        observation(r['observation'])
        match = next((n for n, c in enumerate(checks['checks'], 1)
                      if same_observation(c['observation'], r['observation'])), None)
        if match is not None:
            # Повтор не создаёт записи: одно и то же наблюдение можно записать другой формой слов.
            # Допуск ограничен измерением (см. PROTOCOL.md); всё, что дальше, — новая запись.
            p.notes.append(f'Наблюдение совпадает с уже записанным (запись {match}); новая запись не создаётся.')
        else:
            checks['checks'].append({'at': p.at, 'revision': s['revision'], 'base_version': s['base']['version'],
                                     'adapter_version': (s['adapter'] or {}).get('version'), 'observation': r['observation']})
            p.change(CHECKS, encode(checks))"""

HELPERS = '''# --- 0.1.4: смысловая тождественность наблюдений -----------------------------------
# Допуск измерен на замороженном корпусе (исследование И-020, 112 пар): критические поля и факты
# совпадают точно, смысловые фразы совпадают как набор признаков, а свободный текст может отличаться
# не более чем одним содержательным словом на поле и только если это слово совпадает посимвольно
# не менее чем на 85 %. Добавленное слово — уже другое наблюдение, даже если это «прогон повторён».
_TEXT_FIELDS = ('actual', 'evidence', 'limits', 'conditions')
_CRITICAL = ('case', 'level', 'status', 'expected', 'environment')
_GUARDS = ('не ', 'нет ', 'без ', 'только ', 'исключительно ', 'по памяти', 'со слов', 'не открывался',
           'не проверял', 'предполож', 'возможно', 'вероятно', 'кажется', 'похоже')
_PUNCT = re.compile(r'[^\\w\\s]+', re.UNICODE)
_SPACE = re.compile(r'\\s+')
_WORD = re.compile(r'\\w+', re.UNICODE)
_IDENT = re.compile(r'[A-Za-z_][A-Za-z0-9_.]*\\d*')
_NUMBER = re.compile(r'\\d+')
_STOP = frozenset('и в во на с со по при для от до из или это тот же как что the a of to in and'.split())
_SUFFIX = ('ами', 'ями', 'ов', 'ев', 'ий', 'ый', 'ая', 'ое', 'ые', 'ой', 'ем', 'ом', 'ах', 'ях',
           'ет', 'ут', 'ют', 'ит', 'ат', 'ят', 'ся', 'сь', 'а', 'я', 'о', 'е', 'и', 'ы', 'у', 'ю')


def plain(text):
    """Нижний регистр, ё→е, без пунктуации, одиночные пробелы."""
    text = unicodedata.normalize('NFKC', str(text)).lower().replace('ё', 'е')
    return _SPACE.sub(' ', _PUNCT.sub(' ', text)).strip()


def guard_bits(o):
    """Закрытый лексикон смысла: наличие каждой фразы — признак, сравнение по набору."""
    text = ' ' + plain(' '.join(str(o[k]) for k in _TEXT_FIELDS + ('expected',))) + ' '
    return frozenset(p for p in _GUARDS if p in text)


def fact_bits(o):
    """Идентификаторы и целые числа: изменённый факт запрещает склейку."""
    text = ' '.join([str(o[k]) for k in _TEXT_FIELDS] + [str(o['expected']), str(o['case'])])
    return frozenset(m.lower() for m in _IDENT.findall(text)) | frozenset(_NUMBER.findall(text))


def stem(word):
    for suffix in _SUFFIX:
        if len(word) - len(suffix) >= 4 and word.endswith(suffix):
            return word[:-len(suffix)]
    return word


def content(text):
    """Содержательные слова без служебных, усечённые до основы."""
    return frozenset(stem(w) for w in _WORD.findall(plain(text)) if w not in _STOP and len(w) > 1)


def word_deviation(a, b):
    """(сколько содержательных слов различается, худшее посимвольное сходство различающихся пар)."""
    left, right = content(a) - content(b), content(b) - content(a)
    if not left and not right:
        return 0, 1.0
    if not left or not right:
        return max(len(left), len(right)), 0.0
    worst = 1.0
    for x in sorted(left):
        worst = min(worst, max(difflib.SequenceMatcher(None, x, y).ratio() for y in sorted(right)))
    return max(len(left), len(right)), worst


def same_observation(a, b):
    """Одно и то же наблюдение: критическое равенство, факты, смысловые фразы, допуск на слово."""
    if a == b:
        return True
    for key in _CRITICAL:
        if key == 'environment':
            if dict(a[key]) != dict(b[key]):
                return False
        elif a[key] != b[key]:
            return False
    if guard_bits(a) != guard_bits(b) or fact_bits(a) != fact_bits(b):
        return False
    for key in _TEXT_FIELDS:
        words, worst = word_deviation(a[key], b[key])
        if words > 1 or worst < 0.85:
            return False
    return True


'''

TEST_NEW = """
    @case('X17', 'Точный повтор наблюдения не создаёт записи; изменение любого поля создаёт новую.',
          'Правило 0.1.3: совпадение девяти полей целиком.')
    def test_40_exact_repeat(self):
        self.install();env={k:'synthetic' for k in c.ENV_KEYS.split()}
        o=dict(case='synthetic-exact',level=1,conditions='Linux fixture',expected='exists',actual='exists',status='pass',
               evidence='file fingerprint '+c.digest(b'synthetic input\\n'),limits='presence only',environment=env)
        self.apply(dict(op='record_check',observation=dict(o)));before=(self.a/c.CHECKS).read_bytes()
        self.assertEqual(self.apply(dict(op='record_check',observation=dict(o)))['outcome'],'no_change')
        self.assertEqual(before,(self.a/c.CHECKS).read_bytes());self.assertEqual(len(self.call('status')['observations']),1)
        self.apply(dict(op='record_check',observation=dict(o,limits='presence only, second run')))
        self.assertEqual(len(self.call('status')['observations']),2)

    @case('X18', 'Пересказ того же наблюдения не создаёт записи: регистр, пунктуация, словоформа, порядок слов.',
          'Допуск измерен на корпусе И-020 (112 пар); проверяется правило, не поведение модели.')
    def test_41_semantic_repeat(self):
        self.install();env={k:'synthetic' for k in c.ENV_KEYS.split()}
        base=dict(case='synthetic-semantic',level=1,conditions='Условия синтетические, прогон один',expected='exists',
                  actual='Файл есть, строка 17',status='pass',evidence='file fingerprint '+c.digest(b'synthetic input\\n'),
                  limits='только наличие',environment=env)
        self.apply(dict(op='record_check',observation=dict(base)));before=(self.a/c.CHECKS).read_bytes()
        forms=[dict(base,actual='файл есть строка 17'),
               dict(base,actual='Файл есть, строки 17'),
               dict(base,conditions='Условия синтетичесие, прогон один'),
               dict(base,conditions='прогон один, условия синтетические')]
        for form in forms:
            self.assertEqual(self.apply(dict(op='record_check',observation=form))['outcome'],'no_change')
            self.assertEqual(before,(self.a/c.CHECKS).read_bytes())
        self.assertEqual(len(self.call('status')['observations']),1)
        self.evidence['reworded_forms']=len(forms)

    @case('X19', 'Добавленное или снятое слово, другой факт или другая смысловая фраза создают новую запись.',
          'Проверяется запрет склейки; близость текста сама по себе не склеивает.')
    def test_42_semantic_boundary(self):
        self.install();env={k:'synthetic' for k in c.ENV_KEYS.split()}
        base=dict(case='synthetic-boundary',level=1,conditions='Условия синтетические, прогон один',expected='exists',
                  actual='Файл есть, строка 17',status='pass',evidence='file fingerprint '+c.digest(b'synthetic input\\n'),
                  limits='только наличие',environment=env)
        self.apply(dict(op='record_check',observation=dict(base)))
        others=[dict(base,actual='Файл есть, строка 17; прогон повторён, результат тот же'),
                dict(base,limits='только наличие. Ограничение снято.'),
                dict(base,evidence='file fingerprint '+c.digest(b'synthetic input\\n')+' (по памяти, файл не открывался)'),
                dict(base,conditions='Условия синтетические, прогон один. Только при повторном прогоне.'),
                dict(base,actual='Файл есть, строка 18'),
                dict(base,expected='absent'),
                dict(base,environment=dict(env,os='other'))]
        for i,other in enumerate(others,1):
            self.assertEqual(self.apply(dict(op='record_check',observation=other))['outcome'],'committed')
            self.assertEqual(len(self.call('status')['observations']),i+1)
"""

# 0.1.0 жёстко знал свой номер в регрессиях; при восстановлении линии номер берётся из манифеста.
TESTS_VERSION_PATCHES = [
    ("        for root in (self.kbase, self.lab/'releases/0.1.0'):",
     "        for root in (self.kbase, self.lab/PACKAGE):"),
    ("        self.install_req = dict(op='install', package='releases/0.1.0', pin=PIN)",
     "        self.install_req = dict(op='install', package=PACKAGE, pin=PIN)"),
    ("    def publish(self, version='0.1.1'):", "    def publish(self, version=NEXT_VERSION):"),
    ("        self.assertFalse((self.lab/'releases/0.1.1').exists())",
     "        self.assertFalse((self.lab/(NEXT_VERSION and 'releases/'+NEXT_VERSION)).exists())"),
    ("        (self.lab/'releases/0.1.0/unlisted-synthetic.txt').write_text(marker)",
     "        (self.lab/PACKAGE/'unlisted-synthetic.txt').write_text(marker)"),
    ("req=self.publish('0.1.2')", "req=self.publish(LATER_VERSION)"),
    ("        self.install();r=self.publish();(self.lab/'releases/0.1.0/START.md').write_bytes(b'missing original content')",
     "        self.install();r=self.publish();(self.lab/PACKAGE/'START.md').write_bytes(b'missing original content')"),
    ("self.evidence['version_before_rejected_update']='0.1.1'",
     "self.evidence['version_before_rejected_update']=NEXT_VERSION"),
    ("self.assertEqual(view['installed_version'],'0.1.0')",
     "self.assertEqual(view['installed_version'],BASE_VERSION)"),
    ("PIN = c.digest((KIT/'base/manifest.json').read_bytes())",
     "PIN = c.digest((KIT/'base/manifest.json').read_bytes())\nBASE_VERSION = c.parse((KIT/'base/manifest.json').read_bytes())['base_version']\n"
     "_M, _m, _p = map(int, BASE_VERSION.split('.'))\nNEXT_VERSION = f'{_M}.{_m}.{_p+1}'\nLATER_VERSION = f'{_M}.{_m}.{_p+2}'\n"
     "PACKAGE = 'releases/' + BASE_VERSION"),
]

# --- 0.1.5: тождество записи отделено от происхождения (находка И-023) -------------------------
PATCH_015 = [
    ("_NUMBER = re.compile(r'\\d+')\n",
     "_NUMBER = re.compile(r'\\d+')\n"
     "_FILE = re.compile(r'^\\s*\\S+\\.(?:log|txt|json|md|csv|xml|ya?ml)\\b[,;]?\\s*', re.IGNORECASE)\n"
     "_LINE = re.compile(r',?\\s*строк[аиуе]?\\s*\\d+', re.IGNORECASE)\n"
     "_TIME = re.compile(r'\\b\\d+(?:[.,]\\d+)?\\s*(?:ms|s|sec|secs|min|mins|мс|сек|мин|с)\\b'\n"
     "                   r'|\\(\\d+:\\d{2}:\\d{2}\\)|\\b\\d{1,2}:\\d{2}:\\d{2}\\b', re.IGNORECASE)\n"),
    ("def guard_bits(o):\n    \"\"\"Закрытый лексикон смысла",
     "def body(o, key):\n"
     "    \"\"\"Содержание поля: из улики убирается место, из всех полей — изменчивое время.\n\n"
     "    Место (журнал и номер строки) — происхождение записи, а не её содержание: два прогона\n"
     "    одного события не могут иметь одно место. Длительности и отметки времени — не факт события.\n"
     "    Всё остальное в улике (например, отпечаток файла) остаётся содержанием и защищено.\n"
     "    \"\"\"\n"
     "    text = str(o[key])\n"
     "    if key == 'evidence':\n"
     "        text = _LINE.sub('', _FILE.sub('', text))\n"
     "    return _TIME.sub(' ', text).strip()\n\n\n"
     "def guard_bits(o):\n    \"\"\"Закрытый лексикон смысла"),
    ("    text = ' ' + plain(' '.join(str(o[k]) for k in _TEXT_FIELDS + ('expected',))) + ' '",
     "    text = ' ' + plain(' '.join(body(o, k) for k in _TEXT_FIELDS + ('expected',))) + ' '"),
    ("    text = ' '.join([str(o[k]) for k in _TEXT_FIELDS] + [str(o['expected']), str(o['case'])])",
     "    text = ' '.join([body(o, k) for k in _TEXT_FIELDS] + [str(o['expected']), str(o['case'])])"),
    ("        words, worst = word_deviation(a[key], b[key])",
     "        words, worst = word_deviation(body(a, key), body(b, key))"),
]

TEST_015 = """
    @case('X20', 'Место наблюдения не создаёт новой записи; отпечаток в улике по-прежнему создаёт.',
          'Находка И-023: журнал и номер строки — происхождение, а не содержание.')
    def test_43_place_is_not_content(self):
        self.install();env={k:'synthetic' for k in c.ENV_KEYS.split()}
        base=dict(case='synthetic-place',level=1,conditions='Linux fixture',expected='exists',actual='Файл есть',
                  status='pass',evidence='tests.log, строка 17',limits='только наличие',environment=env)
        self.apply(dict(op='record_check',observation=dict(base)));before=(self.a/c.CHECKS).read_bytes()
        for place in ('other.log, строка 91','tests.log, строки 402','build.txt, строка 3'):
            self.assertEqual(self.apply(dict(op='record_check',observation=dict(base,evidence=place)))['outcome'],
                             'no_change')
            self.assertEqual(before,(self.a/c.CHECKS).read_bytes())
        self.assertEqual(self.apply(dict(op='record_check',observation=dict(
            base,evidence='file fingerprint '+c.digest(b'a')+', строка 17')))['outcome'],'committed')
        self.assertEqual(self.apply(dict(op='record_check',observation=dict(
            base,evidence='file fingerprint '+c.digest(b'b')+', строка 18')))['outcome'],'committed')

    @case('X21', 'Изменчивое время не создаёт новой записи; изменённый счётчик создаёт.',
          'Находка И-023: длительность прогона — не факт события, а число результатов — факт.')
    def test_44_volatile_time(self):
        self.install();env={k:'synthetic' for k in c.ENV_KEYS.split()}
        base=dict(case='synthetic-time',level=3,conditions='Linux fixture, прогон один',expected='Тесты проходят.',
                  actual='Итог прогона: 1 failed, 589 passed in 77.89s (0:01:17).',status='pass',
                  evidence='tests.log, строка 400',limits='только наличие',environment=env)
        self.apply(dict(op='record_check',observation=dict(base)));before=(self.a/c.CHECKS).read_bytes()
        self.assertEqual(self.apply(dict(op='record_check',observation=dict(
            base,actual='Итог прогона: 1 failed, 589 passed in 77.86s (0:01:18).',evidence='tests.log, строка 394'
        )))['outcome'],'no_change')
        self.assertEqual(before,(self.a/c.CHECKS).read_bytes())
        self.assertEqual(self.apply(dict(op='record_check',observation=dict(
            base,actual='Итог прогона: 1 failed, 590 passed in 77.86s (0:01:18).')))['outcome'],'committed')

    @case('X22', 'Смягчённое свидетельство по-прежнему создаёт запись, даже если место совпадает.',
          'Содержание улики защищено: правило 0.1.5 снимает только место.')
    def test_45_witness_still_guarded(self):
        self.install();env={k:'synthetic' for k in c.ENV_KEYS.split()}
        base=dict(case='synthetic-witness',level=2,conditions='Linux fixture',expected='exists',actual='Файл есть',
                  status='pass',evidence='file fingerprint '+c.digest(b'a')+', строка 17',limits='только наличие',
                  environment=env)
        self.apply(dict(op='record_check',observation=dict(base)))
        for other in (dict(base,evidence='file fingerprint '+c.digest(b'a')+' (по памяти, файл не открывался)'),
                      dict(base,limits='только наличие. Ограничение снято.'),
                      dict(base,conditions='Linux fixture, по памяти'),
                      dict(base,actual='Файл есть, строка 18')):
            self.assertEqual(self.apply(dict(op='record_check',observation=other))['outcome'],'committed')
"""

PROTOCOL_015 = """

По правилу 0.1.5 место наблюдения отделено от содержания. Поле `evidence` состоит из двух частей: место — имя журнала и номер строки (`tests.log, строка 17`) — и содержание, то есть всё остальное в этой строке (например, `file fingerprint <отпечаток>`). При сравнении место снимается: два прогона одного события не могут иметь одно место, поэтому запись места в решении не участвует, но в самой записи улика сохраняется как есть. Содержание улики сравнивается как прежде и защищено: изменённый отпечаток или ослабленное свидетельство (`по памяти`, `файл не открывался`) — другое наблюдение. Изменчивое время — длительности и отметки (`77.89s`, `(0:01:17)`, `0:00:03`) — не является фактом события: два прогона одного набора дают разные длительности и при этом остаются одним наблюдением, а изменённый счётчик результатов (589 против 590) — уже другое наблюдение. Допуск на свободный текст, критические поля, закрытый лексикон и запрет на добавленное содержательное слово не менялись.
"""

README_015 = """
## Что изменилось в 0.1.5

Правило тождества то же, но происхождение записи в нём больше не участвует. Повод измерен: в И-023 на настоящих журналах правило 0.1.4 дало 0 ложных склеек и 0 склеек настоящих повторов из 2 — потому что поле `evidence` вместе с именем журнала и номером строки входило в сравнение, а два прогона одного события не могут иметь одну улику. Здесь место снимается, а изменчивое время (длительность) перестаёт быть фактом; содержание улики (отпечаток, `по памяти`) защищено по-прежнему. Переход с `0.1.4` проверяется имитацией: данные предыдущего выпуска читаются и не переписываются.
"""

PROTOCOL_PARA = """

Повтор наблюдения в 0.1.4 не создаёт новой записи, и распознаётся он по смыслу, но допуск ограничен измерением. Сначала сравниваются критические поля — `case`, `level`, `status`, `expected`, `environment` — и они должны совпадать точно. Затем сравниваются факты: латинские идентификаторы (`TypeError`, `test_build`) и целые числа (номера строк, коды возврата, таймауты) — любое отличие запрещает склейку. Затем сравнивается закрытый список смысловых фраз: `не`, `нет`, `без`, `только`, `исключительно`, `по памяти`, `со слов`, `не открывался`, `не проверял`, `предполож`, `возможно`, `вероятно`, `кажется`, `похоже`. Наличие каждой фразы — признак, и наборы признаков двух наблюдений должны совпасть: снятое ограничение, ослабленное свидетельство и суженное условие — другие наблюдения, даже если остальной текст совпадает. Только после этого сравнивается свободный текст полей `actual`, `evidence`, `limits`, `conditions`: он может отличаться не более чем одним содержательным словом на поле, и это слово должно совпадать посимвольно не менее чем на 85 % (словоформа или опечатка). Добавленное содержательное слово — новое наблюдение, даже если это «прогон повторён, результат тот же»: на замороженном корпусе из 112 пар такое же добавление встречается и у повтора, и у другого события, поэтому порог по проценту похожести не используется. Регистр, пунктуация, лишние пробелы и порядок слов на склейку не влияют. Совпавшее наблюдение не создаёт записи: план пуст, `apply` возвращает `no_change`, `checks.json` остаётся байт в байт, а примечание плана указывает номер уже записанной записи. Счётчик повторов не ведётся: сколько раз наблюдение повторяли, комплект не помнит. Точное совпадение всех девяти полей — частный случай этого правила.
"""

RESTORED_NOTE = """
## Восстановленная линия

Выпуски `0.1.1`–`0.1.3` и их архивы утрачены: каталог `dist/` не попадает в снимки рабочего пространства и не хранится в git. Эта линия выведена заново от `0.1.0` и содержит оба правила: побайтный повтор (из 0.1.3) и смысловой повтор (из 0.1.4). Исторических снимков `releases/0.1.1`–`releases/0.1.3` в поставке нет, поэтому переход с этих версий невозможен; переход с `0.1.0` проверен сквозной имитацией. Номер `0.1.4` сохранён, потому что правило и его приёмка те же; байты архивов отличаются от утраченных.
"""


PASS_TOTAL = 89 if newer('0.1.28') else 87 if newer('0.1.27') else 85 if newer('0.1.26') else 83 if newer('0.1.25') else 81 if newer('0.1.24') else 79 if newer('0.1.23') else 77 if newer('0.1.22') else 75 if newer('0.1.21') else 73 if newer('0.1.20') else 71 if newer('0.1.19') else 69 if newer('0.1.18') else 67 if newer('0.1.17') else 65 if newer('0.1.16') else 63 if newer('0.1.15') else 61 if newer('0.1.14') else 59 if newer('0.1.13') else 57 if newer('0.1.12') else 55 if newer('0.1.11') else 52 if newer('0.1.10') else 50 if newer('0.1.9') else 47 if newer('0.1.7') else 46 if newer('0.1.6') else (42 if newer('0.1.5') else (38 if newer('0.1.4') else 35))


def readme_update(text: str, line: str) -> str:
    text = re.sub(r'^(# AgentContractKit\w* )• 0\.1\.0$', r'\1• 0.1.4', text, flags=re.M)
    text = text.replace('| `releases/0.1.0/` | Точные шесть файлов принятой базы. Это исходная точка будущего трёхстороннего обновления, не второй редактируемый реестр. |',
                        '| `releases/0.1.0/`, `releases/0.1.4/` | Неизменённый предок и текущие шесть файлов данных. В проект устанавливается только выбранная одобренная версия. |')
    assert '32 `pass`' in text, 'нет итога испытаний 0.1.0'
    text = text.replace('Отчёт содержит 32 `pass`, 0 `fail`, 3 `not run`', f'Отчёт содержит {PASS_TOTAL} `pass`, 0 `fail`, 3 `not run`')
    marker = '## Состав поставки'
    assert marker in text
    return text.rstrip('\n') + '\n' + RESTORED_NOTE


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--line', default='base', choices=sorted(LINES))
    args = ap.parse_args()
    root_name, origin, suffix = LINES[args.line]
    out = ROOT / args.line
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    with zipfile.ZipFile(SOURCE) as z:
        z.extractall(out)
    tree = out / 'AgentContractLab'
    assert tree.is_dir(), tree

    # 1. программа: смысловое тождество наблюдения и допуск из И-020
    tool = tree / 'kit/tools/contract.py'
    t = tool.read_text(encoding='utf-8')
    assert TOOL_OLD in t, 'программа 0.1.0 отличается от ожидаемой'
    assert 'def same_observation' not in t
    t = t.replace(TOOL_OLD, TOOL_NEW)
    assert "VERSION = '0.1.0'" in t
    t = t.replace("VERSION = '0.1.0'", f"VERSION = '{VERSION}'", 1)
    t = t.replace('import uuid', 'import unicodedata\nimport uuid', 1)
    marker = 'def decision(s, op, at, reason, subject):'
    assert marker in t and 'def plain(' not in t
    tool.write_text(t.replace(marker, HELPERS + marker, 1), encoding='utf-8')
    if newer('0.1.5'):
        program = tool.read_text(encoding='utf-8')
        assert p16.NATIVE_HINTS_OLD in program
        program = program.replace(p16.NATIVE_HINTS_OLD, p16.NATIVE_HINTS_NEW, 1)
        assert 'class Refusal(Exception):' in program and 'ADAPTERS = {' not in program
        program = program.replace('class Refusal(Exception):', p16.ADAPTERS_BLOCK + 'class Refusal(Exception):', 1)
        marker2 = "    exact(payload, '')\n    if command == 'inventory':"
        assert marker2 in program and 'adapter_unknown' not in program
        program = program.replace(marker2, p16.ADAPTER_COMMAND + marker2, 1)
        tool.write_text(program, encoding='utf-8')
    if newer('0.1.6'):
        program = tool.read_text(encoding='utf-8')
        assert p16.NATIVE_HINTS_NEW in program
        program = program.replace(p16.NATIVE_HINTS_NEW, p17.NATIVE_HINTS_NEW, 1)
        assert "ADAPTERS['copilot']" not in program
        assert p17.CONNECT_OLD in program, 'нет места для правки connect'
        program = program.replace(p17.CONNECT_OLD, p17.CONNECT_NEW, 1)
        program = program.rstrip('\n') + '\n\n\n' + p17.COPILOT_BLOCK
        tool.write_text(program, encoding='utf-8')
    if newer('0.1.7'):
        program = tool.read_text(encoding='utf-8')
        assert p18.DISPATCH_OLD in program, 'нет места для правки выдачи карточки'
        program = program.replace(p18.DISPATCH_OLD, p18.DISPATCH_NEW, 1)
        assert 'STUB_ENVIRONMENTS' not in program
        tool.write_text(program.rstrip('\n') + '\n\n\n' + p18.STUB_BLOCK, encoding='utf-8')
    if newer('0.1.8'):
        program = tool.read_text(encoding='utf-8')
        assert 'CONDITIONS' not in program
        assert p19.SAME_OLD in program, 'нет места для правки сравнения environment'
        program = program.replace(p19.SAME_OLD, p19.SAME_NEW, 1)
        assert p19.NOTE_OLD in program, 'нет места для примечания о повторе'
        program = program.replace(p19.NOTE_OLD, p19.NOTE_NEW, 1)
        assert p19.SORT_OLD in program, 'нет места для порядка выпусков'
        program = program.replace(p19.SORT_OLD, p19.SORT_NEW, 1)
        tool.write_text(program.rstrip('\n') + '\n\n\n' + p19.CONSTANTS, encoding='utf-8')
    if newer('0.1.9'):
        program = tool.read_text(encoding='utf-8')
        assert p20.FACTS_OLD in program, 'нет места для правки набора фактов'
        program = program.replace(p20.FACTS_OLD, p20.FACTS_NEW, 1)
        tool.write_text(program, encoding='utf-8')
    if newer('0.1.10'):
        program = tool.read_text(encoding='utf-8')
        program = p21.relocate(program)
        assert p21.CHOICES_OLD in program, 'нет списка команд консоли'
        program = program.replace(p21.CHOICES_OLD, p21.CHOICES_NEW, 1)
        assert p21.STDIN_OLD in program, 'нет чтения нагрузки из консоли'
        program = program.replace(p21.STDIN_OLD, p21.STDIN_NEW, 1)
        tool.write_text(program, encoding='utf-8')
    if newer('0.1.4'):
        program = tool.read_text(encoding='utf-8')
        for old, new in PATCH_015:
            assert old in program, 'нет места для правки тождества: ' + old[:60]
            program = program.replace(old, new, 1)
        assert 'def body(' in program
        tool.write_text(program, encoding='utf-8')
    if newer('0.1.11'):
        program = tool.read_text(encoding='utf-8')
        assert p22.SAFE_TARGET_OLD in program, 'нет места для проекта вне корня комплекта'
        program = program.replace(p22.SAFE_TARGET_OLD, p22.SAFE_TARGET_NEW, 1)
        assert p22.PENDING_OLD in program, 'нет места для переносимого журнала'
        program = program.replace(p22.PENDING_OLD, p22.PENDING_NEW, 1)
        assert p22.STATUS_OLD in program, 'нет места для режима входа'
        program = program.replace(p22.STATUS_OLD, p22.STATUS_NEW, 1)
        assert p22.STATUS_RETURN_OLD in program, 'нет места для полей режима входа'
        program = program.replace(p22.STATUS_RETURN_OLD, p22.STATUS_RETURN_NEW, 1)
        marker = "    if command == 'status':\n        adapter = s['adapter']"
        assert marker in program, 'нет места для команды brief'
        program = program.replace(marker, p22.BRIEF_BLOCK + marker, 1)
        assert p22.CHOICES_OLD in program, 'нет списка команд консоли'
        program = program.replace(p22.CHOICES_OLD, p22.CHOICES_NEW, 1)
        tool.write_text(program, encoding='utf-8')
    if newer('0.1.12'):
        program = tool.read_text(encoding='utf-8')
        marker = "def plan(lab, project, r, at=None):"
        assert marker in program and 'def merge_checks(' not in program, 'нет места для слияния'
        program = program.replace(marker, p23.MERGE_HELPER + marker, 1)
        branch = "    migrated = legacy_zero(parse(p.observe(STATE, True))) if op == 'migrate' else None"
        assert branch in program, 'нет места для ветки merge'
        program = program.replace(branch, p23.MERGE_BRANCH + branch, 1)
        ident = "    if command == 'brief':"
        assert ident in program, 'нет места для команды identity'
        program = program.replace(ident, p23.IDENTITY_COMMAND + ident, 1)
        assert p23.CHOICES_OLD in program, 'нет списка команд консоли 0.1.12'
        program = program.replace(p23.CHOICES_OLD, p23.CHOICES_NEW, 1)
        tool.write_text(program, encoding='utf-8')

    if newer('0.1.13'):
        start = tree / 'kit/base/START.md'
        text = start.read_text(encoding='utf-8')
        assert p24.START_OLD in text, 'нет абзаца первого запроса'
        start.write_text(text.replace(p24.START_OLD, p24.start_block(), 1), encoding='utf-8')
        if args.line == 'edition':
            docs = tree / 'docs'
            if docs.exists():
                shutil.rmtree(docs)
            docs.mkdir()
            (docs / 'ПЕРВЫЙ-ЗАПУСК.md').write_text(p24.docs_text(), encoding='utf-8')

    if newer('0.1.14'):
        program = tool.read_text(encoding='utf-8')
        marker = "    if command == 'adapter':"
        assert marker in program and 'def discovery(' not in program, 'нет места для discovery'
        program = program.replace(marker, p25.DISCOVERY_BRANCH + marker, 1)
        helper = '\n\nclass Refusal(Exception):'
        assert helper in program, 'нет места для таблицы обнаружения'
        program = program.replace(helper, p25.DISCOVERY_ORDER + helper, 1)
        assert p25.CHOICES_OLD in program, 'нет списка команд консоли 0.1.14'
        program = program.replace(p25.CHOICES_OLD, p25.CHOICES_NEW, 1)
        assert p25.STDIN_OLD in program, 'нет чтения входа для discovery'
        program = program.replace(p25.STDIN_OLD, p25.STDIN_NEW, 1)
        tool.write_text(program, encoding='utf-8')

    if newer('0.1.15'):
        program = tool.read_text(encoding='utf-8')
        marker = "    exact(payload, '')\n    if command == 'inventory':"
        assert marker in program and 'def entry_read(' not in program, 'нет места для команды entry'
        program = program.replace(marker, p26.ENTRY_COMMAND + marker, 1)
        assert p26.CHOICES_OLD in program, 'нет списка команд консоли 0.1.15'
        program = program.replace(p26.CHOICES_OLD, p26.CHOICES_NEW, 1)
        assert p26.STDIN_OLD in program, 'нет чтения входа для entry'
        program = program.replace(p26.STDIN_OLD, p26.STDIN_NEW, 1)
        tool.write_text(program, encoding='utf-8')

    if newer('0.1.16'):
        program = tool.read_text(encoding='utf-8')
        marker = "\n\nclass Refusal(Exception):"
        assert marker in program and 'def repeat_reads(' not in program, 'нет места для repeat'
        program = program.replace(marker, '\n\n' + p27.REPEAT_HELPER + marker.lstrip('\n'), 1)
        branch = "    exact(payload, '')\n    if command == 'inventory':"
        assert branch in program, 'нет места для ветки repeat'
        program = program.replace(branch, p27.REPEAT_BRANCH + branch, 1)
        assert p27.CHOICES_OLD in program, 'нет списка команд консоли 0.1.16'
        program = program.replace(p27.CHOICES_OLD, p27.CHOICES_NEW, 1)
        assert p27.STDIN_OLD in program, 'нет чтения входа для repeat'
        program = program.replace(p27.STDIN_OLD, p27.STDIN_NEW, 1)
        tool.write_text(program, encoding='utf-8')

    if newer('0.1.18'):
        program = tool.read_text(encoding='utf-8')
        assert p29.READ_ONLY_OLD in program, 'нет списка команд чтения'
        program = program.replace(p29.READ_ONLY_OLD, p29.READ_ONLY_NEW, 1)
        assert p29.SESSION_OLD in program, 'нет команды session'
        program = program.replace(p29.SESSION_OLD, p29.SESSION_NEW, 1)
        assert "'not_saved'" in program, 'нет отказа на сохранение запроса'
        tool.write_text(program, encoding='utf-8')

    if newer('0.1.17'):
        program = tool.read_text(encoding='utf-8')
        assert p28.DECISION_OLD in program, 'нет функции decision'
        program = program.replace(p28.DECISION_OLD, p28.DECISION_NEW, 1)
        assert p28.CHECK_STATE_OLD in program, 'нет проверки решений'
        program = program.replace(p28.CHECK_STATE_OLD,
                                  p28.CHECK_STATE_NEW + "\n" + p28.CHANGES_CHECK, 1)
        start = program.index(p28.MUTATE_OLD_START)
        end = program.index(p28.MUTATE_OLD_END)
        program = program[:start] + p28.MUTATE_NEW + program[end:]
        assert "'allow_scope'" in program, 'нет согласия на смену области'
        tool.write_text(program, encoding='utf-8')

    if newer('0.1.19'):
        program = tool.read_text(encoding='utf-8')
        assert p30.CHECK_STATE_OLD in program, 'нет проверки схемы состояния'
        program = program.replace(p30.CHECK_STATE_OLD, p30.CHECK_STATE_NEW, 1)
        assert p30.ENTRIES_CHECK_OLD in program, 'нет проверки записей'
        program = program.replace(p30.ENTRIES_CHECK_OLD, p30.ENTRIES_CHECK_NEW, 1)
        assert p30.PURGE_OLD in program, 'нет удаления записи'
        program = program.replace(p30.PURGE_OLD, p30.PURGE_NEW, 1)
        assert p30.HISTORY_OLD in program, 'нет ветки history'
        program = program.replace(p30.HISTORY_OLD, p30.HISTORY_NEW, 1)
        assert p30.STATUS_OLD in program, 'нет ответа status'
        program = program.replace(p30.STATUS_OLD, p30.STATUS_NEW, 1)
        assert p30.READ_ONLY_OLD in program, 'нет списка команд чтения'
        program = program.replace(p30.READ_ONLY_OLD, p30.READ_ONLY_NEW, 1)
        assert p30.CHOICES_OLD in program, 'нет списка команд консоли'
        program = program.replace(p30.CHOICES_OLD, p30.CHOICES_NEW, 1)
        assert "'tombstones'" in program and "'removed'" in program, 'нет следа удаления'
        tool.write_text(program, encoding='utf-8')

    if newer('0.1.20'):
        program = tool.read_text(encoding='utf-8')
        assert p31.DISPATCH_OLD in program, 'нет точки входа команд'
        program = program.replace(p31.DISPATCH_OLD, p31.DISPATCH_NEW, 1)
        program = program.replace(p31.DISPATCH_NEW, p31.SECRETS_BLOCK + p31.WRAPPER + p31.DISPATCH_NEW, 1)
        assert p31.CREATE_OLD in program, 'нет создания записи'
        program = program.replace(p31.CREATE_OLD, p31.CREATE_NEW, 1)
        assert p31.EDIT_OLD in program, 'нет правки записи'
        program = program.replace(p31.EDIT_OLD, p31.EDIT_NEW, 1)
        assert p31.SESSION_OLD in program, 'нет разового запроса'
        program = program.replace(p31.SESSION_OLD, p31.SESSION_NEW, 1)
        assert 'SECRET_PATTERNS' in program and 'def scrubbed(' in program, 'нет очистки ответов'
        tool.write_text(program, encoding='utf-8')

    if newer('0.1.21'):
        program = tool.read_text(encoding='utf-8')
        assert p32.ENTRY_EXACT_OLD in program, 'нет проверки полей записи'
        program = program.replace(p32.ENTRY_EXACT_OLD, p32.ENTRY_EXACT_NEW, 1)
        assert p32.CREATE_EXACT_OLD in program, 'нет создания записи'
        program = program.replace(p32.CREATE_EXACT_OLD, p32.CREATE_EXACT_NEW, 1)
        assert p32.EDITABLE_OLD in program, 'нет списка изменяемых полей'
        program = program.replace(p32.EDITABLE_OLD, p32.EDITABLE_NEW, 1)
        assert p32.MUTATE_EXACT_OLD in program, 'нет разбора операции'
        program = program.replace(p32.MUTATE_EXACT_OLD, p32.MUTATE_EXACT_NEW, 1)
        assert p32.OWNER_OLD in program, 'нет поиска записи'
        program = program.replace(p32.OWNER_OLD, p32.OWNER_NEW, 1)
        assert "'not_owner'" in program and "'allow_owner'" in program, 'нет проверки владельца'
        tool.write_text(program, encoding='utf-8')

    if newer('0.1.22'):
        program = tool.read_text(encoding='utf-8')
        for old, new, why in ((p33.ENTRY_EXACT_OLD, p33.ENTRY_EXACT_NEW, 'проверка полей записи'),
                              (p33.CREATE_EXACT_OLD, p33.CREATE_EXACT_NEW, 'создание записи'),
                              (p33.EDITABLE_OLD, p33.EDITABLE_NEW, 'список изменяемых полей'),
                              (p33.MUTATE_EXACT_OLD, p33.MUTATE_EXACT_NEW, 'разбор операции'),
                              (p33.SAME_OLD, p33.SAME_NEW, 'повтор правки'),
                              (p33.PLAN_CALL_OLD, p33.PLAN_CALL_NEW, 'вызов правки из плана'),
                              (p33.DESCRIBE_OLD, p33.DESCRIBE_NEW, 'ответ плана'),
                              (p33.REVIEW_OLD, p33.REVIEW_NEW, 'ветка смены состояния'),
                              (p33.REVISION_OLD, p33.REVISION_NEW, 'подъём версии'),
                              (p33.PLUS_DAYS_OLD, p33.PLUS_DAYS_NEW, 'функция срока'),
                              (p33.DUE_OLD, p33.DUE_NEW, 'команда due'),
                              (p33.APPLY_OPS_OLD, p33.APPLY_OPS_NEW, 'разбор операций'),
                              (p33.CLI_OLD, p33.CLI_NEW, 'список команд')):
            assert old in program, 'нет: ' + why
            program = program.replace(old, new, 1)
        assert "'same'" in program and "'review_by'" in program, 'нет версии содержимого'
        ast.parse(program)
        tool.write_text(program, encoding='utf-8')

    if newer('0.1.23'):
        program = tool.read_text(encoding='utf-8')
        for old, new, why in ((p34.UNKNOWN_SCHEMA_OLD, p34.UNKNOWN_SCHEMA_NEW, 'проверка схемы проекта'),
                              (p34.LEGACY_OLD, p34.LEGACY_NEW, 'миграция схемы 0')):
            assert old in program, 'нет: ' + why
            program = program.replace(old, new, 1)
        assert "'unknown_schema'" in program, 'нет отказа неизвестной схемы'
        ast.parse(program)
        tool.write_text(program, encoding='utf-8')

    if newer('0.1.24'):
        program = tool.read_text(encoding='utf-8')
        for old, new, why in ((p35.STATUS_OLD, p35.STATUS_NEW, 'ответ при незавершённой операции'),
                              (p35.SALVAGE_OLD, p35.SALVAGE_NEW, 'заметки восстановления')):
            assert old in program, 'нет: ' + why
            program = program.replace(old, new, 1)
        assert "'pending_detail'" in program and "'salvage'" in program, 'нет диагностики частичного сбоя'
        ast.parse(program)
        tool.write_text(program, encoding='utf-8')

    if newer('0.1.25'):
        program = tool.read_text(encoding='utf-8')
        for old, new, why in ((p36.METRICS_OLD, p36.METRICS_NEW, 'команда metrics'),
                              (p36.CLI_OLD, p36.CLI_NEW, 'список команд')):
            assert old in program, 'нет: ' + why
            program = program.replace(old, new, 1)
        assert "'metrics'" in program, 'нет метрик'
        ast.parse(program)
        tool.write_text(program, encoding='utf-8')

    if newer('0.1.26'):
        program = tool.read_text(encoding='utf-8')
        for old, new, why in ((p37.CREATE_PARENT_OLD, p37.CREATE_PARENT_NEW, 'ввод под контрактом'),
                              (p37.TRANSITION_OLD, p37.TRANSITION_NEW, 'переход состояния'),
                              (p37.DUE_STATE_OLD, p37.DUE_STATE_NEW, 'элемент due'),
                              (p37.HIDDEN_OLD, p37.HIDDEN_NEW, 'счёт скрытого'),
                              (p37.HIDDEN_PAYLOAD_OLD, p37.HIDDEN_PAYLOAD_NEW, 'ответ метрик')):
            assert old in program, 'нет: ' + why
            program = program.replace(old, new, 1)
        assert "by_reason=reasons" in program and "'parent_state'" in program, 'нет контура состояний'
        ast.parse(program)
        tool.write_text(program, encoding='utf-8')

    if newer('0.1.27'):
        program = tool.read_text(encoding='utf-8')
        for old, new, why in ((p38.CLI_STDIN_OLD, p38.CLI_STDIN_NEW, 'вход консоли для metrics'),
                              (p38.GENERAL_EXACT_OLD, p38.GENERAL_EXACT_NEW, 'общий разбор полей'),
                              (p38.HELPERS_OLD, p38.HELPERS_NEW, 'сравнение сценариев'),
                              (p38.METRICS_PAYLOAD_OLD, p38.METRICS_PAYLOAD_NEW, 'параметр against'),
                              (p38.METRICS_COMPARE_OLD, p38.METRICS_COMPARE_NEW, 'ответ метрик'),
                              (p38.METRICS_TAIL_OLD, p38.METRICS_TAIL_NEW, 'раздел compare')):
            assert old in program, 'нет: ' + why
            program = program.replace(old, new, 1)
        assert "scene_compare" in program and "'compare'" in program, 'нет сравнения сценариев'
        ast.parse(program)
        tool.write_text(program, encoding='utf-8')

    if newer('0.1.28'):
        program = tool.read_text(encoding='utf-8')
        for old, new, why in ((p39.FOREIGN_OLD, p39.FOREIGN_NEW, 'границы служебного каталога'),
                              (p39.READ_ONLY_OLD, p39.READ_ONLY_NEW, 'список чтения'),
                              (p39.PLAN_OLD, p39.PLAN_NEW, 'проверка перед изменением'),
                              (p39.STATUS_OLD, p39.STATUS_NEW, 'посторонние в статусе'),
                              (p39.RIGHTS_OLD, p39.RIGHTS_NEW, 'команда rights'),
                              (p39.CLI_OLD, p39.CLI_NEW, 'список команд')):
            assert old in program, 'нет: ' + why
            program = program.replace(old, new, 1)
        assert "if command == 'rights'" in program and 'guard_writes' in program, 'нет прав'
        ast.parse(program)
        tool.write_text(program, encoding='utf-8')


    # 2. регрессии на оба правила
    tests = tree / 'kit/tests/test_contract.py'
    tt = tests.read_text(encoding='utf-8')
    end = '\n\nclass Results(unittest.TextTestResult):'
    assert end in tt and 'test_40_exact_repeat' not in tt
    tt = tt.replace(end, TEST_NEW + end, 1)
    if newer('0.1.4'):
        tt = tt.replace(end, TEST_015 + end, 1)
    if newer('0.1.5'):
        tt = tt.replace(end, p16.TEST_016 + end, 1)
    if newer('0.1.6'):
        tt = tt.replace(end, p17.TEST_017 + end, 1)
    if newer('0.1.7'):
        tt = tt.replace(end, p18.TEST_018 + end, 1)
    if newer('0.1.8'):
        tt = tt.replace(end, p19.TEST_019 + end, 1)
        tt = tt.replace(end, p19.TEST_019B + end, 1)
    if newer('0.1.9'):
        for old_line, new_line in p20.FIX_LINES:
            assert old_line in tt, 'нет места для версионно-независимого X33'
            tt = tt.replace(old_line, new_line, 1)
        tt = tt.replace(end, p20.TEST_020 + end, 1)
    if newer('0.1.10'):
        tt = tt.replace(end, p21.TEST_021 + end, 1)
    if newer('0.1.11'):
        tt = tt.replace(end, p22.TEST_022 + end, 1)
    if newer('0.1.12'):
        tt = tt.replace(end, p23.TEST_023 + end, 1)
    if newer('0.1.13'):
        tt = tt.replace(end, p24.TEST_024 + end, 1)
    if newer('0.1.14'):
        tt = tt.replace(end, p25.TEST_025 + end, 1)
    if newer('0.1.15'):
        tt = tt.replace(end, p26.TEST_026 + end, 1)
    if newer('0.1.16'):
        tt = tt.replace(end, p27.TEST_027 + end, 1)
    if newer('0.1.17'):
        tt = tt.replace(end, p28.TEST_028 + end, 1)
    if newer('0.1.18'):
        tt = tt.replace(end, p29.TEST_029 + end, 1)
    if newer('0.1.19'):
        tt = tt.replace(end, p30.TEST_030 + end, 1)
    if newer('0.1.20'):
        tt = tt.replace(end, p31.TEST_031 + end, 1)
    if newer('0.1.21'):
        tt = tt.replace(end, p32.TEST_032 + end, 1)
    if newer('0.1.22'):
        tt = tt.replace(end, p33.TEST_033 + end, 1)
    if newer('0.1.23'):
        assert p34.CHECK04_OLD in tt, 'нет ожидания T04'
        tt = tt.replace(p34.CHECK04_OLD, p34.CHECK04_NEW, 1)
        tt = tt.replace(end, p34.TEST_034 + end, 1)
    if newer('0.1.24'):
        tt = tt.replace(end, p35.TEST_035 + end, 1)
    if newer('0.1.25'):
        tt = tt.replace(end, p36.TEST_036 + end, 1)
    if newer('0.1.26'):
        tt = tt.replace(end, p37.TEST_037 + end, 1)
    if newer('0.1.27'):
        tt = tt.replace(end, p38.TEST_038 + end, 1)
    if newer('0.1.28'):
        tt = tt.replace(end, p39.TEST_039 + end, 1)
    for old, new in TESTS_VERSION_PATCHES:
        assert old in tt, 'нет места для правки версии в регрессиях: ' + old[:60]
        tt = tt.replace(old, new, 1)
    tests.write_text(tt, encoding='utf-8')

    # 3. справочник: новое правило и номер версии
    guide = tree / 'kit/base/PROTOCOL.md'
    g = guide.read_text(encoding='utf-8')
    g = re.sub(r'^# Справочник механизма • 0\.1\.0 / схема 1', f'# Справочник механизма • {VERSION} / схема 1', g, flags=re.M)
    guide.write_text(g.rstrip('\n') + PROTOCOL_PARA, encoding='utf-8')
    if newer('0.1.4'):
        guide.write_text(g.rstrip('\n') + PROTOCOL_PARA + PROTOCOL_015, encoding='utf-8')
    if newer('0.1.5'):
        guide.write_text(g.rstrip('\n') + PROTOCOL_PARA + PROTOCOL_015 + p16.PROTOCOL_016, encoding='utf-8')
    if newer('0.1.6'):
        guide.write_text(g.rstrip('\n') + PROTOCOL_PARA + PROTOCOL_015 + p16.PROTOCOL_016
                         + p17.PROTOCOL_017, encoding='utf-8')
    if newer('0.1.7'):
        guide.write_text(g.rstrip('\n') + PROTOCOL_PARA + PROTOCOL_015 + p16.PROTOCOL_016
                         + p17.PROTOCOL_017 + p18.PROTOCOL_018, encoding='utf-8')
    if newer('0.1.8'):
        guide.write_text(g.rstrip('\n') + PROTOCOL_PARA + PROTOCOL_015 + p16.PROTOCOL_016
                         + p17.PROTOCOL_017 + p18.PROTOCOL_018 + p19.PROTOCOL_019, encoding='utf-8')
    if newer('0.1.9'):
        guide.write_text(g.rstrip('\n') + PROTOCOL_PARA + PROTOCOL_015 + p16.PROTOCOL_016
                         + p17.PROTOCOL_017 + p18.PROTOCOL_018 + p19.PROTOCOL_019
                         + p20.PROTOCOL_020, encoding='utf-8')
    if newer('0.1.10'):
        guide.write_text(g.rstrip('\n') + PROTOCOL_PARA + PROTOCOL_015 + p16.PROTOCOL_016
                         + p17.PROTOCOL_017 + p18.PROTOCOL_018 + p19.PROTOCOL_019
                         + p20.PROTOCOL_020 + p21.PROTOCOL_021, encoding='utf-8')
    if newer('0.1.11'):
        guide.write_text(g.rstrip('\n') + PROTOCOL_PARA + PROTOCOL_015 + p16.PROTOCOL_016
                         + p17.PROTOCOL_017 + p18.PROTOCOL_018 + p19.PROTOCOL_019
                         + p20.PROTOCOL_020 + p21.PROTOCOL_021 + p22.PROTOCOL_022, encoding='utf-8')
    if newer('0.1.12'):
        guide.write_text(g.rstrip('\n') + PROTOCOL_PARA + PROTOCOL_015 + p16.PROTOCOL_016
                         + p17.PROTOCOL_017 + p18.PROTOCOL_018 + p19.PROTOCOL_019
                         + p20.PROTOCOL_020 + p21.PROTOCOL_021 + p22.PROTOCOL_022
                         + p23.PROTOCOL_023, encoding='utf-8')
    if newer('0.1.13'):
        guide.write_text(g.rstrip('\n') + PROTOCOL_PARA + PROTOCOL_015 + p16.PROTOCOL_016
                         + p17.PROTOCOL_017 + p18.PROTOCOL_018 + p19.PROTOCOL_019
                         + p20.PROTOCOL_020 + p21.PROTOCOL_021 + p22.PROTOCOL_022
                         + p23.PROTOCOL_023 + p24.PROTOCOL_024, encoding='utf-8')
    if newer('0.1.14'):
        guide.write_text(g.rstrip('\n') + PROTOCOL_PARA + PROTOCOL_015 + p16.PROTOCOL_016
                         + p17.PROTOCOL_017 + p18.PROTOCOL_018 + p19.PROTOCOL_019
                         + p20.PROTOCOL_020 + p21.PROTOCOL_021 + p22.PROTOCOL_022
                         + p23.PROTOCOL_023 + p24.PROTOCOL_024 + p25.PROTOCOL_025,
                         encoding='utf-8')
    if newer('0.1.15'):
        guide.write_text(g.rstrip('\n') + PROTOCOL_PARA + PROTOCOL_015 + p16.PROTOCOL_016
                         + p17.PROTOCOL_017 + p18.PROTOCOL_018 + p19.PROTOCOL_019
                         + p20.PROTOCOL_020 + p21.PROTOCOL_021 + p22.PROTOCOL_022
                         + p23.PROTOCOL_023 + p24.PROTOCOL_024 + p25.PROTOCOL_025
                         + p26.PROTOCOL_026, encoding='utf-8')
    if newer('0.1.16'):
        guide.write_text(g.rstrip('\n') + PROTOCOL_PARA + PROTOCOL_015 + p16.PROTOCOL_016
                         + p17.PROTOCOL_017 + p18.PROTOCOL_018 + p19.PROTOCOL_019
                         + p20.PROTOCOL_020 + p21.PROTOCOL_021 + p22.PROTOCOL_022
                         + p23.PROTOCOL_023 + p24.PROTOCOL_024 + p25.PROTOCOL_025
                         + p26.PROTOCOL_026 + p27.PROTOCOL_027, encoding='utf-8')
    if newer('0.1.17'):
        guide.write_text(g.rstrip('\n') + PROTOCOL_PARA + PROTOCOL_015 + p16.PROTOCOL_016
                         + p17.PROTOCOL_017 + p18.PROTOCOL_018 + p19.PROTOCOL_019
                         + p20.PROTOCOL_020 + p21.PROTOCOL_021 + p22.PROTOCOL_022
                         + p23.PROTOCOL_023 + p24.PROTOCOL_024 + p25.PROTOCOL_025
                         + p26.PROTOCOL_026 + p27.PROTOCOL_027 + p28.PROTOCOL_028,
                         encoding='utf-8')
    if newer('0.1.18'):
        guide.write_text(g.rstrip('\n') + PROTOCOL_PARA + PROTOCOL_015 + p16.PROTOCOL_016
                         + p17.PROTOCOL_017 + p18.PROTOCOL_018 + p19.PROTOCOL_019
                         + p20.PROTOCOL_020 + p21.PROTOCOL_021 + p22.PROTOCOL_022
                         + p23.PROTOCOL_023 + p24.PROTOCOL_024 + p25.PROTOCOL_025
                         + p26.PROTOCOL_026 + p27.PROTOCOL_027 + p28.PROTOCOL_028
                         + p29.PROTOCOL_029, encoding='utf-8')
    if newer('0.1.19'):
        guide.write_text(g.rstrip('\n') + PROTOCOL_PARA + PROTOCOL_015 + p16.PROTOCOL_016
                         + p17.PROTOCOL_017 + p18.PROTOCOL_018 + p19.PROTOCOL_019
                         + p20.PROTOCOL_020 + p21.PROTOCOL_021 + p22.PROTOCOL_022
                         + p23.PROTOCOL_023 + p24.PROTOCOL_024 + p25.PROTOCOL_025
                         + p26.PROTOCOL_026 + p27.PROTOCOL_027 + p28.PROTOCOL_028
                         + p29.PROTOCOL_029 + p30.PROTOCOL_030, encoding='utf-8')
    if newer('0.1.20'):
        guide.write_text(g.rstrip('\n') + PROTOCOL_PARA + PROTOCOL_015 + p16.PROTOCOL_016
                         + p17.PROTOCOL_017 + p18.PROTOCOL_018 + p19.PROTOCOL_019
                         + p20.PROTOCOL_020 + p21.PROTOCOL_021 + p22.PROTOCOL_022
                         + p23.PROTOCOL_023 + p24.PROTOCOL_024 + p25.PROTOCOL_025
                         + p26.PROTOCOL_026 + p27.PROTOCOL_027 + p28.PROTOCOL_028
                         + p29.PROTOCOL_029 + p30.PROTOCOL_030 + p31.PROTOCOL_031,
                         encoding='utf-8')
    if newer('0.1.21'):
        guide.write_text(g.rstrip('\n') + PROTOCOL_PARA + PROTOCOL_015 + p16.PROTOCOL_016
                         + p17.PROTOCOL_017 + p18.PROTOCOL_018 + p19.PROTOCOL_019
                         + p20.PROTOCOL_020 + p21.PROTOCOL_021 + p22.PROTOCOL_022
                         + p23.PROTOCOL_023 + p24.PROTOCOL_024 + p25.PROTOCOL_025
                         + p26.PROTOCOL_026 + p27.PROTOCOL_027 + p28.PROTOCOL_028
                         + p29.PROTOCOL_029 + p30.PROTOCOL_030 + p31.PROTOCOL_031
                         + p32.PROTOCOL_032, encoding='utf-8')
    if newer('0.1.22'):
        guide.write_text(g.rstrip('\n') + PROTOCOL_PARA + PROTOCOL_015 + p16.PROTOCOL_016
                         + p17.PROTOCOL_017 + p18.PROTOCOL_018 + p19.PROTOCOL_019
                         + p20.PROTOCOL_020 + p21.PROTOCOL_021 + p22.PROTOCOL_022
                         + p23.PROTOCOL_023 + p24.PROTOCOL_024 + p25.PROTOCOL_025
                         + p26.PROTOCOL_026 + p27.PROTOCOL_027 + p28.PROTOCOL_028
                         + p29.PROTOCOL_029 + p30.PROTOCOL_030 + p31.PROTOCOL_031
                         + p32.PROTOCOL_032 + p33.PROTOCOL_033, encoding='utf-8')

    # 4. метаданные выпуска
    files = {}
    for name in ('PROTOCOL.md', 'START.md', 'entry.txt', 'rules.json', 'schema.json'):
        files[name] = sha((tree / 'kit/base' / name).read_bytes())
    manifest = dict(adapter_version=1, base_version=VERSION, files=files, format='agent-contract-release',
                    origin=origin, schema_version=1)
    man_bytes = enc(manifest)
    (tree / 'kit/base/manifest.json').write_bytes(man_bytes)
    release = tree / f'releases/{VERSION}'
    if release.exists():
        shutil.rmtree(release)
    release.mkdir()
    for name in ('PROTOCOL.md', 'START.md', 'entry.txt', 'rules.json', 'schema.json'):
        (release / name).write_bytes((tree / 'kit/base' / name).read_bytes())
    (release / 'manifest.json').write_bytes(man_bytes)

    # 5. собственные испытания комплекта
    runs = tree / 'runs'
    if runs.exists():
        shutil.rmtree(runs)
    rc = subprocess.run([sys.executable, '-I', '-B', 'kit/tests/test_contract.py', '--run-id', f'release-{VERSION}'],
                        cwd=tree, capture_output=True)
    sys.stdout.write(rc.stdout.decode()); sys.stderr.write(rc.stderr.decode())
    assert rc.returncode == 0, 'испытания комплекта не пройдены'
    checks = (tree / f'runs/release-{VERSION}/CHECKS.json').read_bytes()
    (tree / 'reports/CHECKS.json').write_bytes(checks)
    totals = json.loads(checks)['totals']
    shutil.rmtree(runs)

    # 6. сквозная имитация
    pipe = subprocess.run([sys.executable, '-I', '-B', str(ROOT / 'pipeline_check.py'), '--tree', str(tree)],
                          capture_output=True)
    sys.stderr.write(pipe.stderr.decode())
    assert pipe.returncode == 0, 'сквозная имитация не пройдена'
    (tree / 'reports/PIPELINE.json').write_bytes(pipe.stdout)

    # 7. README и ведомость отпечатков
    readme = tree / 'README.md'
    readme.write_text(readme_update(readme.read_text(encoding='utf-8'), args.line), encoding='utf-8')
    if newer('0.1.4'):
        prev_root = ROOT.parent / f'release-{PREV_RELEASE}' / args.line / 'AgentContractLab' / 'releases'
        if prev_root.is_dir():
            for folder in sorted(prev_root.iterdir()):
                target_prev = tree / 'releases' / folder.name
                if folder.is_dir() and folder.name != VERSION and not target_prev.exists():
                    shutil.copytree(folder, target_prev)
        readme.write_text(readme.read_text(encoding='utf-8') + README_015, encoding='utf-8')
    if newer('0.1.5'):
        readme.write_text(readme.read_text(encoding='utf-8') + p16.README_016, encoding='utf-8')
    if newer('0.1.6'):
        readme.write_text(readme.read_text(encoding='utf-8') + p17.README_017, encoding='utf-8')
    if newer('0.1.7'):
        readme.write_text(readme.read_text(encoding='utf-8') + p18.README_018, encoding='utf-8')
    if newer('0.1.8'):
        readme.write_text(readme.read_text(encoding='utf-8') + p19.README_019, encoding='utf-8')
    if newer('0.1.9'):
        readme.write_text(readme.read_text(encoding='utf-8') + p20.README_020, encoding='utf-8')
    if newer('0.1.10'):
        readme.write_text(readme.read_text(encoding='utf-8') + p21.README_021, encoding='utf-8')
    if newer('0.1.11'):
        readme.write_text(readme.read_text(encoding='utf-8') + p22.README_022, encoding='utf-8')
    if newer('0.1.12'):
        readme.write_text(readme.read_text(encoding='utf-8') + p23.README_023, encoding='utf-8')
    if newer('0.1.13'):
        readme.write_text(readme.read_text(encoding='utf-8') + p24.README_024, encoding='utf-8')
    if newer('0.1.14'):
        readme.write_text(readme.read_text(encoding='utf-8') + p25.README_025, encoding='utf-8')
    if newer('0.1.15'):
        readme.write_text(readme.read_text(encoding='utf-8') + p26.README_026, encoding='utf-8')
    if newer('0.1.16'):
        readme.write_text(readme.read_text(encoding='utf-8') + p27.README_027, encoding='utf-8')
    if newer('0.1.17'):
        readme.write_text(readme.read_text(encoding='utf-8') + p28.README_028, encoding='utf-8')
    if newer('0.1.18'):
        readme.write_text(readme.read_text(encoding='utf-8') + p29.README_029, encoding='utf-8')
    if newer('0.1.19'):
        readme.write_text(readme.read_text(encoding='utf-8') + p30.README_030, encoding='utf-8')
    if newer('0.1.20'):
        readme.write_text(readme.read_text(encoding='utf-8') + p31.README_031, encoding='utf-8')
    if newer('0.1.21'):
        readme.write_text(readme.read_text(encoding='utf-8') + p32.README_032, encoding='utf-8')
    if newer('0.1.22'):
        readme.write_text(readme.read_text(encoding='utf-8') + p33.README_033, encoding='utf-8')
    if newer('0.1.23'):
        readme.write_text(readme.read_text(encoding='utf-8') + p34.README_034, encoding='utf-8')
    if newer('0.1.24'):
        readme.write_text(readme.read_text(encoding='utf-8') + p35.README_035, encoding='utf-8')
    if newer('0.1.25'):
        readme.write_text(readme.read_text(encoding='utf-8') + p36.README_036, encoding='utf-8')
    if newer('0.1.26'):
        readme.write_text(readme.read_text(encoding='utf-8') + p37.README_037, encoding='utf-8')
    if newer('0.1.27'):
        readme.write_text(readme.read_text(encoding='utf-8') + p38.README_038, encoding='utf-8')
    if newer('0.1.28'):
        readme.write_text(readme.read_text(encoding='utf-8') + p39.README_039, encoding='utf-8')
    # 7b. цепочка предыдущих выпусков восстанавливается из опубликованных архивов
    if newer('0.1.7'):
        for prev in ('0.1.4', '0.1.5', '0.1.6', '0.1.7', '0.1.8', '0.1.9', '0.1.10', '0.1.11', '0.1.12', '0.1.13', '0.1.14', '0.1.15', '0.1.16', '0.1.17', '0.1.18', '0.1.19', '0.1.20', '0.1.21', '0.1.22', '0.1.23', '0.1.24', '0.1.25', '0.1.26', '0.1.27', '0.1.28'):
            target_prev = tree / 'releases' / prev
            if target_prev.is_dir():
                continue
            archive = ROOT.parent / f'release-{prev}' / f'{root_name}-{prev}{suffix}.zip'
            if not archive.is_file():
                continue
            prefix = f'AgentContractLab/releases/{prev}/'
            with zipfile.ZipFile(archive) as z:
                for name in z.namelist():
                    if name.startswith(prefix) and not name.endswith('/'):
                        target_file = target_prev / name[len(prefix):]
                        target_file.parent.mkdir(parents=True, exist_ok=True)
                        target_file.write_bytes(z.read(name))
            assert (target_prev / 'manifest.json').is_file(), 'цепочка: нет манифеста ' + prev

    sums = []
    for path in sorted(p for p in tree.rglob('*') if p.is_file()):
        rel = path.relative_to(tree).as_posix()
        if rel == 'SHA256SUMS':
            continue
        sums.append(f'{sha(path.read_bytes())}  {rel}\n')
    (tree / 'SHA256SUMS').write_text(''.join(sums), encoding='utf-8')

    # 8. архив
    name = f'{root_name}-{VERSION}{suffix}.zip'
    target = ROOT / name
    if target.exists():
        target.unlink()
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as z:
        for path in sorted(p for p in out.rglob('*') if p.is_file()):
            z.write(path, path.relative_to(out).as_posix())
    print(json.dumps({'line': args.line, 'totals': totals, 'members': len(sums) + 1,
                      'zip': name, 'bytes': target.stat().st_size, 'sha256': sha(target.read_bytes())},
                     ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
