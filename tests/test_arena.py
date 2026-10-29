"""Tests for the arena tool: pure validation plus payload flattening.

`fixtures/arena_payload.json` is a trimmed **real** response captured from the live
service (`{"ok": true, "data": {"code": 0, "data": {"result": [...]}}}`), so the
flattening test fails if the tool stops understanding the shape it actually receives.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import context  # noqa: F401

from aninest.tools.arena import summarise, validate_ids

FIXTURE = Path(__file__).parent / "fixtures" / "arena_payload.json"


class ValidateIdsTests(unittest.TestCase):
    def test_accepts_six_digit_ids(self) -> None:
        self.assertEqual(validate_ids([100101, 100201]), [100101, 100201])

    def test_preserves_order_and_dedupes(self) -> None:
        self.assertEqual(validate_ids([100201, 100101, 100201]), [100201, 100101])

    def test_rejects_empty(self) -> None:
        with self.assertRaises(ValueError):
            validate_ids([])

    def test_accepts_a_full_lineup(self) -> None:
        ids = [100101, 100201, 100301, 100401, 100501]
        self.assertEqual(validate_ids(ids), ids)

    def test_rejects_too_many(self) -> None:
        with self.assertRaises(ValueError):
            validate_ids([100001, 100002, 100003, 100004, 100005, 100006])

    def test_duplicates_do_not_count_towards_the_limit(self) -> None:
        self.assertEqual(validate_ids([100101] * 6), [100101])

    def test_rejects_out_of_range(self) -> None:
        with self.assertRaises(ValueError):
            validate_ids([12345])
        with self.assertRaises(ValueError):
            validate_ids([1234567])

    def test_rejects_non_numeric(self) -> None:
        with self.assertRaises(ValueError):
            validate_ids(["abc"])  # type: ignore[list-item]


class SummariseTests(unittest.TestCase):
    def test_live_payload_shape(self) -> None:
        """The shape we captured from the running service must flatten cleanly."""
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        result = summarise(payload, limit=1)
        self.assertEqual(result["found"], 2)
        team = result["teams"][0]
        self.assertEqual(len(team["defense"]), 5)
        self.assertTrue(all(isinstance(i, int) for i in team["defense"]))
        self.assertEqual(len(team["attack"]), 5)
        self.assertIsInstance(team["upvotes"], int)
        self.assertTrue(team["ref"])

    def test_flat_list_payload(self) -> None:
        payload = {"result": [{"atk": [{"id": 100101}], "up": 12}]}
        result = summarise(payload)
        self.assertEqual(result["found"], 1)
        self.assertEqual(result["teams"][0]["attack"], [100101])
        self.assertEqual(result["teams"][0]["upvotes"], 12)

    def test_unknown_shape_yields_nothing(self) -> None:
        self.assertEqual(summarise({"data": {"result": [{"team": [1, 2, 3]}]}})["found"], 0)

    def test_empty_payload(self) -> None:
        self.assertEqual(summarise({}), {"found": 0, "teams": []})

    def test_empty_result_inside_wrappers(self) -> None:
        payload = {"ok": True, "data": {"code": 0, "data": {"result": []}}}
        self.assertEqual(summarise(payload), {"found": 0, "teams": []})

    def test_limit_is_respected(self) -> None:
        payload = {"result": [{"atk": [{"id": i}]} for i in range(6)]}
        self.assertEqual(len(summarise(payload, limit=2)["teams"]), 2)

    def test_garbage_rows_are_skipped(self) -> None:
        payload = {"result": ["nope", {"atk": [{"id": 100101}]}]}
        self.assertEqual(summarise(payload)["found"], 1)

    def test_summarise_includes_names(self) -> None:
        raw = FIXTURE.read_text(encoding="utf-8")
        payload = json.loads(raw)
        data = summarise(payload, limit=1)
        team = data["teams"][0]
        self.assertEqual(len(team["defense_names"]), len(team["defense"]))
        self.assertTrue(all(isinstance(name, str) and name for name in team["defense_names"]))


if __name__ == "__main__":
    unittest.main()
