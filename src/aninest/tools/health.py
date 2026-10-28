"""Health probe tool: tells the model which local services of the stack are up."""

from __future__ import annotations

import socket
from pathlib import Path

from ..config import SERVICES, SETTINGS


def probe_port(host: str, port: int, timeout: float = 0.6) -> bool:
    """Return True when a TCP connection can be established."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def service_health(host: str | None = None, memory_db: Path | None = None) -> dict:
    """Probe every local service and report the memory database footprint."""
    probe_host = host or SETTINGS.probe_host
    services = {
        name: {"port": port, "up": probe_port(probe_host, port)}
        for name, port in SERVICES.items()
    }
    db = Path(memory_db or SETTINGS.memory_db)
    return {
        "host": probe_host,
        "up": sum(1 for item in services.values() if item["up"]),
        "total": len(services),
        "services": services,
        "memory_db": {"path": str(db), "exists": db.exists()},
    }
