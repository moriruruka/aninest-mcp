"""Talk to the server over real MCP (stdio) without any third-party client.

Usage::

    python scripts/mcp_smoke.py
    python scripts/mcp_smoke.py --call art_search --args '{"query":"初音未来 泳装","count":1}'
    python scripts/mcp_smoke.py --call service_health
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]


async def run(tool: str | None, arguments: dict) -> int:
    env = dict(os.environ)
    env.setdefault("PYTHONPATH", str(ROOT / "src"))
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "aninest"],
        env=env,
        cwd=str(ROOT),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("tools:")
            for item in tools.tools:
                print(f"  - {item.name}: {(item.description or '').splitlines()[0]}")

            prompts = await session.list_prompts()
            print("prompts:", [p.name for p in prompts.prompts])
            resources = await session.list_resource_templates()
            print("resource templates:", [r.uriTemplate for r in resources.resourceTemplates])

            if tool:
                result = await session.call_tool(tool, arguments)
                print(f"\n{tool} ->")
                for block in result.content:
                    text = getattr(block, "text", None)
                    if text is not None:
                        print(text)
                    else:
                        print(f"[{type(block).__name__}]")
                return 0 if not result.isError else 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="MCP self-check client")
    parser.add_argument("--call", help="tool name to call after listing")
    parser.add_argument("--args", default="{}", help="JSON object with tool arguments")
    parser.add_argument("--args-file", help="path to a JSON file with tool arguments")
    options = parser.parse_args()
    if options.args_file:
        arguments = json.loads(Path(options.args_file).read_text(encoding="utf-8-sig"))
    else:
        arguments = json.loads(options.args)
    return asyncio.run(run(options.call, arguments))


if __name__ == "__main__":
    raise SystemExit(main())
