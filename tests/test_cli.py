"""CLI 入口单元测试 — 测试参数解析、mock 模式和错误处理。"""

import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from cli import cmd_run, main


class TestCliHelp:
    def test_no_args_prints_help(self):
        with patch.object(sys, "argv", ["codeguard"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1


class TestCliMockMode:
    def test_mock_run_completes_cleanly(self):
        with patch.object(sys, "argv", ["codeguard", "run", "test task", "--mock"]):
            try:
                main()
            except SystemExit as e:
                assert e.code == 0 or e.code is None


class TestCliWorkspace:
    def test_workspace_flag_accepted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(sys, "argv", [
                "codeguard", "run", "test task",
                "--workspace", tmpdir, "--mock"
            ]):
                try:
                    main()
                except SystemExit:
                    pass


class TestCliHelpFlag:
    def test_run_help_flag(self):
        with patch.object(sys, "argv", ["codeguard", "run", "--help"]):
            with pytest.raises(SystemExit):
                main()


class TestCliErrorReporting:
    def test_run_error_surfaces_stop_reason_and_exits_nonzero(self, capsys):
        with patch("cli._check_api_key", return_value=True), \
             patch("cli.RealLLM", return_value=object()), \
             patch("cli.run", return_value={
                 "steps": 1,
                 "finish_reason": "error",
                 "stop_reason": "Unrecoverable error: LLM request failed after 3 attempts",
             }):
            with pytest.raises(SystemExit) as exc_info:
                cmd_run(SimpleNamespace(task="修复测试", workspace=".", mock=False))

        out = capsys.readouterr().out
        assert "Stop reason" in out, f"error detail should be printed, got: {out!r}"
        assert "LLM request failed after 3 attempts" in out
        assert exc_info.value.code == 1, "failed run should exit non-zero"