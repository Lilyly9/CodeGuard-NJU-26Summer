"""风险分级护栏 — 代码判断，非提示词。返回 RiskDecision 对象。

evaluate(action, workspace) 返回 RiskDecision(level, rule, needs_approval, is_forbidden)
"""

import os
import re

from src.models import RiskDecision, RiskLevel


def evaluate(action, workspace):
    action_type = (action.get("action") or "").strip()
    command = (action.get("command") or "").strip()
    path = (action.get("path") or "").strip()

    cmd_normalized = re.sub(r"\s+", " ", command)

    if any(conn in cmd_normalized for conn in ("&&", "||", "|", ";")):
        return RiskDecision(
            level=RiskLevel.FORBIDDEN,
            rule="Shell connector detected in command",
            needs_approval=False,
            is_forbidden=True,
        )

    if re.search(r"\brm\s+-rf\s+/(?:\s|$)", cmd_normalized):
        return RiskDecision(
            level=RiskLevel.FORBIDDEN,
            rule="rm -rf / is forbidden",
            needs_approval=False,
            is_forbidden=True,
        )

    if re.search(r"\bshutdown\b", cmd_normalized):
        return RiskDecision(
            level=RiskLevel.FORBIDDEN,
            rule="shutdown command is forbidden",
            needs_approval=False,
            is_forbidden=True,
        )

    if re.search(r"\bformat\b", cmd_normalized):
        return RiskDecision(
            level=RiskLevel.FORBIDDEN,
            rule="format command is forbidden",
            needs_approval=False,
            is_forbidden=True,
        )

    if ".." in path:
        return RiskDecision(
            level=RiskLevel.FORBIDDEN,
            rule="Path traversal detected",
            needs_approval=False,
            is_forbidden=True,
        )

    if path:
        basename = os.path.basename(path)
        if basename == ".env":
            return RiskDecision(
                level=RiskLevel.FORBIDDEN,
                rule="Cannot access .env file",
                needs_approval=False,
                is_forbidden=True,
            )
        if basename.endswith(".pem"):
            return RiskDecision(
                level=RiskLevel.FORBIDDEN,
                rule="Cannot access .pem file",
                needs_approval=False,
                is_forbidden=True,
            )
        if basename.endswith(".key"):
            return RiskDecision(
                level=RiskLevel.FORBIDDEN,
                rule="Cannot access .key file",
                needs_approval=False,
                is_forbidden=True,
            )

    if re.search(r"\brm\b", cmd_normalized):
        return RiskDecision(
            level=RiskLevel.HIGH,
            rule="rm command requires approval",
            needs_approval=True,
            is_forbidden=False,
        )

    if "git commit" in cmd_normalized:
        return RiskDecision(
            level=RiskLevel.HIGH,
            rule="git commit requires approval",
            needs_approval=True,
            is_forbidden=False,
        )

    if action_type in ("write_file", "edit_file") and path:
        if _is_outside_workspace(path, workspace):
            return RiskDecision(
                level=RiskLevel.HIGH,
                rule="Write outside workspace requires approval",
                needs_approval=True,
                is_forbidden=False,
            )

    if "pytest" in cmd_normalized:
        return RiskDecision(
            level=RiskLevel.MEDIUM,
            rule="Test execution",
            needs_approval=False,
            is_forbidden=False,
        )

    if action_type in ("write_file", "edit_file") and path.endswith(".py"):
        return RiskDecision(
            level=RiskLevel.MEDIUM,
            rule="Python file write",
            needs_approval=False,
            is_forbidden=False,
        )

    if action_type == "read_file":
        return RiskDecision(
            level=RiskLevel.LOW,
            rule="Read-only operation",
            needs_approval=False,
            is_forbidden=False,
        )

    if action_type in ("list_files", "list_directory"):
        return RiskDecision(
            level=RiskLevel.LOW,
            rule="Read-only operation",
            needs_approval=False,
            is_forbidden=False,
        )

    if "git status" in cmd_normalized or "git diff" in cmd_normalized:
        return RiskDecision(
            level=RiskLevel.LOW,
            rule="Read-only operation",
            needs_approval=False,
            is_forbidden=False,
        )

    return RiskDecision(
        level=RiskLevel.LOW,
        rule="Default low risk",
        needs_approval=False,
        is_forbidden=False,
    )


def _is_outside_workspace(path, workspace):
    ws = os.path.normpath(os.path.abspath(workspace))
    if os.path.isabs(path):
        abs_path = os.path.normpath(os.path.abspath(path))
    else:
        abs_path = os.path.normpath(os.path.abspath(os.path.join(ws, path)))
    if os.path.splitdrive(abs_path)[0] != os.path.splitdrive(ws)[0]:
        return True
    common = os.path.commonpath([abs_path, ws])
    return os.path.normpath(common) != os.path.normpath(ws)