"""LLM 输出解析器 — 返回 ParseResult 对象。

parse_llm_output(raw) 成功 → ParseResult(action=Action(type, params), error=None)
                     失败 → ParseResult(action=None, error="...")
"""

import json

from src.models import ParseResult, Action

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
            return ParseResult(action=None, error="Invalid JSON")

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError, TypeError):
        return ParseResult(action=None, error="Invalid JSON")

    if not isinstance(data, dict):
        return ParseResult(action=None, error="Invalid JSON")

    action_name = data.get("action")
    if not action_name or not isinstance(action_name, str) or not action_name.strip():
        return ParseResult(action=None, error="Missing 'action' field")

    action_name = action_name.strip()

    if action_name not in _ALLOWED_ACTIONS:
        return ParseResult(action=None, error="Unknown action: {}".format(action_name))

    required = _REQUIRED_PARAMS.get(action_name, [])
    params = {}
    for param in required:
        value = data.get(param)
        if value is None or (isinstance(value, str) and not value.strip()):
            return ParseResult(action=None, error="Missing required param: {}".format(param))
        params[param] = value

    for key, value in data.items():
        if key != "action" and key not in params:
            params[key] = value

    action = Action(type=action_name, params=params)
    return ParseResult(action=action, error=None)