# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 与 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Added

- 工具元数据补齐 MCP 规范里的可选字段：5 个工具现在都带 `title`（人类可读名）与
  `annotations`（`readOnlyHint=true`、`destructiveHint=false`；`art_search`/`arena_lookup`
  额外 `openWorldHint=true`），宿主可以据此免确认、或提示"会联网"。
- `docs/COMPLIANCE.md`：逐项列出"已符合 / 有意不做 / 还能加固"，每条都给出可复验的证据与命令。
- `tests/test_server_contract.py`：7 个契约用例，锁住工具清单、schema、title、annotations、
  resource 与 prompt，防止后续改动悄悄丢掉这些字段。
- README 增「只想要命令行：从 GitHub 直接装」——`pip install "git+https://github.com/moriruruka/aninest-mcp.git"`，
  附 2026-10-29 在全新 venv 的实测记录（装出 0.2.0、握手协商 `2025-11-25`、5 个工具、`service_health` 5/5）。

### Fixed

- `config.py` 的默认 User-Agent 还写着 `aninest-mcp/0.1 (+https://github.com/)`（占位 URL、版本过期），
  改为按 `version.py` 的版本号与真实仓库地址生成。
- 记忆库文件不存在时，报错只说"not found"；现在同时给出下一步（设 `ANINEST_MEMORY_DB`
  或跑 `scripts/make_demo_db.py`），新用户不必去翻源码。

## [0.2.0] - 2026-10-29

### Changed

- **中文词典、角色表、礼貌词表与黑名单改为整表移植自助手实现**（171 条别名 / 56 个角色 /
  39 条礼貌词 / 26 条英文黑名单 / 19 条中文黑名单），替换掉此前手写的约 60 条小词表。
  两者现在对同一句中文给出同一组 tag；移植结果由 `scripts/port_tags.py` 生成，可复现。
- 补了 11 个助手词典里没有、但本工具原先支持的词（死库水、水手服、夜空、蓝眼、红眼、
  赛博朋克、腿环、裙、游戏、风景、洛天依），避免移植后能力反而变窄。
- `eval/art_cases.json` 的期望值对齐助手侧的规范拼写（`flowers`、`blonde_hair`、`beach`）。
- 单测 65 → 76：新增词典规模断言（防“改漏”）、`图书馆` 回归、以及 11 条移植用例。

### Fixed

- 礼貌词原先**在别名匹配之前**就被剥离，导致「图书馆」中的「图」被吃掉、剩下「书馆」成了未知词
  （助手侧同样存在，已在 `docs/PORTING.md` 记录）。
- `arena_lookup` 原本接受 1–6 个角色 id，但游戏里一队只有 5 人：上限改为 **5 个不重复 id**
  （去重后才计数量，部分阵容仍合法），并同步工具描述、README 与威胁模型。
- `arena_lookup` 读取的是**上游真实结构**，此前按臆想的扁平行解析（`defense`/`attack`/`views`），
  接真实服务时恒返回 0 支队伍，而 fixture 测试全绿。现在会向下走到第一个队伍列表，
  从 `[{id, star, equip}]` 里取角色 id，票数用 `up`/`down`，不再编造播放量。
  回归样本：`tests/fixtures/arena_payload.json`（真实返回截取）。
- `scripts/fake_arena.py` 的响应结构同步为真实形状，避免替身把错误结构“验成正确”。

### Added

- `scripts/port_tags.py`：从助手的 `tagging.py` 导出词典表（找不到源文件就报错，不写空表）。
- `docs/PORTING.md`：与助手实现的逐项对照（原样搬 / 简化 / 有意改掉 / 没搬）。
- README 增「与助手词典的关系」入口与 **DSH 的 MCP 配置示例**（`dsh-mcp-client` 装配片段）。
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
