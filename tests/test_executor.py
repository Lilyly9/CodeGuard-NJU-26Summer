"""executor 模块单元测试 — 覆盖所有工具分发分支。"""

import pytest

from src.executor import execute_tool


class FakeConfig:
    pass


class MockTools:
    def __init__(self):
        self.calls = []

    def list_files(self, path, workspace):
        self.calls.append(("list_files", path))
        return {"success": True, "data": [], "error": None, "meta": {}}

    def read_file(self, path, workspace):
        self.calls.append(("read_file", path))
        return {"success": True, "data": "content", "error": None, "meta": {}}

    def write_file(self, path, content, workspace, config=None):
        self.calls.append(("write_file", path))
        return {"success": True, "data": None, "error": None, "meta": {"diff": "+x"}}

    def edit_file(self, path, start_line, end_line, new_content, workspace):
        self.calls.append(("edit_file", path))
        return {"success": True, "data": "edited", "error": None, "meta": {"diff": "-old\n+new"}}

    def run_pytest(self, workspace, command="pytest", timeout=30):
        self.calls.append(("run_pytest", command))
        return {"success": True, "data": "1 passed", "error": None, "meta": {}}

    def run_command(self, command, workspace):
        self.calls.append(("run_command", command))
        return {"success": True, "data": "OK", "error": None, "meta": {}}


class TestExecuteTool:
    def test_list_files(self):
        tools = MockTools()
        result = execute_tool("list_files", {"path": "src/"}, "/ws", FakeConfig(), tools)
        assert result["success"] is True
        assert tools.calls[0] == ("list_files", "src/")

    def test_read_file(self):
        tools = MockTools()
        result = execute_tool("read_file", {"path": "x.py"}, "/ws", FakeConfig(), tools)
        assert result["success"] is True
        assert tools.calls[0] == ("read_file", "x.py")

    def test_write_file(self):
        tools = MockTools()
        result = execute_tool("write_file", {"path": "x.py", "content": "x=1"}, "/ws", FakeConfig(), tools)
        assert result["success"] is True
        assert tools.calls[0] == ("write_file", "x.py")

    def test_edit_file(self):
        tools = MockTools()
        result = execute_tool(
            "edit_file",
            {"path": "x.py", "start_line": 1, "end_line": 2, "new_content": "x"},
            "/ws",
            FakeConfig(),
            tools,
        )
        assert result["success"] is True
        assert tools.calls[0] == ("edit_file", "x.py")

    def test_run_pytest(self):
        tools = MockTools()
        result = execute_tool("run_pytest", {}, "/ws", FakeConfig(), tools)
        assert result["success"] is True
        assert tools.calls[0][0] == "run_pytest"

    def test_run_command(self):
        tools = MockTools()
        result = execute_tool("run_command", {"command": "pytest"}, "/ws", FakeConfig(), tools)
        assert result["success"] is True
        assert tools.calls[0] == ("run_command", "pytest")

    def test_finish(self):
        tools = MockTools()
        result = execute_tool("finish", {"summary": "done"}, "/ws", FakeConfig(), tools)
        assert result["success"] is True
        assert result["meta"]["finished"] is True
        assert result["data"] == "done"

    def test_unknown_action(self):
        tools = MockTools()
        result = execute_tool("unknown", {}, "/ws", FakeConfig(), tools)
        assert result["success"] is False
        assert "Unknown action" in result["error"]