"""Generate a synthetic avatar pack so `portrait_identify` can be demonstrated.

Real avatar art cannot ship with the repository (it belongs to the game), so this
script draws geometric portraits instead: one file per character id, plus a
`manifest.json` naming them. Matching still works because the tool compares the
middle band of the image — the same region these drawings vary.

    python scripts/make_demo_avatars.py --out demo_avatars
    ANINEST_PCR_AVATARS=$PWD/demo_avatars python scripts/mcp_smoke.py \
        --call portrait_identify --args '{"images": ["demo_avatars/100101.png"]}'

The ids below are real arena ids, so the returned names are meaningful:
100101 日和, 100201 优衣, 100301 怜, 100701 宫子, 107101 克莉丝提娜.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if _reconfigure is not None:  # Windows consoles default to a legacy code page
        _reconfigure(encoding="utf-8", errors="replace")

PALETTE = [
    (100101, (214, 92, 96), (250, 236, 210)),
    (100201, (86, 132, 208), (240, 244, 252)),
    (100301, (94, 168, 124), (238, 248, 238)),
    (100701, (150, 108, 196), (244, 238, 252)),
    (107101, (206, 140, 72), (252, 244, 232)),
]

SIZE = (144, 144)


def draw(char_id: int, hair: tuple[int, int, int], skin: tuple[int, int, int], seed: int) -> object:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", SIZE, (250, 250, 252))
    paint = ImageDraw.Draw(image)
    # 简化到"脸 + 刘海"两块：中间那条带（0.12–0.88 高度）必须随角色而变化。
    paint.ellipse((34, 30, 110, 122), fill=skin, outline=(90, 90, 100), width=2)
    paint.pieslice((28, 14, 116, 92), start=180, end=360, fill=hair)
    paint.rectangle((28 + seed % 7, 40, 116, 54), fill=hair)
    paint.ellipse((52, 66, 66, 80), fill=(60, 60, 70))
    paint.ellipse((78, 66, 92, 80), fill=(60, 60, 70))
    paint.arc((58, 88, 86, 106), start=10, end=170, fill=(150, 80, 80), width=3)
    return image


def main() -> int:
    parser = argparse.ArgumentParser(description="生成一份合成头像包")
    parser.add_argument("--out", required=True, help="输出目录（会创建）")
    options = parser.parse_args()

    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        print('需要 Pillow：pip install -e ".[vision]"')
        return 2

    target = Path(options.out).resolve()
    target.mkdir(parents=True, exist_ok=True)

    manifest = []
    for index, (char_id, hair, skin) in enumerate(PALETTE):
        image = draw(char_id, hair, skin, seed=index * 11)
        path = target / f"{char_id}.png"
        image.save(path)  # type: ignore[attr-defined]
        manifest.append({"id": char_id, "file": path.name})
        print(f"wrote {path}")

    (target / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n下一步：\n  set ANINEST_PCR_AVATARS={target}")
    print("  python scripts/live_check.py --avatars")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
