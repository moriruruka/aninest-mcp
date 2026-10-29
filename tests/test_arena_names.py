"""Arena lookup by character name, with exclude/replace applied before the call.

The service is faked with a tiny stdlib HTTP server that records the request, so
these tests check what the tool actually sends — not just how it parses a reply.
"""

from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

import context  # noqa: F401

from aninest.config import Settings
from aninest.tools import arena

FIXTURE = Path(__file__).parent / "fixtures" / "arena_payload.json"
PAYLOAD = json.loads(FIXTURE.read_text(encoding="utf-8"))


class _Handler(BaseHTTPRequestHandler):
    received: list[dict] = []

    def do_POST(self) -> None:  # noqa: N802 - stdlib naming
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length)
        try:
            _Handler.received.append(json.loads(body or b"{}"))
        except ValueError:
            _Handler.received.append({})
        raw = json.dumps(PAYLOAD).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *args: object) -> None:  # silence the test output
        return


class ArenaNameTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = HTTPServer(("127.0.0.1", 0), _Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def setUp(self) -> None:
        _Handler.received.clear()
        patcher = mock.patch.object(arena, "SETTINGS", Settings(arena_url=self.url))
        patcher.start()
        self.addCleanup(patcher.stop)

    async def test_names_are_resolved_before_the_call(self) -> None:
        result = await arena.arena_lookup(["布丁", "克总", "真琴"])
        self.assertEqual(result["def_ids"], [100701, 107101, 104301])
        self.assertEqual(_Handler.received[0]["def"], [100701, 107101, 104301])
        names = [slot["name"] for slot in result["lineup"]]
        self.assertEqual(names, ["宫子", "克莉丝提娜", "真琴"])

    async def test_aliases_and_ids_can_be_mixed(self) -> None:
        result = await arena.arena_lookup(["猫拳", 104301, "100301"])
        self.assertEqual(result["def_ids"], [100101, 104301, 100301])

    async def test_exclude_by_name(self) -> None:
        result = await arena.arena_lookup(["布丁", "克总", "真琴"], exclude=["布丁"])
        self.assertEqual(result["def_ids"], [107101, 104301])
        self.assertEqual(result["applied"][0]["action"], "exclude")

    async def test_replace_keeps_the_slot(self) -> None:
        result = await arena.arena_lookup(["布丁", "克总", "真琴"], replace=["布丁->怜"])
        self.assertEqual(result["def_ids"], [100301, 107101, 104301])
        self.assertEqual(result["applied"][0]["slot"], 1)

    async def test_duplicate_replacement_is_refused(self) -> None:
        from mcp.server.fastmcp.exceptions import ToolError

        with self.assertRaises(ToolError) as caught:
            await arena.arena_lookup(["布丁", "克总"], replace=["布丁->克总"])
        self.assertIn("号位", str(caught.exception))
        self.assertEqual(_Handler.received, [])

    async def test_unknown_name_is_reported_not_raised(self) -> None:
        # A partially understood lineup still answers: the host gets ids plus the
        # word it could not read, so it can ask a follow-up question.
        result = await arena.arena_lookup(["布丁", "完全不存在的人"])
        self.assertEqual(result["def_ids"], [100701])
        self.assertEqual(result["unresolved"][0]["input"], "完全不存在的人")
        self.assertTrue(result["unresolved"][0]["suggestions"])

    async def test_nothing_resolved_is_an_error(self) -> None:
        from mcp.server.fastmcp.exceptions import ToolError

        with self.assertRaises(ToolError):
            await arena.arena_lookup(["完全不存在的人"])

    async def test_missing_argument_is_an_error(self) -> None:
        from mcp.server.fastmcp.exceptions import ToolError

        with self.assertRaises(ToolError):
            await arena.arena_lookup(None)

    async def test_ids_only_call_still_works(self) -> None:
        result = await arena.arena_lookup(None, def_ids=[100101, 100201])
        self.assertEqual(result["def_ids"], [100101, 100201])

    async def test_unresolved_partial_lineup_is_reported(self) -> None:
        result = await arena.arena_lookup(["布丁", "克总t"])
        self.assertEqual(result["def_ids"], [100701])
        self.assertEqual(len(result["unresolved"]), 1)


if __name__ == "__main__":
    unittest.main()
