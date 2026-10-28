# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 与 [语义化版本](https://semver.org/lang/zh-CN/)。

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
- 文档：README、`docs/DECISIONS.md`（设计取舍）、`docs/PRIVACY.md`（开源自查清单）、
  `docs/THREAT_MODEL.md`（资产/信任边界/出站能力/已知缺口）、CONTRIBUTING。

### Known limitations

- 依赖锁定 `mcp>=1.20,<2`：2.x 把 `FastMCP` 改名为 `MCPServer`，迁移需同步改工具注册与 `ToolError` 导入。
- 只支持 Gelbooru 风格 JSON API；Moebooru（konachan / yande.re）适配在 Roadmap。
- `arena_lookup` 依赖本机浏览器服务的 HTTP 契约，不内置登录流程。
- `memory_search` 未使用 embedding；规模上万条后建议替换打分函数。
- HTTP/SSE 模式默认无鉴权，只监听 `127.0.0.1`。
