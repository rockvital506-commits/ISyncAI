#!/usr/bin/env python3
"""Адаптация известных локальных исторических тестов к новому пути/подписному формату.

Это новые пробы, не повтор прежних печатей. Исходные тесты и CASES.json не изменяются.
Выполнять каждый номер отдельным процессом: старые тесты ставят необратимые audit hooks.
"""
import ast
import copy
import hashlib
import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'research/audit')]
import core_audit

FILES = {114: 'test_promotion.py', 115: 'test_simulation.py', 116: 'test_conflict_review.py',
         119: 'test_bundle_trust.py', 120: 'test_bundle_rollback.py'}
OLD_DOMAIN = b'AgentContractKit:bundle-signature:v1\x00'
NEW_DOMAIN = b'DomainAgentKit:bundle-signature:v2\x00'
TEST_SEED = bytes.fromhex('9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60')
TEST_PUBLIC = bytes.fromhex('d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a')


class Retarget(ast.NodeTransformer):
    def __init__(self, signature=False):
        self.signature = signature
        self.domains = self.envelopes = 0

    def visit_Constant(self, node):
        if isinstance(node.value, str):
            node.value = core_audit.translated_paths(node.value)
        elif self.signature and node.value == OLD_DOMAIN:
            node.value = NEW_DOMAIN
            self.domains += 1
        return node

    def visit_Dict(self, node):
        self.generic_visit(node)
        keys = [k.value if isinstance(k, ast.Constant) else None for k in node.keys]
        if self.signature and {'format', 'algorithm', 'key_id', 'signature'} <= set(keys):
            i = keys.index('format')
            if not isinstance(node.values[i], ast.Constant) or node.values[i].value != 1:
                raise ValueError('unexpected historical signature envelope')
            node.values[i].value = 2
            self.envelopes += 1
        return node


def load(number):
    path = ROOT/'research'/str(number)/FILES[number]
    spec = importlib.util.spec_from_file_location('domain_adapted_'+str(number), path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    transform = Retarget(signature=number in (119, 120))
    tree = transform.visit(ast.parse(path.read_text(encoding='utf-8'), filename=str(path)))
    if number == 119 and (transform.domains, transform.envelopes) != (1, 1):
        raise ValueError('unexpected historical 119 source')
    if number == 120 and (transform.domains, transform.envelopes) != (0, 1):
        raise ValueError('unexpected historical 120 source')
    exec(compile(tree, str(path), 'exec'), module.__dict__)
    return module


class JsonProxy:
    def __init__(self, adjust):
        self.adjust = adjust
    def loads(self, *args, **kwargs):
        return self.adjust(json.loads(*args, **kwargs))
    def __getattr__(self, name):
        return getattr(json, name)


def retarget_119(module):
    book = json.loads((ROOT/'research/119/CASES.json').read_bytes())
    archives, integrity = module.fixtures()
    key_id = hashlib.sha256(TEST_PUBLIC).hexdigest()
    sigs = {}
    with tempfile.TemporaryDirectory(prefix='domain-agentkit-rfc-test-') as d:
        root = pathlib.Path(d)
        key = root/'rfc-test-key.der'
        key.write_bytes(bytes.fromhex('302e020100300506032b657004220420') + TEST_SEED)
        for name in ('source', 'alternate'):
            message = NEW_DOMAIN + bytes.fromhex(key_id) + bytes.fromhex(integrity[name]['archive_sha256'])
            (root/'message').write_bytes(message)
            p = subprocess.run(['/usr/bin/openssl', 'pkeyutl', '-sign', '-rawin', '-keyform', 'DER',
                                '-inkey', str(key), '-in', str(root/'message'), '-out', str(root/'signature')],
                               stdin=subprocess.DEVNULL, capture_output=True, timeout=20)
            if p.returncode:
                raise RuntimeError('test signer unavailable')
            sigs[name] = (root/'signature').read_bytes()
    book['public'] = {'key': TEST_PUBLIC.hex(), 'key_id': key_id,
                      'signatures': {key: value.hex() for key, value in sigs.items()}}
    ctx = (archives, integrity, TEST_PUBLIC, key_id, sigs)
    checks = 0
    for case in book['cases']:
        expected = module.expected_call(ctx, case)
        case['verifier_input'] = module.call_digest(expected) if expected else None
        checks += bool(expected)
    if checks != 8:
        raise ValueError('unexpected historical 119 verifier case count')
    def adjust(obj):
        if isinstance(obj, dict) and {'archive_sha256', 'baseline', 'cases', 'integrity', 'public'} <= obj.keys():
            return copy.deepcopy(book)
        return obj
    module.json = JsonProxy(adjust)


def retarget_120(module):
    historical = json.loads((ROOT/'research/120/CASES.json').read_bytes())
    original_values = {x['project_sha256'] for x in historical['readbacks'].values()}
    if len(original_values) != 1:
        raise ValueError('unexpected historical project fixture')
    old = original_values.pop()
    new = hashlib.sha256(module.PROJECT).hexdigest()
    if old == new:
        raise ValueError('project fixture did not change')
    def replace(value):
        if isinstance(value, dict):
            return {k: (new if k == 'project_sha256' and v == old else replace(v)) for k, v in value.items()}
        if isinstance(value, list):
            return [replace(v) for v in value]
        return value
    module.json = JsonProxy(replace)


def main(number):
    if number not in FILES:
        raise ValueError('unsupported case')
    if number == 115:
        sys.modules['test_promotion'] = load(114)
    module = load(number)
    if number == 115:
        # Текущий раздел изменён намеренно; исторический фиксированный размер остаётся
        # в неизменённом тесте. Адаптируем явный размер, не вычисляя его из результата.
        if (module.ENTRY_BYTES, module.SECTION_BYTES) != (20, 2363):
            raise ValueError('unexpected historical 115 section size')
        module.SECTION_BYTES = 2861
        module.json = JsonProxy(core_audit.translated_paths)
        # Новое штатное чтение открывает только корень каждой синтетической раскладки
        # как каталог для shared flock. Остальные ограничения исторического monitor сохранены.
        original_event = module.Monitor.event
        def event(monitor, event_name, args):
            if monitor.active and event_name == 'open' and monitor.root is not None:
                path, _, flags = args
                rel = monitor.local(path)
                allowed = {pathlib.Path(fixture) / variant for fixture in module.FIXTURES for variant in module.VARIANTS}
                writes = module.os.O_WRONLY | module.os.O_RDWR | module.os.O_CREAT | module.os.O_TRUNC | module.os.O_APPEND
                profiles = {root / 'profiles/staged' for root in allowed}
                if rel in allowed | profiles and flags & module.os.O_DIRECTORY and not flags & writes:
                    return
            if monitor.active and event_name == 'os.listdir' and type(args[0]) is int:
                try:
                    fdpath = pathlib.Path(module.os.readlink('/proc/self/fd/' + str(args[0])))
                    rel = monitor.local(str(fdpath))
                    profiles = {pathlib.Path(fixture) / variant / 'profiles/staged'
                                for fixture in module.FIXTURES for variant in module.VARIANTS}
                    if rel in profiles:
                        return
                except OSError:
                    pass
            return original_event(monitor, event_name, args)
        module.Monitor.event = event
    elif number == 116:
        get = module.get
        module.get = lambda path: core_audit.translated_paths(get(path)) if path == 'research/115/CASES.json' else get(path)
    elif number == 119:
        retarget_119(module)
    elif number == 120:
        retarget_120(module)
    return module.main()


if __name__ == '__main__':
    raise SystemExit(main(int(sys.argv[1])))
