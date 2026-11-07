"""Offline test of harness authorization/budget accounting, without processes."""
from types import SimpleNamespace
import time
import unittest
from unittest.mock import patch

from m1_harness import HarnessFailure, M1Harness


class HarnessPolicyTests(unittest.TestCase):
    def fake(self):
        h = M1Harness.__new__(M1Harness)
        h.original = b'original immutable line\n'
        h.producer = SimpleNamespace(poll=lambda: None)
        h.receiver = SimpleNamespace(pid=42)
        h.producer_control, h.producer_reports = 10, 11
        h.operations, h.outcome = 0, None
        h.case_deadline = time.monotonic()+120
        return h

    def test_explicit_operation_is_never_automatic_or_unlimited(self):
        h = self.fake()
        original = h.original
        response = b'{"outcome":"unconfirmed","code":"delivery_unconfirmed","attempts":3,"any_sent":true}'
        with patch('m1_harness.control_write'), patch('m1_harness.read_line', return_value=response):
            self.assertEqual(h.send()['outcome'], 'unconfirmed')
            self.assertEqual(h.operations, 1)
            with self.assertRaises(HarnessFailure):
                h.send()
            self.assertEqual(h.send(explicit_retry=True)['outcome'], 'unconfirmed')
            with self.assertRaises(HarnessFailure):
                h.send(explicit_retry=True)
        self.assertEqual(h.original, original)
        self.assertEqual(h.operations, 2)

    def test_later_reject_does_not_erase_prior_uncertainty(self):
        h = self.fake()
        h.operations, h.outcome = 1, 'unconfirmed'
        with patch('m1_harness.control_write'), patch('m1_harness.read_line', return_value=b'{"outcome":"rejected","code":"invalid_event"}'):
            result = h.send(explicit_retry=True)
        self.assertEqual((result['outcome'], result['operation_outcome']), ('unconfirmed', 'rejected'))

    def test_acknowledged_pending_event_cannot_be_retried(self):
        h = self.fake()
        h.outcome = 'acknowledged'
        with self.assertRaises(HarnessFailure):
            h.send(explicit_retry=True)
