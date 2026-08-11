"""Agent 主循环 — 手写 while 循环，绝对禁止使用 LangChain。

run(task, workspace, max_steps=10) 驱动完整的"感知-决策-执行-反馈"闭环。
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


def run(task, workspace, max_steps=10, *,
        llm_client=None, parse_fn=None, evaluate_fn=None,
        validate_fn=None, assess_risk_fn=None,
        approval_fn=None, tools_module=None, config=None):
    if llm_client is None:
        from src.llm_client import LLMClient
        llm_client = LLMClient()
    if parse_fn is None:
        from src.parser import parse_llm_output
        parse_fn = parse_llm_output
    if evaluate_fn is None and validate_fn is None:
        from src.validation import validate_action as validate_fn
        from src.guardrail import assess_risk as assess_risk_fn
        from src.config import Config
        if config is None:
            config = Config()
    if approval_fn is None:
        from src.approval import request_approval
        approval_fn = request_approval
    if tools_module is None:
        import src.tools as tools_module
    if config is None:
        from src.config import Config
        config = Config()

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
    last_action_type = None
    action_repeat_count = 0
    stop_reason = ""

    try:
        while step < max_steps:
            step += 1

            try:
                raw = llm_client.get_response(context)
            except KeyboardInterrupt:
                stop_reason = "用户手动中断"
                break

            parsed = parse_fn(raw)
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
                last_action_type = None
                action_repeat_count = 0
                continue

            consecutive_failures = 0
            action_dict = _action_to_dict(parsed)

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

            if action_dict.get("action") == last_action_type:
                action_repeat_count += 1
                if action_repeat_count >= 3:
                    stop_reason = "连续 3 次相同无效动作"
                    break
            else:
                last_action_type = action_dict.get("action")
                action_repeat_count = 1

            if evaluate_fn is not None:
                risk = evaluate_fn(action_dict, workspace)
            else:
                validated = validate_fn(action_dict, workspace, config)
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
                risk = assess_risk_fn(validated, config)

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
                continue

            if risk.level == RiskLevel.HIGH:
                approval_result = _call_approval(approval_fn, risk, action_dict, workspace)
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
                        "final_decision": "REJECTED",
                    })
                    memory.add_history(action_dict, {"success": False, "error": "User rejected", "meta": {"blocked": True}})
                    continue

            tool_result = execute_tool(action_dict.get("action"), action_dict, workspace, config, tools_module)
            feedback = build_feedback(tool_result)
            context.append({"role": "user", "content": feedback})

            logger.log({
                "step": step,
                "timestamp": datetime.now(),
                "action": action_dict,
                "risk_level": risk.level.value,
                "tool_result": tool_result,
                "final_decision": "EXECUTED",
            })
            memory.add_history(action_dict, tool_result)
            if action_dict.get("action") == "run_pytest":
                memory.last_test_result = tool_result
                if config.auto_finish_on_test_pass and tool_result.get("success"):
                    stop_reason = "all_tests_passed"
                    break

    except Exception as e:
        stop_reason = f"Unrecoverable error: {e}"

    if stop_reason:
        finish_reason = "parse_failure" if "解析失败" in stop_reason else \
                        "repeated_action" if "相同无效动作" in stop_reason else \
                        "keyboard_interrupt" if "用户手动中断" in stop_reason else \
                        "all_tests_passed" if stop_reason == "all_tests_passed" else \
                        "error"
    else:
        finish_reason = "finish_action" if finished else "max_steps"

    return {
        "success": True,
        "steps": step,
        "finish_reason": finish_reason,
        "stop_reason": stop_reason,
        "audit_log": logger.get_entries(),
    }


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