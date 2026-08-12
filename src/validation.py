"""Validation 层 — 预执行验证，两阶段安全校验的第一阶段。

validate_action(parsed, workspace, config) 返回 ValidationResult 对象。
"""

import os

from src.parser import _ALLOWED_ACTIONS, _REQUIRED_PARAMS
from src.models import ValidationResult

_PARAM_TYPES = {
    "path": (str,),
    "content": (str,),
    "new_content": (str,),
    "start_line": (int,),
    "end_line": (int,),
    "command": (str,),
    "summary": (str,),
}

_SENSITIVE_EXTENSIONS = {".pem", ".key"}
_SENSITIVE_FILES = {".env"}


def validate_action(parsed: dict, workspace: str, config) -> ValidationResult:
    errors = []
    warnings = []

    if not isinstance(parsed, dict):
        return ValidationResult(
            valid=False,
            reason="Parsed action is not a dictionary",
            errors=["Parsed action is not a dictionary"],
        )

    action = parsed.get("action")
    if not action or not isinstance(action, str) or not action.strip():
        errors.append("Missing or invalid 'action' field")
        return ValidationResult(
            valid=False,
            reason="Missing or invalid 'action' field",
            errors=errors,
        )

    action = action.strip()

    if action not in _ALLOWED_ACTIONS:
        errors.append(f"Unknown action: {action}")
        return ValidationResult(
            valid=False,
            reason=f"Unknown action: {action}",
            errors=errors,
        )

    required = _REQUIRED_PARAMS.get(action, [])
    for param in required:
        value = parsed.get(param)
        if value is None or (isinstance(value, str) and not value.strip()):
            errors.append(f"Missing required param: {param}")

    for param, value in parsed.items():
        if param == "action":
            continue
        expected_types = _PARAM_TYPES.get(param)
        if expected_types is not None and value is not None:
            if not isinstance(value, expected_types):
                errors.append(
                    f"Type error for '{param}': expected {expected_types}, got {type(value).__name__}"
                )

    path = parsed.get("path")
    if path and isinstance(path, str):
        if ".." in path:
            errors.append("Path traversal detected: '..' in path")

        if ".git" in path.replace("\\", "/").split("/"):
            errors.append("Cannot access .git directory")

        basename = os.path.basename(path)
        if basename in _SENSITIVE_FILES:
            errors.append(f"Cannot access sensitive file: {basename}")

        ext = os.path.splitext(basename)[1]
        if ext in _SENSITIVE_EXTENSIONS:
            errors.append(f"Cannot access sensitive file: {basename}")

        if action in ("write_file", "edit_file", "read_file", "list_files"):
            if not _is_inside_workspace(path, workspace):
                errors.append("Path outside workspace")

    known_fields = {"action"}.union(required).union({"summary", "reason"})
    for key in parsed:
        if key not in known_fields:
            warnings.append(f"Unknown field: {key}")

    if errors:
        return ValidationResult(
            valid=False,
            reason="; ".join(errors),
            errors=errors,
            warnings=warnings,
        )

    return ValidationResult(
        valid=True,
        sanitized_params=dict(parsed),
        warnings=warnings,
    )


def _is_inside_workspace(path_str: str, workspace: str) -> bool:
    try:
        if not os.path.isabs(path_str):
            path_str = os.path.join(workspace, path_str)
        resolved_path = os.path.realpath(path_str)
        resolved_ws = os.path.realpath(workspace)
        common = os.path.commonpath([resolved_path, resolved_ws])
        return common == resolved_ws
    except ValueError:
        return False