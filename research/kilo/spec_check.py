#!/usr/bin/env python3
"""Проверка состояния Kilo по известной спецификации.

Читает только файлы, ничего не пишет, не запускает клиент и не трогает настройки.

Пример:
    python3 -B research/kilo/spec_check.py --state research/kilo/examples/state-example.json
    python3 -B research/kilo/spec_check.py --kilo-jsonc path/to/kilo.jsonc
    python3 -B research/kilo/spec_check.py --selftest
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SPEC = Path(__file__).with_name('KILO-SPEC.json')

LEVELS = ('error', 'gap', 'info')
TOOLS = ('read', 'edit', 'bash', 'glob', 'grep', 'list', 'task', 'external_directory',
         'webfetch', 'websearch', 'lsp', 'skill', 'todoread', 'todowrite',
         'agent_manager', 'doom_loop', 'browser_open')
AGENT_FIELDS = ('name', 'description', 'prompt', 'model', 'variant', 'temperature', 'top_p',
                'steps', 'permission', 'mode', 'hidden', 'disable', 'color')
MODES = ('primary', 'subagent', 'all')
ACTIONS = ('allow', 'ask', 'deny')
TOP_KEYS = ('$schema', 'model', 'small_model', 'default_agent', 'agent', 'mode', 'command', 'mcp',
            'permission', 'instructions', 'provider', 'username', 'share', 'keybinds',
            'compaction', 'skills', 'plugin', 'hide_prompt_training_models', 'reasoning_display',
            'terminal_command_display', 'code_edit_display', 'mcp_tool_display', 'experimental')


def spec() -> dict:
    return json.loads(SPEC.read_bytes())


def rule(code: str, where: str, reason: str) -> dict:
    assert code in LEVELS, code
    return {'level': code, 'where': where, 'reason': reason}


def check_permission(perm, out):
    if perm is None:
        return
    if not isinstance(perm, dict):
        out.append(rule('error', 'permission', 'ожидался объект инструментов'))
        return
    for tool, value in perm.items():
        if tool not in TOOLS and '_' not in tool:
            out.append(rule('error', f'permission.{tool}', 'неизвестный инструмент'))
            continue
        if isinstance(value, str):
            if value not in ACTIONS:
                out.append(rule('error', f'permission.{tool}', 'ожидалось allow|ask|deny'))
        elif isinstance(value, dict):
            for glob, action in value.items():
                if action not in ACTIONS:
                    out.append(rule('error', f'permission.{tool}.{glob}', 'ожидалось allow|ask|deny'))
        else:
            out.append(rule('error', f'permission.{tool}', 'значение должно быть строкой или объектом'))


def check_agent(name, agent, out):
    if not isinstance(agent, dict):
        out.append(rule('error', f'agent.{name}', 'ожидался объект'))
        return
    for key in agent:
        if key not in AGENT_FIELDS:
            out.append(rule('error', f'agent.{name}.{key}', 'неизвестное поле агента'))
    if 'mode' in agent and agent['mode'] not in MODES:
        out.append(rule('error', f'agent.{name}.mode', 'ожидалось primary|subagent|all'))
    if 'temperature' in agent and not isinstance(agent['temperature'], (int, float)):
        out.append(rule('error', f'agent.{name}.temperature', 'ожидалось число'))
    if 'steps' in agent and not isinstance(agent['steps'], int):
        out.append(rule('error', f'agent.{name}.steps', 'ожидалось целое'))
    check_permission(agent.get('permission'), out)


def check_context(doc, out):
    provider = doc.get('provider') or {}
    declared = False
    if isinstance(provider, dict):
        for pname, pdata in provider.items():
            models = (pdata or {}).get('models') or {}
            if not isinstance(models, dict):
                out.append(rule('error', f'provider.{pname}.models', 'ожидался объект'))
                continue
            for mname, mdata in models.items():
                limit = (mdata or {}).get('limit')
                if isinstance(limit, dict) and isinstance(limit.get('context'), int) and limit['context'] > 0:
                    declared = True
    if not declared:
        out.append(rule('gap', 'provider.*.models.*.limit.context',
                        'не объявлено: учёт контекста и автосжатие не работают (KILO-SPEC.context.hard_rule)'))


def check_kilo_jsonc(doc: dict) -> dict:
    out: list = []
    if not isinstance(doc, dict):
        return {'ok': False, 'findings': [rule('error', 'root', 'ожидался объект')]}
    for key in doc:
        if key not in TOP_KEYS:
            out.append(rule('error', key, 'неизвестный ключ верхнего уровня'))
    if 'instructions' in doc:
        val = doc['instructions']
        if not isinstance(val, list) or not all(isinstance(x, str) for x in val):
            out.append(rule('error', 'instructions', 'ожидался массив путей или glob'))
    check_permission(doc.get('permission'), out)
    agents = doc.get('agent') or {}
    if agents and not isinstance(agents, dict):
        out.append(rule('error', 'agent', 'ожидался объект'))
    elif isinstance(agents, dict):
        for name, agent in agents.items():
            check_agent(name, agent, out)
    compact = doc.get('compaction')
    if compact is not None:
        if not isinstance(compact, dict):
            out.append(rule('error', 'compaction', 'ожидался объект'))
        else:
            known = {'auto', 'threshold_percent', 'prune', 'tail_turns',
                     'preserve_recent_tokens', 'reserved'}
            for key in compact:
                if key not in known:
                    out.append(rule('error', f'compaction.{key}', 'неизвестный параметр'))
            tp = compact.get('threshold_percent')
            if tp is not None and not (isinstance(tp, (int, float)) and 1 <= tp <= 100):
                out.append(rule('error', 'compaction.threshold_percent', 'ожидалось 1–100'))
    mcp = doc.get('mcp')
    if mcp is not None:
        if not isinstance(mcp, dict):
            out.append(rule('error', 'mcp', 'ожидался объект'))
        else:
            for name, server in mcp.items():
                if not isinstance(server, dict):
                    out.append(rule('error', f'mcp.{name}', 'ожидался объект'))
                    continue
                if 'type' in server and server['type'] not in ('local', 'remote'):
                    out.append(rule('error', f'mcp.{name}.type', 'ожидалось local|remote'))
    check_context(doc, out)
    if any(f['level'] == 'error' for f in out):
        out.append(rule('info', 'итог', 'состояние неполно: есть ошибки'))
    else:
        out.append(rule('info', 'итог', 'ошибок нет; пробелы перечислены отдельно'))
    return {'ok': not any(f['level'] == 'error' for f in out), 'findings': out}


def check_state(doc: dict) -> dict:
    """Состояние досье: id, fingerprint, evidence_level."""
    out: list = []
    sp = spec()
    for key in ('id', 'fingerprint', 'evidence_level'):
        if key not in doc:
            out.append(rule('error', key, 'обязательное поле состояния'))
    used = {e for e in ('vendor', 'observed_ui', 'observed', 'not run')}
    if doc.get('evidence_level') and doc['evidence_level'] not in used:
        out.append(rule('error', 'evidence_level', f'ожидалось одно из {sorted(used)}'))
    fp = doc.get('fingerprint')
    if fp is not None and not isinstance(fp, dict):
        out.append(rule('error', 'fingerprint', 'ожидался объект'))
    if doc.get('evidence_level') == 'observed' and not doc.get('runs'):
        out.append(rule('error', 'runs', 'наблюдение требует числа прогонов'))
    inj = doc.get('kilo_jsonc')
    if inj is not None:
        inner = check_kilo_jsonc(inj)
        out.extend(inner['findings'])
    if not any(f['level'] == 'error' for f in out):
        out.append(rule('info', 'итог', 'состояние описывает данные, а не обещание поведения'))
    return {'ok': not any(f['level'] == 'error' for f in out), 'findings': out}


def selftest() -> int:
    bad = {'permission': {'bash': 'maybe'}}
    res = check_kilo_jsonc(bad)
    assert res['ok'] is False, 'должен отвергнуть недопустимое значение права'
    assert any(f['where'] == 'permission.bash' for f in res['findings'])
    unknown = check_kilo_jsonc({'agent': {'x': {'qqq': 1}}})
    assert unknown['ok'] is False, 'должен отвергнуть неизвестное поле агента'
    good = check_kilo_jsonc({'permission': {'bash': {'*': 'ask', 'git *': 'allow'}},
                             'agent': {'code': {'mode': 'primary', 'steps': 20}},
                             'provider': {'kilo': {'models': {'m': {'limit': {'context': 200000, 'output': 32000}}}}}})
    assert good['ok'] is True, good
    ctx = check_kilo_jsonc({'model': 'kilo/free'})
    assert any(f['level'] == 'gap' for f in ctx['findings']), 'без limit.context должен быть gap'
    st = check_state({'id': 'ST-X', 'fingerprint': {}, 'evidence_level': 'observed'})
    assert st['ok'] is False, 'observed без прогонов запрещён'
    print('selftest: ok (5 проверок)')
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description='Проверка состояния Kilo по KILO-SPEC.json')
    ap.add_argument('--kilo-jsonc', help='путь к файлу kilo.jsonc (только чтение)')
    ap.add_argument('--state', help='путь к состоянию досье в JSON')
    ap.add_argument('--selftest', action='store_true')
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if args.kilo_jsonc:
        raw = Path(args.kilo_jsonc).read_bytes()
        text = raw.decode('utf-8')
        result = check_kilo_jsonc(json.loads(text))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result['ok'] else 1
    if args.state:
        result = check_state(json.loads(Path(args.state).read_bytes()))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result['ok'] else 1
    print('укажите --kilo-jsonc, --state или --selftest', file=sys.stderr)
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
