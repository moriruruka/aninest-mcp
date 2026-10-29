"""Portrait identification: which character is this 128×128 avatar?

The arena screenshot problem is two problems: find the portrait boxes, then say
who is in each box. Finding boxes is layout work that depends on the game UI and
belongs to whoever owns the screenshot; naming a crop is a capability, and that
is what this module does — one image in, ranked characters out.

Matching is normalised cross-correlation between grayscale, zero-mean, unit-norm
tiles. It is the same idea as the assistant's original face-band comparison,
without pulling in OpenCV: PIL decodes, numpy does the arithmetic.

Why the avatar pack is not in the repo: the images are game art. Point
``ANINEST_PCR_AVATARS`` at a directory of ``<six-digit-id>.<png|webp|jpg>`` files
that you already have, and matching turns on. Without the pack the tool says so
instead of guessing.
"""

from __future__ import annotations

import base64
import binascii
import os
from collections.abc import Iterable, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any

_IMAGE_SUFFIXES = (".png", ".webp", ".jpg", ".jpeg", ".bmp")
_SIDE = 72
#: Full tile plus two overlay crops: the game frames differ between screens
#: (rank badges, level text), so the best of three views beats one fixed crop.
_CROPS = ((0.0, 1.0), (0.12, 0.88), (0.24, 0.76))


class VisionUnavailable(RuntimeError):
    """Raised when numpy/Pillow or the avatar pack is missing."""


#: Imported once, on the main thread, at module load.
#: Doing this lazily inside a tool call costs ~15 s in some environments: the import
#: runs on a worker thread while the server's event loop is blocked on stdio, and the
#: two contend for the import lock. Paying it at startup keeps the first call fast.
try:  # pragma: no cover - exercised by import, not by a test branch
    import numpy as _np
    from PIL import Image as _Image
except ImportError:  # pragma: no cover - depends on install extras
    _np = None
    _Image = None


def _require_deps() -> tuple[Any, Any]:
    if _np is None or _Image is None:
        raise VisionUnavailable(
            "portrait matching needs the [vision] extra: pip install 'aninest-mcp[vision]'"
        )
    return _np, _Image


def pack_dir() -> Path | None:
    """Directory holding the avatar images, or None when unset."""

    from ..config import SETTINGS

    raw = (SETTINGS.pcr_avatars or os.environ.get("ANINEST_PCR_AVATARS", "")).strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    return path if path.is_dir() else None


def _tile(np: Any, image: Any) -> list[Any]:
    """Grayscale, zero-mean, unit-norm views of one image."""

    gray = image.convert("L")
    width, height = gray.size
    views = []
    for top, bottom in _CROPS:
        box = (
            int(width * 0.06),
            int(height * top) + int(height * 0.06),
            int(width * 0.94),
            int(height * bottom) - int(height * 0.06),
        )
        crop = gray.crop(box).resize((_SIDE, _SIDE))
        arr = np.asarray(crop, dtype="float32").ravel()
        arr = arr - arr.mean()
        norm = float(np.linalg.norm(arr))
        if norm < 1e-6:
            views.append(None)
        else:
            views.append(arr / norm)
    return views


def _load_bytes(image: Any, Image: Any) -> Any:
    import io

    if isinstance(image, (bytes, bytearray)):
        return Image.open(io.BytesIO(bytes(image)))
    if isinstance(image, (str, Path)):
        text = str(image)
        candidate = Path(text).expanduser()
        if candidate.is_file():
            return Image.open(candidate)
        payload = text.split(",", 1)[1] if text.startswith("data:") else text
        try:
            return Image.open(io.BytesIO(base64.b64decode(payload, validate=False)))
        except (binascii.Error, ValueError) as exc:
            raise ValueError("image is neither a readable path nor base64 data") from exc
    raise ValueError("image must be a path, raw bytes or base64 text")


@lru_cache(maxsize=1)
def _pack(signature: tuple[str, float]) -> list[tuple[int, list[Any]]]:
    """Load and tile every avatar in the pack (cached per mtime signature)."""

    np, Image = _require_deps()
    root = Path(signature[0])
    entries: list[tuple[int, list[Any]]] = []
    for path in sorted(root.iterdir()):
        if path.suffix.lower() not in _IMAGE_SUFFIXES:
            continue
        stem = path.stem
        if not stem.isdigit():
            continue
        try:
            with Image.open(path) as handle:
                views = _tile(np, handle.convert("RGBA"))
        except Exception:  # pragma: no cover - a corrupt file must not break the pack
            continue
        entries.append((int(stem), views))
    return entries


def _pack_signature() -> tuple[str, float]:
    root = pack_dir()
    if root is None:
        raise VisionUnavailable(
            "avatar pack not configured: set ANINEST_PCR_AVATARS to a directory of "
            "<six-digit-id>.png/.webp files (game art is not redistributed here)"
        )
    try:
        mtime = max((p.stat().st_mtime for p in root.iterdir()), default=0.0)
    except OSError as exc:
        raise VisionUnavailable(f"cannot read avatar pack {root}: {exc}") from exc
    return str(root), round(mtime, 3)


def pack_size() -> int:
    try:
        return len(_pack(_pack_signature()))
    except VisionUnavailable:
        return 0


def identify(images: Iterable[Any], top_k: int = 3, min_score: float = 0.55) -> dict[str, Any]:
    """Rank characters for each image.

    Args:
        images: paths, raw bytes or base64 strings — one portrait each.
        top_k: candidates per image (1-10).
        min_score: similarity floor; below it the result is reported as unknown.
    """

    np, Image = _require_deps()
    signature = _pack_signature()
    entries = _pack(signature)
    if not entries:
        raise VisionUnavailable(f"avatar pack {signature[0]} has no usable images")

    limit = max(1, min(10, int(top_k)))
    floor = max(0.0, min(1.0, float(min_score)))
    wanted = list(images)
    if not wanted:
        raise ValueError("images is empty")

    results = []
    for item in wanted:
        handle = _load_bytes(item, Image)
        views = _tile(np, handle)
        scored: list[tuple[float, int]] = []
        for char_id, views_ref in entries:
            best = -1.0
            for left, right in zip(views, views_ref, strict=True):
                if left is None or right is None:
                    continue
                score = float(np.dot(left, right))
                if score > best:
                    best = score
            if best > -1.0:
                scored.append((best, char_id))
        scored.sort(key=lambda pair: (-pair[0], pair[1]))
        top = [
            {"id": char_id, "score": round(score, 4)}
            for score, char_id in scored[:limit]
            if score >= floor
        ]
        results.append(
            {
                "best": top[0] if top else None,
                "candidates": top,
                "known": bool(top),
            }
        )
    return {"pack": signature[0], "images": len(results), "results": results}


def discover_pack(root: Path | str | None = None, limit: int = 20) -> dict[str, Any]:
    """Report how many avatars the pack can see (useful when first wiring it up)."""

    _require_deps()
    directory = Path(root).expanduser() if root else pack_dir()
    if directory is None or not directory.is_dir():
        raise VisionUnavailable("ANINEST_PCR_AVATARS is not set to an existing directory")
    files = [p for p in directory.iterdir() if p.suffix.lower() in _IMAGE_SUFFIXES]
    return {
        "dir": str(directory),
        "files": len(files),
        "sample": [p.name for p in sorted(files)[: max(1, limit)]],
    }


def ids_to_names(ids: Sequence[int]) -> list[str]:
    """Character names for identified ids (empty names when unknown)."""

    from . import pcr

    index = pcr.index()
    return [index.name_of(char_id) for char_id in ids]
