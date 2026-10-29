"""A minimal host: the smallest program that can *hold a conversation* and call AniNest.

为什么仓库里要有这个文件
------------------------
AniNest 本身不是聊天机器人，它是「能力层」。真实的使用者是另一个程序——

    ┌────────────────────┐   MCP(stdio/HTTP)   ┌──────────────┐
    │ 宿主：桌面助手/QQ 机器人 │ ─────────────────► │  AniNest     │
    └────────────────────┘                     └──────────────┘

只发一个 server，读者会问「那谁在用它？怎么用？」。这个文件就是答案：
它能连上 server、听懂一句话、挑一个工具、把结果说成人话。

它**故意不用大模型**：这里用一条确定性路由（关键词 → 工具），所以不需要 API key，
任何人都能复现。真实宿主里这一步是模型在做——文末有一段说明怎么接。

用法::

    python demo/host.py                                  # 交互式
    python demo/host.py --say "本机服务都活着吗"          # 单句
    python demo/host.py --say "来一张初音未来泳装压缩图"
    python demo/host.py --say "查一下 100141 100241 100341 100441 100541 的作业"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
VERBOSE = False

# Windows 控制台默认 cp936/cp1252，打印中文和 emoji 会炸；统一切成 UTF-8。
for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if _reconfigure is not None:
        try:
            _reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):  # pragma: no cover - unusual streams
            pass

# ---------------------------------------------------------------- routing ---

_ID = re.compile(r"\b\d{6}\b")
_REPLACE = re.compile(
    r"把?\s*([^\s，,、。；;：:]{1,12})\s*(?:换成|替换成|替换为|改成|换作)\s*"
    r"([^\s，,、。；;：:]{1,12})"
)
_ARENA_WORDS = ("作业", "阵容", "防守", "队伍", "jjc")
_CHAR_WORDS = ("哪个角色", "什么角色", "是谁", "分别是", "对应哪个", "叫什么")
_NOISE = (
    "查一下", "帮我查", "帮我", "请问", "问一下", "再查一次", "再查", "查",
    "看看", "这个", "这套", "的作业", "作业", "阵容", "防守", "竞技场", "竞技", "就换一个",
    "换一个", "一下", "呢", "吗", "。", "？", "?", "，", ",", "：", ":",
    "分别是哪个角色", "分别是", "哪个角色", "什么角色", "是谁", "对应哪个", "叫什么",
)
_SPLIT = re.compile(r"[、,，和与及/\s]+")


def _clean(text: str) -> str:
    out = text
    for word in _NOISE:
        out = out.replace(word, " ")
    return " ".join(part for part in _SPLIT.split(out) if part)


def route(text: str) -> tuple[str, dict] | None:
    """把一句话映射成一次工具调用；认不出来就返回 None（交给模型/提示用户）。"""
    lowered = text.lower()
    ids = [int(m) for m in _ID.findall(text)]

    if any(word in text for word in ("服务", "状态", "活着", "端口")) or "health" in lowered:
        return "service_health", {}

    if any(word in text for word in _CHAR_WORDS):
        return "character_lookup", {"query": _clean(text), "limit": 5}

    replace = _REPLACE.search(text)
    if replace and any(word in text for word in _ARENA_WORDS):
        lineup = _clean(text.replace(replace.group(0), " ")).split()
        return "arena_lookup", {
            "defense": lineup or None,
            "replace": [f"{replace.group(1)}->{replace.group(2)}"],
            "limit": 3,
        }

    if any(word in text for word in _ARENA_WORDS) or "arena" in lowered:
        lineup = _clean(text).split()
        if not ids and not lineup:
            return None
        if ids and not lineup:
            return "arena_lookup", {"def_ids": ids, "limit": 3}
        return "arena_lookup", {"defense": lineup or None, "def_ids": ids or None, "limit": 3}

    if any(word in text for word in ("统计", "多少条", "规模")) and any(
        word in text for word in ("记忆", "知识", "memory")
    ):
        return "memory_stats", {}

    if any(word in text for word in ("回忆", "记得", "记忆")) or "remember" in lowered:
        polite = r"^(帮我|请|麻烦你)?"
        verbs = r"(回忆一下|回忆|记得|想一想|查一下|找一下|看看)"
        query = re.sub(polite + verbs + r"[:：,，]?\s*", "", text).strip()
        return "memory_search", {"query": query or text, "limit": 5}

    art_words = ("图", "插画", "画一个", "来一张", "来两张")
    if any(word in text for word in art_words) or "art" in lowered:
        query = re.sub(r"^(帮我|请)?(来|找|搜|要)?(一|两|三|几)?张?", "", text).strip()
        count = 2 if "两" in text or "2" in text else 1
        return "art_search", {"query": query or text, "count": count, "size": "compressed"}

    return None


# ------------------------------------------------------------------ host ---


def _env() -> dict[str, str]:
    env = dict(os.environ)
    env.setdefault("PYTHONPATH", str(ROOT / "src"))
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


def _first_text(result) -> str:
    for block in result.content:
        text = getattr(block, "text", None)
        if text is not None:
            return text
    return "（工具没有返回文本）"


_ERROR_HINTS = {
    "cannot apply replacement": "这次替换没改成——同一个角色、或者队里已经有这个人了。换一个再试。",
    "no character resolved": "这几个名字一个都没认出来。可以先用 character_lookup 看看标准写法。",
    "defense is required": "没给阵容。至少要有一个角色名或 id。",
    "arena service rejected": "作业服务拒绝了这次请求（多半是登录态或风控）。",
    "arena request failed": "连不上作业服务，检查它有没有在跑。",
    "vision": "这台机器没装识图依赖，或者没有头像包。",
    "address must be http or https": "只接受 http/https 地址。",
    "host not allowed": "这个域名不在允许列表里。",
}


def _speak_error(tool: str, payload: str) -> str:
    """把工具报错说成人话；对不上的原样给出来，免得吞掉信息。"""
    for needle, hint in _ERROR_HINTS.items():
        if needle in payload:
            return f"{hint}（原文：{payload.splitlines()[0][:160]}）"
    return payload.splitlines()[0][:200] if payload else "工具报错了，但没给具体原因。"


def _unresolved(payload: str) -> list[str]:
    """Tokens the lookup could not resolve — the ones worth a similarity hint."""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return []
    return [str(item) for item in data.get("unresolved") or []]


def _speak_match(payload: str) -> str:
    try:
        matches = json.loads(payload).get("matches") or []
    except json.JSONDecodeError:
        return ""
    return "、".join(f"{item['name']}（{item['score']:.2f}）" for item in matches[:3])


def _speak(tool: str, payload: str) -> str:
    """把工具返回的结构化 JSON 说成人话——真实宿主里这步由模型完成。"""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return payload

    if tool == "service_health":
        services = data.get("services") or {}
        down = [name for name, item in services.items() if not item.get("up")]
        speech = f"{data.get('up')}/{data.get('total')} 个服务在线。"
        return speech + (f"没起来的：{'、'.join(down)}。" if down else "")

    if tool == "character_lookup":
        matches = data.get("matches") or []
        if not matches:
            return "这个角色名我没认出来（真实宿主里会把候选念给你听）。"
        said = "、".join(f"{item['name']}（{item['id']}）" for item in matches)
        unknown = data.get("unresolved") or []
        return f"对上 {len(matches)} 个：{said}。" + (
            f" 没认出来的：{'、'.join(unknown)}。" if unknown else ""
        )

    if tool == "arena_lookup":
        teams = data.get("teams") or []
        lineups = data.get("lineup") or []
        asked = " / ".join(
            f"{item['slot']}号位 {item['name']}" for item in lineups
        ) or "（未知阵容）"
        if not teams:
            return f"按 {asked} 查，作业网没给结果。"
        first = teams[0]
        names = first.get("defense_names") or first.get("defense") or []
        lineup = " / ".join(str(n) for n in names) or "（未知阵容）"
        votes = []
        if first.get("upvotes") is not None:
            votes.append(f"赞 {first['upvotes']}")
        if first.get("downvotes") is not None:
            votes.append(f"踩 {first['downvotes']}")
        tail = f"（{'、'.join(votes)}）" if votes else ""
        applied = data.get("applied") or []
        change = ""
        for item in applied:
            action = item.get("action")
            if action == "replace":
                change += f"（把 {item.get('from')} 换成 {item.get('to')}）"
            elif action == "exclude":
                change += f"（先拿掉 {item.get('from')}）"
        return (
            f"按 {asked} 查{change}：找到 {data.get('found', len(teams))} 支队伍，"
            f"最热门的是 {lineup}{tail}。"
        )

    if tool == "art_search":
        images = data.get("results") or []
        if not images:
            return "这次没搜到合适的图。"
        note = f"（第 {data.get('attempt')} 次尝试，条件放宽过）" if data.get("relaxed") else ""
        return f"给你 {len(images)} 张{note}：{images[0].get('url')}"

    if tool == "memory_search":
        hits = data.get("hits") or []
        if not hits:
            return "记忆库没有相关条目。"
        return f"想起 {len(hits)} 条，最相关的是：「{hits[0].get('content')}」"

    if tool == "memory_stats":
        scopes = data.get("by_scope") or {}
        return (
            f"记忆库 {data.get('rows')} 条（全局 {scopes.get('global', 0)}、"
            f"会话 {scopes.get('session', 0)}，平均 {data.get('avg_content_chars')} 字）。"
        )

    return payload


async def converse(lines: list[str], echo_prompts: bool = True, verbose: bool = False) -> int:
    global VERBOSE
    VERBOSE = verbose or os.environ.get("ANINEST_DEMO_VERBOSE") == "1"
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "aninest"], env=_env(), cwd=str(ROOT)
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            if echo_prompts:
                tools = await session.list_tools()
                names = "、".join(t.name for t in tools.tools)
                print(f"[host] 已连接 {len(tools.tools)} 个工具：{names}")
                print()

            for line in lines:
                line = line.strip()
                if not line:
                    continue
                if line in {"exit", "quit", "退出"}:
                    print("[host] 再见。")
                    return 0

                print(f"你   > {line}")
                picked = route(line)
                if picked is None:
                    print("host > 这句话没匹配到工具（真实宿主里，这里交给模型判断）。")
                    print()
                    continue

                tool, args = picked
                if VERBOSE:
                    print(f"host > 调 {tool}({json.dumps(args, ensure_ascii=False)})")
                result = await session.call_tool(tool, args)
                payload = _first_text(result)
                # 名字没认出来时，真实宿主会先问"你是不是指 X"；这里用相似度工具演示同一件事。
                missing = _unresolved(payload) if tool == "character_lookup" else []
                if missing:
                    hint = await session.call_tool(
                        "character_match", {"query": missing[0], "threshold": 0.4}
                    )
                    suggestion = _speak_match(_first_text(hint))
                    if suggestion:
                        print(f"host > 这个角色名我没对上，最接近的是：{suggestion}")
                        print("host > （真实宿主会问要不要用这个；")
                        print("host >   确认后用 character_correct 记住它）")
                        print()
                        continue
                if result.isError:
                    print(f"host > 这一步没成功：{_speak_error(tool, payload)}")
                    if VERBOSE:
                        print(f"mcp  > 工具报错：{payload}")
                else:
                    if VERBOSE:
                        print(f"mcp  > {payload[:280]}{'' if len(payload) <= 280 else ' …'}")
                    print(f"host > {_speak(tool, payload)}")
                print()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="AniNest demo host")
    parser.add_argument("--say", action="append", default=[], help="说一句话然后退出（可重复）")
    parser.add_argument("--quiet-prompts", action="store_true", help="不打印工具清单")
    parser.add_argument("--verbose", action="store_true", help="额外打印工具名、原始 JSON")
    options = parser.parse_args()

    if options.say:
        return asyncio.run(
            converse(options.say, echo_prompts=not options.quiet_prompts, verbose=options.verbose)
        )

    print("[host] 这是一个最小宿主示例。输入一句话，或 Ctrl-C 退出。")
    print("[host] 试试：本机服务都活着吗")
    print("[host] 或：来两张初音未来泳装压缩图")
    print("[host] 或：查一下 100141 100241 100341 100441 100541 的作业")
    print()
    lines: list[str] = []
    for raw in sys.stdin:
        lines.append(raw)
    return asyncio.run(converse(lines, echo_prompts=True, verbose=options.verbose))


if __name__ == "__main__":
    raise SystemExit(main())
