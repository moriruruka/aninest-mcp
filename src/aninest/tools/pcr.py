"""Character name / alias → six-digit arena id.

Players know names ("布丁", "克总", "真琴"), the arena API wants six-digit ids.
This module ports the resolution rules the assistant already uses:

* ids are accepted as ``100101`` (six digits) or ``1001`` (four-digit uid);
* names are matched exactly, then by prefix, then by substring;
* an alias map lets a whole run of names be split without separators
  ("布丁克总" → 宫子 + 克莉丝提娜), but only when the split yields ≥ 2 characters;
* unknown words get suggestions scored by edit distance.

The table itself lives in ``aninest/data/pcr_chars.json`` and carries facts only
(ids, names, aliases, server flags) — see ``scripts/port_characters.py``.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

from mcp.server.fastmcp.exceptions import ToolError

from ..config import SETTINGS

_SPLIT_RE = re.compile(r"[\s\u3000,，、+＋/|｜;；]+")
_SPACE_RE = re.compile(r"[\s\u3000]+")
_ID_RE = re.compile(r"^(?:id)?(\d{3,6})$", re.IGNORECASE)
_ARROW_RE = re.compile(r"\s*(?:->|→|=>|换成|换成|替换为|改成了?|改为)\s*")


def normalize(text: Any) -> str:
    """Full-width → half-width, drop blanks, lowercase."""

    if text is None:
        return ""
    value = unicodedata.normalize("NFKC", str(text))
    value = _SPACE_RE.sub("", value)
    return value.casefold()


def edit_distance(left: str, right: str) -> int:
    """Levenshtein distance — short names only, pure Python is fine."""

    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)
    if len(left) > len(right):
        left, right = right, left
    previous = list(range(len(left) + 1))
    for row, right_char in enumerate(right, 1):
        current = [row]
        for col, left_char in enumerate(left, 1):
            cost = 0 if left_char == right_char else 1
            current.append(
                min(previous[col] + 1, current[col - 1] + 1, previous[col - 1] + cost)
            )
        previous = current
    return previous[-1]


def similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    longest = max(len(left), len(right))
    return max(0.0, 1.0 - edit_distance(left, right) / longest)


@dataclass(slots=True)
class Character:
    id: int
    uid4: int
    name: str
    aliases: list[str] = field(default_factory=list)
    jp: str = ""
    servers: list[str] = field(default_factory=list)

    @property
    def all_names(self) -> list[str]:
        # The Japanese name is included on purpose: new characters ship in Japan
        # first, so a host may be holding "ミヤコ" long before a Chinese alias
        # exists for it.
        return [self.name, *self.aliases, *([self.jp] if self.jp else [])]

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "uid4": self.uid4,
            "name": self.name,
            "aliases": self.aliases,
            "jp": self.jp,
            "servers": self.servers,
        }


@dataclass(slots=True)
class Hit:
    character: Character
    score: float
    matched: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.character.id,
            "name": self.character.name,
            "matched": self.matched,
            "score": round(self.score, 2),
        }


@dataclass(slots=True)
class ParseResult:
    ids: list[int] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)
    tokens: list[str] = field(default_factory=list)
    truncated: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "ids": self.ids,
            "unknown": self.unknown,
            "tokens": self.tokens,
            "truncated": self.truncated,
        }


class CharacterIndex:
    """Id / name / alias index over the packaged table."""

    def __init__(self, payload: Mapping[str, Any] | Iterable[Mapping[str, Any]]):
        rows = payload.get("characters") if isinstance(payload, Mapping) else payload
        rows = list(rows or [])
        self.characters: list[Character] = []
        self.by_id: dict[int, Character] = {}
        self.by_uid4: dict[int, Character] = {}
        self._alias_map: dict[str, list[int]] = {}
        self._max_alias_len = 1

        for row in rows:
            try:
                char_id = int(row["id"])
            except (KeyError, TypeError, ValueError):
                continue
            name = str(row.get("name") or "").strip()
            if not name:
                continue
            uid4 = int(row.get("uid4") or char_id // 100)
            aliases = [str(a).strip() for a in row.get("aliases") or [] if str(a).strip()]
            character = Character(
                id=char_id,
                uid4=uid4,
                name=name,
                aliases=[a for a in aliases if a != name],
                jp=str(row.get("jp") or ""),
                servers=[s for s in row.get("servers") or [] if isinstance(s, str)],
            )
            self.characters.append(character)
            self.by_id[char_id] = character
            # Keep the base form for a uid4: variant ids share it, and the base is
            # the one players name (100111 -> 100101, 日和).
            self.by_uid4.setdefault(uid4, character)
            for alias in character.all_names:
                key = normalize(alias)
                if not key:
                    continue
                self._alias_map.setdefault(key, []).append(char_id)
                self._max_alias_len = max(self._max_alias_len, len(key))

        self.characters.sort(key=lambda item: item.id)
        for key, ids in self._alias_map.items():
            self._alias_map[key] = sorted(set(ids))

    def __len__(self) -> int:
        return len(self.characters)

    # -- lookups ---------------------------------------------------------
    def character(self, value: int | str) -> Character | None:
        try:
            number = int(value)
        except (TypeError, ValueError):
            return None
        found = self.by_id.get(number) or self.by_uid4.get(number)
        if found is not None:
            return found
        # A variant avatar id (100111 六星/庆典) resolves to its base character.
        if 100000 <= number <= 999999:
            return self.by_uid4.get(number // 100)
        return None

    def canonical_id(self, value: int | str) -> int:
        character = self.character(value)
        if character is not None:
            return character.id
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def name_of(self, value: int | str) -> str:
        character = self.character(value)
        return character.name if character else str(value)

    def _id_from_token(self, token: str) -> int | None:
        value = unicodedata.normalize("NFKC", token).strip()
        match = _ID_RE.fullmatch(value)
        if not match:
            return None
        digits = match.group(1)
        number = int(digits)
        if len(digits) == 6:
            character = self.by_id.get(number)
            if character is not None:
                return character.id
            character = self.by_uid4.get(number // 100)
            return character.id if character is not None else None
        character = self.by_uid4.get(number)
        return character.id if character is not None else None

    def resolve_token(self, token: str) -> int | None:
        raw = str(token or "").strip()
        if not raw:
            return None
        by_id = self._id_from_token(raw)
        if by_id is not None:
            return by_id
        key = normalize(raw)
        if not key:
            return None
        exact = self._alias_map.get(key)
        if exact:
            return exact[0]
        if len(key) >= 2:
            prefix_hits: list[tuple[int, int]] = []
            substring_hits: list[tuple[int, int]] = []
            for alias, ids in self._alias_map.items():
                if len(alias) < 2:
                    continue
                if alias.startswith(key):
                    prefix_hits.append((len(alias) - len(key), ids[0]))
                elif key in alias:
                    substring_hits.append((len(alias) - len(key), ids[0]))
            if prefix_hits:
                prefix_hits.sort(key=lambda item: (item[0], item[1]))
                return prefix_hits[0][1]
            if substring_hits:
                substring_hits.sort(key=lambda item: (item[0], item[1]))
                return substring_hits[0][1]
        return None

    def _conjunction_split(self, token: str) -> list[int]:
        """Resolve "布丁和克总" — split on 和/与/及 only if every part is a known name.

        A blanket split would break names that contain those characters (日和), so the
        split is attempted only after the whole token failed to resolve.
        """

        parts = [part for part in _CONJ_RE.split(normalize(token)) if part]
        if len(parts) < 2:
            return []
        ids: list[int] = []
        for part in parts:
            char_id = self.resolve_token(part)
            if char_id is None:
                return []
            ids.append(char_id)
        return ids

    def segment_token(self, token: str) -> list[int]:
        """Split "布丁克总" into known aliases when a full split exists."""

        text = normalize(token)
        if len(text) < 4:
            return []
        memo: dict[int, list[int] | None] = {}

        def walk(pos: int) -> list[int] | None:
            if pos == len(text):
                return []
            if pos in memo:
                return memo[pos]
            upper = min(len(text), pos + self._max_alias_len)
            for end in range(upper, pos + 1, -1):
                piece = text[pos:end]
                if len(piece) < 2:
                    continue
                ids = self._alias_map.get(piece)
                if not ids:
                    continue
                rest = walk(end)
                if rest is not None:
                    result = [ids[0], *rest]
                    memo[pos] = result
                    return result
            memo[pos] = None
            return None

        result = walk(0)
        return result if result and len(result) >= 2 else []

    def parse_text(self, text: str, limit: int = 5) -> ParseResult:
        tokens = [part for part in _SPLIT_RE.split(str(text or "").strip()) if part]
        ids: list[int] = []
        unknown: list[str] = []
        for token in tokens:
            char_id = self.resolve_token(token)
            if char_id is None:
                segmented = self.segment_token(token)
                if segmented:
                    ids.extend(segmented)
                    continue
                joined = self._conjunction_split(token)
                if joined:
                    ids.extend(joined)
                else:
                    unknown.append(token)
            else:
                ids.append(char_id)

        deduped: list[int] = []
        seen: set[int] = set()
        for char_id in ids:
            if char_id in seen:
                continue
            seen.add(char_id)
            deduped.append(char_id)
        truncated = len(deduped) > max(1, limit)
        if truncated:
            deduped = deduped[: max(1, limit)]
        return ParseResult(ids=deduped, unknown=unknown, tokens=tokens, truncated=truncated)

    def filter_ids(self, ids: Iterable[int], region: int = 0) -> list[int]:
        """region 1 = mainland (cn), 2 = overseas (us), anything else = keep all."""

        if region not in (1, 2):
            return [self.canonical_id(value) for value in ids]
        wanted = "cn" if region == 1 else "us"
        filtered: list[int] = []
        for value in ids:
            character = self.character(value)
            if character is None:
                continue
            if wanted in character.servers or not character.servers:
                filtered.append(character.id)
        return filtered

    # -- search / suggest ------------------------------------------------
    def _score_keyword(self, key: str, alias: str) -> float:
        if not key or not alias:
            return 0.0
        if alias == key:
            return 100.0
        if alias.startswith(key):
            return 88.0 - min(12.0, len(alias) - len(key))
        if key in alias:
            return 74.0 - min(10.0, len(alias) - len(key))
        if len(key) >= 2 and alias in key:
            return 62.0 - min(8.0, len(key) - len(alias))
        ratio = similarity(key, alias)
        if ratio >= 0.6:
            return ratio * 58.0
        return 0.0

    def search(self, keyword: str, limit: int = 5) -> list[Hit]:
        key = normalize(keyword)
        if not key:
            return []
        direct = self._id_from_token(str(keyword))
        if direct is not None:
            return [Hit(character=self.by_id[direct], score=100.0, matched=str(direct))]
        hits: list[Hit] = []
        for character in self.characters:
            best_score = 0.0
            best_alias = character.name
            for alias in character.all_names:
                score = self._score_keyword(key, normalize(alias))
                if score > best_score:
                    best_score = score
                    best_alias = alias
            if best_score > 0:
                hits.append(Hit(character=character, score=best_score, matched=best_alias))
        hits.sort(key=lambda item: (-item.score, item.character.id))
        return hits[: max(1, limit)]

    def suggest(self, token: str, limit: int = 3) -> list[Hit]:
        key = normalize(token)
        if not key:
            return []
        direct = self._id_from_token(str(token))
        if direct is not None:
            return [Hit(character=self.by_id[direct], score=100.0, matched=str(direct))]
        hits: list[Hit] = []
        for character in self.characters:
            best_score = 0.0
            best_alias = character.name
            for alias in character.all_names:
                alias_key = normalize(alias)
                if not alias_key:
                    continue
                if alias_key.startswith(key):
                    score = 90.0 - min(20.0, len(alias_key) - len(key))
                elif key in alias_key:
                    score = 70.0 - min(15.0, len(alias_key) - len(key))
                else:
                    score = similarity(key, alias_key) * 65.0
                if score > best_score:
                    best_score = score
                    best_alias = alias
            if best_score > 0:
                hits.append(Hit(character=character, score=best_score, matched=best_alias))
        hits.sort(key=lambda item: (-item.score, item.character.id))
        return hits[: max(1, limit)]


@lru_cache(maxsize=1)
def index() -> CharacterIndex:
    """Load the packaged table once per process, with the local overlay applied."""

    text = resources.files("aninest.data").joinpath("pcr_chars.json").read_text("utf-8")
    rows = (json.loads(text) or {}).get("characters") or []
    return CharacterIndex({"characters": merge_overlay(rows, load_overlay())})


def reset_index() -> None:
    """Drop the cached index (tests / hot reload)."""

    index.cache_clear()


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [item for item in value if str(item).strip()]
    return [value]


_CONJ_RE = re.compile(r"[和与及]")


def resolve_team(items: Any, limit: int = 5) -> dict[str, Any]:
    """Resolve a mixture of names, aliases and ids into canonical ids.

    Returns ``ids`` plus one entry per unknown token so a host can ask a
    follow-up question instead of failing with a bare error.
    """

    idx = index()
    tokens: list[str] = []
    for item in _as_list(items):
        if isinstance(item, str) and _SPLIT_RE.search(item):
            tokens.extend(part for part in _SPLIT_RE.split(item) if part)
        else:
            tokens.append(str(item))
    result = idx.parse_text(" ".join(tokens), limit=limit)
    resolved = [
        {"input": token, "id": char_id, "name": idx.name_of(char_id)}
        for token in result.tokens
        for char_id in [idx.resolve_token(token)]
        if char_id is not None
    ]
    unresolved = []
    for token in result.unknown:
        unresolved.append(
            {
                "input": token,
                "suggestions": [hit.as_dict() for hit in idx.suggest(token, limit=3)],
            }
        )
    return {
        "ids": result.ids,
        "resolved": resolved,
        "unresolved": unresolved,
        "truncated": result.truncated,
    }


def apply_exclude(ids: Sequence[int], exclude: Any) -> dict[str, Any]:
    """Remove characters by name or id; unknown names are reported back."""

    idx = index()
    resolved = resolve_team(exclude, limit=5) if exclude else {"ids": [], "unresolved": []}
    drop = {idx.canonical_id(value) for value in resolved["ids"]}
    kept = [int(value) for value in ids if int(value) not in drop]
    applied = [
        {"action": "exclude", "id": char_id, "name": idx.name_of(char_id)}
        for char_id in sorted(drop)
    ]
    return {"ids": kept, "applied": applied, "unresolved": list(resolved["unresolved"])}


def apply_replace(ids: Sequence[int], replace: Any) -> dict[str, Any]:
    """Replace characters in place.

    ``replace`` accepts ``["宫子->真琴"]``, ``[{"from": "宫子", "to": "真琴"}]``
    or ``{ "宫子": "真琴" }``. Position matters: a replacement keeps the slot,
    which is what "把 3 号位换成 X" means in an arena lineup.
    """

    idx = index()
    pairs: list[tuple[str, str]] = []
    if isinstance(replace, Mapping):
        pairs = [(str(k), str(v)) for k, v in replace.items()]
    else:
        for item in _as_list(replace):
            if isinstance(item, Mapping):
                pairs.append((str(item.get("from") or ""), str(item.get("to") or "")))
                continue
            parts = _ARROW_RE.split(str(item), maxsplit=1)
            if len(parts) == 2:
                pairs.append((parts[0], parts[1]))

    current = [int(value) for value in ids]
    applied: list[dict[str, Any]] = []
    problems: list[dict[str, Any]] = []
    for old_raw, new_raw in pairs:
        old_id = idx.resolve_token(old_raw)
        new_id = idx.resolve_token(new_raw)
        if old_id is None:
            problems.append(
                {
                    "from": old_raw,
                    "reason": "unknown",
                    "suggestions": [hit.as_dict() for hit in idx.suggest(old_raw, 3)],
                }
            )
            continue
        if new_id is None:
            problems.append(
                {
                    "to": new_raw,
                    "reason": "unknown",
                    "suggestions": [hit.as_dict() for hit in idx.suggest(new_raw, 3)],
                }
            )
            continue
        if old_id == new_id:
            problems.append(
                {
                    "from": old_raw,
                    "to": new_raw,
                    "reason": "same_character",
                    "detail": "换成了同一个角色",
                }
            )
            continue
        if old_id not in current:
            problems.append(
                {
                    "from": old_raw,
                    "reason": "not_in_team",
                    "detail": f"{idx.name_of(old_id)} 不在当前阵容里",
                }
            )
            continue
        if new_id in current:
            slot = current.index(new_id) + 1
            problems.append(
                {
                    "to": new_raw,
                    "reason": "duplicate",
                    "detail": f"{idx.name_of(new_id)} 已经在 {slot} 号位",
                }
            )
            continue
        slot = current.index(old_id)
        current[slot] = new_id
        applied.append(
            {
                "action": "replace",
                "slot": slot + 1,
                "from": idx.name_of(old_id),
                "to": idx.name_of(new_id),
            }
        )
    return {"ids": current, "applied": applied, "problems": problems}


def describe(ids: Sequence[int]) -> list[dict[str, Any]]:
    """Names for a list of ids, in slot order (1 号位 … 5 号位)."""

    idx = index()
    return [
        {"slot": number, "id": int(char_id), "name": idx.name_of(char_id)}
        for number, char_id in enumerate(ids, 1)
    ]


# -- local overlay: aliases you added, names you corrected --------------------
#
# The packaged table is read-only: it ships with the release and an upgrade
# replaces it. Anything the user fixes or adds lives in a separate JSON file so
# it survives upgrades and so a wrong correction is easy to spot (and delete).

OVERLAY_VERSION = 1


def overlay_path() -> Path:
    """Where local overrides are stored (``ANINEST_PCR_OVERLAY``)."""

    return Path(SETTINGS.pcr_overlay)


def _empty_overlay() -> dict[str, Any]:
    return {"version": OVERLAY_VERSION, "characters": {}, "corrections": []}


def load_overlay(path: str | Path | None = None) -> dict[str, Any]:
    """Read the overlay, tolerating a missing or half-written file."""

    target = Path(path) if path is not None else overlay_path()
    if not target.exists():
        return _empty_overlay()
    try:
        data = json.loads(target.read_text("utf-8"))
    except (OSError, ValueError):
        return _empty_overlay()
    if not isinstance(data, dict):
        return _empty_overlay()
    characters = data.get("characters")
    corrections = data.get("corrections")
    return {
        "version": int(data.get("version") or OVERLAY_VERSION),
        "characters": characters if isinstance(characters, dict) else {},
        "corrections": corrections if isinstance(corrections, list) else [],
    }


def save_overlay(data: Mapping[str, Any], path: str | Path | None = None) -> Path:
    """Write the overlay atomically: a crash never leaves a truncated file."""

    target = Path(path) if path is not None else overlay_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".tmp")
    payload = json.dumps(dict(data), ensure_ascii=False, indent=2, sort_keys=True)
    temp.write_text(payload + "\n", "utf-8")
    temp.replace(target)
    return target


def merge_overlay(
    rows: Iterable[Mapping[str, Any]], overlay: Mapping[str, Any] | None = None
) -> list[dict[str, Any]]:
    """Apply the overlay to the packaged rows (aliases union, names override)."""

    data = overlay if overlay is not None else load_overlay()
    overrides: Mapping[str, Any] = data.get("characters") or {}
    merged: dict[int, dict[str, Any]] = {}
    order: list[int] = []

    for row in rows:
        try:
            char_id = int(row.get("id"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        merged[char_id] = dict(row)
        merged[char_id]["aliases"] = [str(a) for a in row.get("aliases") or []]
        order.append(char_id)

    for key, patch in overrides.items():
        if not isinstance(patch, Mapping):
            continue
        try:
            char_id = int(patch.get("id") or key)
        except (TypeError, ValueError):
            continue
        base = merged.get(char_id)
        if base is None:
            base = {"id": char_id, "aliases": []}
            order.append(char_id)
            merged[char_id] = base
        for field_name in ("name", "jp", "uid4"):
            value = patch.get(field_name)
            if value:
                base[field_name] = value
        if patch.get("servers"):
            base["servers"] = [str(item) for item in patch["servers"]]
        aliases = [str(a) for a in base.get("aliases") or []]
        for alias in patch.get("aliases") or []:
            text = str(alias).strip()
            if text and text not in aliases:
                aliases.append(text)
        base["aliases"] = aliases

    return [merged[char_id] for char_id in order]


def update_character(
    char_id: int | str,
    name: str | None = None,
    aliases: Any = None,
    jp: str | None = None,
    servers: Any = None,
    remove_aliases: Any = None,
    *,
    path: str | Path | None = None,
) -> dict[str, Any]:
    """Create or extend one character in the overlay.

    ``id`` must be a six-digit arena id; ``uid4`` is derived from it. Nothing is
    fetched from the network — a new Japanese-first character is entered by hand
    (or by a host that scraped it), which keeps the tool deterministic.
    """

    try:
        number = int(str(char_id).strip())
    except (TypeError, ValueError):
        raise ToolError(f"character id must be a number, got {char_id!r}") from None
    if not 100000 <= number <= 999999:
        raise ToolError(f"character id out of range: {number} (expected six digits)")

    idx = index()
    existing = idx.by_id.get(number)
    if existing is None and not name:
        raise ToolError(
            f"character {number} is not in the table; pass name to create it"
        )

    overlay = load_overlay(path)
    record = dict(overlay["characters"].get(str(number)) or {})
    current_name = str(record.get("name") or (existing.name if existing else "")).strip()
    if name and name.strip():
        current_name = name.strip()
    if not current_name:
        raise ToolError(f"character {number} needs a name")

    merged_aliases = list(record.get("aliases") or [])
    if existing is not None:
        for alias in existing.aliases:
            if alias not in merged_aliases:
                merged_aliases.append(alias)
    added: list[str] = []
    for alias in _as_list(aliases):
        text = str(alias).strip()
        if text and text not in merged_aliases and text != current_name:
            merged_aliases.append(text)
            added.append(text)

    removed: list[str] = []
    for alias in _as_list(remove_aliases):
        text = str(alias).strip()
        if text in merged_aliases:
            merged_aliases.remove(text)
            removed.append(text)

    character_jp = (jp or record.get("jp") or (existing.jp if existing else "")).strip()
    character_servers = [str(item) for item in _as_list(servers)] or list(
        record.get("servers")
        or (existing.servers if existing else [])
        or ["cn", "jp"]
    )

    record.update(
        {
            "id": number,
            "uid4": int(record.get("uid4") or number // 100),
            "name": current_name,
            "jp": character_jp,
            "aliases": merged_aliases,
            "servers": character_servers,
        }
    )
    overlay["characters"][str(number)] = record
    saved = save_overlay(overlay, path)
    reset_index()

    return {
        "action": "updated" if existing is not None else "created",
        "character": {
            "id": number,
            "uid4": int(record.get("uid4") or number // 100),
            "name": current_name,
            "jp": character_jp,
            "aliases": merged_aliases,
            "servers": character_servers,
        },
        "added_aliases": added,
        "removed_aliases": removed,
        "overlay": str(saved),
        "characters_in_overlay": len(overlay["characters"]),
    }


def record_correction(
    term: str,
    char_id: int | str,
    note: str = "",
    *,
    path: str | Path | None = None,
) -> dict[str, Any]:
    """Remember "when the user says X, they mean character Y".

    This is the manual escape hatch for a wrong match: the term becomes an alias
    of the chosen character, so the very next lookup resolves it, and the
    correction is logged with a timestamp for the user to audit.
    """

    key = str(term or "").strip()
    if not key:
        raise ToolError("term is required")
    idx = index()
    resolved = idx.resolve_token(str(char_id)) if idx.character(char_id) is None else None
    target = idx.character(char_id) or (idx.character(resolved) if resolved else None)
    if target is None:
        raise ToolError(f"unknown character: {char_id!r}")
    if normalize(key) == normalize(target.name):
        return {
            "action": "noop",
            "reason": "term is already the character name",
            "id": target.id,
            "name": target.name,
        }

    overlay = load_overlay(path)
    record = dict(overlay["characters"].get(str(target.id)) or {})
    merged_aliases = list(record.get("aliases") or [])
    if target.id in idx.by_id:
        for alias in idx.by_id[target.id].aliases:
            if alias not in merged_aliases:
                merged_aliases.append(alias)

    already = any(normalize(alias) == normalize(key) for alias in merged_aliases)
    action = "already_known" if already else "alias_added"
    if not already:
        merged_aliases.append(key)
        record.setdefault("id", target.id)
        record["uid4"] = int(record.get("uid4") or target.uid4)
        record["name"] = str(record.get("name") or target.name)
        record["aliases"] = merged_aliases
        overlay["characters"][str(target.id)] = record
        overlay["corrections"].append(
            {
                "term": key,
                "id": target.id,
                "note": note.strip(),
                "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
        )

    saved = save_overlay(overlay, path)
    reset_index()
    return {
        "action": action,
        "term": key,
        "id": target.id,
        "name": target.name,
        "aliases": merged_aliases,
        "corrections": len(overlay["corrections"]),
        "overlay": str(saved),
    }


def match_names(
    query: str, top_k: int = 5, threshold: float = 0.45
) -> dict[str, Any]:
    """Rank characters by how close their names are to ``query``.

    Exists because a host often hands over a name a language model already
    translated, so it may differ from what the user typed (宫子 / ミヤコ /
    "miyako"). Every candidate carries the score and what matched, so a host can
    decide whether to ask the user instead of guessing.
    """

    raw = str(query or "").strip()
    if not raw:
        raise ToolError("query is required")
    idx = index()
    key = normalize(raw)
    scored: list[dict[str, Any]] = []

    for character in idx.characters:
        best_score = 0.0
        best_name = character.name
        best_mode = "none"
        for label, value in (
            ("name", character.name),
            ("alias", ",".join(character.aliases)),
            ("jp", character.jp),
        ):
            if not value:
                continue
            for piece in (value.split(",") if label == "alias" else [value]):
                candidate = normalize(piece)
                if not candidate:
                    continue
                if candidate == key:
                    score, mode = 1.0, f"exact_{label}"
                elif candidate.startswith(key) or key.startswith(candidate):
                    shorter = min(len(candidate), len(key))
                    span = max(len(candidate), len(key))
                    score = 0.72 + 0.2 * shorter / span
                    mode = f"prefix_{label}"
                elif key in candidate or candidate in key:
                    score, mode = 0.66, f"substring_{label}"
                else:
                    shared = len(set(key) & set(candidate))
                    total = max(1, len(set(key) | set(candidate)))
                    overlap = shared / total
                    score = max(similarity(key, candidate), overlap * 0.95)
                    mode = f"fuzzy_{label}"
                if score > best_score:
                    best_score, best_name, best_mode = score, piece, mode

        if best_score >= threshold:
            scored.append(
                {
                    "id": character.id,
                    "uid4": character.uid4,
                    "name": character.name,
                    "jp": character.jp,
                    "score": round(min(1.0, best_score), 3),
                    "matched": best_name,
                    "matched_on": best_mode,
                }
            )

    scored.sort(key=lambda item: (-item["score"], item["id"]))
    top = scored[: max(1, int(top_k))]
    return {
        "query": raw,
        "threshold": threshold,
        "matches": top,
        "total_above_threshold": len(scored),
    }
