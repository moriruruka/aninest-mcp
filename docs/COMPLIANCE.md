# MCP 规范符合性

基线：MCP 修订版 **2025-11-25**（下面第 1 条握手时实测协商到的值），SDK 为 `mcp` 1.x（`pyproject.toml` 里钉了 `<2`）。

判定原则：只写**能当场复验**的项。每一条的"证据"列都可以用 `python scripts/mcp_smoke.py` 或
`scripts/live_check.py` 复现；需要看原始报文时用 `npx @modelcontextprotocol/inspector`。

## 1. 已符合

| 规范项 | 状态 | 证据 |
| --- | --- | --- |
| `initialize` 与版本协商 | 已符合 | 握手返回 `protocolVersion = 2025-11-25` |
| `serverInfo` 的 name / version | 已符合 | `aninest-mcp` / `0.2.0`（`src/aninest/version.py`，并在 `server.py` 里覆盖了 SDK 默认值） |
| `tools/list` 与 `inputSchema` | 已符合 | 5 个工具，schema 由类型注解 + docstring 生成（`tests/test_server_contract.py` 断言每个工具都带 schema） |
| `tools/call` 的 `isError` 语义 | 已符合 | 业务错误抛 `ToolError` → 客户端收到 `isError: true`；记忆库不存在时实测如此 |
| `structuredContent` | 已符合 | 每次调用同时给文本 JSON 与结构化结果（`test_server_contract.py` 第二组用例） |
| 工具 `title`（人类可读名） | 已符合 | `Illustration search` / `Arena lineup lookup` / `Memory search` / `Memory store stats` / `Service health` |
| 工具 `annotations` | 已符合 | 5 个工具全部 `readOnlyHint=true`、`destructiveHint=false`；`art_search`、`arena_lookup` 额外 `openWorldHint=true`（结果依赖外部系统），记忆类 `idempotentHint=true` |
| `resources/list` + `resources/read` | 已符合 | `aninest://memory/stats` |
| `prompts/list` + `prompts/get` | 已符合 | `find_illustration` |
| 服务级 `instructions` | 已符合 | 启动时下发给宿主，说明"先调 `service_health`" |
| stdio 传输 | 已符合 | 默认 `python -m aninest` / `aninest-mcp` |
| Streamable HTTP 传输 | 已符合 | `ANINEST_MCP_TRANSPORT=streamable-http` |
| HTTP 的 DNS-rebinding 防护 | 已符合 | 绑定 `127.0.0.1` 时 SDK 自动启用 `allowed_hosts` / `allowed_origins` 限定本机（`config.py` 默认即 `127.0.0.1`） |
| 凭据处理 | 已符合 | 不读密钥文件，全部选项走环境变量；记忆库以 `mode=ro` 只读打开 |

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
python scripts/live_check.py                # 五个工具逐个调真服务
python -m unittest discover -s tests        # 契约与纯函数
```

这些脚本不依赖任何客户端，退出码 0 才算过。
