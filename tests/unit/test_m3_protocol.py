import json
import tempfile
import unittest
from pathlib import Path

from engine.ingestion.m3_progress import Progress, ProgressError
from engine.ingestion.m3_protocol import REQUEST_LIMIT, dispatch


class ProtocolTests(unittest.TestCase):
    def test_scope_and_capacity_fail_without_advancing(self):
        scope = dict(activation="a", generation="g", lease="current")
        with tempfile.TemporaryDirectory() as directory:
            ledger = Progress(Path(directory) / "progress.db", "a", "g", 0, position_limit=1)
            try:
                def register(**updates):
                    message = dict(scope, version=3, op="register", identity="1.001:1",
                                   begin=0, end=10, eoe=False)
                    message.update(updates)
                    return dispatch(json.dumps(message).encode() + b"\n", ledger, scope)

                for updates in ({"lease": "stale"}, {"generation": "wrong"}, {"version": True},
                                {"begin": False}, {"extra": 1}):
                    with self.assertRaises(ProgressError):
                        register(**updates)
                for invalid in (b'{"version":3,"version":3}\n', b" " * REQUEST_LIMIT + b"\n",
                                b"{}", b"\xff\n"):
                    with self.assertRaises(ProgressError):
                        dispatch(invalid, ledger, scope)
                self.assertEqual(ledger.positions(), (0, 0))
                self.assertEqual(register(), "admit")
                with self.assertRaisesRegex(ProgressError, "capacity"):
                    register(begin=10, end=20)
                self.assertEqual(register(), "replay")
                self.assertEqual(ledger.positions(), (10, 0))
            finally:
                ledger.close()
