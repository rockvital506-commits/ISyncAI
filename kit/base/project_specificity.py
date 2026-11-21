"""Ограниченная классификация одной записи L2: только данные в памяти, без переноса."""
import re
from unicodedata import normalize

from . import schema_v2

ANALYSIS_FORMAT = 1
_MAX_ENTRY_CHARS = 65_536
_MAX_HINTS, _MAX_HINT_CHARS = 32, 128
_CONTEXT_FIELDS = ('project_names', 'machine_names', 'project_paths')
_FIELDS = ('id', 'parent', 'scope', 'title', 'text', 'basis', 'criterion', 'key', 'value')

# Сетевой URI не равен машинному пути. Однобуквенный дисковый префикс не является URI.
_URI = re.compile(r"""(?i)(?<![\w+.-])([a-z][a-z0-9+.-]+)://[^\s<>`'\"]+""")
_PATHS = (
    ('posix_local', re.compile(r'(?<![\w./\\:@$~\-])/(?:home|Users|root|tmp|var|etc|opt|srv|mnt|Volumes|workspace|workspaces)'
                               r'(?=$|/|[^\w./\\-])')),
    ('windows_drive', re.compile(r'(?<![\w./\\:])[A-Za-z]:[\\/]')),
    ('unc_path', re.compile(r"""(?<![\w/\\])\\\\[^\\/\s<>`'\"]+\\[^\\/\s<>`'\"]+""")),
    ('home_path', re.compile(r'(?<![\w./\\:@$~\-])~[\\/]')),
)
_CREDENTIAL = (r'(?:api[-_. ]?key|(?:(?:access|auth|refresh)[-_. ]?)?token|(?:client[-_. ]?)?secret|'
               r'password|passwd|private[-_. ]?key)')
_RHS = r"""(?:"[^"\r\n]*"|'[^'\r\n]*'|`[^`\r\n]*`|[^\s`,;\]\)]+)"""
_ASSIGNMENT = re.compile(rf"""(?<![\w-]){_CREDENTIAL}(?![\w-])["']?[ \t]*[:=][ \t]*({_RHS})""", re.IGNORECASE)
_BEARER = re.compile(rf"""(?<![\w-])authorization["']?[ \t]*:[ \t]*bearer[ \t]+({_RHS})""", re.IGNORECASE)
_CREDENTIAL_KEY = re.compile(rf'(?:^|\.){_CREDENTIAL}$', re.IGNORECASE)
_KEY_HEADER = re.compile(r'-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----')
_VAR = r'[A-Za-z_][A-Za-z0-9_]*'
_REFERENCE = re.compile(rf'(?:<{_VAR}>|\$\{{{_VAR}\}}|\${_VAR}|%{_VAR}%)')


def _valid_entry(entry):
    if (type(entry) is not dict or not 10 <= len(entry) <= 12
            or any(type(k) is not str or len(k) > 16 for k in entry)
            or sum(len(v) for v in entry.values() if type(v) is str) > _MAX_ENTRY_CHARS):
        return False
    try:
        # Нужна форма L2, а не выдуманные документ, родитель, адрес или полномочия.
        schema_v2._entry_shape(entry, 'L2', '')
    except schema_v2.SchemaError:
        return False
    return True


def _fold(text):
    return normalize('NFC', text).casefold()


def _hints(context):
    if (type(context) is not dict or len(context) != len(_CONTEXT_FIELDS)
            or any(type(k) is not str for k in context) or set(context) != set(_CONTEXT_FIELDS)):
        return None
    prepared = {}
    for field in _CONTEXT_FIELDS:
        items = context[field]
        if type(items) is not list or len(items) > _MAX_HINTS:
            return None
        for item in items:
            if (type(item) is not str or not 0 < len(item) <= _MAX_HINT_CHARS
                    or item != item.strip() or not item.isprintable()):
                return None
            if field == 'project_paths':
                try:
                    schema_v2._portable_path(item, '')
                except schema_v2.SchemaError:
                    return None
        prepared[field] = sorted(set(items if field == 'project_paths' else map(_fold, items)))
    return prepared


def _matcher(values, left, right):
    return re.compile(left + '(?:' + '|'.join(map(re.escape, values)) + ')' + right) if values else None


def _paths(text, *, field, prefixes, relative):
    found = set()

    def mask(match):
        if match[1].lower() == 'file':
            found.add('file_uri')
        return ' '

    path_text = _URI.sub(mask, text)
    found.update(code for code, pattern in _PATHS if pattern.search(path_text))
    if field == 'scope':
        known = any(text == p or text.startswith(p + '/') for p in prefixes)
    else:
        known = relative is not None and relative.search(path_text) is not None
    if known:
        found.add('project_prefix')
    return found


def _literal(value):
    value = value.strip()
    if len(value) >= 2 and value[0] in ('"', "'", '`') and value[-1] == value[0]:
        value = value[1:-1].strip()
    return bool(value) and _REFERENCE.fullmatch(value) is None


def _secrets(text, *, labelled):
    if any(_literal(m[1]) for m in _ASSIGNMENT.finditer(text)):
        yield 'credential_assignment'
    if labelled and _literal(text):
        yield 'credential_value'
    if any(_literal(m[1]) for m in _BEARER.finditer(text)):
        yield 'bearer_literal'
    if _KEY_HEADER.search(text):
        yield 'private_key_header'


def _result(outcome, findings, *, code=None):
    result = {'analysis_format': ANALYSIS_FORMAT, 'outcome': outcome, 'findings': findings}
    if code is not None:
        result['code'] = code
    return result


def inspect_entry(entry, *, context):
    """Сообщить только известные признаки, а не дать разрешение на перенос.

    entry — одна явно переданная запись L2; context — три явных списка подсказок.
    Исходные строки, значения совпадений и сведения о среде в ответ не попадают.
    """
    if not _valid_entry(entry):
        return _result('invalid_input', [], code='invalid_entry')
    hints = _hints(context)
    if hints is None:
        return _result('invalid_input', [], code='invalid_context')
    project = _matcher(hints['project_names'], r'(?<![\w-])', r'(?![\w-])')
    machine = _matcher(hints['machine_names'], r'(?<![\w-])', r'(?![\w-])')
    prefixes = hints['project_paths']
    relative = _matcher(prefixes, r'(?<![\w./\\:-])', r'(?=$|/|[^\w./\\-])')
    credential_key = _CREDENTIAL_KEY.search(entry.get('key', '')) is not None
    findings = []
    for field in _FIELDS:
        text = entry.get(field)
        if text is None:
            continue
        found = {('secret', code) for code in _secrets(text, labelled=field == 'value' and credential_key)}
        found.update(('path', code) for code in _paths(text, field=field, prefixes=prefixes, relative=relative))
        if project is not None or machine is not None:
            folded = _fold(text)
            if project is not None and project.search(folded):
                found.add(('project_name', 'known_project'))
            if machine is not None and machine.search(folded):
                found.add(('machine', 'known_machine'))
        findings.extend({'field': field, 'category': category, 'code': code} for category, code in sorted(found))
    outcome = ('possible_secret' if any(f['category'] == 'secret' for f in findings)
               else 'project_specific' if findings else 'no_markers')
    return _result(outcome, findings)
