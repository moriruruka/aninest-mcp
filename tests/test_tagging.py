"""Tests for the request parser that turns human wording into booru tags."""

from __future__ import annotations

import unittest

import context  # noqa: F401  (adds src/ to sys.path)

from aninest.tagging import (
    _EXTRA_ALIASES,
    _EXTRA_CHARACTERS,
    BLOCKED_CN,
    BLOCKED_TAGS,
    CN_CHARACTERS,
    CN_TAG_ALIASES,
    STOP_PHRASES,
    build_query,
    normalize_tag,
    parse_request,
)


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
        parsed = parse_request("初音未来 玄学")
        self.assertEqual(parsed.tags, ["hatsune_miku"])
        self.assertEqual(parsed.unknown, ["玄学"])

    def test_politeness_phrases_are_stripped(self) -> None:
        # the assistant strips "帮我找一张 … 图" before matching tags; keep that behaviour
        parsed = parse_request("帮我找一张初音未来的泳装图")
        self.assertEqual(parsed.tags, ["hatsune_miku", "swimsuit"])
        self.assertEqual(parsed.unknown, [])

    def test_chinese_numeral_count(self) -> None:
        self.assertEqual(parse_request("来两张初音未来泳装").count, 2)

    def test_multi_tag_expansion(self) -> None:
        # 蓝天 is two tags in the assistant's table, not one
        self.assertEqual(parse_request("蓝天").tags, ["sky", "blue_sky"])

    def test_character_names_cover_more_than_miku(self) -> None:
        self.assertEqual(parse_request("甘雨 泳装").tags, ["ganyu_(genshin_impact)", "swimsuit"])

    def test_min_width_is_extracted(self) -> None:
        self.assertEqual(parse_request("泳装 1024p").min_width, 1024)
        self.assertEqual(parse_request("泳装 大尺寸").min_width, 1600)

    def test_mode_synonyms(self) -> None:
        self.assertEqual(parse_request("泳装 省流").size, "compressed")
        self.assertEqual(parse_request("泳装 无损").size, "original")

    def test_blocked_chinese_word_raises(self) -> None:
        with self.assertRaises(ValueError):
            parse_request("萝莉 泳装")

    def test_blocked_english_tag_raises(self) -> None:
        with self.assertRaises(ValueError):
            parse_request("loli swimsuit")

    def test_blocklist_matches_the_assistant_defaults(self) -> None:
        # yuri / nakadashi / tentacles only appear in the assistant's list; the tool's
        # earlier hand-written list missed them, which is the drift this port fixes.
        for word in ("yuri", "nakadashi", "tentacles", "ahegao"):
            with self.assertRaises(ValueError):
                parse_request(f"swimsuit {word}")

    def test_dictionary_sizes_match_the_source_table(self) -> None:
        # Pinned numbers: if a future port silently drops table rows, this fails
        # before the behaviour drift shows up as missing tags in the wild.
        self.assertEqual(len(CN_TAG_ALIASES), 171 + len(_EXTRA_ALIASES))
        self.assertEqual(len(CN_CHARACTERS), 56 + len(_EXTRA_CHARACTERS))
        self.assertEqual(len(STOP_PHRASES), 39)
        self.assertEqual(len(BLOCKED_TAGS), 26)
        self.assertEqual(len(BLOCKED_CN), 19)

    def test_library_is_not_eaten_by_stop_phrases(self) -> None:
        # "图" is a politeness/stop word; stripping it before alias matching turned
        # "图书馆" into the unknown chunk "书馆".
        self.assertEqual(parse_request("图书馆").tags, ["library"])

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
