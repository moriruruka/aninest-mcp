"""Check the tools against **your own** running stack, through real MCP stdio.

Unit tests use fixtures; this script is the other half — it talks to whatever is actually
running on this machine and tells you, tool by tool, whether it still works.

    python scripts/live_check.py
    python scripts/live_check.py --ids 100101 100201      # optional defence lineup
    python scripts/live_check.py --skip-network           # no internet, skip art_search
    python scripts/live_check.py --memory-db path/to/memory.db   # 指定记忆库
    python scripts/live_check.py --lineup 布丁 克总 真琴         # 按角色名查作业
    python scripts/live_check.py --avatars demo_avatars          # 头像包就位时验识图

Exit code is 0 only when every checked tool passed, so it is safe to use in a smoke run.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if _reconfigure is not None:  # Windows consoles default to a legacy code page
        _reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IDS = [100101, 100201]


def _first_line(text: str) -> str:
    return text.strip().splitlines()[0] if text.strip() else ""


async def _call(session: ClientSession, tool: str, arguments: dict) -> tuple[bool, str]:
    result = await session.call_tool(tool, arguments)
    text = "".join(
        getattr(block, "text", "") for block in result.content if getattr(block, "text", None)
    )
    if result.isError:
        return False, _first_line(text)[:160]
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return True, _first_line(text)[:120]
    return True, payload


def _check_health(payload: dict) -> str:
    down = [name for name, item in (payload.get("services") or {}).items() if not item.get("up")]
    state = f"{payload.get('up')}/{payload.get('total')} up"
    return f"{state}, down: {', '.join(down)}" if down else state


def _check_memory_stats(payload: dict) -> str:
    scopes = payload.get("by_scope") or {}
    return (
        f"rows={payload.get('rows')} "
        f"global={scopes.get('global', 0)} session={scopes.get('session', 0)}"
    )


def _check_memory_search(payload: dict) -> str:
    return f"scanned={payload.get('scanned')} matched={payload.get('matched')}"


def _check_arena(payload: dict) -> str:
    teams = payload.get("teams") or []
    if not teams:
        return f"found={payload.get('found')} (no teams for this lineup)"
    team = teams[0]
    return (
        f"found={payload.get('found')} defense={team.get('defense')} "
        f"up={team.get('upvotes')}"
    )


def _check_character(payload: dict) -> str:
    matches = payload.get("matches") or []
    if not matches:
        return "no match"
    names = "、".join(f"{item.get('name')}({item.get('id')})" for item in matches)
    unknown = payload.get("unresolved") or []
    return f"matches={len(matches)} {names}" + (f" unresolved={unknown}" if unknown else "")


def _check_portrait(payload: dict) -> str:
    results = payload.get("results") or []
    if not results:
        return "no portraits"
    best = results[0].get("best") or {}
    return f"{len(results)} portrait(s) best={best.get('name')} score={best.get('score')}"


def _check_match(payload: dict) -> str:
    if not payload.get("ok", True):
        return str(payload)
    matches = payload.get("matches") or []
    if not matches:
        return "no candidate"
    top = matches[0]
    return f"{top['id']} {top['name']} score={top['score']} via={top['matched_on']}"


def _check_update(payload: dict) -> str:
    character = payload.get("character") or {}
    return (
        f"{payload.get('action')} {character.get('id')} {character.get('name')} "
        f"aliases={len(character.get('aliases') or [])} overlay={payload.get('overlay')}"
    )


def _check_correct(payload: dict) -> str:
    return f"{payload.get('action')} {payload.get('term')} -> {payload.get('name')}"


def _check_art(payload: dict) -> str:
    images = payload.get("results") or []
    if not images:
        return "no images"
    first = images[0]
    size = f"{first.get('width')}x{first.get('height')}"
    return f"{len(images)} image(s) {size} rating={first.get('rating')}"


async def run(
    ids: list[int],
    skip_network: bool,
    memory_db: str | None = None,
    lineup: list[str] | None = None,
    avatars: str | None = None,
) -> int:
    env = dict(os.environ)
    if memory_db:
        env["ANINEST_MEMORY_DB"] = str(Path(memory_db).expanduser().resolve())
    if avatars:
        env["ANINEST_PCR_AVATARS"] = str(Path(avatars).expanduser().resolve())
    env.setdefault("PYTHONPATH", str(ROOT / "src"))
    # Exercise the two write tools against a throwaway overlay, never the real one.
    scratch = tempfile.TemporaryDirectory(prefix="aninest-live-")
    env["ANINEST_PCR_OVERLAY"] = str(Path(scratch.name) / "pcr_overlay.json")
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "aninest"], env=env, cwd=str(ROOT)
    )

    arena_args: dict = (
        {"defense": lineup, "limit": 2} if lineup else {"def_ids": ids, "limit": 2}
    )
    checks: list[tuple[str, dict, object, bool]] = [
        ("service_health", {}, _check_health, True),
        ("memory_stats", {}, _check_memory_stats, True),
        ("memory_search", {"query": "竞技场", "limit": 2}, _check_memory_search, True),
        ("character_lookup", {"query": "布丁 克总", "limit": 3}, _check_character, True),
        ("arena_lookup", arena_args, _check_arena, True),
        ("character_match", {"query": "宫紫", "threshold": 0.4}, _check_match, True),
        ("character_update", {"char_id": 199901, "name": "检查用角色", "jp": "チェック用",
                              "aliases": ["检查别名"]}, _check_update, True),
        ("character_correct", {"term": "宫紫", "char_id": 100701}, _check_correct, True),
        ("art_search", {"query": "hatsune_miku swimsuit", "count": 1},
         _check_art, not skip_network),
    ]
    pack = env.get("ANINEST_PCR_AVATARS")
    if pack:
        images = sorted(Path(pack).glob("*"))
        images = [item for item in images if item.suffix.lower() in {".png", ".webp", ".jpg"}]
        if images:
            checks.append(
                ("portrait_identify", {"images": [str(images[0])]}, _check_portrait, True)
            )

    print(f"memory db : {env.get('ANINEST_MEMORY_DB', '(default)')}")
    print(f"arena url : {env.get('ANINEST_ARENA_URL', '(default)')}")
    print(f"lineup    : {lineup if lineup else ids}")
    print(f"avatars   : {env.get('ANINEST_PCR_AVATARS', '(not configured)')}")
    print()

    failures = 0
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = {item.name for item in (await session.list_tools()).tools}
            print(f"tools ({len(tools)}): {', '.join(sorted(tools))}\n")

            for tool, arguments, summarise, enabled in checks:
                if tool not in tools:
                    print(f"[FAIL] {tool:<15} not registered")
                    failures += 1
                    continue
                if not enabled:
                    print(f"[skip] {tool:<15} (--skip-network)")
                    continue
                try:
                    ok, detail = await _call(session, tool, arguments)
                except Exception as exc:  # noqa: BLE001 - report, don't crash the sweep
                    print(f"[FAIL] {tool:<15} {type(exc).__name__}: {exc}")
                    failures += 1
                    continue
                if ok:
                    print(f"[ ok ] {tool:<15} {summarise(detail)}")
                else:
                    print(f"[FAIL] {tool:<15} {detail}")
                    failures += 1

    print()
    print("all checks passed" if failures == 0 else f"{failures} check(s) failed")
    return 0 if failures == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Live check of the tools")
    parser.add_argument(
        "--ids", type=int, nargs="+", default=DEFAULT_IDS, help="defence lineup ids"
    )
    parser.add_argument("--skip-network", action="store_true", help="skip art_search")
    parser.add_argument(
        "--memory-db", help="path to the assistant's memory.db (overrides ANINEST_MEMORY_DB)"
    )
    parser.add_argument(
        "--lineup", nargs="+", help="look the lineup up by character name instead of ids"
    )
    parser.add_argument("--avatars", help="avatar pack directory for portrait_identify")
    options = parser.parse_args()
    return asyncio.run(
        run(options.ids, options.skip_network, options.memory_db, options.lineup, options.avatars)
    )


if __name__ == "__main__":
    raise SystemExit(main())
