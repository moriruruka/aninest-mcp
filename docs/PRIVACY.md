# 开源前的隐私自查（Open-source privacy checklist）

这个仓库是"能力层"剥离出来的：它只保留可以公开的协议代码，不包含运行时数据。
但**在 push 之前仍然要自己跑一遍下面的检查**，因为最容易泄露的往往不是代码，而是顺手贴进去的日志与截图。

## 1. 仓库里刻意没有的东西

| 类别 | 本仓库的处理 |
| --- | --- |
| 账号密码 / Cookie / SESSDATA | 不落地。所有凭证由使用者本机的服务持有，本仓库只通过环境变量取 URL 与路径。 |
| QQ 号、UID、昵称 | 源码与测试里没有任何真实号码，测试一律用 `100101` 这类假数据。 |
| 本机绝对路径 | 只有 `.env.example` 里出现 `C:/Users/you/...` 这种占位写法。 |
| 数据库文件 | 不包含。`ANINEST_MEMORY_DB` 指向使用者自己的路径，且以只读模式打开。 |
| 抓取到的图片 / 字幕 / 评论原文 | 不落盘、不进仓库。检索结果只有 URL。 |
| 日志 | `.gitignore` 已排除 `*.log`、`eval/report.json`、`.env`。 |

## 2. push 之前跑这几条

```bash
# 1) 真实 QQ 号 / UID（把 11 位和 9 位数字都扫一遍，人工判断命中）
git grep -nE "\b[1-9][0-9]{8,10}\b" -- . | grep -vE "100101|100201|127\.0\.0\.1|0\.0\.0\.0|:8[0-9]{3}|:6199|:6191|:6185|:9880|:6190|8765"

# 2) 凭证关键字
git grep -niE "sessdata|bili_jct|buvid3|dedeuserid|password|passwd|secret|token|api[_-]?key|cookie" -- .

# 3) 本机绝对路径（盘符 + 反斜杠）
git grep -nE "[A-Za-z]:\\\\|[A-Za-z]:/" -- . | grep -v "C:/Users/you"

# 4) 私有域名 / 内网地址
git grep -nE "192\.168\.|10\.[0-9]+\.|172\.(1[6-9]|2[0-9]|3[01])\." -- .

# 5) 历史提交也要干净（如果之前提交过敏感内容）
git log -p --all | grep -niE "sessdata|bili_jct|password" | head
```

命中后逐条判断：测试数据可以保留（改成假值），真实数据必须删掉并**重写历史**（`git filter-repo` 或直接重新初始化仓库）。

## 3. 图片与截图的额外注意

- 截图里可能带：QQ 号、群名、手机状态栏、浏览器书签栏、内网 IP。发 README 配图前先裁掉或打码。
- 本项目的实测截图（竞技场、私信、B 站后台）**不要**直接进公开仓库；需要示意图时用 `docs/images/` 里手绘的流程图。

## 4. 运行时数据边界（写进 README 的那句话）

> 这个 MCP 服务器只做三件事：编译 tag、发一个 HTTP 请求、只读查询本地 SQLite。
> 它不保存对话、不上传用户数据、不写任何文件。

## 5. 上线前的最后一次确认

- [x] `python -m unittest discover -s tests` 全绿（55 tests OK）
- [x] `python eval/run_eval.py` 全绿（离线，26/26）
- [x] `git status` 里没有 `data/`、`logs/`、`.env`、`*.db`
- [x] 上面 5 条 grep 全部人工看过（号码/凭证/路径/内网 IP 均无真实值）
- [x] GitHub 用户名已全部填成 `moriruruka`（原占位符 `<your-name>` 已替换）
- [x] LICENSE 里的年份与作者已确认（`Copyright (c) 2026 moriruruka`）
