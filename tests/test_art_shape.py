"""Tests for the pure filtering logic of the art search tool."""

from __future__ import annotations

import unittest

import context  # noqa: F401

from aninest.tools.art import shape_results


def post(**overrides: object) -> dict:
    base = {
        "id": 1,
        "width": 1200,
        "height": 1800,
        "rating": "safe",
        "tags": "hatsune_miku swimsuit",
        "file_url": "https://example.test/full.jpg",
        "sample_url": "https://example.test/sample.jpg",
        "preview_url": "https://example.test/preview.jpg",
    }
    base.update(overrides)
    return base


class ShapeResultsTests(unittest.TestCase):
    def test_compressed_prefers_sample(self) -> None:
        result = shape_results([post()], "compressed", None, 1)
        self.assertEqual(result[0]["image_url"], "https://example.test/sample.jpg")

    def test_original_prefers_file(self) -> None:
        result = shape_results([post()], "original", None, 1)
        self.assertEqual(result[0]["image_url"], "https://example.test/full.jpg")

    def test_missing_sample_falls_back(self) -> None:
        result = shape_results([post(sample_url="")], "compressed", None, 1)
        self.assertEqual(result[0]["image_url"], "https://example.test/preview.jpg")

    def test_non_safe_posts_are_dropped(self) -> None:
        self.assertEqual(shape_results([post(rating="questionable")], "compressed", None, 5), [])
        self.assertEqual(shape_results([post(rating="e")], "compressed", None, 5), [])

    def test_short_rating_alias_is_accepted(self) -> None:
        result = shape_results([post(rating="s")], "compressed", None, 5)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["rating"], "safe")

    def test_rating_absent_is_accepted(self) -> None:
        self.assertEqual(len(shape_results([post(rating=None)], "compressed", None, 5)), 1)

    def test_orientation_filter(self) -> None:
        portrait = post(width=1000, height=2000)
        landscape = post(id=2, width=2000, height=1000)
        square = post(id=3, width=1000, height=1000)
        rows = [portrait, landscape, square]
        self.assertEqual([r["id"] for r in shape_results(rows, "compressed", "portrait", 5)], [1])
        self.assertEqual([r["id"] for r in shape_results(rows, "compressed", "landscape", 5)], [2])
        self.assertEqual([r["id"] for r in shape_results(rows, "compressed", "square", 5)], [3])

    def test_count_is_respected(self) -> None:
        rows = [post(id=i) for i in range(1, 6)]
        self.assertEqual(len(shape_results(rows, "compressed", None, 2)), 2)

    def test_page_url_is_built(self) -> None:
        result = shape_results([post(id=42)], "compressed", None, 1)
        self.assertIn("id=42", result[0]["page_url"])

    def test_tags_are_truncated(self) -> None:
        result = shape_results([post(tags="x" * 900)], "compressed", None, 1)
        self.assertEqual(len(result[0]["tags"]), 400)


if __name__ == "__main__":
    unittest.main()
