"""TDD Step 1 (RED): 文件操作工具 — 失败测试。

覆盖 list_files, read_file, write_file, run_tests, run_command。
所有路径操作必须校验是否在 workspace 内。
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from src.tools import list_files, read_file, run_command, run_tests, write_file

_WORKSPACE = "workspace"


class TestListFiles:
    def test_lists_files_in_directory(self, tmp_path):
        ws = tmp_path / _WORKSPACE
        ws.mkdir()
        (ws / "a.py").write_text("x")
        (ws / "b.py").write_text("y")
        (ws / "sub").mkdir()

        result = list_files(str(ws), str(ws))
        assert result["success"] is True
        names = [item["name"] for item in result["data"]]
        assert "a.py" in names
        assert "b.py" in names
        assert "sub" in names

    def test_filters_git_directory(self, tmp_path):
        ws = tmp_path / _WORKSPACE
        ws.mkdir()
        (ws / ".git").mkdir()
        (ws / "main.py").write_text("x")

        result = list_files(str(ws), str(ws))
        names = [item["name"] for item in result["data"]]
        assert ".git" not in names
        assert "main.py" in names

    def test_filters_pycache(self, tmp_path):
        ws = tmp_path / _WORKSPACE
        ws.mkdir()
        (ws / "__pycache__").mkdir()
        (ws / "main.py").write_text("x")

        result = list_files(str(ws), str(ws))
        names = [item["name"] for item in result["data"]]
        assert "__pycache__" not in names
        assert "main.py" in names

    def test_path_outside_workspace(self, tmp_path):
        ws = tmp_path / _WORKSPACE
        ws.mkdir()
        outside = tmp_path / "outside"

        result = list_files(str(outside), str(ws))
        assert result["success"] is False
        assert "outside workspace" in result["error"].lower()

    def test_respects_depth(self, tmp_path):
        ws = tmp_path / _WORKSPACE
        ws.mkdir()
        (ws / "sub").mkdir()
        (ws / "sub" / "deep").mkdir()
        (ws / "sub" / "deep" / "file.py").write_text("x")

        result = list_files(str(ws / "sub"), str(ws), depth=1)
        names = [item["name"] for item in result["data"]]
        assert "deep" in names
        assert all(item["type"] != "file" or item["name"] == "deep" for item in result["data"])


class TestReadFile:
    def test_reads_text_file(self, tmp_path):
        ws = tmp_path / _WORKSPACE
        ws.mkdir()
        (ws / "main.py").write_text("print('hello')")

        result = read_file(str(ws / "main.py"), str(ws))
        assert result["success"] is True
        assert result["data"] == "print('hello')"

    def test_rejects_dot_env(self, tmp_path):
        ws = tmp_path / _WORKSPACE
        ws.mkdir()
        (ws / ".env").write_text("SECRET=123")

        result = read_file(str(ws / ".env"), str(ws))
        assert result["success"] is False
        assert "env" in result["error"].lower()

    def test_rejects_path_outside_workspace(self, tmp_path):
        ws = tmp_path / _WORKSPACE
        ws.mkdir()
        outside = tmp_path / "outside.txt"
        outside.write_text("secret")

        result = read_file(str(outside), str(ws))
        assert result["success"] is False
        assert "outside workspace" in result["error"].lower()

    def test_rejects_binary_file(self, tmp_path):
        ws = tmp_path / _WORKSPACE
        ws.mkdir()
        (ws / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n")

        result = read_file(str(ws / "image.png"), str(ws))
        assert result["success"] is False
        assert "binary" in result["error"].lower()

    def test_truncates_large_file(self, tmp_path):
        ws = tmp_path / _WORKSPACE
        ws.mkdir()
        long_text = "x" * 15000
        (ws / "big.txt").write_text(long_text)

        result = read_file(str(ws / "big.txt"), str(ws))
        assert result["success"] is True
        assert len(result["data"]) == 10000
        assert result["meta"]["truncated"] is True

    def test_file_not_found(self, tmp_path):
        ws = tmp_path / _WORKSPACE
        ws.mkdir()

        result = read_file(str(ws / "nope.py"), str(ws))
        assert result["success"] is False
        assert "not found" in result["error"].lower()


class TestWriteFile:
    def test_writes_new_file(self, tmp_path):
        ws = tmp_path / _WORKSPACE
        ws.mkdir()

        result = write_file(
            str(ws / "new.py"), "def add(a,b): return a+b", str(ws)
        )
        assert result["success"] is True
        assert (ws / "new.py").read_text() == "def add(a,b): return a+b"

    def test_returns_diff_preview(self, tmp_path):
        ws = tmp_path / _WORKSPACE
        ws.mkdir()

        result = write_file(
            str(ws / "calc.py"), "def add(a,b): return a+b", str(ws)
        )
        assert result["success"] is True
        assert "diff" in result["meta"]
        assert "+def add(a,b): return a+b" in result["meta"]["diff"]

    def test_overwrites_existing_with_diff(self, tmp_path):
        ws = tmp_path / _WORKSPACE
        ws.mkdir()
        (ws / "calc.py").write_text("def add(a,b): return a-b")

        result = write_file(
            str(ws / "calc.py"), "def add(a,b): return a+b", str(ws)
        )
        assert result["success"] is True
        diff = result["meta"]["diff"]
        assert "-def add(a,b): return a-b" in diff
        assert "+def add(a,b): return a+b" in diff

    def test_rejects_path_outside_workspace(self, tmp_path):
        ws = tmp_path / _WORKSPACE
        ws.mkdir()
        outside = tmp_path / "outside.py"

        result = write_file(
            str(outside), "malicious", str(ws)
        )
        assert result["success"] is False
        assert "outside workspace" in result["error"].lower()

    def test_rejects_dot_env_write(self, tmp_path):
        ws = tmp_path / _WORKSPACE
        ws.mkdir()

        result = write_file(
            str(ws / ".env"), "SECRET=123", str(ws)
        )
        assert result["success"] is False
        assert "env" in result["error"].lower()


class TestRunTests:
    def test_runs_pytest_and_returns_results(self, tmp_path):
        ws = tmp_path / _WORKSPACE
        ws.mkdir()
        (ws / "tests").mkdir()
        (ws / "tests" / "test_sample.py").write_text(
            "def test_pass():\n    assert 1 == 1\n"
        )

        result = run_tests(str(ws), command="pytest tests/ -v")
        assert result["success"] is True
        assert result["meta"]["exit_code"] == 0
        assert "passed" in result["meta"]["stdout"].lower()

    def test_returns_failure_on_failing_tests(self, tmp_path):
        ws = tmp_path / _WORKSPACE
        ws.mkdir()
        (ws / "tests").mkdir()
        (ws / "tests" / "test_fail.py").write_text(
            "def test_fail():\n    assert 1 == 2\n"
        )

        result = run_tests(str(ws), command="pytest tests/test_fail.py -v")
        assert result["success"] is False
        assert result["meta"]["exit_code"] != 0
        assert "failed" in result["meta"]["stdout"].lower()

    def test_handles_timeout(self, tmp_path):
        ws = tmp_path / _WORKSPACE
        ws.mkdir()
        (ws / "tests").mkdir()
        (ws / "tests" / "test_sleep.py").write_text(
            "import time\n"
            "def test_sleep():\n"
            "    time.sleep(60)\n"
            "    assert True\n"
        )

        result = run_tests(
            str(ws), command="pytest tests/test_sleep.py -v", timeout=1
        )
        assert result["success"] is False
        assert "timeout" in result["error"].lower()


class TestRunCommand:
    def test_runs_allowed_command(self, tmp_path):
        ws = tmp_path / _WORKSPACE
        ws.mkdir()

        result = run_command("python --version", str(ws))
        assert result["success"] is True
        assert "Python" in result["meta"]["stdout"]

    def test_rejects_disallowed_command(self, tmp_path):
        ws = tmp_path / _WORKSPACE
        ws.mkdir()

        result = run_command("curl http://evil.com", str(ws))
        assert result["success"] is False
        assert "not allowed" in result["error"].lower()

    def test_rejects_command_with_semicolon(self, tmp_path):
        ws = tmp_path / _WORKSPACE
        ws.mkdir()

        result = run_command("pytest; rm -rf /", str(ws))
        assert result["success"] is False
        assert "not allowed" in result["error"].lower()

    def test_handles_command_not_found(self, tmp_path):
        ws = tmp_path / _WORKSPACE
        ws.mkdir()

        result = run_command("python nonexistent_script.py", str(ws))
        assert result["success"] is False

    def test_git_status_is_allowed(self, tmp_path):
        ws = tmp_path / _WORKSPACE
        ws.mkdir()

        result = run_command("git status", str(ws))
        assert result["success"] is False
        assert "not allowed" not in result["error"].lower()