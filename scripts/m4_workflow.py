#!/usr/bin/env python3
"""Explicit M4 fixture scope using the existing private-report/source workflow."""
import argparse
from pathlib import Path
import sys
import tempfile

import dev
from m3_workflow import Run, source_digest, ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path(tempfile.gettempdir()).resolve() / 'hids-m4-workflow')
    parser.add_argument('--expected-manifest', help='Require a verified immutable source snapshot on Ubuntu')
    args = parser.parse_args()
    if args.expected_manifest:
        dev.verify(ROOT, args.expected_manifest)
    run = Run(args.output, 'm4_synthetic_pilot', source_digest())
    error = None
    try:
        run.phase('python', [sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'tests/unit', '-p', 'test_m4*.py'])
        run.phase('m3_regression', [sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'tests/unit', '-p', 'test_m3*.py'])
        run.phase('demo', [sys.executable, '-B', 'scripts/m4_pilot.py', '--store', str(run.path / 'demo-store')])
        if args.expected_manifest:
            dev.verify(ROOT, args.expected_manifest)
    except Exception as exc:
        error = str(exc)
    run.finish(error)
    return 1 if error else 0


if __name__ == '__main__':
    raise SystemExit(main())
