#!/usr/bin/env python3
"""Выпуск AgentContractKit 0.1.7: адаптер GitHub Copilot / VS Code — инструкции вместо правил, второй вход запрещён.

Итерация И-027. Линия выводится от 0.1.0 теми же правками, что дали 0.1.4–0.1.6, и затем получает
адаптер GitHub Copilot / VS Code: карточку среды с покрытием по поверхностям, обнаружение
инструкций и файлов правил, и отказ на второй вход — запрет на второй реестр как код отказа. Скрипт правит программу, регрессии, справочник и метаданные, прогоняет собственные
испытания комплекта и сквозную имитацию, затем собирает архив.

Запуск: python3 build.py [--line base|edition]
"""
from __future__ import annotations

import argparse
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
REPO = ROOT.parents[1]
DIST = REPO / 'dist'
SOURCE = DIST / 'AgentContractKit-0.1.0.zip'
VERSION = '0.1.7'
PREV_RELEASE = '0.1.6'
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


PASS_TOTAL = 46 if VERSION > '0.1.6' else (42 if VERSION > '0.1.5' else (38 if VERSION > '0.1.4' else 35))


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
    if VERSION > '0.1.5':
        program = tool.read_text(encoding='utf-8')
        assert p16.NATIVE_HINTS_OLD in program
        program = program.replace(p16.NATIVE_HINTS_OLD, p16.NATIVE_HINTS_NEW, 1)
        assert 'class Refusal(Exception):' in program and 'ADAPTERS = {' not in program
        program = program.replace('class Refusal(Exception):', p16.ADAPTERS_BLOCK + 'class Refusal(Exception):', 1)
        marker2 = "    exact(payload, '')\n    if command == 'inventory':"
        assert marker2 in program and 'adapter_unknown' not in program
        program = program.replace(marker2, p16.ADAPTER_COMMAND + marker2, 1)
        tool.write_text(program, encoding='utf-8')
    if VERSION > '0.1.6':
        program = tool.read_text(encoding='utf-8')
        assert p16.NATIVE_HINTS_NEW in program
        program = program.replace(p16.NATIVE_HINTS_NEW, p17.NATIVE_HINTS_NEW, 1)
        assert "ADAPTERS['copilot']" not in program
        assert p17.CONNECT_OLD in program, 'нет места для правки connect'
        program = program.replace(p17.CONNECT_OLD, p17.CONNECT_NEW, 1)
        program = program.rstrip('\n') + '\n\n\n' + p17.COPILOT_BLOCK
        tool.write_text(program, encoding='utf-8')
    if VERSION > '0.1.4':
        program = tool.read_text(encoding='utf-8')
        for old, new in PATCH_015:
            assert old in program, 'нет места для правки тождества: ' + old[:60]
            program = program.replace(old, new, 1)
        assert 'def body(' in program
        tool.write_text(program, encoding='utf-8')

    # 2. регрессии на оба правила
    tests = tree / 'kit/tests/test_contract.py'
    tt = tests.read_text(encoding='utf-8')
    end = '\n\nclass Results(unittest.TextTestResult):'
    assert end in tt and 'test_40_exact_repeat' not in tt
    tt = tt.replace(end, TEST_NEW + end, 1)
    if VERSION > '0.1.4':
        tt = tt.replace(end, TEST_015 + end, 1)
    if VERSION > '0.1.5':
        tt = tt.replace(end, p16.TEST_016 + end, 1)
    if VERSION > '0.1.6':
        tt = tt.replace(end, p17.TEST_017 + end, 1)
    for old, new in TESTS_VERSION_PATCHES:
        assert old in tt, 'нет места для правки версии в регрессиях: ' + old[:60]
        tt = tt.replace(old, new, 1)
    tests.write_text(tt, encoding='utf-8')

    # 3. справочник: новое правило и номер версии
    guide = tree / 'kit/base/PROTOCOL.md'
    g = guide.read_text(encoding='utf-8')
    g = re.sub(r'^# Справочник механизма • 0\.1\.0 / схема 1', f'# Справочник механизма • {VERSION} / схема 1', g, flags=re.M)
    guide.write_text(g.rstrip('\n') + PROTOCOL_PARA, encoding='utf-8')
    if VERSION > '0.1.4':
        guide.write_text(g.rstrip('\n') + PROTOCOL_PARA + PROTOCOL_015, encoding='utf-8')
    if VERSION > '0.1.5':
        guide.write_text(g.rstrip('\n') + PROTOCOL_PARA + PROTOCOL_015 + p16.PROTOCOL_016, encoding='utf-8')
    if VERSION > '0.1.6':
        guide.write_text(g.rstrip('\n') + PROTOCOL_PARA + PROTOCOL_015 + p16.PROTOCOL_016
                         + p17.PROTOCOL_017, encoding='utf-8')

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
    if VERSION > '0.1.4':
        prev_root = ROOT.parent / f'release-{PREV_RELEASE}' / args.line / 'AgentContractLab' / 'releases'
        if prev_root.is_dir():
            for folder in sorted(prev_root.iterdir()):
                target_prev = tree / 'releases' / folder.name
                if folder.is_dir() and folder.name != VERSION and not target_prev.exists():
                    shutil.copytree(folder, target_prev)
        readme.write_text(readme.read_text(encoding='utf-8') + README_015, encoding='utf-8')
    if VERSION > '0.1.5':
        readme.write_text(readme.read_text(encoding='utf-8') + p16.README_016, encoding='utf-8')
    if VERSION > '0.1.6':
        readme.write_text(readme.read_text(encoding='utf-8') + p17.README_017, encoding='utf-8')
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
