"""LLM 输出解析器 — 解析 LLM 原始输出为结构化动作指令。

parse_llm_output(raw) 返回 ParseResult dataclass。
成功时 ParseResult.action 包含 Action(type, params, reason)；
失败时 ParseResult.error 包含错误描述。
"""

import json

from src.models import Action, ParseResult

_ALLOWED_ACTIONS = frozenset(
    {"read_file", "write_file", "edit_file", "run_pytest", "run_command", "list_files", "finish"}
)

_REQUIRED_PARAMS = {
    "read_file": ["path"],
    "write_file": ["path", "content"],
    "edit_file": ["path", "start_line", "end_line", "new_content"],
    "run_command": ["command"],
    "run_pytest": [],
    "list_files": [],
    "finish": [],
}


def parse_llm_output(raw) -> ParseResult:
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
    for param in required:
        value = data.get(param)
        if value is None or (isinstance(value, str) and not value.strip()):
            return ParseResult(action=None, error="Missing required param: {}".format(param))

    params = {k: v for k, v in data.items() if k != "action"}

    return ParseResult(
        action=Action(type=action_name, params=params),
        error=None,
    )