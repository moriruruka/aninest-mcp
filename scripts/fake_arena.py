"""A tiny stand-in for the arena browser service, so reviewers can try ``arena_lookup``.

The real service keeps a logged-in browser session and is intentionally not part of
this repository. This stub speaks the same ``POST /search`` contract with canned
data, which is enough to verify the tool's request/response shape end to end.

    python scripts/fake_arena.py --port 6192
    ANINEST_ARENA_URL=http://127.0.0.1:6192 python scripts/mcp_smoke.py --call arena_lookup

Response contract — copied from a real response, including the two wrapper levels and
the field names (`def`/`atk` hold unit objects, counters are `up`/`down`, timestamp is
`updated`; there is no view counter upstream):

    {"ok": true, "data": {"code": 0, "message": "0",
                          "data": {"result": [{"id": "...", "up": 1, "down": 0,
                                               "def": [{...}], "atk": [{...}],
                                               "updated": "2025-07-21T15:04:17.372Z"}]}}}
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def _unit(char_id: int, star: int = 5) -> dict:
    return {"equip": True, "id": char_id, "star": star}


TEAMS = [
    {
        "id": "687e56f1071db9fa8609e532",
        "def": [_unit(100201, 6), _unit(110501), _unit(102301, 6), _unit(100101, 6), _unit(114701)],
        "atk": [_unit(129001), _unit(132001), _unit(123001), _unit(126101), _unit(108901, 6)],
        "up": 1,
        "down": 0,
        "comment": None,
        "updated": "2025-07-21T15:04:17.372Z",
        "private": False,
        "group": False,
    },
    {
        "id": "687e56f1071db9fa8609e533",
        "def": [_unit(100101, 6), _unit(102301, 6), _unit(106401), _unit(111001), _unit(114701)],
        "atk": [_unit(100201, 6), _unit(101001), _unit(104301), _unit(109401), _unit(112001)],
        "up": 7,
        "down": 1,
        "comment": None,
        "updated": "2025-07-19T09:12:03.114Z",
        "private": False,
        "group": False,
    },
]


class Handler(BaseHTTPRequestHandler):
    server_version = "fake-arena/0.1"

    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        if self.path.rstrip("/") in ("/health", ""):
            self._send(200, {"ok": True, "service": "fake-arena"})
            return
        self._send(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:  # noqa: N802 - stdlib naming
        if self.path.rstrip("/") != "/search":
            self._send(404, {"ok": False, "error": "not found"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            request = json.loads(raw or b"{}")
        except ValueError:
            self._send(400, {"ok": False, "error": "invalid json"})
            return
        def_ids = request.get("def") or []
        if not isinstance(def_ids, list) or not def_ids:
            self._send(400, {"ok": False, "error": "def must be a non-empty list"})
            return
        self._send(
            200,
            {
                "ok": True,
                "data": {
                    "code": 0,
                    "message": "0",
                    "data": {"result": TEAMS, "page": {"page": 1, "hasMore": False}},
                    "version": "20261024",
                },
            },
        )

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[fake-arena] {fmt % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Canned arena service for local testing.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=6192)
    args = parser.parse_args()

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"fake arena listening on http://{args.host}:{args.port} (Ctrl-C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
