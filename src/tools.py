"""Tools — 文件操作与命令执行工具。

所有路径操作均校验是否在 workspace 内。
"""

import difflib
import os
import subprocess
from pathlib import Path

_ALLOWED_COMMANDS = {"pytest", "python", "ruff", "mypy", "git diff", "git status"}
_MAX_READ_SIZE = 10000
_MAX_FILE_SIZE = 100 * 1024
_BLOCKED_DIRS = {".git", "__pycache__"}
_BLOCKED_FILES = {".env"}
_DEFAULT_TIMEOUT = 30


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
    if not os.path.isabs(path):
        path = os.path.join(workspace, path)
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
    if not path:
        return _make_error("Path cannot be empty")

    if not os.path.isabs(path):
        path = os.path.join(workspace, path)
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


def write_file(path: str, content: str, workspace: str, config=None) -> dict:
    # Ensure workspace exists on disk before any path operations
    ws_abs = os.path.abspath(workspace)
    os.makedirs(ws_abs, exist_ok=True)

    if not os.path.isabs(path):
        path = os.path.join(ws_abs, path)
    if not _is_inside_workspace(path, ws_abs):
        return _make_error("Path outside workspace")

    max_size = _MAX_FILE_SIZE
    if config is not None:
        max_size = config.max_file_size

    if len(content) > max_size:
        return _make_error(f"Content too large: {len(content)} bytes (max {max_size})")

    p = Path(path)
    if p.name in _BLOCKED_FILES:
        return _make_error("Cannot write to .env file")

    if ".git" in p.resolve().parts:
        return _make_error("Cannot write to .git directory")

    old_content = ""
    if p.exists():
        old_content = p.read_text(encoding="utf-8")

    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")

    # Invalidate bytecode cache (.pyc) so the next pytest/import always
    # reads the updated source — critical on Linux CI where filesystem
    # timestamp granularity can be too coarse to trigger recompilation.
    if p.suffix == ".py":
        pycache_dir = p.parent / "__pycache__"
        if pycache_dir.is_dir():
            stem = p.stem
            for pyc in list(pycache_dir.glob(f"{stem}*.pyc")):
                try:
                    pyc.unlink()
                except OSError:
                    pass

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


def run_pytest(workspace: str, command: str = "pytest", timeout: int = _DEFAULT_TIMEOUT) -> dict:
    # Ensure workspace exists and is absolute so pytest always runs in the right directory
    ws = os.path.abspath(workspace)
    os.makedirs(ws, exist_ok=True)
    try:
        proc = subprocess.run(
            command.split(),
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=ws,
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

    # Ensure workspace exists and is absolute so commands always run in the right directory
    ws = os.path.abspath(workspace)
    os.makedirs(ws, exist_ok=True)

    try:
        proc = subprocess.run(
            command.split(),
            shell=False,
            capture_output=True,
            text=True,
            timeout=_DEFAULT_TIMEOUT,
            cwd=ws,
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


def edit_file(path: str, start_line: int, end_line: int, new_content: str, workspace: str) -> dict:
    if not os.path.isabs(path):
        path = os.path.join(workspace, path)
    if not _is_inside_workspace(path, workspace):
        return _make_error("Path outside workspace")

    p = Path(path)
    basename = p.name

    if basename in _BLOCKED_FILES:
        return _make_error("Cannot edit .env file")

    if basename.endswith(".pem"):
        return _make_error("Cannot edit .pem file")

    if basename.endswith(".key"):
        return _make_error("Cannot edit .key file")

    parts = p.resolve().parts
    if ".git" in parts:
        return _make_error("Cannot edit .git directory")

    if not p.exists():
        return _make_error("File not found")

    if not p.is_file():
        return _make_error("Not a file")

    if _is_binary(p):
        return _make_error("Cannot edit binary file")

    file_size = p.stat().st_size
    if file_size > _MAX_FILE_SIZE:
        return _make_error(f"File too large: {file_size} bytes (max {_MAX_FILE_SIZE})")

    try:
        old_content = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return _make_error("Cannot edit binary file")

    lines = old_content.splitlines(keepends=True)

    if start_line < 1:
        return _make_error("start_line must be >= 1")
    if end_line > len(lines):
        return _make_error(f"end_line ({end_line}) exceeds file length ({len(lines)})")
    if start_line > end_line:
        return _make_error("start_line must be <= end_line")

    if new_content and not new_content.endswith("\n"):
        new_content = new_content + "\n"

    backup_path = p.with_suffix(p.suffix + ".bak")
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path.write_text(old_content, encoding="utf-8")

    new_lines = lines[:start_line - 1] + [new_content] + lines[end_line:]
    new_text = "".join(new_lines)
    p.write_text(new_text, encoding="utf-8")

    diff_lines = list(
        difflib.unified_diff(
            old_content.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=str(p),
            tofile=str(p),
            lineterm="",
        )
    )
    diff_text = "\n".join(diff_lines) if diff_lines else "(no changes)"

    return _make_success(new_text, diff=diff_text)