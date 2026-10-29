# MCP 规范符合性

基线：MCP 修订版 **2025-11-25**（下面第 1 条握手时实测协商到的值），SDK 为 `mcp` 1.x（`pyproject.toml` 里钉了 `<2`）。

判定原则：只写**能当场复验**的项。每一条的"证据"列都可以用 `python scripts/mcp_smoke.py` 或
`scripts/live_check.py` 复现；需要看原始报文时用 `npx @modelcontextprotocol/inspector`。

## 1. 已符合

| 规范项 | 状态 | 证据 |
| --- | --- | --- |
| `initialize` 与版本协商 | 已符合 | 握手返回 `protocolVersion = 2025-11-25` |
| `serverInfo` 的 name / version | 已符合 | `aninest-mcp` / `0.4.0`（`src/aninest/version.py`，并在 `server.py` 里覆盖了 SDK 默认值） |
| `tools/list` 与 `inputSchema` | 已符合 | 10 个工具，schema 由类型注解 + docstring 生成（`tests/test_server_contract.py` 断言每个工具都带 schema，且与 `server.EXPECTED_TOOLS` 一致） |
| `tools/call` 的 `isError` 语义 | 已符合 | 业务错误抛 `ToolError` → 客户端收到 `isError: true`；记忆库不存在时实测如此 |
| `structuredContent` | 已符合 | 每次调用同时给文本 JSON 与结构化结果（`test_server_contract.py` 第二组用例） |
| 工具 `title`（人类可读名） | 已符合 | `Illustration search` / `Character lookup` / `Portrait identification` / `Arena lineup lookup` / `Memory search` / `Memory store stats` / `Service health` / `Character name match` / `Character update` / `Character name correction` |
| 工具 `annotations`（只读组） | 已符合 | 原有七个工具 `readOnlyHint=true`、`destructiveHint=false`；`art_search`、`arena_lookup` 额外 `openWorldHint=true`（结果依赖外部系统），本地类（角色表、头像包）不开 `openWorldHint`，记忆类 `idempotentHint=true` |
| 工具 `annotations`（本地写组） | 已符合 | `character_update` / `character_correct` 用 `WRITE_LOCAL = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)`：写的是本地覆盖层，不联网、不删数据、重复调用不产生重复记录；`character_match` 仍属只读组。`tests/test_server_contract.py` 逐个工具断言这三个 flag |
| `resources/list` + `resources/read` | 已符合 | `aninest://memory/stats` |
| `prompts/list` + `prompts/get` | 已符合 | `find_illustration` |
| 服务级 `instructions` | 已符合 | 启动时下发给宿主，说明"先调 `service_health`" |
| stdio 传输 | 已符合 | 默认 `python -m aninest` / `aninest-mcp` |
| Streamable HTTP 传输 | 已符合 | `ANINEST_MCP_TRANSPORT=streamable-http` |
| HTTP 的 DNS-rebinding 防护 | 已符合 | 绑定 `127.0.0.1` 时 SDK 自动启用 `allowed_hosts` / `allowed_origins` 限定本机（`config.py` 默认即 `127.0.0.1`） |
| 凭据处理 | 已符合 | 不读密钥文件，全部选项走环境变量；记忆库以 `mode=ro` 只读打开 |

信任边界：写入范围只有 `ANINEST_PCR_OVERLAY`（默认 `~/.aninest/pcr_overlay.json`）。随包分发的
`src/aninest/data/pcr_chars.json`（升级时整个替换）和记忆库（`mode=ro` 打开）都不在任何写路径上；
覆盖层是临时文件 + 原子替换，最坏情况是这份 JSON 写坏——`load_overlay()` 会把它当成空覆盖层忽略，
服务照常启动，删掉文件就回到出厂状态。宿主可以凭 `readOnlyHint` 对只读工具免确认，把两个写工具留一次用户确认。

## 2. 有意不做

| 项 | 原因 |
| --- | --- |
| 提交官方 Registry | Registry 要求"公开可安装"（PyPI / npm / 公开 OCI 镜像）。本项目**不发 PyPI**（作者的选择），所以不提交；等发了包再加 `server.json` 即可。 |
| OAuth / 令牌鉴权 | 本地 stdio 为主，HTTP 只绑 `127.0.0.1`，没有暴露到局域网。 |
| `resources/subscribe`、进度通知、日志通知 | 当前都是"一次请求一次响应"的短调用，用不上；等有长任务再加。 |
| 分页（`cursor`） | 结果集都远小于 100，未触发分页。 |

## 3. 还可以再加固的三件事（按性价比排序）

1. **把返回值改成 dict 并显式声明 `outputSchema`**：现在 `structuredContent` 已可用，但没有对外声明 schema，客户端无法做严格校验。改动量小（`server.py` 里加 `structured_output=True`，工具返回 dict 而不是 `json.dumps` 字符串）。
2. **发布到 PyPI + 提交 Registry**：`uvx aninest-mcp` 一行就能跑，也能被 Registry 搜到（名字 `io.github.moriruruka/aninest-mcp`）。
3. **`resources/subscribe` 用于记忆库热更新**：宿主可订阅 `aninest://memory/stats`，记忆写入时收到变更通知。

## 4. 第三方接入时怎么快速自检

```bash
python scripts/mcp_smoke.py                 # 真实握手 + tools/list
python scripts/mcp_smoke.py --call service_health
python scripts/live_check.py                # 十个工具逐个调真服务（两个写工具写到临时覆盖层，识图是条件项）
python -m unittest discover -s tests        # 契约与纯函数
```

这些脚本不依赖任何客户端，退出码 0 才算过。
