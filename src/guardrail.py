"""风险分级护栏 — 代码判断，非提示词。

evaluate(action, workspace) 返回: "low", "medium", "high", "forbidden"
"""

import os
import re


def evaluate(action, workspace):
    action_type = (action.get("action") or "").strip()
    command = (action.get("command") or "").strip()
    path = (action.get("path") or "").strip()

    cmd_normalized = re.sub(r"\s+", " ", command)

    # ── forbidden ──────────────────────────────────────────────────────────

    if any(conn in cmd_normalized for conn in ("&&", "||", "|", ";")):
        return "forbidden"

    if re.search(r"\brm\s+-rf\s+/(?:\s|$)", cmd_normalized):
        return "forbidden"

    if re.search(r"\bshutdown\b", cmd_normalized):
        return "forbidden"

    if re.search(r"\bformat\b", cmd_normalized):
        return "forbidden"

    if ".." in path:
        return "forbidden"

    if path:
        basename = os.path.basename(path)
        if basename == ".env":
            return "forbidden"
        if basename.endswith(".pem"):
            return "forbidden"
        if basename.endswith(".key"):
            return "forbidden"

    # ── high ───────────────────────────────────────────────────────────────

    if re.search(r"\brm\b", cmd_normalized):
        return "high"

    if "git commit" in cmd_normalized:
        return "high"

    if action_type in ("write_file", "edit_file") and path:
        if _is_outside_workspace(path, workspace):
            return "high"

    # ── medium ─────────────────────────────────────────────────────────────

    if "pytest" in cmd_normalized:
        return "medium"

    if action_type in ("write_file", "edit_file") and path.endswith(".py"):
        return "medium"

    # ── low ────────────────────────────────────────────────────────────────

    if action_type == "read_file":
        return "low"

    if action_type in ("list_files", "list_directory"):
        return "low"

    if "git status" in cmd_normalized or "git diff" in cmd_normalized:
        return "low"

    return "low"


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