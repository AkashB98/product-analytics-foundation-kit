"""Hermetic guard: the whole pipeline runs with sockets stubbed."""

import os
import socket
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestNoNetwork(unittest.TestCase):
    def test_pipeline_offline(self):
        real = socket.socket

        def blocked(*a, **k):
            raise AssertionError("network access attempted")

        socket.socket = blocked
        try:
            from generator import generate_events
            from metrics import impact_table
            impact = impact_table(generate_events())
            self.assertEqual(impact["cleaned"]["sessions"]["sessions"], 232)
        finally:
            socket.socket = real


if __name__ == "__main__":
    unittest.main()
