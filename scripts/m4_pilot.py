#!/usr/bin/env python3
"""Run the approved synthetic-only demo in a NEW private store. No live input."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.detection.m4_pilot import Store, load_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--store', type=Path, required=True, help='New canonical directory; must not already exist')
    args = parser.parse_args()
    event = load_json(ROOT / 'tests/fixtures/m4/execution.json')
    rule = load_json(ROOT / 'rules/pilot/configured-executable.json')
    with Store(args.store, create=True) as store:
        key = store.receive(event, rule)
        result = store.evaluate(key, rule['id'], rule['revision'])
        alert = store.db.execute('SELECT alert_id,explanation,severity FROM m4p_alerts').fetchone()
        if result != 'matched' or alert is None:
            raise RuntimeError('synthetic demo did not produce its expected alert')
        print(json.dumps(dict(synthetic=True, demo=True, event_key=key, result=result,
            alert_id=alert[0], explanation=alert[1], severity=alert[2]), sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
