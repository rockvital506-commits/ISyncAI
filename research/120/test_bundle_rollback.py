#!/usr/bin/env python3
"""И-120: независимые байты N-1, оракул истории, наблюдение замены и штатное чтение v2."""
from collections import Counter
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from hashlib import sha256
from importlib import import_module
from io import BytesIO, StringIO
import json
import os
from pathlib import Path
import platform
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zipfile import ZipFile, ZipInfo

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BOOK = 'research/120/CASES.json'
TEST = 'research/120/test_bundle_rollback.py'
MODULE = 'kit/base/bundle_rollback.py'
SOURCE = 'research/117/Synthetic-Bundle-117.zip'
PUBLIC = 'research/119/CASES.json'
META, L0, L1, L2 = 'manifest.json', 'kit/base/registry.json', 'profiles/staged/registry.json', '.agent-contract/project/registry.json'
ENTRY = 'R-sample-117'
NOW, EXPIRY = '2026-11-18T12:00:00Z', '2026-11-18T12:00:01Z'
BASELINE = '83553b045b640d69dccb476fe10ab7e04f0e9c86'
APPROVER = 'stand-approver-120'
COUNTS = ('pass', 'fail', 'not run')

sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
from kit.base.bundle_verify import bundle_verify
from kit.base.registry_policy import StoreError, check_operation
from kit.base.registry_store import Layout, read_registry, status


def canon(obj):
    return json.dumps(obj, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def packet(obj):
    return canon(obj) + b'\n'


def H(raw):
    return sha256(raw).hexdigest() if raw is not None else None


PROJECT = packet({'schema_version': 2, 'area': 'L2', 'roots': ['.agent-contract'], 'revision': 3, 'entries': []})


def fail(code, where, reason):
    return {'code': code, 'where': where, 'details': {'reason': reason}}


def compose(items):
    with BytesIO() as stream:
        with ZipFile(stream, 'w', allowZip64=False) as z:
            for n, data in sorted(items.items()):
                i = ZipInfo(n); i.create_system, i.external_attr = 3, 0o100644 << 16
                z.writestr(i, data)
        return stream.getvalue()


def rule(profile):
    return next(r for r in profile['entries'] if r['id'] == ENTRY)


def fixtures():
    """Тестовые ZIP сделаны без продукта И-120 и без вызова сборщика И-117."""
    source = (ROOT/SOURCE).read_bytes()
    with ZipFile(BytesIO(source)) as z:
        assert len(z.namelist()) == 17 and z.testzip() is None
        base = {n: z.read(n) for n in z.namelist() if n != META}
        original = z.read(META)
    l1 = json.loads(base[L1]); revision = l1['revision']; assert revision == 7
    system = json.loads(base[L0]); assert system['entries'] == []

    def manifest(payload):
        body = {'revision': revision, 'roots': ['kit', 'profiles/staged'],
                'files': [{'path': n, 'size': len(b), 'sha256': H(b)} for n, b in sorted(payload.items())]}
        return dict(body, digest=H(canon(body)))

    assert original == packet(manifest(base)) and source == compose({**base, META: original})
    packs, refs, reads, payloads, manifests = {}, {}, {}, {}, {}
    for k in ('A', 'B', 'C', 'B_rebuilt'):
        payload = dict(base)
        profile = deepcopy(l1)
        if k != 'A':
            rule(profile)['text'] = f'Synthetic readback I-120: {k}.'
            payload[L1] = packet(profile)
        m = manifest(payload)
        raw = compose({**payload, META: packet(m)})
        packs[k], payloads[k], manifests[k] = raw, payload, packet(m)
        refs[k] = {'bundle_format': 1, 'outcome': 'verified', 'revision': revision, 'manifest_digest': m['digest'], 'archive_sha256': H(raw)}
        reads[k] = {'archive_sha256': H(raw), 'profile_sha256': H(payload[L1]), 'rule_text_sha256': H(rule(profile)['text'].encode()),
                    'system_sha256': H(base[L0]), 'project_sha256': H(PROJECT), 'release_version': system['release_version'],
                    'profile_revision': revision, 'project_revision': 3, 'reader_unchanged': True}
    assert len({x['profile_sha256'] for x in reads.values()}) == 4
    # Один и тот же размер при повреждении: CRC корректен, но SHA-256 члена нет.
    for k in ('B', 'C'):
        good = json.loads(payloads[k][L1]); choice = rule(good)
        assert choice['text'].endswith('.')
        choice['text'] = choice['text'][:-1] + '!'
        flipped = packet(good); assert len(flipped) == len(payloads[k][L1])
        packs[k + '_bad'] = compose({**payloads[k], L1: flipped, META: manifests[k]})
    packs['B_incomplete'] = compose(payloads['B'])
    assert packs['A'] == source and len({H(b) for b in packs.values()}) == len(packs)
    return packs, refs, reads


def verified_reader(raw, active):
    """Наблюдатель стенда, не установщик: два фиксированных члена как данные, L2 не из ZIP."""
    info = bundle_verify(raw)
    assert info['archive_sha256'] == active
    with ZipFile(BytesIO(raw)) as z:
        blobs = {L0: z.read(L0), L1: z.read(L1), L2: PROJECT}
    with TemporaryDirectory(prefix='ack-i120-consumer-') as d:
        root = Path(d).resolve()
        for name, b in blobs.items():
            f = root/name; f.parent.mkdir(parents=True, exist_ok=True); f.write_bytes(b)
        layout = Layout(root, 'profiles/staged')
        pre = {n: file_stamp(root/n) for n in blobs}
        facts = status(layout)
        profile = read_registry(layout, target='L1')
        project = read_registry(layout, target='L2')
        assert canon(profile) == canon(json.loads(blobs[L1])) and canon(project) == canon(json.loads(PROJECT))
        unchanged = pre == {n: file_stamp(root/n) for n in blobs}
        unchanged &= sorted(f.relative_to(root).as_posix() for f in root.rglob('*') if f.is_file()) == sorted(blobs)
    return {'archive_sha256': info['archive_sha256'], 'profile_sha256': H(blobs[L1]), 'rule_text_sha256': H(rule(profile)['text'].encode()),
            'system_sha256': H(blobs[L0]), 'project_sha256': H(blobs[L2]), 'release_version': facts['release_version'],
            'profile_revision': facts['profile_revision'], 'project_revision': facts['project_revision'], 'reader_unchanged': unchanged}


def port_control():
    decisions = {}
    for op in ('rollout', 'rollback', 'rollout_status'):
        try:
            check_operation(op, target='L1')
        except StoreError as e:
            decisions[op] = e.code
        else:
            decisions[op] = 'available'
    return decisions


def setup(book):
    packs, refs, reads = fixtures()
    assert book['format'] == 1 and book['baseline'] == BASELINE
    assert canon(refs) == canon(book['integrity']) and canon(reads) == canon(book['readbacks'])
    assert {n: H(b) for n, b in packs.items()} == book['archive_sha256']
    public = json.loads((ROOT/PUBLIC).read_bytes())
    key = bytes.fromhex(public['public']['key']); sig = bytes.fromhex(public['public']['signatures']['source'])
    assert len(key) == 32 and len(sig) == 64 and H(key) == public['public']['key_id']
    assert public['integrity']['source'] == refs['A']
    return packs, key, sig


def control(book, packs):
    for k, receipt in book['integrity'].items():
        assert canon(bundle_verify(packs[k])) == canon(receipt)
    reads = {k: verified_reader(packs[k], book['archive_sha256'][k]) for k in ('A', 'B', 'C')}
    wanted = {k: book['readbacks'][k] for k in reads}
    assert canon(reads) == canon(wanted)
    return {'profiles': reads, 'working_port': port_control(), 'rebuild_integrity': book['integrity']['B_rebuilt']}


# Оракул описывает заранее выбранную историю, не ищет предыдущую запись в результате продукта.
def make_event(book, previous, number, token, decision='optional'):
    name = token.removeprefix('~'); ref = book['integrity'][name]
    return {'seq': number, 'action': 'rollback' if token.startswith('~') else 'rollout', 'from_sha256': previous,
            'to_sha256': ref['archive_sha256'], 'manifest_digest': ref['manifest_digest'], 'revision': ref['revision'],
            'signature_status': 'unsigned', 'policy_decision': decision}


def history_doc(book, tokens):
    active, journal = None, []
    for i, token in enumerate(tokens, 1):
        event = make_event(book, active, i, token)
        journal.append(event); active = event['to_sha256']
    return {'rollout_format': 1, 'active_sha256': active, 'journal': journal}


def advance(doc, event):
    return dict(doc, active_sha256=event['to_sha256'], journal=[*doc['journal'], event])


def broken(book, doc, mutation):
    doc = deepcopy(doc)
    if mutation == 'truncated':
        return b'{"rollout_format":1,"SYNTHETIC_JOURNAL_DO_NOT_ECHO_120"'
    if mutation == 'chain':
        doc['journal'][-1]['from_sha256'] = book['archive_sha256']['A']
    elif mutation == 'head':
        doc['active_sha256'] = book['archive_sha256']['B']
    elif mutation == 'duplicate':
        return b'{"rollout_format":1,' + packet(doc)[1:]
    elif mutation == 'bool_seq':
        doc['journal'][0]['seq'] = True
    elif mutation == 'skip_previous':
        doc = advance(doc, make_event(book, doc['active_sha256'], 4, '~A'))
    elif mutation == 'size':
        return b' ' * (65536 + 1)
    elif mutation == 'receipt':
        doc['journal'][-2]['revision'] += 1
    elif mutation == 'encoding':
        return packet(doc) + b'\n'
    elif mutation == 'version':
        doc['rollout_format'] = 2
    else:
        raise AssertionError('unknown_mutation')
    return packet(doc)


def expected_observation(book, c):
    doc = history_doc(book, c['history']); before = packet(doc)
    mode, operation = c.get('mode'), c['action']
    if c.get('mutation'):
        before = broken(book, doc, c['mutation'])
    initial_hash = H(before)
    if c.get('replacement_history'):
        before = packet(history_doc(book, c['replacement_history']))
    if mode in ('outside', 'reject_target'):
        before = None
    at = c.get('at'); event = None; proposal = None; result = None; attempts = []
    after = before
    if at in (None, 'apply'):
        token = ('~' if operation == 'rollback' else '') + c['candidate']
        decision = 'exception' if c.get('context') == 'exception' else 'optional'
        event = make_event(book, doc['active_sha256'], len(doc['journal']) + 1, token, decision)
        fresh = packet(advance(doc, event))
        proposal = {'plan_format': 1, 'outcome': 'planned', 'target': 'stand', 'state_sha256': initial_hash,
                    'after_sha256': H(fresh), **event}
        if at is None and mode != 'preview':
            after = fresh
            result = {'outcome': 'applied', 'state_sha256': H(after), 'active_sha256': event['to_sha256'], 'event': event}
        if result is not None or mode == 'write_failure':
            attempts.append({'old_sha256': H(before), 'staged_sha256': H(fresh), 'completed': result is not None, 'one_file': True})
    reads = None
    if c.get('witness'):
        current = book['readbacks']['C'] if c['witness'] == 'healthy' else fail('digest_mismatch', 'files', 'sha256')
        reads = {'previous': book['readbacks']['B'], 'current': current, 'restored': book['readbacks']['B']}
    return {'plan': proposal, 'result': result, 'error': c.get('error'), 'at': at, 'state_before': H(before), 'state_after': H(after),
            'file_effect': 'absent' if before is None else 'replaced' if result else 'unchanged', 'replace': attempts,
            'prefix_preserved': True if result else None, 'retry_rejected': True if result or mode in ('retry', 'write_failure') else None,
            'readback': reads, 'cleanup': True, 'context_unchanged': True, 'quiet': True}


def context(book, public, signature, kind, name):
    opts = {'policy': {'require_signature': kind not in ('optional', 'unchecked', 'bad_signature'),
                       'public_keys': (public,), 'exception_approvers': (APPROVER,)},
            'now': NOW, 'signature': None, 'exceptions': ()}
    if kind in ('exception', 'expired', 'wrong_approver', 'wrong_archive'):
        reference = ('A' if name != 'A' else 'B') if kind == 'wrong_archive' else name
        opts['exceptions'] = ({'archive_sha256': book['archive_sha256'][reference], 'expiry': EXPIRY,
                               'approver': 'foreign-approved-by-nobody' if kind == 'wrong_approver' else APPROVER},)
        if kind == 'expired': opts['now'] = EXPIRY
    if kind in ('unchecked', 'bad_signature'):
        opts['signature'] = {'format': 1, 'algorithm': 'ed25519', 'key_id': H(public),
                             'signature': signature if kind == 'unchecked' else b''}
    if kind == 'bad_policy': opts['policy']['require_signature'] = 1
    if kind == 'bad_clock': opts['now'] = '2026-11-18T12:00:00+00:00'
    return opts


def file_stamp(path):
    st = path.lstat()
    return st.st_dev, st.st_ino, st.st_mode, st.st_mtime_ns, path.read_bytes()


def snapshot(path):
    return {f.name: file_stamp(f) for f in path.parent.iterdir()}


def read_active(session, book, packs, *, broken_current=False):
    active = session.status()['active_sha256']
    name = next(k for k, v in book['integrity'].items() if v['archive_sha256'] == active)
    raw = packs[name + '_bad' if broken_current and name == 'C' else name]
    try:
        return verified_reader(raw, active)
    except StoreError as e:
        return e.diagnostic()


def seed(session, book, values, tokens, witness):
    packs, key, sig = values
    prior_read = None
    for i, token in enumerate(tokens, 1):
        t = token.removeprefix('~'); opts = context(book, key, sig, 'optional', t)
        plan = session.plan(packs[t], action='rollback' if t != token else 'rollout', **opts)
        session.apply(plan, confirmed_ticket=plan['ticket'], archive=packs[t], **opts)
        want = history_doc(book, tokens[:i]); assert canon(session.status()) == canon(dict(want, state_sha256=H(packet(want))))
        if witness and i == 2:
            prior_read = read_active(session, book, packs)
    return prior_read


def diagnostic(fn):
    try:
        fn()
    except StoreError as e:
        return e.diagnostic()
    return None


def observe(product, book, values, c):
    packs, key, sig = values
    mode = c.get('mode'); name = c.get('candidate'); apply_name = c.get('apply_candidate', name)
    opts = context(book, key, sig, c.get('context', 'optional'), name)
    updated = context(book, key, sig, c.get('recheck', c.get('context', 'optional')), apply_name)
    before_options = deepcopy((opts, updated))
    plan = None; at = None; error = None; result = None; attempts = []; prefix = None; reused = None; readback = None
    effect = 'absent'; pre_hash = post_hash = None; clean = True
    if mode in ('outside', 'reject_target'):
        with patch.object(product, 'TemporaryDirectory', side_effect=AssertionError('unexpected_workspace')):
            if mode == 'outside':
                at = 'plan'; s = product.RolloutSession()
                error = diagnostic(lambda: s.plan(packs[name], action=c['action'], **opts))
            else:
                def use_live():
                    with product.RolloutSession(target='live'):
                        pass
                at = 'init'; error = diagnostic(use_live)
    else:
        with product.RolloutSession() as s:
            path = s._state_path
            assert isinstance(path, Path) and path.name == 'rollout.json' and path.resolve() == path
            prior = seed(s, book, values, c['history'], c.get('witness'))
            previous = s.status(); raw = path.read_bytes()
            assert H(raw) == previous['state_sha256']
            if c.get('witness'):
                readback = {'previous': prior, 'current': read_active(s, book, packs, broken_current=c['witness'] != 'healthy')}
            if c.get('mutation'):
                path.write_bytes(broken(book, json.loads(raw), c['mutation']))
            before = snapshot(path)
            assert set(before) == {path.name}

            def replace_once(src, dst):
                src, dst = Path(src), Path(dst)
                assert dst == path and src.parent == dst.parent and src != dst and src.resolve() == src
                at_replace = snapshot(path)
                one = set(at_replace) == {path.name, src.name} and at_replace[path.name] == before[path.name]
                trace = {'old_sha256': H(dst.read_bytes()), 'staged_sha256': H(src.read_bytes()), 'one_file': one, 'completed': False}
                attempts.append(trace)
                if mode == 'write_failure':
                    raise OSError('SYNTHETIC_WRITE_DO_NOT_ECHO_120')
                os.replace(src, dst); trace['completed'] = True

            with patch.object(product, 'replace', replace_once):
                try:
                    at = 'plan'; issued = s.plan(packs.get(name), action=c['action'], **opts)
                    assert snapshot(path) == before and type(issued['ticket']) is object
                    plan = {k: v for k, v in issued.items() if k != 'ticket'}; at = None
                    if mode != 'preview':
                        ticket = issued['ticket']
                        if mode in ('no_ticket', 'retry'): ticket = None
                        elif mode == 'foreign_ticket':
                            with product.RolloutSession() as other:
                                # Замена другого собственного файла не является эффектом проверяемой сессии.
                                with patch.object(product, 'replace', os.replace):
                                    seed(other, book, values, c['history'], None)
                                other_plan = other.plan(packs[name], action=c['action'], **opts)
                                assert canon({k:v for k,v in other_plan.items() if k != 'ticket'}) == canon(plan)
                                ticket = other_plan['ticket']
                        elif mode == 'plan_tamper': issued['to_sha256'] = book['archive_sha256']['A']
                        elif mode == 'plan_bool': issued['plan_format'] = True
                        elif mode == 'superseded':
                            bad = diagnostic(lambda: s.plan(packs['B_rebuilt'], action='rollback', **opts))
                            assert bad == fail('rollback_unavailable', 'archive', 'not_previous')
                        if c.get('replacement_history'):
                            path.write_bytes(packet(history_doc(book, c['replacement_history']))); before = snapshot(path)
                        at = 'apply'; result = s.apply(issued, confirmed_ticket=ticket, archive=packs.get(apply_name), **updated); at = None
                except StoreError as e:
                    error = e.diagnostic()
                if result or mode in ('retry', 'write_failure'):
                    reused = diagnostic(lambda: s.apply(issued, confirmed_ticket=issued['ticket'], archive=packs[name], **opts)) == fail('rollout_unconfirmed', 'plan', 'ticket')
            after = snapshot(path)
            assert set(after) == {path.name}
            before_stamp, after_stamp = before[path.name], after[path.name]
            pre_hash, post_hash = H(before_stamp[-1]), H(after_stamp[-1])
            effect = 'unchanged' if before == after else 'replaced' if before_stamp[:2] != after_stamp[:2] else 'in_place'
            if result:
                current = s.status(); new_raw = after_stamp[-1]
                assert canon(current) == canon(dict(json.loads(new_raw), state_sha256=post_hash))
                assert snapshot(path) == after
                prefix = current['journal'][:-1] == previous['journal'] and current['journal'][-1] == result['event']
                if readback: readback['restored'] = read_active(s, book, packs)
        clean = not path.parent.exists()
    return {'plan': plan, 'result': result, 'error': error, 'at': at, 'state_before': pre_hash, 'state_after': post_hash,
            'file_effect': effect, 'replace': attempts, 'prefix_preserved': prefix, 'retry_rejected': reused,
            'readback': readback, 'cleanup': clean, 'context_unchanged': (opts, updated) == before_options}


def main():
    book = json.loads((ROOT/BOOK).read_bytes()); values = setup(book)
    ctl = control(book, values[0]); assert canon(ctl) == canon(book['expected_control'])
    product = import_module('kit.base.bundle_rollback') if (ROOT/MODULE).is_file() else None
    rows = []
    for c in book['cases']:
        row = {'id': c['id']}
        try:
            if product is None:
                rows.append(dict(row, status='fail', reason='bundle_rollback_missing')); continue
            with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()) as stderr:
                obs = observe(product, book, values, c)
            obs['quiet'] = not (stdout.getvalue() or stderr.getvalue())
            match = canon(obs) == canon(expected_observation(book, c))
        except Exception as e:
            rows.append(dict(row, status='fail', reason=type(e).__name__))
        else:
            rows.append(dict(row, status='pass', observation=obs) if match else dict(row, status='fail', reason='oracle_mismatch'))
    count = Counter(r['status'] for r in rows)
    print(json.dumps({'format': 1, 'control': ctl, 'os': platform.system(), 'python': platform.python_version(),
                      'rows': rows, 'counts': {k: count[k] for k in COUNTS}}, ensure_ascii=False, sort_keys=True))
    return int(bool(count['fail'] or count['not run']))


if __name__ == '__main__':
    raise SystemExit(main())
