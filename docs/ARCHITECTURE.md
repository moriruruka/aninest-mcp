# 代码结构与改动指引

这份文档说明仓库里每个文件负责什么、改动时会牵连到哪些地方，以及当前已经验证到什么程度。
面向两类读者：想读懂实现的读者，和准备提 PR 的贡献者。

## 目录结构

```
aninest-mcp/
├── src/aninest/            # 包本体（hatchling 布局）
│   ├── config.py           # 环境变量 → Settings
│   ├── version.py          # 单一版本号来源
│   ├── tagging.py          # 中文口语 → booru tag 编译器（纯函数）
│   ├── server.py           # FastMCP 注册：5 工具 + 1 resource + 1 prompt
│   └── tools/              # 五个工具的实现（每个文件一个领域）
├── tests/                  # 63 个 unittest 用例，无需安装即可运行
├── eval/                   # 26 条 golden case + 离线/联网评测器
├── scripts/                # 可复现替身与 MCP 自检
├── demo/                   # 最小宿主 + 一键 story（端到端演示）
├── examples/               # 客户端接入样例
└── docs/                   # 设计取舍、威胁模型、数据边界、本文件
```

## 模块职责

| 文件 | 作用 | 改动时注意 |
| --- | --- | --- |
| `src/aninest/config.py` | 把环境变量解析成 `Settings` | 五个本地端口（6185/6199/9880/6190/6191）是通用占位，改端口需同步 `docs/` 与 README 配置表 |
| `src/aninest/tagging.py` | 中文 → tag 编译（规则表 + 优先级替换） | `BLOCKED_TAGS` / `BLOCKED_CN` 是硬编码黑名单；增删词条要同步 `tests/test_tagging.py` 与 `eval/art_cases.json` |
| `src/aninest/server.py` | 注册工具、resource、prompt | docstring 会成为宿主模型看到的工具描述，改描述等于改调用行为 |
| `src/aninest/version.py` | 版本号唯一来源 | 发版时改这里，`pyproject.toml` 与 `CHANGELOG.md` 同步 |
| `src/aninest/tools/art.py` | 检索、结果整形、降级阶梯、分级归一化 | `RATING_ALIASES` 决定放行范围（只放行 safe）；`build_attempts` 决定最多请求几次 |
| `src/aninest/tools/arena.py` | 阵容 id 校验 + payload 扁平化 | 只依赖本地服务 `POST /search` 契约，不携带任何凭证 |
| `src/aninest/tools/memory.py` | 只读 SQLite 检索与统计 | 表名/字段名需与目标库一致（`memories`、`pending_corrections`）；连接一律 `mode=ro` |
| `src/aninest/tools/health.py` | TCP 探活 | 端口表在 `config.SERVICES`；它是 liveness，不是 readiness |

## 数据流

```
宿主模型 ──tools/call──► server.py 分发 ──► tools/*.py
                                            ├─ art_search      ──► 图站 HTTP API（出网）
                                            ├─ arena_lookup    ──► 本机服务 POST /search
                                            ├─ memory_*        ──► 本地 SQLite（只读）
                                            └─ service_health  ──► 5 个固定端口的 TCP connect
```

三条约束贯穿全部工具：

1. **工具参数里没有 URL**：出站地址只来自环境变量，模型无法指定目标（详见 `docs/THREAT_MODEL.md` 第 3 节）。
2. **失败要显式**：网络错误、非 JSON、空结果分别抛 `ToolError`，不返回示例数据。
3. **降级要留痕**：放宽条件后返回 `relaxed` / `attempt`，让宿主知道结果打了折扣。

## 测试与评测

| 文件 | 覆盖 | 说明 |
| --- | --- | --- |
| `tests/test_tagging.py` | 编译器 12 例 | 含黑名单拦截；调整词表需同步期望值 |
| `tests/test_art_shape.py` | 结果整形 11 例 | 含 `s`/`e` 分级别名归一化 |
| `tests/test_arena.py` | id 校验与扁平化 11 例 | 全部使用假 id |
| `tests/test_memory.py` | 检索/统计 12 例 | 临时 SQLite，自建表结构 |
| `tests/test_health.py` | 探活 4 例 | 只连 loopback |
| `eval/art_cases.json` | 26 条 golden case | 6 条为「应被拒绝」用例 |
| `eval/run_eval.py` | 离线/联网评测 | 联网模式会真实请求图站；CI 只跑离线 |

## 验证记录（本机实测）

- ✅ `ruff check src tests eval scripts` → All checks passed
- ✅ `python -m unittest discover -s tests` → 65 tests OK
- ✅ `python eval/run_eval.py` → 26/26，recall / precision / 字段准确率均 1.000
- ✅ `python eval/run_eval.py --network --online-cases 18` → 18/18，p50 1.67 s，p95 1.99 s
- ✅ `python scripts/mcp_smoke.py --call service_health` → 5 个工具 + prompt 可见，工具返回 JSON
- ✅ `python scripts/mcp_smoke.py --call art_search` → 返回真实图片 URL（分级 safe、方向 portrait）
- ✅ `python scripts/make_demo_db.py` + `ANINEST_MEMORY_DB=… --call memory_stats` → rows 5 / global 3 / session 2
- ✅ `python scripts/fake_arena.py` + `ANINEST_ARENA_URL=127.0.0.1:6192 --call arena_lookup` → 返回 2 支假队伍
- ✅ 干净 venv 安装：`pip install <repo>` → `aninest-mcp 0.1.0`，console script 与 `import aninest` 均正常
- ✅ Docker 镜像（本机 Docker 29.9.2）：`docker build` 成功（252 MB）→ 以 `uid=10001` 非 root 运行 →
  `HEALTHCHECK` 转 healthy → `initialize` 返回 `serverInfo.version=0.1.0` → `tools/list` 返回 5 个工具
- ℹ️ 构建机器所在网络无法直连 Docker Hub，镜像构建使用了 `--build-arg PYTHON_IMAGE=docker.m.daocloud.io/library/python:3.12-slim`；
  CI 使用默认的 `python:3.12-slim`
