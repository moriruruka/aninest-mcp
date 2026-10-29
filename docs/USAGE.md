# 使用说明

这份文档面向"已经装好了、想知道怎么用"的人。安装见 [INSTALL.md](INSTALL.md)。

AniNest 不是聊天机器人，它是一层**能力**。真正和你对话的是宿主（Claude Desktop、DSH、编辑器插件等），
宿主在需要的时候调用这五个工具。所以"怎么用"其实是两件事：**你会怎么问**，以及**工具会返回什么**。

---

## 1. 五个工具能做什么

| 工具 | 一句话 | 典型问法 |
| --- | --- | --- |
| `art_search` | 把一句中文描述变成图站能懂的标签，再取回图片链接 | "来两张初音未来泳装的竖图" |
| `arena_lookup` | 拿阵容去查竞技场作业（别人怎么防守/进攻） | "这队作业查一下：100141 100241 100341 100441 100541" |
| `memory_search` | 在助手自己的记忆库里检索（只读） | "上次说的那个配色偏好还记得吗" |
| `memory_stats` | 记忆库有多大、多少条、按范围分布 | "你的记忆存了多少了" |
| `service_health` | 本机那几个服务此刻在不在 | "服务都活着吗" |

顺序建议：**先 `service_health`，再调其它**。这样"服务没起"不会被误当成"你参数给错了"。

---

## 2. `art_search`：中文 → 标签 → 图片

### 你会怎么问

- 来两张初音未来泳装的竖图
- 找张樱花场景的横图，要原图
- 画个银发红眼的女孩子（不要血腥）
- 来点赛博朋克风的城市夜景

### 参数

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `query` | 字符串 | 随便说，中文英文都行。**张数、原图/压缩、横竖方，都可以直接写在里面**，工具会自己解析 |
| `count` | 1–10 | 想要几张（默认 1），也会被 `query` 里的"两张/3 张"覆盖 |
| `size` | `compressed` / `original` | 压缩图省流量（默认），原图更清楚 |
| `orientation` | `landscape` / `portrait` / `square` | 可选，横 / 竖 / 方 |
| `extra_tags` | 字符串数组 | 追加规范 tag（英文、下划线），比如 `["thighhighs"]` |
| `negative` | 字符串数组 | 排除 tag，比如 `["text", "watermark"]` |

### 它会返回什么

```json
{
  "query": "初音未来 泳装 竖图",
  "tags": ["hatsune_miku", "swimsuit"],
  "tags_used": "hatsune_miku swimsuit order:score",
  "negative": [],
  "unknown_words": [],
  "size": "compressed",
  "orientation": "portrait",
  "relaxed": false,
  "attempt": 1,
  "count": 2,
  "results": [
    { "image_url": "https://…jpg", "width": 1200, "height": 1800, "rating": "safe", "tags": "hatsune_miku swimsuit …" }
  ]
}
```

几个值得注意的字段：

- `unknown_words`：模型没认出、也没法翻译成 tag 的词。**空数组不代表翻得完美**，只代表每个词都找到了落点。
- `relaxed` / `attempt`：命中时用的是第几档条件。`relaxed: true` 表示"严格条件没结果，放宽后才找到"——
  这时结果和你的要求可能有偏差，值得让宿主说明一句。
- 只返回 `rating: safe` 的结果，这是硬编码，没有开关。

### 它怎么工作（三句话）

1. **拆需求**：把"两张 / 原图 / 竖图"从句子里剥出来，剩下的当描述。
2. **翻成标签**：中文词典（171 条别名）+ 角色名表（56 个）+ 站点真实 tag 表，翻成 `hatsune_miku` 这种下划线写法。
3. **检索并放宽**：先按全部条件查；空就依次去掉方向约束、逐个减少 tag——最多几档，避免"明明有图却回没有"。

### 常见情况

| 你看到的 | 意思 | 怎么办 |
| --- | --- | --- |
| `no image matched after N attempts` | 图站真的没有这组组合（或站点暂时连不上） | 减一个限定词再试，比如去掉"竖图" |
| `no usable tag was produced` | 整句话没翻出任何 tag | 换成"角色名 + 一两个名词"的说法 |
| 报错里提到 `blocked` | 命中了内置的敏感词表 | 换描述；这是安全边界，不做绕过 |
| 结果长得不像你要的 | 走了降级档（`relaxed: true`） | 让宿主说得更具体，或直接给 `extra_tags` |

---

## 3. `arena_lookup`：查作业

### 你会怎么问

- 这队作业查一下：100141 100241 100341 100441 100541
- 帮我看看这个防守阵容别人怎么打

**位置上要注意**：公主连结的编队从右往左是「前卫 → 中卫 → 后卫」，
所以 1 号位是最右边那个。工具本身只吃 id 数组，顺序就是你给的顺序。

### 参数

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `def_ids` | 整数数组 | 1–5 个六位角色 id，按 1 号位到 5 号位给 |
| `region` | 整数 | 区服，默认 1（官服） |
| `limit` | 1–6 | 最多返回几支队伍（默认 3，只是显示上限，不是游戏规则） |

### 它会返回什么

```json
{
  "found": 10,
  "teams": [
    { "defense": [100201, 110501, 102301, 100101, 114701],
      "attack": [100101, 102301, 100201],
      "upvotes": 1, "downvotes": 0, "updated": "2026-10-20", "ref": 1234567 }
  ]
}
```

- `found` 是上游返回的队伍总数，`teams` 是按 `limit` 截断后的摘要。
- 作业数据来自作业站，**时效性由上游决定**；`updated` 是它的更新时间，越新越可信。
- 角色人少（比如只剩 2 个）时命中率会明显下降——这是数据本身的性质，不是 bug。

### 它需要什么

它不直接连作业站，而是连你本机的**浏览器服务**（默认 `http://127.0.0.1:6191`），
由那个服务带着登录态去抓。服务没起时：

```json
{ "ok": false, "error": "… (set ANINEST_ARENA_URL to a service that answers POST /search)" }
```

这时先 `service_health` 看 6191 通不通。

---

## 4. `memory_search` / `memory_stats`：只读地翻记忆

这两个工具**只读**，不会写、不会改、不会删。数据库以 `mode=ro` 打开。

### `memory_search`

| 参数 | 说明 |
| --- | --- |
| `query` | 关键词或一句话 |
| `limit` | 1–20，默认 5 |
| `scope` | `all` / `session`（本会话）/ `global`（跨会话知识） |

返回：

```json
{ "query": "泳装插画", "scanned": 36, "matched": 2,
  "hits": [ { "score": 0.93, "content": "…", "scope": "global", "importance": 4 } ] }
```

打分是**词重合度 + 重要性先验**，不是向量检索：中文按字覆盖、英文按词。好处是零依赖、可解释；
坏处是同义改写召回不到。想更准就往 `query` 里多写几个实际出现过的词。

### `memory_stats`

返回行数、按 scope 的分布、平均文本长度、库文件大小与路径。适合"我的记忆存了多少了"这种问题。

### 没有库的时候

```
memory database not found: C:\Users\you\.aninest\memory.db.
Point ANINEST_MEMORY_DB at an existing SQLite file, or create a sample one with
`python scripts/make_demo_db.py --out <path>`.
```

本仓库不负责**产生**记忆——它只读别人写好的库。想先玩一下，就造个示例库（见上）。

---

## 5. `service_health`：本机服务在不在

```json
{ "host": "127.0.0.1", "up": 5, "total": 5,
  "services": {
    "astrbot-webui": { "port": 6185, "up": true },
    "onebot-ws":     { "port": 6199, "up": true },
    "tts":           { "port": 9880, "up": true },
    "stt":           { "port": 6190, "up": true },
    "arena-browser": { "port": 6191, "up": true }
  },
  "memory_db": { "path": "…", "exists": true } }
```

只看 TCP 能不能连上（0.6 秒超时），**不代表那个服务功能正常**。
单用本仓库时这些端口大概率是 down——正常，它只是探测"助手栈"是否在旁边。

---

## 6. 配置项（全部走环境变量）

| 变量 | 默认值 | 作用 |
| --- | --- | --- |
| `ANINEST_ARENA_URL` | `http://127.0.0.1:6191` | 浏览器作业服务的地址 |
| `ANINEST_MEMORY_DB` | `~/.aninest/memory.db` | 记忆库路径（只读） |
| `ANINEST_BOORU_URL` | `https://safebooru.org/index.php` | 图站地址 |
| `ANINEST_HTTP_TIMEOUT` | `15` | 单次 HTTP 超时（秒） |
| `ANINEST_USER_AGENT` | `aninest-mcp/<版本> (+仓库地址)` | 出站 UA |
| `ANINEST_MCP_TRANSPORT` | `stdio` | `stdio` 或 `streamable-http` |
| `ANINEST_MCP_HOST` / `ANINEST_MCP_PORT` | `127.0.0.1` / `8765` | HTTP 传输时监听地址；默认只绑本机 |
| `ANINEST_PROBE_HOST` | `127.0.0.1` | `service_health` 探的地址 |
| `ANINEST_FETCH_ALLOW_HOSTS` | 空（不限制） | 若启用网页抓取，可限定允许的域名 |

安全相关的固定行为：工具参数里**没有 URL**（出站地址只来自环境变量，模型无法让服务去访问任意地址）、
记忆库只读、图站结果只放行 `safe`。

---

## 7. 常见问题

**Q：宿主里看不到这五个工具？**
先确认 `command` 是绝对路径、客户端已重启；再用 `npx @modelcontextprotocol/inspector <command>` 看能不能列出工具。
命令行能起、客户端里没有，多半是客户端配置写错了层级（要放在 `mcpServers` 下）。

**Q：为什么它不自己说话？**
它没有对话能力，只有工具。说话的永远是宿主里的模型。

**Q：中文搜图搜不出来？**
看返回里的 `unknown_words` 和 `relaxed`；把描述换成"角色名 + 名词"最稳，形容词多了容易被降级。

**Q：能写记忆 / 能发评论 / 能操作用户账号吗？**
都不能。五个工具全是只读，这是设计边界（见 [THREAT_MODEL.md](THREAT_MODEL.md)）。

**Q：能同时开多个客户端吗？**
stdio 模式下每个客户端各起一个进程，互不影响；HTTP 模式注意只绑 `127.0.0.1`。

**Q：日志在哪？**
stdout 只走协议，日志在 stderr。客户端一般会把 stderr 收进自己的日志面板；
命令行直接跑时，stderr 会打在终端上。

---

## 8. 想改它

见 [ARCHITECTURE.md](ARCHITECTURE.md)（模块职责、改动时注意什么）与 [TESTING.md](TESTING.md)（五层验证、每层能证明什么）。
改完至少跑一遍：

```bash
python -m ruff check src tests eval scripts demo
python -m unittest discover -s tests
python eval/run_eval.py
python scripts/live_check.py --memory-db <你的 memory.db>
```
