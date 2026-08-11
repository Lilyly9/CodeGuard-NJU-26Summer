"""人工审批模块单元测试 — 返回 ApprovalResult 对象。"""

import json
from unittest.mock import patch

import pytest

from src.approval import request_approval, get_approval_log, clear_approval_log
from src.models import ApprovalResult


class TestApprovalResultType:
    def test_returns_approval_result(self):
        with patch("builtins.input", return_value="y"):
            result = request_approval(
                {"action": "write_file", "path": "x.py", "content": "x=1"},
                "/ws",
                timeout=5,
            )
        assert isinstance(result, ApprovalResult)

    def test_approved_has_user_and_reason(self):
        with patch("builtins.input", return_value="y"):
            result = request_approval(
                {"action": "write_file", "path": "x.py", "content": "x=1"},
                "/ws",
                timeout=5,
            )
        assert result.approved is True
        assert result.reason == "APPROVED"

    def test_rejected_has_reason(self):
        with patch("builtins.input", return_value="n"):
            result = request_approval(
                {"action": "write_file", "path": "x.py", "content": "x=1"},
                "/ws",
                timeout=5,
            )
        assert result.approved is False
        assert result.reason == "REJECTED"

    def test_forbidden_returns_rejected(self):
        result = request_approval(
            {"action": "run_command", "command": "rm -rf /"},
            "/ws",
            timeout=5,
        )
        assert isinstance(result, ApprovalResult)
        assert result.approved is False
        assert result.reason == "FORBIDDEN"

    def test_approval_result_has_timestamp(self):
        with patch("builtins.input", return_value="y"):
            result = request_approval(
                {"action": "write_file", "path": "x.py", "content": "x=1"},
                "/ws",
                timeout=5,
            )
        assert result.timestamp is not None


class TestApprovalLog:
    def test_logs_approval(self):
        clear_approval_log()
        with patch("builtins.input", return_value="y"):
            request_approval(
                {"action": "write_file", "path": "x.py"},
                "/ws",
                timeout=5,
            )
        log = get_approval_log()
        assert len(log) >= 1
        assert log[0]["approved"] is True

    def test_logs_rejection(self):
        clear_approval_log()
        with patch("builtins.input", return_value="n"):
            request_approval(
                {"action": "write_file", "path": "x.py"},
                "/ws",
                timeout=5,
            )
        log = get_approval_log()
        assert len(log) >= 1
        assert log[0]["approved"] is False

    def test_clear_log(self):
        clear_approval_log()
        with patch("builtins.input", return_value="y"):
            request_approval(
                {"action": "write_file", "path": "x.py"},
                "/ws",
                timeout=5,
            )
        clear_approval_log()
        assert len(get_approval_log()) == 0