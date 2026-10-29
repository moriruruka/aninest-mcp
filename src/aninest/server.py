"""MCP server exposing AniNest capabilities to any MCP-compatible agent host.

Run over stdio (default)::

    python -m aninest

Run over Streamable HTTP::

    ANINEST_MCP_TRANSPORT=streamable-http ANINEST_MCP_PORT=8765 python -m aninest
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from .config import SETTINGS
from .tools import arena, art, health, memory, pcr, portrait
from .version import VERSION

#: Every tool only reads: nothing writes user data, so hosts may auto-approve them.
READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
#: Local maintenance: touches the overlay file under ``~/.aninest``, never the network.
WRITE_LOCAL = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

#: Same, but the result depends on outside systems (remote board, local browser service).
READ_ONLY_OPEN = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=True,
)

#: The tool set this server promises. Kept next to the registration so CI, the
#: contract test and the docs can all assert against one list instead of three
#: hand-maintained copies that drift on every added tool.
EXPECTED_TOOLS: tuple[str, ...] = (
    "art_search",
    "character_lookup",
    "portrait_identify",
    "arena_lookup",
    "memory_search",
    "memory_stats",
    "service_health",
    "character_match",
    "character_update",
    "character_correct",
)

INSTRUCTIONS = """\
AniNest tool server. Ten capabilities:
- art_search: turn a Chinese illustration request into booru tags, then return image links.
- character_lookup: map a character name or nickname ("布丁", "克总") to its arena id.
- arena_lookup: look up arena defence teams for a lineup — names or ids, with optional
  exclude/replace so "查不到就换个角色再查" is one call, not a reimplementation.
- portrait_identify: name the characters in cropped portrait images (needs an avatar pack).
- memory_search / memory_stats: read-only retrieval over the assistant's local memory store.
- service_health: report which local services of the stack are currently reachable.
- character_match: rank characters by name similarity (for names a model translated).
- character_update / character_correct: keep the character table current — add a
  Japanese-first character, or fix a wrong match by teaching an alias.

Call service_health first when another tool fails, so a down service is not
mistaken for bad input. The first seven tools are read-only. The last three write
only ``ANINEST_PCR_OVERLAY`` (default ``~/.aninest/pcr_overlay.json``); they never
touch the packaged table, the memory database or the network.
"""

mcp = FastMCP("aninest-mcp", instructions=INSTRUCTIONS)
# The low-level server reports the MCP SDK's version unless told otherwise; report ours.
mcp._mcp_server.version = VERSION


def _dump(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.tool(title="Illustration search", annotations=READ_ONLY_OPEN)
async def art_search(
    query: str,
    count: int = 1,
    size: str = "compressed",
    orientation: str | None = None,
    extra_tags: list[str] | None = None,
    negative: list[str] | None = None,
) -> str:
    """Search an illustration for a Chinese or English request.

    Args:
        query: free-form request, e.g. "初音未来 泳装 竖图"; tags/count/orientation are parsed.
        count: number of images, 1-10.
        size: "compressed" for a smaller preview, "original" for the full-size file.
        orientation: optional "landscape", "portrait" or "square" filter.
        extra_tags: additional canonical booru tags to include.
        negative: tags to exclude, sent to the board as "-tag".
    """
    return _dump(
        await art.search_art(
            query,
            count=count,
            size=size,
            orientation=orientation,
            extra_tags=extra_tags,
            negative=negative,
        )
    )


@mcp.tool(title="Character lookup", annotations=READ_ONLY)
def character_lookup(query: str, limit: int = 5) -> str:
    """Map a character name, nickname, four-digit uid or six-digit id to an arena id.

    Args:
        query: what the player said — "布丁", "克总", "猫拳", "1001", "100101".
        limit: how many candidates to return, 1-10.
    """
    index = pcr.index()
    parsed = index.parse_text(query, limit=max(1, limit))
    matches = []
    for slot, char_id in enumerate(parsed.ids, start=1):
        character = index.character(char_id)
        if character is None:
            continue
        item = character.as_dict()
        item["slot"] = slot
        matches.append(item)

    payload: dict[str, Any] = {
        "query": query,
        "matches": matches,
        "unresolved": parsed.unknown,
        "total_characters": len(index),
    }
    if not matches:
        payload["suggestions"] = [hit.as_dict() for hit in index.suggest(query, 3)]
    return _dump(payload)


@mcp.tool(title="Portrait identification", annotations=READ_ONLY)
def portrait_identify(images: list[str], top_k: int = 3, min_score: float = 0.55) -> str:
    """Identify which characters are in cropped portrait images.

    Args:
        images: one entry per portrait — a file path, raw bytes as base64, or a data URI.
        top_k: candidates per portrait, 1-10.
        min_score: similarity floor below which the portrait counts as unknown, 0-1.
    """
    try:
        payload = portrait.identify(images, top_k=top_k, min_score=min_score)
    except portrait.VisionUnavailable as exc:
        raise ToolError(str(exc)) from exc
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    for result in payload["results"]:
        for candidate in result["candidates"]:
            candidate["name"] = pcr.index().name_of(candidate["id"])
        if result["best"]:
            result["best"]["name"] = pcr.index().name_of(result["best"]["id"])
    return _dump(payload)


@mcp.tool(title="Arena lineup lookup", annotations=READ_ONLY_OPEN)
async def arena_lookup(
    defense: list[str] | None = None,
    def_ids: list[int] | None = None,
    region: int = 1,
    limit: int = 3,
    exclude: list[str] | None = None,
    replace: list[str] | None = None,
) -> str:
    """Look up defence teams for a lineup via the local arena browser service.

    Args:
        defense: the lineup by name — "布丁", "克总", "真琴" … (names, aliases or ids).
        def_ids: the same thing as six-digit ids, if you already have them.
        region: arena region id, 1 = mainland, 2 = overseas, 0 = no filtering.
        limit: how many teams to summarise, 1-6 (display cap, not a game rule).
        exclude: names to drop before searching ("先排除一个再查").
        replace: in-place swaps such as ["宫子->真琴"]; positions are preserved.
    """
    return _dump(
        await arena.arena_lookup(
            defense if defense else def_ids,
            region=region,
            limit=limit,
            exclude=exclude,
            replace=replace,
        )
    )


@mcp.tool(title="Memory search", annotations=READ_ONLY)
def memory_search(query: str, limit: int = 5, scope: str = "all") -> str:
    """Search the assistant's local memory store (read-only).

    Args:
        query: keywords or a sentence to look for.
        limit: maximum hits, 1-20.
        scope: "all", "session" or "global".
    """
    if scope not in ("all", "session", "global"):
        raise ToolError("scope must be all, session or global")
    try:
        return _dump(memory.search_memories(query, limit=limit, scope=scope))
    except FileNotFoundError as exc:
        raise ToolError(str(exc)) from exc
    except ValueError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(title="Memory store stats", annotations=READ_ONLY)
def memory_stats() -> str:
    """Report row counts and database size of the local memory store."""
    try:
        return _dump(memory.memory_stats())
    except FileNotFoundError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(title="Service health", annotations=READ_ONLY)
def service_health() -> str:
    """Probe the local services of the assistant stack and report their status."""
    return _dump(health.service_health())


@mcp.tool(title="Character name match", annotations=READ_ONLY)
def character_match(query: str, top_k: int = 5, threshold: float = 0.45) -> str:
    """Rank characters by how close their names are to a query.

    Use this when a lookup fails because the name is not in the table: the score
    and ``matched_on`` say whether the candidate is trustworthy, so the host can
    ask the user instead of guessing.

    Args:
        query: a name in any form, e.g. "宫紫", "ミヤコ", "miyako".
        top_k: how many candidates to return, 1-20.
        threshold: minimum score, 0-1; below it nothing is returned.
    """
    try:
        return _dump(pcr.match_names(query, top_k=top_k, threshold=threshold))
    except ToolError:
        raise
    except Exception as exc:  # noqa: BLE001 - surfaced to the model as text
        raise ToolError(str(exc)) from exc


@mcp.tool(title="Character update", annotations=WRITE_LOCAL)
def character_update(
    char_id: int,
    name: str | None = None,
    aliases: list[str] | None = None,
    jp: str | None = None,
    servers: list[str] | None = None,
    remove_aliases: list[str] | None = None,
) -> str:
    """Add a character or extend its aliases in the local overlay file.

    New characters are usually published in Japan first and arrive with a
    Japanese name before any Chinese alias exists; pass ``jp`` so lookups by the
    Japanese name work immediately. The packaged table is never modified.

    Args:
        char_id: six-digit arena id, e.g. 100701.
        name: Chinese name; required when creating a character that is not known.
        aliases: extra names to accept, e.g. ["布丁新皮", "miyako"].
        jp: Japanese name, e.g. "ミヤコ".
        servers: servers the character exists on, e.g. ["jp", "cn"].
        remove_aliases: aliases to drop (a wrong alias is worse than a missing one).
    """
    try:
        return _dump(
            pcr.update_character(
                char_id,
                name=name,
                aliases=aliases,
                jp=jp,
                servers=servers,
                remove_aliases=remove_aliases,
            )
        )
    except ToolError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ToolError(str(exc)) from exc


@mcp.tool(title="Character name correction", annotations=WRITE_LOCAL)
def character_correct(term: str, char_id: int | str, note: str = "") -> str:
    """Teach the table that ``term`` refers to a character.

    This is the manual fix for a wrong match: the term is stored as an alias of
    the chosen character and the correction is logged with a timestamp.

    Args:
        term: what the user actually typed, e.g. "宫紫".
        char_id: the character it should resolve to (id or any known name).
        note: optional free text kept with the correction.
    """
    try:
        return _dump(pcr.record_correction(term, char_id, note=note))
    except ToolError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ToolError(str(exc)) from exc


@mcp.resource("aninest://memory/stats")
def memory_stats_resource() -> str:
    """Memory store footprint, exposed as an MCP resource."""
    try:
        return _dump(memory.memory_stats())
    except FileNotFoundError as exc:
        return _dump({"error": str(exc)})


@mcp.prompt()
def find_illustration(request: str) -> str:
    """Prompt template that asks the host model to search an illustration."""
    return (
        "Use the art_search tool for this request, then describe the returned image "
        f"briefly and give its link:\n\n{request}"
    )


def main() -> None:
    transport = SETTINGS.transport
    if transport == "streamable-http":
        mcp.settings.host = SETTINGS.host
        mcp.settings.port = SETTINGS.port
        mcp.run(transport="streamable-http")
    elif transport == "sse":
        mcp.settings.host = SETTINGS.host
        mcp.settings.port = SETTINGS.port
        mcp.run(transport="sse")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
