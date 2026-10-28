# 接入方式速查

## 1. stdio（桌面客户端最常用）

宿主负责拉起进程，通过 stdin/stdout 收发 JSON-RPC。

```json
{
  "mcpServers": {
    "aninest": {
      "command": "aninest-mcp",
      "env": { "ANINEST_MEMORY_DB": "C:/Users/you/.aninest/memory.db" }
    }
  }
}
```

- Claude Desktop：配置文件名 `claude_desktop_config.json`（见同目录示例）。
- DSH 等支持 MCP 的宿主：把 `aninest` 加进它的 MCP 服务器列表；命令用 `aninest-mcp` 或
  `python -m aninest`，并设置 `PYTHONPATH` 指向 `src` 或先用 `pip install -e .` 安装。
- 自己写客户端：`mcp` 包提供 `stdio_client` + `ClientSession`，参考 `scripts/mcp_smoke.py`。

## 2. Streamable HTTP（跨机器 / 容器）

```bash
ANINEST_MCP_TRANSPORT=streamable-http ANINEST_MCP_PORT=8765 aninest-mcp
```

客户端连接 `http://127.0.0.1:8765/mcp`。Docker 场景：

```yaml
services:
  aninest-mcp:
    build: .
    ports: ["127.0.0.1:8765:8765"]
    environment:
      ANINEST_MCP_TRANSPORT: streamable-http
      ANINEST_ARENA_URL: http://host.docker.internal:6191
```

> 当前 HTTP 模式没有鉴权，默认只监听 127.0.0.1。要暴露到网络前请加反向代理与鉴权。

## 3. SSE（旧版客户端兼容）

```bash
ANINEST_MCP_TRANSPORT=sse ANINEST_MCP_PORT=8765 aninest-mcp
```

## 4. 不接客户端也能验证

```bash
python scripts/mcp_smoke.py                                     # 列工具 + 调 service_health
python scripts/mcp_smoke.py --call memory_stats
python scripts/mcp_smoke.py --call art_search --args-file args.json
```

`args.json`：

```json
{ "query": "初音未来 泳装 竖图", "count": 1, "size": "compressed" }
```
