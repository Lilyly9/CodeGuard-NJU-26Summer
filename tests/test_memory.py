"""TDD Task 10: Memory 对话记忆模块测试 — 历史截断、持久化、get_recent。"""

import json
import pytest
from pathlib import Path

from src.memory import Memory


class TestMemoryCreation:
    def test_create_minimal(self):
        m = Memory(task="fix bug")
        assert m.task == "fix bug"
        assert m.history == []
        assert m.last_test_result is None
        assert m.step_count == 0

    def test_create_with_history(self):
        m = Memory(task="test", history=[{"action": "read_file", "path": "x.py"}])
        assert len(m.history) == 1
        assert m.history[0]["action"] == "read_file"


class TestMemoryAddHistory:
    def test_add_history_increments_step_count(self):
        m = Memory(task="test")
        m.add_history({"action": "read_file", "path": "x.py"}, {"success": True})
        assert m.step_count == 1
        assert len(m.history) == 1

    def test_add_history_stores_action_and_result(self):
        m = Memory(task="test")
        m.add_history(
            {"action": "write_file", "path": "y.py", "content": "x=1"},
            {"success": True, "data": None, "error": None, "meta": {"diff": "+x=1"}},
        )
        entry = m.history[0]
        assert entry["action"]["action"] == "write_file"
        assert entry["result"]["success"] is True

    def test_add_30_truncates_to_20(self):
        m = Memory(task="test")
        for i in range(30):
            m.add_history({"action": "read_file", "path": f"file_{i}.py"}, {"success": True})
        assert len(m.history) == 20
        assert m.step_count == 30
        assert m.history[0]["action"]["path"] == "file_10.py"
        assert m.history[-1]["action"]["path"] == "file_29.py"

    def test_add_5_no_truncation(self):
        m = Memory(task="test")
        for i in range(5):
            m.add_history({"action": "read_file", "path": f"file_{i}.py"}, {"success": True})
        assert len(m.history) == 5


class TestGetRecent:
    def test_get_recent_5(self):
        m = Memory(task="test")
        for i in range(10):
            m.add_history({"action": "read_file", "path": f"file_{i}.py"}, {"success": True})
        recent = m.get_recent(5)
        assert len(recent) == 5
        assert recent[0]["action"]["path"] == "file_5.py"
        assert recent[-1]["action"]["path"] == "file_9.py"

    def test_get_recent_less_than_available(self):
        m = Memory(task="test")
        for i in range(3):
            m.add_history({"action": "read_file", "path": f"file_{i}.py"}, {"success": True})
        recent = m.get_recent(10)
        assert len(recent) == 3

    def test_get_recent_default_n(self):
        m = Memory(task="test")
        for i in range(10):
            m.add_history({"action": "read_file", "path": f"file_{i}.py"}, {"success": True})
        recent = m.get_recent()
        assert len(recent) == 5

    def test_get_recent_empty_history(self):
        m = Memory(task="test")
        recent = m.get_recent()
        assert recent == []


class TestMemoryPersistence:
    def test_save_and_load(self, tmp_path):
        save_path = tmp_path / "memory.json"
        m = Memory(task="fix bug")
        m.add_history({"action": "read_file", "path": "x.py"}, {"success": True, "data": "hello"})
        m.add_history({"action": "write_file", "path": "y.py", "content": "x=1"},
                       {"success": True, "data": None, "meta": {"diff": "+x=1"}})
        m.last_test_result = {"success": True, "exit_code": 0}
        m.save(str(save_path))

        m2 = Memory(task="")
        m2.load(str(save_path))
        assert m2.task == "fix bug"
        assert m2.step_count == 2
        assert len(m2.history) == 2
        assert m2.history[0]["action"]["path"] == "x.py"
        assert m2.history[1]["action"]["path"] == "y.py"
        assert m2.last_test_result["success"] is True

    def test_load_nonexistent_file(self, tmp_path):
        m = Memory(task="test")
        m.load(str(tmp_path / "nonexistent.json"))
        assert m.task == "test"
        assert m.history == []
        assert m.step_count == 0

    def test_save_creates_parent_dirs(self, tmp_path):
        save_path = tmp_path / "subdir" / "nested" / "memory.json"
        m = Memory(task="test")
        m.save(str(save_path))
        assert save_path.exists()

    def test_save_truncates_history_to_20(self, tmp_path):
        save_path = tmp_path / "memory.json"
        m = Memory(task="test")
        for i in range(30):
            m.add_history({"action": "read_file", "path": f"file_{i}.py"}, {"success": True})
        m.save(str(save_path))

        loaded = json.loads(save_path.read_text())
        assert len(loaded["history"]) == 20

    def test_save_preserves_step_count(self, tmp_path):
        save_path = tmp_path / "memory.json"
        m = Memory(task="test")
        for i in range(25):
            m.add_history({"action": "read_file", "path": f"file_{i}.py"}, {"success": True})
        m.save(str(save_path))

        loaded = json.loads(save_path.read_text())
        assert loaded["step_count"] == 25


class TestMemoryLastTestResult:
    def test_update_last_test_result(self):
        m = Memory(task="test")
        m.last_test_result = {"success": True, "exit_code": 0}
        assert m.last_test_result["success"] is True

    def test_last_test_result_initially_none(self):
        m = Memory(task="test")
        assert m.last_test_result is None


class TestMemorySensitiveFiltering:
    def test_filters_api_key_in_result(self):
        m = Memory(task="test")
        m.add_history(
            {"action": "run_command", "command": "pytest"},
            {"success": False, "error": "x", "meta": {"api_key": "sk-secret-123"}},
        )
        serialized = json.dumps(m.history, ensure_ascii=False)
        assert "sk-secret-123" not in serialized
        assert "***REDACTED***" in serialized

    def test_filters_password_in_result(self):
        m = Memory(task="test")
        m.add_history(
            {"action": "write_file", "path": "x.py"},
            {"success": True, "data": None, "error": None,
             "meta": {"password": "hunter2"}},
        )
        serialized = json.dumps(m.history, ensure_ascii=False)
        assert "hunter2" not in serialized

    def test_does_not_filter_normal_fields(self):
        m = Memory(task="test")
        m.add_history(
            {"action": "read_file", "path": "main.py"},
            {"success": True, "data": "hello", "error": None, "meta": {}},
        )
        entry = m.history[0]
        assert entry["result"]["data"] == "hello"