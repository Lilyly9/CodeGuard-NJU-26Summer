"""LLM 输出解析器 — 解析 LLM 原始输出为结构化动作指令。

parse_llm_output(raw) 对合法 JSON 返回解析后的 dict；
对非法 JSON / 缺失字段 / 不支持动作返回 {"error": ..., "raw": ...}。
"""

import json

_ALLOWED_ACTIONS = frozenset(
    {"read_file", "write_file", "run_tests", "run_command", "list_files", "finish"}
)

_REQUIRED_PARAMS = {
    "read_file": ["path"],
    "write_file": ["path", "content"],
    "run_command": ["command"],
    "run_tests": [],
    "list_files": [],
    "finish": [],
}


def parse_llm_output(raw):
    if not isinstance(raw, str):
        try:
            raw = str(raw)
        except Exception:
            return {"error": "Invalid JSON", "raw": repr(raw)}

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError, TypeError):
        return {"error": "Invalid JSON", "raw": raw}

    if not isinstance(data, dict):
        return {"error": "Invalid JSON", "raw": raw}

    action = data.get("action")
    if not action or not isinstance(action, str) or not action.strip():
        return {"error": "Missing 'action' field", "raw": raw}

    action = action.strip()

    if action not in _ALLOWED_ACTIONS:
        return {"error": "Unknown action: {}".format(action), "raw": raw}

    required = _REQUIRED_PARAMS.get(action, [])
    for param in required:
        value = data.get(param)
        if value is None or (isinstance(value, str) and not value.strip()):
            return {"error": "Missing required param: {}".format(param), "raw": raw}

    return data