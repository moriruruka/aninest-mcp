"""Host-side glue: one arena screenshot in, one lineup out.

This script is **deliberately not part of the server**. Cropping avatars out of a
screenshot is glue: every host frames its screenshots differently (device size,
UI version, how many rows are visible), so it belongs next to the host, not inside
the capability layer. The server only answers the narrow, stateless question
"which character is in this cropped portrait?".

The pipeline shown here has three steps:

    screenshot ──crop──► N portrait files ──portrait_identify──► ids ──arena_lookup──► teams

Step 1 (crop) is approximate on purpose: a uniform grid is enough for the common
"5 columns per row" layout, and ``--boxes`` lets you pin exact rectangles when it
is not. Step 2 and 3 are real MCP calls over stdio, exactly what a host would do.

Slot order matters. In this game the numbering runs **right to left** (slot 1 is
the rightmost, the front row), so the default ``--order rtl`` assigns slot 1 to
the rightmost crop of each row.

Usage::

    python demo/screenshot_lineup.py shot.png                      # 5x3 grid, first row
    python demo/screenshot_lineup.py shot.png --rows 2             # two rows, one lineup each
    python demo/screenshot_lineup.py shot.png --grid 5x3 --inset 6
    python demo/screenshot_lineup.py shot.png --boxes "0,0,120,120;130,0,120,120"
    python demo/screenshot_lineup.py shot.png --no-arena           # only identify
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------- cropping ---
def parse_grid(text: str) -> tuple[int, int]:
    """Parse ``"5x3"`` into ``(cols, rows)``."""

    parts = text.lower().replace("×", "x").split("x")
    if len(parts) != 2:
        raise ValueError(f"grid must look like 5x3, got {text!r}")
    cols, rows = int(parts[0]), int(parts[1])
    if cols < 1 or rows < 1:
        raise ValueError("grid needs at least one column and one row")
    return cols, rows


def parse_boxes(text: str) -> list[tuple[int, int, int, int]]:
    """Parse ``"x,y,w,h;x,y,w,h"`` into rectangles."""

    boxes: list[tuple[int, int, int, int]] = []
    for chunk in text.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        values = [int(part) for part in chunk.replace(",", " ").split()]
        if len(values) != 4:
            raise ValueError(f"each box needs x,y,w,h — got {chunk!r}")
        boxes.append((values[0], values[1], values[2], values[3]))
    if not boxes:
        raise ValueError("no boxes given")
    return boxes


def grid_boxes(
    width: int, height: int, cols: int, rows: int, inset: int = 0
) -> list[tuple[int, int, int, int]]:
    """Split an image into a uniform grid, shaving ``inset`` pixels off each cell."""

    if width <= 0 or height <= 0:
        raise ValueError("image has no area")
    cell_w, cell_h = width // cols, height // rows
    if cell_w <= 2 * inset or cell_h <= 2 * inset:
        raise ValueError("inset is larger than a cell")
    boxes: list[tuple[int, int, int, int]] = []
    for row in range(rows):
        for col in range(cols):
            boxes.append(
                (
                    col * cell_w + inset,
                    row * cell_h + inset,
                    cell_w - 2 * inset,
                    cell_h - 2 * inset,
                )
            )
    return boxes


def slot_order(count: int, order: str = "rtl") -> list[int]:
    """Map crop order (left to right) onto slot numbers.

    Returns the crop indices sorted into slot order: for ``rtl`` the rightmost
    crop becomes slot 1, which is how arena lineups are numbered in game;
    ``ltr`` keeps reading order.
    """

    indices = list(range(count))
    if order == "rtl":
        return list(reversed(indices))
    if order == "ltr":
        return indices
    raise ValueError(f"order must be rtl or ltr, got {order!r}")


def crop_all(image_path: Path, boxes: list[tuple[int, int, int, int]], out_dir: Path) -> list[Path]:
    """Write one PNG per box and return the paths in the given order."""

    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - exercised only without deps
        raise SystemExit("需要 Pillow 才能裁图：pip install pillow") from exc

    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    with Image.open(image_path) as opened:
        image = opened.convert("RGB")
        for index, box in enumerate(boxes, start=1):
            target = out_dir / f"cell-{index:02d}.png"
            image.crop((box[0], box[1], box[0] + box[2], box[1] + box[3])).save(target)
            written.append(target)
    return written


# -------------------------------------------------------------- MCP side ---
def _env() -> dict[str, str]:
    import os

    env = dict(os.environ)
    env.setdefault("PYTHONPATH", str(ROOT / "src"))
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


def _payload(result) -> dict:
    for block in result.content:
        text = getattr(block, "text", None)
        if text:
            return json.loads(text)
    return {}


async def identify(crops: list[Path], min_score: float, top_k: int) -> list[dict]:
    """Call ``portrait_identify`` once (it accepts a list) and flatten the answers."""

    params = StdioServerParameters(
        command=sys.executable, args=["-m", "aninest"], env=_env(), cwd=str(ROOT)
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "portrait_identify",
                {
                    "images": [str(path) for path in crops],
                    "top_k": top_k,
                    "min_score": min_score,
                },
            )
            if result.isError:
                raise SystemExit(f"portrait_identify 失败：{_payload(result)}")
            data = _payload(result)
            return data.get("results") or []


async def lookup(ids: list[int], limit: int) -> dict:
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "aninest"], env=_env(), cwd=str(ROOT)
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "arena_lookup", {"def_ids": ids, "limit": limit}
            )
            if result.isError:
                raise SystemExit(f"arena_lookup 失败：{_payload(result)}")
            return _payload(result)


# ------------------------------------------------------------------ main ---
def main() -> int:
    parser = argparse.ArgumentParser(description="screenshot -> lineup (host-side glue)")
    parser.add_argument("screenshot", help="arena screenshot (png/jpg)")
    parser.add_argument("--grid", default="5x3", help="cols x rows, default 5x3")
    parser.add_argument("--boxes", help="explicit rectangles: x,y,w,h;x,y,w,h")
    parser.add_argument("--inset", type=int, default=0, help="pixels to shave off each cell")
    parser.add_argument("--order", default="rtl", choices=("rtl", "ltr"))
    parser.add_argument("--rows", type=int, default=1, help="how many rows to read (default 1)")
    parser.add_argument("--min-score", type=float, default=0.55)
    parser.add_argument("--top-k", type=int, default=2)
    parser.add_argument("--limit", type=int, default=3, help="how many teams to fetch")
    parser.add_argument("--no-arena", action="store_true", help="only identify, skip the lookup")
    parser.add_argument("--keep", help="keep the cropped cells in this directory")
    options = parser.parse_args()

    shot = Path(options.screenshot).expanduser()
    if not shot.is_file():
        raise SystemExit(f"截图不存在：{shot}")

    from PIL import Image

    with Image.open(shot) as opened:
        width, height = opened.size

    if options.boxes:
        boxes = parse_boxes(options.boxes)
        cols = len(boxes)
        rows = 1
    else:
        cols, rows = parse_grid(options.grid)
        boxes = grid_boxes(width, height, cols, rows, max(0, options.inset))

    rows = max(1, min(rows, options.rows))
    out_dir = Path(options.keep) if options.keep else Path(tempfile.mkdtemp(prefix="aninest-crop-"))
    crops = crop_all(shot, boxes, out_dir)
    print(f"[crop] {width}x{height} -> {len(boxes)} cells in {out_dir}")

    lineups: list[list[int]] = []
    for row in range(rows):
        offset = row * cols
        cells = crops[offset : offset + cols]
        results = asyncio.run(identify(cells, options.min_score, options.top_k))
        print()
        print(f"第 {row + 1} 行（{cols} 个格子，按 {options.order} 编 1..{cols} 号位）")
        ids: list[int] = []
        for slot, cell_index in enumerate(slot_order(len(results), options.order), start=1):
            result = results[cell_index]
            best = result.get("best") or {}
            name = best.get("name") or "未知"
            score = best.get("score")
            hint = "" if result.get("known") else "  ← 低于阈值，建议人工核对"
            score_text = f"{score:.2f}" if isinstance(score, float) else "—"
            print(f"  {slot} 号位  {name}（{best.get('id', '?')}）  {score_text}{hint}")
            if result.get("known") and best.get("id"):
                ids.append(int(best["id"]))
        lineups.append(ids)

    if options.no_arena:
        return 0

    for number, ids in enumerate(lineups, start=1):
        if not ids:
            continue
        data = asyncio.run(lookup(ids, options.limit))
        lineup = data.get("lineup") or []
        described = " / ".join(
            f"{item.get('slot')}号位 {item.get('name')}" for item in lineup
        )
        print()
        print(f"[arena] 第 {number} 行 {described}：找到 {data.get('found', 0)} 支队伍")
        for team in (data.get("teams") or [])[:2]:
            names = team.get("defense_names") or team.get("defense") or []
            print(f"  - {' / '.join(str(n) for n in names)}（赞 {team.get('upvotes')}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
