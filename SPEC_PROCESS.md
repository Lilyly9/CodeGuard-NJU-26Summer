# SPEC / PLAN 冷启动测试反馈

> 由盲测审计员在实现 T03（配置模块）过程中记录。

---

### 冷启动测试反馈（由盲测审计员记录）

#### 卡点 1：SPEC §9.4 与 PLAN T03 的 Config 字段不一致

- **依据文档**：
  - SPEC §9.4 原文：*"支持项：`workspace`, `max_steps`, `command_timeout`, `max_file_size`, `allow_network`, `allowed_commands`, `protected_files`, `risk_levels`（可自定义）。"*
  - PLAN T03 原文：`Config` dataclass 包含 `workspace`, `max_steps`, `command_timeout`, `max_file_size`, `allowed_commands`, `protected_files`, `allowed_extensions`, `auto_finish_on_test_pass`, `log_level`, `high_size_threshold`, `forbidden_shell_chars`。
- **我的困惑**：SPEC 明确列出了 `allow_network` 和 `risk_levels`（可自定义），但 PLAN 的 Config 实现中完全没有这两个字段。是实现时遗漏了，还是 PLAN 有意将其排除在第一版之外？我应该以哪个文档为准？
- **我做出的错误解读（如果有）**：我以 PLAN 为准实现了 Config，忽略掉了 SPEC 中的 `allow_network` 和 `risk_levels`。如果 SPEC 是权威来源，这两个字段应该补入 Config。

#### 卡点 2：TOML 配置文件的 section 名称未在文档中显式声明

- **依据文档**：
  - SPEC §9.4 原文：*"配置文件 `config.toml`（示例见附录 C）。"* —— 但附录 C 缺失。
  - PLAN T03 原文：`config.toml` 写入 `[agent] workspace = "./demo_project"`；测试代码 `p.write_text("[agent]\nmax_steps = 5")`。
- **我的困惑**：TOML 的 section 名称 `[agent]` 仅出现在 PLAN 的测试代码片段中，SPEC 完全没有提及。如果未来需要扩展其他 section（如 `[logging]`、`[sandbox]`），`[agent]` 这个名称是否合适？这个名称是正式约定还是临时占位？
- **我做出的错误解读（如果有）**：我直接使用了 `[agent]` 作为 section 名称，因为它出现在 PLAN 的测试代码中。如果未来需要拆分，可能需要重构。

#### 卡点 3：`load_config` 函数的默认路径参数行为不明确

- **依据文档**：
  - PLAN T03 原文函数签名：`def load_config(path: str = "config.toml") -> Config`。
  - PLAN T03 测试代码：`p = tmp_path / "config.toml"; … c = load_config(str(p))`。
- **我的困惑**：当 `path` 为默认值 `"config.toml"` 时，它会被解析为相对于当前工作目录的路径。但文档没有明确说明：如果文件不存在，是返回全默认的 Config 还是报错？如果文件存在但格式错误（非 TOML），应该抛出异常还是返回默认值？
- **我做出的错误解读（如果有）**：我实现了"文件不存在 → 返回全默认 Config"，"文件存在但格式错误 → 让 TOML 解析异常向上传播"。这两个行为都是凭经验推断的，文档未明确要求。

#### 卡点 4：`_merge_config` 函数的行为未完整定义

- **依据文档**：
  - PLAN T03 原文（重构栏）：*"提取 `_merge_config` 函数"*。
- **我的困惑**：PLAN 只提到了"提取 `_merge_config` 函数"这个名字，但没有给出函数签名、入参类型、出参类型、以及合并逻辑细节（如：遇到未知 key 是忽略还是报错？是修改原对象还是返回新对象？）。
- **我做出的错误解读（如果有）**：我将其实现为 `def _merge_config(config: Config, data: dict) -> Config`，修改原对象并返回，遇到未知 key 静默忽略。这三个行为都是推测的，文档未定义。

#### 卡点 5：`tomli` 与 `tomllib` 的兼容策略未声明

- **依据文档**：
  - SPEC §14 原文：*"`tomli` — 解析 TOML 配置文件（Python 3.11 后可内置 `tomllib`）。"*
  - PLAN T03 原文：*"使用 `tomli.load()` 读取"*。
- **我的困惑**：SPEC 同时提到了 `tomli` 和 `tomllib`，但 PLAN 只写了 `tomli`。当前环境是 Python 3.13，应该用 `tomllib` 还是继续依赖 `tomli`？`pyproject.toml` 的 dependencies 中写了 `tomli`，但 Python 3.11+ 不需要安装它。
- **我做出的错误解读（如果有）**：我实现了 try/except 回退逻辑（先 `tomli`，再 `tomllib`），但这引入了额外复杂度。文档应该明确"优先使用标准库 `tomllib`，`tomli` 仅作为 Python 3.10 的 backfill"。

#### 卡点 6：`Config` 的 `allowed_commands` 字段使用空格还是列表拆分的格式不明确

- **依据文档**：
  - PLAN T03 原文：`allowed_commands: list = field(default_factory=lambda: ["python","pytest","ruff","mypy","git diff","git status"])`。
  - PLAN T05（命令沙箱）原文：`cmd_name = command.split()[0]; if cmd_name not in [c.split()[0] for c in config.allowed_commands]`。
- **我的困惑**：`allowed_commands` 列表中同时包含单词命令（`"python"`）和多词命令（`"git diff"`）。T05 的代码用 `c.split()[0]` 提取命令名，这意味着 `"git diff"` 会被提取为 `"git"`。那么 `"git diff"` 中的 `"diff"` 子命令是否被校验？如果 LLM 请求 `"git commit"`，`c.split()[0]` 提取出 `"git"`，它会被判为允许吗？这似乎是一个安全漏洞。
- **我做出的错误解读（如果有）**：我在 T03 中只是原样存储了命令列表，没有处理这个格式问题。这是一个需要跨 T03 和 T05 协调的设计问题。