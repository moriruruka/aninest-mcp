"""一条命令跑完整个故事：不需要账号、不需要网络、不需要客户端。

它做四件事：

1. 起一个假的本机作业服务（`scripts/fake_arena.py`），代替需要登录态的私有服务；
2. 造一个示例记忆库（`scripts/make_demo_db.py`）；
3. 用最小宿主（`demo/host.py`）通过 **真实 MCP stdio 协议** 连上 server；
4. 依次说三句话，把返回的 JSON 说成人话。

    python demo/story.py

输出就是一段可以直接贴进 README / 面试里讲的对话记录。
"""

from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Windows 控制台默认 cp936；先把输出切到 UTF-8，否则中文提示会是乱码。
for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if _reconfigure is not None:
        try:
            _reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):  # pragma: no cover - unusual streams
            pass
DEMO_DB = ROOT / "demo" / "demo_memory.db"
ARENA_PORT = 6192

SCRIPT = [
    "本机服务都活着吗",
    "帮我回忆一下泳装插画那件事",
    "布丁、克总、真琴、纺希、莉莎这个防守的作业",
    "布丁、克总、真琴、纺希、莉莎这个防守，把布丁换成怜，再查一次",
    "布丁和克总分别是哪个角色",
]


def _port_free(port: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.3)
        return sock.connect_ex(("127.0.0.1", port)) != 0


def prepare() -> subprocess.Popen | None:
    """造数据 + 起假服务；返回需要善后的进程。"""
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "make_demo_db.py"), "--out", str(DEMO_DB)],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    if not _port_free(ARENA_PORT):
        print(f"[story] 端口 {ARENA_PORT} 已被占用，复用现有服务")
        return None
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "scripts" / "fake_arena.py"), "--port", str(ARENA_PORT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(50):
        if not _port_free(ARENA_PORT):
            break
        time.sleep(0.1)
    return proc


def main() -> int:
    print("[story] 准备：示例记忆库 + 假作业服务")
    proc = prepare()
    os.environ["ANINEST_MEMORY_DB"] = str(DEMO_DB)
    os.environ["ANINEST_ARENA_URL"] = f"http://127.0.0.1:{ARENA_PORT}"
    print("[story] 连上 server，开始对话\n")

    sys.path.insert(0, str(ROOT / "demo"))
    import host  # noqa: E402  (放在 env 设好之后导入)

    try:
        code = asyncio.run(host.converse(SCRIPT, echo_prompts=True))
    finally:
        if proc is not None:
            proc.terminate()
            proc.wait(timeout=5)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
