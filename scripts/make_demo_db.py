"""Build a small demo memory database so reviewers can try the memory tools.

The real store belongs to a running assistant and is never shipped. This script
creates a database with the same schema and obviously fictional rows, so that
``memory_search`` / ``memory_stats`` can be exercised end to end.

    python scripts/make_demo_db.py --out demo_memory.db
    ANINEST_MEMORY_DB=./demo_memory.db python scripts/mcp_smoke.py --call memory_search \
        --args '{"query":"泳装 插画"}'
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    tags TEXT DEFAULT '[]',
    importance INTEGER DEFAULT 3,
    scope TEXT DEFAULT 'session',
    subject TEXT DEFAULT '',
    confidence REAL DEFAULT 0.8,
    status TEXT DEFAULT 'active',
    created_at REAL DEFAULT 0,
    updated_at REAL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS pending_corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    old_id INTEGER,
    subject TEXT,
    new_content TEXT,
    reason TEXT,
    created_at REAL DEFAULT 0
);
"""

ROWS = [
    ("用户偏好竖构图的人物插画，尤其是海边的场景。", '["preference","art"]', 4, "global", "art"),
    ("示例：某个角色的称号是「海边的守护者」。", '["example"]', 3, "global", "lore"),
    ("示例：这套防守阵容的核心是二号位的治疗角色。", '["example","arena"]', 3, "session", "arena"),
    ("用户不喜欢把图片裁成正方形，要求保留原始比例。", '["preference"]', 4, "global", "art"),
    ("示例：查攻略时优先看最近七天的作业。", '["example"]', 2, "session", "arena"),
]


def build(out: Path) -> None:
    if out.exists():
        out.unlink()
    conn = sqlite3.connect(out)
    try:
        conn.executescript(SCHEMA)
        conn.executemany(
            "INSERT INTO memories (content, tags, importance, scope, subject, updated_at) "
            "VALUES (?, ?, ?, ?, ?, 0)",
            ROWS,
        )
        conn.commit()
    finally:
        conn.close()
    print(f"wrote {out} ({out.stat().st_size} bytes, {len(ROWS)} rows)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a demo memory database.")
    parser.add_argument("--out", default="demo_memory.db", help="output sqlite file")
    args = parser.parse_args()
    build(Path(args.out))


if __name__ == "__main__":
    main()
