# CodeGuard — 实施计划

> 基于 `SPEC.md` 生成，面向课程 A.6 验收标准（三个机制演示）。
> 所有任务遵循 TDD 五步法：写失败测试 → 红色 → 写最少代码 → 绿色 → 提交。

---

## 第一部分：文件结构映射表

```
codeguard/
├── pyproject.toml                    # 项目元数据、依赖声明、pytest 配置
├── conftest.py                       # pytest 全局 fixture（MockLLM、临时目录、配置）
├── config.toml                       # 默认配置文件（用户可覆盖）
├── demo.py                           # 三机制演示脚本（不联网，MockLLM 驱动）
│
├── src/
│   ├── __init__.py                   # 空包标记
│   ├── models.py                     # 数据模型：ParseResult, ValidationResult, RiskDecision, ApprovalResult, ToolResult, AuditLog, Memory
│   ├── config.py                     # Config 类：加载 config.toml，提供默认值
│   ├── keyring_manager.py            # KeyringManager：get/set/delete API Key
│   ├── path_sandbox.py               # is_path_allowed()：resolve + commonpath + 黑名单优先
│   ├── command_sandbox.py            # is_command_allowed()：白名单 + 禁止符正则
│   ├── tools.py                      # 六大工具实现：list_files, read_file, write_file, run_tests, run_command, finish
│   ├── llm.py                        # LLMAdapter 抽象基类 + MockLLM + RealLLM
│   ├── parser.py                     # parse_llm_output()：JSON 解析 + 字段校验
│   ├── validation.py                 # validate_action()：调用 path_sandbox + command_sandbox
│   ├── risk.py                       # assess_risk()：四级风险分级（LOW/MEDIUM/HIGH/FORBIDDEN）
│   ├── approval.py                   # request_approval()：CLI 交互 Y/N，超时自动拒绝
│   ├── executor.py                   # execute_tool()：根据 action 分发到 tools.py
│   ├── feedback.py                   # build_feedback()：ToolResult → 结构化文本
│   ├── memory.py                     # Memory 类：内存存储 + ~/.codeguard/memory.json 持久化
│   ├── audit_log.py                  # AuditLogger：JSON 每步记录，过滤 API Key
│   ├── agent.py                      # run_agent()：手写 while 主循环
│   └── cli.py                        # 入口：argparse 解析，调用 agent.run_agent()
│
└── tests/
    ├── __init__.py                   # 空包标记
    ├── conftest.py                   # 测试专用 fixture（临时目录、MockLLM 实例、示例文件）
    ├── test_models.py                # 数据模型创建与字段验证
    ├── test_config.py                # Config 加载与默认值
    ├── test_keyring_manager.py       # Mock keyring 的 set/get/delete
    ├── test_path_sandbox.py          # 路径遍历、敏感文件、黑名单优先
    ├── test_command_sandbox.py       # 命令白名单、禁止符、网络命令
    ├── test_tools.py                 # 六大工具的正常路径与错误路径
    ├── test_llm.py                   # MockLLM 预设响应、RealLLM 调用（集成测试跳过）
    ├── test_parser.py                # 合法 JSON、非法 JSON、缺失字段
    ├── test_validation.py            # 合法动作、路径越界、命令越界
    ├── test_risk.py                  # 四级风险分级的每条规则
    ├── test_approval.py              # 用户输入 Y、N、超时
    ├── test_executor.py              # 工具分发、异常处理
    ├── test_feedback.py              # 成功/失败反馈格式
    ├── test_memory.py                # 添加、读取、持久化
    ├── test_audit_log.py             # 日志写入、不含 API Key
    ├── test_agent.py                 # 主循环完整流程（MockLLM 驱动）
    └── test_demo.py                  # 三个剧本的端到端验证
```

---

## 第二部分：任务列表（按依赖顺序）

### 阶段 0：项目脚手架

| 任务 | 名称 | 依赖 | 涉及文件 | 实现要点 | 验证步骤 |
|------|------|------|---------|---------|---------|
| T00 | 初始化项目结构与依赖 | 无 | `pyproject.toml`, `src/__init__.py`, `tests/__init__.py`, `tests/conftest.py`, `conftest.py` | `pyproject.toml` 声明：`[project] name="codeguard", requires-python=">=3.10", dependencies=["keyring", "tomli", "openai"]`；`[tool.pytest.ini_options] testpaths=["tests"]`；`src/__init__.py` 空文件；`tests/__init__.py` 空文件；`conftest.py` 全局 fixture 占位，`tests/conftest.py` 测试专用 fixture 占位 | `pytest tests/ --collect-only` 通过，显示 0 个测试被收集 |

---

### 阶段 1：数据模型与配置（可并行）

| 任务 | 名称 | 依赖 | 涉及文件 | 实现要点 | 验证步骤 |
|------|------|------|---------|---------|---------|
| T01 | 实现数据模型 | T00 | `src/models.py`, `tests/test_models.py` | 定义 7 个 dataclass：<br>`@dataclass class ParseResult: success: bool; action: str \| None; params: dict \| None; error: str \| None`<br>`@dataclass class ValidationResult: valid: bool; reason: str; sanitized_params: dict`<br>`@dataclass class RiskDecision: level: str; rule: str; needs_approval: bool; is_forbidden: bool`<br>`@dataclass class ApprovalResult: approved: bool; reason: str; timestamp: str`<br>`@dataclass class ToolResult: success: bool; data: Any; error: str; meta: dict`<br>`@dataclass class AuditLog: step: int; timestamp: str; action: str; params: dict; risk_level: str; approval: ApprovalResult \| None; result: ToolResult \| None`<br>`@dataclass class Memory: task: str; history: list; step_count: int`<br>使用 `from dataclasses import dataclass, field` | `pytest tests/test_models.py -v`，测试创建每个模型实例，字段默认值正确 |
| T02 | 实现配置模块 | T00 | `src/config.py`, `tests/test_config.py`, `config.toml` | ```python @dataclass class Config: workspace: str = "."; max_steps: int = 10; command_timeout: int = 30; max_file_size: int = 100000; allowed_commands: list = field(default_factory=lambda: ["python","pytest","ruff","mypy","git diff","git status"]); protected_files: list = field(default_factory=lambda: [".env",".git","*.pem","*.key"]); allowed_extensions: list = field(default_factory=lambda: [".py",".json",".toml",".md",".txt"]); auto_finish_on_test_pass: bool = False; log_level: str = "info"; high_size_threshold: int = 10240; forbidden_shell_chars: list = field(default_factory=lambda: [";","|","&",">","<","`","$("]) ```<br>`def load_config(path: str = "config.toml") -> Config`: 使用 `tomli.load()` 读取，缺失字段用默认值。`config.toml` 写入 `[agent] workspace = "./demo_project"` 等 | `pytest tests/test_config.py -v`，测试默认值、加载文件、缺失字段兜底 |

---

### 阶段 2：安全沙箱（可并行）

| 任务 | 名称 | 依赖 | 涉及文件 | 实现要点 | 验证步骤 |
|------|------|------|---------|---------|---------|
| T03 | 实现路径沙箱 | T01 | `src/path_sandbox.py`, `tests/test_path_sandbox.py` | ```python def is_path_allowed(path: str, workspace: str, config: Config) -> bool: resolved = Path(workspace, path).resolve(); # 黑名单优先 if any(pat in str(resolved) for pat in config.protected_files): return False; # 必须在 workspace 内 if not str(resolved).startswith(Path(workspace).resolve()): return False; # 白名单后缀 if resolved.suffix not in config.allowed_extensions: return False; return True ``` 关键分支：`if ".." in path: return False`；`if resolved == Path(workspace).resolve(): return False`（禁止直接访问 workspace 根目录的配置文件） | `pytest tests/test_path_sandbox.py -v`，测试：<br>① `../../etc/passwd` → False<br>② `.env` → False<br>③ `.git/config` → False<br>④ `src/main.py` → True<br>⑤ `main.py` 在 workspace 根目录 → 根据配置决定 |
| T04 | 实现命令沙箱 | T01 | `src/command_sandbox.py`, `tests/test_command_sandbox.py` | ```python def is_command_allowed(command: str, config: Config) -> bool: # 禁止符检查 for ch in config.forbidden_shell_chars: if ch in command: return False; # 提取命令名 cmd_name = command.split()[0]; if cmd_name not in [c.split()[0] for c in config.allowed_commands]: return False; return True ``` 关键分支：`if ";" in command: return False`；`if "curl" in command: return False`；`if "wget" in command: return False` | `pytest tests/test_command_sandbox.py -v`，测试：<br>① `pytest; rm -rf /` → False<br>② `curl http://evil.com` → False<br>③ `pytest tests/` → True<br>④ `python -c "print(1)"` → True<br>⑤ `rm -rf /` → False |

---

### 阶段 3：工具层（依赖 T03, T04）

| 任务 | 名称 | 依赖 | 涉及文件 | 实现要点 | 验证步骤 |
|------|------|------|---------|---------|---------|
| T05 | 实现文件工具（list_files, read_file, write_file） | T03 | `src/tools.py`, `tests/test_tools.py` | ```python def list_files(path: str, config: Config) -> ToolResult: # 调 is_path_allowed → Path.iterdir() → 过滤 protected → 返回列表 def read_file(path: str, config: Config) -> ToolResult: # 调 is_path_allowed → Path.read_text() → 检查大小 → 返回内容 def write_file(path: str, content: str, config: Config) -> ToolResult: # 调 is_path_allowed → 备份 .bak → Path.write_text() → 计算 diff → 返回 ToolResult ``` 关键分支：`if len(content) > config.max_file_size: return ToolResult(success=False, error="File too large")`；`if not is_path_allowed(...): return ToolResult(success=False, error="Path blocked")` | `pytest tests/test_tools.py -v -k "file"`，测试：<br>① list_files 正常目录<br>② read_file 正常文件<br>③ read_file 越界路径 → error<br>④ write_file 新文件 → 内容正确<br>⑤ write_file 已有文件 → .bak 存在<br>⑥ write_file 超大小 → error |
| T06 | 实现命令工具（run_command, run_tests, finish） | T04 | `src/tools.py`, `tests/test_tools.py` | ```python def run_command(command: str, config: Config) -> ToolResult: # 调 is_command_allowed → subprocess.run(cmd.split(), shell=False, capture_output=True, timeout=config.command_timeout, env={"PATH": os.environ["PATH"]}) → 返回 ToolResult def run_tests(args: str, config: Config) -> ToolResult: # 调 run_command("pytest " + args) → 解析 stdout 里的 passed/failed 数量 def finish(summary: str = "") -> ToolResult: # 返回 ToolResult(success=True, data={"summary": summary, "finished": True}) ``` 关键分支：`if not is_command_allowed(...): return ToolResult(success=False, error="Command blocked")`；`subprocess.run` 必须 `shell=False` 且 `env` 只含 PATH | `pytest tests/test_tools.py -v -k "command"`，测试：<br>① run_command 白名单命令 → exit_code=0<br>② run_command 禁止命令 → error<br>③ run_tests 存在测试文件 → 通过<br>④ run_tests 超时 → TimeoutExpired 被捕获<br>⑤ finish → success=True, meta.finished=True |

---

### 阶段 4：LLM 抽象层（独立于阶段 3）

| 任务 | 名称 | 依赖 | 涉及文件 | 实现要点 | 验证步骤 |
|------|------|------|---------|---------|---------|
| T07 | 实现 MockLLM | T01 | `src/llm.py`, `tests/test_llm.py` | ```python class BaseLLM(ABC): @abstractmethod def next_action(self, context: str) -> str: pass class MockLLM(BaseLLM): def __init__(self, responses: list[str]): self.responses = responses; self.index = 0 def next_action(self, context: str) -> str: if self.index >= len(self.responses): return '{"action": "finish"}'; resp = self.responses[self.index]; self.index += 1; return resp ``` | `pytest tests/test_llm.py -v`，测试：<br>① MockLLM 返回预设响应<br>② MockLLM 耗尽后返回 finish<br>③ 上下文参数被忽略（Mock 不读 context） |
| T08 | 实现 RealLLM | T07 | `src/llm.py`, `tests/test_llm.py` | ```python class RealLLM(BaseLLM): def __init__(self, api_key: str, model: str = "gpt-4o-mini"): self.api_key = api_key; self.model = model def next_action(self, context: str) -> str: from openai import OpenAI; client = OpenAI(api_key=self.api_key); resp = client.chat.completions.create(model=self.model, messages=[{"role": "user", "content": context}]); return resp.choices[0].message.content ``` 集成测试标记 `@pytest.mark.skipif(os.environ.get("OPENAI_API_KEY") is None)` | `pytest tests/test_llm.py -v -k "real"`，无 API Key 时跳过 |

---

### 阶段 5：治理层（依赖 T01, T03, T04）

| 任务 | 名称 | 依赖 | 涉及文件 | 实现要点 | 验证步骤 |
|------|------|------|---------|---------|---------|
| T09 | 实现 Parser | T01 | `src/parser.py`, `tests/test_parser.py` | ```python def parse_llm_output(raw: str) -> ParseResult: try: data = json.loads(raw); if "action" not in data: return ParseResult(success=False, error="Missing 'action' field"); action = data["action"]; params = data.get("params", {}); if action not in ["list_files","read_file","write_file","run_command","run_tests","finish"]: return ParseResult(success=False, error=f"Unknown action: {action}"); return ParseResult(success=True, action=action, params=params) except json.JSONDecodeError: return ParseResult(success=False, error="Invalid JSON") ``` | `pytest tests/test_parser.py -v`，测试：<br>① 合法 JSON → success=True<br>② 非 JSON 文本 → error<br>③ 缺失 action → error<br>④ 未知 action → error<br>⑤ 空 params → 默认 `{}` |
| T10 | 实现 Validation | T03, T04, T09 | `src/validation.py`, `tests/test_validation.py` | ```python def validate_action(action: str, params: dict, config: Config) -> ValidationResult: if action in ("list_files", "read_file", "write_file"): path = params.get("path", ""); if not is_path_allowed(path, config.workspace, config): return ValidationResult(valid=False, reason="Path blocked"); if action == "run_command": command = params.get("command", ""); if not is_command_allowed(command, config): return ValidationResult(valid=False, reason="Command blocked"); return ValidationResult(valid=True, reason="", sanitized_params=params) ``` 关键分支：`if action == "write_file" and len(params.get("content","")) > config.max_file_size: return ValidationResult(valid=False, reason="Content too large")` | `pytest tests/test_validation.py -v`，测试：<br>① read_file 合法路径 → valid=True<br>② read_file 越界路径 → valid=False<br>③ run_command 合法命令 → valid=True<br>④ run_command 含禁止符 → valid=False<br>⑤ write_file 超大小 → valid=False |
| T11 | 实现 Risk 分级 | T01, T10 | `src/risk.py`, `tests/test_risk.py` | ```python def assess_risk(action: str, params: dict, validation: ValidationResult, config: Config) -> RiskDecision: if not validation.valid: return RiskDecision(level="FORBIDDEN", rule="Validation failed", needs_approval=False, is_forbidden=True); if action in ("list_files",): return RiskDecision(level="LOW", rule="Read-only operation"); if action in ("read_file",): return RiskDecision(level="LOW", rule="Read-only operation"); if action in ("write_file", "run_command"): path = params.get("path", ""); content = params.get("content", ""); if len(content) > config.high_size_threshold: return RiskDecision(level="HIGH", rule="Large file write", needs_approval=True); return RiskDecision(level="MEDIUM", rule="Write operation"); if action == "run_tests": return RiskDecision(level="MEDIUM", rule="Test execution"); if action == "finish": return RiskDecision(level="LOW", rule="Normal termination"); return RiskDecision(level="MEDIUM", rule="Default") ``` | `pytest tests/test_risk.py -v`，测试：<br>① list_files → LOW<br>② read_file 合法 → LOW<br>③ write_file 小文件 → MEDIUM<br>④ write_file 大文件 → HIGH<br>⑤ validation 失败 → FORBIDDEN<br>⑥ finish → LOW |
| T12 | 实现 Approval 管理器 | T01 | `src/approval.py`, `tests/test_approval.py` | ```python def request_approval(action: str, params: dict, risk: RiskDecision, timeout: int = 30) -> ApprovalResult: print(f"\n[APPROVAL] Action: {action}"); print(f"Params: {params}"); print(f"Risk: {risk.level} - {risk.rule}"); print("Approve? (y/N): ", end="", flush=True); try: import select; import sys; if select.select([sys.stdin], [], [], timeout)[0]: choice = sys.stdin.readline().strip().lower(); if choice == "y": return ApprovalResult(approved=True, reason="User approved"); else: return ApprovalResult(approved=False, reason="User rejected"); else: print(" (timeout)"); return ApprovalResult(approved=False, reason="Timeout") except: return ApprovalResult(approved=False, reason="Error") ``` 测试使用 `unittest.mock.patch('sys.stdin')` 模拟输入。关键分支：`if choice == "y": approved=True`；`else: approved=False`；`timeout` 触发 → `approved=False` | `pytest tests/test_approval.py -v`，测试：<br>① 输入 `y` → approved=True<br>② 输入 `n` → approved=False<br>③ 输入空 → approved=False<br>④ 超时 → approved=False（mock select 返回空列表） |

---

### 阶段 6：执行器与反馈（依赖 T05, T06, T09, T10, T11, T12）

| 任务 | 名称 | 依赖 | 涉及文件 | 实现要点 | 验证步骤 |
|------|------|------|---------|---------|---------|
| T13 | 实现 Executor | T05, T06, T09, T10, T11, T12 | `src/executor.py`, `tests/test_executor.py` | ```python def execute_tool(action: str, params: dict) -> ToolResult: if action == "list_files": return list_files(params.get("path","."), config); if action == "read_file": return read_file(params.get("path",""), config); if action == "write_file": return write_file(params.get("path",""), params.get("content",""), config); if action == "run_command": return run_command(params.get("command",""), config); if action == "run_tests": return run_tests(params.get("args",""), config); if action == "finish": return finish(params.get("summary","")); return ToolResult(success=False, error=f"Unknown action: {action}") ``` 关键分支：`execute_tool` 内部 `try/except Exception as e: return ToolResult(success=False, error=str(e))` | `pytest tests/test_executor.py -v`，测试：<br>① 分发到正确工具<br>② 未知 action → error<br>③ 异常被捕获 → success=False |
| T14 | 实现 Feedback Processor | T01, T13 | `src/feedback.py`, `tests/test_feedback.py` | ```python def build_feedback(result: ToolResult) -> str: if result.success: output = f"Action succeeded.\n"; if result.meta.get("exit_code") is not None: output += f"Exit code: {result.meta['exit_code']}\n"; if result.meta.get("stdout"): output += f"Output:\n{result.meta['stdout']}\n"; if result.meta.get("diff"): output += f"Diff:\n{result.meta['diff']}\n"; return output; else: return f"Action failed: {result.error}\n" ``` 关键分支：`if result.meta.get("finished"): return "Task completed successfully."` | `pytest tests/test_feedback.py -v`，测试：<br>① 成功反馈含 exit_code<br>② 失败反馈含 error<br>③ finish 的反馈格式 |

---

### 阶段 7：记忆与审计（可并行，依赖 T01）

| 任务 | 名称 | 依赖 | 涉及文件 | 实现要点 | 验证步骤 |
|------|------|------|---------|---------|---------|
| T15 | 实现 Memory | T01 | `src/memory.py`, `tests/test_memory.py` | ```python class Memory: def __init__(self, task: str, memory_dir: str = "~/.codeguard"): self.task = task; self.history = []; self.step_count = 0; self.memory_dir = Path(memory_dir).expanduser(); self.memory_dir.mkdir(parents=True, exist_ok=True); self.file_path = self.memory_dir / "memory.json"; self._load() def add(self, action: str, params: dict, result: ToolResult): self.history.append({"action": action, "params": params, "result": {"success": result.success, "meta": result.meta}}); self.step_count += 1; self._save() def _save(self): self.file_path.write_text(json.dumps({"task": self.task, "history": self.history[-20:], "step_count": self.step_count}, indent=2)) def _load(self): if self.file_path.exists(): data = json.loads(self.file_path.read_text()); self.task = data.get("task", self.task); self.history = data.get("history", []); self.step_count = data.get("step_count", 0) ``` | `pytest tests/test_memory.py -v`，测试：<br>① add 后 history 长度 +1<br>② 持久化文件存在<br>③ 重新加载后数据恢复<br>④ history 最大 20 条 |
| T16 | 实现 AuditLogger | T01 | `src/audit_log.py`, `tests/test_audit_log.py` | ```python class AuditLogger: def __init__(self, log_dir: str = "~/.codeguard"): self.log_dir = Path(log_dir).expanduser(); self.log_dir.mkdir(parents=True, exist_ok=True); self.log_file = self.log_dir / f"audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"; self.entries = [] def log(self, step: int, action: str, params: dict, risk_level: str, approval: ApprovalResult, result: ToolResult): # 过滤 content 字段，只保留长度 safe_params = {k: v for k, v in params.items()}; if "content" in safe_params: safe_params["content_length"] = len(safe_params.pop("content")); entry = {"step": step, "timestamp": datetime.now().isoformat(), "action": action, "params": safe_params, "risk_level": risk_level, "approval": {"approved": approval.approved, "reason": approval.reason} if approval else None, "result": {"success": result.success, "error": result.error}, "final_decision": "EXECUTED" if result.success else "BLOCKED"}; # 确保不记录 API Key assert "api_key" not in str(entry).lower(); self.entries.append(entry); with open(self.log_file, "a") as f: f.write(json.dumps(entry) + "\n") ``` | `pytest tests/test_audit_log.py -v`，测试：<br>① 日志文件创建<br>② 日志条目含所有字段<br>③ content 被替换为 content_length<br>④ 不包含 "api_key" 字符串 |

---

### 阶段 8：Agent 主循环（依赖所有阶段 3-7）

| 任务 | 名称 | 依赖 | 涉及文件 | 实现要点 | 验证步骤 |
|------|------|------|---------|---------|---------|
| T17 | 实现 Agent 主循环 | T07, T09, T10, T11, T12, T13, T14, T15, T16 | `src/agent.py`, `tests/test_agent.py` | ```python def run_agent(task: str, llm: BaseLLM, config: Config) -> Memory: memory = Memory(task); audit = AuditLogger(); context = f"Task: {task}\nYou are a coding agent. Available actions: list_files, read_file, write_file, run_command, run_tests, finish.\n"; step = 0; consecutive_failures = 0; while step < config.max_steps: step += 1; raw = llm.next_action(context); parse_result = parse_llm_output(raw); if not parse_result.success: consecutive_failures += 1; context += f"Step {step} parse error: {parse_result.error}\n"; if consecutive_failures >= 3: break; continue; action = parse_result.action; params = parse_result.params; val_result = validate_action(action, params, config); risk = assess_risk(action, params, val_result, config); if risk.is_forbidden: result = ToolResult(success=False, error=f"Action forbidden: {risk.rule}"); elif risk.needs_approval: approval = request_approval(action, params, risk); if not approval.approved: result = ToolResult(success=False, error=f"User rejected: {approval.reason}"); else: result = execute_tool(action, params); else: result = execute_tool(action, params); approval = ApprovalResult(approved=True, reason="Auto-approved") if not risk.needs_approval else approval; audit.log(step, action, params, risk.level, approval, result); memory.add(action, params, result); feedback = build_feedback(result); context += f"Step {step} result: {feedback}\n"; if action == "finish": break; if consecutive_failures >= 3: break; consecutive_failures = 0; if action == "finish": break; return memory ``` 主循环 `while` 手动实现，无任何 AgentExecutor 依赖。停机条件按优先级实现：`finish` > `consecutive_failures >= 3` > `step >= max_steps` | `pytest tests/test_agent.py -v`，测试：<br>① MockLLM `[finish]` → 1 步结束<br>② MockLLM `[read_file, write_file, finish]` → 3 步结束 |
| T18 | 实现死循环保护 | T17 | `src/agent.py`, `tests/test_agent.py` | 在 T17 的 `while` 循环内加入：`last_action = None; same_action_count = 0; if action == last_action: same_action_count += 1; else: same_action_count = 0; last_action = action; if same_action_count >= 3: context += "Dead loop detected: same action repeated 3 times.\n"; break` | `pytest tests/test_agent.py -v -k "dead_loop"`，测试：<br>① 连续 3 次相同 action → 停机<br>② 不同 action 交替 → 不停机 |

---

### 阶段 9：凭据安全（独立）

| 任务 | 名称 | 依赖 | 涉及文件 | 实现要点 | 验证步骤 |
|------|------|------|---------|---------|---------|
| T19 | 实现 KeyringManager | T00 | `src/keyring_manager.py`, `tests/test_keyring_manager.py` | ```python import keyring; SERVICE_NAME = "codeguard"; class KeyringManager: @staticmethod def set_key(api_key: str) -> bool: keyring.set_password(SERVICE_NAME, "api_key", api_key); return keyring.get_password(SERVICE_NAME, "api_key") == api_key; @staticmethod def get_key() -> str \| None: return keyring.get_password(SERVICE_NAME, "api_key"); @staticmethod def delete_key() -> bool: try: keyring.delete_password(SERVICE_NAME, "api_key"); return True; except: return False; @staticmethod def is_configured() -> bool: return KeyringManager.get_key() is not None ``` 测试使用 `unittest.mock.patch('keyring.get_password')` 和 `unittest.mock.patch('keyring.set_password')` | `pytest tests/test_keyring_manager.py -v`，测试：<br>① set_key 返回 True<br>② get_key 返回设置的值<br>③ delete_key 返回 True<br>④ is_configured 返回 True/False |

---

### 阶段 10：CLI 入口（依赖 T17, T19）

| 任务 | 名称 | 依赖 | 涉及文件 | 实现要点 | 验证步骤 |
|------|------|------|---------|---------|---------|
| T20 | 实现 CLI 入口 | T17, T19 | `src/cli.py` | ```python def main(): import argparse; parser = argparse.ArgumentParser(prog="codeguard"); parser.add_argument("task", nargs="?", help="Task description"); parser.add_argument("--workspace", default="."); parser.add_argument("--mock", action="store_true", help="Use MockLLM for testing"); args = parser.parse_args(); config = load_config(); config.workspace = args.workspace; if args.mock: llm = MockLLM([...]) else: key = KeyringManager.get_key(); if not key: print("API Key not configured. Run 'codeguard setup'"); return; llm = RealLLM(key) if args.task: memory = run_agent(args.task, llm, config); print(f"Done. Steps: {memory.step_count}"); else: parser.print_help() if __name__ == "__main__": main() ``` | `python -m src.cli --help` 显示帮助信息 |

---

### 阶段 11：三机制演示 + 集成测试

| 任务 | 名称 | 依赖 | 涉及文件 | 实现要点 | 验证步骤 |
|------|------|------|---------|---------|---------|
| T21 | 实现 demo.py 三机制演示 | T17, T18 | `demo.py` | ```python from src.llm import MockLLM; from src.config import Config; from src.agent import run_agent; import tempfile, os, json; config = Config(); config.max_steps = 10; # 剧本 1：拦截危险命令 print("=== Demo 1: Block dangerous command ==="); mock1 = MockLLM(['{"action":"run_command","params":{"command":"pytest; rm -rf /"}}','{"action":"finish"}']); mem1 = run_agent("Test block", mock1, config); print(f"Steps: {mem1.step_count}, History: {len(mem1.history)}"); # 剧本 2：高风险审批被拒绝（Mock stdin 输入 'n'） import unittest.mock; print("\n=== Demo 2: HITL rejection ==="); mock2 = MockLLM(['{"action":"write_file","params":{"path":"big.py","content":"x"*20000}}','{"action":"finish"}']); with unittest.mock.patch('sys.stdin', new=unittest.mock.MagicMock()): from src.approval import request_approval; # 实际控制台输入 N import sys; original_stdin = sys.stdin; from io import StringIO; sys.stdin = StringIO("n\n"); mem2 = run_agent("Test approval", mock2, config); sys.stdin = original_stdin; print(f"Steps: {mem2.step_count}, History: {len(mem2.history)}"); # 剧本 3：测试失败后修正并通过（使用临时目录） print("\n=== Demo 3: Feedback loop ==="); with tempfile.TemporaryDirectory() as tmpdir: os.makedirs(f"{tmpdir}/src"); os.makedirs(f"{tmpdir}/tests"); with open(f"{tmpdir}/src/add.py", "w") as f: f.write("def add(a,b): return a+b+1"); with open(f"{tmpdir}/tests/test_add.py", "w") as f: f.write("from src.add import add\ndef test_add(): assert add(1,2) == 3"); config.workspace = tmpdir; mock3 = MockLLM(['{"action":"read_file","params":{"path":"src/add.py"}}','{"action":"write_file","params":{"path":"src/add.py","content":"def add(a,b): return a+b"}}','{"action":"run_tests","params":{"args":"tests/"}}','{"action":"finish"}']); mem3 = run_agent("Fix add function", mock3, config); print(f"Steps: {mem3.step_count}, Final file: {open(f'{tmpdir}/src/add.py').read()}"); print("\n=== All demos completed ===") ``` | `python demo.py` 输出三个演示结果，不联网 |
| T22 | 实现端到端集成测试（三个剧本） | T17, T18 | `tests/test_demo.py` | 使用 pytest 重写 T21 的三个场景，`test_demo_block.py`、`test_demo_approval.py`、`test_demo_feedback.py`，每个测试函数使用 `tmp_path` fixture 和 `MockLLM`，断言动作计数和最终状态 | `pytest tests/test_demo.py -v`，三个测试全部绿色 |

---

### 阶段 12：配置完善

| 任务 | 名称 | 依赖 | 涉及文件 | 实现要点 | 验证步骤 |
|------|------|------|---------|---------|---------|
| T23 | 实现 setup.py 命令行配置 | T19 | `setup.py` | 交互式录入 API Key 并存入 keyring：`def setup(): key = input("Enter OpenAI API Key: ").strip(); if KeyringManager.set_key(key): print("API Key saved securely."); else: print("Failed to save key.")` | `python setup.py` 后 `python -c "from src.keyring_manager import KeyringManager; print(KeyringManager.is_configured())"` 输出 True |
| T24 | 完善 README.md | T00 | `README.md` | 写安装步骤、快速开始、配置说明、三机制演示说明 | 无 |

---

## 第三部分：并行执行计划

以下任务**无依赖关系**，可以使用 `git worktree` 隔离并行开发：

| 并行组 | 任务 | 负责人分工建议 |
|--------|------|--------------|
| **组 A**（数据层） | T01 数据模型, T02 配置模块, T15 Memory, T16 AuditLogger | 可分配给 1 人串行或 2 人并行 |
| **组 B**（安全层） | T03 路径沙箱, T04 命令沙箱, T19 KeyringManager | 可分配给 2 人并行 |
| **组 C**（工具层，依赖组 B 完成后） | T05 文件工具, T06 命令工具 | 可分配给 2 人并行（但 tools.py 共享文件，需注意合并冲突） |
| **组 D**（治理层，依赖组 A + B） | T09 Parser, T10 Validation, T11 Risk, T12 Approval | 可分配给 4 人并行（每个文件独立） |
| **组 E**（LLM 层，独立） | T07 MockLLM, T08 RealLLM | 可分配给 1 人 |
| **组 F**（编排层，依赖全部） | T13 Executor, T14 Feedback, T17 Agent, T18 死循环保护 | 必须串行 |

**依赖链图（缩进 = 依赖关系）：**
```
T00 (脚手架)
├── T01 (数据模型) ──┬── T15 (Memory) ──┐
│                    └── T16 (Audit)   ──┤
├── T02 (配置) ──────┬───────────────────┤
│                    └── T03 (路径沙箱) ──┼── T05 (文件工具) ──┐
│                    └── T04 (命令沙箱) ──┼── T06 (命令工具) ──┤
├── T07 (MockLLM) ───────────────────────┼── T13 (Executor) ──┼── T17 (Agent) ── T21 (Demo)
├── T08 (RealLLM) ───────────────────────┘                    │
├── T09 (Parser) ──┬── T10 (Validation) ── T11 (Risk) ────────┤
├── T12 (Approval) ────────────────────────────────────────────┘
└── T19 (Keyring) ── T20 (CLI) ── T23 (setup.py)
```

---

## 最终验证命令

```bash
# 运行所有单元测试
pytest tests/ -v

# 运行三机制演示（不联网）
python demo.py

# 运行端到端集成测试
pytest tests/test_demo.py -v
```

所有测试通过后，输出应为：
```
tests/test_models.py ......                                       [  5%]
tests/test_config.py .....                                        [ 10%]
tests/test_path_sandbox.py ........                               [ 18%]
tests/test_command_sandbox.py ......                              [ 23%]
tests/test_tools.py ..............                                [ 36%]
tests/test_llm.py .....                                           [ 41%]
tests/test_parser.py .....                                        [ 46%]
tests/test_validation.py ....                                     [ 50%]
tests/test_risk.py .......                                        [ 57%]
tests/test_approval.py ....                                       [ 61%]
tests/test_executor.py ....                                       [ 65%]
tests/test_feedback.py ....                                       [ 69%]
tests/test_memory.py ....                                         [ 73%]
tests/test_audit_log.py ....                                      [ 77%]
tests/test_agent.py .....                                         [ 82%]
tests/test_demo.py ...                                            [ 85%]
tests/test_demo.py::test_demo_block PASSED                        [ 88%]
tests/test_demo.py::test_demo_approval PASSED                     [ 94%]
tests/test_demo.py::test_demo_feedback PASSED                     [100%]

========================= 35 passed in 2.34s =========================
```