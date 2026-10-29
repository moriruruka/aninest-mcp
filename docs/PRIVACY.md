# 数据边界与隐私（Data boundary）

AniNest 是一个**无状态的能力层**（唯一例外：`character_update` / `character_correct` 会写本地覆盖层，见第 2 节）：它只做「编译 tag、发一个 HTTP 请求、只读查询一个 SQLite 文件、读本地角色表与头像包、连一下本地端口」这几类动作。
下面把「它碰什么、不碰什么、数据往哪去」写清楚，便于部署前评估。

## 1. 不保存、不上传

| 类别 | 处理方式 |
| --- | --- |
| 账号 / 密码 / Cookie / SESSDATA | 仓库内零凭证。需要登录态的能力（如作业查询）由**部署者自己的本机服务**持有，本仓库只通过环境变量取一个 HTTP 地址。 |
| 用户标识（UID、昵称、群号等） | 源码与测试中没有任何真实标识；测试数据一律使用 `100101` 这类假值。 |
| 本机绝对路径 | 仅 `.env.example` 出现 `C:/Users/you/...` 占位写法。 |
| 数据库文件 | 不随仓库分发。`ANINEST_MEMORY_DB` 指向部署者自己的库，且以 `mode=ro` 只读打开。 |
| 抓取内容 | 图站检索只保留 URL 与元数据，不下载、不落盘；日志不写入任何文件（默认打到 stderr）。 |
| 遥测 | 没有。本仓库不发任何统计、不回传使用数据。 |

## 2. 运行时的数据流向

```
模型参数 ──► 本进程 ──► ①图站 HTTP API（只出站，只带 query 串）
                     ├─► ②本机服务的 /search（只出站，不带凭证）
                     ├─► ③本地 SQLite（只读）
                     ├─► ④本地角色表 `data/pcr_chars.json` + 覆盖层（随包分发，写只写覆盖层）
                     └─► ⑤本地头像包 `ANINEST_PCR_AVATARS`（只读）
```

- **出站地址不来自模型**：目标 host 由环境变量固定，工具参数里没有 URL 字段（见 `docs/THREAT_MODEL.md` 第 3 节）。
- **只读打开数据库**：`file:...?mode=ro` 由 SQLite 层直接拒绝写操作，工具不会修改记忆库。
- **识图不外传**：`portrait_identify` 的图片和头像包都只在本进程内比对，不请求任何远端服务；
  它接受的文件路径由宿主传入，所以宿主要自己决定给不给它读任意路径。
- **只写一个本地文件**：唯一落盘的是 `character_update` / `character_correct` 写的 `ANINEST_PCR_OVERLAY`
  （默认 `~/.aninest/pcr_overlay.json`，临时文件 + 原子替换，可随时删掉）；包内表与记忆库都写不进去。
  除此之外，除部署者显式指定 `--json` 把评测结果写到本地文件外，工具不写任何文件。

## 3. fork 或二次发布前的自查

如果要把本仓库（或它的改造版）放到公开位置，建议跑一遍下面几条，确认没有夹带自己环境里的真实数据：

```bash
# 1) 形似账号的数字（人工判断命中项）
git grep -nE "\b[1-9][0-9]{8,10}\b" -- . | grep -vE "100101|100201|127\.0\.0\.1|0\.0\.0\.0|:8[0-9]{3}|8765"

# 2) 凭证关键字
git grep -niE "sessdata|bili_jct|buvid3|dedeuserid|password|passwd|secret|token|api[_-]?key|cookie" -- .

# 3) 本机绝对路径
git grep -nE "[A-Za-z]:\\\\|[A-Za-z]:/" -- . | grep -v "C:/Users/you"

# 4) 私有网段地址
git grep -nE "192\.168\.|10\.[0-9]+\.|172\.(1[6-9]|2[0-9]|3[01])\." -- .

# 5) 历史提交也要干净
git log -p --all | grep -niE "sessdata|bili_jct|password" | head
```

命中后逐条判断：假数据可以保留，真实数据必须删除并重写历史（`git filter-repo` 或重新初始化仓库）。

## 4. 配图注意

截图里常见的泄露点是边框之外的区域：账号昵称、群名、手机状态栏、浏览器书签栏、内网地址。
公开前先裁掉或打码；需要示意图时优先用矢量/手绘流程图，而不是界面截图。

## 5. 本仓库当前状态

- [x] `python -m unittest discover -s tests` 全绿（172 tests OK，未安装 `[vision]` 时识图用例跳过）
- [x] 头像包（游戏美术素材）不进仓库：它由 `ANINEST_PCR_AVATARS` 指向使用者自己的目录；仓库里只有
      `scripts/make_demo_avatars.py` 生成的合成头像
- [x] 本地覆盖层（`ANINEST_PCR_OVERLAY`，默认 `~/.aninest/pcr_overlay.json`）只存名字、别名、
      更正备注，不含凭证；它在家目录，不在仓库里
- [x] `python eval/run_eval.py` 全绿（离线，26/26）
- [x] `git status` 中没有 `data/`、`logs/`、`.env`、`*.db`
- [x] 上述 5 条 grep 已逐条核对（无真实号码、凭证、绝对路径、内网地址）
- [x] `LICENSE` 与 `pyproject.toml` 的维护者信息与仓库归属一致
