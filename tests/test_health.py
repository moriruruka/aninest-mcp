"""Tests for the health probe (network calls are limited to loopback)."""

from __future__ import annotations

import socket
import unittest

import context  # noqa: F401

from aninest.tools.health import probe_port, service_health


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class ProbeTests(unittest.TestCase):
    def test_closed_port_is_down(self) -> None:
        self.assertFalse(probe_port("127.0.0.1", free_port(), timeout=0.3))

    def test_open_port_is_up(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.bind(("127.0.0.1", 0))
            server.listen(1)
            port = int(server.getsockname()[1])
            self.assertTrue(probe_port("127.0.0.1", port, timeout=1.0))


class ServiceHealthTests(unittest.TestCase):
    def test_shape(self) -> None:
        result = service_health(memory_db="C:/definitely/not/here.db")
        self.assertEqual(result["total"], 5)
        self.assertIn("astrbot-webui", result["services"])
        self.assertEqual(result["up"], sum(1 for s in result["services"].values() if s["up"]))
        self.assertFalse(result["memory_db"]["exists"])


if __name__ == "__main__":
    unittest.main()
