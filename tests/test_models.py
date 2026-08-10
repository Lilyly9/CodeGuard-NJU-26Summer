"""T02 数据模型单元测试 — 严格按 SPEC §12 验收。

覆盖 8 个核心实体 + RiskLevel 枚举的创建、默认值、字段类型、to_dict() 序列化。
"""

import json
from datetime import datetime

import pytest

from src.models import (
    Action,
    ApprovalResult,
    AuditLog,
    Memory,
    ParseResult,
    RiskDecision,
    RiskLevel,
    ToolResult,
    ValidationResult,
    _serialize,
)


# ---------------------------------------------------------------------------
# RiskLevel 枚举
# ---------------------------------------------------------------------------

class TestRiskLevel:
    def test_enum_members(self):
        assert RiskLevel.LOW.value == "LOW"
        assert RiskLevel.MEDIUM.value == "MEDIUM"
        assert RiskLevel.HIGH.value == "HIGH"
        assert RiskLevel.FORBIDDEN.value == "FORBIDDEN"

    def test_enum_is_string(self):
        assert isinstance(RiskLevel.LOW, str)

    def test_enum_iteration(self):
        levels = [lvl.value for lvl in RiskLevel]
        assert levels == ["LOW", "MEDIUM", "HIGH", "FORBIDDEN"]


# ---------------------------------------------------------------------------
# Action
# ---------------------------------------------------------------------------

class TestAction:
    def test_create_minimal(self):
        a = Action(type="read_file")
        assert a.type == "read_file"
        assert a.params == {}
        assert a.reason == ""

    def test_create_full(self):
        a = Action(type="write_file", params={"path": "a.py"}, reason="fix bug")
        assert a.type == "write_file"
        assert a.params == {"path": "a.py"}
        assert a.reason == "fix bug"

    def test_to_dict(self):
        a = Action(type="read_file", params={"path": "src/main.py"}, reason="read")
        d = a.to_dict()
        assert d == {
            "type": "read_file",
            "params": {"path": "src/main.py"},
            "reason": "read",
        }

    def test_to_dict_json_serializable(self):
        a = Action(type="finish", params={}, reason="done")
        json.dumps(a.to_dict())


# ---------------------------------------------------------------------------
# ParseResult
# ---------------------------------------------------------------------------

class TestParseResult:
    def test_create_success(self):
        action = Action(type="read_file", params={"path": "x.py"})
        r = ParseResult(action=action)
        assert r.success is True
        assert r.action is action
        assert r.error is None

    def test_create_error(self):
        r = ParseResult(error="Invalid JSON")
        assert r.success is False
        assert r.action is None
        assert r.error == "Invalid JSON"

    def test_create_defaults(self):
        r = ParseResult()
        assert r.success is False
        assert r.action is None
        assert r.error is None

    def test_to_dict_success(self):
        action = Action(type="read_file", params={"path": "x.py"})
        r = ParseResult(action=action)
        d = r.to_dict()
        assert d["action"]["type"] == "read_file"
        assert d["error"] is None

    def test_to_dict_error(self):
        r = ParseResult(error="Invalid JSON")
        d = r.to_dict()
        assert d["action"] is None
        assert d["error"] == "Invalid JSON"

    def test_to_dict_json_serializable(self):
        r = ParseResult(error="bad json")
        json.dumps(r.to_dict())


# ---------------------------------------------------------------------------
# ValidationResult
# ---------------------------------------------------------------------------

class TestValidationResult:
    def test_create_valid(self):
        r = ValidationResult(valid=True, sanitized_params={"path": "src/main.py"})
        assert r.valid is True
        assert r.reason == ""
        assert r.sanitized_params == {"path": "src/main.py"}

    def test_create_invalid(self):
        r = ValidationResult(valid=False, reason="Path blocked")
        assert r.valid is False
        assert r.reason == "Path blocked"
        assert r.sanitized_params == {}

    def test_defaults(self):
        r = ValidationResult(valid=True)
        assert r.reason == ""
        assert r.sanitized_params == {}

    def test_to_dict(self):
        r = ValidationResult(valid=False, reason="Path blocked")
        d = r.to_dict()
        assert d == {"valid": False, "reason": "Path blocked", "sanitized_params": {}}

    def test_to_dict_json_serializable(self):
        r = ValidationResult(valid=True, sanitized_params={"path": "ok.py"})
        json.dumps(r.to_dict())


# ---------------------------------------------------------------------------
# RiskDecision
# ---------------------------------------------------------------------------

class TestRiskDecision:
    def test_create_low(self):
        d = RiskDecision(level=RiskLevel.LOW, rule="Read-only operation")
        assert d.level == RiskLevel.LOW
        assert d.rule == "Read-only operation"
        assert d.needs_approval is False
        assert d.is_forbidden is False

    def test_create_high(self):
        d = RiskDecision(
            level=RiskLevel.HIGH, rule="Large file write", needs_approval=True
        )
        assert d.level == RiskLevel.HIGH
        assert d.needs_approval is True
        assert d.is_forbidden is False

    def test_create_forbidden(self):
        d = RiskDecision(
            level=RiskLevel.FORBIDDEN,
            rule="Path traversal detected",
            is_forbidden=True,
        )
        assert d.level == RiskLevel.FORBIDDEN
        assert d.needs_approval is False
        assert d.is_forbidden is True

    def test_to_dict(self):
        d = RiskDecision(level=RiskLevel.MEDIUM, rule="Write operation")
        result = d.to_dict()
        assert result == {
            "level": "MEDIUM",
            "rule": "Write operation",
            "needs_approval": False,
            "is_forbidden": False,
        }

    def test_to_dict_json_serializable(self):
        d = RiskDecision(level=RiskLevel.HIGH, rule="test", needs_approval=True)
        json.dumps(d.to_dict())


# ---------------------------------------------------------------------------
# ApprovalResult
# ---------------------------------------------------------------------------

class TestApprovalResult:
    def test_create_approved(self):
        ts = datetime(2025, 6, 15, 10, 30, 0)
        r = ApprovalResult(approved=True, user="admin", timestamp=ts, reason="looks ok")
        assert r.approved is True
        assert r.user == "admin"
        assert r.timestamp == ts
        assert r.reason == "looks ok"

    def test_create_rejected(self):
        r = ApprovalResult(approved=False, reason="too risky")
        assert r.approved is False
        assert r.user == "user"
        assert r.reason == "too risky"

    def test_default_timestamp(self):
        r = ApprovalResult(approved=True)
        assert isinstance(r.timestamp, datetime)

    def test_to_dict(self):
        ts = datetime(2025, 6, 15, 10, 30, 0)
        r = ApprovalResult(approved=True, user="admin", timestamp=ts, reason="ok")
        d = r.to_dict()
        assert d["approved"] is True
        assert d["user"] == "admin"
        assert d["timestamp"] == "2025-06-15T10:30:00"
        assert d["reason"] == "ok"

    def test_to_dict_json_serializable(self):
        r = ApprovalResult(approved=False, reason="timeout")
        json.dumps(r.to_dict())


# ---------------------------------------------------------------------------
# ToolResult
# ---------------------------------------------------------------------------

class TestToolResult:
    def test_create_success(self):
        r = ToolResult(
            success=True,
            data="file content",
            meta={"exit_code": 0, "stdout": "1 passed"},
        )
        assert r.success is True
        assert r.data == "file content"
        assert r.error is None
        assert r.meta == {"exit_code": 0, "stdout": "1 passed"}

    def test_create_failure(self):
        r = ToolResult(success=False, error="File not found")
        assert r.success is False
        assert r.data is None
        assert r.error == "File not found"
        assert r.meta == {}

    def test_defaults(self):
        r = ToolResult(success=True)
        assert r.data is None
        assert r.error is None
        assert r.meta == {}

    def test_to_dict_success(self):
        r = ToolResult(
            success=True,
            data="hello",
            meta={"exit_code": 0, "stdout": "ok"},
        )
        d = r.to_dict()
        assert d["success"] is True
        assert d["data"] == "hello"
        assert d["error"] is None
        assert d["meta"]["exit_code"] == 0

    def test_to_dict_failure(self):
        r = ToolResult(success=False, error="blocked", meta={"blocked": True})
        d = r.to_dict()
        assert d["success"] is False
        assert d["error"] == "blocked"
        assert d["meta"]["blocked"] is True

    def test_to_dict_json_serializable(self):
        r = ToolResult(success=True, data="ok", meta={"finished": True})
        json.dumps(r.to_dict())


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------

class TestMemory:
    def test_create_minimal(self):
        m = Memory(task="fix add function")
        assert m.task == "fix add function"
        assert m.history == []
        assert m.last_test_result is None
        assert m.approvals == []
        assert m.step_count == 0

    def test_create_with_history(self):
        actions = [Action(type="read_file"), Action(type="write_file")]
        m = Memory(task="test", history=actions, step_count=2)
        assert len(m.history) == 2
        assert m.step_count == 2

    def test_to_dict(self):
        m = Memory(task="fix add", step_count=1)
        d = m.to_dict()
        assert d["task"] == "fix add"
        assert d["history"] == []
        assert d["last_test_result"] is None
        assert d["approvals"] == []
        assert d["step_count"] == 1

    def test_to_dict_with_nested(self):
        action = Action(type="read_file", params={"path": "x.py"})
        tr = ToolResult(success=True, data="content")
        m = Memory(
            task="test",
            history=[action],
            last_test_result=tr,
            step_count=1,
        )
        d = m.to_dict()
        assert len(d["history"]) == 1
        assert d["history"][0]["type"] == "read_file"
        assert d["last_test_result"]["success"] is True

    def test_to_dict_json_serializable(self):
        m = Memory(task="test", step_count=0)
        json.dumps(m.to_dict())


# ---------------------------------------------------------------------------
# AuditLog
# ---------------------------------------------------------------------------

class TestAuditLog:
    def test_create_full(self):
        ts = datetime(2025, 6, 15, 12, 0, 0)
        action = Action(type="write_file", params={"path": "a.py"})
        approval = ApprovalResult(approved=True, user="admin", timestamp=ts)
        tr = ToolResult(success=True, data="ok")
        log = AuditLog(
            step=1,
            timestamp=ts,
            action=action,
            risk_level="MEDIUM",
            approval=approval,
            tool_result=tr,
            final_decision="EXECUTED",
        )
        assert log.step == 1
        assert log.timestamp == ts
        assert log.action.type == "write_file"
        assert log.risk_level == "MEDIUM"
        assert log.approval.approved is True
        assert log.tool_result.success is True
        assert log.final_decision == "EXECUTED"

    def test_create_blocked(self):
        action = Action(type="run_command", params={"command": "rm -rf /"})
        tr = ToolResult(success=False, error="FORBIDDEN", meta={"blocked": True})
        log = AuditLog(
            step=3,
            timestamp=datetime.now(),
            action=action,
            risk_level="FORBIDDEN",
            tool_result=tr,
            final_decision="BLOCKED",
        )
        assert log.final_decision == "BLOCKED"
        assert log.approval is None

    def test_to_dict(self):
        ts = datetime(2025, 6, 15, 12, 0, 0)
        action = Action(type="read_file", params={"path": "x.py"})
        approval = ApprovalResult(approved=True, timestamp=ts)
        tr = ToolResult(success=True, data="content")
        log = AuditLog(
            step=1,
            timestamp=ts,
            action=action,
            risk_level="LOW",
            approval=approval,
            tool_result=tr,
            final_decision="EXECUTED",
        )
        d = log.to_dict()
        assert d["step"] == 1
        assert d["timestamp"] == "2025-06-15T12:00:00"
        assert d["action"]["type"] == "read_file"
        assert d["risk_level"] == "LOW"
        assert d["approval"]["approved"] is True
        assert d["tool_result"]["success"] is True
        assert d["final_decision"] == "EXECUTED"

    def test_to_dict_json_serializable(self):
        action = Action(type="finish")
        log = AuditLog(
            step=1,
            timestamp=datetime.now(),
            action=action,
            risk_level="LOW",
            final_decision="EXECUTED",
        )
        json.dumps(log.to_dict())


# ---------------------------------------------------------------------------
# _serialize 辅助函数
# ---------------------------------------------------------------------------

class TestSerialize:
    def test_none(self):
        assert _serialize(None) is None

    def test_datetime(self):
        ts = datetime(2025, 1, 1, 0, 0, 0)
        assert _serialize(ts) == "2025-01-01T00:00:00"

    def test_enum(self):
        assert _serialize(RiskLevel.HIGH) == "HIGH"

    def test_list(self):
        data = [1, "two", None]
        assert _serialize(data) == [1, "two", None]

    def test_dict(self):
        data = {"key": "value", "num": 42}
        assert _serialize(data) == {"key": "value", "num": 42}

    def test_primitive(self):
        assert _serialize(42) == 42
        assert _serialize("hello") == "hello"
        assert _serialize(True) is True

    def test_nested_list_of_dicts(self):
        data = [{"a": 1}, {"b": datetime(2025, 1, 1, 0, 0, 0)}]
        result = _serialize(data)
        assert result[0] == {"a": 1}
        assert result[1]["b"] == "2025-01-01T00:00:00"

    def test_nested_dataclass(self):
        action = Action(type="read_file")
        result = _serialize(action)
        assert result["type"] == "read_file"
        assert result["params"] == {}
        assert result["reason"] == ""


# ---------------------------------------------------------------------------
# 跨模型集成测试
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_full_audit_roundtrip(self):
        """验证完整审计日志链路可序列化为 JSON 并通过 json.loads 还原。"""
        ts = datetime(2025, 6, 15, 14, 0, 0)
        action = Action(
            type="write_file",
            params={"path": "src/calc.py", "content": "def add(a,b): return a+b"},
            reason="fix add function",
        )
        approval = ApprovalResult(
            approved=True, user="admin", timestamp=ts, reason="approved"
        )
        tr = ToolResult(
            success=True,
            data="written",
            meta={"diff": "+def add(a,b): return a+b", "exit_code": 0},
        )
        log = AuditLog(
            step=2,
            timestamp=ts,
            action=action,
            risk_level="HIGH",
            approval=approval,
            tool_result=tr,
            final_decision="EXECUTED",
        )
        serialized = json.dumps(log.to_dict(), indent=2)
        restored = json.loads(serialized)
        assert restored["step"] == 2
        assert restored["action"]["type"] == "write_file"
        assert restored["risk_level"] == "HIGH"
        assert restored["approval"]["approved"] is True
        assert restored["tool_result"]["meta"]["diff"] == "+def add(a,b): return a+b"
        assert restored["final_decision"] == "EXECUTED"