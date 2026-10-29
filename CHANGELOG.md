# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 与 [语义化版本](https://semver.org/lang/zh-CN/)。

## [0.4.1] - 2026-10-29

### Fixed

- Python 3.10 下 `from datetime import UTC` 会直接 ImportError（`UTC` 是 3.11 才有的别名），
  导致 `character_correct` 所在的模块在 3.10 上完全无法导入。改用 `datetime.timezone.utc`。
  CI 矩阵里的 3.10 两个 job 因此从红转绿。

## [0.4.0] - 2026-10-29

### Added

- `character_match(query, top_k=5, threshold=0.45)`：按名字相似度给候选，每个候选带 `score`（0–1）与
  `matched_on`（`exact_name` / `exact_alias` / `prefix_jp` / `substring_alias` / `fuzzy_name` 等），
  让宿主在"查不到这个名字"时把候选摆给用户挑，而不是猜一个。只读、不出网。
- `character_update(char_id, name=None, aliases=None, jp=None, servers=None, remove_aliases=None)`：
  新建角色或补别名。日服先上线的角色往往只有日文名，传 `jp="ミヤコ"` 就能立刻按日文名查到；
  表里没有的 id 必须带 `name`，重复发同一批别名不会写重复项。
- `character_correct(term, char_id, note="")`：修正匹配——把 `term` 记成该角色的别名，并在覆盖层里
  留一条带时间的更正记录；写完立刻重载索引，下一次调用就生效。`char_id` 接受六位 id 或任何已知名字。
- **本地覆盖层** `ANINEST_PCR_OVERLAY`（默认 `~/.aninest/pcr_overlay.json`）：随包分发的
  `src/aninest/data/pcr_chars.json` 升级时会被整个替换，所以用户加的角色、教过的别名都写在这个独立
  JSON 里，和包内表合并后生效（临时文件 + 原子替换；文件缺失或写坏时按空覆盖层处理，不影响启动）。
- 日文名进入可查名字集合（`all_names` 现在含 `jp`）：`ミヤコ` 能直接解析到宫子（100701），
  不必先有中文别名。

### Changed

- 工具数量 7 → 10。两个写工具用 `WRITE_LOCAL = ToolAnnotations(readOnlyHint=False, destructiveHint=False,
  idempotentHint=True, openWorldHint=False)` 标注：只写本地覆盖层，不联网、不删数据；其余七个仍是
  `readOnlyHint=True`，宿主可以据此只对这两个要一次确认。
- `aninest.server.EXPECTED_TOOLS` 成为工具清单的单一来源：CI 与 `tests/test_server_contract.py`
  都对着它断言，不再维护第三份手写列表。
- `scripts/live_check.py` 把 `ANINEST_PCR_OVERLAY` 指向临时目录，并把 `character_match` /
  `character_update` / `character_correct` 纳入联调（输出变成 `tools (10)`）：一次真机联调不会往你真实的
  覆盖层里写测试角色。
- 测试 139 → 162（11 个测试模块，新增 `tests/test_pcr_overlay.py`）；README、USAGE、ARCHITECTURE、
  COMPLIANCE、TESTING 的工具表与计数同步到十个工具。

## [0.3.0] - 2026-10-29

### Added

- `character_lookup(query, limit=5)`：把玩家嘴里的叫法（`布丁`、`克总`、四位数 `1007`、六位 `100701`、日文名、
  英文名、别名词）映射到标准角色，一句话里用 `、，和与及` 或空格就能问多个。纯本地匹配、不出网：角色表随包分发
  （`src/aninest/data/pcr_chars.json`，351 个角色 / 2211 条别名，由 `scripts/port_characters.py` 生成）。
- `portrait_identify(images, top_k=3, min_score=0.55)`：给一张**已经裁好**的人像/头像，用归一化互相关比对中间那条
  "脸带"（3 个裁剪视窗）回答是哪个角色，低于 `min_score` 视为未知；`images` 接受文件路径、裸 bytes、base64、data URI。
  头像包因为游戏美术版权不随仓库分发，用 `ANINEST_PCR_AVATARS` 指向自己的 `<六位 id>.webp` 目录；
  需要可选依赖 `pip install -e ".[vision]"`（numpy + Pillow）。
- `arena_lookup` 支持**按名字查作业**：`defense` 可以直接写角色名 / 黑话 / 四位 uid / 六位 id，字符串或数组都行。
  在此之前要先自己把名字换成六位 id，玩家侧的叫法（`布丁`）根本进不来。
- 同一次调用里就能**排除或替换**一个角色再查：`exclude` 先拿掉某人，`replace` 支持 `"布丁->怜"` / `"布丁→怜"` /
  `"布丁 换成 怜"` / `{"from": …, "to": …}`。省掉"查不到作业 → 手工改 id → 再查"的来回。
- `scripts/make_demo_avatars.py`：没有真实素材时生成 5 张合成头像（100101 / 100201 / 100301 / 100701 / 107101），
  让识图链路任何人都能复现——之前这一步必须有游戏素材才能试。
- `scripts/live_check.py` 新增 `--lineup 布丁 克总 真琴`（按名字查作业）与 `--avatars <目录>`（顺带验 `portrait_identify`）。

### Changed

- `arena_lookup` 的入参与返回：除 `def_ids` 外新增 `defense` / `exclude` / `replace`；返回新增 `lineup[]`
  （把输入理解成了哪 5 个人）、`applied[]`（实际做了哪次排除/替换、换了哪个号位）、`unresolved[]`
  （没认出来的词 + 候选建议）；`teams[]` 新增 `defense_names` / `attack_names`，同时保留 `defense` / `attack`（id），
  宿主可以直接对着人说人话。
- `ANINEST_PCR_AVATARS` 现在和其他配置一样从 `config.Settings` 读（`portrait` 仍兼容直接读环境变量），
  文档里七个环境变量与代码一一对应。
- 工具数量 5 → 7（`tools/list` 与契约测试同步）；README、USAGE 的工具表、模块表、测试数按七个工具重写。
- 版本号 0.2.1 → 0.3.0（`version.py` 与 `pyproject.toml` 同步）；测试 83 → 139（10 个测试模块，新增
  `test_pcr_chars.py`、`test_arena_names.py`、`test_portrait.py`）。

### Fixed

- `portrait_identify` 第一次调用要卡约 15 秒：numpy / Pillow 原先在工具调用里才 import，而工具跑在工作线程、
  主线程正阻塞在 stdio 读上，两边抢 import 锁。改为模块加载时（启动阶段、主线程）就导入，首次调用立即返回。
- `布丁和克总` 这类用「和 / 与 / 及」连写的句子，只有在**整串认不出**时才按连接词拆；否则 `日和` 这种名字里带
  「和」的角色会被拆成两半。
- 阵容人数统一按 5 校验：解析阶段多给的名字会被截掉并在返回里标 `truncated`，`validate_ids` 也只接受 5 个。
- 角色表装进 wheel 后读不出来：`src/aninest/data/` 少了 `__init__.py`，`importlib.resources` 在 3.10 上
  找不到它。补成真正的子包，并用干净 venv 装 wheel 复验（`351 角色 / 2211 别名`）。
- 在中文 Windows 控制台（cp936）上跑 `scripts/mcp_smoke.py` 会崩：角色别名里有 emoji（如宫子的 `🍮`），
  `print` 时 `UnicodeEncodeError`。`mcp_smoke.py` / `live_check.py` / `make_demo_avatars.py` 现在
  启动时把 stdout/stderr 切到 UTF-8（`errors="replace"`），与 `demo/story.py` 一致。
- `scripts/port_tags.py` 里残留了某台机器上的绝对路径作为默认源；删除该默认值，只认 `--source` 或
  `ANINEST_TAG_SOURCE`，避免把某台机器的目录结构带进仓库。
- `server.py` 的 `INSTRUCTIONS` 开头写着「Eight capabilities」，实际是 7 个工具；改为 Seven。

## [0.2.1] - 2026-10-29

### Added

- 工具元数据补齐 MCP 规范里的可选字段：5 个工具现在都带 `title`（人类可读名）与
  `annotations`（`readOnlyHint=true`、`destructiveHint=false`；`art_search`/`arena_lookup`
  额外 `openWorldHint=true`），宿主可以据此免确认、或提示"会联网"。
- `docs/COMPLIANCE.md`：逐项列出"已符合 / 有意不做 / 还能加固"，每条都给出可复验的证据与命令。
- `tests/test_server_contract.py`：7 个契约用例，锁住工具清单、schema、title、annotations、
  resource 与 prompt，防止后续改动悄悄丢掉这些字段。
- **一键安装脚本**：`install.cmd`（Windows 双击）/ `install.ps1` / `install.sh`。
  自建独立 venv（不碰系统 Python）→ 装依赖 → 自己跑一次 MCP 握手自检 → 打印可直接粘贴的客户端配置；
  支持 `-Mirror`（国内镜像）、`-MemoryDb`、`-WriteClaudeConfig`（合并写入并备份原配置）、`-Upgrade`。
  在 Windows 11 + Python 3.13 实测：装出 0.2.1，握手 `protocol=2025-11-25`、5 个工具，退出码 0。
- **面向使用者的文档**：`docs/INSTALL.md`（四条安装路径 + 客户端配置 + 装不上排查表）、
  `docs/USAGE.md`（每个工具怎么问、参数含义、返回字段、常见报错、环境变量、FAQ）。
- README 改成"先给结论"的结构：30 秒上手三条路、五个工具对照表（示例问句）、文档地图；
  开发细节下移，重复的安装段落合并到 `docs/INSTALL.md`。

### Changed

- 版本号 0.2.0 → 0.2.1（`version.py` 与 `pyproject.toml` 同步；sdist 里带上 `scripts/` 与安装脚本）。
- 文档里的测试数量统一为当前真实值（83），不再出现 65/67/76 等历史数字。

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
  （同类过滤顺序问题，已一并修正）。
- `arena_lookup` 原本接受 1–6 个角色 id，但游戏里一队只有 5 人：上限改为 **5 个不重复 id**
  （去重后才计数量，部分阵容仍合法），并同步工具描述、README 与威胁模型。
- `arena_lookup` 读取的是**上游真实结构**，此前按臆想的扁平行解析（`defense`/`attack`/`views`），
  接真实服务时恒返回 0 支队伍，而 fixture 测试全绿。现在会向下走到第一个队伍列表，
  从 `[{id, star, equip}]` 里取角色 id，票数用 `up`/`down`，不再编造播放量。
  回归样本：`tests/fixtures/arena_payload.json`（真实返回截取）。
- `scripts/fake_arena.py` 的响应结构同步为真实形状，避免替身把错误结构“验成正确”。

### Added

- `scripts/port_tags.py`：从助手的 `tagging.py` 导出词典表（找不到源文件就报错，不写空表）。
- 角色表与 tag 词典改为按上游数据整表移植，来源与覆盖范围见 `docs/USAGE.md`。
- README 增「与助手词典的关系」入口与 **DSH 的 MCP 配置示例**（`dsh-mcp-client` 装配片段）。
- `scripts/live_check.py`：对着**本机真实运行的服务**做端到端检查——真实 MCP stdio 起 server，
  逐个调五个工具并打印一行结果，全过才返回 0；带 `--skip-network`、`--ids`。
- `docs/TESTING.md`：分层验证手册（lint → 单测 → 离线评测 → 替身演示 → 真机联调），
  每层写明“能证明什么、不能证明什么”，附失败排查表与已知未覆盖清单。
- `demo/host.py`：最小 MCP 宿主（26 行路由 + 结构化结果说人话），证明 server 不依赖特定客户端。
- `demo/story.py`：一条命令跑完整段对话——起假作业服务、造示例记忆库、经真实 stdio 协议调三个工具。
- `tests/test_demo_router.py`：8 个用例覆盖路由与结果转述；连同阵容校验的两条新用例，单测总数 55 → 65。
- `docs/ARCHITECTURE.md`：模块职责与依赖方向，便于定位改动点。
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
  `CONTRIBUTING.md`。

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
