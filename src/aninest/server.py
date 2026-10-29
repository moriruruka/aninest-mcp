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
from .tools import arena, art, health, memory
from .version import VERSION

#: Every tool only reads: nothing writes user data, so hosts may auto-approve them.
READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
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

INSTRUCTIONS = """\
AniNest tool server. Five capabilities:
- art_search: turn a Chinese illustration request into booru tags, then return image links.
- arena_lookup: look up arena defence teams for a lineup through the local browser service.
- memory_search / memory_stats: read-only retrieval over the assistant's local memory store.
- service_health: report which local services of the stack are currently reachable.

Call service_health first when another tool fails, so a down service is not
mistaken for bad input. All tools are read-only; nothing here writes user data.
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


@mcp.tool(title="Arena lineup lookup", annotations=READ_ONLY_OPEN)
async def arena_lookup(def_ids: list[int], region: int = 1, limit: int = 3) -> str:
    """Look up defence teams for a lineup via the local arena browser service.

    Args:
        def_ids: 1-5 six-digit character ids forming the defence lineup.
        region: arena region id, 1 = main.
        limit: how many teams to summarise, 1-6 (display cap, not a game rule).
    """
    return _dump(await arena.arena_lookup(def_ids, region=region, limit=limit))


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
