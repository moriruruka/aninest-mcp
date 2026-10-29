"""Character name → id resolution.

These tests pin the behaviour a player-facing tool needs: nicknames resolve, a
whole run of names without separators splits, an unknown word comes back with
suggestions instead of a bare failure, and a variant avatar id maps to its base
character (that is what a screenshot crop gives you).
"""

from __future__ import annotations

import unittest

import context  # noqa: F401

from aninest.tools import pcr


class TableTests(unittest.TestCase):
    def test_table_is_packaged_and_complete(self) -> None:
        index = pcr.index()
        self.assertGreaterEqual(len(index), 340)
        self.assertIn(100101, index.by_id)
        self.assertEqual(index.by_id[100101].name, "日和")

    def test_ids_are_six_digit_and_unique(self) -> None:
        index = pcr.index()
        ids = [character.id for character in index.characters]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(100000 <= value <= 999999 for value in ids))

    def test_every_character_has_a_name(self) -> None:
        for character in pcr.index().characters:
            self.assertTrue(character.name.strip(), character.id)

    def test_aliases_are_not_the_name_itself(self) -> None:
        for character in pcr.index().characters[:80]:
            self.assertNotIn(character.name, character.aliases)


class ResolveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.index = pcr.index()

    def test_name(self) -> None:
        self.assertEqual(self.index.resolve_token("日和"), 100101)

    def test_known_nicknames(self) -> None:
        self.assertEqual(self.index.resolve_token("布丁"), 100701)  # 宫子
        self.assertEqual(self.index.resolve_token("克总"), 107101)  # 克莉丝提娜
        self.assertEqual(self.index.resolve_token("猫拳"), 100101)

    def test_full_width_and_case_are_normalised(self) -> None:
        self.assertEqual(self.index.resolve_token("ＵＥ"), self.index.resolve_token("ue"))

    def test_six_digit_id(self) -> None:
        self.assertEqual(self.index.resolve_token("104301"), 104301)

    def test_four_digit_uid(self) -> None:
        self.assertEqual(self.index.resolve_token("1043"), 104301)

    def test_variant_avatar_id_maps_to_base_character(self) -> None:
        self.assertEqual(self.index.resolve_token("104311"), 104301)
        self.assertEqual(self.index.name_of(104311), self.index.name_of(104301))

    def test_unknown_returns_none(self) -> None:
        self.assertIsNone(self.index.resolve_token("这个人不存在"))

    def test_prefix_and_substring_need_two_characters(self) -> None:
        # The table does contain single-character aliases (克 → 克莉丝提娜, 布 → 宫子),
        # so an exact one-letter hit is by design; the *fuzzy* scan must not guess.
        self.assertEqual(self.index.resolve_token("克"), 107101)
        self.assertIsNone(self.index.resolve_token("真"))
        self.assertIsNotNone(self.index.resolve_token("真琴"))


class SegmentTests(unittest.TestCase):
    def test_splits_names_written_without_separators(self) -> None:
        ids = pcr.index().segment_token("布丁克总")
        self.assertEqual(len(ids), 2)
        self.assertEqual(set(ids), {100701, 107101})

    def test_refuses_garbage(self) -> None:
        self.assertEqual(pcr.index().segment_token("随便写点东西"), [])

    def test_too_short_to_split(self) -> None:
        self.assertEqual(pcr.index().segment_token("布丁"), [])


class ResolveTeamTests(unittest.TestCase):
    def test_mixed_inputs(self) -> None:
        result = pcr.resolve_team(["布丁", "克总", 104301])
        self.assertEqual(result["ids"], [100701, 107101, 104301])
        self.assertEqual(result["unresolved"], [])
        names = [item["name"] for item in result["resolved"]]
        self.assertEqual(names, ["宫子", "克莉丝提娜", "真琴"])

    def test_string_with_separators(self) -> None:
        result = pcr.resolve_team("布丁,克总 真琴")
        self.assertEqual(result["ids"], [100701, 107101, 104301])

    def test_unknown_word_comes_back_with_suggestions(self) -> None:
        result = pcr.resolve_team(["布丁", "克总t"])
        self.assertEqual(result["ids"], [100701])
        self.assertEqual(len(result["unresolved"]), 1)
        suggestions = result["unresolved"][0]["suggestions"]
        self.assertTrue(suggestions)
        self.assertIn("克莉丝提娜", [item["name"] for item in suggestions])

    def test_limit_is_five(self) -> None:
        result = pcr.resolve_team(["布丁", "克总", "真琴", "纺希", "莉莎", "日和"])
        self.assertEqual(len(result["ids"]), 5)
        self.assertTrue(result["truncated"])

    def test_duplicates_collapse(self) -> None:
        result = pcr.resolve_team(["日和", "猫拳"])
        self.assertEqual(result["ids"], [100101])


class ExcludeReplaceTests(unittest.TestCase):
    def test_exclude_by_name(self) -> None:
        outcome = pcr.apply_exclude([100701, 107101, 104301], "布丁")
        self.assertEqual(outcome["ids"], [107101, 104301])
        self.assertEqual(outcome["applied"][0]["name"], "宫子")

    def test_exclude_unknown_is_reported(self) -> None:
        outcome = pcr.apply_exclude([100701], "不存在的角色")
        self.assertEqual(outcome["ids"], [100701])
        self.assertEqual(len(outcome["unresolved"]), 1)

    def test_replace_keeps_the_slot(self) -> None:
        outcome = pcr.apply_replace([100701, 107101, 104301], "布丁->真琴x")
        self.assertEqual(outcome["problems"][0]["reason"], "unknown")
        outcome = pcr.apply_replace([100701, 107101, 104301], "布丁->怜")
        self.assertEqual(outcome["ids"], [100301, 107101, 104301])
        self.assertEqual(outcome["applied"][0]["slot"], 1)

    def test_replace_accepts_arrow_variants(self) -> None:
        for text in ("布丁->怜", "布丁→怜", "布丁 换成 怜"):
            outcome = pcr.apply_replace([100701], text)
            self.assertEqual(outcome["ids"], [100301], text)

    def test_replace_rejects_duplicate(self) -> None:
        outcome = pcr.apply_replace([100701, 107101], "布丁->克总")
        self.assertEqual(outcome["ids"], [100701, 107101])
        self.assertEqual(outcome["problems"][0]["reason"], "duplicate")
        self.assertIn("2 号位", outcome["problems"][0]["detail"])

    def test_replace_rejects_same_character(self) -> None:
        outcome = pcr.apply_replace([100701], "布丁->宫子")
        self.assertEqual(outcome["problems"][0]["reason"], "same_character")

    def test_replace_rejects_character_not_in_team(self) -> None:
        outcome = pcr.apply_replace([100701], "日和->怜")
        self.assertEqual(outcome["problems"][0]["reason"], "not_in_team")


class SearchTests(unittest.TestCase):
    def test_exact_name_wins(self) -> None:
        hits = pcr.index().search("真琴", limit=3)
        self.assertEqual(hits[0].character.id, 104301)
        self.assertEqual(hits[0].score, 100.0)

    def test_id_shortcut(self) -> None:
        hits = pcr.index().search("104301", limit=1)
        self.assertEqual(hits[0].character.id, 104301)

    def test_typo_still_ranks_the_right_character_first(self) -> None:
        hits = pcr.index().suggest("克莉丝提那", limit=3)
        self.assertEqual(hits[0].character.name, "克莉丝提娜")

    def test_region_filter(self) -> None:
        ids = [100101, 104301]
        self.assertEqual(pcr.index().filter_ids(ids, 0), ids)
        self.assertLessEqual(len(pcr.index().filter_ids(ids, 1)), len(ids))


class DescribeTests(unittest.TestCase):
    def test_slot_numbering(self) -> None:
        described = pcr.describe([100701, 107101])
        self.assertEqual([item["slot"] for item in described], [1, 2])
        self.assertEqual(described[0]["name"], "宫子")

    def test_conjunction_split_needs_known_names(self) -> None:
        parsed = pcr.index().parse_text("布丁和克总")
        self.assertEqual(parsed.ids, [100701, 107101])
        self.assertEqual(parsed.unknown, [])

    def test_conjunction_characters_do_not_split_real_names(self) -> None:
        # 日和 contains 和; it must still resolve as one character.
        parsed = pcr.index().parse_text("日和")
        self.assertEqual(parsed.ids, [100101])


if __name__ == "__main__":
    unittest.main()
