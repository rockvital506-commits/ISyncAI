#!/usr/bin/env python3
"""A-001: аудит машины состояний на выпуске 0.1.26.

Прогоняет опубликованную команду в отдельном процессе и сверяет факты с эталоном состояний:
`draft → active ⇄ suspended → revoked`, `revoked` — терминальное, проект может быть `retired`.

Разделы:
  1. matrix         — все 16 пар переходов для контракта и правила;
  2. effect         — что каждое состояние делает с действующим набором (`list`) и счётом (`metrics`);
  3. child          — можно ли создать правило под контрактом в каждом состоянии;
  4. ops            — как ведут себя edit / review / purge / due в каждом состоянии записи;
  5. retire         — что даёт retired проекта;
  6. invariants     — сходится ли счёт состояний с `list` и `metrics`.

Запуск: python3 state_audit.py --tree ../release-0.1.26/base/AgentContractLab --out AUDIT-0.1.26.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

STATES = ('draft', 'active', 'suspended', 'revoked')
ALLOWED = {('draft', 'active'), ('draft', 'revoked'), ('active', 'suspended'), ('active', 'revoked'),
           ('suspended', 'active'), ('suspended', 'revoked')}


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


class Lab:
    def __init__(self, tree, root):
        self.tree = pathlib.Path(tree).absolute()
        self.root = pathlib.Path(root)
        self.lab = self.root / 'lab'
        self.proj = self.root / 'proj'
        shutil.copytree(self.tree, self.lab)
        self.proj.mkdir(parents=True)
        (self.proj / 'demo.txt').write_text('аудит\n', encoding='utf-8')
        self.version = json.loads((self.lab / 'releases/0.1.26/manifest.json').read_text())['base_version']

    def cli(self, command, payload=None):
        proc = subprocess.run([sys.executable, '-I', '-B', str(self.lab / 'kit/tools/contract.py'),
                               '--lab', str(self.lab), '--project', str(self.proj), command],
                              input=json.dumps(payload).encode() if payload is not None else b'',
                              capture_output=True, timeout=60)
        try:
            out = json.loads(proc.stdout.decode())
        except Exception:
            out = {'raw': proc.stdout.decode()[:300], 'stderr': proc.stderr.decode()[-300:]}
        return proc.returncode, out

    def install(self):
        folder = 'releases/' + self.version
        rc, out = self.cli('plan', {'op': 'install', 'package': folder,
                                    'pin': sha(self.lab / folder / 'manifest.json')})
        assert rc == 0, out
        rc, out = self.cli('apply', {'request': {'op': 'install', 'package': folder,
                                                 'pin': sha(self.lab / folder / 'manifest.json')},
                                     'ticket': out['ticket']})
        assert rc == 0, out
        self.ok({'op': 'connect'})
        return out

    def ok(self, request, extra=None):
        payload = dict(request, **extra) if extra else request
        rc, view = self.cli('plan', payload)
        if rc == 0 and not view.get('changes'):
            return 'no_change'
        assert rc == 0, (payload, view)
        rc, out = self.cli('apply', {'request': payload, 'ticket': view['ticket']})
        assert rc == 0, (payload, out)
        return out['outcome']

    def refused(self, payload):
        rc, view = self.cli('plan', payload)
        return ('ok' if rc == 0 else view.get('error'))

    def entry(self, ident):
        rc, out = self.cli('status')
        rc, hist = self.cli('history')
        for d in hist['decisions']:
            pass
        raw = json.loads((self.proj / '.agent-contract/project/state.json').read_text())
        for e in raw['entries']:
            if e['id'] == ident:
                return e
        return None


def last_id(lab):
    raw = json.loads((lab.proj / '.agent-contract/project/state.json').read_text())
    return raw['entries'][-1]['id']


def build_state(lab, kind, target, n, contract='P-1'):
    """Создаёт запись, доводит её до target и возвращает id."""
    if kind == 'contract':
        base = dict(op='create', kind='contract', title='к%s' % n, scope='.', text='контракт',
                    basis='fixture', criterion='observable', reason='аудит')
    else:
        base = dict(op='create', kind='rule', contract=contract, title='п%s' % n, scope='.', text='правило',
                    basis='fixture', criterion='observable', reason='аудит')
    if target in ('draft', 'active'):
        lab.ok(base, {'state': target})
    else:
        lab.ok(base, {'state': 'active'})
    ident = last_id(lab)
    if target == 'suspended':
        assert lab.ok(dict(op='transition', id=ident, to='suspended', reason='аудит')) == 'committed'
    elif target == 'revoked':
        assert lab.ok(dict(op='transition', id=ident, to='revoked', reason='аудит')) == 'committed'
    return ident


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tree', required=True)
    ap.add_argument('--out', default='AUDIT-0.1.26.json')
    args = ap.parse_args()
    root = pathlib.Path(tempfile.mkdtemp(prefix='audit-'))
    lab = Lab(args.tree, root)
    lab.install()
    report = {'release': lab.version, 'at': '2026-11-18', 'states': list(STATES),
              'allowed_expected': sorted('%s→%s' % p for p in ALLOWED)}

    # 1. матрица переходов
    matrix = {}
    n = 2
    for kind in ('contract', 'rule'):
        fresh = Lab(args.tree, tempfile.mkdtemp(prefix='audit-matrix-'))
        fresh.install()
        contract_id = None
        if kind == 'rule':
            fresh.ok(dict(op='create', kind='contract', title='к', scope='.', text='контракт',
                          basis='fixture', criterion='observable', state='active', reason='аудит'))
            contract_id = last_id(fresh)
        rows = {}
        for frm in STATES:
            for to in STATES:
                ident = build_state(fresh, kind, frm, n, contract_id or 'P-1')
                n += 1
                res = fresh.refused(dict(op='transition', id=ident, to=to, reason='аудит'))
                rows['%s→%s' % (frm, to)] = res
                if res == 'ok':
                    fresh.ok(dict(op='transition', id=ident, to=to, reason='аудит'))
        matrix[kind] = rows
    report['matrix'] = matrix
    report['matrix_gaps'] = sorted(
        k for kind in matrix for k, v in matrix[kind].items()
        if (v == 'ok') != (tuple(k.split('→')) in ALLOWED))

    # 2. влияние состояний на набор
    lab2 = Lab(args.tree, tempfile.mkdtemp(prefix='audit-effect-'))
    lab2.install()
    lab2.ok(dict(op='create', kind='contract', title='к', scope='.', text='контракт', basis='fixture',
                 criterion='observable', state='active', reason='аудит'))
    lab2.ok(dict(op='create', kind='rule', contract='P-1', title='п', scope='.', text='правило',
                 basis='fixture', criterion='observable', state='active', reason='аудит'))
    effect = {}
    def snap(tag):
        _, lst = lab2.cli('list', {})
        _, met = lab2.cli('metrics', {})
        effect[tag] = {'list_active': len(lst.get('active', [])),
                       'metrics_active': met.get('active', {}).get('count'),
                       'metrics_hidden': met.get('hidden', {}).get('count'),
                       'metrics_noise': met.get('noise', {}).get('count'),
                       'metrics_revoked': met.get('revoked', {}).get('count')}
    snap('active')
    lab2.ok(dict(op='transition', id='P-1', to='suspended', reason='аудит')); snap('contract_suspended')
    lab2.ok(dict(op='transition', id='P-1', to='active', reason='аудит'))
    lab2.ok(dict(op='transition', id='P-2', to='suspended', reason='аудит')); snap('rule_suspended')
    lab2.ok(dict(op='transition', id='P-2', to='active', reason='аудит'))
    lab2.ok(dict(op='transition', id='P-1', to='revoked', reason='аудит')); snap('contract_revoked')
    report['effect'] = effect

    # 3. создание ребёнка под каждым состоянием контракта
    child = {}
    for state in STATES:
        l3 = Lab(args.tree, tempfile.mkdtemp(prefix='audit-child-'))
        l3.install()
        ident = build_state(l3, 'contract', state, 1)
        res = l3.refused(dict(op='create', kind='rule', contract=ident, title='ребёнок', scope='.',
                              text='правило', basis='fixture', criterion='observable', state='active',
                              reason='аудит'))
        child[state] = res
    report['child_under_contract'] = child

    # 3b. активный ребёнок под каждым состоянием контракта и активация существующего
    child_active, activate_child = {}, {}
    for state in STATES:
        l3b = Lab(args.tree, tempfile.mkdtemp(prefix='audit-child-active-'))
        l3b.install()
        ident = build_state(l3b, 'contract', state, 1)
        child_active[state] = l3b.refused(dict(op='create', kind='rule', contract=ident, title='активный',
                                               scope='.', text='правило', basis='fixture',
                                               criterion='observable', state='active', reason='аудит'))
        l3b.ok(dict(op='create', kind='rule', contract=ident, title='черновик', scope='.',
                    text='правило', basis='fixture', criterion='observable', state='draft', reason='аудит'))
        activate_child[state] = l3b.refused(dict(op='transition', id=last_id(l3b), to='active',
                                                 reason='аудит'))
    report['child_active_under_contract'] = child_active
    report['activate_child_under_contract'] = activate_child

    # 3c. форма due и причины скрытого
    l3c = Lab(args.tree, tempfile.mkdtemp(prefix='audit-due-'))
    l3c.install()
    l3c.ok(dict(op='create', kind='contract', title='к', scope='.', text='контракт', basis='fixture',
                criterion='observable', state='active', reason='аудит'))
    l3c.ok(dict(op='create', kind='rule', contract='P-1', title='черновик', scope='.', text='правило',
                basis='fixture', criterion='observable', state='draft', reason='аудит'))
    l3c.ok(dict(op='create', kind='rule', contract='P-1', title='действует', scope='.', text='правило',
                basis='fixture', criterion='observable', state='active', reason='аудит'))
    _, due = l3c.cli('due', {})
    report['due_shape'] = {'count': due.get('count'), 'fields': sorted(due['due'][0]) if due.get('due') else [],
                           'states': sorted({d.get('state') for d in due.get('due', [])}, key=str)}
    l3c.ok(dict(op='transition', id='P-1', to='suspended', reason='аудит'))
    _, met = l3c.cli('metrics', {})
    report['hidden_shape'] = {'count': met['hidden']['count'], 'ids': met['hidden']['ids'],
                              'fields': sorted(met['hidden']), 'by_reason': met['hidden'].get('by_reason')}

    # 4. операции в каждом состоянии записи
    ops = {}
    for state in STATES:
        l4 = Lab(args.tree, tempfile.mkdtemp(prefix='audit-ops-'))
        l4.install()
        l4.ok(dict(op='create', kind='contract', title='к', scope='.', text='контракт', basis='fixture',
                   criterion='observable', state='active', reason='аудит'))
        ident = build_state(l4, 'rule', state, 2, last_id(l4))
        ops[state] = {
            'edit': l4.refused(dict(op='edit', id=ident, fields=dict(text='иначе'), reason='аудит')),
            'review': l4.refused(dict(op='review', id=ident, reason='аудит')),
            'purge': l4.refused(dict(op='purge', id=ident, allow_delete=True, reason='аудит')),
            'due_contains': None,
        }
        _, due = l4.cli('due', {})
        ops[state]['due_contains'] = any(d['id'] == ident for d in due.get('due', []))
    report['ops_by_state'] = ops

    # 5. retired проекта
    l5 = Lab(args.tree, tempfile.mkdtemp(prefix='audit-retire-'))
    l5.install()
    l5.ok(dict(op='create', kind='contract', title='к', scope='.', text='контракт', basis='fixture',
               criterion='observable', state='active', reason='аудит'))
    l5.ok(dict(op='create', kind='rule', contract='P-1', title='п', scope='.', text='правило',
               basis='fixture', criterion='observable', state='active', reason='аудит'))
    l5.ok(dict(op='retire', allow_delete=True))
    _, lst = l5.cli('list', {})
    _, met = l5.cli('metrics', {})
    report['retired'] = {'list_active': len(lst.get('active', [])),
                         'metrics_active': met['active']['count'],
                         'metrics_hidden': met['hidden']['count'],
                         'metrics_hidden_ids': met['hidden']['ids'],
                         'status_health': l5.cli('status')[1].get('health')}

    # 6. инварианты счёта
    _, met = l5.cli('metrics', {})
    by_state = met['entries']['by_state']
    report['invariants'] = {
        'sum_states_eq_total': sum(by_state.values()) == met['entries']['total'],
        'active_le_by_state': met['active']['count'] <= by_state.get('active', 0),
        'hidden_le_active': met['hidden']['count'] <= by_state.get('active', 0),
        'noise_le_draft_suspended': met['noise']['count'] <= by_state.get('draft', 0) + by_state.get('suspended', 0),
        'revoked_eq_by_state': met['revoked']['count'] == by_state.get('revoked', 0),
    }

    pathlib.Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
                                      encoding='utf-8')
    print(json.dumps({'release': report['release'], 'matrix_gaps': report['matrix_gaps'],
                      'child': report['child_under_contract'],
                      'child_active': report['child_active_under_contract'],
                      'activate_child': report['activate_child_under_contract'],
                      'due_shape': report['due_shape'], 'hidden_shape': report['hidden_shape'],
                      'retired': report['retired'], 'invariants': report['invariants']},
                     ensure_ascii=False, indent=1))
    shutil.rmtree(root, ignore_errors=True)


if __name__ == '__main__':
    main()
