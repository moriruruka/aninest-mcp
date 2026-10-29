# 安装

四种装法，按"你是什么人"来选。每种都在 Windows 11 + Python 3.13 上实跑过。

| 你是谁 | 用哪种 | 需要 |
| --- | --- | --- |
| 只想用，不想碰命令行 | [A. 双击安装脚本](#a-双击安装脚本windows) | Windows 10/11 |
| 习惯命令行、只要这个服务 | [B. 一条 pip 命令](#b-一条命令装完推荐) | Python 3.10+、git |
| 要改代码 / 跑测试 | [C. clone 下来开发](#c-clone-下来开发) | Python 3.10+、git |
| 想用容器 / 部署到别处 | [D. Docker](#d-docker) | Docker |

装完都要做同一件事：**告诉你的 MCP 客户端去启动它**（见 [接入客户端](#接入客户端)）。

---

## A. 双击安装脚本（Windows）

仓库根目录有 `install.cmd`（双击）和它调用的 `install.ps1`。

1. 下载仓库：在 GitHub 页面点 `Code → Download ZIP`，解压到任意目录（路径可以带空格、中文）。
2. 双击 **`install.cmd`**。
3. 脚本会依次：找 Python（要 3.10+）→ 在 `%LOCALAPPDATA%\aninest-mcp\venv` 建独立环境（**不污染系统 Python**）→
   装依赖 → 自己跑一次 MCP 握手确认能用 → 打印一段可以直接粘贴的客户端配置。

想顺手把 Claude Desktop 的配置也写好：

```powershell
.\install.ps1 -WriteClaudeConfig
```

它会把原文件备份成 `claude_desktop_config.json.bak-<时间戳>` 再合并，不会覆盖你已有的其它 server。

国内网络慢就加镜像（清华源实测 8–18 MB/s）：

```powershell
.\install.ps1 -Mirror https://pypi.tuna.tsinghua.edu.cn/simple
```

记忆库在别处时，顺手填进去：

```powershell
.\install.ps1 -MemoryDb "D:\path\to\memory.db"
```

其它参数：`-Upgrade` 重装/升级（不带参数时若已装好会直接跳过）、`-ArenaUrl http://127.0.0.1:6191` 指定作业服务地址。

> 卸载：删掉 `%LOCALAPPDATA%\aninest-mcp` 整个目录即可（它自己不带注册表项、不写系统目录）。

macOS / Linux 用同名脚本 `install.sh`：

```bash
chmod +x install.sh
./install.sh                      # 或 ./install.sh --mirror https://pypi.tuna.tsinghua.edu.cn/simple
./install.sh --write-claude       # 顺手写好 Claude Desktop 配置
```

它把环境放在 `${XDG_DATA_HOME:-~/.local/share}/aninest-mcp/venv`。

## B. 一条命令装完（推荐）

不打算改代码，就不必 clone：

```bash
pip install "git+https://github.com/moriruruka/aninest-mcp.git"
```

国内网络超时就加镜像：

```bash
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple "git+https://github.com/moriruruka/aninest-mcp.git"
```

装完多出一个命令 `aninest-mcp`（等价于 `python -m aninest`）。

> **注意**：本仓库**没有发布到 PyPI**，所以 `pip install aninest-mcp` 会 404。
> 上面这条 git URL 才是官方装法。要装进独立环境而不动系统 Python，用 `pipx install "git+…"`。

实测记录（2026-10-29，全新 venv，pip 25.2）：装出 `aninest_mcp-0.2.1`，
`aninest-mcp.exe` 可直接启动，握手协商到 `protocol=2025-11-25`，`tools/list` 返回 5 个工具。

## C. clone 下来开发

```bash
git clone https://github.com/moriruruka/aninest-mcp.git
cd aninest-mcp

python -m venv .venv
# Windows: .venv\Scripts\activate     macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"

python -m unittest discover -s tests    # 83 个用例
python eval/run_eval.py                 # 离线评测 26/26
python scripts/live_check.py            # 打真服务，全过才 exit 0
```

要接进客户端时，`command` 指向这个 venv 里的 `aninest-mcp` 即可（也可写成
`python -m aninest` 并把 `PYTHONPATH` 指到 `src`）。

## D. Docker

```bash
docker build -t aninest-mcp .
docker run --rm -p 127.0.0.1:8765:8765 aninest-mcp
# 或者
docker compose up --build
```

国内拉不到 `python:3.12-slim` 时，换一个可达的基础镜像，构建步骤不变：

```bash
docker build --build-arg PYTHON_IMAGE=docker.m.daocloud.io/library/python:3.12-slim -t aninest-mcp .
```

镜像行为实测（Docker 29.9.2，Linux 容器）：以 `uid=10001` 非 root 运行、`HEALTHCHECK` 转 healthy、
`initialize` 返回 `serverInfo.version = 0.2.1`、`tools/list` 返回 5 个工具。
容器里用 HTTP 传输（`ANINEST_MCP_TRANSPORT=streamable-http`），宿主机请只映射到 `127.0.0.1`。

---

## 接入客户端

装好之后，任何 MCP 宿主只需要知道"从哪启动、给什么环境变量"。

**Claude Desktop**（`claude_desktop_config.json`）：

```json
{
  "mcpServers": {
    "aninest": {
      "command": "C:\\Users\\<you>\\AppData\\Local\\aninest-mcp\\venv\\Scripts\\aninest-mcp.exe",
      "env": {
        "ANINEST_ARENA_URL": "http://127.0.0.1:6191",
        "ANINEST_MEMORY_DB": "D:\\path\\to\\memory.db"
      }
    }
  }
}
```

配置完**重启客户端**。Windows 上 `command` 建议写绝对路径（PATH 里不一定有这个 venv）。

**DSH**（`C:\Users\<you>\.dsh\profiles\desktop\cordis.patch.yml` 的 `dsh-mcp-client` 条目）：

```yaml
- id: mcp-client
  config:
    servers:
      - serverName: aninest
        transport:
          type: stdio
          command: 'C:\Users\<you>\AppData\Local\aninest-mcp\venv\Scripts\aninest-mcp.exe'
          args: []
```

**只是想看看它长什么样**（不用任何客户端）：

```bash
npx @modelcontextprotocol/inspector aninest-mcp
```

左栏 `tools/list` 能看到五个工具，点任意一个填参数就能调。

---

## 装完之后怎么确认真的能用

三层，从便宜到真实：

```bash
# 1) 服务自己能起、协议能握手（无需网络、无需账号）
python scripts/mcp_smoke.py

# 2) 五个工具逐个调——对着你本机真正在跑的服务
python scripts/live_check.py --memory-db <你的 memory.db>

# 3) 一段完整对话（假作业服务 + 示例记忆库，真实 stdio 协议）
python demo/story.py
```

第 2 层会打印一行一个结果，全过才是 `exit 0`。若某项失败，它会直接告诉你是端口没起、数据库不存在，还是图站连不上。

## 装不上时最常见的原因

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `pip install` 卡住或超时 | 默认 PyPI 在国内不稳 | 加 `-i https://pypi.tuna.tsinghua.edu.cn/simple` |
| `git: command not found` | 没装 Git | 装 Git for Windows / `apt install git`；或改用 A（脚本会从 ZIP 装） |
| `No module named 'mcp'` | 装到了另一个 Python | 用 `python -m pip install …`，确认 `python -c "import sys;print(sys.executable)"` 指向你想用的那个 |
| 客户端里看不到工具 | `command` 相对路径 / 没重启客户端 | 写绝对路径，重启客户端；用 Inspector 先验证命令能起 |
| `memory database not found` | 没配记忆库 | 设 `ANINEST_MEMORY_DB`，或 `python scripts/make_demo_db.py --out demo.db` 造一个 |
| `service_health` 全是 down | 那些服务本来就没跑 | 正常：这是探测本机助手栈的端口（6185/6199/9880/6190/6191），单用本仓库不需要它们 |
