"""Arena lookup tool: calls the local browser service that has a logged-in session."""

from __future__ import annotations

import httpx
from mcp.server.fastmcp.exceptions import ToolError

from ..config import SETTINGS
from . import pcr


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


def _row_list(node: object, depth: int = 0) -> list[dict]:
    """Find the first list of team records, wherever the service nests it.

    The live service answers `{"ok": true, "data": {"code": 0, "data": {"result": [...]}}}`,
    so the rows sit two levels below the top. Walking down instead of hard-coding the
    path keeps the tool working if a version adds or drops one wrapper.
    """
    if depth > 6:
        return []
    if isinstance(node, list):
        dicts = [item for item in node if isinstance(item, dict)]
        if dicts and any("atk" in item or "def" in item for item in dicts):
            return dicts
        for item in node:
            found = _row_list(item, depth + 1)
            if found:
                return found
        return []
    if isinstance(node, dict):
        for key in ("result", "data", "teams", "list"):
            if key in node:
                found = _row_list(node[key], depth + 1)
                if found:
                    return found
        for value in node.values():
            found = _row_list(value, depth + 1)
            if found:
                return found
    return []


def _unit_ids(units: object) -> list[int]:
    """Character ids out of `[{id, star, equip}, ...]` (or a plain id list)."""
    if not isinstance(units, list):
        return []
    ids: list[int] = []
    for unit in units:
        value = unit.get("id") if isinstance(unit, dict) else unit
        try:
            ids.append(int(value))
        except (TypeError, ValueError):
            continue
    return ids


def _names(ids: list[int]) -> list[str]:
    """Human names for a lineup, so a host can read it aloud without a second call."""
    try:
        from . import pcr

        index = pcr.index()
    except Exception:  # pragma: no cover - names are a convenience, never a failure
        return []
    return [index.name_of(char_id) for char_id in ids]


def summarise(payload: dict, limit: int = 3) -> dict:
    """Flatten the upstream payload into a small, model-friendly structure.

    Field names are the live ones: `def` / `atk` hold unit objects, and the counters are
    `up` / `down` (votes). There is no view counter upstream — don't invent one.
    """
    rows = _row_list(payload)
    summaries = []
    for row in rows[:limit]:
        defense = _unit_ids(row.get("def"))
        attack = _unit_ids(row.get("atk"))
        summaries.append(
            {
                "defense": defense,
                "attack": attack,
                "defense_names": _names(defense),
                "attack_names": _names(attack),
                "upvotes": row.get("up"),
                "downvotes": row.get("down"),
                "updated": row.get("updated"),
                "ref": row.get("id"),
            }
        )
    return {"found": len(rows), "teams": summaries}


async def arena_lookup(
    defense: object = None,
    def_ids: object = None,
    region: int = 1,
    limit: int = 3,
    exclude: object = None,
    replace: object = None,
) -> dict:
    """Look up defence teams for a lineup through the local arena browser service.

    Args:
        defense: the lineup — character names, aliases, four-digit uids or six-digit
            ids, mixed freely ("布丁 克总 真琴", ["宫子", 100301]). Slot order is the
            caller's business; the service only needs the set.
        def_ids: same thing but ids only (kept for callers that already hold ids).
        region: arena region id (1 = mainland, 2 = overseas, 0 = no filtering).
        limit: how many teams to summarise (1-6, a display cap rather than a game rule).
        exclude: names/ids to drop before searching — "先排除一个角色再查".
        replace: swap a character in place, e.g. ["宫子->真琴"] or
            [{"from": "宫子", "to": "真琴"}]; positions are preserved.
    """
    source = defense if defense not in (None, "", []) else def_ids
    if source in (None, "", []):
        raise ToolError("defense is required: pass character names or ids")

    resolved = pcr.resolve_team(source, limit=5)
    ids: list[int] = list(resolved["ids"])
    unresolved: list[dict] = list(resolved["unresolved"])
    applied: list[dict] = []

    if exclude:
        outcome = pcr.apply_exclude(ids, exclude)
        ids = outcome["ids"]
        applied.extend(outcome["applied"])
        unresolved.extend(outcome["unresolved"])

    if replace:
        outcome = pcr.apply_replace(ids, replace)
        ids = outcome["ids"]
        applied.extend(outcome["applied"])
        if outcome["problems"]:
            details = []
            for problem in outcome["problems"]:
                if problem.get("reason") == "unknown":
                    names = ", ".join(
                        hit["name"] for hit in problem.get("suggestions") or []
                    )
                    details.append(
                        f"{problem.get('from') or problem.get('to')} is not a known "
                        f"character (did you mean {names}?)"
                    )
                else:
                    details.append(str(problem.get("detail") or problem.get("reason")))
            raise ToolError("cannot apply replacement: " + "; ".join(details))

    if not ids:
        hint = ""
        if unresolved:
            first = unresolved[0]
            names = ", ".join(hit["name"] for hit in first.get("suggestions") or [])
            hint = f" (nothing matched {first['input']!r}; did you mean {names}?)"
        raise ToolError("no character resolved from the given lineup" + hint)

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
    summary["lineup"] = pcr.describe(ids)
    summary["region"] = int(region)
    if applied:
        summary["applied"] = applied
    if unresolved:
        summary["unresolved"] = unresolved
    return summary
