"""执行器单元测试。"""

import pytest

from src.executor import execute
from src.models import Action, ToolResult


class TestExecute:
    def test_execute_returns_tool_result(self):
        action = Action(type="read_file", params={"path": "src/executor.py"})
        result = execute(action, ".")
        assert isinstance(result, ToolResult)

    def test_execute_unknown_action(self):
        action = Action(type="unknown", params={})
        result = execute(action, ".")
        assert result.success is False
        assert "Unknown action" in result.error