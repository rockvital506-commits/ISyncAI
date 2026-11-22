"""И-121: локальная проверка формы и границ одного каталога, не интерфейс Kit."""
from collections import Counter
import json

_MAX_BYTES = 96 * 1024
_S = 'research/STRATEGY.md:'
_BASE = 'research/strategy/BASELINE.json:'
_BOOT = 'research/112/BOOTSTRAP.json:'
_STAGE = ('presence', 'detected', 'read', 'applied', 'repeat')
_MANUAL = 'kit/base/entry.txt → kit/base/START.md §0'
_PILOT = 'Windows 11 / VS Code 1.146'
_FIELDS = {'format', 'iteration', 'scope', 'limits', 'protected', 'environments', 'donor_discrepancy'}
_ROW = {'status', 'stub_reason', 'target', 'entry', 'priority', 'caps', 'unchanged', 'coverage', 'metrics', 'gaps', 'donor'}
_LIMITS = {'context_percent': [25, 30], 'context_status': 'target', 'start_section_max_bytes': 4096,
           'start_status': 'kit_only', 'basis': [_S+'P8', _BOOT+'controls.S05']}
_PROTECTED = ['.isai/', 'kit/', 'AGENTS.md', 'реестры и профили L0/L1/L2', 'глобальные настройки и права',
              'секреты и проектные данные', 'порт и CI']
_DISAGREEMENT = ['research/101/AgentContractKit-Iteration-101.zip:research/strategy/BASELINE.json:adapters.copilot',
                 'research/102/BASELINE.json:adapters.copilot', 'research/101/REPORT.md:инвентарь адаптеров']
_ENV = {
    # Поверхность, планируемая среда, строки-кандидаты, гипотезы, нет записи, будущий шаг, отдельный пробел.
    'arena': ('Arena Agent Mode / GitHub', None, ['AGENTS.md'], ['sandbox-root-vs-nested'],
              ['AGENTS.md', '.github/workflows/', 'настройки репозитория и веток'], 'И‑124', 'copy_boundary'),
    'kilo': ('Kilo / VS Code', _PILOT, ['AGENTS.md', 'kilo.jsonc', '.kilo/rules/'], ['agents-vs-kilo-rules'],
             ['AGENTS.md', 'kilo.jsonc', '.kilo/rules/', 'настройки VS Code и расширения'], 'И‑122', 'foreign_entry'),
    'copilot': ('GitHub Copilot / VS Code', _PILOT,
                ['AGENTS.md', '.github/copilot-instructions.md', '.github/instructions/*.instructions.md'],
                ['nearest-wins', 'root-vs-path-scoped'],
                ['AGENTS.md', '.github/copilot-instructions.md', '.github/instructions/', 'настройки VS Code и расширения'],
                'И‑123', 'single_registry'),
    'claude': ('Claude Code', None, [], [], ['CLAUDE.md', 'пользовательские настройки Claude Code'], None, None),
    'cursor': ('Cursor', None, [], [], ['.cursor/rules/', 'пользовательские настройки Cursor'], None, None),
    'antigravity': ('Antigravity', None, [], [], ['GEMINI.md', 'настройки IDE/App/CLI'], None, None),
}


class SurfaceError(ValueError):
    def __init__(self, code, where, reason):
        self.code, self.where, self.reason = code, where, reason
        super().__init__(f'{code} at {where}')

    def diagnostic(self):
        return {'code': self.code, 'where': self.where, 'reason': self.reason}


def _require(allowed, code, where, reason):
    if not allowed:
        raise SurfaceError('surfaces_'+code, where, reason) from None


def _fields(obj, fields):
    return type(obj) is dict and obj.keys() == fields


def _same(obj, wanted):
    if type(obj) is not type(wanted):
        return False
    if type(wanted) is dict:
        return obj.keys() == wanted.keys() and all(_same(obj[k], v) for k, v in wanted.items())
    if type(wanted) is list:
        return len(obj) == len(wanted) and all(_same(k, v) for k, v in zip(obj, wanted))
    return obj == wanted


def _text(value):
    return type(value) is str and 0 < len(value) <= 2048 and bool(value.strip()) and '\0' not in value


def _unique(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise ValueError
        out[k] = v
    return out


def _nonfinite(_):
    raise ValueError


def _parse(raw):
    _require(type(raw) is bytes and raw, 'input', 'matrix', 'bytes')
    _require(len(raw) <= _MAX_BYTES, 'input', 'matrix', 'limit')
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=_unique, parse_constant=_nonfinite)
    except (ValueError, RecursionError):
        raise SurfaceError('surfaces_input', 'matrix', 'json') from None


def _donor(baseline):
    # Это явный вход исторического контроля, не данные из матрицы и не поиск адаптеров.
    _require(type(baseline) is dict and baseline.get('release') == '0.1.36'
             and _same(baseline.get('absent_adapters'), ['arena'])
             and _fields(baseline.get('adapters'), set(_ENV)-{'arena'}), 'donor', 'matrix', 'baseline')
    donors = {'arena': dict(status='absent', entry=None, rank=None, of=None, release='0.1.36',
                            basis=_BASE+'absent_adapters; research/101/CLEANROOM.json:7-adapter-arena')}
    for name, fact in baseline['adapters'].items():
        _require(_fields(fact, {'title', 'status', 'entry', 'rank', 'of'}), 'donor', name, 'baseline')
        status, entry, rank, of = (fact[k] for k in ('status', 'entry', 'rank', 'of'))
        stub = _ENV[name][5] is None
        plausible = (status == 'stub' and entry is None and rank is None and of is None if stub else
                     status == 'documented' and entry == 'AGENTS.md' and type(rank) is type(of) is int and 1 <= rank <= of)
        _require(plausible, 'donor', name, 'baseline')
        donors[name] = dict(status=status, entry=entry, rank=rank, of=of, release='0.1.36', basis=_BASE+'adapters.'+name)
    return donors


def _gaps(gaps, name, phase, special):
    next_steps = {'scope': None} if phase is None else {'entry': phase, 'priority': phase, special: phase,
                                                        'read_apply_repeat': 'И‑125', 'context_budget': 'И‑126'}
    _require(_fields(gaps, next_steps.keys()), 'gaps', name, 'set')
    for key, needed in next_steps.items():
        gap = gaps[key]
        _require(_fields(gap, {'next', 'basis', 'criterion'}), 'gaps', name, 'fields')
        _require(_same(gap['next'], needed), 'gaps', name, 'next')
        _require(_same(gap['basis'], _S+(needed or '§1.2')), 'gaps', name, 'basis')
        _require(_text(gap['criterion']), 'gaps', name, 'criterion')


def _environment(name, row, donor):
    label, pilot, paths, hypotheses, unchanged, step, special = _ENV[name]
    stub = step is None; status = 'stub' if stub else 'candidate'; evidence = 'out_of_scope' if stub else 'not run'
    src = _S+(step or '§1.2')
    _require(_fields(row, _ROW), 'shape', name, 'fields')
    _require(_same(row['status'], status), 'status', name, status)
    _require(_text(row['stub_reason']) if stub else row['stub_reason'] is None, 'status', name, 'reason')
    target = row['target']
    _require(_fields(target, {'surface', 'pilot', 'observed_version', 'observed_mode', 'basis'}), 'status', name, 'target')
    _require(target['observed_version'] is None and target['observed_mode'] is None, 'status', name, 'observation')
    _require(_same(target, {'surface':label, 'pilot':pilot, 'observed_version':None, 'observed_mode':None,
                            'basis':[src, *([_S+'Ф8'] if pilot else [])]}), 'status', name, 'target')
    entry = row['entry']
    _require(_fields(entry, {'status', 'paths', 'config_key', 'manual', 'basis'}), 'entry', name, 'fields')
    _require(entry['config_key'] is None, 'entry', name, 'unverified_key')
    wanted_entry = {'status':'disabled' if stub else 'candidate', 'paths':paths, 'config_key':None,
                    'manual':None if stub else _MANUAL, 'basis':[src, *([] if stub else [_BOOT+'witness'])]}
    _require(_same(entry, wanted_entry), 'entry', name, 'surfaces')
    _require(_same(row['priority'], {'status':evidence, 'winner':None, 'hypotheses':hypotheses}), 'priority', name, 'unverified')
    _require(_same(row['caps'], {'status':evidence, 'context_tokens':None, 'instruction_bytes':None, 'truncation':None}),
             'caps', name, 'native_unknown')
    _require(_same(row['unchanged'], unchanged), 'guard', name, 'unchanged')
    _require(_same(row['coverage'], dict.fromkeys(_STAGE, evidence)), 'coverage', name, 'stages')
    _require(_same(row['metrics'], {'runs':None if stub else 0, 'read_rate':None, 'apply_rate':None, 'false_positive':None}),
             'coverage', name, 'metrics')
    _gaps(row['gaps'], name, step, special)
    _require(_same(row['donor'], donor), 'donor', name, 'inventory')


def _discrepancy(got, donor, report_rank):
    ref = donor['copilot']; inventory = [ref['rank'], ref['of']]
    valid = type(report_rank) is list and len(report_rank) == 2 and all(type(n) is int for n in report_rank)
    _require(valid and 1 <= report_rank[0] <= report_rank[1] and report_rank != inventory, 'donor', 'copilot', 'baseline')
    facts = {'id':'copilot', 'inventory':inventory, 'report':report_rank, 'resolution':'inventory_for_donor_only',
             'cause_known':False, 'basis':_DISAGREEMENT}
    _require(_fields(got, facts.keys() | {'criterion'}) and all(_same(got[k], v) for k, v in facts.items())
             and _text(got['criterion']), 'donor', 'copilot', 'discrepancy')


def validate_surfaces(raw, *, baseline, report_rank):
    """Проверить И-121 офлайн; положительный ответ не засчитывает ни одной пробы клиента."""
    doc = _parse(raw)
    _require(_fields(doc, _FIELDS), 'shape', 'matrix', 'fields')
    _require(_same(doc['format'], 1) and _same(doc['iteration'], 'И-121'), 'shape', 'matrix', 'version')
    _require(_same(doc['scope'], 'inventory_only'), 'shape', 'matrix', 'scope')
    _require(_same(doc['limits'], _LIMITS), 'caps', 'limits', 'kit_limits')
    _require(_same(doc['protected'], _PROTECTED), 'guard', 'matrix', 'protected')
    envs = doc['environments']
    _require(_fields(envs, _ENV.keys()), 'rows', 'environments', 'exact')
    donor = _donor(baseline)
    for name in _ENV:
        _environment(name, envs[name], donor[name])
    _discrepancy(doc['donor_discrepancy'], donor, report_rank)
    labels = {name: envs[name]['status'] for name in _ENV}
    return {'format':doc['format'], 'scope':doc['scope'], 'environments':labels,
            'entry_candidates':sum(len(r['entry']['paths']) for r in envs.values()),
            'by_status':dict(Counter(labels.values())), 'by_coverage':dict(Counter(v for r in envs.values() for v in r['coverage'].values())),
            'client_runs':sum(r['metrics']['runs'] for r in envs.values() if r['metrics']['runs'] is not None)}
