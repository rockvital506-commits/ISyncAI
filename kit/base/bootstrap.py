"""Явный короткий вход к PlanSession на уже подготовленной раскладке v2."""
from contextlib import contextmanager
from hashlib import sha256
from io import BytesIO

from . import operation_card, operation_plan, registry_store
from .registry_policy import StoreError

_ENTRY = 'kit/base/entry.txt'
_START = 'kit/base/START.md'
_POINTER = (_START + '#0').encode('ascii')
_SECTION_LIMIT = 4096
_HEADING = b'## 0. '
_END = b'<!-- /bootstrap-0 -->'


def _line_forms(content):
    return (content + b'\n', content + b'\r\n')


@contextmanager
def _input(workspace, rel):
    # Те же требования к существующему обычному файлу и его пути, что у реестров.
    path, _ = registry_store._existing(workspace, rel, registry=True)
    try:
        # BufferedReader может прочитать за границей §0 даже при корректных строках.
        with path.open('rb', buffering=0) as stream:
            yield stream
    except OSError as error:
        raise StoreError('io_error', rel) from error


def _entry_stream(stream):
    raw = stream.read(len(_POINTER) + 3)  # Максимальный CRLF и ещё байт для проверки хвоста.
    if raw not in _line_forms(_POINTER):
        raise StoreError('invalid_entrypoint', _ENTRY)
    return raw


def _section_stream(stream):
    head = stream.readline(_SECTION_LIMIT)
    if not (head.startswith(_HEADING) and head.endswith(b'\n') and head[len(_HEADING):].strip()):
        raise StoreError('invalid_start_section', _START)
    raw, body = bytearray(head), False
    while len(raw) < _SECTION_LIMIT:
        line = stream.readline(_SECTION_LIMIT - len(raw))
        if not line.endswith(b'\n') or line.startswith(b'## '):
            break
        raw.extend(line)
        if line in _line_forms(_END):
            if not body:
                break
            try:
                return bytes(raw), raw.decode('utf-8')
            except UnicodeDecodeError as error:
                raise StoreError('invalid_start_section', _START) from error
        body = body or bool(line.strip())
    raise StoreError('invalid_start_section', _START)


def _read_entry(workspace):
    with _input(workspace, _ENTRY) as stream:
        return _entry_stream(stream)


def _read_section(workspace):
    with _input(workspace, _START) as stream:
        return _section_stream(stream)


def _read_fact(rel, raw):
    return {'file': rel, 'bytes': len(raw), 'sha256': sha256(raw).hexdigest()}


def extract_start(entry_bytes, start_bytes):
    """Разобрать явно переданные байты без I/O; вызывающий отвечает за их доверие."""
    if type(entry_bytes) is not bytes or type(start_bytes) is not bytes:
        raise StoreError('invalid_entrypoint', _ENTRY)
    entry = _entry_stream(BytesIO(entry_bytes))
    section, text = _section_stream(BytesIO(start_bytes))
    return {'section0': text, 'inputs': [_read_fact(_ENTRY, entry), _read_fact(_START, section)]}


class BootstrapSession:
    """Шаг 1: прочитать два минимальных входа, не проверяя здоровье реестров.

    Layout и profile_id — доверенная явная привязка; ни Markdown, ни фраза
    не выбирают за вызывающий код пути на диске или полномочия.
    """

    def __init__(self, layout, *, profile_id):
        workspace = registry_store._workspace(layout.workspace)
        self._layout = registry_store.Layout(workspace, layout.profile_root)
        self._profile_id = profile_id
        self._session = self._new_session()
        entry = _read_entry(workspace)
        section, self.section0 = _read_section(workspace)
        self.inputs = [_read_fact(_ENTRY, entry), _read_fact(_START, section)]

    def _new_session(self):
        return operation_plan.PlanSession(self._layout, profile_id=self._profile_id)

    def plan(self, request):
        """Шаг 2: сначала компиляция фразы, затем обычный dry-run.

        Новая попытка отзывает прежний план даже при ошибке компиляции.
        """
        self._session = self._new_session()
        return self._session.plan(operation_card.compile_prompt(request))

    def apply(self, plan, *, confirmed_ticket=None):
        """Шаг 3: проверить отдельный билет, точный план и свежесть данных."""
        return self._session.apply(plan, confirmed_ticket=confirmed_ticket)
