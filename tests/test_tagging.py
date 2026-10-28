"""Tests for the request parser that turns human wording into booru tags."""

from __future__ import annotations

import unittest

import context  # noqa: F401  (adds src/ to sys.path)

from aninest.tagging import build_query, normalize_tag, parse_request


class NormalizeTagTests(unittest.TestCase):
    def test_spaces_become_underscores(self) -> None:
        self.assertEqual(normalize_tag("  Hatsune  Miku "), "hatsune_miku")

    def test_punctuation_is_dropped(self) -> None:
        self.assertEqual(normalize_tag("blue-hair!"), "blue_hair")

    def test_empty_input(self) -> None:
        self.assertEqual(normalize_tag("   "), "")


class ParseRequestTests(unittest.TestCase):
    def test_chinese_request_becomes_tags(self) -> None:
        parsed = parse_request("初音未来 泳装")
        self.assertEqual(parsed.tags, ["hatsune_miku", "swimsuit"])
        self.assertEqual(parsed.unknown, [])

    def test_count_and_size_and_orientation_are_extracted(self) -> None:
        parsed = parse_request("初音未来 泳装 竖图 2张 压缩图")
        self.assertEqual(parsed.count, 2)
        self.assertEqual(parsed.size, "compressed")
        self.assertEqual(parsed.orientation, "portrait")
        # the numeric phrase must not leak into the tag list
        self.assertEqual(parsed.tags, ["hatsune_miku", "swimsuit"])

    def test_original_size(self) -> None:
        parsed = parse_request("初音未来 原图")
        self.assertEqual(parsed.size, "original")

    def test_count_is_clamped(self) -> None:
        self.assertEqual(parse_request("泳装 99张").count, 10)
        self.assertEqual(parse_request("泳装 0张").count, 1)

    def test_english_words_are_kept(self) -> None:
        parsed = parse_request("hatsune miku swimsuit")
        self.assertEqual(parsed.tags, ["hatsune", "miku", "swimsuit"])

    def test_unknown_chinese_words_are_reported(self) -> None:
        parsed = parse_request("初音未来 某个不存在的词")
        self.assertEqual(parsed.tags, ["hatsune_miku"])
        self.assertEqual(parsed.unknown, ["某个不存在的词"])

    def test_blocked_chinese_word_raises(self) -> None:
        with self.assertRaises(ValueError):
            parse_request("萝莉 泳装")

    def test_blocked_english_tag_raises(self) -> None:
        with self.assertRaises(ValueError):
            parse_request("loli swimsuit")

    def test_empty_request_raises(self) -> None:
        with self.assertRaises(ValueError):
            parse_request("   ")

    def test_nothing_usable_raises(self) -> None:
        with self.assertRaises(ValueError):
            parse_request("2张 压缩图")


class BuildQueryTests(unittest.TestCase):
    def test_extra_tags_are_merged_and_deduped(self) -> None:
        parsed = build_query("初音未来", extra_tags=["swimsuit", "hatsune_miku"])
        self.assertEqual(parsed.tags, ["hatsune_miku", "swimsuit"])

    def test_negative_tags_are_appended(self) -> None:
        parsed = build_query("初音未来", negative=["text", "watermark"])
        self.assertEqual(parsed.negative, ["text", "watermark"])
        self.assertEqual(parsed.tag_query(), "hatsune_miku -text -watermark")

    def test_negative_tag_with_leading_dash(self) -> None:
        parsed = build_query("初音未来", negative=["-text"])
        self.assertEqual(parsed.negative, ["text"])

    def test_blocked_extra_tag_raises(self) -> None:
        with self.assertRaises(ValueError):
            build_query("初音未来", extra_tags=["lolicon"])

    def test_blocked_negative_tag_raises(self) -> None:
        with self.assertRaises(ValueError):
            build_query("初音未来", negative=["loli"])


if __name__ == "__main__":
    unittest.main()
