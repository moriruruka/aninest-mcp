"""The local overlay: added characters, taught aliases, similarity matching.

The overlay exists because the packaged table cannot cover two cases: a new
character that shipped in Japan before an English/Chinese name existed, and a
match that went wrong and needs to be corrected by hand. These tests pin the
properties that make it safe to use: the package is never touched, writes are
atomic and idempotent, and a correction takes effect on the next lookup.
"""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from aninest.tools import pcr  # noqa: E402


class OverlayTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.overlay = pathlib.Path(self._temp.name) / "pcr_overlay.json"
        self._patch = mock.patch.object(pcr, "overlay_path", return_value=self.overlay)
        self._patch.start()
        pcr.reset_index()

    def tearDown(self) -> None:
        self._patch.stop()
        pcr.reset_index()
        self._temp.cleanup()

    def read_overlay(self) -> dict:
        return json.loads(self.overlay.read_text("utf-8"))


class UpdateCharacterTests(OverlayTestCase):
    def test_creates_new_character_and_resolves_it(self) -> None:
        result = pcr.update_character(199901, name="新角色", jp="シンキャラ", aliases=["新酱"])
        self.assertEqual(result["action"], "created")
        self.assertEqual(result["character"]["uid4"], 1999)

        index = pcr.index()
        self.assertEqual(index.resolve_token("新角色"), 199901)
        self.assertEqual(index.resolve_token("新酱"), 199901)
        self.assertEqual(index.resolve_token("シンキャラ"), 199901)

    def test_extends_aliases_of_existing_character(self) -> None:
        before = len(pcr.index())
        data = pcr.update_character(100701, aliases=["布丁新皮"])
        self.assertEqual(data["action"], "updated")
        self.assertIn("布丁新皮", data["added_aliases"])
        self.assertEqual(len(pcr.index()), before)
        self.assertEqual(pcr.index().resolve_token("布丁新皮"), 100701)

    def test_idempotent_when_nothing_changes(self) -> None:
        pcr.update_character(100701, aliases=["重复别名"])
        again = pcr.update_character(100701, aliases=["重复别名"])
        self.assertEqual(again["added_aliases"], [])
        self.assertEqual(
            len(self.read_overlay()["characters"]["100701"]["aliases"]),
            len(set(self.read_overlay()["characters"]["100701"]["aliases"])),
        )

    def test_remove_alias_drops_it_from_lookup(self) -> None:
        pcr.update_character(100701, aliases=["坏别名"])
        self.assertEqual(pcr.index().resolve_token("坏别名"), 100701)
        pcr.update_character(100701, remove_aliases=["坏别名"])
        self.assertIsNone(pcr.index().resolve_token("坏别名"))

    def test_unknown_character_needs_a_name(self) -> None:
        with self.assertRaises(pcr.ToolError):
            pcr.update_character(199902)

    def test_rejects_ids_outside_the_six_digit_space(self) -> None:
        for bad in (1007, 1007011, "abc"):
            with self.subTest(bad=bad), self.assertRaises(pcr.ToolError):
                pcr.update_character(bad, name="x")

    def test_package_data_is_untouched(self) -> None:
        source = pathlib.Path(pcr.__file__).with_name("..").parent / "data" / "pcr_chars.json"
        before = source.read_text("utf-8") if source.exists() else None
        pcr.update_character(199903, name="只写覆盖层")
        if source.exists():
            self.assertEqual(source.read_text("utf-8"), before)
        self.assertIn("199903", self.read_overlay()["characters"])


class RecordCorrectionTests(OverlayTestCase):
    def test_teaches_a_typo_and_logs_it(self) -> None:
        result = pcr.record_correction("宫紫", 100701, note="用户手误")
        self.assertEqual(result["action"], "alias_added")
        self.assertEqual(result["name"], "宫子")
        self.assertEqual(pcr.index().resolve_token("宫紫"), 100701)

        stored = self.read_overlay()
        self.assertEqual(stored["corrections"][0]["term"], "宫紫")
        self.assertIn("at", stored["corrections"][0])

    def test_accepts_a_name_instead_of_an_id(self) -> None:
        result = pcr.record_correction("缪亚可", "宫子")
        self.assertEqual(result["id"], 100701)

    def test_second_call_is_idempotent(self) -> None:
        pcr.record_correction("宫紫", 100701)
        again = pcr.record_correction("宫紫", 100701)
        self.assertEqual(again["action"], "already_known")
        self.assertEqual(len(self.read_overlay()["corrections"]), 1)

    def test_rejects_unknown_target(self) -> None:
        with self.assertRaises(pcr.ToolError):
            pcr.record_correction("随便什么", "不存在的角色名")

    def test_rejects_empty_term(self) -> None:
        with self.assertRaises(pcr.ToolError):
            pcr.record_correction("   ", 100701)


class MatchNamesTests(unittest.TestCase):
    def test_exact_name_scores_one(self) -> None:
        top = pcr.match_names("宫子")["matches"][0]
        self.assertEqual(top["id"], 100701)
        self.assertEqual(top["score"], 1.0)

    def test_japanese_name_matches(self) -> None:
        top = pcr.match_names("ミヤコ")["matches"][0]
        self.assertEqual(top["id"], 100701)
        self.assertGreaterEqual(top["score"], 0.99)

    def test_near_miss_is_ranked_but_not_certain(self) -> None:
        result = pcr.match_names("宫紫", threshold=0.4)
        self.assertTrue(result["matches"])
        top = result["matches"][0]
        self.assertEqual(top["id"], 100701)
        self.assertLess(top["score"], 1.0)
        self.assertIn("fuzzy", top["matched_on"])

    def test_threshold_filters_everything_out(self) -> None:
        self.assertEqual(pcr.match_names("完全不存在的名字", threshold=0.99)["matches"], [])

    def test_top_k_is_respected(self) -> None:
        self.assertLessEqual(len(pcr.match_names("宫", top_k=3, threshold=0.1)["matches"]), 3)

    def test_empty_query_is_rejected(self) -> None:
        with self.assertRaises(pcr.ToolError):
            pcr.match_names("  ")


class OverlayFileHandlingTests(OverlayTestCase):
    def test_corrupt_overlay_does_not_break_lookup(self) -> None:
        self.overlay.write_text("{ not json", "utf-8")
        self.assertEqual(len(pcr.index()), 351)

    def test_overlay_is_written_atomically(self) -> None:
        pcr.update_character(199904, name="原子写")
        leftovers = list(self.overlay.parent.glob("*.tmp"))
        self.assertEqual(leftovers, [])
        self.assertEqual(self.overlay.read_text("utf-8")[-1], "\n")


if __name__ == "__main__":
    unittest.main()
