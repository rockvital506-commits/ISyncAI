"""Распознать узкую русскую формулировку, не обращаясь к реестрам или исполнителям."""
from dataclasses import dataclass
import re

from .registry_policy import operation_matrix

CARD_FORMAT = 1
_VERBS = {word: op for op, words in {
    'create': ('создай', 'добавь', 'оформи', 'зарегистрируй', 'запиши', 'сделай'),
    'list': ('покажи', 'посмотри'),
    'edit': ('измени', 'отредактируй'),
    'suspend': ('приостанови', 'приостановить'),
    'resume': ('возобнови', 'возобновить'),
    'revoke': ('отмени', 'отменить'),
    'delete': ('удали', 'удалить'),
}.items() for word in words}
_KINDS = {word: kind for kind, words in {
    'contract': ('контракт', 'контракта', 'контракты', 'контрактов'),
    'rule': ('правило', 'правила', 'правил'),
    'constraint': ('ограничение', 'ограничения', 'ограничений'),
    'protocol': ('протокол', 'протокола', 'протоколы', 'протоколов'),
    'preference': ('предпочтение', 'предпочтения', 'предпочтений'),
}.items() for word in words}
# Грамматическая подсказка → (поле, вид значения). Константы обозначают явно названные области.
_CLAUSES = {
    **{('в', area.lower()): ('target', area) for area in ('L0', 'L1', 'L2')},
    ('в', 'проект'): ('target', 'L2'),
    ('в', 'проекте'): ('target', 'L2'),
    ('в', 'системном', 'слое'): ('target', 'L0'),
    ('в', 'профиль'): ('profile', 'reference'),
    ('в', 'профиле'): ('profile', 'reference'),
    ('по', 'контракту'): ('contract', 'reference'),
    ('под', 'контрактом'): ('contract', 'reference'),
    ('для', 'контракта'): ('contract', 'reference'),
    ('в', 'области'): ('scope', 'literal'),
    ('область',): ('scope', 'literal'),
    ('назови',): ('title', 'literal'),
    ('название',): ('title', 'literal'),
    ('с', 'названием'): ('title', 'literal'),
    ('основание',): ('basis', 'literal'),
    ('с', 'основанием'): ('basis', 'literal'),
    ('критерий',): ('criterion', 'literal'),
    ('с', 'критерием'): ('criterion', 'literal'),
}
_QUESTIONS = {
    'operation': 'Какую одну операцию нужно выполнить?',
    'target': 'К какой области относится запрос?',
    'profile': 'Какой профиль L1 имеется в виду?',
    'kind': 'Какого вида новая запись?',
    'contract': 'Укажите ID родительского контракта.',
    'scope': 'Для какой области действия нужна запись?',
    'entry_id': 'Какой ID у записи?',
    'state': 'Какое состояние вы хотите указать?',
    'title': 'Как назвать запись?',
    'text': 'Какова точная формулировка?',
    'basis': 'Каково основание записи?',
    'criterion': 'По какому критерию её проверять?',
}
_QUOTED = r'«[^«»]*»|"[^"]*"'
_LEXEME = re.compile(rf'{_QUOTED}|\s+|[:,;]|[^\s«»":,;]+')
_REFERENCE = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}')
_CONNECTORS = ('и', 'или')
_ABSENT = object()
_INVALID = object()


@dataclass(frozen=True)
class _Token:
    value: str
    quoted: bool = False

    @property
    def word(self):
        return None if self.quoted else self.value.casefold()


class _Unclear(ValueError):
    pass


def _split(request):
    tokens, pos, body = [], 0, None
    while pos < len(request):
        match = _LEXEME.match(request, pos)
        if match is None:
            raise _Unclear('invalid')
        raw = match.group()
        pos = match.end()
        if raw == ':':
            body = request[pos:].strip()
            break
        if raw.startswith(('«', '"')):
            tokens.append(_Token(raw[1:-1], quoted=True))
        elif not raw.isspace() and raw not in (',', ';'):
            tokens.append(_Token(raw))
    # Отдельная пунктуация после последнего слова не часть ID; ID с точкой в конце можно заключить в кавычки.
    while tokens and not tokens[-1].quoted:
        cleaned = tokens[-1].value.rstrip('.!?')
        if cleaned:
            tokens[-1] = _Token(cleaned)
            break
        tokens.pop()
    return tokens, body


def _mark(words, pos):
    for phrase, slot in _CLAUSES.items():
        if words[pos:pos + len(phrase)] == phrase:
            return len(phrase), slot
    return None


def _value(token, form):
    if form == 'reference':
        return token.value if _REFERENCE.fullmatch(token.value) else _INVALID
    return token.value if token.quoted and token.value.strip() else _INVALID


def _arguments(tokens, words, pos, operation, claims):
    def has_value(at):
        return at < len(tokens) and words[at] not in _CONNECTORS and _mark(words, at) is None

    previous = None
    while pos < len(tokens):
        join = words[pos] if words[pos] in _CONNECTORS else None
        if join is not None:
            if previous is None:
                raise _Unclear('unrecognized')
            pos += 1
        marker = _mark(words, pos)
        if marker is None:
            raise _Unclear('unrecognized')
        width, (field, form) = marker
        group = 'target' if field in ('target', 'profile') else field
        if join == 'или':
            if group != previous[0]:
                raise _Unclear('ambiguous')
            if (field, form) == ('target', 'L1') or previous[1:] == ('target', 'L1'):
                # У альтернативы «в L1» профиль не назван; соседний вариант его не заполняет.
                claims.setdefault('profile', []).append(_ABSENT)
        if group != 'target' and operation != 'create':
            raise _Unclear('unrecognized')
        pos += width
        if field == 'target':
            claims.setdefault(field, []).append(form)
        else:
            if field == 'profile':
                claims.setdefault('target', []).append('L1')
            values = claims.setdefault(field, [])
            if has_value(pos):
                values.append(_value(tokens[pos], form))
                pos += 1
                # «C-1 или C-2» без повторения метки. Альтернатива другой цели разбирается как новая часть.
                while pos < len(tokens) and words[pos] == 'или' and has_value(pos + 1):
                    values.append(_value(tokens[pos + 1], form))
                    pos += 2
            else:
                values.append(_ABSENT)
        previous = (group, field, form)


def _extract(request):
    tokens, body = _split(request)
    words = tuple(token.word for token in tokens)
    start = int(bool(words) and words[0] == 'пожалуйста')
    if start == len(words):
        raise _Unclear('absent')
    operation = _VERBS.get(words[start])
    if operation is None:
        raise _Unclear('unrecognized')
    pos = start + 1
    if any(word in _VERBS for word in words[pos:]):
        raise _Unclear('ambiguous')
    claims = {}

    def take(*choices):
        nonlocal pos
        if pos < len(words) and words[pos] in choices:
            pos += 1
            return True
        return False

    if operation == 'list':
        take('только')
        if take('текст'):
            claims['view'] = ['text']
        if take('действующее', 'действующие', 'действующего', 'действующих'):
            claims['state'] = ['active']
    elif operation == 'create':
        if take('черновик'):
            claims['state'] = ['draft']
        if take('постоянное', 'постоянный', 'постоянного'):
            claims['persistence'] = ['permanent']
    else:
        take('это', 'этот', 'эту')  # Только грамматическая форма, не ссылка на последнюю запись.
    if pos < len(words) and words[pos] in _KINDS:
        claims['kind'] = [_KINDS[words[pos]]]
        pos += 1
        if (pos < len(tokens) and words[pos] not in _CONNECTORS and _mark(words, pos) is None
                and (tokens[pos].quoted or tokens[pos].value.isascii())):
            claims['entry_id'] = [_value(tokens[pos], 'reference')]
            pos += 1
    _arguments(tokens, words, pos, operation, claims)
    if body is not None:
        if operation not in ('create', 'edit'):
            raise _Unclear('unrecognized')
        if re.fullmatch(_QUOTED, body):
            body = body[1:-1]
        claims['text'] = [body if body.strip() else _INVALID]
    return operation, claims


def _card(request, operation, params, missing, *, refusal=None):
    outcome = 'rejected' if refusal else 'missing_params' if missing else 'complete'
    return {'card_format': CARD_FORMAT, 'request': request, 'operation': operation, 'params': params,
            'missing': missing, 'questions': [{'field': row['field'], 'text': _QUESTIONS[row['field']]} for row in missing[:3]],
            'outcome': outcome, 'code': refusal or ('missing_params' if missing else None)}


def compile_prompt(request):
    """Одна карточка ввода. Даже complete не даёт прав, плана, билета или изменения состояния."""
    if type(request) is not str:
        raise TypeError('request: ожидается строка')
    request.encode('utf-8')  # Сохраняем весь исходный текст в JSON, не заменяя непредставимые символы.
    try:
        operation, claims = _extract(request)
    except _Unclear as error:
        return _card(request, None, {}, [{'field': 'operation', 'reason': str(error)}])

    params, unresolved = {}, {}
    for field, values in claims.items():
        alternatives = set(values)
        if len(alternatives) > 1:
            unresolved[field] = 'ambiguous'
        elif _INVALID in alternatives:
            unresolved[field] = 'invalid'
        elif _ABSENT in alternatives:
            unresolved[field] = 'absent'
        else:
            params[field] = values[0]

    target, kind = params.get('target'), params.get('kind')
    if target != 'L1':
        params.pop('profile', None)
        unresolved.pop('profile', None)
    if target is not None:
        route = operation_matrix()[operation][target]
        if route['state'] == 'forbidden':
            return _card(request, operation, params, [], refusal=route['code'])
    if operation == 'create' and kind == 'contract' and 'contract' in claims:
        return _card(request, operation, params, [], refusal='parent')

    required = {'target'} | ({'profile'} if target == 'L1' else set())
    if operation == 'create':
        required.update(('kind', 'scope', 'entry_id', 'state', 'title', 'text', 'basis', 'criterion'))
        if kind is not None and kind != 'contract':
            required.add('contract')
    elif operation != 'list' or params.get('view') == 'text':
        required.add('entry_id')
    if operation == 'edit':
        required.add('text')
    missing = [{'field': field, 'reason': unresolved.get(field, 'absent')} for field in _QUESTIONS
               if field in unresolved or (field in required and field not in params)]
    return _card(request, operation, params, missing)
