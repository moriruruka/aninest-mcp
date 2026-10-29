#!/usr/bin/env python3
"""Regenerate the packaged character table (``src/aninest/data/pcr_chars.json``).

The table only carries facts: id, 4-digit uid, display name, Japanese name,
alias list and server flags. It is produced from a local assistant install that
already maintains the same data; nothing here is game art or user data.

Usage::

    python scripts/port_characters.py --source "D:/path/to/plugin_data/pcrbot"

The source directory is expected to contain ``characters.json``
(``{"characters": [...]}``) and optionally ``aliases_extra.json`` /
``aliases_remove.json``. After running, commit the generated JSON.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TARGET = REPO_ROOT / "src" / "aninest" / "data" / "pcr_chars.json"


def _clean(values):
    seen = set()
    out = []
    for raw in values or []:
        if not isinstance(raw, str):
            continue
        value = raw.strip()
        key = value.casefold()
        if not value or key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def build(source: Path) -> dict:
    payload = json.loads((source / "characters.json").read_text(encoding="utf-8"))
    characters = payload.get("characters") or []

    extra_path = source / "aliases_extra.json"
    extras: dict[int, list[str]] = {}
    if extra_path.exists():
        raw = json.loads(extra_path.read_text(encoding="utf-8"))
        for key, values in raw.items():
            try:
                uid4 = int(key)
            except (TypeError, ValueError):
                continue
            if isinstance(values, list):
                extras.setdefault(uid4, []).extend(values)

    remove_path = source / "aliases_remove.json"
    banned: dict[int, set[str]] = {}
    if remove_path.exists():
        raw = json.loads(remove_path.read_text(encoding="utf-8"))
        for key, values in raw.items():
            try:
                char_id = int(key)
            except (TypeError, ValueError):
                continue
            if isinstance(values, list):
                banned.setdefault(char_id, set()).update(
                    str(value).strip() for value in values
                )

    rows = []
    for item in characters:
        try:
            char_id = int(item["id"])
        except (KeyError, TypeError, ValueError):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        uid4 = int(item.get("uid4") or char_id // 100)
        aliases = _clean(item.get("aliases") or [])
        aliases += _clean(extras.get(uid4, []))
        drop = banned.get(char_id) or set()
        aliases = [alias for alias in aliases if alias not in drop and alias != name]
        rows.append(
            {
                "id": char_id,
                "uid4": uid4,
                "name": name,
                "jp": str(item.get("name_jp") or ""),
                "aliases": aliases,
                "servers": [s for s in (item.get("servers") or []) if isinstance(s, str)],
            }
        )

    rows.sort(key=lambda row: row["id"])
    stats = payload.get("stats") or {}
    return {
        "schema": 1,
        "source": "local assistant character table (ids/names/aliases)",
        "count": len(rows),
        "stats": {
            "cn": int(stats.get("cn") or 0),
            "us": int(stats.get("us") or 0),
            "zh": int(stats.get("zh") or 0),
        },
        "characters": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="directory holding characters.json")
    parser.add_argument("--target", default=str(TARGET))
    args = parser.parse_args()

    data = build(Path(args.source).expanduser())
    target = Path(args.target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    aliases = sum(len(row["aliases"]) for row in data["characters"])
    size = target.stat().st_size
    print(f"wrote {target} ({size} bytes, {data['count']} characters, {aliases} aliases)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
