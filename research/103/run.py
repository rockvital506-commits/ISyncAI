#!/usr/bin/env python3
"""Драйвер И-103: П3–П8 с дополнительной пробой версий, без изменений Kit."""
from pathlib import Path
import sys

from version_probe import collect

HERE = Path(__file__).resolve().parent
STRATEGY = HERE.parent / 'strategy'
sys.path.insert(0, str(STRATEGY / 'harness'))
import probes
from run_iteration import main


def versioning(artifact):
    return collect(artifact, STRATEGY / 'COMPATIBILITY.json', probes)


if __name__ == '__main__':
    raise SystemExit(main(['--spec', str(HERE / 'ITERATION.json'), *sys.argv[1:]],
                          extra_probes={'versioning': ('VERSION-EVIDENCE.json', versioning)}))
