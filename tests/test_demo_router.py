"""unittest coverage for the demo host's deterministic router (no MCP, no network)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "demo"))

import host  # noqa: E402  (needs the sys.path tweak above)

HEALTH_JSON = (
    '{"host":"127.0.0.1","up":1,"total":2,'
    '"services":{"a":{"port":1,"up":true},"b":{"port":2,"up":false}}}'
)
ARENA_JSON = '{"found":1,"teams":[{"defense":[100101,100201],"upvotes":9,"downvotes":0}]}'


class RouterTest(unittest.TestCase):
    def test_health(self) -> None:
        self.assertEqual(host.route("本机服务都活着吗")[0], "service_health")
        self.assertEqual(host.route("check service health")[0], "service_health")

    def test_arena_needs_ids(self) -> None:
        tool, args = host.route("查一下 100141 100241 100341 100441 100541 的作业")
        self.assertEqual(tool, "arena_lookup")
        self.assertEqual(args["def_ids"], [100141, 100241, 100341, 100441, 100541])

    def test_arena_without_ids_falls_through(self) -> None:
        self.assertIsNone(host.route("查一下竞技场的作业"))

    def test_memory_search_strips_politeness(self) -> None:
        tool, args = host.route("帮我回忆一下泳装插画那件事")
        self.assertEqual(tool, "memory_search")
        self.assertFalse(args["query"].startswith("帮我"))

    def test_art_defaults_and_count(self) -> None:
        tool, args = host.route("来两张初音未来泳装压缩图")
        self.assertEqual(tool, "art_search")
        self.assertEqual(args["count"], 2)
        self.assertIn("初音未来", args["query"])

    def test_arena_accepts_character_names(self) -> None:
        tool, args = host.route("布丁、克总、真琴、纺希、莉莎这个防守的作业")
        self.assertEqual(tool, "arena_lookup")
        self.assertEqual(args["defense"], ["布丁", "克总", "真琴", "纺希", "莉莎"])

    def test_arena_replace_keeps_slot(self) -> None:
        tool, args = host.route("布丁、克总、真琴、纺希、莉莎这个防守，把布丁换成怜，再查一次")
        self.assertEqual(tool, "arena_lookup")
        self.assertEqual(args["replace"], ["布丁->怜"])
        # 队形原样传给工具，替换在工具里按名字原地换掉（保住号位）。
        self.assertEqual(args["defense"], ["布丁", "克总", "真琴", "纺希", "莉莎"])

    def test_character_question_goes_to_lookup(self) -> None:
        tool, args = host.route("布丁和克总分别是哪个角色")
        self.assertEqual(tool, "character_lookup")
        self.assertEqual(args["query"], "布丁 克总")

    def test_unknown_sentence(self) -> None:
        self.assertIsNone(host.route("今天天气怎么样"))

    def test_speak_health(self) -> None:
        self.assertEqual(
            host._speak("service_health", HEALTH_JSON), "1/2 个服务在线。没起来的：b。"
        )

    def test_speak_arena(self) -> None:
        speech = host._speak("arena_lookup", ARENA_JSON)
        self.assertIn("找到 1 支队伍", speech)
        self.assertIn("9", speech)


if __name__ == "__main__":
    unittest.main()
