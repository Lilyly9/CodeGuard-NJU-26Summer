# PLAN.md 审查报告

> 审查日期：2026-08-10  
> 审查对象：`docs/PLAN.md` vs `docs/SPEC.md`  
> 审查维度：完整性、一致性、SPEC 对齐、TDD 纪律、技术正确性

---

## 1. 🔴 严重问题（Critical）

### C-01：`edit_file` 工具在 PLAN 中完全缺失

- **涉及任务**：T06（文件工具）
- **问题描述**：SPEC §2.1 工具清单明确列出 `edit_file` 作为 P0 核心工具（基于 `str.replace` 精确替换），SPEC §6.1 P0 清单也包含 `edit_file`。但 PLAN 的 T06 只实现了 `list_files`、`read_file`、`write_file` 三个文件工具，`edit_file` 没有任何实现任务对应。文件结构映射表（第一部分）的 `tools.py` 注释也只写了"六大工具"，实际列出的 6 个名称中不包含 `edit_file`。
- **修正建议**：在 T06 中增加 `edit_file` 的实现，或在 T06 之后新增一个子任务专门实现 `edit_file`。参数：`{"path": str, "old_str": str, "new_str": str}`，行为：`read_file` → `str.replace` → `write_file`，边界：`old_str` 不存在时返回错误，替换后超大小回滚。

### C-02：路径沙箱使用 `startswith` 存在绕过漏洞

- **涉及任务**：T04（路径沙箱），第 86 行
- **问题描述**：T04 的 `is_path_allowed` 实现中使用 `str(resolved).startswith(str(Path(workspace).resolve()))` 检查路径是否在 workspace 内。这是已知的绕过模式：当 workspace 为 `/tmp/ws` 时，路径 `/tmp/ws-extra/../etc/passwd` 经过 `resolve()` 后变成 `/tmp/ws-extra/etc/passwd`，`startswith("/tmp/ws")` 返回 **True**，但实际路径在 workspace 之外。SPEC §5.1 明确要求使用 `os.path.commonpath()` 进行比较。
- **修正建议**：将 `startswith` 改为 `os.path.commonpath`：
  ```python
  import os
  ws_resolved = os.path.realpath(workspace)
  path_resolved = os.path.realpath(os.path.join(workspace, path))
  if os.path.commonpath([ws_resolved, path_resolved]) != ws_resolved:
      return False
  ```

### C-03：课程要求的交付文档（`SPEC_PROCESS.md`、`AGENT_LOG.md`、`REFLECTION.md`）在 PLAN 中缺失

- **涉及任务**：无对应任务
- **问题描述**：课程《通用要求》§4.3 通常要求提交过程文档（如会议记录、需求变更日志、反思报告）。SPEC.md 顶部引用了"相关文档：[通用要求]、[AI4SE_Coding_Agent_Harness]、[CodeGuard 项目要求]"，但 PLAN 中没有为 `SPEC_PROCESS.md`、`AGENT_LOG.md`、`REFLECTION.md` 等文档创建任何任务。如果课程要求提交这些文档，它们应该是明确的交付物任务。
- **修正建议**：在阶段 12（配置完善）中新增任务 T26，创建 `docs/SPEC_PROCESS.md`（记录 Brainstorm 过程与决策）、`docs/AGENT_LOG.md`（Agent 运行日志示例）、`docs/REFLECTION.md`（项目反思）。或者先确认课程是否要求这些文档，若不需要则忽略。

---

## 2. 🟡 警告与矛盾（Warnings）

### W-01：Risk 分级未覆盖 `run_command` 含 `install`/`commit` 的 HIGH 场景

- **涉及任务**：T12（Risk 分级），SPEC §4.3
- **问题描述**：SPEC 第 4.3 节规定 HIGH 风险包括 `run_command` 包含 `install`、`commit` 等操作。但 PLAN T12 的 `assess_risk` 实现中，`run_command` 统一走 MEDIUM（除非内容超大小进入 HIGH），没有对 `install`/`commit` 关键词做特殊检查。这意味着 LLM 请求 `pip install` 或 `git commit` 时只会被标记为 MEDIUM 自动执行，不会触发 HITL 审批。
- **修正建议**：在 T12 的 `assess_risk` 函数中增加对 `run_command` 参数的二次检查：
  ```python
  if action == "run_command":
      command = params.get("command", "")
      if any(kw in command for kw in ["install", "commit", "push"]):
          return RiskDecision(level="HIGH", rule="Dangerous command keyword", needs_approval=True)
  ```

### W-02：`execute_tool` 函数签名缺少 `config` 参数，但内部使用 `config`

- **涉及任务**：T14（Executor），第 124 行
- **问题描述**：T14 的 `execute_tool` 函数签名定义为 `def execute_tool(action: str, params: dict) -> ToolResult`，但内部调用的 `list_files(params.get("path","."), config)` 等函数需要 `config` 参数。`config` 变量在函数体内未定义，将导致 `NameError`。
- **修正建议**：将函数签名改为 `def execute_tool(action: str, params: dict, config: Config) -> ToolResult`，并在所有工具调用时传入 `config`。

### W-03：`pyproject.toml` 缺少 `pytest` 开发依赖声明

- **涉及任务**：T00（项目初始化）
- **问题描述**：T00 的 `pyproject.toml` 声明了 `dependencies=["keyring", "tomli", "openai"]`，但未声明 `pytest` 作为开发依赖。项目使用 `pytest` 作为测试框架，如果未安装 `pytest`，`tests/` 目录下的测试无法运行。且 T07 的 `run_tests` 工具也依赖 `pytest` 在系统中可用。
- **修正建议**：在 `pyproject.toml` 中增加 `[project.optional-dependencies] dev = ["pytest"]`，或在 `[tool.pytest.ini_options]` 上方增加 `requires-pytest` 说明。同时 T00 的包依赖应包含 `pytest`（至少作为 `dev` 依赖）。

### W-04：T21 (CLI) 的 `test_cli_help` 测试依赖 `SystemExit`，但 `argparse` 默认行为不可靠

- **涉及任务**：T21（CLI 入口），第 159 行
- **问题描述**：T21 的验证步骤中写 `def test_cli_help(): sys.argv = ["codeguard", "--help"]; with pytest.raises(SystemExit): main()`。但 `argparse` 仅在 `add_help=True`（默认）时调用 `sys.exit(0)`，且 `main()` 函数通常不会直接 `sys.exit()`。如果 `main()` 捕获异常或 `argparse` 被配置为不退出，测试会误判。
- **修正建议**：使用 `pytest` 的 `capsys` fixture 捕获输出，而不是依赖 `SystemExit`：
  ```python
  def test_cli_help(capsys):
      sys.argv = ["codeguard", "--help"]
      with pytest.raises(SystemExit):
          main()
      captured = capsys.readouterr()
      assert "usage:" in captured.out
  ```
  同时在 T21 实现要点中更新 `main()` 函数，确保 `--help` 时 `argparse` 的默认行为不被覆盖。

### W-05：T22 (demo.py) 的 `demo_approval_rejected` 修改全局 `sys.stdin` 可能导致测试间污染

- **涉及任务**：T22（demo.py），第 167 行
- **问题描述**：`demo_approval_rejected` 函数直接修改 `sys.stdin = StringIO("n\n")` 且未在 `finally` 块中恢复。如果函数中途抛出异常，`sys.stdin` 将永久损坏，影响后续测试。T23 虽然使用了 `monkeypatch` 解决了这个问题，但 T22 的 `demo_approval_rejected` 实现本身存在风险。
- **修正建议**：在 T22 的 `demo_approval_rejected` 函数中使用 `try/finally` 确保 `sys.stdin` 被恢复，或者在 T22 的实现中注明使用 `contextlib.redirect_stdin`。

---

## 3. 🟢 建议优化（Suggestions）

### S-01：Memory 持久化路径与 SPEC 不一致

- **涉及任务**：T16（Memory），SPEC §9.3
- **问题描述**：SPEC §9.3 规定记忆持久化到 `codeguard_memory.json`（相对路径，无目录前缀）。PLAN T16 使用 `~/.codeguard/memory.json`（用户 home 目录）。PLAN 的路径更合理（避免污染工作目录），但两者不一致，建议在 SPEC 中更新或统一。
- **优化思路**：在 SPEC 中更新 §9.3 的记忆持久化路径为 `~/.codeguard/memory.json`，使两文档一致。或者让 PLAN 回退到 `codeguard_memory.json`（工作目录下），但前者的安全性和整洁性更好。

### S-02：T06 缺少 `list_files` 的 `depth` 参数实现

- **涉及任务**：T06（文件工具），SPEC §9.2
- **问题描述**：SPEC §9.2 规定 `list_directory` 的参数为 `{"path": str, "depth": int}`（depth 默认 1），且不允许深度 > 3。PLAN T06 的 `list_files` 实现要点中未提及 `depth` 参数和递归深度限制。
- **优化思路**：在 T06 的 `list_files` 实现中添加 `depth` 参数处理：`if depth > 3: return ToolResult(success=False, error="Max depth exceeded")`，并使用递归或 `Path.rglob` 限制深度。

### S-03：T07 (run_tests) 应过滤危险 pytest 参数

- **涉及任务**：T07（命令工具），SPEC §9.2
- **问题描述**：SPEC §9.2 规定 `run_pytest` 应"禁止添加危险参数（如 `--pdb`）"。PLAN T07 的 `run_tests` 实现中未对此做检查。`--pdb` 参数会在测试失败时进入交互式调试器，阻塞 Agent 主循环。
- **优化思路**：在 `run_tests` 函数中添加参数黑名单检查：`dangerous_args = ["--pdb", "--pdbcls", "--coverage"]; if any(arg in args for arg in dangerous_args): return ToolResult(success=False, error="Dangerous pytest argument blocked")`。

### S-04：T22 (demo.py) 的 `demo_approval_rejected` 在 SPEC 剧本 2 中应触发 HIGH 风险

- **涉及任务**：T22（demo.py），SPEC §7.2
- **问题描述**：SPEC §7.2 剧本 2 的预期是"Risk 层判定为 HIGH"，但 PLAN T22 的 `demo_approval_rejected` 使用 `write_file` 写入 `"x"*20000`（20KB），这超过了 `high_size_threshold`（默认 10KB），所以会触发 HIGH。但如果 `high_size_threshold` 被配置为更大值，剧本 2 就会失效。当前实现依赖阈值配置，不够鲁棒。
- **优化思路**：在 `demo_approval_rejected` 中显式设置 `config.high_size_threshold = 100`（1KB），确保 20KB 内容一定触发 HIGH。或者在 T12 中增加一个"写入特定路径"的 HIGH 规则（如写入 `src/secrets.py`）。

### S-05：T22 和 T23 的依赖关系标注不精确

- **涉及任务**：T22、T23
- **问题描述**：T22 和 T23 的依赖列都只写了 `T19`（死循环保护），但实际它们也依赖 T18（Agent 基础版），因为 T19 是在 T18 基础上的增量。虽然 T19 隐含了 T18，但依赖标注不够精确。
- **优化思路**：将 T22 和 T23 的依赖改为 `T18, T19`，或者在依赖链图中明确标注 T18→T19→T22/T23 的路径。

---

## 4. 总体结论

- [ ] 通过（无阻塞性问题）
- [ ] 有条件通过（存在警告，但不影响开发启动）
- [x] **不通过（存在严重问题，需立即修改）**

**判定理由**：存在 3 个 🔴 严重问题，其中 C-01（`edit_file` 完全缺失）和 C-02（路径沙箱 `startswith` 绕过漏洞）是功能完整性和安全性的硬伤，必须在开发启动前修复。C-03（课程交付文档缺失）需根据课程要求确认。

**建议修复优先级**：
1. **立即修复**：C-01 补 `edit_file`，C-02 改 `startswith` 为 `commonpath`
2. **开始前确认**：C-03 确认课程是否要求 `SPEC_PROCESS.md`、`AGENT_LOG.md`、`REFLECTION.md`
3. **开发前修复**：W-01 补充 Risk 分级的 `install`/`commit` 检查，W-02 修复 `execute_tool` 签名
4. **开发中注意**：W-03 补充 `pytest` 依赖，W-04 修复 CLI 测试，S-01~S-05 按需优化