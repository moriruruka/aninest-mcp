"""A tiny stand-in for the arena browser service, so reviewers can try ``arena_lookup``.

The real service keeps a logged-in browser session and is intentionally not part of
this repository. This stub speaks the same ``POST /search`` contract with canned
data, which is enough to verify the tool's request/response shape end to end.

    python scripts/fake_arena.py --port 6192
    ANINEST_ARENA_URL=http://127.0.0.1:6192 python scripts/mcp_smoke.py --call arena_lookup

Response contract (mirrors the real service):

    {"ok": true, "data": {"result": [{"atk": [100141, ...], "likes": 12, "views": 345}]}}
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TEAMS = [
    {
        "atk": [100141, 100241, 100341, 100441, 100541],
        "likes": 128,
        "views": 4210,
        "updated": "2026-10-20",
    },
    {
        "atk": [100142, 100242, 100342, 100442, 100542],
        "likes": 64,
        "views": 2088,
        "updated": "2026-10-11",
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
        self._send(200, {"ok": True, "data": {"result": TEAMS}})

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
