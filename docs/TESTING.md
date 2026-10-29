# 怎么验证这个仓库

这个仓库的“能用”分五层，每层证明的东西不一样。想快速判断，只看第 3 节的三行；想彻底确认，从上往下走一遍，十分钟内做完。

| 层 | 证明什么 | 需要什么 | 耗时 |
| --- | --- | --- | --- |
| 1 静态检查 | 代码能过 lint，没有明显的未用导入/未定义名 | Python | 3 秒 |
| 2 单元测试 | 每个纯函数在**固定输入**下行为正确 | Python | 1 秒 |
| 3 离线评测 | 中文需求 → tag 的规则覆盖了 26 个真实用例 | Python | 2 秒 |
| 4 替身演示 | server + host + 数据链路能跑通，且是**真的 MCP 协议** | Python | 20 秒 |
| 5 真机联调 | 接**你实际在跑的服务**是否仍然工作 | 你的服务在跑 | 30 秒 |

第 1–4 层在任何机器上都能跑，第 5 层依赖你本机的五个端口。

---

## 0. 准备

```bash
git clone https://github.com/moriruruka/aninest-mcp
cd aninest-mcp
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -e .
```

`pip install -e .` 之后 `python -m aninest` 与 `aninest-mcp` 两个入口都可用。

下面的命令都在仓库根目录执行。Windows 上如果中文输出报编码错，先设一次：

```powershell
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
```

---

## 1. 静态检查

```bash
ruff check src tests eval scripts demo
```

期望输出：

```text
All checks passed!
```

失败时它会直接指出文件:行号:规则，`ruff check --fix` 能自动修一部分。

---

## 2. 单元测试

```bash
python -m unittest discover -s tests
```

期望输出（数字会随用例增长）：

```text
Ran 67 tests in 0.588s
OK
```

这 67 个用例全部只用 fixtures，不联网、不需要服务。它们覆盖：

- `test_tagging.py`：中文词 → tag 的别名表、黑名单、方向/尺寸/张数解析、负向 tag
- `test_art_shape.py`：把图站返回的原始行规整成结果、分级归一（`s`/`safe`/`g`…）、降级阶梯
- `test_arena.py`：阵容 id 校验（1–5 个、去重、范围）、**真实返回结构的解析**（`data.data.result[].def/atk` 对象、`up`/`down`）
- `test_memory.py`：只读打开、打分、统计
- `test_health.py`：端口探活的成功/失败分支
- `test_demo_router.py`：host 的路由与措辞（不需要真的连 server）

想只跑一个文件：

```bash
python -m unittest tests.test_arena -v
```

---

## 3. 离线评测（看“翻 tag”的质量）

```bash
python eval/run_eval.py
```

期望输出：

```text
cases=26 passed=26 recall=1.0 precision=1.0 field_accuracy=1.0
```

它读 `eval/art_cases.json` 里 26 条中文需求（含 6 条**应当被拒绝**的），逐条比对：

- `recall`：该出现的 tag 是否都在
- `precision`：有没有多出不该有的 tag
- `field_accuracy`：张数/方向/尺寸/分级解析是否正确

加 `--network` 会真的去 safebooru 抓图，报告成功率与延迟：

```bash
python eval/run_eval.py --network
python eval/run_eval.py --network --json out.json   # 落盘，便于对比两次改动
```

---

## 4. 替身演示（不需要联网，也不需要你的服务）

```bash
python demo/story.py
```

它会自动起一个示例记忆库和一个假作业服务，然后用 stdio 真的连上 server，演三段对话：探活 → 回忆 → 查作业。期望看到（节选）：

```text
[host] 已连接 5 个工具：art_search、arena_lookup、memory_search、memory_stats、service_health

你   > 查一下 100141 100241 100341 100441 100541 的作业
host > 调 arena_lookup({"def_ids": [100141, 100241, 100341, 100441, 100541], "limit": 3})
mcp  > { "found": 2, "teams": [{ "defense": [100201, 110501, 102301, 100101, 114701], "upvotes": 1 }] }
host > 找到 2 支队伍，最热门的是：100201 / 110501 / 102301 / 100101 / 114701（赞 1、踩 0）。
```

两个步骤也可以单独看：

```bash
python scripts/make_demo_db.py demo_memory.db      # 造示例库
python scripts/fake_arena.py --port 6192           # 起假作业服务（另开一个窗口）
ANINEST_ARENA_URL=http://127.0.0.1:6192 python scripts/mcp_smoke.py --call arena_lookup
```

> `demo/story.py` 用的是替身，它证明“协议与数据链路通”，**不**证明“接你的服务也通”。后者是下一节。

---

## 5. 真机联调（推荐你自己跑一次）

```bash
python scripts/live_check.py
```

它用真实 MCP stdio 启动 server，逐个调五个工具，打印一行结果；**只有全部通过时退出码才是 0**。

在本机（五个服务都在跑、记忆库 36 条）的实测输出：

```text
tools (5): arena_lookup, art_search, memory_search, memory_stats, service_health

[ ok ] service_health  5/5 up
[ ok ] memory_stats    rows=36 global=5 session=31
[ ok ] memory_search   scanned=36 matched=2
[ ok ] arena_lookup    found=10 defense=[100201, 110501, 102301, 100101, 114701] up=1
[ ok ] art_search      1 image(s) 665x957 rating=safe

all checks passed
```

常用参数：

```bash
python scripts/live_check.py --ids 100101 100201     # 指定要查的防守阵容
python scripts/live_check.py --skip-network          # 没网时跳过 art_search
```

环境变量（任选，缺项就用默认值）：

| 变量 | 默认 | 作用 |
| --- | --- | --- |
| `ANINEST_ARENA_URL` | `http://127.0.0.1:6191` | 作业服务地址，需能答 `POST /search` |
| `ANINEST_MEMORY_DB` | `~/.aninest/memory.db` | 记忆库路径（只读打开） |
| `ANINEST_BOORU_URL` | `https://safebooru.org/index.php` | 图站 |
| `ANINEST_PROBE_HOST` | `127.0.0.1` | `service_health` 探的地址 |

失败时的读法：

| 输出 | 含义 | 怎么办 |
| --- | --- | --- |
| `[FAIL] service_health 3/5 up, down: tts, stt` | 服务没起 | 先启动对应服务；`--skip-network` 不影响这一项 |
| `[FAIL] memory_stats missing database` | 库路径不对 | 设 `ANINEST_MEMORY_DB` 指向真实 `.db` |
| `[FAIL] arena_lookup arena browser service is not running …` | 6191 没起 | 起浏览器服务；或指向你自己的实现 |
| `[FAIL] art_search …` 且提示超时 | 图站不通 | 换 `ANINEST_BOORU_URL`，或用 `--skip-network` |

---

## 6. 接到真实客户端（最后一层，可选）

不用写代码，用官方 Inspector 点一点：

```bash
npx @modelcontextprotocol/inspector python -m aninest
```

浏览器里会列出五个工具，逐个点开填参数即可。或者把 server 加进你惯用的客户端（Claude Desktop / Cursor / Cline 等），配置形状都一样：

```json
{
  "mcpServers": {
    "aninest": {
      "command": "python",
      "args": ["-m", "aninest"],
      "env": { "ANINEST_MEMORY_DB": "/path/to/memory.db" }
    }
  }
}
```

接上以后用三句自然语言验收，看它有没有选对工具：

1. “本机那几个服务还活着吗” → 应调 `service_health`
2. “我之前是不是说过喜欢竖构图的插画” → 应调 `memory_search`
3. “帮我找两张初音未来泳装的图” → 应调 `art_search`

---

## 7. 每一层不能证明什么（重要）

| 层 | 不能证明 |
| --- | --- |
| 1 lint | 逻辑正确性 |
| 2 单测 | 上游返回结构没变——**这正是上一版漏掉 `data.data.result` 的原因** |
| 3 离线评测 | 图站此刻可用、返回字段与假设一致 |
| 4 替身演示 | 你的真实服务行为；替身是我们按捕获样本写的 |
| 5 真机联调 | 图站/作业网改版后的长期稳定；跨机器环境差异 |

所以第 2 层和第 5 层必须**同时**存在：一个防回归，一个防“上游变了我们还以为没事”。`tests/fixtures/arena_payload.json` 就是从真实返回里截的样本，让第 2 层能盯住上游结构。

---

## 8. 现在还没覆盖的（诚实清单）

- **图站改版**：`art_search` 只对 safebooru 的 dapi 结构做过适配；换站要改 `tools/art.py` 的字段映射。
- **作业服务实现**：仓库不含登录态的浏览器服务，只约定 `POST /search` 的入参出参；别人的实现若字段不同，要改 `summarise`。
- **记忆库 schema**：只读 `memories` 表，字段缺失会报错而不是降级。
- **并发/长跑**：没有压力测试，也没有长连接下的内存曲线。
- **Windows 之外的路径**：路径处理用的是 `pathlib`，但没有在 macOS 上实测。

这几条都写在 issue 里比写在这里更有用——如果你 fork 后补上了，欢迎 PR。
