"""Tests for read-only memory retrieval against a throw-away SQLite database."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import context  # noqa: F401

from aninest.tools.memory import memory_stats, score, search_memories

SCHEMA = """
CREATE TABLE memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    tags TEXT DEFAULT '[]',
    importance INTEGER DEFAULT 3,
    scope TEXT DEFAULT 'session',
    subject TEXT DEFAULT '',
    confidence REAL DEFAULT 0.8,
    updated_at INTEGER DEFAULT 0,
    status TEXT DEFAULT 'active'
);
CREATE TABLE pending_corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT
);
"""


def build_db(path: Path, rows: list[tuple[str, str, int, str]]) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    for content, scope, importance, status in rows:
        conn.execute(
            "INSERT INTO memories (content, tags, importance, scope, status, updated_at) "
            "VALUES (?, ?, ?, ?, ?, 0)",
            (content, json.dumps([]), importance, scope, status),
        )
    conn.execute("INSERT INTO pending_corrections (content) VALUES ('x')")
    conn.commit()
    conn.close()


class ScoreTests(unittest.TestCase):
    def test_overlap_scores_higher(self) -> None:
        tokens = ["hkdse", "physics"]
        self.assertGreater(score(tokens, "hkdse physics syllabus", 3), 0.5)

    def test_no_overlap_is_zero(self) -> None:
        self.assertEqual(score(["nothing"], "hkdse physics", 3), 0.0)

    def test_importance_gives_a_mild_bonus(self) -> None:
        self.assertGreater(score(["physics"], "physics", 5), score(["physics"], "physics", 1))

    def test_empty_content_is_zero(self) -> None:
        self.assertEqual(score(["physics"], "", 3), 0.0)


class SearchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "memory.db"
        build_db(
            self.db,
            [
                ("The HKDSE physics syllabus was revised in 2024", "session", 4, "active"),
                ("初音未来 的 泳装 插画 偏好 竖图", "session", 3, "active"),
                ("global: user prefers Python over C#", "global", 3, "active"),
                ("deprecated note", "session", 1, "archived"),
            ],
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_search_finds_matching_row(self) -> None:
        result = search_memories("physics syllabus", db_path=self.db)
        self.assertEqual(result["matched"], 1)
        self.assertIn("HKDSE", result["hits"][0]["content"])

    def test_archived_rows_are_ignored(self) -> None:
        result = search_memories("deprecated note", db_path=self.db)
        self.assertEqual(result["matched"], 0)

    def test_scope_filter(self) -> None:
        result = search_memories("python", scope="global", db_path=self.db)
        self.assertEqual(result["matched"], 1)
        self.assertEqual(result["hits"][0]["scope"], "global")

    def test_chinese_query(self) -> None:
        result = search_memories("泳装", db_path=self.db)
        self.assertEqual(result["matched"], 1)

    def test_limit_is_applied(self) -> None:
        result = search_memories("physics", limit=0, db_path=self.db)
        self.assertEqual(len(result["hits"]), 1)

    def test_missing_database_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            search_memories("x", db_path=self.db.parent / "nope.db")

    def test_empty_query_raises(self) -> None:
        with self.assertRaises(ValueError):
            search_memories("   ", db_path=self.db)


class StatsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "memory.db"
        build_db(
            self.db,
            [
                ("one", "session", 3, "active"),
                ("two", "global", 3, "active"),
                ("three", "session", 3, "archived"),
            ],
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_counts_and_groups(self) -> None:
        stats = memory_stats(db_path=self.db)
        self.assertEqual(stats["rows"], 3)
        self.assertEqual(stats["by_scope"], {"session": 2, "global": 1})
        self.assertEqual(stats["by_status"], {"active": 2, "archived": 1})
        self.assertEqual(stats["pending_corrections"], 1)
        self.assertGreater(stats["db_bytes"], 0)

    def test_missing_database_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            memory_stats(db_path=self.db.parent / "nope.db")


if __name__ == "__main__":
    unittest.main()
