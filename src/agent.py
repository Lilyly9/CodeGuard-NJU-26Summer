"""Agent 主循环 — 手写 while 循环，绝对禁止使用 LangChain。

Agent 类通过 __init__ 注入依赖（llm_client / parse_fn / 等），
run(task, workspace) 驱动完整的"感知-决策-执行-反馈"闭环。
模块级 run() 函数作为向后兼容包装器保留。
"""

import json
import os
from datetime import datetime
from pathlib import Path

from src.audit_log import AuditLogger
from src.executor import execute_tool
from src.feedback import build_feedback
from src.memory import Memory
from src.models import ParseResult, RiskLevel


def _action_to_dict(parsed: ParseResult) -> dict:
    return {"action": parsed.action.type, **parsed.action.params}


class Agent:
    """AI 编程助手主循环，所有外部依赖通过 __init__ 注入。"""

    def __init__(self, *,
                 llm_client=None,
                 parse_fn=None,
                 validate_fn=None,
                 assess_risk_fn=None,
                 approval_fn=None,
                 tools_module=None,
                 config=None,
                 progress_callback=None):
        if llm_client is None:
            from src.llm_client import RealLLM
            llm_client = RealLLM()
        self.llm_client = llm_client

        if parse_fn is None:
            from src.parser import parse_llm_output
            parse_fn = parse_llm_output
        self.parse_fn = parse_fn

        if validate_fn is None:
            from src.validation import validate_action as validate_fn
        self.validate_fn = validate_fn

        if assess_risk_fn is None:
            from src.guardrail import assess_risk as assess_risk_fn
        self.assess_risk_fn = assess_risk_fn

        if approval_fn is None:
            from src.approval import request_approval
            approval_fn = request_approval
        self.approval_fn = approval_fn

        if tools_module is None:
            import src.tools as tools_module
        self.tools_module = tools_module

        if config is None:
            from src.config import Config
            config = Config()
        self.config = config

        self.progress_callback = progress_callback

    def _notify(self, event_type: str, data: dict):
        """Notify progress callback if set."""
        if self.progress_callback:
            try:
                self.progress_callback(event_type, data)
            except Exception:
                pass  # never let callback failures crash the agent

    def run(self, task: str, workspace: str, max_steps: int = 10) -> dict:
        ws_path = Path(workspace)
        if not ws_path.exists():
            raise ValueError(f"Workspace does not exist: {workspace}")
        if not os.access(str(ws_path), os.R_OK):
            raise PermissionError(f"Workspace not readable: {workspace}")

        memory = Memory(task=task)
        context = _build_context(task, memory)
        step = 0
        logger = AuditLogger(Path(workspace) / ".codeguard" / "audit.jsonl")
        finished = False
        consecutive_failures = 0
        last_action_signature = None
        action_repeat_count = 0
        stop_reason = ""

        try:
            while step < max_steps:
                step += 1

                try:
                    raw = self.llm_client.get_response(context)
                except KeyboardInterrupt:
                    stop_reason = "用户手动中断"
                    break

                parsed = self.parse_fn(raw)
                if parsed.error:
                    consecutive_failures += 1
                    if consecutive_failures >= 3:
                        stop_reason = "连续 3 次解析失败"
                        step -= 1
                        break
                    context.append({"role": "user", "content": f"Parse error: {parsed.error}. Please respond with valid JSON."})
                    logger.log({
                        "step": step,
                        "timestamp": datetime.now(),
                        "action": {},
                        "risk_level": "",
                        "final_decision": "PARSE_ERROR",
                    })
                    memory.add_history({}, {"success": False, "error": parsed.error})
                    last_action_signature = None
                    action_repeat_count = 0
                    continue

                consecutive_failures = 0
                action_dict = _action_to_dict(parsed)

                self._notify("step", {"step": step, "action": action_dict})

                if action_dict.get("action") == "finish":
                    logger.log({
                        "step": step,
                        "timestamp": datetime.now(),
                        "action": action_dict,
                        "risk_level": "",
                        "final_decision": "FINISHED",
                    })
                    memory.add_history(action_dict, {"success": True, "meta": {"finished": True}})
                    finished = True
                    break

                current_signature = (action_dict.get("action"), frozenset(action_dict.items()))
                if current_signature == last_action_signature:
                    action_repeat_count += 1
                    if action_repeat_count >= 3:
                        if step < max_steps:
                            stop_reason = "连续 3 次相同无效动作"
                        break
                else:
                    last_action_signature = current_signature
                    action_repeat_count = 1

                validated = self.validate_fn(action_dict, workspace, self.config)
                if not validated.valid:
                    consecutive_failures += 1
                    if consecutive_failures >= 3:
                        stop_reason = "连续 3 次验证失败"
                        step -= 1
                        break
                    context.append({
                        "role": "user",
                        "content": f"Validation error: {validated.reason}. Please fix the action and respond with valid JSON.",
                    })
                    logger.log({
                        "step": step,
                        "timestamp": datetime.now(),
                        "action": action_dict,
                        "risk_level": "",
                        "final_decision": "VALIDATION_ERROR",
                    })
                    memory.add_history(action_dict, {"success": False, "error": validated.reason, "meta": {"validation_error": True}})
                    continue
                consecutive_failures = 0
                risk = self.assess_risk_fn(validated, self.config)

                if risk.level == RiskLevel.FORBIDDEN:
                    context.append({
                        "role": "user",
                        "content": f"Action '{action_dict.get('action')}' is forbidden by security policy. Please try a different approach.",
                    })
                    logger.log({
                        "step": step,
                        "timestamp": datetime.now(),
                        "action": action_dict,
                        "risk_level": risk.level.value,
                        "final_decision": "BLOCKED",
                    })
                    memory.add_history(action_dict, {"success": False, "error": "Action forbidden", "meta": {"blocked": True}})
                    self._notify("blocked", {"step": step, "action": action_dict, "risk_level": risk.level.value, "reason": "forbidden"})
                    continue

                approval_info = None
                if risk.level == RiskLevel.HIGH:
                    approval_result = _call_approval(self.approval_fn, risk, action_dict, workspace)
                    approval_info = {
                        "approved": bool(approval_result.approved),
                        "reason": approval_result.reason,
                    }
                    if not approval_result.approved:
                        context.append({
                            "role": "user",
                            "content": "User rejected the action. Please try a different approach.",
                        })
                        logger.log({
                            "step": step,
                            "timestamp": datetime.now(),
                            "action": action_dict,
                            "risk_level": risk.level.value,
                            "approval": approval_info,
                            "final_decision": "REJECTED",
                        })
                        memory.add_history(action_dict, {"success": False, "error": "User rejected", "meta": {"blocked": True}})
                        self._notify("blocked", {"step": step, "action": action_dict, "risk_level": risk.level.value, "reason": "rejected"})
                        continue

                tool_result = execute_tool(action_dict.get("action"), action_dict, workspace, self.config, self.tools_module)
                feedback = build_feedback(tool_result)
                context.append({"role": "user", "content": feedback})

                logger.log({
                    "step": step,
                    "timestamp": datetime.now(),
                    "action": action_dict,
                    "risk_level": risk.level.value,
                    "approval": approval_info,
                    "tool_result": tool_result,
                    "final_decision": "EXECUTED",
                })
                memory.add_history(action_dict, tool_result)
                self._notify("executed", {"step": step, "action": action_dict, "result": tool_result, "risk_level": risk.level.value})
                if action_dict.get("action") == "run_pytest":
                    memory.last_test_result = tool_result
                    if self.config.auto_finish_on_test_pass and tool_result.get("success"):
                        stop_reason = "all_tests_passed"
                        break

        except Exception as e:
            stop_reason = f"Unrecoverable error: {e}"
            self._notify("error", {"step": step, "error": str(e)})

        if stop_reason:
            finish_reason = "parse_failure" if "解析失败" in stop_reason else \
                            "repeated_action" if "相同无效动作" in stop_reason else \
                            "keyboard_interrupt" if "用户手动中断" in stop_reason else \
                            "all_tests_passed" if stop_reason == "all_tests_passed" else \
                            "error"
        else:
            finish_reason = "finish_action" if finished else "max_steps"

        audit_log = logger.get_entries()

        # Extract summary fields from the audit log for the caller.
        modified_files = []
        for entry in audit_log:
            action = entry.get("action", {}) or {}
            if action.get("action") in ("write_file", "edit_file") and \
                    entry.get("final_decision") == "EXECUTED":
                path = action.get("path")
                if path and path not in modified_files:
                    modified_files.append(path)

        final_test_result = None
        for entry in reversed(audit_log):
            action = entry.get("action", {}) or {}
            if action.get("action") in ("run_pytest", "run_command"):
                final_test_result = entry.get("tool_result")
                break

        result = {
            "success": True,
            "steps": step,
            "finish_reason": finish_reason,
            "stop_reason": stop_reason,
            "audit_log": audit_log,
            "modified_files": modified_files,
            "final_test_result": final_test_result,
            "pending": [],
        }
        self._notify("completed", result)
        return result


def run(task, workspace, max_steps=10, *,
        llm_client=None, parse_fn=None,
        validate_fn=None, assess_risk_fn=None,
        approval_fn=None, tools_module=None, config=None):
    """向后兼容的模块级入口。等价于创建 Agent 实例后调用 run()。"""
    agent = Agent(
        llm_client=llm_client,
        parse_fn=parse_fn,
        validate_fn=validate_fn,
        assess_risk_fn=assess_risk_fn,
        approval_fn=approval_fn,
        tools_module=tools_module,
        config=config,
    )
    return agent.run(task, workspace, max_steps=max_steps)


def _call_approval(approval_fn, risk, action_dict, workspace):
    if hasattr(approval_fn, "request_approval"):
        return approval_fn.request_approval(risk)
    return approval_fn(risk)


def _build_context(task, memory=None):
    system_prompt = (
        "You are a coding assistant. Your task is to help fix code issues.\n\n"
        "You MUST respond with a JSON object containing an 'action' field and any required parameters.\n\n"
        "Available actions:\n"
        '- list_files: {"action": "list_files", "path": "src/"}\n'
        '- read_file: {"action": "read_file", "path": "src/main.py"}\n'
        '- write_file: {"action": "write_file", "path": "src/main.py", "content": "..."}\n'
        '- edit_file: {"action": "edit_file", "path": "src/main.py", "start_line": 10, "end_line": 15, "new_content": "..."}\n'
        '- run_pytest: {"action": "run_pytest"}\n'
        '- run_command: {"action": "run_command", "command": "pytest"}\n'
        '- finish: {"action": "finish", "summary": "Task completed"}\n\n'
        "Respond with ONLY the JSON object, no markdown code blocks or extra text."
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": task},
    ]
    if memory is not None:
        recent = memory.get_recent(5)
        if recent:
            history_text = "Recent actions:\n" + json.dumps(recent, indent=2, ensure_ascii=False)
            messages.append({"role": "user", "content": history_text})
    return messages