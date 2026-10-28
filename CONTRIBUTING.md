# 贡献指南

## 本地开发

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # macOS / Linux
pip install -e ".[dev]"
```

## 提交前必须通过

```bash
ruff check src tests eval
python -m unittest discover -s tests -v
python eval/run_eval.py
```

三条都绿再开 PR。CI 会在两个平台上重复这三步，并额外构建 Docker 镜像。

## 代码约定

- **纯函数优先**：解析、校验、过滤、打分这些逻辑写成无副作用函数，便于单测（见 `tagging.parse_request`、`art.shape_results`）。
- **网络与 IO 放在最外层**：工具函数只做参数校验 → 调用 → 结果整形；出错统一抛 `ToolError`，带可读原因。
- **不偷偷降级**：任何"放宽了条件"的行为都要在返回值里标出来（参考 `relaxed` / `attempt`）。
- **不编造数据**：抓不到就报错，不返回示例值。
- **类型注解齐全**，`from __future__ import annotations`；行宽 100。

## 新增一个工具

1. 在 `src/aninest/tools/<name>.py` 实现核心逻辑（纯函数 + 一个 async 入口）。
2. 在 `server.py` 用 `@mcp.tool()` 注册，写清 docstring（它会成为工具描述，宿主模型据此判断何时调用）。
3. 在 `tests/` 加单元测试，覆盖：正常路径、边界值、错误路径。
4. 更新 `README.md` 的工具表、`CHANGELOG.md` 的 `Added`。
5. 如果引入了新的环境变量，同步 `.env.example` 与 README 的配置表。

## 新增一条评测用例

编辑 `eval/art_cases.json`：

```json
{"query": "银发 蓝眼 女仆 横图", "expect_tags": ["silver_hair", "blue_eyes", "maid"], "orientation": "landscape"}
```

`expect_tags` 里的 tag 必须全部命中；多出来的 tag 会算进 precision，但不会让用例失败。
`count` / `size` / `orientation` 可选，给了就会校验。要求被拒绝的用例写 `{"query": "…", "blocked": true}`。

## 分支与提交信息

- 分支：`feat/<短描述>`、`fix/<短描述>`、`docs/<短描述>`
- 提交：`feat: 支持按角色名前查 id`、`fix: 分级为 s 的结果被误过滤`

## 敏感信息

不要在 issue、PR、测试数据里粘贴真实账号、Cookie、用户名、本机绝对路径。
提交前看一眼 [docs/PRIVACY.md](docs/PRIVACY.md)。
