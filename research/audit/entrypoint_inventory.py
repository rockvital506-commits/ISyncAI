#!/usr/bin/env python3
"""Статическая инвентаризация явных Python __main__ в kit; не security-аудит."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
# Классификация — исследовательская; документ не наделяет точки входа доверием.
CLASSES = {
    'compare_old.py': 'diagnostic',
    'copilot_deploy.py': 'adapter_write',
    'guard.py': 'guard',
    'guard_tree.py': 'guard',
    'init_workspace_cli.py': 'initialization_write',
    'kilo_deploy.py': 'adapter_write',
    'kilo_inspect.py': 'diagnostic',
    'legacy_capsule.py': 'diagnostic',
    'legacy_projection.py': 'diagnostic',
    'move_recovery_inspect.py': 'diagnostic',
    'move_session_cli.py': 'move_write',
    'preview_rule.py': 'diagnostic',
    'profile_copy.py': 'profile_write',
    'render_rule.py': 'diagnostic',
    'session_cli.py': 'registry_write',
    'snapshot_export.py': 'delivery_write',
    'snapshot_move_session.py': 'move_write',
    'snapshot_session.py': 'registry_write',
    'source_release_trust.py': 'guard',
    'terminal_init.py': 'initialization_write',
    'terminal_move.py': 'move_write',
    'terminal_recovery.py': 'move_write',
    'terminal_session.py': 'registry_write',
    'verify_candidate.py': 'guard',
}
def _is_main(node):
    if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
        return False
    test = node.test
    return (isinstance(test.left, ast.Name) and test.left.id == '__name__'
            and len(test.ops) == 1 and isinstance(test.ops[0], ast.Eq)
            and len(test.comparators) == 1 and isinstance(test.comparators[0], ast.Constant)
            and test.comparators[0].value == '__main__')


def inventory(root):
    root = Path(root)
    result = []
    for path in sorted((root / 'kit').rglob('*.py')):
        if any(part == '__pycache__' for part in path.parts) or path.is_symlink():
            continue
        raw = path.read_bytes()
        tree = ast.parse(raw, filename=str(path))
        if not any(_is_main(node) for node in tree.body):
            continue
        rel = path.relative_to(root / 'kit').as_posix()
        category = CLASSES.get(rel)
        if category is None:
            raise ValueError('unclassified_entrypoint:' + rel)
        result.append({'path': 'kit/' + rel, 'category': category,
                       'sha256': hashlib.sha256(raw).hexdigest()})
    expected = set(CLASSES)
    observed = {row['path'].removeprefix('kit/') for row in result}
    if expected != observed:
        raise ValueError('missing_classified_entrypoint:' + ','.join(sorted(expected - observed)))
    return {'format': 1, 'basis': 'explicit_top_level_name_main_only', 'entries': result,
            'limitations': ['dynamic_execution_not_detected', 'imported_library_api_not_enumerated',
                            'no_security_or_environment_attestation']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', type=Path)
    args = parser.parse_args()
    try:
        data = (json.dumps(inventory(ROOT), ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode()
        if args.check is not None:
            if args.check.read_bytes() != data:
                print('entrypoint_inventory_mismatch', file=sys.stderr)
                return 1
            print('entrypoint_inventory_pass')
        else:
            sys.stdout.buffer.write(data)
        return 0
    except (OSError, ValueError, SyntaxError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
