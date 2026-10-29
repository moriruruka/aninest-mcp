"""Runtime settings, resolved from environment variables only (no secret files)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .version import VERSION

DEFAULT_UA = f"aninest-mcp/{VERSION} (+https://github.com/moriruruka/aninest-mcp)"


def _env(name: str, default: str) -> str:
    value = os.environ.get(name, "").strip()
    return value or default


@dataclass(frozen=True)
class Settings:
    """Everything the server needs, with safe defaults for local development."""

    #: Base URL of the local arena browser service (see AniNest runtime/pcrdfans_browser.py).
    arena_url: str = field(default_factory=lambda: _env("ANINEST_ARENA_URL", "http://127.0.0.1:6191"))
    #: Path to the assistant's SQLite memory database (read-only access).
    memory_db: Path = field(
        default_factory=lambda: Path(
            _env("ANINEST_MEMORY_DB", str(Path.home() / ".aninest" / "memory.db"))
        )
    )
    #: Boilerplate image board used as the default search backend.
    booru_url: str = field(
        default_factory=lambda: _env("ANINEST_BOORU_URL", "https://safebooru.org/index.php")
    )
    http_timeout: float = field(default_factory=lambda: float(_env("ANINEST_HTTP_TIMEOUT", "15")))
    user_agent: str = field(default_factory=lambda: _env("ANINEST_USER_AGENT", DEFAULT_UA))
    #: Transport for `python -m aninest`: "stdio" (default) or "streamable-http".
    transport: str = field(default_factory=lambda: _env("ANINEST_MCP_TRANSPORT", "stdio").lower())
    host: str = field(default_factory=lambda: _env("ANINEST_MCP_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: int(_env("ANINEST_MCP_PORT", "8765")))
    #: Hosts probed by the health tool.
    probe_host: str = field(default_factory=lambda: _env("ANINEST_PROBE_HOST", "127.0.0.1"))


SETTINGS = Settings()

#: Fixed local ports of the assistant stack, surfaced by `service_health`.
SERVICES: dict[str, int] = {
    "astrbot-webui": 6185,
    "onebot-ws": 6199,
    "tts": 9880,
    "stt": 6190,
    "arena-browser": 6191,
}
