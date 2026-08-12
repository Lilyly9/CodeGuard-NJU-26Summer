"""人工审批模块单元测试 — 使用 RiskDecision + ApprovalResult。"""

import time
from unittest.mock import patch

import pytest

from src.approval import request_approval, get_approval_log, clear_approval_log
from src.models import ApprovalResult, RiskDecision, RiskLevel


class TestApproval:
    def test_approve_yes(self):
        decision = RiskDecision(
            level=RiskLevel.HIGH,
            rule="test approval",
            needs_approval=True,
            action={"action": "write_file", "path": "x.py"},
        )
        with patch("builtins.input", return_value="y"):
            result = request_approval(decision, timeout=5)
        assert isinstance(result, ApprovalResult)
        assert result.approved is True

    def test_reject_no(self):
        decision = RiskDecision(
            level=RiskLevel.HIGH,
            rule="test approval",
            needs_approval=True,
            action={"action": "write_file", "path": "x.py"},
        )
        with patch("builtins.input", return_value="n"):
            result = request_approval(decision, timeout=5)
        assert isinstance(result, ApprovalResult)
        assert result.approved is False

    def test_forbidden_auto_rejected(self):
        decision = RiskDecision(
            level=RiskLevel.FORBIDDEN,
            rule="forbidden",
            is_forbidden=True,
            action={"action": "run_command", "command": "rm -rf /"},
        )
        result = request_approval(decision, timeout=5)
        assert isinstance(result, ApprovalResult)
        assert result.approved is False
        assert result.reason == "FORBIDDEN"

    def test_logs_approval(self):
        clear_approval_log()
        decision = RiskDecision(
            level=RiskLevel.HIGH,
            rule="test approval",
            needs_approval=True,
            action={"action": "write_file", "path": "x.py"},
        )
        with patch("builtins.input", return_value="y"):
            request_approval(decision, timeout=5)
        log = get_approval_log()
        assert len(log) >= 1
        assert log[0]["approved"] is True

    def test_logs_rejection(self):
        clear_approval_log()
        decision = RiskDecision(
            level=RiskLevel.HIGH,
            rule="test approval",
            needs_approval=True,
            action={"action": "write_file", "path": "x.py"},
        )
        with patch("builtins.input", return_value="n"):
            request_approval(decision, timeout=5)
        log = get_approval_log()
        assert len(log) >= 1
        assert log[0]["approved"] is False

    def test_clear_log(self):
        clear_approval_log()
        decision = RiskDecision(
            level=RiskLevel.HIGH,
            rule="test approval",
            needs_approval=True,
            action={"action": "write_file", "path": "x.py"},
        )
        with patch("builtins.input", return_value="y"):
            request_approval(decision, timeout=5)
        clear_approval_log()
        assert len(get_approval_log()) == 0


class TestBoundaryExploits:
    def test_timeout_auto_rejects(self):
        decision = RiskDecision(
            level=RiskLevel.HIGH,
            rule="test approval",
            needs_approval=True,
            action={"action": "write_file", "path": "x.py"},
        )
        result = request_approval(decision, get_input=lambda _: time.sleep(999), timeout=1)
        assert isinstance(result, ApprovalResult)
        assert result.approved is False

    def test_forbidden_cannot_be_overridden(self):
        decision = RiskDecision(
            level=RiskLevel.FORBIDDEN,
            rule="forbidden",
            is_forbidden=True,
            action={"action": "run_command", "command": "rm -rf /"},
        )
        with patch("builtins.input", return_value="y"):
            result = request_approval(decision, timeout=5)
        assert result.approved is False
        assert result.reason == "FORBIDDEN"

    def test_consecutive_rejections(self):
        clear_approval_log()
        decision = RiskDecision(
            level=RiskLevel.HIGH,
            rule="test approval",
            needs_approval=True,
            action={"action": "write_file", "path": "x.py"},
        )
        with patch("builtins.input", return_value="n"):
            r1 = request_approval(decision, timeout=5)
            r2 = request_approval(decision, timeout=5)
        assert r1.approved is False
        assert r2.approved is False
        assert len(get_approval_log()) == 2