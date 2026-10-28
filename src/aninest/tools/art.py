"""Art search tool: Chinese request -> tags -> booru search -> image links."""

from __future__ import annotations

import httpx
from mcp.server.fastmcp.exceptions import ToolError

from ..config import SETTINGS
from ..tagging import build_query

#: Boards disagree on how they spell a rating: Gelbooru-style APIs use "s"/"q"/"e",
#: others return "safe"/"questionable"/"explicit". Normalise before filtering.
RATING_ALIASES = {
    "s": "safe",
    "safe": "safe",
    "g": "safe",
    "general": "safe",
    "q": "questionable",
    "questionable": "questionable",
    "e": "explicit",
    "explicit": "explicit",
}


def normalise_rating(raw: object) -> str:
    """Map a board-specific rating to ``safe`` / ``questionable`` / ``explicit``."""
    return RATING_ALIASES.get(str(raw or "safe").strip().lower(), "safe")


def _pick_url(post: dict, size: str) -> str:
    if size == "original":
        return post.get("file_url") or post.get("sample_url") or post.get("preview_url") or ""
    return post.get("sample_url") or post.get("preview_url") or post.get("file_url") or ""


def _orientation_of(width: int, height: int) -> str:
    if width > height * 1.15:
        return "landscape"
    if height > width * 1.15:
        return "portrait"
    return "square"


def shape_results(posts: list[dict], size: str, orientation: str | None, count: int) -> list[dict]:
    """Filter and normalise raw booru posts. Pure function, unit-testable."""
    picked: list[dict] = []
    for post in posts:
        width = int(post.get("width") or 0)
        height = int(post.get("height") or 0)
        if normalise_rating(post.get("rating")) != "safe":
            continue
        if orientation and _orientation_of(width, height) != orientation:
            continue
        url = _pick_url(post, size)
        if not url:
            continue
        picked.append(
            {
                "id": post.get("id"),
                "page_url": f"https://safebooru.org/index.php?page=post&s=view&id={post.get('id')}",
                "image_url": url,
                "width": width,
                "height": height,
                "rating": normalise_rating(post.get("rating")),
                "tags": (post.get("tags") or "")[:400],
            }
        )
        if len(picked) >= count:
            break
    return picked


async def search_art(
    query: str,
    count: int = 1,
    size: str = "compressed",
    orientation: str | None = None,
    extra_tags: list[str] | None = None,
    negative: list[str] | None = None,
) -> dict:
    """Search one image for a Chinese/English request and return links.

    Args:
        query: free-form request, e.g. "初音未来 泳装 竖图".
        count: how many images to return (1-10).
        size: "compressed" (sample/preview) or "original" (full size).
        orientation: optional landscape / portrait / square filter.
        extra_tags: extra canonical booru tags to include.
        negative: tags to exclude (sent as ``-tag``).
    """
    try:
        parsed = build_query(query, extra_tags=extra_tags, negative=negative)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    limit = max(1, min(10, int(count)))
    size = parsed.size or size
    orientation = parsed.orientation or orientation
    if size not in ("compressed", "original"):
        raise ToolError(f"unsupported size: {size}")
    if orientation not in (None, "landscape", "portrait", "square"):
        raise ToolError(f"unsupported orientation: {orientation}")
    if not parsed.tags:
        raise ToolError("no usable tag was produced from the request")

    tag_query = parsed.tag_query()
    attempts = build_attempts(parsed.tags, parsed.negative, orientation)
    errors: list[str] = []

    async with httpx.AsyncClient(timeout=SETTINGS.http_timeout) as client:
        for index, (tags, wanted_orientation) in enumerate(attempts):
            try:
                posts = await fetch_posts(client, tags, limit)
            except ToolError as exc:
                errors.append(str(exc))
                continue
            results = shape_results(posts, size, wanted_orientation, limit)
            if results:
                return {
                    "query": query,
                    "tags": parsed.tags,
                    "tags_used": tags,
                    "negative": parsed.negative,
                    "unknown_words": parsed.unknown,
                    "size": size,
                    "orientation": wanted_orientation,
                    "relaxed": index > 0,
                    "attempt": index + 1,
                    "count": len(results),
                    "results": results,
                }

    raise ToolError(
        "no image matched after "
        f"{len(attempts)} attempts (tags: {tag_query})"
        + (f"; last error: {errors[-1]}" if errors else "")
    )


def build_attempts(
    tags: list[str], negative: list[str], orientation: str | None
) -> list[tuple[str, str | None]]:
    """Build a relaxation ladder: exact request first, then looser variants.

    A board can simply have nothing for ``a b c`` while having plenty for
    ``a``; asking once and giving up makes the tool look broken. Each rung is
    one extra HTTP call and only runs when the previous rung came back empty.
    """
    suffix = [f"-{tag}" for tag in negative]

    def render(include: list[str]) -> str:
        return " ".join(include + suffix)

    attempts: list[tuple[str, str | None]] = [(render(tags), orientation)]
    if orientation:
        attempts.append((render(tags), None))
    remaining = tags[:-1]
    while remaining:
        attempts.append((render(remaining), None))
        remaining = remaining[:-1]

    unique: list[tuple[str, str | None]] = []
    for attempt in attempts:
        if attempt not in unique:
            unique.append(attempt)
    return unique


async def fetch_posts(client: httpx.AsyncClient, tags: str, limit: int) -> list[dict]:
    """One board request; transport problems surface as ``ToolError``."""
    params = {
        "page": "dapi",
        "s": "post",
        "q": "index",
        "json": "1",
        "limit": str(max(limit * 4, 12)),
        "tags": tags,
    }
    try:
        response = await client.get(
            SETTINGS.booru_url, params=params, headers={"User-Agent": SETTINGS.user_agent}
        )
        response.raise_for_status()
        raw = response.json()
    except httpx.HTTPError as exc:  # network / status problems are reported, never faked
        raise ToolError(f"booru request failed: {type(exc).__name__}: {exc}") from exc
    except ValueError as exc:
        raise ToolError("booru returned a non-JSON body (rate limited?)") from exc
    return raw if isinstance(raw, list) else []
