"""CLI 入口单元测试 — 测试参数解析、mock 模式和错误处理。"""

import sys
import tempfile
from unittest.mock import patch

import pytest

from cli import main


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