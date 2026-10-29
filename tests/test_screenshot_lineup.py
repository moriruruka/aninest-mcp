"""unittest coverage for the host-side screenshot glue (pure helpers only)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "demo"))

import screenshot_lineup as glue  # noqa: E402  (needs the sys.path tweak above)


class GridParseTest(unittest.TestCase):
    def test_parse_grid(self) -> None:
        self.assertEqual(glue.parse_grid("5x3"), (5, 3))
        self.assertEqual(glue.parse_grid("5X2"), (5, 2))
        self.assertEqual(glue.parse_grid("5×2"), (5, 2))

    def test_parse_grid_rejects_junk(self) -> None:
        for bad in ("5", "5x", "x3", "0x3", "5xa"):
            with self.assertRaises(ValueError):
                glue.parse_grid(bad)

    def test_parse_boxes(self) -> None:
        boxes = glue.parse_boxes("0,0,120,120; 130 0 120 120")
        self.assertEqual(len(boxes), 2)
        self.assertEqual(boxes[0], (0, 0, 120, 120))
        self.assertEqual(boxes[1], (130, 0, 120, 120))

    def test_parse_boxes_rejects_wrong_arity(self) -> None:
        with self.assertRaises(ValueError):
            glue.parse_boxes("0,0,120")


class GridBoxesTest(unittest.TestCase):
    def test_uniform_grid_covers_image(self) -> None:
        boxes = glue.grid_boxes(720, 288, 5, 2)
        self.assertEqual(len(boxes), 10)
        self.assertEqual(boxes[0], (0, 0, 144, 144))
        self.assertEqual(boxes[4], (576, 0, 144, 144))
        self.assertEqual(boxes[5], (0, 144, 144, 144))

    def test_inset_shaves_every_cell(self) -> None:
        box = glue.grid_boxes(720, 288, 5, 2, inset=6)[0]
        self.assertEqual(box, (6, 6, 132, 132))

    def test_inset_larger_than_cell_is_an_error(self) -> None:
        with self.assertRaises(ValueError):
            glue.grid_boxes(720, 288, 5, 2, inset=80)


class SlotOrderTest(unittest.TestCase):
    def test_rtl_puts_rightmost_first(self) -> None:
        # 5 crops left to right; slot 1 is the rightmost one.
        self.assertEqual(glue.slot_order(5, "rtl"), [4, 3, 2, 1, 0])

    def test_ltr_keeps_reading_order(self) -> None:
        self.assertEqual(glue.slot_order(5, "ltr"), [0, 1, 2, 3, 4])

    def test_unknown_order_is_an_error(self) -> None:
        with self.assertRaises(ValueError):
            glue.slot_order(5, "zigzag")


if __name__ == "__main__":
    unittest.main()
