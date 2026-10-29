"""Arena lookup tool: calls the local browser service that has a logged-in session."""

from __future__ import annotations

import httpx
from mcp.server.fastmcp.exceptions import ToolError

from ..config import SETTINGS


def validate_ids(def_ids: list[int]) -> list[int]:
    """Normalise and validate six-digit character ids. Pure function.

    A defence lineup is five characters, so one to five distinct ids is accepted:
    partial lineups are legitimate (a screenshot may hide a slot, and the reference
    service answers such queries too), but six is not a lineup the game has.
    """
    if not def_ids:
        raise ValueError("def_ids is empty")
    out: list[int] = []
    for raw in def_ids:
        try:
            value = int(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"bad character id: {raw!r}") from exc
        if not 100000 <= value <= 999999:
            raise ValueError(f"character id out of range: {value}")
        if value not in out:
            out.append(value)
    if len(out) > 5:
        raise ValueError(
            f"a defence lineup has 5 characters, got {len(out)} distinct ids"
        )
    return out


def summarise(payload: dict, limit: int = 3) -> dict:
    """Flatten the upstream payload into a small, model-friendly structure."""
    teams = payload.get("result") or payload.get("data") or payload
    if isinstance(teams, dict):
        teams = teams.get("result") or teams.get("data") or []
    if not isinstance(teams, list):
        teams = []
    summaries = []
    for row in teams[:limit]:
        if not isinstance(row, dict):
            continue
        summaries.append(
            {
                "team": row.get("atk") or row.get("def") or row.get("team"),
                "likes": row.get("likes") or row.get("like_num"),
                "views": row.get("views") or row.get("view_num"),
                "updated": row.get("updated") or row.get("modified"),
            }
        )
    return {"found": len(teams), "teams": summaries}


async def arena_lookup(def_ids: list[int], region: int = 1, limit: int = 3) -> dict:
    """Look up defence teams for a lineup through the local arena browser service.

    Args:
        def_ids: 1-5 six-digit character ids that form the defence lineup.
        region: arena region id (1 = main).
        limit: how many teams to summarise (1-6, a display cap rather than a game rule).
    """
    try:
        ids = validate_ids(list(def_ids))
    except ValueError as exc:
        raise ToolError(str(exc)) from exc

    url = SETTINGS.arena_url.rstrip("/") + "/search"
    try:
        async with httpx.AsyncClient(timeout=SETTINGS.http_timeout) as client:
            response = await client.post(url, json={"def": ids, "region": int(region)})
            response.raise_for_status()
            payload = response.json()
    except httpx.ConnectError as exc:
        raise ToolError(
            f"arena browser service is not running at {url} "
            f"(set ANINEST_ARENA_URL to a service that answers POST /search)"
        ) from exc
    except httpx.HTTPError as exc:
        raise ToolError(f"arena request failed: {type(exc).__name__}: {exc}") from exc
    except ValueError as exc:
        raise ToolError("arena service returned a non-JSON body") from exc

    if not payload.get("ok"):
        raise ToolError(f"arena service rejected the request: {payload.get('error') or payload}")

    data = payload.get("data") or {}
    summary = summarise(data, max(1, min(6, int(limit))))
    summary["def_ids"] = ids
    summary["region"] = int(region)
    return summary
