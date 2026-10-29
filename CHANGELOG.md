# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 与 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Fixed

- `arena_lookup` 原本接受 1–6 个角色 id，但游戏里一队只有 5 人：上限改为 **5 个不重复 id**
  （去重后才计数量，部分阵容仍合法），并同步工具描述、README 与威胁模型。
- `arena_lookup` 读取的是**上游真实结构**，此前按臆想的扁平行解析（`defense`/`attack`/`views`），
  接真实服务时恒返回 0 支队伍，而 fixture 测试全绿。现在会向下走到第一个队伍列表，
  从 `[{id, star, equip}]` 里取角色 id，票数用 `up`/`down`，不再编造播放量。
  回归样本：`tests/fixtures/arena_payload.json`（真实返回截取）。
- `scripts/fake_arena.py` 的响应结构同步为真实形状，避免替身把错误结构“验成正确”。

### Added

- `scripts/live_check.py`：对着**本机真实运行的服务**做端到端检查——真实 MCP stdio 起 server，
  逐个调五个工具并打印一行结果，全过才返回 0；带 `--skip-network`、`--ids`。
- `docs/TESTING.md`：分层验证手册（lint → 单测 → 离线评测 → 替身演示 → 真机联调），
  每层写明“能证明什么、不能证明什么”，附失败排查表与已知未覆盖清单。
- `demo/host.py`：最小 MCP 宿主（26 行路由 + 结构化结果说人话），证明 server 不依赖特定客户端。
- `demo/story.py`：一条命令跑完整段对话——起假作业服务、造示例记忆库、经真实 stdio 协议调三个工具。
- `tests/test_demo_router.py`：8 个用例覆盖路由与结果转述；连同阵容校验的两条新用例，单测总数 55 → 65。
- `docs/ORIGIN.md`：写在“为什么会有这个仓库”——能力原先是私有助手的一部分，抽成 MCP 后才可复用、可测试、可评测。
- README 增「来历」「看得见的验证」两节（含 mermaid 图与实跑对话记录）。
- CI 增演示步骤（`python demo/story.py`），lint 覆盖 `demo/`。

## [0.1.0] - 2026-10-29

首个公开版本：把个人助手（AniNest）的四类本地能力暴露为 MCP 工具。

### Added

- `art_search`：中文/英文描述 → booru tag → 图站检索 → 图片链接。
  - `tagging.py` 规则编译器（最长优先替换、未知词回报、黑名单拦截）。
  - 检索降级阶梯：`全条件 → 去掉方向约束 → 逐个减 tag`，返回 `relaxed` / `attempt`。
  - 分级归一化：`s/safe/g/general` 视为 safe，`q/e` 丢弃。
  - 支持 `count`、`size`（compressed/original）、`orientation`、`extra_tags`、`negative`。
- `arena_lookup`：通过本机浏览器服务查询阵容作业，含 id 校验与 payload 扁平化。
- `memory_search` / `memory_stats`：只读 SQLite 记忆检索（token 重叠 + 重要性先验）与库规模统计。
- `service_health`：五个本地服务端口的 TCP 探活。
- MCP 附加能力：`aninest://memory/stats` resource、`find_illustration` prompt。
- 55 个单元测试（`tests/`），26 条 golden case 的离线评测与联网评测脚本（`eval/`）。
- 自检客户端 `scripts/mcp_smoke.py`（真实 MCP stdio 会话，不依赖第三方宿主）。
- 可复现替身：`scripts/fake_arena.py`（同契约假响应，验证 `arena_lookup`）、
  `scripts/make_demo_db.py`（生成示例记忆库，验证 `memory_search` / `memory_stats`）。
- CI：Linux + Windows × Python 3.10/3.12/3.13，lint → 单测 → 离线评测 → Docker 构建与冒烟。
- Dockerfile（非 root、HEALTHCHECK，基础镜像可用 `--build-arg PYTHON_IMAGE=` 覆盖）与 docker-compose。
- 握手自报版本：`initialize` 的 `serverInfo.version` 由 `src/aninest/version.py` 提供（0.1.0），
  不再回落到 MCP SDK 的版本号。
- 文档：README、`docs/DECISIONS.md`（设计取舍）、`docs/ARCHITECTURE.md`（代码结构与改动指引）、
  `docs/PRIVACY.md`（数据边界与自查命令）、`docs/THREAT_MODEL.md`（资产/信任边界/出站能力/已知缺口）、
  `docs/NAMING.md`（命名由来）、CONTRIBUTING。

### Fixed

- CI 在 Windows 运行器上因控制台编码（cp1252）打印中文用例崩溃：`eval/run_eval.py` 与 `tests/context.py`
  现在显式把 stdout/stderr 切到 UTF-8，workflow 级也设了 `PYTHONIOENCODING=utf-8`。
- CI 的 Docker 冒烟步骤原先用 heredoc 喂 stdin，未加 `-i` 时容器读不到脚本、等于空跑；改为
  `--entrypoint python -c "…"`，断言失败会真正让任务变红。

### Changed

- CI 升到 `actions/checkout@v7` 与 `actions/setup-python@v7`（消除 Node.js 20 弃用告警），
  运行器标签由 `ubuntu-latest` / `windows-latest` 固定为 `ubuntu-24.04` / `windows-2025`，
  避免镜像滚动（Ubuntu 26 迁移）带来的意外变更。

### Known limitations

- 依赖锁定 `mcp>=1.20,<2`：2.x 把 `FastMCP` 改名为 `MCPServer`，迁移需同步改工具注册与 `ToolError` 导入。
- 只支持 Gelbooru 风格 JSON API；Moebooru（konachan / yande.re）适配在 Roadmap。
- `arena_lookup` 依赖本机浏览器服务的 HTTP 契约，不内置登录流程。
- `memory_search` 未使用 embedding；规模上万条后建议替换打分函数。
- HTTP/SSE 模式默认无鉴权，只监听 `127.0.0.1`。
