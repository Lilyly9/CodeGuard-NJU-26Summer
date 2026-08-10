# CodeGuard — 技术规格说明书

> 版本：1.0  
> 状态：待评审  
> 相关文档：[通用要求]、[AI4SE_Coding_Agent_Harness]、[CodeGuard 项目要求]

---

## 1. 项目定位与核心价值

### 1.1 问题陈述

大语言模型（LLM）可以生成代码修改建议，但其输出具有不确定性，可能提议删除整个项目、读取 `.env` 文件、执行危险 Shell 命令等。如果直接执行 LLM 的每一条指令，会导致代码丢失、凭据泄露、系统文件破坏等严重后果。现有 Coding Agent 大多依赖提示词约束安全，但这种软性约束不可靠、不可测试。  
CodeGuard 通过一个 **确定性代码实现的治理层**，在 LLM 与操作系统之间建立硬性护栏，将“安全”从提示词转移到可测试的工程代码中。

### 1.2 核心价值（唯一不可替代性）

- **硬护栏而非软提示**：风险识别、分级、拦截、审批均由 Python 代码实现，不依赖 LLM 的“自觉”。
- **可测试的安全机制**：所有治理逻辑在移除真实 LLM 后仍能通过单元测试验证，符合课程“机制必须是代码”的核心纪律。
- **人机协同（HITL）**：高风险操作必须经人工审批，防止自动化失控。
- **反馈闭环**：测试结果、命令退出码等客观信号回灌给 LLM，驱动其自我修正。

### 1.3 目标用户画像

- 希望使用 AI 辅助修改代码的学生/开发者  
- 希望观察 Agent 决策过程的初学者  
- 需要限制 Agent 权限的安全敏感型团队  
- 课程评审人员（需要验证工程深度与可测试性）

### 1.4 核心使用场景

用户向 CodeGuard 提交一个 Python 项目的修复任务（如“修正 `calculator.py` 中失败的加法函数”），CodeGuard 自动执行多轮循环：  
**读取项目 → 修改代码 → 运行测试 → 根据反馈调整**，所有动作经过风险分级，危险操作被拦截或等待审批。

---

## 2. 核心能力拆解

### 2.1 工具清单（P0 核心集）

| 工具             | 技术实现                                                            | 验收方式                                      |
| ---------------- | ------------------------------------------------------------------- | --------------------------------------------- |
| `list_directory` | `pathlib.Path` + 路径沙箱检查，返回文件/目录列表（过滤敏感项）      | 路径沙箱类 Mock 测试                          |
| `read_file`      | 路径沙箱 + 大小限制（默认 100KB），只读文本文件                     | 同上                                          |
| `write_file`     | 路径沙箱 + 备份原内容（`.bak`）+ 生成 diff                          | 同上                                          |
| `edit_file`      | 基于 `str.replace` 精确替换（或 `difflib` 生成 patch）              | 同上                                          |
| `run_command`    | 白名单命令 + 禁止连接符正则（`[;&                                   | >]`），使用 `subprocess.run` 且 `shell=False` | 命令沙箱类 Mock 测试 |
| `run_pytest`     | 专门执行 `pytest`，设置超时（默认 30s），捕获 stdout/stderr、退出码 | 命令沙箱 + 超时测试                           |
| `finish`         | 主循环停机信号，附带完成摘要                                        | 停机逻辑类 Mock 测试                          |

### 2.2 工具分类验收框架

- **文件工具**（list/read/write/edit）统一经过 `is_path_allowed()` 检查，禁止访问外部路径、敏感文件（`.env`、`.git/`、`*.pem`、`*.key`）。
- **命令工具**（run_command / run_pytest）经过 `is_command_allowed()` 检查，禁止 Shell 控制符、禁止网络命令（`curl`、`wget`、`ssh`）。
- **停机工具**（finish）无需安全检查，直接触发循环终止。

### 2.3 安全拦截两阶段

1. **预执行验证（Validation Layer）**：检查动作格式、参数合法性、路径/命令是否命中黑名单。  
2. **风险分级（Risk Layer）**：对合法动作定级（LOW/MEDIUM/HIGH/FORBIDDEN），FORBIDDEN 直接拦截，HIGH 进入人工审批，LOW/MEDIUM 自动执行并记录。

---

## 3. 系统边界

### 3.1 第一版绝对不做（10 条红线）

| #   | 边界红线                   | 理由                                                                         |
| --- | -------------------------- | ---------------------------------------------------------------------------- |
| 1   | 不支持任意 Shell 命令      | 仅白名单命令（`python`, `pytest`, `ruff`, `mypy`, `git diff`, `git status`） |
| 2   | 不支持网络访问             | 拦截 `curl`/`wget`/`scp`/`ssh`，且环境变量清理 `PATH` 仅保留必要路径         |
| 3   | 不支持自动 git commit/push | 课程要求，且避免意外污染远程仓库                                             |
| 4   | 不支持多 Agent 协作        | 课程要求                                                                     |
| 5   | 不支持任意编程语言         | 仅 Python 项目（`pytest` 作为测试框架）                                      |
| 6   | 不支持自动部署             | 课程要求                                                                     |
| 7   | 不支持操作系统级沙箱       | 使用路径沙箱 + 命令白名单作为轻量替代                                        |
| 8   | 不支持向量数据库           | 简单记忆使用 JSON 文件或内存对象                                             |
| 9   | 不支持任意文件类型         | 仅允许 `.py`, `.json`, `.toml`, `.md` 等文本文件；禁止二进制文件             |
| 10  | 不提供 WebUI               | 仅 CLI 交互（人工审批通过终端输入 Y/N）                                      |

### 3.2 超出边界的响应策略

- 若 LLM 返回的动作超出支持范围（如请求 `run_command` 但命令不在白名单），Validation 层返回“不支持的动作”错误，反馈给 LLM 要求重试。
- 若路径指向外部或敏感文件，拦截并反馈“路径被禁止”。

---

## 4. 架构分层设计

### 4.1 五层架构总览
User Task → Context Builder → LLM → Parser → Validation → Risk → Approval → Execute → Feedback → Context Update → (loop)

text

各层职责如下：

- **Context Builder**：组装系统提示、历史动作、测试结果、记忆等。
- **LLM 抽象层**：可插拔，支持真实 OpenAI API 和 MockLLM（预设响应序列）。
- **Parser**：将 LLM 输出解析为结构化动作（JSON），检查字段完整性。
- **Validation**：对动作的参数进行合法性校验（路径、命令、文件类型等）。
- **Risk Assessor**：根据预定义规则进行风险分级。
- **Approval Manager**：高风险动作向用户请求批准/拒绝，支持超时和取消。
- **Executor**：实际执行工具操作，返回 `ToolResult`（包含成功/失败、stdout/stderr、退出码、diff 等）。
- **Feedback Processor**：将 `ToolResult` 转换为供 LLM 理解的文本反馈，并更新上下文。

### 4.2 各层函数签名（Python 类型示意）

| 层         | 函数签名                                                     | 职责                                                  |
| ---------- | ------------------------------------------------------------ | ----------------------------------------------------- |
| Parser     | `parse_llm_output(raw: str) -> ParseResult`                  | 解析 JSON，验证 action 字段存在，参数完整             |
| Validation | `validate_action(parsed: ParseResult) -> ValidationResult`   | 路径沙箱检查、命令白名单检查、敏感文件黑名单          |
| Risk       | `assess_risk(validated: ValidationResult) -> RiskDecision`   | 返回风险等级及触发规则                                |
| Approval   | `request_approval(decision: RiskDecision) -> ApprovalResult` | 阻塞等待用户输入 Y/N/超时，返回审批结果               |
| Execute    | `execute_tool(action: str, params: dict) -> ToolResult`      | 调用具体工具实现，捕获异常                            |
| Feedback   | `build_feedback(result: ToolResult) -> str`                  | 生成自然语言反馈，附加结构化数据（如 diff、测试统计） |

### 4.3 Governance Layer 风险分级逻辑（代码规则）

- **LOW**：`list_directory`, `read_file`（非敏感文件），`git status`, `git diff`  
  → 自动执行，记录审计日志。
- **MEDIUM**：`write_file`, `edit_file`（普通代码文件），`run_pytest`，`ruff`, `mypy`  
  → 自动执行，但必须保存 diff/备份，并详细记录输入输出。
- **HIGH**：`write_file` 覆盖大于 10KB 的文件，`run_command` 包含 `install`、`commit`，删除文件（`rm` 不在白名单，但若 LLM 误生成则视为 HIGH）  
  → 暂停，请求人工审批。
- **FORBIDDEN**：路径包含 `..` 或绝对外部路径，读取 `.env`/`.pem`/`.key`，命令含 `rm -rf /`、`shutdown`、`drop database`、`curl`/`wget` 等网络命令，包含 Shell 控制符（`;`、`|`、`&`、`>`、`<`）  
  → 直接拦截，不允许人工批准绕过。

### 4.4 停机条件与优先级

停机判断由主循环负责，按以下优先级（高→低）：
1. LLM 返回 `{"action": "finish"}` → 正常结束。
2. 所有测试通过且用户任务明确声明“测试全部通过即完成”（可通过配置开关）。
3. 达到最大步数（默认 10）→ 强制停止。
4. 用户主动按下 `Ctrl+C` → 优雅退出。
5. 连续 3 次解析失败或连续 3 次相同无效动作 → 视为死循环，停止。
6. 发生不可恢复错误（如工作目录不存在）→ 停止。

---

## 5. 安全设计（威胁建模）

### 5.1 正向攻击防护

| 攻击类型                 | 防护层           | 防护方式                                                             | 状态                              |
| ------------------------ | ---------------- | -------------------------------------------------------------------- | --------------------------------- |
| 路径遍历（`../`）        | 路径沙箱         | `Path.resolve()` + `os.path.commonpath()` 检查是否在 workspace 内    | P0                                |
| 危险 Shell 注入          | 命令沙箱         | 禁止 Shell 控制符正则 `[;&                                           | ><]`；使用 `shell=False` 参数列表 | P0 |
| 读取敏感文件（`.env`）   | 黑名单前缀       | `BLOCKED_PATTERNS = (".env", ".git", "*.pem", "*.key")` 优先于白名单 | P0                                |
| 磁盘填充（写入超大文件） | Tool 层          | `MAX_FILE_SIZE = 100_000`（字节），超限拒绝                          | P0                                |
| 篡改 `.git/`             | 黑名单优先       | 任何路径包含 `.git/` 直接拒绝                                        | P0                                |
| 环境变量泄露             | Tool 层          | `subprocess.run` 使用 `env={"PATH": os.environ["PATH"]}` 清理环境    | P0                                |
| 命令超时 & 无限循环      | Tool 层 + 主循环 | `run_command` 设置 `timeout=30`；主循环最大步数限制                  | P0                                |

### 5.2 侧信道攻击（已知风险）

| 攻击类型                   | 当前状态                     | 计划                                                 |
| -------------------------- | ---------------------------- | ---------------------------------------------------- |
| TOCTOU（符号链接替换）     | 第一版放过，仅记录风险       | P2 加 `os.open(..., O_NOFOLLOW)` + `stat()` 二次验证 |
| 时序竞争（如多次写入并发） | 第一版放过                   | P2 引入文件锁                                        |
| 日志泄露敏感信息           | 审计日志过滤器已屏蔽 API Key | 持续加固                                             |

---

## 6. 功能优先级（MoSCoW）

### 6.1 P0 — 没有就不能跑（核心骨架）

- 手写 Agent 主循环（`while` 循环，含上下文管理、LLM 调用、解析、分发、反馈、停机判断）。
- LLM 抽象层（支持 `MockLLM` 和 `OpenAILLM`，可注入）。
- Parser 层：`parse_llm_output` 正确解析 JSON，错误时返回 ParseError。
- 路径沙箱：`is_path_allowed(path)` 检查绝对路径是否在 workspace 内且不匹配黑名单。
- 命令沙箱：`is_command_allowed(cmd)` 检查命令是否在白名单且无禁止符。
- 基础工具栏：`list_directory`, `read_file`, `write_file`, `edit_file`, `run_command`（仅白名单），`finish`。
- `run_pytest` 作为独立工具（或作为 `run_command` 的特殊案例）。
- 最大步数限制和连续无效动作检测（死循环保护）。
- Keyring 密钥管理（首次录入、查看状态、更新、清除）。

### 6.2 P1 — 核心价值（安全与反馈）

- 风险分级器：基于规则（代码硬编码或配置文件）返回 `RiskLevel`。
- HITL 人工审批：`HIGH` 级别动作阻塞等待用户输入（终端交互）。
- FORBIDDEN 级别直接拦截，反馈给 LLM 解释原因。
- 审计日志：结构化 JSON 记录每轮 step、动作、风险等级、审批结果、执行结果（不记录 API Key）。
- 反馈闭环：测试失败/命令错误信息清晰回灌，驱动 LLM 修正。
- 配置文件（`config.toml`）：支持 workspace、max_steps、命令白名单、敏感文件列表、超时等。

### 6.3 P2 — 加分项（增强体验与加固）

- 审计日志 HTML 导出。
- 配置文件热加载（`watchdog`）。
- TOCTOU 防护（符号链接验证）。
- 文件写入大小可配置。
- 多会话历史日志（按时间戳存储）。
- CI/CD（GitHub Actions 自动运行测试并构建 Docker 镜像）。

---

## 7. 验收标准（确定性剧本）

### 7.1 剧本 1：拦截危险命令（命令越狱）

- **前置**：MockLLM 预置响应序列  
  Step 1: `{"action": "run_command", "params": {"command": "pytest; rm -rf /"}}`  
  Step 2: `{"action": "finish"}`
- **预期**：
  - Validation 层检测到禁止符 `;`，返回 `FORBIDDEN`。
  - `subprocess.run` 未被调用。
  - 审计日志记录拦截事件。
  - LLM 收到反馈：“命令包含禁止字符，已拦截”。
- **断言**：`subprocess.run.call_count == 0`，且主循环在 Step 2 正常结束。

### 7.2 剧本 2：高风险人工审批（HITL 弹窗）

- **前置**：MockLLM 预置响应  
  Step 1: `{"action": "write_file", "params": {"path": "src/config.py", "content": "SECRET=123"}}`  
  Step 2: `{"action": "finish"}`
- **预期**：
  - Risk 层判定为 `HIGH`（因写入文件大于阈值或路径敏感？实际可配置为 HIGH）。
  - 程序暂停，打印审批请求，等待用户输入 `Y` 或 `N`。
  - 若输入 `N`，文件未被写入，审计日志记录“用户拒绝”。
  - 若输入 `Y`，文件正确写入，且备份生成。
- **断言**：审批结果与文件实际修改状态一致。

### 7.3 剧本 3：反馈闭环（修改→测试→通过）

- **前置**：MockLLM 预置响应  
  Step 1: `{"action": "read_file", "params": {"path": "src/calculator.py"}}`  
  Step 2: `{"action": "write_file", "params": {"path": "src/calculator.py", "content": "def add(a,b): return a+b"}}`  
  Step 3: `{"action": "run_command", "params": {"command": "pytest tests/test_calculator.py"}}`  
  Step 4: `{"action": "finish"}`
- **预期**：
  - Step 3 中 `run_command` 执行 pytest，返回 `exit_code=0`。
  - 反馈包含“所有测试通过”。
  - Step 4 收到 `finish`，主循环结束。
- **断言**：最终文件内容正确，pytest 被调用且退出码为 0。

---

## 8. 用户故事（INVEST 原则）

1. **作为用户，我希望 CodeGuard 能列出项目目录下的文件**，以便 Agent 了解项目结构。  
   *验收*：仅显示 workspace 内文件，自动隐藏 `.git`、`.env`、`__pycache__` 等。

2. **作为用户，我希望 Agent 能读取源代码文件**，以便分析待修改内容。  
   *验收*：只能读取文本文件，大小不超过 100KB，禁止读取 `.env` 等敏感文件。

3. **作为用户，我希望 Agent 能修改代码文件**，并保留修改前后的 diff。  
   *验收*：修改前自动备份（`.bak`），生成 unified diff 记录，并写入审计日志。

4. **作为用户，我希望 Agent 能运行 pytest**，以验证修改是否正确。  
   *验收*：pytest 输出（包括失败详情）被捕获并回灌给 LLM；超时（30s）被强制终止。

5. **作为用户，我希望高风险操作（如写入大文件或执行安装命令）能暂停并请求我的批准**。  
   *验收*：终端显示动作详情、风险原因，等待我输入 Y/N，超时后自动拒绝。

6. **作为用户，我希望系统能无条件拦截极度危险操作（如 `rm -rf /`、读取 SSH 私钥）**，绝不执行。  
   *验收*：拦截后反馈给 Agent，审计日志永久记录，且无法通过审批绕过。

7. **作为用户，我希望查看 CodeGuard 的完整执行记录**，以便审计每步动作。  
   *验收*：审计日志以 JSON 格式存储每轮 step，含时间戳、动作、风险等级、审批结果、执行结果（不包含密钥）。

---

## 9. 功能规约（按模块详述）

### 9.1 Agent 主循环

- **输入**：用户任务（字符串）、workspace 路径、配置（`Config` 对象）。
- **行为**：
  1. 初始化上下文（系统提示、任务描述、记忆）。
  2. 循环 `step = 1..max_steps`：
     - 调用 LLM（或 Mock）获取动作 JSON。
     - 解析并验证。
     - 风险分级 → 审批（若 HIGH）或拦截（若 FORBIDDEN）。
     - 执行工具 → 得到 `ToolResult`。
     - 生成反馈，更新上下文。
     - 检查停机条件。
  3. 停止后输出摘要。
- **输出**：最终状态（成功/失败/超时/用户取消）、修改文件列表、测试结果。
- **边界条件**：`max_steps` 默认为 10；连续无效动作超过 3 次强制停止。
- **错误处理**：任何层抛出异常均捕获，记录日志并尝试反馈给 LLM 重试，若连续失败则停止。

### 9.2 工具模块

每个工具都接受 `params` 字典，返回 `ToolResult`（含 `success: bool`, `data: Any`, `error: str`, `meta: dict`）。

- **list_directory**  
  - 参数：`{"path": str, "depth": int}`（depth 默认 1）。  
  - 行为：返回目录下文件和子目录列表，过滤黑名单模式。  
  - 边界：不允许深度 > 3，防止递归爆炸。  
  - 错误：路径不在 workspace 内 → 返回错误。

- **read_file**  
  - 参数：`{"path": str, "start_line": int, "end_line": int}`。  
  - 行为：读取文件内容，若指定行号则截取片段。  
  - 边界：文件大小超过 `max_file_size` → 拒绝；二进制文件 → 拒绝。  
  - 错误：路径黑名单命中 → 返回“禁止读取”。

- **write_file**  
  - 参数：`{"path": str, "content": str}`。  
  - 行为：若文件存在，先备份为 `{path}.bak`；写入新内容；计算 diff。  
  - 边界：文件大小超限 → 拒绝；路径不在 workspace 或命中黑名单 → 拒绝。  
  - 错误：磁盘空间不足 → 返回错误。

- **edit_file**  
  - 参数：`{"path": str, "old_str": str, "new_str": str}`。  
  - 行为：读取文件，替换所有出现的 `old_str` 为 `new_str`，写回。  
  - 边界：若 `old_str` 不存在，返回错误；路径检查同 `write_file`。  
  - 错误：替换后文件大小超限 → 回滚。

- **run_command**  
  - 参数：`{"command": str}`（完整命令字符串，但内部解析为列表）。  
  - 行为：解析命令名称和参数；检查白名单和禁止符；使用 `subprocess.run` 执行，超时。  
  - 边界：仅允许 `python`, `pytest`, `ruff`, `mypy`, `git diff`, `git status`；禁止网络命令。  
  - 错误：命令不在白名单 → 返回“命令不允许”。

- **run_pytest**（可独立实现，也可复用 run_command）  
  - 参数：`{"args": str}`（如 `tests/test_add.py -v`）。  
  - 行为：调用 `pytest`，捕获输出，解析通过/失败数量。  
  - 边界：超时 30s；禁止添加危险参数（如 `--pdb`）。  
  - 错误：pytest 未安装 → 返回错误。

- **finish**  
  - 参数：`{"summary": str}`（可选）。  
  - 行为：返回停机信号，附带摘要。

### 9.3 记忆模块

- **数据**：当前任务描述、历史动作列表（最多 20 条）、最后测试结果、用户审批记录、工作目录、配置项。
- **存储**：内存字典 + 持久化到 JSON 文件（`codeguard_memory.json`）。
- **上下文提供**：每次构造提示时，将最近的 5 条历史动作和测试结果注入系统提示，避免全量载入。

### 9.4 配置模块

- 配置文件 `config.toml`（示例见附录 C）。
- 支持项：`workspace`, `max_steps`, `command_timeout`, `max_file_size`, `allow_network`, `allowed_commands`, `protected_files`, `risk_levels`（可自定义）。
- 启动时读取，若缺失则使用默认值；提供 `Config` 类管理。

---

## 10. 非功能性需求

### 10.1 安全性

- 所有 API Key 通过操作系统 keyring 存储（Windows Credential Manager / macOS Keychain / Linux Secret Service），不写入文件、日志或环境变量。
- 审计日志过滤任何可能包含密钥的字段。
- 命令执行清理环境变量，仅保留 `PATH`，阻断网络代理泄露。

### 10.2 可观测性

- 结构化日志（JSON 格式）记录每步动作、风险判断、审批结果、工具输出。
- 支持 `--verbose` 模式打印详细调试信息。
- 终端彩色输出区分动作类型和风险等级。

### 10.3 可用性

- 首次运行通过交互式引导录入 API Key（`codeguard setup`）。
- 错误信息简明，提供解决建议（如“请检查 pytest 是否安装”）。
- README 包含快速开始、安装步骤、配置示例。

### 10.4 性能

- 路径沙箱判断时间 < 1ms。
- 命令执行超时默认 30s，可配置。
- 文件读取大小限制防止 OOM。
- 主循环最大步数 10，保证响应时间可控。

---

## 11. 系统架构

### 11.1 组件图
+-------------------+ +-------------------+ +-------------------+
| CLI/UI |------>| AgentOrchestrator |------>| LLMAdapter |
| (交互式输入/输出) | | (主循环) | | (OpenAI/Mock) |
+-------------------+ +-------------------+ +-------------------+
|
v
+-------------------+
| GovernanceLayer |
| (Parser/Validation|
| /Risk/Approval) |
+-------------------+
|
v
+-------------------+
| ToolExecutor |
| (文件/命令/pytest) |
+-------------------+
|
v
+-------------------+
| Memory & Logging |
| (JSON/Keyring) |
+-------------------+

text

### 11.2 数据流

1. 用户通过 CLI 输入任务 → `AgentOrchestrator`。
2. `AgentOrchestrator` 构建上下文 → 调用 `LLMAdapter`。
3. `LLMAdapter` 返回原始字符串 → 传入 `Parser` 得到结构化动作。
4. 动作经 `Validation` 检查 → 若有效则进入 `Risk` 分级。
5. 高风险 → `Approval` 模块等待用户输入；FORBIDDEN → 直接拦截。
6. 通过 → `ToolExecutor` 执行，返回 `ToolResult`。
7. `ToolResult` 转换为反馈，追加到上下文。
8. 循环直至停机条件满足。

### 11.3 外部依赖

- **LLM 供应商**：OpenAI API（可替换为其他兼容接口）。
- **Python 标准库**：`pathlib`, `subprocess`, `json`, `logging`, `keyring`。
- **第三方库**：`pytest`（测试框架）、`python-dotenv`（用于加载环境变量，但推荐 keyring）、`tomli`（解析 TOML）。

---

## 12. 数据模型

| 实体                 | 字段                                                                                                                                                  | 说明           |
| -------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- | -------------- |
| **Action**           | `type: str` (工具名), `params: dict`, `reason: str`                                                                                                   | LLM 产生的动作 |
| **ParseResult**      | `action: Action`, `error: str`                                                                                                                        | 解析结果       |
| **ValidationResult** | `valid: bool`, `reason: str`, `sanitized_params: dict`                                                                                                | 校验结果       |
| **RiskDecision**     | `level: RiskLevel`, `rule: str`, `needs_approval: bool`                                                                                               | 风险分级结果   |
| **ApprovalResult**   | `approved: bool`, `user: str`, `timestamp: datetime`                                                                                                  | 审批记录       |
| **ToolResult**       | `success: bool`, `data: any`, `error: str`, `meta: dict`（含 `diff`, `exit_code`, `stdout`, `stderr`）                                                | 工具执行结果   |
| **Memory**           | `task: str`, `history: List[Action]`, `last_test_result: ToolResult`, `approvals: List[ApprovalResult]`, `step_count: int`                            | 会话记忆       |
| **AuditLog**         | `step: int`, `timestamp: datetime`, `action: Action`, `risk_level: str`, `approval: ApprovalResult`, `tool_result: ToolResult`, `final_decision: str` | 审计日志条目   |

关系：一个会话包含一个 Memory，Memory 关联多个 AuditLog。

---

## 13. 凭据与分发设计

### 13.1 API Key 安全存储

- **威胁模型**：源码泄露、Git 历史泄露、日志泄露、进程环境窥探、终端历史泄露。
- **对策**：
  - 使用 `keyring` 库存储密钥（Windows Credential Manager / macOS Keychain / Linux Secret Service）。
  - 首次运行 `codeguard setup` 引导用户输入密钥，并保存到 keyring。
  - `codeguard status` 只显示“已配置”或“未配置”，不返回明文。
  - `codeguard clear` 删除密钥。
  - 禁止将密钥写入 `.env` 或配置文件，环境变量仅作为备选（并在文档中说明明文风险）。
- **实现**：`KeyringManager` 类封装 `get`, `set`, `delete`，使用 `service_name="codeguard"`。

### 13.2 分发形态

- **首选**：PyPI 包（`pip install codeguard`），CLI 工具。
- **备选**：Docker 镜像（`docker run -it codeguard`），便于跨平台。
- **目标平台**：Windows / macOS / Linux（Python 3.10+）。
- **首次运行**：用户需执行 `codeguard setup` 配置工作目录和 API Key；或通过环境变量 `OPENAI_API_KEY`（但文档明确风险）。

### 13.3 目标机安全配置

- 建议用户在专用项目目录使用，避免对系统目录操作。
- 配置文件中 `workspace` 强制定向，防止 Agent 越权。

---

## 14. 技术选型与理由

| 技术             | 选型理由                                                                  |
| ---------------- | ------------------------------------------------------------------------- |
| **Python 3.10+** | 广泛用于 AI 生态，丰富的标准库（`pathlib`, `subprocess`），便于快速实现。 |
| **OpenAI API**   | 主流 LLM 接口，稳定可靠，便于教学演示。                                   |
| **MockLLM**      | 内置预设响应，实现确定性测试。                                            |
| **pytest**       | Python 标准测试框架，与项目测试要求一致。                                 |
| **keyring**      | 跨平台凭据管理，符合课程“安全存储”要求。                                  |
| **tomli**        | 解析 TOML 配置文件（Python 3.11 后可内置 `tomllib`）。                    |
| **Docker**       | 提供容器化分发，确保环境一致性。                                          |

---

## 15. 领域与机制设计（AI4SE 专项要求）

### 15.1 领域分析（Coding）

- **反馈信号**：pytest 退出码、测试通过/失败数量、命令退出码、文件修改是否成功、diff 是否存在。这些信号客观、可计算，不依赖 LLM 解释。
- **危险动作**：删除文件、读取 `.env`/私钥、执行 `rm -rf`、网络请求、修改 `.git/`、Shell 命令拼接。
- **所需工具**：文件列表、读取、写入、编辑、运行测试、执行白名单命令、停机。
- **记忆需求**：当前任务、最近 5 步动作、测试结果、审批记录；无需向量检索，仅简单键值存储。

### 15.2 重点维度：治理护栏（Governance Layer）

- **为何选择**：安全是 Coding Agent 落地的核心痛点，治理护栏天然由代码构成，可独立测试，最符合课程“机制必须是代码”的要求。
- **实现策略**：
  - **硬编码规则 + 配置文件**：黑名单（敏感文件、Shell 控制符）、白名单（命令、文件扩展名）均为代码常量，可配置化但默认值牢固。
  - **分层验证**：先校验语法，再校验路径/命令，最后风险分级，每层可单独单元测试。
  - **HITL 状态机**：审批逻辑实现为同步阻塞，带超时和取消，保证用户控制权。
- **测试覆盖**：使用 MockLLM 注入危险动作，验证拦截/审批流程，无需真实 LLM。

---

## 16. 风险与未决问题

| 风险                              | 影响                   | 缓解措施                                                       |
| --------------------------------- | ---------------------- | -------------------------------------------------------------- |
| 符号链接绕过路径沙箱（TOCTOU）    | 可能访问外部文件       | 第一版记录风险，P2 增加 `O_NOFOLLOW` 和 `stat()` 二次检查      |
| 配置错误导致 workspace 设置过宽   | Agent 意外修改系统文件 | 文档强调使用专用目录；首次运行检查 workspace 是否为系统根目录  |
| pytest 超时或卡死                 | Agent 循环阻塞         | 设置 `timeout`，超时后终止进程并返回错误                       |
| LLM 反复请求被拦截动作            | 浪费步数，死循环       | 连续 3 次相同拦截动作后强制停止                                |
| keyring 在某些 Linux 环境下不可用 | 无法安全存储密钥       | 备选方案：加密文件（如 `cryptography` 库）并提示用户保管主密码 |

---

## 附录 A：架构决策记录（ADR）

| ADR     | 决策                                                         | 理由                                                         |
| ------- | ------------------------------------------------------------ | ------------------------------------------------------------ |
| ADR-001 | 手写 `while` 主循环，禁止使用 LangChain AgentExecutor 等框架 | 确保主循环完全受控，便于插桩测试，符合“自己实现 harness”要求 |
| ADR-002 | MockLLM 优先用于测试，真实 API 仅用于集成验证                | 保持单元测试确定性、快速、无费用                             |
| ADR-003 | Keyring 作为密钥存储首选，拒绝明文                           | 满足课程凭据安全要求，防止泄露                               |
| ADR-004 | 黑名单优先于白名单的路径检查                                 | 先拒绝已知危险（如 `.env`），再允许常规文件，安全优先        |
| ADR-005 | `pytest exit_code == 0` 不自动停机，除非用户明确要求         | 停机条件需用户声明，避免意外停止                             |
| ADR-006 | 拒绝动作时返回硬编码错误模板，不生成 LLM 建议                | 防止 LLM 幻觉，保持确定性                                    |

---

## 附录 B：核心伪代码（主循环）

```python
def run_agent(task: str, config: Config):
    context = build_initial_context(task, config)
    memory = Memory(config)
    step = 0
    consecutive_failures = 0

    while step < config.max_steps:
        step += 1
        raw = llm.next_action(context)
        parse_result = parse_llm_output(raw)
        if parse_result.error:
            context.append(f"Parse error: {parse_result.error}")
            consecutive_failures += 1
            if consecutive_failures >= 3: break
            continue

        action = parse_result.action
        # Validation
        val_result = validate_action(action, config)
        if not val_result.valid:
            context.append(f"Invalid action: {val_result.reason}")
            consecutive_failures += 1
            if consecutive_failures >= 3: break
            continue

        # Risk assessment
        risk = assess_risk(val_result, config)
        if risk.level == FORBIDDEN:
            result = ToolResult(success=False, error="Action forbidden", meta={"blocked": True})
        elif risk.level == HIGH:
            approval = request_approval(action, risk)
            if not approval.approved:
                result = ToolResult(success=False, error="User rejected", meta={"blocked": True})
            else:
                result = execute_tool(action)
        else:
            result = execute_tool(action)

        # Feedback and context update
        feedback = build_feedback(result)
        memory.add(action, result)
        context.append(feedback)

        # Check stop conditions
        if action.type == "finish": break
        if all_tests_passed and config.auto_finish: break
        if result.success and result.meta.get("exit_code") == 0 and action.type == "run_pytest": # 可配置
            pass

    return memory.summarize()
```