# AGENT_LOG — CodeGuard 关键过程日志

> 记录从项目初始化到最终交付的关键节点，每条约 2-3 行。日期范围：2026-08-07 至 2026-08-12。

---

## 1. 项目初始化 — 2026-08-07

- **触发**：`@opencode` 执行 T00-T01，创建 `pyproject.toml`（依赖 keyring / tomli / openai），搭建 `src/` 与 `tests/` 骨架目录。
- **干预**：手动确认依赖列表，Python 3.10 需 `tomli` 回退（3.11+ 内置 `tomllib`），在 `pyproject.toml` 中声明 `requires-python = ">=3.10"`。
- **教训**：项目脚手架应优先创建 `__init__.py` 和 `pyproject.toml`，确保 `pytest` 能在空目录下正确收集测试。

---

## 2. 护栏实现 — 2026-08-08

- **触发**：`@opencode` 实现 `guardrail.py` 的命令白名单（`_ALLOWED_COMMANDS`）与禁止符检测（`;` / `&&` / `||` / `|`），四级风险分级（LOW / MEDIUM / HIGH / FORBIDDEN）。
- **干预**：旧版 `evaluate()` 包装器标记为 `@deprecated`，统一走 `validate_action → assess_risk` 新路径；初始测试 39 个全部通过。
- **教训**：向后兼容包装器需明确标注生命周期，避免技术债务堆积；禁止符检测应使用正则而非 `str.find()`，防止误判引号内的合法字符。

---

## 3. 主循环调试 — 2026-08-09

- **触发**：`@opencode` 实现 `agent.py` 的 while 循环（`run()` 函数），包含死循环保护（连续 3 次相同动作停机）、解析失败重试（最多 3 次）、上下文回灌。
- **干预**：修复上下文无限膨胀问题——`Memory.add_history()` 中添加截断策略（保留最近 20 条记录）；修复 `LLMClient` 导入错误（`RealLLM` 类名）；修复 `request_approval` 被双重评估的 Bug。
- **教训**：函数签名变更后需全局 grep 确认所有调用点已同步；Agent 上下文中不应直接追加原始工具输出，应通过 `build_feedback()` 构建摘要后再加入。

---

## 4. 测试增强 — 2026-08-10

- **触发**：根据安全审计建议，补齐抗攻击增强测试：大小写绕过（`RM -RF /` → 修复 `guardrail.py` 正则添加 `re.IGNORECASE`）、空路径拒绝（`read_file("")` → 修复 `tools.py` 增加空路径检查）、合法重复动作不误杀（`read_file` 不同路径 → 修复 `agent.py` 死循环检测改为追踪 `(action, frozenset(params))` 组合）。
- **干预**：`write_file` 增加 `config` 参数和 `max_file_size` 检查；`tools.py` 中 `_is_inside_workspace` 增加相对路径拼接（`os.path.join(workspace, path)`），与 `validation.py` 行为一致。
- **教训**：安全测试必须覆盖大小写、空白字符、参数组合等边界；防御代码不应假设输入总是"干净的"。

---

## 5. 演示验收 — 2026-08-11

- **触发**：实现并调试 `demo.py`（三机制演示：拦截 / 审批拒绝 / 反馈修正）与 `test_demo.py`（端到端集成测试），使用 MockLLM 驱动，不联网。
- **干预**：修复相对路径解析 Bug——`demo_feedback_loop` 中 `write_file("src/add.py", ...)` 因 `Path(path)` 只相对于 CWD 解析导致文件未写入，修复为 `if not os.path.isabs(path): path = os.path.join(workspace, path)` 应用于 `write_file` / `read_file` / `list_files` / `edit_file` 四个函数；新增 guardrail 规则：大文件写入（>10KB）标记为 HIGH 风险。
- **教训**：工具函数中的路径解析必须与 workspace 绑定，不能依赖 CWD；端到端测试应覆盖真实文件系统操作，而不仅仅是 mock 返回值。

---

## 6. CI 配置 — 2026-08-12

- **触发**：创建 `.github/workflows/ci.yml`，配置 `unit-test` job（Python 3.10 / 3.11 双版本矩阵），通过 `push` 和 `pull_request` 触发。
- **干预**：验证 `requirements.txt` 包含所有依赖（keyring / tomli / openai / pytest / pytest-cov / flask）；确认 `pyproject.toml` 中 `pythonpath = ["."]` 使 `pytest` 能正确发现 `src/` 模块。
- **教训**：CI 配置应在项目早期（而非末期）完成，以便每次提交自动验证；`pytest-cov` 覆盖率报告能帮助发现未被测试覆盖的代码路径。

---

## 统计

| 指标 | 数值 |
|------|------|
| 总测试数 | 385 |
| 通过 | 385 |
| 跳过 | 1 |
| 源文件 | 16 |
| 测试文件 | 19 |
| 关键干预次数 | 7 |
| 开发周期 | 2026-08-07 至 2026-08-12（6 天） |

---

*文档版本：2.0*
*最后更新：2026-08-12*