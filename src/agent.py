"""Agent 主循环 — 手写 while 循环，绝对禁止使用 LangChain。

run(task, workspace, max_steps=10) 驱动完整的"感知-决策-执行-反馈"闭环。
"""

import json
from datetime import datetime

from src.memory import Memory


def run(task, workspace, max_steps=10, *,
        llm_client=None, parse_fn=None, evaluate_fn=None,
        approval_fn=None, tools_module=None):
    if llm_client is None:
        from src.llm_client import LLMClient
        llm_client = LLMClient()
    if parse_fn is None:
        from src.parser import parse_llm_output
        parse_fn = parse_llm_output
    if evaluate_fn is None:
        from src.guardrail import evaluate
        evaluate_fn = evaluate
    if approval_fn is None:
        from src.approval import request_approval
        approval_fn = request_approval
    if tools_module is None:
        import src.tools as tools_module

    memory = Memory(task=task)
    context = _build_context(task, memory)
    step = 0
    audit_log = []
    finished = False

    while step < max_steps:
        step += 1

        raw = llm_client.get_response(context)

        parsed = parse_fn(raw)
        if "error" in parsed:
            context.append({"role": "user", "content": f"Parse error: {parsed['error']}. Please respond with valid JSON."})
            audit_log.append({
                "step": step,
                "timestamp": datetime.now(),
                "action": {},
                "risk_level": "",
                "final_decision": "PARSE_ERROR",
            })
            memory.add_history({}, {"success": False, "error": parsed["error"]})
            continue

        action = parsed

        if action.get("action") == "finish":
            audit_log.append({
                "step": step,
                "timestamp": datetime.now(),
                "action": action,
                "risk_level": "",
                "final_decision": "FINISHED",
            })
            memory.add_history(action, {"success": True, "meta": {"finished": True}})
            finished = True
            break

        risk_level = evaluate_fn(action, workspace)

        if risk_level == "forbidden":
            context.append({
                "role": "user",
                "content": f"Action '{action.get('action')}' is forbidden by security policy. Please try a different approach.",
            })
            audit_log.append({
                "step": step,
                "timestamp": datetime.now(),
                "action": action,
                "risk_level": risk_level,
                "final_decision": "BLOCKED",
            })
            memory.add_history(action, {"success": False, "error": "Action forbidden", "meta": {"blocked": True}})
            continue

        if risk_level == "high":
            approved = _call_approval(approval_fn, action, workspace)
            if not approved:
                context.append({
                    "role": "user",
                    "content": "User rejected the action. Please try a different approach.",
                })
                audit_log.append({
                    "step": step,
                    "timestamp": datetime.now(),
                    "action": action,
                    "risk_level": risk_level,
                    "final_decision": "REJECTED",
                })
                memory.add_history(action, {"success": False, "error": "User rejected", "meta": {"blocked": True}})
                continue

        tool_result = _execute_tool(action, workspace, tools_module)
        feedback = _build_feedback(tool_result)
        context.append({"role": "user", "content": feedback})

        audit_log.append({
            "step": step,
            "timestamp": datetime.now(),
            "action": action,
            "risk_level": risk_level,
            "tool_result": tool_result,
            "final_decision": "EXECUTED",
        })
        memory.add_history(action, tool_result)
        if action.get("action") == "run_tests":
            memory.last_test_result = tool_result

    finish_reason = "finish_action" if finished else "max_steps"

    return {
        "success": True,
        "steps": step,
        "finish_reason": finish_reason,
        "audit_log": _serialize_audit_log(audit_log),
    }


def _call_approval(approval_fn, action, workspace):
    if hasattr(approval_fn, "request_approval"):
        return approval_fn.request_approval(action, workspace)
    return approval_fn(action, workspace)


def _build_context(task, memory=None):
    system_prompt = (
        "You are a coding assistant. Your task is to help fix code issues.\n\n"
        "You MUST respond with a JSON object containing an 'action' field and any required parameters.\n\n"
        "Available actions:\n"
        '- list_files: {"action": "list_files", "path": "src/"}\n'
        '- read_file: {"action": "read_file", "path": "src/main.py"}\n'
        '- write_file: {"action": "write_file", "path": "src/main.py", "content": "..."}\n'
        '- run_tests: {"action": "run_tests"}\n'
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


def _execute_tool(action, workspace, tools):
    action_type = action.get("action")
    if action_type == "list_files":
        path = action.get("path", workspace)
        return tools.list_files(path, workspace)
    elif action_type == "read_file":
        return tools.read_file(action["path"], workspace)
    elif action_type == "write_file":
        return tools.write_file(action["path"], action["content"], workspace)
    elif action_type == "run_tests":
        return tools.run_tests(workspace)
    elif action_type == "run_command":
        return tools.run_command(action["command"], workspace)
    elif action_type == "finish":
        return {"success": True, "data": action.get("summary", ""), "error": None, "meta": {"finished": True}}
    else:
        return {"success": False, "data": None, "error": f"Unknown action: {action_type}", "meta": {}}


def _build_feedback(result):
    if result.get("success"):
        data = result.get("data")
        if data:
            return f"Tool executed successfully.\nOutput:\n{data}"
        meta = result.get("meta", {})
        if meta.get("diff"):
            return f"Tool executed successfully.\nDiff:\n{meta['diff']}"
        return "Tool executed successfully."
    else:
        return f"Tool execution failed: {result.get('error', 'Unknown error')}"


def _serialize_audit_log(audit_log):
    result = []
    for entry in audit_log:
        serialized = dict(entry)
        if "timestamp" in serialized and isinstance(serialized["timestamp"], datetime):
            serialized["timestamp"] = serialized["timestamp"].isoformat()
        if "tool_result" in serialized:
            tr = serialized["tool_result"]
            if isinstance(tr, dict):
                serialized["tool_result"] = {
                    "success": tr.get("success"),
                    "data": str(tr.get("data")) if tr.get("data") is not None else None,
                    "error": tr.get("error"),
                    "meta": {str(k): str(v) for k, v in tr.get("meta", {}).items()},
                }
        result.append(serialized)
    return result