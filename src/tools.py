"""Tools — 文件操作与命令执行工具。

所有路径操作均校验是否在 workspace 内。
"""

import difflib
import os
import subprocess
from pathlib import Path

_ALLOWED_COMMANDS = {"pytest", "python", "ruff", "git diff", "git status"}
_MAX_READ_SIZE = 10000
_BLOCKED_DIRS = {".git", "__pycache__"}
_BLOCKED_FILES = {".env"}
_DEFAULT_TIMEOUT = 30


def _is_inside_workspace(path_str: str, workspace: str) -> bool:
    try:
        resolved = Path(path_str).resolve()
        ws_resolved = Path(workspace).resolve()
        return str(resolved).startswith(str(ws_resolved))
    except (ValueError, OSError):
        return False


def _is_binary(file_path: Path) -> bool:
    try:
        with open(file_path, "rb") as f:
            chunk = f.read(1024)
        return b"\x00" in chunk
    except OSError:
        return False


def _make_error(msg: str) -> dict:
    return {"success": False, "data": None, "error": msg, "meta": {}}


def _make_success(data=None, **meta) -> dict:
    return {"success": True, "data": data, "error": None, "meta": meta}


def list_files(path: str, workspace: str, depth: int = 2) -> dict:
    if not _is_inside_workspace(path, workspace):
        return _make_error("Path outside workspace")

    p = Path(path)
    if not p.exists() or not p.is_dir():
        return _make_error("Path not found or not a directory")

    result = []
    for item in p.iterdir():
        name = item.name
        if name in _BLOCKED_DIRS:
            continue
        if item.is_dir():
            if depth > 1:
                entry = {"name": name, "type": "dir"}
                sub = list_files(str(item), workspace, depth=depth - 1)
                if sub["success"]:
                    entry["children"] = sub["data"]
                result.append(entry)
            else:
                result.append({"name": name, "type": "dir"})
        else:
            result.append({"name": name, "type": "file"})

    return _make_success(result)


def read_file(path: str, workspace: str) -> dict:
    if not _is_inside_workspace(path, workspace):
        return _make_error("Path outside workspace")

    p = Path(path)
    if p.name in _BLOCKED_FILES:
        return _make_error("Cannot read .env file")

    if not p.exists():
        return _make_error("File not found")

    if not p.is_file():
        return _make_error("Not a file")

    if _is_binary(p):
        return _make_error("Cannot read binary file")

    try:
        content = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return _make_error("Cannot read binary file")

    truncated = False
    if len(content) > _MAX_READ_SIZE:
        content = content[:_MAX_READ_SIZE]
        truncated = True

    return _make_success(content, truncated=truncated, size=len(content))


def write_file(path: str, content: str, workspace: str) -> dict:
    if not _is_inside_workspace(path, workspace):
        return _make_error("Path outside workspace")

    p = Path(path)
    if p.name in _BLOCKED_FILES:
        return _make_error("Cannot write to .env file")

    old_content = ""
    if p.exists():
        old_content = p.read_text(encoding="utf-8")

    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")

    diff_lines = list(
        difflib.unified_diff(
            old_content.splitlines(keepends=True),
            content.splitlines(keepends=True),
            fromfile=str(p),
            tofile=str(p),
            lineterm="",
        )
    )
    diff_text = "\n".join(diff_lines) if diff_lines else "(no changes)"

    return _make_success(None, diff=diff_text)


def run_tests(workspace: str, command: str = "pytest", timeout: int = _DEFAULT_TIMEOUT) -> dict:
    try:
        proc = subprocess.run(
            command.split(),
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=workspace,
            env={"PATH": os.environ.get("PATH", ""), "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")},
        )
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        return {
            "success": proc.returncode == 0,
            "data": stdout,
            "error": None if proc.returncode == 0 else stderr,
            "meta": {
                "exit_code": proc.returncode,
                "stdout": stdout,
                "stderr": stderr,
            },
        }
    except subprocess.TimeoutExpired:
        return _make_error("Command timeout: exceeded time limit")
    except FileNotFoundError:
        return _make_error("pytest not found")


def run_command(command: str, workspace: str) -> dict:
    cmd_name = command.split()[0]
    allowed = any(
        command.startswith(allowed_cmd)
        for allowed_cmd in _ALLOWED_COMMANDS
    )
    if not allowed:
        return _make_error(f"Command '{command}' not allowed")

    for ch in (";", "&&", "||", "|"):
        if ch in command:
            return _make_error(f"Command not allowed: forbidden character '{ch}'")

    try:
        proc = subprocess.run(
            command.split(),
            capture_output=True,
            text=True,
            timeout=_DEFAULT_TIMEOUT,
            cwd=workspace,
            env={"PATH": os.environ.get("PATH", ""), "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")},
        )
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        return {
            "success": proc.returncode == 0,
            "data": stdout,
            "error": None if proc.returncode == 0 else stderr,
            "meta": {
                "exit_code": proc.returncode,
                "stdout": stdout,
                "stderr": stderr,
            },
        }
    except FileNotFoundError:
        return _make_error(f"Command not found: {cmd_name}")