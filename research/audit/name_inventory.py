#!/usr/bin/env python3
"""Инвентарь имён в ограниченном наборе текстов; не читает секреты и архивы."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
EXTRA = {
    'research/README.md', 'research/kilo/ROADMAP.md', 'research/kilo/REVISION-ROADMAP-IMPLEMENTATION.md',
    'research/kilo/roadmap-evaluation/PROTOCOL.md', 'research/kilo/roadmap-evaluation/QUESTIONS.md',
    'research/kilo/roadmap-evaluation/RUBRIC.md', 'research/kilo/roadmap-evaluation/SELF-REVIEW.md',
    'research/kilo/NAME-CHANGE-ANALYSIS.md', 'research/audit/test_roadmap_contract.py',
    'research/audit/name_inventory.py', 'research/audit/test_name_inventory.py',
}
EXTENSIONS = {'.md', '.json', '.py', '.txt', '.html', '.toml', '.yml', '.yaml'}
EXCLUDED = re.compile(r'(?i)(?:^|/)(?:\.env(?:\.|$)|[^/]*(?:credential|secret|private[-_]?key)[^/]*)')
PATTERNS = {
    'old_brand': re.compile(r'Agent[ _-]*Contract[ _-]*Kit', re.I),
    'new_brand': re.compile(r'Domain[ _-]*Agent[ _-]*Kit', re.I),
    'donor_lab': re.compile(r'Agent[ _-]*Contract[ _-]*Lab', re.I),
    'project_path': re.compile(r'\.agent-contract', re.I),
    'kit_import': re.compile(r'\b(?:from|import)\s+kit\b'),
    'donor_version': re.compile(r'0\.1\.36'),
    'candidate_version': re.compile(r'0\.2\.0'),
}
MAX_BYTES = 3_000_000


def area(name):
    if name.startswith('kit/'):
        return 'candidate_kit'
    if name.startswith('research/kilo/'):
        return 'kilo_docs_and_history'
    if name.startswith('research/audit/'):
        return 'audit'
    if name.startswith('research/'):
        return 'historical_research_and_policy'
    return 'root_reference'


def allowed(name):
    p = PurePosixPath(name)
    return (not p.is_absolute() and '..' not in p.parts
            and (name.startswith(('kit/', 'research/')) or name in ('README.md', 'AGENTS.md'))
            and p.suffix.lower() in EXTENSIONS and not EXCLUDED.search(name)
            and not any(part in {'.isai', '.git', 'profiles', 'node_modules'} for part in p.parts)
            and name != 'research/kilo/NAME-CHANGE-INVENTORY.json')


def scan_content(text):
    """Чистый анализ одного предоставленного текста, без выдачи текста/фрагментов."""
    return {key: len(found) for key, pattern in PATTERNS.items() if (found := pattern.findall(text))}


def build(root, names):
    root = Path(root)
    files, skipped = [], []
    for name in sorted(set(names)):
        if not allowed(name):
            continue
        path = root / name
        try:
            if (any((root.joinpath(*PurePosixPath(name).parts[:i])).is_symlink()
                    for i in range(1, len(PurePosixPath(name).parts)))
                    or path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES):
                skipped.append(name)
                continue
            raw = path.read_bytes()
            if b'\x00' in raw:
                skipped.append(name)
                continue
            text = raw.decode('utf-8')
        except (OSError, UnicodeError):
            skipped.append(name)
            continue
        hits = scan_content(text)
        files.append({'path': name, 'area': area(name), 'hits': hits})
    artifact_paths = sorted(name for name in set(names)
                            if name.startswith(('kit/', 'research/', 'dist/'))
                            and not EXCLUDED.search(name)
                            and PurePosixPath(name).suffix.lower() == '.zip'
                            and (PATTERNS['old_brand'].search(name) or PATTERNS['donor_lab'].search(name)))
    return {'format': 1, 'scope': 'tracked-allowed-text-plus-explicit-working-files',
            'scanned_files': len(files), 'skipped_files': skipped,
            'archive_paths_only_not_opened': artifact_paths,
            'matches': [row for row in files if row['hits']]}


def main():
    raw = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT, check=True, stdout=subprocess.PIPE).stdout
    names = {name.decode('utf-8', 'surrogateescape') for name in raw.split(b'\0') if name} | EXTRA
    report = build(ROOT, names)
    print(json.dumps(report, ensure_ascii=True, sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
