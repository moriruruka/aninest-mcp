"""Turn a free-form Chinese request into image-board tags.

This is a port of the assistant's own art plugin (`astrbot_plugin_art_gallery/tagging.py`),
not a re-invention: the alias tables, the stop-phrase list, the blocked lists and the
count/mode/orientation parsing all come from there, so a request that works in chat
produces the same tags through the tool. The tables live in `_tag_tables.py`, generated
by `scripts/sync_tag_tables.py`.

Deliberately rule-based: no network, no model call, fully unit-testable.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from . import _tag_tables as tables

#: Longest key wins, so "初音未来" beats "初音" and "蓝天" beats "天".
#: Base tables come from the assistant; the extras below are words this tool had
#: before the port and the assistant's table does not (yet) list. Where both sides
#: know a word, the assistant's spelling wins — that is the reference implementation.
_EXTRA_ALIASES: dict[str, list[str]] = {
    "死库水": ["school_swimsuit"],
    "水手服": ["serafuku"],
    "夜空": ["night_sky"],
    "蓝眼": ["blue_eyes"],
    "红眼": ["red_eyes"],
    "赛博朋克": ["cyberpunk"],
    "腿环": ["thigh_strap"],
    "裙": ["skirt"],
    "游戏": ["game"],
    "风景": ["scenery"],
}
_EXTRA_CHARACTERS: dict[str, str] = {"洛天依": "luo_tianyi"}

CN_TAG_ALIASES: dict[str, list[str]] = {**_EXTRA_ALIASES, **tables.CN_TAG_ALIASES}
#: Character names first (they expand to one canonical tag each).
CN_CHARACTERS: dict[str, str] = {**_EXTRA_CHARACTERS, **tables.CN_CHARACTERS}
#: Politeness and "give me a picture" phrasing: stripped before tag matching.
STOP_PHRASES: tuple[str, ...] = tuple(tables.STOP_PHRASES)

#: Words that must never reach a search request. Same defaults as the assistant; a host
#: may override them with `set_blocked`, which is how the panel-editable list works there.
BLOCKED_TAGS: set[str] = set(tables.DEFAULT_BLOCKED_TAGS)
BLOCKED_CN: tuple[str, ...] = tuple(tables.DEFAULT_BLOCKED_CN)

_CN_NUM: dict[str, int] = dict(tables._CN_NUM)
_ORIENTATION_WORDS: dict[str, tuple[str, ...]] = dict(tables._ORIENTATION_WORDS)
_MODE_WORDS: dict[str, tuple[str, ...]] = dict(tables._MODE_WORDS)

#: Count: "3张", "两张", "x2" — mirrors the assistant's pattern.
_COUNT_PATTERN = re.compile(
    r"(?:[xX×*]\s*(\d{1,2}))|(\d{1,2})\s*[张幅个]|([一二两三四五六七八九十])\s*[张幅个]"
)
_MIN_WIDTH = re.compile(r"(\d{3,4})\s*[pP]")
_EN_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_\-]{1,40}")
_SPLIT_UNKNOWN = re.compile(r"[\s，,。.!！?？、;；:：/|（）()\[\]\"'~～]+")
_NON_ASCII_WORD = re.compile(r"[A-Za-z0-9_\-]+")


@dataclass
class ParsedRequest:
    """What the user asked for, in board terms."""

    raw: str = ""
    tags: list[str] = field(default_factory=list)
    negative: list[str] = field(default_factory=list)
    orientation: str | None = None  # portrait / landscape / square
    size: str | None = None  # compressed / original
    count: int | None = None
    min_width: int = 0
    unknown: list[str] = field(default_factory=list)

    def tag_query(self) -> str:
        """Render the booru ``tags`` parameter, negatives as ``-tag``."""
        return " ".join(self.tags + [f"-{tag}" for tag in self.negative])


def set_blocked(
    tags: list[str] | tuple[str, ...] | None = None,
    cn: list[str] | tuple[str, ...] | None = None,
) -> None:
    """Override the runtime blocklists (``None`` keeps the current value).

    Same contract as the assistant's plugin: an empty list means "block nothing",
    ``None`` means "leave it alone". This is what a host uses to apply a panel setting.
    """

    global BLOCKED_TAGS, BLOCKED_CN
    if tags is not None:
        BLOCKED_TAGS = {normalize_tag(str(item)) for item in tags if str(item).strip()}
    if cn is not None:
        BLOCKED_CN = tuple(str(item).strip() for item in cn if str(item).strip())


def normalize_tag(raw: str) -> str:
    """Lower-case, width-fold, snake_case and strip punctuation from a tag.

    Parentheses survive on purpose: danbooru-style character tags are spelled
    ``ganyu_(genshin_impact)``, and dropping the brackets makes them unmatchable.
    """
    text = unicodedata.normalize("NFKC", raw).strip().lower()
    text = re.sub(r"[\s\-]+", "_", text)
    if not re.search(r"[\u4e00-\u9fff]", text):
        text = re.sub(r"[^0-9a-z_.()']", "", text)
    text = re.sub(r"_{2,}", "_", text)
    return text.strip("_")


def detect_blocked(text: str) -> list[str]:
    """Return every blocked word or tag found in ``text`` (empty means allowed)."""
    hits: list[str] = []
    folded = unicodedata.normalize("NFKC", text or "").casefold()
    for word in BLOCKED_CN:
        if word.casefold() in folded:
            hits.append(word)
    for token in _EN_TOKEN.findall(text or ""):
        tag = normalize_tag(token)
        if tag in BLOCKED_TAGS:
            hits.append(token)
    for tag in BLOCKED_TAGS:
        if re.search(rf"(?<![a-z0-9_]){re.escape(tag)}(?![a-z0-9_])", folded) and tag not in hits:
            hits.append(tag)
    return hits


def _extract_count(text: str) -> tuple[int | None, str]:
    """Pull "3张 / 两张 / x2" out of the text. ``None`` when the user did not say."""
    match = _COUNT_PATTERN.search(text)
    if not match:
        return None, text
    if match.group(1):
        count = int(match.group(1))
    elif match.group(2):
        count = int(match.group(2))
    else:
        count = _CN_NUM.get(match.group(3) or "", 0)
    cleaned = text[: match.start()] + " " + text[match.end() :]
    return (count or 0), cleaned


def _extract_words(text: str, mapping: dict[str, tuple[str, ...]]) -> tuple[str | None, str]:
    """Remove the first matching synonym from each synonym group."""
    for value, words in mapping.items():
        for word in words:
            if word.isascii():
                if re.search(rf"\b{re.escape(word)}\b", text, re.I):
                    return value, re.sub(rf"\b{re.escape(word)}\b", " ", text, flags=re.I)
            elif word in text:
                return value, text.replace(word, " ")
    return None, text


def _extract_min_width(text: str) -> tuple[int, str]:
    match = _MIN_WIDTH.search(text)
    if match:
        return int(match.group(1)), text[: match.start()] + " " + text[match.end() :]
    if "大尺寸" in text or "高分辨率" in text:
        return 1600, text.replace("大尺寸", " ").replace("高分辨率", " ")
    return 0, text


def parse_request(text: str) -> ParsedRequest:
    """Parse a request such as ``初音未来 泳装 竖图 2张 压缩图``.

    Raises:
        ValueError: if the request is empty, contains a blocked word, or yields no tag.
    """
    raw = (text or "").strip()
    if not raw:
        raise ValueError("empty request")

    blocked = detect_blocked(raw)
    if blocked:
        raise ValueError(f"request contains a blocked word: {blocked[0]}")

    result = ParsedRequest(raw=raw)
    working = unicodedata.normalize("NFKC", raw)

    count, working = _extract_count(working)
    if count is not None:
        result.count = max(1, min(10, count))

    mode, working = _extract_words(working, _MODE_WORDS)
    if mode:
        result.size = "original" if mode == "original" else "compressed"

    orientation, working = _extract_words(working, _ORIENTATION_WORDS)
    result.orientation = orientation or None

    min_width, working = _extract_min_width(working)
    result.min_width = min_width

    seen: set[str] = set()

    # 1) bare English words are tags already (users type `underwater`, `bikini`).
    for token in _EN_TOKEN.findall(working):
        tag = normalize_tag(token)
        if len(tag) >= 3 and tag not in seen:
            seen.add(tag)
            result.tags.append(tag)

    # 2) Chinese: character names first (longest first), then ordinary words.
    chinese_only = _NON_ASCII_WORD.sub(" ", working)
    leftovers = chinese_only
    for name in sorted(CN_CHARACTERS, key=len, reverse=True):
        if name and name in leftovers:
            tag = normalize_tag(CN_CHARACTERS[name])
            if tag and tag not in seen:
                seen.add(tag)
                result.tags.append(tag)
            leftovers = leftovers.replace(name, " ")

    for phrase in sorted(CN_TAG_ALIASES, key=len, reverse=True):
        if phrase and phrase in leftovers:
            for tag in CN_TAG_ALIASES[phrase]:
                value = normalize_tag(tag)
                if value and value not in seen:
                    seen.add(value)
                    result.tags.append(value)
            leftovers = leftovers.replace(phrase, " ")

    # 3) whatever Chinese is left over is reported back instead of guessed at.
    # Politeness goes first: stripping it earlier would eat real words ("图书馆"
    # contains "图", which is a stop phrase).
    for phrase in STOP_PHRASES:
        leftovers = leftovers.replace(phrase, " ")
    for chunk in _SPLIT_UNKNOWN.split(leftovers):
        chunk = chunk.strip()
        if len(chunk) >= 2:
            result.unknown.append(chunk)

    if not result.tags and not result.unknown:
        raise ValueError("no usable tag in request")

    return result


def build_query(
    text: str,
    extra_tags: list[str] | None = None,
    negative: list[str] | None = None,
) -> ParsedRequest:
    """Parse a request and merge caller-supplied include/exclude tags on top."""
    parsed = parse_request(text)
    for raw in extra_tags or []:
        tag = normalize_tag(raw)
        if not tag or tag in parsed.tags:
            continue
        if tag in BLOCKED_TAGS:
            raise ValueError(f"tag is blocked: {tag}")
        parsed.tags.append(tag)
    for raw in negative or []:
        tag = normalize_tag(raw).lstrip("-")
        if not tag or tag in parsed.negative:
            continue
        if tag in BLOCKED_TAGS:
            raise ValueError(f"negative tag is blocked: {tag}")
        parsed.negative.append(tag)
    return parsed
