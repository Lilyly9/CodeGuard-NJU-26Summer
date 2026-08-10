"""Guardrail — 风险分级护栏（纯代码判断，非提示词约束）。

evaluate(action, workspace) -> "low" | "medium" | "high" | "forbidden"
"""

from pathlib import Path

_FORBIDDEN_COMMANDS = {"rm -rf /", "shutdown", "format"}
_FORBIDDEN_SHELL_CHARS = {"&&", "||", "|", ";"}
_SENSITIVE_SUFFIXES = {".env", ".pem", ".key"}
_HIGH_COMMANDS = {"rm", "git commit"}
_READ_ONLY_ACTIONS = {"read_file", "list_files"}
_WRITE_ACTIONS = {"write_file", "edit_file"}
_READ_ONLY_COMMANDS = {"git status"}


def _is_inside_workspace(path_str: str, workspace: str) -> bool:
    try:
        resolved = (Path(workspace) / path_str).resolve()
        workspace_resolved = Path(workspace).resolve()
        return str(resolved).startswith(str(workspace_resolved))
    except (ValueError, OSError):
        return False


def _has_path_traversal(path_str: str) -> bool:
    return ".." in path_str.replace("\\", "/").split("/")


def _is_sensitive_suffix(path_str: str) -> bool:
    name = Path(path_str).name
    return any(name.endswith(suffix) for suffix in _SENSITIVE_SUFFIXES)


def evaluate(action: dict, workspace: str) -> str:
    action_type = action.get("action", "")
    command = action.get("command", "")
    path = action.get("path", "")

    # --- FORBIDDEN checks (highest priority) ---

    if path and _has_path_traversal(path):
        return "forbidden"

    if path and _is_sensitive_suffix(path):
        return "forbidden"

    if command:
        if any(ch in command for ch in _FORBIDDEN_SHELL_CHARS):
            return "forbidden"

        if any(fc in command for fc in _FORBIDDEN_COMMANDS):
            return "forbidden"

    # --- HIGH checks ---

    if command:
        if any(command.startswith(hc) for hc in _HIGH_COMMANDS):
            return "high"

    if action_type in _WRITE_ACTIONS and path:
        if not _is_inside_workspace(path, workspace):
            return "high"

    # --- LOW checks ---

    if action_type in _READ_ONLY_ACTIONS:
        return "low"

    if command and any(command.startswith(rc) for rc in _READ_ONLY_COMMANDS):
        return "low"

    # --- MEDIUM (default) ---

    return "medium"