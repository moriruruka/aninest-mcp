# 使用说明

这份文档面向"已经装好了、想知道怎么用"的人。安装见 [INSTALL.md](INSTALL.md)。

AniNest 不是聊天机器人，它是一层**能力**。真正和你对话的是宿主（Claude Desktop、DSH、编辑器插件等），
宿主在需要的时候调用这十个工具。所以"怎么用"其实是两件事：**常见问法**，以及**工具会返回什么**。

---

## 1. 十个工具能做什么

| 工具 | 一句话 | 典型问法 |
| --- | --- | --- |
| `art_search` | 把一句中文描述变成图站能懂的标签，再取回图片链接 | "来两张初音未来泳装的竖图" |
| `arena_lookup` | 按名字（或 id）查一个防守阵容的作业，可顺带排除/替换再查 | "布丁、克总、真琴、纺希、莉莎这队作业" |
| `character_lookup` | 把嘴里的叫法对上标准角色：名字 / 黑话 / 四位 uid / 六位 id | "布丁和克总分别是哪个角色" |
| `character_match` | 名字相似度排序：查不到时列出候选、分数和命中方式 | "宫紫 是哪个角色" |
| `character_update` | 新建角色或补别名（**写本地覆盖层**） | "日服刚出的新角色，加一下" |
| `character_correct` | 把一个词记到某角色名下（**写本地覆盖层**） | "宫紫 就是宫子，记住" |
| `portrait_identify` | 看一张已经裁好的头像，说出是哪个角色 | "这张头像上是谁" |
| `memory_search` | 在助手自己的记忆库里检索（只读） | "上次说的那个配色偏好还记得吗" |
| `memory_stats` | 记忆库有多大、多少条、按范围分布 | "你的记忆存了多少了" |
| `service_health` | 本机那几个服务此刻在不在 | "服务都活着吗" |

顺序建议：**先 `service_health`，再调其它**。这样"服务没起"不会被误当成"你参数给错了"。
阵容里的人名认不准时，先 `character_lookup` 对一遍再 `arena_lookup`，比直接查省事；
`character_lookup` 没对上就用 `character_match` 看候选（见第 4 节）。

前七个工具只读；`character_match` 也只读。`character_update` / `character_correct` 会写本地覆盖层
`~/.aninest/pcr_overlay.json`，不碰随包分发的角色表、记忆库和网络（第 4 节专门讲这三个）。

---

## 2. `art_search`：中文 → 标签 → 图片

### 常见问法

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
   （这里的 56 条是**图站 tag 用**的角色名映射；`character_lookup` 用的是另一张 351 角色的表，两者用途不同。）
3. **检索并放宽**：先按全部条件查；空就依次去掉方向约束、逐个减少 tag——最多几档，避免"明明有图却回没有"。

### 常见情况

| 你看到的 | 意思 | 怎么办 |
| --- | --- | --- |
| `no image matched after N attempts` | 图站真的没有这组组合（或站点暂时连不上） | 减一个限定词再试，比如去掉"竖图" |
| `no usable tag was produced` | 整句话没翻出任何 tag | 换成"角色名 + 一两个名词"的说法 |
| 报错里提到 `blocked` | 命中了内置的敏感词表 | 换描述；这是安全边界，不做绕过 |
| 结果长得不像你要的 | 走了降级档（`relaxed: true`） | 让宿主说得更具体，或直接给 `extra_tags` |

---

## 3. `character_lookup`：叫法 → 标准角色

### 常见问法

- 布丁是哪个角色
- 布丁和克总分别是哪个角色
- 1007 是谁（四位数 uid）
- 100701 是谁（六位 id）
- ミヤコ 是哪个角色（日文名、英文名、别名词都认）

### 参数

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `query` | 字符串 | 一句话里可以有好几个名字，用 `、，和与及` 或空格分开（`"布丁和克总"` → 2 个角色） |
| `limit` | 1–5 | 最多认几个（默认 5），超出的截掉 |

### 它会返回什么

```json
{
  "query": "布丁和克总",
  "matches": [
    { "slot": 1, "id": 100701, "uid4": 1007, "name": "宫子",
      "aliases": ["…"], "jp": "…", "servers": [] },
    { "slot": 2, "id": 107101, "uid4": 1071, "name": "克莉丝提娜",
      "aliases": ["…"], "jp": "…", "servers": [] }
  ],
  "unresolved": [],
  "total_characters": 351
}
```

- `slot`：这句话里的第几个名字（**不是**队伍号位）。
- `id` / `uid4`：六位 id 与四位数写法（`1007` ↔ `100701`，两种都能当输入）。
- `name` 是标准中文名，`aliases` 是全部别名，`jp` 是日文名，`servers` 是限定区服（空数组 = 各区通用）。
- `unresolved`：没认出来的词；`total_characters`：表里一共多少角色。
- 一个都没对上时，返回里会多一个 `suggestions`（按编辑距离给的近似候选）。

### 已知边界

- 单字别名（比如 `克`）只在**完全相等**时命中，不参与模糊猜测——否则几乎任何词都能蹭上。
- `日和` 这种名字里带「和」的角色不会被拆成两半：`和`只在整串都认不出时才当分隔符。
- 日文名也是可查的名字：`all_names` 里含 `jp`，所以 `ミヤコ` 能直接查到宫子（100701）。
- 角色表随包分发（`src/aninest/data/pcr_chars.json`，351 个角色 / 2211 条别名），纯本地匹配、不出网；
  本地覆盖层里的新角色与别名会**并进同一张索引**，包里的表不会被改（见第 4 节）。

---

## 4. 认不准 / 有新角色：`character_match`、`character_update`、`character_correct`

这三个工具管的是**角色表本身**，不查作业、不查图：一个帮你列候选，另外两个把更正写进本地覆盖层。
随包分发的 `src/aninest/data/pcr_chars.json`（351 个角色 / 2211 条别名）是只读的，升级时整个替换；
你加的东西写在覆盖层 `~/.aninest/pcr_overlay.json`（`ANINEST_PCR_OVERLAY` 可改路径），
和包里的表合并后生效。所以升级不会丢，写坏了删掉这个文件就回到出厂状态。

### 4.1 `character_match`：查不到名字时，先把候选摆出来

宿主该在什么时候调它：`character_lookup` 一个都没对上、或 `arena_lookup` 的 `unresolved` 非空时。
它按名字相似度排序，给出分数和**命中方式**；宿主把这些候选连同分数给用户看，让用户挑，
再决定要不要 `character_correct`——**不要自己挑一个"最像的"就写进去**。

参数：

| 参数 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `query` | 字符串 | 必填 | 要认的名字：中文 / 日文 / 罗马字 / 手误都行（`宫紫`、`ミヤコ`、`miyako`） |
| `top_k` | 整数 | `5` | 最多返回几个候选（1–20） |
| `threshold` | 浮点 | `0.45` | 分数下限（0–1），低于它的不算候选 |

返回：

```json
{
  "query": "宫紫",
  "threshold": 0.45,
  "matches": [
    { "id": 100701, "uid4": 1007, "name": "宫子", "jp": "ミヤコ",
      "score": 0.5, "matched": "宫子", "matched_on": "fuzzy_name" }
  ],
  "total_above_threshold": 1
}
```

- `score`：0–1，`1.0` 只给完全相同的写法。
- `matched_on` 说明它是怎么对上的：`exact_name` / `exact_alias` / `exact_jp` 可以信；
  `prefix_*`、`substring_*` 依次弱一些；`fuzzy_*` 只表示"像"，**不该当确定答案**。
- `matched`：具体对上的是哪个写法（标准名 / 某条别名 / 日文名）。
- `total_above_threshold`：过线的总数，可能大于 `matches` 的长度（被 `top_k` 截了）。

失败：`query is required`（`query` 去掉空白后是空的）。

### 4.2 `character_update`：加一个新角色、补别名

只用于**表里真的没有**的角色——日服先上线、中文名和黑话还没传开的那些。
"匹配错了"不是它的场景，那种情况用 `character_correct`，别再造一个人出来。

参数：

| 参数 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `char_id` | 整数 | 必填 | 六位竞技场 id（100000–999999） |
| `name` | 字符串 | `null` | 中文名；表里没有这个 id 时**必须**给 |
| `aliases` | 字符串数组 | `null` | 要接受的其它叫法，如 `["新酱"]` |
| `jp` | 字符串 | `null` | 日文名；新角色通常只有这个，给了就能按日文名查 |
| `servers` | 字符串数组 | `null` | 出现的区服，如 `["jp", "cn"]`；不填沿用原值或 `["cn", "jp"]` |
| `remove_aliases` | 字符串数组 | `null` | 要删掉的别名（错的别名比没有更糟） |

返回：

```json
{
  "action": "created",
  "character": { "id": 199901, "uid4": 1999, "name": "新角色", "jp": "シンキャラ",
                 "aliases": ["新酱"], "servers": ["cn", "jp"] },
  "added_aliases": ["新酱"],
  "removed_aliases": [],
  "overlay": "C:/Users/you/.aninest/pcr_overlay.json",
  "characters_in_overlay": 1
}
```

- `action`：`created`（表里原来没有）或 `updated`（原来就有）。
- **幂等**：同样的别名再发一次，`added_aliases` 是空数组，文件里不会出现重复项。
- `overlay` 是真正写入的路径，`characters_in_overlay` 是覆盖层里累计几个角色。

失败：
`character id must be a number, got …`（不是数字）、
`character id out of range: … (expected six digits)`（不在 100000–999999）、
`character 199902 is not in the table; pass name to create it`（新建却没给 `name`）。

### 4.3 `character_correct`：把一个词记到某角色名下

这是"匹配错了"的手工修正：`term` 存成该角色的别名，并在覆盖层里记一条带时间的更正。
写完会立刻重载索引，**下一次调用就生效，不用重启进程**。

参数：

| 参数 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `term` | 字符串 | 必填 | 用户实际打出来的词，如 `宫紫` |
| `char_id` | 整数或字符串 | 必填 | 它应该指向谁：六位 id，或任何已知名字（`宫子`） |
| `note` | 字符串 | `""` | 备注，跟着这条更正一起存 |

返回：

```json
{
  "action": "alias_added",
  "term": "宫紫",
  "id": 100701,
  "name": "宫子",
  "aliases": ["…", "宫紫"],
  "corrections": 1,
  "overlay": "C:/Users/you/.aninest/pcr_overlay.json"
}
```

- `action`：`alias_added`（新学会）、`already_known`（这条别名本来就有，不重复写）、
  `noop`（`term` 就是角色名本身，没什么可加的——这时只返回 `action` / `reason` / `id` / `name`）。
- `corrections`：覆盖层里累计的更正条数。

失败：`term is required`（`term` 是空的）、`unknown character: '…'`（`char_id` 既不是 id 也对不上名字）。

### 4.4 三者的分工

| 情况 | 用哪个 |
| --- | --- |
| `character_lookup` 没对上，想知道像谁 | `character_match` |
| 用户确认"就是这些候选里的某一个" | `character_correct(term, 那个 id)` |
| 用户确认"是没收录的新角色" | `character_update(jp=…)`（表里没有这个 id，必须带 `name`） |
| 某条别名总把人带错 | 先 `character_update(remove_aliases=[…])` 删掉，再 `character_correct` 教对的 |

---

## 5. `portrait_identify`：这张头像是谁

### 常见问法

- 这张头像上是谁
- 这几张图分别是谁

**它不做的事**：输入得是**已经裁好的人像/头像**；在截图里找头像框、切图，是宿主的事，它只回答"这张脸是谁"。

### 先用起来（两件事）

1. 装可选依赖：`pip install -e ".[vision]"`（numpy + Pillow，只在识图时需要）。
2. 指一个头像包目录：`ANINEST_PCR_AVATARS` 指向的目录里放 `<六位角色 id>.webp` / `.png` / `.jpg`。

头像包**不进仓库**（游戏美术版权），得自己准备。手上一张都没有时，可以先造几张合成的：

```bash
python scripts/make_demo_avatars.py --out demo_avatars
```

然后在同一个 shell 里把 `ANINEST_PCR_AVATARS` 指向它的**绝对路径**，再调工具。生成的 5 张是
100101 / 100201 / 100301 / 100701 / 107101，用来验证链路通不通，认不了真实头像。

### 参数

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `images` | 数组 | 每项可以是文件路径、裸 bytes、base64 串、data URI；至少给一张 |
| `top_k` | 1–5 | 每张图给几个候选（默认 3） |
| `min_score` | 0–1 | 低于它就当"未知"（默认 0.55） |

### 它会返回什么

```json
{
  "pack": "C:/path/to/avatars",
  "images": 1,
  "results": [
    { "best": { "id": 100701, "score": 1.0, "name": "宫子" },
      "candidates": [ { "id": 100701, "score": 1.0, "name": "宫子" } ],
      "known": true }
  ]
}
```

- `best`：最高分的那个；分数低于 `min_score` 时是 `null`。
- `candidates`：前 `top_k` 个候选，`score` 是归一化互相关（1.0 ≈ 逐像素一致）。
- `known`：`false` 表示"给了图，但一个都不够像"。

### 它怎么认

灰度 → 零均值 → 单位化，取头像中间那条"脸带"的 3 个裁剪视窗（0–100%、12%–88%、24%–76%），
和头像包里每张图做归一化互相关，取最高分。所以对**居中、正面、构图接近**的头像最准；
侧脸、花背景、大透视会掉分，这时看 `candidates` 比看 `best` 有用。

### 常见情况

| 你看到的 | 意思 | 怎么办 |
| --- | --- | --- |
| `portrait matching needs the [vision] extra: pip install 'aninest-mcp[vision]'` | 没装 numpy / Pillow | `pip install -e ".[vision]"`（已安装的用 `pip install "aninest-mcp[vision]"`） |
| `avatar pack not configured: set ANINEST_PCR_AVATARS to a directory of …` | 没指头像包 | 设 `ANINEST_PCR_AVATARS` 指向目录 |
| `avatar pack … has no usable images` | 目录里没有能读的图 | 放 `<六位 id>.webp/.png`，或跑 `make_demo_avatars.py` |
| `images is empty` | 没给图 | 至少给一张 |
| `known: false` / 分数很低 | 认不出 | 换更正的裁图，或把 `min_score` 调低一点再看候选 |

---

## 6. `arena_lookup`：按名字查作业

### 常见问法

- 布丁、克总、真琴、纺希、莉莎这个防守的作业
- 布丁 克总 100301（名字和 id 混着写也行）
- 这队把布丁换成怜，再查一次
- 查不到就先排除真琴试试

**位置上要注意**：名字按给的顺序落到 1–5 号位，1 号位是队伍最前面那个（一般是坦克）。
想知道它具体把谁放到了几号位，看返回里的 `lineup`。

### 参数

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `defense` | 字符串或数组 | 阵容：角色名 / 黑话 / 四位 uid / 六位 id 混着写，一队 5 人；超过 5 个会被截断，返回里带 `truncated` |
| `def_ids` | 整数数组 | 只给 id 的旧写法，仍然可用：1–5 个六位 id，顺序就是号位 |
| `region` | 整数 | 区服，默认 1（官服） |
| `limit` | 1–6 | 最多返回几支队伍（默认 3，只是显示上限，不是游戏规则） |
| `exclude` | 字符串或数组 | 先拿掉一个角色再查（查不到作业时用） |
| `replace` | 字符串 / 对象 / 数组 | 把 A 换成 B 再查：`"布丁->怜"`、`"布丁→怜"`、`"布丁 换成 怜"`、`{"from": "布丁", "to": "怜"}` 都行 |

`defense` 优先：给了它就用它，没给才看 `def_ids`。

### 它会返回什么

```json
{
  "found": 3,
  "region": 1,
  "def_ids": [100701, 107101, 100301],
  "lineup": [
    { "slot": 1, "id": 100701, "name": "宫子" },
    { "slot": 2, "id": 107101, "name": "克莉丝提娜" },
    { "slot": 3, "id": 100301, "name": "怜" }
  ],
  "teams": [
    { "defense": [105101, 107101, 105401, 104301, 100701],
      "defense_names": ["…"],
      "attack": [100101, 102301, 100201],
      "attack_names": ["…"],
      "upvotes": 0, "downvotes": 0, "updated": "2026-10-20", "ref": 1234567 }
  ]
}
```

（上面的 id 只表示字段形状，不代表某组具体阵容。）

- `lineup`：它把输入理解成了哪 5 个人——**名字认错时先看这里**。
- `applied`：这次实际做了哪次排除/替换（替换会带 `slot`，说明换了哪个号位）；没有可记的动作时这个键不出现。
- `unresolved`：没认出来的词 + 候选建议。
- `teams[]`：`defense` / `attack` 是 id，`defense_names` / `attack_names` 是人话名字。
- `found` 是上游返回的队伍总数，`teams` 是按 `limit` 截断后的摘要。
- 作业数据来自作业站，**时效性由上游决定**；`updated` 是它的更新时间，越新越可信。
- 角色人少（比如只剩 2 个）时命中率会明显下降——这是数据本身的性质，不是 bug。

### 出错时

| 看到的 | 意思 | 怎么办 |
| --- | --- | --- |
| `no character resolved from the given lineup` | 整队一个都没认出来 | 先 `character_lookup` 对一遍名字，或改用 `def_ids` |
| `cannot apply replacement: … same_character` | 把 A 换成了 A | 换一个真的不同的角色 |
| `cannot apply replacement: … duplicate` | 换成的人已经在队里（会说明在几号位） | 换别人，或先 `exclude` 掉那个位置 |
| `cannot apply replacement: … not_in_team` | 要换的角色不在队里 | 看 `lineup` 确认它在不在 |
| `arena browser service is not running at …` | 本机作业服务没起 | 起服务，或改 `ANINEST_ARENA_URL` |

### 它需要什么

它不直接连作业站，而是连你本机的**浏览器服务**（默认 `http://127.0.0.1:6191`），
由那个服务带着登录态去抓。服务没起时：

```json
{ "ok": false, "error": "… (set ANINEST_ARENA_URL to a service that answers POST /search)" }
```

这时先 `service_health` 看 6191 通不通。

---

## 7. `memory_search` / `memory_stats`：只读地翻记忆

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

## 8. `service_health`：本机服务在不在

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

## 9. 配置项（全部走环境变量）

| 变量 | 默认值 | 作用 |
| --- | --- | --- |
| `ANINEST_ARENA_URL` | `http://127.0.0.1:6191` | 浏览器作业服务的地址 |
| `ANINEST_MEMORY_DB` | `~/.aninest/memory.db` | 记忆库路径（只读） |
| `ANINEST_PCR_AVATARS` | 空（未配） | 头像包目录，里面是 `<六位角色 id>.webp` / `.png`；不配则 `portrait_identify` 明确报错 |
| `ANINEST_PCR_OVERLAY` | `~/.aninest/pcr_overlay.json` | 本地角色覆盖层：`character_update` / `character_correct` 写它，`character_lookup` / `character_match` 读它 |
| `ANINEST_BOORU_URL` | `https://safebooru.org/index.php` | 图站地址 |
| `ANINEST_HTTP_TIMEOUT` | `15` | 单次 HTTP 超时（秒） |
| `ANINEST_USER_AGENT` | `aninest-mcp/<版本> (+仓库地址)` | 出站 UA |
| `ANINEST_MCP_TRANSPORT` | `stdio` | `stdio` 或 `streamable-http` |
| `ANINEST_MCP_HOST` / `ANINEST_MCP_PORT` | `127.0.0.1` / `8765` | HTTP 传输时监听地址；默认只绑本机 |
| `ANINEST_PROBE_HOST` | `127.0.0.1` | `service_health` 探的地址 |

安全相关的固定行为：工具参数里**没有 URL**（出站地址只来自环境变量，模型无法让服务去访问任意地址）、
记忆库只读、图站结果只放行 `safe`、写操作只有一个目标（覆盖层文件，原子写、可随时删掉回到出厂状态）。

---

## 10. 常见问题

**Q：宿主里看不到这十个工具？**
先确认 `command` 是绝对路径、客户端已重启；再用 `npx @modelcontextprotocol/inspector <command>` 看能不能列出工具。
命令行能起、客户端里没有，多半是客户端配置写错了层级（要放在 `mcpServers` 下）。

**Q：为什么它不自己说话？**
它没有对话能力，只有工具。说话的永远是宿主里的模型。

**Q：`portrait_identify` 说缺依赖 / 缺头像包？**
识图是可选能力：先 `pip install -e ".[vision]"`，再把 `ANINEST_PCR_AVATARS` 指向你的 `<六位 id>.webp` 目录。
两个都没有时其余九个工具照常工作。

**Q：中文搜图搜不出来？**
看返回里的 `unknown_words` 和 `relaxed`；把描述换成"角色名 + 名词"最稳，形容词多了容易被降级。

**Q：能写记忆 / 能发评论 / 能操作用户账号吗？**
都不能。这是设计边界（见 [THREAT_MODEL.md](THREAT_MODEL.md)）。原有七个工具只读；`character_match` 也只读；
`character_update` / `character_correct` 只写本地覆盖层 `~/.aninest/pcr_overlay.json`——
原子写、不删任何数据、不联网、不碰随包分发的角色表和记忆库。

**Q：能同时开多个客户端吗？**
stdio 模式下每个客户端各起一个进程，互不影响；HTTP 模式注意只绑 `127.0.0.1`。

**Q：日志在哪？**
stdout 只走协议，日志在 stderr。客户端一般会把 stderr 收进自己的日志面板；
命令行直接跑时，stderr 会打在终端上。

---

## 11. 想改它

见 [ARCHITECTURE.md](ARCHITECTURE.md)（模块职责、改动时注意什么）与 [TESTING.md](TESTING.md)（五层验证、每层能证明什么）。
改完至少跑一遍：

```bash
python -m ruff check src tests eval scripts demo
python -m unittest discover -s tests
python eval/run_eval.py
python scripts/live_check.py --memory-db <你的 memory.db>
```

## 12. 宿主侧胶水：从一张截图到一套阵容

`portrait_identify` 只回答"这张**已经裁好**的头像图是谁"。截图里怎么找到头像、
怎么把同一行的五个头像组成一队，属于宿主的版面适配，仓库给了一个可直接运行的参考实现：

```bash
python demo/screenshot_lineup.py shot.png --grid 5x3 --rows 1 --order rtl
```

它做三件事：按格子裁图 → `portrait_identify` 认出每格是谁 → 把同一行的五个 id
交给 `arena_lookup`。号位从右往左数（1 号位是最右边的前卫），所以默认 `--order rtl`；
格子的尺寸不固定时用 `--boxes "x,y,w,h;..."` 直接给矩形。

为什么这条链不放进 server：不同模拟器分辨率、不同 UI 版本、可见行数都不一样，
把版面参数塞进能力层会让它变成"只对这一种截图有效"的工具。能力层保持无状态、可复用，
宿主拿自己的截图去适配，是这个分层的关键。
