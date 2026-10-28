"""Turn a free-form Chinese request into image-board tags.

Deliberately rule-based: no network, no model call, fully unit-testable.
A model can call this tool to get canonical tags before searching, which keeps
the "LLM guesses a tag" failure mode out of the search path.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

#: Common Chinese words -> booru tag. Longest key wins, so "初音未来" beats "初音".
CN_TAG_ALIASES: dict[str, str] = {
    "初音未来": "hatsune_miku",
    "初音": "hatsune_miku",
    "洛天依": "luo_tianyi",
    "泳装": "swimsuit",
    "泳衣": "swimsuit",
    "比基尼": "bikini",
    "死库水": "school_swimsuit",
    "星空": "starry_sky",
    "夜空": "night_sky",
    "樱花": "cherry_blossoms",
    "花海": "flower_field",
    "猫耳": "cat_ears",
    "兽耳": "animal_ears",
    "女仆": "maid",
    "校服": "school_uniform",
    "水手服": "serafuku",
    "和服": "kimono",
    "浴衣": "yukata",
    "双马尾": "twintails",
    "马尾": "ponytail",
    "长发": "long_hair",
    "短发": "short_hair",
    "银发": "silver_hair",
    "白发": "white_hair",
    "黑发": "black_hair",
    "金发": "blonde",
    "蓝眼": "blue_eyes",
    "红眼": "red_eyes",
    "微笑": "smile",
    "害羞": "blush",
    "睡觉": "sleeping",
    "雨天": "rain",
    "雪": "snow",
    "图书馆": "library",
    "咖啡馆": "cafe",
    "教室": "classroom",
    "海滩": "beach",
    "机甲": "mecha",
    "赛博朋克": "cyberpunk",
    "白丝": "white_thighhighs",
    "黑丝": "black_thighhighs",
    "腿环": "thigh_strap",
    "裙": "skirt",
    "制服": "uniform",
    "游戏": "game",
    "风景": "scenery",
}

#: Words that must never reach a search request.
BLOCKED_TAGS: frozenset[str] = frozenset(
    {
        "loli",
        "lolicon",
        "shota",
        "shotacon",
        "toddler",
        "child",
        "underage",
        "rape",
        "bestiality",
        "guro",
        "scat",
    }
)
BLOCKED_CN: frozenset[str] = frozenset(
    {"萝莉", "幼女", "幼齿", "正太", "强暴", "兽交", "猎奇", "中出"}
)

_CN_PUNCT = re.compile(r"[\s,，。、;；:：!！?？~～\-—_/\\|]+")
_EN_TOKEN = re.compile(r"^[a-z0-9](?:[a-z0-9_:()'.\-]*[a-z0-9])?$")
_COUNT = re.compile(r"(\d{1,2})\s*(?:张|幅|个)")
_ORIENTATION = {
    "横图": "landscape",
    "横版": "landscape",
    "宽图": "landscape",
    "竖图": "portrait",
    "竖版": "portrait",
    "方图": "square",
    "方形": "square",
}
_SIZE = {
    "原图": "original",
    "高清": "original",
    "大图": "original",
    "压缩图": "compressed",
    "压缩": "compressed",
    "小图": "compressed",
    "缩略图": "compressed",
}


@dataclass
class ParsedRequest:
    tags: list[str] = field(default_factory=list)
    negative: list[str] = field(default_factory=list)
    orientation: str | None = None
    size: str | None = None
    count: int | None = None
    unknown: list[str] = field(default_factory=list)

    def tag_query(self) -> str:
        """Render the booru ``tags`` parameter, negatives as ``-tag``."""
        return " ".join(self.tags + [f"-{tag}" for tag in self.negative])


def normalize_tag(raw: str) -> str:
    """Lower-case, width-fold, snake_case and strip punctuation from a tag."""
    text = unicodedata.normalize("NFKC", raw).strip().lower()
    text = re.sub(r"[\s\-]+", "_", text)
    if not re.search(r"[\u4e00-\u9fff]", text):
        text = re.sub(r"[^\w]", "", text)
    return text.strip("_")


def is_blocked(tag: str) -> bool:
    return normalize_tag(tag) in BLOCKED_TAGS


def _split_chinese(text: str) -> list[str]:
    return [chunk for chunk in _CN_PUNCT.split(text) if chunk]


def parse_request(text: str) -> ParsedRequest:
    """Parse a request such as ``初音未来 泳装 竖图 2张 压缩图``.

    Raises:
        ValueError: if the request contains a blocked word.
    """
    if not text or not text.strip():
        raise ValueError("empty request")

    folded = unicodedata.normalize("NFKC", text).strip()
    lowered = folded.lower()

    for word in BLOCKED_CN:
        if word in folded:
            raise ValueError(f"request contains a blocked word: {word}")

    result = ParsedRequest()

    match = _COUNT.search(folded)
    if match:
        result.count = max(1, min(10, int(match.group(1))))
        folded = _COUNT.sub(" ", folded)

    for word, value in _ORIENTATION.items():
        if word in folded:
            result.orientation = value
            folded = folded.replace(word, " ")
            break

    for word, value in _SIZE.items():
        if word in folded:
            result.size = value
            folded = folded.replace(word, " ")
            break

    seen: set[str] = set()
    for token in _split_chinese(folded):
        token = token.strip()
        if not token:
            continue

        matched = False
        for word in sorted(CN_TAG_ALIASES, key=len, reverse=True):
            if word and word in token:
                tag = CN_TAG_ALIASES[word]
                if tag not in seen:
                    seen.add(tag)
                    result.tags.append(tag)
                token = token.replace(word, " ")
                matched = True
        if not matched:
            candidate = normalize_tag(token)
            if not candidate:
                continue
            if is_blocked(candidate):
                raise ValueError(f"request contains a blocked tag: {candidate}")
            if _EN_TOKEN.match(candidate) and candidate not in seen:
                seen.add(candidate)
                result.tags.append(candidate)
            elif candidate not in seen:
                result.unknown.append(token)

    for word in lowered.split():
        candidate = normalize_tag(word)
        if _EN_TOKEN.match(candidate) and not is_blocked(candidate) and candidate not in seen:
            seen.add(candidate)
            result.tags.append(candidate)

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
        if is_blocked(tag):
            raise ValueError(f"tag is blocked: {tag}")
        parsed.tags.append(tag)
    for raw in negative or []:
        tag = normalize_tag(raw).lstrip("-")
        if not tag or tag in parsed.negative:
            continue
        if is_blocked(tag):
            raise ValueError(f"negative tag is blocked: {tag}")
        parsed.negative.append(tag)
    return parsed
