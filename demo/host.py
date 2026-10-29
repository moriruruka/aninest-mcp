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


def route(text: str) -> tuple[str, dict] | None:
    """把一句话映射成一次工具调用；认不出来就返回 None（交给模型/提示用户）。"""
    lowered = text.lower()
    ids = [int(m) for m in _ID.findall(text)]

    if any(word in text for word in ("服务", "状态", "活着", "端口")) or "health" in lowered:
        return "service_health", {}

    arena_words = ("作业", "阵容", "队伍", "jjc")
    if ids and (any(word in text for word in arena_words) or "arena" in lowered):
        return "arena_lookup", {"def_ids": ids, "limit": 3}

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

    if tool == "arena_lookup":
        teams = data.get("teams") or []
        if not teams:
            return "作业网这次没给结果。"
        first = teams[0]
        lineups = first.get("defense") or first.get("attack") or []
        lineup = " / ".join(str(n) for n in lineups) or "（未知阵容）"
        votes = []
        if first.get("upvotes") is not None:
            votes.append(f"赞 {first['upvotes']}")
        if first.get("downvotes") is not None:
            votes.append(f"踩 {first['downvotes']}")
        tail = f"（{'、'.join(votes)}）" if votes else ""
        return f"找到 {data.get('found', len(teams))} 支队伍，最热门的是：{lineup}{tail}。"

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


async def converse(lines: list[str], echo_prompts: bool = True) -> int:
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
                print(f"host > 调 {tool}({json.dumps(args, ensure_ascii=False)})")
                result = await session.call_tool(tool, args)
                payload = _first_text(result)
                if result.isError:
                    print(f"mcp  > 工具报错：{payload}")
                else:
                    print(f"mcp  > {payload[:280]}{'' if len(payload) <= 280 else ' …'}")
                    print(f"host > {_speak(tool, payload)}")
                print()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="AniNest demo host")
    parser.add_argument("--say", action="append", default=[], help="说一句话然后退出（可重复）")
    parser.add_argument("--quiet-prompts", action="store_true", help="不打印工具清单")
    options = parser.parse_args()

    if options.say:
        return asyncio.run(converse(options.say, echo_prompts=not options.quiet_prompts))

    print("[host] 这是一个最小宿主示例。输入一句话，或 Ctrl-C 退出。")
    print("[host] 试试：本机服务都活着吗")
    print("[host] 或：来两张初音未来泳装压缩图")
    print("[host] 或：查一下 100141 100241 100341 100441 100541 的作业")
    print()
    lines: list[str] = []
    for raw in sys.stdin:
        lines.append(raw)
    return asyncio.run(converse(lines, echo_prompts=True))


if __name__ == "__main__":
    raise SystemExit(main())
