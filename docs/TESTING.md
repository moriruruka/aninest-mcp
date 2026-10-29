# 怎么验证这个仓库

这个仓库的“能用”分五层，每层证明的东西不一样。想快速判断，只看第 3 节的三行；想彻底确认，从上往下走一遍，十分钟内做完。

| 层 | 证明什么 | 需要什么 | 耗时 |
| --- | --- | --- | --- |
| 1 静态检查 | 代码能过 lint，没有明显的未用导入/未定义名 | Python | 3 秒 |
| 2 单元测试 | 每个纯函数在**固定输入**下行为正确 | Python | ≈8 秒 |
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
Ran 162 tests in 7.5s
OK (skipped=11)
```

`skipped=11` 是没装 `[vision]` 时的正常现象：`test_portrait.py` 那 11 个用例需要 numpy + Pillow，
装过 `pip install -e ".[vision]"` 之后它们会真的跑起来。

这 162 个用例里，绝大多数只用 fixtures，不联网、不需要服务。它们覆盖：

- `test_tagging.py`：中文词 → tag 的别名表、黑名单、方向/尺寸/张数解析、负向 tag
- `test_art_shape.py`：把图站返回的原始行规整成结果、分级归一（`s`/`safe`/`g`…）、降级阶梯
- `test_arena.py`：阵容 id 校验（1–5 个、去重、范围）、**真实返回结构的解析**（`data.data.result[].def/atk` 对象、`up`/`down`）
- `test_arena_names.py`：按名字查作业——用 stdlib 起一个假作业服务，检查**实际发出去的 `def`**，以及 `exclude` / `replace` / 部分认不出
- `test_pcr_chars.py`：角色表规模与唯一性、别名与四位 uid / 六位 id 解析、无分隔连写切分、排除替换，以及「布丁和克总」能拆、「日和」不被拆
- `test_pcr_overlay.py`：本地覆盖层 20 例——新建角色、扩别名、幂等（同样的别名加两次不重复）、删别名后查不到、包内 `pcr_chars.json` 一个字节都不改、覆盖层写成坏 JSON 也不影响查询、原子写（不留 `.tmp`、文件以换行结尾）、更正入日志且带时间戳、`character_match` 的分数与 `matched_on`（精确 / 日文名 / 手误 fuzzy / 阈值过滤 / `top_k` / 空 query 报错）
- `test_portrait.py`：临时目录里画合成头像跑 NCC（原图 / 裸字节 / base64 / 低于 `min_score` 判未知）；没装 `[vision]` 时整体跳过
- `test_memory.py`：只读打开、打分、统计
- `test_health.py`：端口探活的成功/失败分支
- `test_demo_router.py`：host 的路由与措辞（不需要真的连 server）
- `test_server_contract.py`：MCP 契约——工具清单（10 个，并与 `server.EXPECTED_TOOLS` 对表）、schema、title、annotations、resource、prompt

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

它会自动起一个示例记忆库和一个假作业服务，然后用 stdio 真的连上 server，把五句话依次变成工具调用：
探活 → 回忆 → 按名字查作业 → 换人再查 → 认角色。期望看到（节选）：

```text
[host] 已连接 10 个工具：art_search、character_lookup、portrait_identify、arena_lookup、memory_search、memory_stats、service_health、character_match、character_update、character_correct

你   > 布丁、克总、真琴、纺希、莉莎这个防守的作业
host > 按 1号位 宫子 / 2号位 克莉丝提娜 / 3号位 真琴 / 4号位 纺希 / 5号位 莉莎 查：找到 2 支队伍，最热门的是 优衣 / 香织(夏日) / 绫音 / 日和 / 矛依未(新年)（赞 1、踩 0）。

你   > 布丁和克总分别是哪个角色
host > 对上 2 个：宫子（100701）、克莉丝提娜（107101）。
```

想看它到底调了哪个工具、参数是什么，加 `--verbose`（或设 `ANINEST_DEMO_VERBOSE=1`），
每步会多出 `host > 调 arena_lookup({"defense": [...], "limit": 3})` 和一段原始 JSON。

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

它用真实 MCP stdio 启动 server，逐个调十个工具，打印一行结果；**只有全部通过时退出码才是 0**。

在本机（五个服务都在跑、记忆库 37 条）的实测输出：

```text
tools (10): arena_lookup, art_search, character_correct, character_lookup, character_match, character_update, memory_search, memory_stats, portrait_identify, service_health

[ ok ] service_health  5/5 up
[ ok ] memory_stats    rows=37 global=5 session=32
[ ok ] memory_search   scanned=37 matched=2
[ ok ] character_lookup matches=2 宫子(100701)、克莉丝提娜(107101)
[ ok ] arena_lookup    found=10 defense=[100201, 110501, 102301, 100101, 114701] up=1
[ ok ] character_match 100701 宫子 score=0.5 via=fuzzy_name
[ ok ] character_update created 199901 检查用角色 aliases=1 overlay=<temp>\pcr_overlay.json
[ ok ] character_correct alias_added 宫紫 -> 宫子
[ ok ] art_search      1 image(s) 2048x1050 rating=safe
[ ok ] portrait_identify 1 portrait(s) best=日和 score=1.0

all checks passed
```

常用参数：

```bash
python scripts/live_check.py --ids 100101 100201          # 用 id 指定要查的防守阵容
python scripts/live_check.py --lineup 布丁 克总 真琴       # 用角色名查作业（更容易试）
python scripts/live_check.py --skip-network               # 没网时跳过 art_search
python scripts/live_check.py --avatars demo_avatars       # 头像包就位时顺带验 portrait_identify
```

`portrait_identify` 是**条件项**：只有设了 `ANINEST_PCR_AVATARS`（`--avatars` 等同于替你设）且目录里有图时才会出现，
否则这一项直接缺席，其它项照跑。

两个写工具（`character_update` / `character_correct`）跑在**临时覆盖层**上：脚本把 `ANINEST_PCR_OVERLAY`
指到一个 `TemporaryDirectory`，跑完即弃，所以一次联调不会往你真实的 `~/.aninest/pcr_overlay.json` 里塞测试角色。

环境变量（任选，缺项就用默认值）：

| 变量 | 默认 | 作用 |
| --- | --- | --- |
| `ANINEST_ARENA_URL` | `http://127.0.0.1:6191` | 作业服务地址，需能答 `POST /search` |
| `ANINEST_MEMORY_DB` | `~/.aninest/memory.db` | 记忆库路径（只读打开） |
| `ANINEST_BOORU_URL` | `https://safebooru.org/index.php` | 图站 |
| `ANINEST_PROBE_HOST` | `127.0.0.1` | `service_health` 探的地址 |
| `ANINEST_PCR_AVATARS` | 空 | 头像包目录；配了才会查 `portrait_identify` |
| `ANINEST_PCR_OVERLAY` | `~/.aninest/pcr_overlay.json` | 角色覆盖层；`live_check.py` 会临时改成一次性目录，不用你管 |

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

浏览器里会列出十个工具，逐个点开填参数即可。或者把 server 加进你惯用的客户端（Claude Desktop / Cursor / Cline 等），配置形状都一样：

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
| 4 替身演示 | 你的真实服务行为；替身脚本按捕获样本编写 |
| 5 真机联调 | 图站/作业网改版后的长期稳定；跨机器环境差异 |

所以第 2 层和第 5 层必须**同时**存在：一个防回归，一个防“上游变了而自检仍是绿的”。`tests/fixtures/arena_payload.json` 就是从真实返回里截的样本，让第 2 层能盯住上游结构。

---

## 8. 现在还没覆盖的（诚实清单）

- **图站改版**：`art_search` 只对 safebooru 的 dapi 结构做过适配；换站要改 `tools/art.py` 的字段映射。
- **作业服务实现**：仓库不含登录态的浏览器服务，只约定 `POST /search` 的入参出参；别人的实现若字段不同，要改 `summarise`。
- **记忆库 schema**：只读 `memories` 表，字段缺失会报错而不是降级。
- **识图准确率**：`portrait_identify` 只在合成头像和本机头像包上验过，没有公开的准确率基准；
  换素材、换分辨率、换截图来源都值得自己重测一遍。
- **并发/长跑**：没有压力测试，也没有长连接下的内存曲线。
- **Windows 之外的路径**：路径处理用的是 `pathlib`，但没有在 macOS 上实测。

这几条都写在 issue 里比写在这里更有用——如果你 fork 后补上了，欢迎 PR。
