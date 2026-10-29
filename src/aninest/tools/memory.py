"""Memory retrieval tool: read-only search over the assistant's SQLite memory store.

The store is written by the assistant itself; this tool only ever opens it with
``mode=ro`` so a tool call can never corrupt live state.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from ..config import SETTINGS

_TOKEN = re.compile(r"[0-9a-zA-Z_]+|[\u4e00-\u9fff]")


def _tokens(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN.findall(text or "")]


def score(query_tokens: list[str], content: str, importance: int) -> float:
    """Token-overlap score with a mild importance prior. Pure function."""
    content_tokens = set(_tokens(content))
    if not content_tokens or not query_tokens:
        return 0.0
    hits = sum(1 for token in query_tokens if token in content_tokens)
    if hits == 0:
        return 0.0
    coverage = hits / max(1, len(set(query_tokens)))
    return round(coverage * 0.85 + min(importance, 5) / 5 * 0.15, 4)


def _connect(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        raise FileNotFoundError(
            f"memory database not found: {db_path}. "
            "Point ANINEST_MEMORY_DB at an existing SQLite file, or create a sample "
            "one with `python scripts/make_demo_db.py --out <path>`."
        )
    uri = f"file:{db_path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def search_memories(
    query: str,
    limit: int = 5,
    scope: str = "all",
    db_path: Path | None = None,
) -> dict:
    """Search stored memories by token overlap."""
    path = Path(db_path or SETTINGS.memory_db)
    query_tokens = _tokens(query)
    if not query_tokens:
        raise ValueError("query has no searchable token")

    sql = (
        "SELECT id, content, tags, importance, scope, subject, confidence, updated_at "
        "FROM memories WHERE status = 'active'"
    )
    args: list[object] = []
    if scope in ("session", "global"):
        sql += " AND scope = ?"
        args.append(scope)
    sql += " ORDER BY id DESC LIMIT 500"

    conn = _connect(path)
    try:
        rows = conn.execute(sql, args).fetchall()
    finally:
        conn.close()

    ranked = []
    for row in rows:
        value = score(query_tokens, row["content"], int(row["importance"] or 3))
        if value <= 0:
            continue
        ranked.append(
            {
                "id": row["id"],
                "score": value,
                "content": row["content"],
                "tags": json.loads(row["tags"] or "[]"),
                "scope": row["scope"],
                "subject": row["subject"],
                "importance": row["importance"],
            }
        )
    ranked.sort(key=lambda item: (item["score"], item["importance"]), reverse=True)
    top = ranked[: max(1, min(20, limit))]
    return {"query": query, "scanned": len(rows), "matched": len(ranked), "hits": top}


def memory_stats(db_path: Path | None = None) -> dict:
    """Return counts and size information without touching row content."""
    path = Path(db_path or SETTINGS.memory_db)
    conn = _connect(path)
    try:
        total = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        by_scope = dict(
            conn.execute("SELECT scope, COUNT(*) FROM memories GROUP BY scope").fetchall()
        )
        by_status = dict(
            conn.execute("SELECT status, COUNT(*) FROM memories GROUP BY status").fetchall()
        )
        pending = conn.execute("SELECT COUNT(*) FROM pending_corrections").fetchone()[0]
        avg_len = conn.execute("SELECT AVG(LENGTH(content)) FROM memories").fetchone()[0] or 0
    finally:
        conn.close()
    size = path.stat().st_size
    return {
        "db": str(path),
        "rows": total,
        "by_scope": by_scope,
        "by_status": by_status,
        "pending_corrections": pending,
        "avg_content_chars": round(float(avg_len), 1),
        "db_bytes": size,
    }
