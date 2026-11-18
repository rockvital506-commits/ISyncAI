#!/usr/bin/env python3
"""Agent Contract Kit 0.1.0. Offline, data-only package format; standard library.

Reads never create files. A write requires an exact, project-bound review ticket.
Nothing in this module is imported from the managed project or from a release.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import unicodedata
import uuid
from dataclasses import dataclass, field

VERSION = '0.1.4'
PREFIX = '.agent-contract/'
BASE = PREFIX + 'base/'
STATE = PREFIX + 'project/state.json'
CHECKS = PREFIX + 'project/checks.json'
LOCAL = PREFIX + 'local/'
OPS = LOCAL + 'ops/'
ENTRY = 'AGENTS.md'
DATA = ('START.md', 'PROTOCOL.md', 'schema.json', 'rules.json', 'entry.txt')
FILES = ('manifest.json', *DATA)
TARGETS = frozenset((ENTRY, STATE, CHECKS, *(BASE + n for n in FILES)))
MAX_BYTES = 2 * 1024 * 1024
TYPES = ('contract', 'rule', 'constraint', 'protocol', 'preference')
TRANSITIONS = {'draft': ['active', 'revoked'], 'active': ['suspended', 'revoked'],
               'suspended': ['active', 'revoked'], 'revoked': []}
ENTRY_KEYS = 'id kind contract title state scope text basis criterion key value revision updated_at reason'
SEV = re.compile(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z')
ID = re.compile(r'[BP]-[1-9][0-9]{0,11}\Z')
HEX = re.compile(r'[0-9a-f]{64}\Z')
TX = re.compile(r'[0-9a-f]{32}\Z')
ENV_KEYS = 'os editor editor_version extension extension_version mode model profile permissions'
NATIVE_HINTS = ('.github/copilot-instructions.md', '.github/instructions', 'kilo.jsonc', '.kilocode/rules',
                'CLAUDE.md', '.claude/CLAUDE.md', '.cursor/rules', 'GEMINI.md')


class Refusal(Exception):
    def __init__(self, code, message, details=None):
        super().__init__(message)
        self.code, self.details = code, details


def need(ok, code, message, details=None):
    if not ok:
        raise Refusal(code, message, details)


def exact(obj, required, optional=''):
    need(isinstance(obj, dict), 'format', 'Ожидается объект JSON.')
    required, optional = set(required.split()), set(optional.split())
    missing, unknown = required - obj.keys(), obj.keys() - required - optional
    need(not (missing or unknown), 'fields', 'Поля не соответствуют формату. Запись запрещена.',
         {'missing': sorted(missing), 'unknown': sorted(unknown)})


def string(s, field_name='text', maximum=16384):
    need(type(s) is str and 0 < len(s) <= maximum and s.strip() and '\x00' not in s,
         'field', f'Нужно непустое текстовое поле: {field_name}.')
    return s


def integer(n, low=0):
    return type(n) is int and low <= n <= 10**12


def digest(b):
    return None if b is None else hashlib.sha256(b).hexdigest()


def encode(obj):
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf-8')


def parse(b):
    def unique(pairs):
        obj = {}
        for name, value in pairs:
            need(name not in obj, 'duplicate_key', 'Повторяющееся имя поля JSON.', {'field': name})
            obj[name] = value
        return obj
    def reject(_):
        raise Refusal('json', 'Нечисловые константы запрещены.')
    try:
        need(len(b) <= MAX_BYTES, 'limit', 'Слишком большой документ.')
        obj = json.loads(b.decode('utf-8-sig'), object_pairs_hook=unique, parse_constant=reject)
        # Reject unpaired Unicode surrogates rather than failing midway through a write.
        json.dumps(obj, ensure_ascii=False, allow_nan=False).encode('utf-8')
        return obj
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise Refusal('json', 'Неверный JSON или кодировка UTF-8.') from exc


def timestamp():
    return dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def date_ok(s):
    try:
        return type(s) is str and bool(re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ', s)) and bool(dt.datetime.strptime(s, '%Y-%m-%dT%H:%M:%SZ'))
    except ValueError:
        return False


def rel(s, dot=False):
    string(s, 'path', 1024)
    if dot and s == '.':
        return s
    for p in s.split('/'):
        need(p not in ('', '.', '..') and p.lower() not in ('.git', '.isai', '.env') and
             not p.lower().startswith('.env.') and not p.endswith(('.', ' ')) and
             not re.search(r'[\\:"<>|?*\x00-\x1f]', p) and
             not re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])', p.split('.')[0], re.I),
             'path', 'Недопустимый относительный путь.', {'path': s})
    return s


def fscheck(p):
    """Check all existing components, including the selected root. No link traversal."""
    for q in (*reversed(p.parents), p):
        try:
            st = q.lstat()
        except FileNotFoundError:
            break
        isdir = stat.S_ISDIR(st.st_mode)
        need(not stat.S_ISLNK(st.st_mode) and not (getattr(st, 'st_file_attributes', 0) & 0x400),
             'boundary', 'Ссылка или reparse point: операция остановлена.', {'path': str(q)})
        need(isdir or (q == p and stat.S_ISREG(st.st_mode) and st.st_nlink == 1),
             'boundary', 'Необычный файл, hard link или файл вместо каталога.', {'path': str(q)})
    return p


def safe(root, name):
    rel(name, dot=True)
    p = root if name == '.' else root.joinpath(*name.split('/'))
    return fscheck(p)


def labroot(arg):
    spelling = os.fspath(arg)
    need(not spelling.replace(chr(92), '/').startswith('//'), 'root', 'Сетевые пути и пути устройств не поддерживаются.')
    p = Path(arg)
    need(p.is_absolute() and '..' not in p.parts and p != Path(p.anchor), 'root', 'Нужен абсолютный путь к отдельному каталогу, не корень диска.')
    for component in p.parts[1:]:
        rel(component)
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        drive_type = ctypes.windll.kernel32.GetDriveTypeW
        drive_type.argtypes, drive_type.restype = [wintypes.LPCWSTR], wintypes.UINT
        need(drive_type(p.anchor) in (2, 3, 6), 'root', 'Нужен подтверждённый локальный том.')
    fscheck(p)
    need(p.is_dir(), 'root', 'Лаборатория не найдена.')
    return p


def read(root, name, *, required=False):
    p = safe(root, name)
    try:
        with p.open('rb') as f:
            b = f.read(MAX_BYTES + 1)
    except FileNotFoundError:
        need(not required, 'missing', 'Нет необходимого файла.', {'path': name})
        return None
    need(len(b) <= MAX_BYTES, 'limit', 'Файл превышает лимит.', {'path': name})
    return b


def native_hints(root):
    # Closed list, metadata only; never enumerate these directories or open their files.
    result = []
    for name in NATIVE_HINTS:
        try:
            st = safe(root, name).lstat()
        except FileNotFoundError:
            continue
        except Refusal as exc:
            if exc.code != 'boundary':
                raise
            result.append({'path': name, 'kind': 'inaccessible_boundary'})
            continue
        result.append({'path': name, 'kind': 'directory' if stat.S_ISDIR(st.st_mode) else 'file',
                       'size': st.st_size, 'mtime_ns': st.st_mtime_ns})
    return result


def flushdir(p):
    if os.name != 'nt' and hasattr(os, 'O_DIRECTORY'):
        fd = os.open(p, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def mkdirs(p):
    fscheck(p)
    if not p.is_dir():
        mkdirs(p.parent)
        p.mkdir(exist_ok=True)
        fscheck(p)
        flushdir(p.parent)


def put(root, name, data):
    p = safe(root, name)
    if data is None:
        p.unlink()  # caller must have a separately approved deletion in the exact plan
        flushdir(p.parent)
        return
    need(len(data) <= MAX_BYTES, 'limit', 'Результат превышает лимит файла.')
    mkdirs(p.parent)
    fd, tmp = tempfile.mkstemp(prefix='.contract-tmp-', dir=p.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        fscheck(p)
        os.replace(tmp, p)
        flushdir(p.parent)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)  # our own uncommitted staging file only


@contextlib.contextmanager
def writer(root, name=LOCAL + 'writer.lock'):
    p = safe(root, name)
    mkdirs(p.parent)
    with p.open('a+b') as handle:
        handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (ImportError, OSError) as exc:
            raise Refusal('writer_busy', 'Не получена межпроцессная блокировка. Запись запрещена.') from exc
        try:
            yield
        finally:
            if os.name == 'nt':
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def schema_doc():
    return {'format': 'agent-contract-fields', 'schema_version': 1, 'kinds': list(TYPES),
            'fields': ENTRY_KEYS.split(), 'transitions': TRANSITIONS, 'scope': '. or relative subtree',
            'structured_conflict': 'equal non-null key + unequal value in intersecting effective scopes'}


def within(child, parent):
    child, parent = child.casefold(), parent.casefold()
    return parent == '.' or child == parent or child.startswith(parent + '/')


def registry(base, project):
    result = {}
    for prefix, records in [('B', base), ('P', project)]:
        need(type(records) is list and len(records) <= 4096, 'registry', 'Некорректный список записей.')
        for e in records:
            exact(e, ENTRY_KEYS)
            i = string(e['id'], 'id')
            need(ID.fullmatch(i) and i.startswith(prefix + '-') and i not in result, 'id', 'Неверный или повторяющийся ID.', {'id': i})
            need(e['kind'] in TYPES and type(e['state']) is str and e['state'] in TRANSITIONS, 'state', 'Неизвестный вид или состояние записи.')
            rel(e['scope'], dot=True)
            for k in ('title', 'text', 'basis', 'criterion', 'reason'):
                string(e[k], k)
            need(integer(e['revision'], 1) and date_ok(e['updated_at']), 'revision', 'Неверная версия или дата записи.')
            need((e['key'] is None and e['value'] is None) or
                 (type(e['key']) is str and re.fullmatch(r'[a-z][a-z0-9_.-]{0,63}', e['key']) and string(e['value'], 'value', 1024)),
                 'key', 'Ключ сравнения и его строковое значение задаются вместе.')
            if e['kind'] == 'contract':
                need(e['contract'] is None and e['key'] is None, 'parent', 'У контракта нет родителя и ключа сравнения.')
            else:
                need(type(e['contract']) is str, 'parent', 'Запись должна принадлежать контракту.')
            result[i] = e
    for e in result.values():
        if e['contract'] is not None:
            parent = result.get(e['contract'])
            need(parent and parent['kind'] == 'contract' and within(e['scope'], parent['scope']) and
                 not (e['id'].startswith('B-') and not parent['id'].startswith('B-')), 'parent',
                 'Отсутствует контракт или область выходит за его границы.', {'id': e['id'], 'parent': e['contract']})
    return result


def effective(records, target=None):
    if target is not None:
        rel(target, dot=True)
    return [e for e in records.values() if e['kind'] != 'contract' and e['state'] == 'active'
            and records[e['contract']]['state'] == 'active' and (target is None or within(target, e['scope']))]


def contradictions(records):
    groups = {}
    problems = []
    for e in effective(records):
        if e['key'] is None:
            continue
        group = groups.setdefault(e['key'], [])
        for other in group:
            if other['value'] != e['value'] and (within(e['scope'], other['scope']) or within(other['scope'], e['scope'])):
                problems.append([{k: x[k] for k in ('id', 'key', 'value', 'scope', 'text')} for x in (other, e)])
                if len(problems) >= 32:
                    return problems
        group.append(e)
    return problems


def manifest_check(raw):
    m = parse(raw)
    exact(m, 'format schema_version base_version origin adapter_version files')
    need(m['format'] == 'agent-contract-release' and integer(m['schema_version'], 1) and m['schema_version'] == 1,
         'schema', 'Неподдерживаемая схема выпуска: только чтение.')
    need(SEV.fullmatch(string(m['base_version'], 'version', 32)) and integer(m['adapter_version'], 1), 'version', 'Неверная версия.')
    string(m['origin'], 'origin')
    need(type(m['files']) is dict and set(m['files']) == set(DATA) and
         all(HEX.fullmatch(string(h, 'sha256', 64)) for h in m['files'].values()), 'manifest', 'Состав выпуска не соответствует разрешённому списку.')
    return m


def base_check(files):
    need(encode(parse(files['schema.json'])) == encode(schema_doc()), 'schema', 'Неизвестное описание схемы. Интерпретация запрещена.')
    obj = parse(files['rules.json'])
    exact(obj, 'schema_version entries')
    need(type(obj['schema_version']) is int and obj['schema_version'] == 1, 'schema', 'Неизвестная схема базовых записей.')
    records = registry(obj['entries'], [])
    issues = contradictions(records)
    need(not issues, 'conflict', 'Противоречивые активные базовые правила.', issues)
    for name in ('START.md', 'PROTOCOL.md', 'entry.txt'):
        try:
            text = files[name].decode('utf-8')
        except UnicodeError as exc:
            raise Refusal('encoding', 'Требуется UTF-8.', {'path': name}) from exc
        need(bool(text.strip()) and '\x00' not in text, 'base_text', 'Пустой или бинарный документ базы.')
    return obj['entries']


def package(lab, folder, pin):
    rel(folder)
    need(re.fullmatch(r'releases/(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', folder), 'package_path', 'Используйте локальный releases/<версия>.')
    root = safe(lab, folder)
    raw = read(root, 'manifest.json', required=True)
    need(type(pin) is str and HEX.fullmatch(pin) and digest(raw) == pin, 'trust', 'Отпечаток не совпадает с отдельно одобренным выпуском.')
    m = manifest_check(raw)
    need('releases/' + m['base_version'] == folder, 'version', 'Имя каталога и версия выпуска различаются.')
    files = {'manifest.json': raw}
    for name in DATA:
        b = read(root, name, required=True)
        need(digest(b) == m['files'][name], 'integrity', 'Содержимое не совпадает с отпечатком выпуска.', {'path': name})
        files[name] = b
    base_check(files)
    inspect_links(files)
    return files, m


def baseline(m, files):
    return {'version': m['base_version'], 'pin': digest(files['manifest.json']), 'origin': m['origin'],
            'installed': {name: digest(files[name]) for name in DATA}}


def check_state(s):
    need(isinstance(s, dict) and type(s.get('schema_version')) is int and s['schema_version'] == 1, 'schema', 'Схема проекта неизвестна или требует отдельной миграции.')
    exact(s, 'schema_version revision next_id entries decisions base adapter retired')
    need(integer(s['revision']) and integer(s['next_id'], 1) and type(s['retired']) is bool, 'state', 'Неверное состояние проекта.')
    exact(s['base'], 'version pin origin installed')
    need(SEV.fullmatch(string(s['base']['version'], 'version', 32)) and HEX.fullmatch(string(s['base']['pin'])), 'version', 'Неверная привязка базы.')
    string(s['base']['origin'], 'origin')
    hashes = s['base']['installed']
    need(isinstance(hashes, dict) and set(hashes) == set(DATA) and all(HEX.fullmatch(string(h)) for h in hashes.values()), 'integrity', 'Неверные отпечатки установки.')
    if s['adapter'] is not None:
        exact(s['adapter'], 'path version sha256')
        need(s['adapter']['path'] == ENTRY and integer(s['adapter']['version'], 1) and HEX.fullmatch(string(s['adapter']['sha256'])), 'adapter', 'Неверная запись адаптера.')
    need(type(s['entries']) is list and type(s['decisions']) is list and len(s['decisions']) == s['revision'], 'history', 'Разрыв в истории ревизий.')
    for n, d in enumerate(s['decisions'], 1):
        exact(d, 'revision at op reason subject')
        need(integer(d['revision'], 1) and d['revision'] == n and date_ok(d['at']), 'history', 'Неверная ревизия решения.')
        for k in ('op', 'reason', 'subject'):
            string(d[k], k)
    for e in s['entries']:
        need(type(e) is dict and ID.fullmatch(string(e.get('id'), 'id')) and int(e['id'].split('-')[1]) < s['next_id'], 'id', 'Нарушен счётчик ID.')


def check_results(raw):
    data = parse(raw)
    exact(data, 'schema_version checks')
    need(type(data['schema_version']) is int and data['schema_version'] == 1 and type(data['checks']) is list, 'schema', 'Неизвестный формат проверок.')
    for item in data['checks']:
        exact(item, 'at revision base_version adapter_version observation')
        need(date_ok(item['at']) and integer(item['revision']) and SEV.fullmatch(string(item['base_version'])) and
             (item['adapter_version'] is None or integer(item['adapter_version'], 1)), 'check', 'Некорректный контекст проверки.')
        observation(item['observation'])
    return data


def observation(o):
    exact(o, 'case level conditions expected actual status evidence limits environment')
    need(o['status'] in ('pass', 'fail', 'not run', 'inconclusive') and integer(o['level'], 1) and o['level'] <= 5, 'check', 'Неверный статус или уровень наблюдения.')
    for k in ('case', 'conditions', 'expected', 'limits'):
        string(o[k], k)
    for k in ('actual', 'evidence'):
        need(type(o[k]) is str and len(o[k]) <= 16384, 'check', 'Ожидается краткая запись наблюдения.')
        if o['status'] in ('pass', 'fail'):
            string(o[k], k)
    exact(o['environment'], ENV_KEYS)
    for k in ENV_KEYS.split():
        string(o['environment'][k], k)


# --- 0.1.4: смысловая тождественность наблюдений -----------------------------------
# Допуск измерен на замороженном корпусе (исследование И-020, 112 пар): критические поля и факты
# совпадают точно, смысловые фразы совпадают как набор признаков, а свободный текст может отличаться
# не более чем одним содержательным словом на поле и только если это слово совпадает посимвольно
# не менее чем на 85 %. Добавленное слово — уже другое наблюдение, даже если это «прогон повторён».
_TEXT_FIELDS = ('actual', 'evidence', 'limits', 'conditions')
_CRITICAL = ('case', 'level', 'status', 'expected', 'environment')
_GUARDS = ('не ', 'нет ', 'без ', 'только ', 'исключительно ', 'по памяти', 'со слов', 'не открывался',
           'не проверял', 'предполож', 'возможно', 'вероятно', 'кажется', 'похоже')
_PUNCT = re.compile(r'[^\w\s]+', re.UNICODE)
_SPACE = re.compile(r'\s+')
_WORD = re.compile(r'\w+', re.UNICODE)
_IDENT = re.compile(r'[A-Za-z_][A-Za-z0-9_.]*\d*')
_NUMBER = re.compile(r'\d+')
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


def decision(s, op, at, reason, subject):
    s['revision'] += 1
    s['decisions'].append({'revision': s['revision'], 'op': op, 'at': at, 'reason': string(reason, 'reason'), 'subject': subject})


@dataclass
class Review:
    root: Path
    request: dict
    at: str
    seen: dict = field(default_factory=dict)
    after: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)
    hints: list | None = None

    def observe(self, path, required=False):
        if path not in self.seen:
            self.seen[path] = read(self.root, path)
        value = self.seen[path]
        need(not required or value is not None, 'missing', 'Отсутствует необходимый файл.', {'path': path})
        return value

    def change(self, path, data):
        need(path in TARGETS, 'boundary', 'Запись не входит в закрытый список.')
        need(data is None or len(data) <= MAX_BYTES, 'limit', 'Результат слишком велик.')
        if data != self.observe(path):
            self.after[path] = data

    def fingerprint(self, extra=None):
        return digest(encode({'format': VERSION, 'root': str(self.root), 'at': self.at, 'request': self.request,
                              'before': {p: digest(b) for p, b in self.seen.items()},
                              'after': {p: digest(b) for p, b in self.after.items()}, 'entry_metadata': self.hints, 'extra': extra}))

    def describe(self, extra=None):
        items = []
        for path, data in self.after.items():
            old = self.seen[path]
            diff = ''.join(difflib.unified_diff((old or b'').decode('utf-8-sig').splitlines(True),
                        (data or b'').decode('utf-8-sig').splitlines(True), fromfile='до/'+path, tofile='после/'+path))
            items.append({'path': path, 'before': digest(old), 'after': digest(data), 'diff': diff})
        return {'ticket': {'at': self.at, 'digest': self.fingerprint(extra)}, 'changes': items, 'notes': self.notes,
                'request': self.request, 'writes': False}


def inspect_links(files):
    # Deliberately small grammar: inline relative Markdown links in shipped guides.
    # Targets are matched against the format, not followed on the filesystem.
    for name in ('START.md', 'PROTOCOL.md', 'entry.txt'):
        targets = []
        fenced = False
        for line in files[name].decode('utf-8').splitlines():
            if line.lstrip().startswith('```'):
                fenced = not fenced
            elif not fenced:
                targets.extend(re.findall(r'\[[^\]]*\]\(([^)]+)\)', line))
        allowed = {BASE + f for f in FILES} if name == 'entry.txt' else set(FILES) | {'../project/state.json', '../project/checks.json'}
        for dest in targets:
            need(dest.split('#', 1)[0] in allowed, 'link', 'Неизвестная цель внутренней ссылки.', {'file': name, 'target': dest})
        if name == 'entry.txt':
            need(BASE + 'START.md' in targets, 'link', 'Адаптер не ссылается на стартовый файл.')


def read_project(p, state=None, *, allow_drift=False, allow_conflict=False):
    s = parse(p.observe(STATE, True)) if state is None else state
    check_state(s)
    files = {n: p.observe(BASE + n, True) for n in FILES}
    m = manifest_check(files['manifest.json'])
    need(digest(files['manifest.json']) == s['base']['pin'] and m['base_version'] == s['base']['version'], 'trust', 'Установленный манифест не совпадает с одобренным.')
    drift = [n for n in DATA if digest(files[n]) != s['base']['installed'][n]]
    need(not drift or allow_drift, 'drift', 'Обнаружены несогласованные локальные изменения базы.', drift)
    base = base_check(files)
    inspect_links(files)
    recs = registry(base, s['entries'])
    issues = contradictions(recs)
    need(not issues or allow_conflict, 'conflict', 'Конфликт действующих правил.', issues)
    checks = check_results(p.observe(CHECKS, True))
    return s, files, m, recs, checks, drift, issues


def merge_base(old, local, new, choices):
    """3 inputs, never fall back to a guessed ancestor. Rules merged by ID.

    A divergent edit of one record, even on different fields, requires a choice.
    Missing records are distinct from present records. No conflict markers written.
    """
    need(type(choices) is dict and all(v in ('local', 'incoming') for v in choices.values()), 'resolutions', 'Разрешения: local или incoming.')
    used, unresolved = set(), []
    def one(key, a, b, c):
        if b == c or a == c:
            return b
        if a == b:
            return c
        if key in choices:
            used.add(key)
            return b if choices[key] == 'local' else c
        def printable(v):
            return v.decode('utf-8') if isinstance(v, bytes) else v
        unresolved.append({'key': key, 'original': printable(a), 'local': printable(b), 'incoming': printable(c)})
        return b
    out = {'manifest.json': new['manifest.json']}
    for n in DATA:
        if n == 'rules.json' and local[n] != old[n] and new[n] != old[n] and local[n] != new[n]:
            sets = [{e['id']: e for e in parse(b[n])['entries']} for b in (old, local, new)]
            merged = []
            for i in sorted(set.union(*(set(s) for s in sets))):
                record = one(n + ':' + i, *(s.get(i) for s in sets))
                if record is not None:
                    merged.append(record)
            out[n] = encode({'schema_version': 1, 'entries': merged})
        else:
            out[n] = one(n, old[n], local[n], new[n])
    need(not unresolved, 'merge_conflict', 'Нужен выбор по каждому конфликту.', unresolved)
    need(set(choices) == used, 'resolutions', 'Выбор относится к отсутствующему конфликту; перепроверьте план.')
    base_check(out)
    inspect_links(out)
    return out


def legacy_zero(s):
    """Supported interchange fixture, not a claim about a previously shipped product."""
    exact(s, 'schema_version project_revision next_id entries decisions base adapter retired')
    need(type(s['schema_version']) is int and s['schema_version'] == 0 and type(s['entries']) is list,
         'schema', 'Поддерживается только явно определённый обменный формат 0 → 1.')
    s['schema_version'], s['revision'] = 1, s.pop('project_revision')
    for e in s['entries']:
        need(type(e) is dict and 'status' in e and 'state' not in e, 'migration', 'Неоднозначное преобразование status → state.')
        e['state'] = e.pop('status')
    check_state(s)
    return s


def mutate_entry(s, r, at):
    op = r['op']
    editable = 'title scope text basis criterion key value'
    if op == 'create':
        exact(r, 'op kind title scope text basis criterion reason', 'contract state key value')
        i = 'P-' + str(s['next_id'])
        e = {k: r.get(k) for k in editable.split()}
        e.update(id=i, kind=r['kind'], contract=r.get('contract'), state=r.get('state', 'draft'), revision=1, updated_at=at, reason=string(r['reason']))
        need(e['state'] in ('draft', 'active'), 'transition', 'Новая запись должна быть draft или active.')
        s['entries'].append(e)
        s['next_id'] += 1
    else:
        exact(r, {'edit': 'op id fields reason', 'transition': 'op id to reason', 'purge': 'op id reason allow_delete'}[op])
        i = string(r['id'], 'id')
        e = next((x for x in s['entries'] if x['id'] == i), None)
        need(e is not None, 'id', 'Изменять можно только существующую проектную запись.', {'id': i})
        if op == 'edit':
            exact(r['fields'], '', editable)
            need(e['state'] != 'revoked' and r['fields'], 'edit', 'Отменённая запись или пустое изменение.')
            if all(e[k] == v for k, v in r['fields'].items()):
                return
            e.update(r['fields'])
        elif op == 'transition':
            need(r['to'] in TRANSITIONS[e['state']], 'transition', 'Переход состояния не разрешён.', {'from': e['state'], 'to': r['to']})
            e['state'] = r['to']
        else:
            need(e['state'] == 'revoked' and r['allow_delete'] is True, 'delete', 'Удаление только после отмены и отдельного согласия.')
            need(not any(x['contract'] == i for x in s['entries']), 'parent', 'Есть дочерние записи. Каскадное удаление запрещено.')
            s['entries'].remove(e)
        e['revision'] += 1
        e['updated_at'], e['reason'] = at, string(r['reason'])
    decision(s, op, at, r['reason'], i)


def safe_target(lab, project):
    root = safe(lab, rel(project))
    need(root.is_dir() and project.split('/')[0].casefold() not in ('releases', 'kit') and
         all(part.casefold() != '.agent-contract' for part in project.split('/')),
         'root', 'Нужна отдельная существующая папка проекта, не kit/releases/служебный каталог.')
    return root


def install_space(root):
    # A failed/restored first installation leaves its own lock and journals.
    # It must be possible to retry without cleaning or adopting other files.
    folder = safe(root, '.agent-contract')
    if not folder.exists():
        return
    need(folder.is_dir(), 'occupied', 'Служебное имя занято файлом.')
    for item in folder.iterdir():
        need(item.name in ('base', 'project', 'local'), 'occupied', 'Неизвестный объект в служебном каталоге.')
        path = safe(root, PREFIX + item.name)
        need(path.is_dir(), 'occupied', 'Служебный каталог занят файлом.')
        if item.name == 'local':
            need(all(x.name in ('writer.lock','ops') for x in path.iterdir()), 'occupied', 'Неизвестные локальные данные.')
        else:
            need(not any(path.iterdir()), 'occupied', 'Не принимаем существующие данные под управление.')


def plan(lab, project, r, at=None):
    root = safe_target(lab, project)
    p = Review(root, r, timestamp() if at is None else at)
    need(date_ok(p.at), 'time', 'Некорректное время билета.')
    need(type(r) is dict and type(r.get('op')) is str, 'request', 'Нужно указать op.')
    op = r['op']
    need(not pending(root), 'pending', 'Есть незавершённая операция. Сначала диагностика восстановления.')
    if op == 'install':
        exact(r, 'op package pin')
        files, m = package(lab, r['package'], r['pin'])
        inspect_links(files)
        for path in TARGETS - {ENTRY}:
            need(p.observe(path) is None, 'occupied', 'Целевой файл уже существует.', {'path': path})
        # Unknown data in an existing control folder is never adopted or overwritten.
        install_space(root)
        for name, data in files.items():
            p.change(BASE + name, data)
        s = {'schema_version': 1, 'revision': 0, 'next_id': 1, 'entries': [], 'decisions': [],
             'base': baseline(m, files), 'adapter': None, 'retired': False}
        decision(s, op, p.at, 'Установлен отдельно одобренный выпуск.', m['base_version'])
        p.change(STATE, encode(s))
        p.change(CHECKS, encode({'schema_version': 1, 'checks': []}))
        p.notes.append('Профиль пуст. Нативный адаптер не подключён. Установленные расширения не проверялись.')
        return p
    migrated = legacy_zero(parse(p.observe(STATE, True))) if op == 'migrate' else None
    s, local, lm, recs, checks, drift, issues = read_project(p, migrated, allow_drift=op=='update', allow_conflict=True)
    need(not s['retired'] or op in ('record_check',), 'retired', 'Контракт выведен из эксплуатации. Данные сохранены.')
    base = parse(local['rules.json'])['entries']
    if op in ('create', 'edit', 'transition', 'purge'):
        mutate_entry(s, r, p.at)
    elif op == 'migrate':
        exact(r, 'op reason')
        decision(s, op, p.at, r['reason'], '0 -> 1')
        p.notes.append('Только переименование project_revision → revision и status → state; неизвестные поля не удаляются.')
    elif op in ('connect', 'disconnect', 'retire'):
        exact(r, 'op', 'ack_existing' if op == 'connect' else 'allow_delete')
        adapter = s['adapter']
        if op == 'connect':
            if adapter is not None:
                current = p.observe(ENTRY)
                need(digest(current) == adapter['sha256'] == digest(local['entry.txt']), 'adapter_drift', 'Принадлежащий контракту вход изменён или отсутствует.')
            else:
                need(not safe(root, ENTRY).exists(), 'foreign_entry', 'Вход уже занят. Он не будет принят под управление. Доступен ручной вход через START.md.')
                p.hints = native_hints(root)
                paths = [f['path'] for f in p.hints]
                need(r.get('ack_existing', []) == paths, 'existing_sources', 'Известны другие возможные источники инструкций. Присутствие не доказывает конфликт. Для совместного входа укажите перечисленные path в массиве ack_existing в данном порядке; иначе используйте ручное чтение.', p.hints)
                if paths:
                    p.notes.append({'existing_sources_not_read_or_modified': p.hints})
                p.change(ENTRY, local['entry.txt'])
                s['adapter'] = {'path': ENTRY, 'version': lm['adapter_version'], 'sha256': digest(local['entry.txt'])}
                decision(s, op, p.at, 'Создан вход; обнаружение и чтение не проверены.', ENTRY)
        else:
            if adapter is not None:
                need(r.get('allow_delete') is True, 'delete', 'Для удаления входа требуется явное allow_delete.')
                need(digest(p.observe(ENTRY)) == adapter['sha256'], 'adapter_drift', 'Чужую правку или отсутствующий вход не перезаписываем.')
                p.change(ENTRY, None)
                s['adapter'] = None
            if op == 'retire':
                s['retired'] = True
            if adapter is not None or op == 'retire':
                decision(s, op, p.at, 'Отключение без очистки пользовательских данных.', ENTRY)
    elif op == 'update':
        exact(r, 'op package pin', 'resolutions')
        try:
            old, om = package(lab, 'releases/' + s['base']['version'], s['base']['pin'])
        except (OSError, Refusal) as exc:
            raise Refusal('no_ancestor', 'Исходный одобренный выпуск недоступен. Трёхстороннее сравнение не выполнено.') from exc
        new, nm = package(lab, r['package'], r['pin'])
        def ver(m): return tuple(map(int, m['base_version'].split('.')))
        need(ver(nm) >= ver(om), 'downgrade', 'Автоматическое понижение запрещено.')
        need(ver(nm) != ver(om) or r['pin'] == s['base']['pin'], 'version_collision', 'Одна версия обозначает два разных выпуска.')
        merged = merge_base(old, local, new, r.get('resolutions', {}))
        base = parse(merged['rules.json'])['entries']
        for n in FILES:
            p.change(BASE+n, merged[n])
        binding = baseline(nm, merged)
        if s['adapter'] is not None:
            need(digest(p.observe(ENTRY)) == s['adapter']['sha256'], 'adapter_drift', 'Вход изменён вне контракта: остановка обновления.')
            p.change(ENTRY, merged['entry.txt'])
            s['adapter'].update(version=nm['adapter_version'], sha256=digest(merged['entry.txt']))
        if binding != s['base'] or p.after:
            s['base'] = binding
            decision(s, op, p.at, 'Сверены исходная, локальная и предлагаемая версии.', nm['base_version'])
        p.notes.extend(['Нет исполнения кода из выпуска. Повторить структурные проверки и новый сеанс каждого агента.',
                        {'unapproved_drift_before': drift, 'local_differences_after': [n for n in DATA if merged[n] != new[n]]}])
    elif op == 'record_check':
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
            p.change(CHECKS, encode(checks))
    else:
        raise Refusal('op', 'Операция не поддерживается.')
    problems = contradictions(registry(base, s['entries']))
    need(not problems or op in ('record_check','retire','disconnect'), 'conflict',
         'Пересечение действующих требований. Нужен выбор владельца; молчаливого приоритета нет.', problems)
    check_state(s)
    # An unchanged state stays byte-identical (also if formatted by the owner).
    if s != parse(p.seen[STATE]):
        p.change(STATE, encode(s))
    return p


def journal_name(tx):
    need(type(tx) is str and TX.fullmatch(tx), 'transaction', 'Неверный ID операции.')
    return OPS + tx + '/plan.json'


def journal(root, tx):
    j = parse(read(root, journal_name(tx), required=True))
    exact(j, 'format tx root status ticket files op at')
    string(j['op'], 'op')
    need(date_ok(j['at']), 'journal', 'Неверное время операции.')
    need(type(j['format']) is int and j['format'] == 1 and j['tx'] == tx and j['root'] == str(root)
         and j['status'] in ('pending', 'committed', 'restored') and HEX.fullmatch(string(j['ticket'])), 'journal', 'Неподдерживаемый журнал.')
    need(type(j['files']) is dict and 0 < len(j['files']) <= len(TARGETS), 'journal', 'Неверный список файлов операции.')
    for path, h in j['files'].items():
        need(path in TARGETS, 'journal', 'Журнал указывает за пределы управляемых файлов.')
        exact(h, 'before after')
        need(h['before'] != h['after'] and all(x is None or (type(x) is str and HEX.fullmatch(x)) for x in h.values()), 'journal', 'Неверный отпечаток в журнале.')
    return j


def pending(root):
    folder = safe(root, OPS.rstrip('/'))
    if not folder.exists():
        return []
    result = []
    for d in sorted(folder.iterdir()):
        need(TX.fullmatch(d.name), 'journal', 'Неизвестный объект в каталоге журналов. Ничего не удалено.')
        marker = safe(root, journal_name(d.name))
        # A preparation without a published marker cannot have modified a destination.
        if marker.exists() and journal(root, d.name)['status'] == 'pending':
            result.append(d.name)
    return result


def confirm(ticket, p, extra=None):
    exact(ticket, 'at digest')
    need(ticket['at'] == p.at and ticket['digest'] == p.fingerprint(extra), 'stale_plan',
         'Билет не совпадает с точным планом. Получите новое сравнение; запись не выполнена.')


def unchanged(p):
    if p.hints is not None:
        need(native_hints(p.root) == p.hints, 'stale_plan', 'Изменились метаданные источников инструкций.')
    for path, value in p.seen.items():
        need(read(p.root, path) == value, 'stale_plan', 'Файл изменён после просмотра плана.', {'path': path})


def apply(lab, project, r, ticket, *, _after_write=None):
    exact(ticket, 'at digest')
    p = plan(lab, project, r, ticket['at'])
    confirm(ticket, p)
    if not p.after:
        return {'outcome': 'no_change', 'files': []}
    with writer(p.root):
        need(not pending(p.root), 'pending', 'Требуется восстановление.')
        unchanged(p)
        if r['op'] == 'install':
            # Lock creation itself introduces local/. Do not adopt a concurrently added control tree.
            install_space(p.root)
        tx = uuid.uuid4().hex
        j = {'format': 1, 'tx': tx, 'root': str(p.root), 'status': 'pending', 'ticket': ticket['digest'], 'files': {}, 'op': r['op'], 'at': p.at}
        for path, new in p.after.items():
            old = p.seen[path]
            if old is not None:
                backup = OPS + tx + '/before/' + path
                put(p.root, backup, old)
                need(read(p.root, backup, required=True) == old, 'backup', 'Не удалось подтвердить резервную копию.')
            j['files'][path] = {'before': digest(old), 'after': digest(new)}
        put(p.root, journal_name(tx), encode(j))  # durable intent before first managed write
        for idx, (path, new) in enumerate(p.after.items(), 1):
            need(read(p.root, path) == p.seen[path], 'stale_plan', 'Постороннее изменение; операция оставлена в журнале.', {'path': path})
            put(p.root, path, new)
            if _after_write is not None:  # in-process reliability tests only, never provided by a package/request
                _after_write(idx)
        need(all(read(p.root, path) == b for path, b in p.after.items()), 'postcondition', 'Не подтверждены конечные байты. Операция остаётся незавершённой.')
        j['status'] = 'committed'
        put(p.root, journal_name(tx), encode(j))
        return {'outcome': 'committed', 'transaction': tx, 'files': list(p.after)}


def recovery_plan(lab, project, r, at=None):
    exact(r, 'op tx', 'allow_delete')
    need(r['op'] in ('restore', 'undo'), 'op', 'Ожидается restore или undo.')
    root = safe_target(lab, project)
    p = Review(root, r, at if at is not None else timestamp())
    need(date_ok(p.at), 'time', 'Неверная дата.')
    tx = r['tx']
    j = journal(root, tx)
    need(j['status'] in (('committed', 'restored') if r['op']=='undo' else ('pending', 'restored')), 'journal', 'Для прерывания: restore; для явного отката завершённой операции: undo.')
    if r['op'] == 'undo':
        need(not pending(root), 'pending', 'Сначала завершите восстановление прерванной операции.')
    classes = {}
    if j['status'] == 'restored':
        return p, j, classes
    for path, h in j['files'].items():
        actual = digest(p.observe(path))
        classes[path] = 'before' if actual == h['before'] else 'after' if actual == h['after'] else 'foreign'
        if classes[path] == 'after':
            if h['before'] is None:
                if r.get('allow_delete') is not True:
                    classes[path] = 'delete_requires_consent'
                    continue
                old = None
            else:
                old = read(root, OPS + tx + '/before/' + path, required=True)
                need(digest(old) == h['before'], 'backup', 'Повреждена резервная копия. Запись запрещена.', {'path': path})
            p.change(path, old)
    if j['status'] == 'committed':
        need(all(v == 'after' for v in classes.values()), 'undo_guard', 'Откат завершённой операции требует точного постсостояния и согласия на каждое удаление.', classes)
    p.notes.append({'classification': classes, 'foreign_files_are_never_overwritten': True})
    return p, j, classes


def restore(lab, project, r, ticket):
    exact(ticket, 'at digest')
    p, j, classes = recovery_plan(lab, project, r, ticket['at'])
    confirm(ticket, p, j)
    if j['status'] == 'restored':
        return {'outcome': 'no_change', 'files': []}
    with writer(p.root):
        need(journal(p.root, r['tx']) == j, 'stale_plan', 'Журнал изменился.')
        unchanged(p)
        if j['status'] == 'committed':
            need(not pending(p.root), 'pending', 'Есть другая незавершённая операция.')
            j['status'] = 'pending'
            put(p.root, journal_name(r['tx']), encode(j))
        for path, data in p.after.items():
            need(read(p.root, path) == p.seen[path], 'stale_plan', 'Неожиданное изменение при восстановлении.')
            put(p.root, path, data)
        unresolved = [path for path, h in j['files'].items() if digest(read(p.root, path)) != h['before']]
        if not unresolved:
            j['status'] = 'restored'
            put(p.root, journal_name(r['tx']), encode(j))
        return {'outcome': 'partial' if unresolved else 'restored', 'files': list(p.after), 'unresolved': unresolved}


def publish_plan(lab, r, at=None):
    """Publish only an explicit allowlist from kit/base. No template scripts or hooks."""
    exact(r, 'op version origin adapter_version')
    need(r['op'] == 'publish' and SEV.fullmatch(string(r['version'], 'version', 32)) and integer(r['adapter_version'], 1), 'version', 'Неверные параметры публикации.')
    root = safe(lab, 'kit/base')
    data = {n: read(root, n, required=True) for n in DATA}
    base_check(data)
    inspect_links(data)
    m = {'format': 'agent-contract-release', 'schema_version': 1, 'base_version': r['version'],
         'adapter_version': r['adapter_version'], 'origin': string(r['origin'], 'origin'), 'files': {n: digest(b) for n,b in data.items()}}
    raw = encode(m)
    manifest_check(raw)
    dest = safe(lab, 'releases/' + r['version'])
    p = Review(dest, r, at if at is not None else timestamp())
    need(date_ok(p.at), 'time', 'Неверная дата билета.')
    need(not dest.exists(), 'occupied', 'Версия уже существует: не перезаписывается.')
    for n, b in {**data, 'manifest.json': raw}.items():
        p.seen[n], p.after[n] = None, b
    p.notes.append({'release_pin': digest(raw), 'transfer_list': list(FILES)})
    return p


def publish(lab, r, ticket):
    exact(ticket, 'at digest')
    p = publish_plan(lab, r, ticket['at'])
    confirm(ticket, p)
    parent = safe(lab, 'releases')
    mkdirs(parent)
    # Build out of sight of release discovery. No installed consumer is touched on a crash.
    staging = safe(lab, 'releases/.prepare-' + uuid.uuid4().hex)
    staging.mkdir()
    for name, data in p.after.items():
        put(staging, name, data)
        need(read(staging, name) == data, 'postcondition', 'Не подтверждены байты выпуска.')
    # Concurrent publishers of this kit never overwrite an existing release.
    with writer(parent, '.publish.lock'):
        need(not fscheck(p.root).exists(), 'occupied', 'Версия уже опубликована.')
        os.rename(staging, p.root)
        flushdir(parent)
    return {'outcome': 'published', 'package': 'releases/' + r['version'], 'pin': digest(p.after['manifest.json'])}


def available(lab):
    root = safe(lab, 'releases')
    releases = []
    if root.is_dir():
        for d in sorted(root.iterdir()):
            if SEV.fullmatch(d.name):
                raw = read(root, d.name + '/manifest.json', required=True)
                m = manifest_check(raw)
                need(m['base_version'] == d.name, 'version', 'Версия не совпадает с именем каталога.')
                releases.append({'folder': 'releases/' + d.name, 'version': m['base_version'], 'observed_hash': digest(raw), 'trust_verified': False})
    return releases


def dispatch(lab, project, command, payload, target=None):
    if command == 'updates':
        exact(payload, '')
        releases = available(lab)
        installed = None
        if project != '.':
            root = safe_target(lab, project)
            need(not pending(root), 'pending', 'Не определяем версию по частично обновлённому проекту.')
            raw = read(root, STATE)
            if raw is not None:
                state = parse(raw)
                check_state(state)
                installed = state['base']['version']
        for candidate in releases:
            candidate['newer'] = tuple(map(int,candidate['version'].split('.'))) > tuple(map(int,installed.split('.'))) if installed else None
        return {'installed_version': installed, 'local_candidates': releases, 'network': False}
    if command in ('plan', 'apply'):
        if command == 'apply':
            exact(payload, 'request ticket')
            r, ticket = payload['request'], payload['ticket']
        else:
            r, ticket = payload, None
        need(isinstance(r, dict), 'request', 'Нужен объект запроса.')
        if r.get('op') == 'publish':
            return publish_plan(lab, r).describe() if command == 'plan' else publish(lab, r, ticket)
        if r.get('op') in ('restore', 'undo'):
            if command == 'apply':
                return restore(lab, project, r, ticket)
            p, j, _ = recovery_plan(lab, project, r)
            return p.describe(j)
        return plan(lab, project, r).describe() if command == 'plan' else apply(lab, project, r, ticket)
    root = safe_target(lab, project)
    if command == 'session':
        exact(payload, 'kind text')
        need(payload['kind'] in ('temporary', 'proposal', 'hypothesis'), 'intent', 'Ожидается временное указание, предложение или гипотеза.')
        string(payload['text'])
        return {'kind': payload['kind'], 'persisted': False, 'active_rule_created': False}
    exact(payload, '')
    if command == 'inventory':
        return {'native_paths': native_hints(root), 'entry_exists': safe(root, ENTRY).exists(), 'contents_read': False, 'runtime_inferred': False}
    outstanding = pending(root)
    if command == 'operations':
        folder = safe(root, OPS.rstrip('/'))
        records = [journal(root, d.name) for d in sorted(folder.iterdir()) if safe(root, journal_name(d.name)).exists()] if folder.is_dir() else []
        return {'operations': [{k: j[k] for k in ('tx','at','op','status')} for j in records]}
    if command == 'pending':
        return {'pending': outstanding}
    if outstanding and command == 'status':
        return {'health': 'partial', 'pending': outstanding, 'writes': False}
    need(not outstanding, 'pending', 'Сначала диагностика незавершённого изменения.')
    p = Review(root, {}, timestamp())
    if p.observe(STATE) is None and command == 'status':
        exists = safe(root, '.agent-contract').exists()
        return {'health': 'uninitialized_or_residual' if exists else 'absent', 'writes': False}
    s, files, m, recs, checks, drift, issues = read_project(p, allow_drift=True, allow_conflict=True)
    if command == 'status':
        adapter = s['adapter']
        # Never read the contents of an unowned instruction file for automatic attachment.
        exists = safe(root, ENTRY).exists()
        entry = ('absent' if not exists else 'unmanaged') if adapter is None else (
            'created' if digest(read(root, ENTRY)) == adapter['sha256'] else 'drift')
        return {'health': 'attention' if drift or issues or entry == 'drift' else 'retired' if s['retired'] else 'valid',
                'schema_version': 1, 'project_revision': s['revision'], 'base': s['base'], 'entry': entry,
                'adapter_version': (adapter or {}).get('version'), 'unapproved_drift': drift,
                'base_local_edits': [n for n in DATA if digest(files[n]) != m['files'][n]], 'conflicts': issues,
                'observations': checks['checks'], 'runtime_inferred': False}
    if command == 'list':
        need(not drift and not issues, 'ambiguous', 'Нельзя объявить действующим набор с отклонениями или конфликтами.', {'drift': drift, 'conflicts': issues})
        return {'project_revision': s['revision'], 'active': [] if s['retired'] else effective(recs, target),
                'contracts': [e for e in recs.values() if e['kind']=='contract' and e['state']=='active' and not s['retired'] and (target is None or within(target,e['scope']))]}
    if command == 'history':
        return {'decisions': s['decisions']}
    raise Refusal('command', 'Неизвестная команда.')


def main(argv=None):
    cli = argparse.ArgumentParser(description='Контракт проекта • офлайн • без внешних модулей')
    cli.add_argument('--version', action='version', version=VERSION)
    cli.add_argument('--lab', required=True, help='абсолютный путь к отдельному корню лаборатории')
    cli.add_argument('--project', default='.', help='папка проекта относительно лаборатории; обязательна для проектных операций')
    cli.add_argument('--target', help='относительный путь для фильтра list')
    cli.add_argument('command', choices=('status', 'list', 'history', 'updates', 'pending', 'operations', 'inventory', 'session', 'plan', 'apply'))
    args = cli.parse_args(argv)
    try:
        data = parse(sys.stdin.buffer.read(MAX_BYTES+1)) if args.command in ('session', 'plan', 'apply') else {}
        out = dispatch(labroot(args.lab), args.project, args.command, data, args.target)
        code = 2 if out.get('outcome') == 'partial' or out.get('health') in ('partial', 'attention') else 0
    except Refusal as exc:
        out, code = {'error': exc.code, 'message': str(exc), 'details': exc.details}, 2
    except (OSError, ValueError, UnicodeError, RecursionError) as exc:
        out, code = {'error': 'io_or_data', 'message': str(exc), 'next': 'Не считать успешным. Проверьте pending.'}, 2
    sys.stdout.buffer.write(encode(out))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
