"""Tests for the arena tool: pure validation plus payload flattening."""

from __future__ import annotations

import unittest

import context  # noqa: F401

from aninest.tools.arena import summarise, validate_ids


class ValidateIdsTests(unittest.TestCase):
    def test_accepts_six_digit_ids(self) -> None:
        self.assertEqual(validate_ids([100101, 100201]), [100101, 100201])

    def test_preserves_order_and_dedupes(self) -> None:
        self.assertEqual(validate_ids([100201, 100101, 100201]), [100201, 100101])

    def test_rejects_empty(self) -> None:
        with self.assertRaises(ValueError):
            validate_ids([])

    def test_rejects_too_many(self) -> None:
        with self.assertRaises(ValueError):
            validate_ids([100001, 100002, 100003, 100004, 100005, 100006, 100007])

    def test_rejects_out_of_range(self) -> None:
        with self.assertRaises(ValueError):
            validate_ids([12345])
        with self.assertRaises(ValueError):
            validate_ids([1234567])

    def test_rejects_non_numeric(self) -> None:
        with self.assertRaises(ValueError):
            validate_ids(["abc"])  # type: ignore[list-item]


class SummariseTests(unittest.TestCase):
    def test_flat_list_payload(self) -> None:
        payload = {"result": [{"atk": [100101], "likes": 12, "views": 340}]}
        result = summarise(payload)
        self.assertEqual(result["found"], 1)
        self.assertEqual(result["teams"][0]["likes"], 12)

    def test_nested_data_wrapper(self) -> None:
        payload = {"data": {"result": [{"team": [1, 2, 3], "like_num": 5}]}}
        result = summarise(payload)
        self.assertEqual(result["found"], 1)
        self.assertEqual(result["teams"][0]["likes"], 5)

    def test_empty_payload(self) -> None:
        self.assertEqual(summarise({}), {"found": 0, "teams": []})

    def test_limit_is_respected(self) -> None:
        payload = {"result": [{"atk": [i]} for i in range(6)]}
        self.assertEqual(len(summarise(payload, limit=2)["teams"]), 2)

    def test_garbage_rows_are_skipped(self) -> None:
        payload = {"result": ["nope", {"atk": [1]}]}
        self.assertEqual(summarise(payload)["found"], 2)
        self.assertEqual(len(summarise(payload)["teams"]), 1)


if __name__ == "__main__":
    unittest.main()
