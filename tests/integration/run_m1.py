"""Run only the approved synthetic two-process slice on Linux, without root."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from m1_harness import M1Harness
from engine.ingestion.m1_contract import canonical


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--producer", required=True)
    args = parser.parse_args()
    with M1Harness(args.producer, ROOT / "tests/fixtures/process/synthetic-exec-001.json") as harness:
        harness.start_producer()
        result = harness.send()
        if result["outcome"] != "acknowledged":
            raise RuntimeError("M1 delivery was not acknowledged")
        event = harness.retrieve()
        report = {"result": "PASS", "event_id": event["event_id"],
                  "contract_version": event["contract_version"], "ack": result["code"],
                  "activity_wall_time": event["timestamps"]["activity_wall_time"],
                  "native_timestamp_ns": event["native"]["timestamp_ns"],
                  "retrieved_sha256": hashlib.sha256(canonical(event).encode()).hexdigest(),
                  "private_directory": str(harness.directory)}
        (harness.directory / "result.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
