#!/usr/bin/env python3
"""И-112: независимый эталон трёх шагов, фактические открытия/байты/замены."""
from collections import Counter
from copy import deepcopy
from difflib import unified_diff
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import platform
import re
import sys
import tempfile
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
from kit.base import operation_card, operation_plan, registry_store
from kit.base.registry_policy import StoreError

ENTRY, START, MODULE = ('kit/base/' + n for n in ('entry.txt', 'START.md', 'bootstrap.py'))
DOCS = ['kit/base/' + n for n in ('OPERATION-CARD.md', 'OPERATION-PLAN.md', 'SCHEMA-V2.md', 'STORAGE-V2.md')]
PROFILE = 'profiles/pilot'
FILES = {'L1': PROFILE + '/registry.json', 'L0': 'kit/base/registry.json', 'L2': '.agent-contract/project/registry.json'}
AUTHORITY = {'L0': 'system_release', 'L1': 'profile_owner', 'L2': 'project_owner'}
VERSION = '0.2.0-dev.112'
POINTER, MARKER = b'kit/base/START.md#0', b'<!-- /bootstrap-0 -->'
ENTRY_LIMIT, START_LIMIT = len(POINTER) + 3, 4096
TOKEN = re.compile(r'[a-f0-9]{64}')
CALLS = ['compile', 'verify-card']
LAYERS = ['L1', 'L0', 'L2']
TEMP = PROFILE + '/.registry-*.tmp'
WRITE = ['stage:' + PROFILE, 'allocate:' + TEMP, 'write:' + TEMP, 'replace:' + TEMP + '→' + FILES['L1']]


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def saved_bytes(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')


def digest(raw):
    return sha256(raw).hexdigest()


def read_book():
    return json.loads((HERE / 'CASES.json').read_bytes())


def fact(name, data):
    return {'file': name, 'bytes': len(data), 'sha256': digest(data)}


def section_prefix(raw):
    end = re.search(rb'^' + re.escape(MARKER) + rb'\r?\n', raw, re.M)
    return raw[:end.end()] if end else raw


def original_docs():
    files = {name: (ROOT / name).read_bytes() for name in [ENTRY, START, *DOCS]}
    section = section_prefix(files[START])
    if not section.endswith(MARKER + b'\n') or not files[START][len(section):].lstrip().startswith(b'## 1. '):
        raise ValueError('У §0 должен быть явный конец и отдельный хвост полного чтения')
    return files


def row(area, id_, *, kind='contract', parent=None, text='Контракт стенда.'):
    return {'id': id_, 'kind': kind, 'parent': parent, 'state': 'active', 'scope': 'docs',
            'authority': AUTHORITY[area], 'title': id_, 'text': text,
            'basis': 'Фикстура И‑112', 'criterion': 'Сверить адрес и реестр.'}


def fixture(case, start_files):
    """Форма данных до вызова Kit. Ни один файл не производится его установщиком."""
    files, links = dict(start_files), {}
    docs = {a: {'schema_version': 2, 'area': a, 'roots': [root], 'entries': [],
                **({'release_version': VERSION} if a == 'L0' else {'revision': 0})}
            for a, root in zip(('L0', 'L1', 'L2'), ('kit', PROFILE, '.agent-contract'))}
    setup = case.get('setup')
    if setup == 'missing-entry':
        files.pop(ENTRY)
    elif setup == 'other-pointer':
        files[ENTRY] = b'kit/base/OTHER.md#0\n'
        files['kit/base/OTHER.md'] = files[START]
    elif setup == 'oversize-entry':
        files[ENTRY] = POINTER + b'\r\n' + b'x' * 8192
    elif setup == 'missing-start':
        files.pop(START)
    elif setup == 'section-cap':
        files[START] = b'## 0. Test\n' + b'content\n' * 800 + MARKER + b'\n'
    elif setup == 'bad-utf8':
        files[START] = files[START].replace(b'\n', b'\n\xff\n', 1)
    elif setup == 'start-symlink':
        files['kit/base/OTHER.md'] = files.pop(START)
        links[START] = ('symlink', 'kit/base/OTHER.md')
    elif setup == 'entry-hardlink':
        files['kit/base/OTHER.txt'] = files.pop(ENTRY)
        links[ENTRY] = ('hardlink', 'kit/base/OTHER.txt')
    elif setup == 'crlf':
        for name in (ENTRY, START):
            files[name] = files[name].replace(b'\n', b'\r\n')
    elif setup in ('local-parent', 'foreign-parent'):
        a = 'L1' if setup == 'local-parent' else 'L2'
        docs[a]['entries'] = [row(a, 'C-112')]
    elif setup == 'conflict':
        for a, who, value, text in [('L0', 'system', 'required', 'Системное условие стенда.'),
                                    ('L1', 'profile', 'skip', 'Профильное условие стенда.')]:
            contract = row(a, 'C-' + who)
            rule = row(a, 'R-' + who, kind='rule', parent=contract['id'], text=text)
            docs[a]['entries'] = [contract, dict(rule, key='workflow.review', value=value)]
    elif setup == 'old-schema':
        docs['L1']['schema_version'] = 1
    for a, doc in docs.items():
        if setup != 'no-catalog' and not (setup == 'partial' and a == 'L2'):
            files[FILES[a]] = canonical(doc)  # Намеренно без LF: дифф отражает фактические байты.
    return files, links


def seed(work, files, links):
    for name, raw in files.items():
        path = work / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    if FILES['L1'] in files:
        (work / FILES['L2']).parent.mkdir(parents=True, exist_ok=True)  # «partial»: есть именно каталог, нет файла.
    for name, (kind, source) in links.items():
        path, source = work / name, work / source
        if kind == 'symlink':
            path.symlink_to(source.name)
        else:
            os.link(source, path)


def snapshot(work):
    items = {}
    for path in work.rglob('*'):
        st = path.lstat()
        value = (('link', str(path.readlink())) if path.is_symlink()
                 else ('dir', None) if path.is_dir() else ('file', path.read_bytes()))
        stamps = () if value[0] == 'dir' else (st.st_mtime_ns, st.st_ctime_ns, st.st_nlink)
        items[path.relative_to(work).as_posix()] = (value, st.st_ino, st.st_mode, stamps)
    return items


def changes(before, after):
    return sorted(name for name in before.keys() | after.keys() if before.get(name) != after.get(name))


class Meter:
    """Учитываем реальные байты io.open, не пересчитываем по файлу задним числом."""
    def __init__(self, stream, name, trace, limit):
        self.stream, self.name, self.trace, self.limit = stream, name, trace, limit
        self.raw = bytearray()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.trace['reads'].append(fact(self.name, self.raw))
        return self.stream.__exit__(*args)

    def read(self, n=-1):
        return self._take(self.stream.read(n))

    def readline(self, n=-1):
        return self._take(self.stream.readline(n))

    def _take(self, data):
        self.raw.extend(data)
        if self.limit is not None and len(self.raw) > self.limit:
            raise AssertionError('Чтение за границей префикса: ' + self.name)
        return data


class Audit:
    """События уровня Python в целевых фазах, без импортов, фикстур и проверочных снимков."""
    def __init__(self):
        self.trace = None
        self.open_file = io.open
        self.compile = operation_card.compile_prompt
        self.verify = operation_plan.compile_prompt
        sys.addaudithook(self._audit)

    def rel(self, arg):
        path = Path(os.fsdecode(arg))
        if not path.is_absolute():
            path = Path.cwd() / path
        name = path.relative_to(self.work).as_posix() if path.is_relative_to(self.work) else '<outside>'
        return re.sub(r'(?<=/)\.registry-[^/]+\.tmp$', '.registry-*.tmp', name)

    def _audit(self, event, args):
        if self.trace is None:
            return
        events = self.trace['events']
        if event == 'open' and not isinstance(args[0], int):
            name = self.rel(args[0])
            if args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC):
                # CPython 3.11: NamedTemporaryFile передаёт каталог custom opener,
                # за которым должны последовать отдельные mkstemp и open файла.
                if name == PROFILE and args[1] == 'w':
                    events.append('stage:' + name)
                else:
                    events.append('write:' + name)
                    if name != TEMP:
                        raise AssertionError('Несогласованный путь записи: ' + name)
            else:
                events.append('read:' + name)
                if name not in {ENTRY, START, *FILES.values()}:
                    raise AssertionError('Посторонний вход: ' + name)
        elif event == 'tempfile.mkstemp':
            name = self.rel(args[0])
            events.append('allocate:' + name)
            if name != TEMP:
                raise AssertionError('Посторонний временный файл: ' + name)
        elif event == 'os.rename':
            src, dst = map(self.rel, args[:2])
            events.append('replace:' + src + '→' + dst)
            if not (src == TEMP and dst == FILES['L1']):
                raise AssertionError('Посторонняя замена')
        elif event in ('os.scandir', 'os.listdir', 'os.remove', 'os.mkdir', 'os.rmdir', 'os.symlink', 'os.link',
                       'os.chmod', 'os.truncate', 'os.chdir', 'subprocess.Popen', 'os.system', 'socket.__new__'):
            events.append(event)
            raise AssertionError('Непредусмотренное действие: ' + event)

    def _open(self, file, mode='r', buffering=-1, *args, **kwargs):
        if isinstance(file, int) or mode != 'rb':
            return self.open_file(file, mode, buffering, *args, **kwargs)
        name = self.rel(file)
        limit = self.limits.get(name)
        if limit is not None and buffering != 0:
            raise AssertionError('Буфер опередил ограниченное чтение: ' + name)
        stream = self.open_file(file, mode, buffering, *args, **kwargs)
        return Meter(stream, name, self.trace, limit)

    def _call(self, name, func, request):
        self.trace['events'].append(name)
        return func(request)

    def run(self, work, limits, step, fn, view=lambda x: x):
        self.work, self.limits = work, limits
        before = snapshot(work)
        trace = {'events': [], 'reads': []}
        with patch.object(io, 'open', self._open), \
             patch.object(operation_card, 'compile_prompt', lambda r: self._call('compile', self.compile, r)), \
             patch.object(operation_plan, 'compile_prompt', lambda r: self._call('verify-card', self.verify, r)):
            self.trace = trace
            try:
                value, error = fn(), None
            except StoreError as exc:
                value, error = None, exc.diagnostic()
            finally:
                self.trace = None
        reply = {'outcome': 'refused', 'error': error} if error is not None else view(value)
        return value, {'step': step, 'reply': reply, **trace, 'changed': changes(before, snapshot(work))}


def start_view(boot):
    return {'outcome': 'ready', 'inputs': boot.inputs, 'section_sha256': digest(boot.section0.encode('utf-8'))}


def public(plan):
    view = deepcopy(plan)
    if 'ticket' in view:
        token = view.pop('ticket')
        issued = type(token) is str and TOKEN.fullmatch(token) is not None
        view['ticket_state'] = 'issued' if issued else 'malformed'
    questions = view['card']['questions']
    if type(questions) is not list or any(q.keys() != {'field', 'text'} or type(q['text']) is not str or not q['text'].strip() for q in questions):
        raise AssertionError('Неверная форма уточнений')
    view['card']['questions'] = [q['field'] for q in questions]
    return view


def expected_saved(phrase, files):
    # Только contract/draft L1 на нулевой ревизии. Не используем результат компилятора или порт как эталон.
    p = phrase['params']
    entry = {k: p[k] for k in ('kind', 'state', 'scope', 'title', 'text', 'basis', 'criterion')}
    entry.update(id=p['entry_id'], parent=None, authority='profile_owner')
    original = json.loads(files[FILES['L1']])
    return {'registry_format': 2, 'registry': dict(original, revision=1, entries=[entry]),
            'journal': {'base_revision': 0, 'base_entries': {}, 'decisions': [
                {'operation': 'create', 'entry_id': entry['id'], 'profile_revision': 1, 'before_sha256': None,
                 'after_sha256': digest(canonical(entry))}]}}


def expected_plan(phrase, files):
    card = dict(phrase, card_format=1, questions=[m['field'] for m in phrase['missing'][:3]])
    outcome = phrase['outcome']
    plan = {'outcome': outcome, 'dry_run': True, 'plan_format': 1, 'card': card}
    if outcome != 'complete':
        return plan
    rel = FILES['L1']
    a, b = files[rel], saved_bytes(expected_saved(phrase, files))
    lines = unified_diff(a.decode('utf-8').splitlines(keepends=True), b.decode('utf-8').splitlines(keepends=True),
                         fromfile='a/' + rel, tofile='b/' + rel)
    diff = ''.join(line if line.endswith('\n') else line + '\n\\ No newline at end of file\n' for line in lines)
    return dict(plan, outcome='planned', ticket_state='issued', inputs_sha256={a: digest(files[n]) for a, n in FILES.items()},
                diff={'file': rel, 'revision': {'from': 0, 'to': 1}, 'unified': diff,
                      'before_sha256': digest(a), 'after_sha256': digest(b)})


def refused(code, where):
    return {'outcome': 'refused', 'error': {'code': code, 'where': where}}


def expected_step(step, reply, readings=(), *, before=(), after=(), changed=()):
    return {'step': step, 'reply': reply, 'events': [*before, *('read:' + n for n, _ in readings), *after],
            'reads': [fact(n, raw) for n, raw in readings], 'changed': list(changed)}


def expected(case, book, start_files):
    files, links = fixture(case, start_files)
    prefix = [(n, files[n][:ENTRY_LIMIT] if n == ENTRY else section_prefix(files[n])[:START_LIMIT])
              for n in case.get('startup_files', [ENTRY, START])]
    if 'startup_error' in case:
        result = {'outcome': 'refused', 'error': case['startup_error']}
    else:
        result = {'outcome': 'ready', 'inputs': [fact(n, data) for n, data in prefix], 'section_sha256': digest(prefix[1][1])}
    observed = {'files': sorted(files.keys() | links.keys()), 'steps': [expected_step('bootstrap', result, prefix)],
                'changed': [], 'stored': None, 'injected': []}
    steps = observed['steps']
    if 'phrase' not in case:
        return observed
    phrase = book['phrases'][case['phrase']]
    answer = {'outcome': 'refused', 'error': case['plan_error']} if 'plan_error' in case else expected_plan(phrase, files)
    reading = [(FILES[a], files[FILES[a]]) for a in case.get('areas', ())]
    steps.append(expected_step('phrase', answer, reading, before=CALLS))
    trial = case.get('trial')
    if trial == 'confirm':
        value = expected_saved(phrase, files)
        status = {'schema_version': 2, 'release_version': VERSION, 'profile_root': PROFILE, 'profile_revision': 1, 'project_revision': 0}
        steps.append(expected_step('confirmation', {'outcome': 'applied', 'status': status}, reading, after=WRITE, changed=[FILES['L1']]))
        observed.update(changed=[FILES['L1']], stored={'document': value, 'sha256': digest(saved_bytes(value))})
    elif trial == 'drift':
        drifted = [(n, raw + b'\n' if n == FILES['L2'] else raw) for n, raw in reading]
        steps.append(expected_step('confirmation', refused('stale_plan', 'inputs/L2'), drifted))
        steps.append(expected_step('replay', refused('ticket_unknown', 'ticket')))
        observed.update(changed=[FILES['L2']], injected=[FILES['L2']])
    elif trial == 'new-phrase':
        steps.append(expected_step('rephrase', expected_plan(book['phrases']['temporary'], files), before=CALLS))
        steps.append(expected_step('confirmation', refused('ticket_unknown', 'ticket')))
    elif trial:
        error = refused('plan_mismatch', 'plan') if trial == 'changed-diff' else refused('confirmation_required', 'confirmed_ticket')
        steps.append(expected_step('confirmation', error))
    return observed


def observe(case, book, start_files, audit, session):
    files, links = fixture(case, start_files)
    limits = {ENTRY: ENTRY_LIMIT}
    if START in files:
        limits[START] = min(START_LIMIT, len(section_prefix(files[START])))
    with tempfile.TemporaryDirectory(prefix='ack-i112-fixture-') as tmp:
        work = Path(tmp).resolve()
        seed(work, files, links)
        initial = snapshot(work)
        layout = registry_store.Layout(work, case.get('profile_root', PROFILE))
        boot, start = audit.run(work, limits, 'bootstrap', lambda: session(layout, profile_id='Pilot'), start_view)
        steps, injected = [start], []
        stored = None
        if 'phrase' in case and boot is not None:
            phrase = book['phrases'][case['phrase']]['request']
            plan, step = audit.run(work, limits, 'phrase', lambda: boot.plan(phrase), public)
            steps.append(step)
            trial = case.get('trial')
            if trial:
                wanted = expected(case, book, start_files)['steps'][:2]
                if canonical(steps) != canonical(wanted):
                    raise AssertionError('Отдельное согласие только после наблюдения точного, неизменившего ничего dry-run')
                token = plan['ticket']
                action = lambda: boot.apply(plan, confirmed_ticket=token)
                if trial == 'withheld':
                    action = lambda: boot.apply(plan)
                elif trial == 'foreign-ticket':
                    action = lambda: boot.apply(plan, confirmed_ticket=('f' if token[0] == '0' else '0') * 64)
                elif trial == 'changed-diff':
                    altered = dict(plan, diff=dict(plan['diff'], unified=plan['diff']['unified'] + '\n+иная строка\n'))
                    action = lambda: boot.apply(altered, confirmed_ticket=token)
                elif trial == 'drift':
                    # Внешнее изменение фикстуры, не запись Kit. Ревизия и JSON-поля те же.
                    (work / FILES['L2']).write_bytes(files[FILES['L2']] + b'\n')
                    injected.append(FILES['L2'])
                elif trial == 'new-phrase':
                    text = book['phrases']['temporary']['request']
                    _, fresh = audit.run(work, limits, 'rephrase', lambda: boot.plan(text), public)
                    steps.append(fresh)
                _, applied = audit.run(work, limits, 'confirmation', action)
                steps.append(applied)
                if trial == 'drift':
                    _, replay = audit.run(work, limits, 'replay', action)
                    steps.append(replay)
                if trial == 'confirm' and applied['reply']['outcome'] == 'applied':
                    data = (work / FILES['L1']).read_bytes()
                    stored = {'sha256': digest(data), 'document': json.loads(data)}
        after = snapshot(work)
        return {'files': sorted(n for n, info in initial.items() if info[0][0] != 'dir'), 'steps': steps,
                'changed': changes(initial, after), 'stored': stored, 'injected': injected}


def baseline(book, audit, missing):
    """Отделяем отсутствие старта от уже существующей способности собрать дифф."""
    files, links = fixture({}, {})
    phrase = book['phrases']['create']
    with tempfile.TemporaryDirectory(prefix='ack-i112-base-') as tmp:
        work = Path(tmp).resolve()
        seed(work, files, links)
        layout = registry_store.Layout(work, PROFILE)
        session = operation_plan.PlanSession(layout, profile_id='Pilot')
        _, step = audit.run(work, {}, 'direct-plan', lambda: session.plan(operation_card.compile_prompt(phrase['request'])), public)
    wanted = expected_step('direct-plan', expected_plan(phrase, files), [(FILES[a], files[FILES[a]]) for a in LAYERS], before=CALLS)
    return {'missing': missing, 'direct_plan_matches': canonical(step) == canonical(wanted), 'direct_plan': step}


def run():
    book = read_book()
    audit = Audit()
    missing = [n for n in (ENTRY, START, MODULE) if not (ROOT / n).is_file()]
    rows = []
    if missing:
        control = baseline(book, audit, missing)
        rows = [{'id': c['id'], 'status': 'fail', 'reason': 'bootstrap_missing'} for c in book['cases']]
    else:
        from kit.base.bootstrap import BootstrapSession
        docs, control = original_docs(), None
        for case in book['cases']:
            try:
                actual = observe(case, book, docs, audit, BootstrapSession)
                wanted = expected(case, book, docs)
                mismatches = [key for key, value in wanted.items() if canonical(actual[key]) != canonical(value)]
                status = 'fail' if mismatches else 'pass'
                row_ = {'id': case['id'], 'status': status, 'observed': actual, 'mismatches': mismatches}
            except (AssertionError, AttributeError, KeyError, OSError, TypeError, ValueError) as error:
                row_ = {'id': case['id'], 'status': 'fail', 'reason': type(error).__name__, 'error': str(error)}
            rows.append(row_)
    tally = Counter(row_['status'] for row_ in rows)
    print(json.dumps({'format': 1, 'os': platform.system(), 'python': platform.python_version(), 'baseline': control, 'rows': rows,
                      'counts': {s: tally[s] for s in ('pass', 'fail', 'not run')}}, ensure_ascii=False))
    return int(tally['fail'] != 0)


if __name__ == '__main__':
    raise SystemExit(run())
