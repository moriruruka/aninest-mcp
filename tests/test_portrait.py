"""Portrait identification: crop a portrait, get the character back.

The avatar images are game art, so the repo ships none. These tests build a tiny
synthetic pack in a temporary directory — two clearly different patterns — and
check that the scoring actually discriminates instead of always returning the
first entry.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import context  # noqa: F401

from aninest.tools import portrait

try:  # the vision extra is optional; skip cleanly when it is absent
    from PIL import Image, ImageDraw

    HAVE_VISION = True
except ImportError:  # pragma: no cover - exercised only on slim installs
    HAVE_VISION = False


def _write_pattern(directory: Path, name: str, kind: str) -> Path:
    """Two visually distinct 128×128 avatars with a border, like the game's frames."""

    image = Image.new("RGBA", (128, 128), (30, 30, 40, 255))
    draw = ImageDraw.Draw(image)
    if kind == "diagonal":
        for offset in range(-128, 128, 8):
            draw.line([(0, offset), (128, offset + 128)], fill=(240, 200, 80, 255), width=6)
    else:
        draw.ellipse([28, 28, 100, 100], fill=(90, 200, 240, 255))
        draw.rectangle([54, 20, 74, 108], fill=(240, 120, 160, 255))
    draw.rectangle([0, 0, 127, 127], outline=(200, 200, 200, 255), width=4)
    path = directory / f"{name}.png"
    image.save(path)
    return path


@unittest.skipUnless(HAVE_VISION, "needs the [vision] extra (numpy + Pillow)")
class IdentifyTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.pack = Path(self._tmp.name) / "pack"
        self.pack.mkdir()
        self.diag = _write_pattern(self.pack, "100101", "diagonal")
        self.circle = _write_pattern(self.pack, "100201", "circle")
        self._old = os.environ.get("ANINEST_PCR_AVATARS")
        os.environ["ANINEST_PCR_AVATARS"] = str(self.pack)
        portrait._pack.cache_clear()

    def tearDown(self) -> None:
        if self._old is None:
            os.environ.pop("ANINEST_PCR_AVATARS", None)
        else:
            os.environ["ANINEST_PCR_AVATARS"] = self._old
        portrait._pack.cache_clear()
        self._tmp.cleanup()

    def test_pack_is_seen(self) -> None:
        self.assertEqual(portrait.pack_size(), 2)

    def test_identifies_the_original(self) -> None:
        result = portrait.identify([str(self.diag)], top_k=2)
        best = result["results"][0]["best"]
        self.assertIsNotNone(best)
        self.assertEqual(best["id"], 100101)
        self.assertGreater(best["score"], 0.95)

    def test_does_not_confuse_the_two(self) -> None:
        result = portrait.identify([str(self.circle)], top_k=2)
        candidates = result["results"][0]["candidates"]
        self.assertEqual(candidates[0]["id"], 100201)
        self.assertLess(candidates[0]["score"], 1.0001)

    def test_accepts_raw_bytes(self) -> None:
        result = portrait.identify([self.diag.read_bytes()], top_k=1)
        self.assertEqual(result["results"][0]["best"]["id"], 100101)

    def test_accepts_base64(self) -> None:
        import base64

        encoded = base64.b64encode(self.circle.read_bytes()).decode()
        result = portrait.identify([encoded], top_k=1)
        self.assertEqual(result["results"][0]["best"]["id"], 100201)

    def test_min_score_can_declare_unknown(self) -> None:
        noisy = Image.new("RGB", (128, 128), (128, 128, 128))
        noisy_path = Path(self._tmp.name) / "noise.png"
        noisy.save(noisy_path)
        result = portrait.identify([str(noisy_path)], top_k=3, min_score=0.95)
        self.assertFalse(result["results"][0]["known"])
        self.assertIsNone(result["results"][0]["best"])

    def test_empty_input_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            portrait.identify([])

    def test_bad_base64_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            portrait.identify(["/definitely/not/a/file.png"])


@unittest.skipUnless(HAVE_VISION, "needs the [vision] extra (numpy + Pillow)")
class MissingPackTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old = os.environ.pop("ANINEST_PCR_AVATARS", None)
        portrait._pack.cache_clear()

    def tearDown(self) -> None:
        if self._old is not None:
            os.environ["ANINEST_PCR_AVATARS"] = self._old
        portrait._pack.cache_clear()

    def test_unset_pack_explains_itself(self) -> None:
        with self.assertRaises(portrait.VisionUnavailable) as caught:
            portrait.identify(["whatever.png"])
        self.assertIn("ANINEST_PCR_AVATARS", str(caught.exception))

    def test_pack_size_is_zero_without_pack(self) -> None:
        self.assertEqual(portrait.pack_size(), 0)


@unittest.skipUnless(HAVE_VISION, "needs the [vision] extra (numpy + Pillow)")
class DiscoverTests(unittest.TestCase):
    def test_discover_lists_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_pattern(root, "100101", "diagonal")
            report = portrait.discover_pack(root)
            self.assertEqual(report["files"], 1)
            self.assertEqual(report["sample"], ["100101.png"])


if __name__ == "__main__":
    unittest.main()
