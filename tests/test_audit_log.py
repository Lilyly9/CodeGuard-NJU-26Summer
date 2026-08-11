"""audit_log 模块单元测试 — 覆盖日志写入、JSONL 格式、敏感信息过滤、序列化。"""

import json
from datetime import datetime

import pytest

from src.audit_log import AuditLogger


class TestAuditLogger:
    def test_log_writes_jsonl(self, tmp_path):
        log_path = tmp_path / "audit.jsonl"
        logger = AuditLogger(log_path)

        logger.log({
            "step": 1,
            "timestamp": datetime(2025, 1, 1, 12, 0, 0),
            "action": {"action": "read_file", "path": "x.py"},
            "risk_level": "LOW",
            "final_decision": "EXECUTED",
        })

        assert log_path.exists()
        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["step"] == 1
        assert entry["timestamp"] == "2025-01-01T12:00:00"
        assert entry["final_decision"] == "EXECUTED"

    def test_log_appends_multiple_entries(self, tmp_path):
        log_path = tmp_path / "audit.jsonl"
        logger = AuditLogger(log_path)

        logger.log({"step": 1, "final_decision": "EXECUTED"})
        logger.log({"step": 2, "final_decision": "FINISHED"})

        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2

    def test_get_entries_returns_logged(self, tmp_path):
        log_path = tmp_path / "audit.jsonl"
        logger = AuditLogger(log_path)

        logger.log({"step": 1, "final_decision": "EXECUTED"})
        logger.log({"step": 2, "final_decision": "BLOCKED"})

        entries = logger.get_entries()
        assert len(entries) == 2
        assert entries[0]["step"] == 1
        assert entries[1]["step"] == 2

    def test_serializes_timestamp(self, tmp_path):
        log_path = tmp_path / "audit.jsonl"
        logger = AuditLogger(log_path)

        logger.log({
            "step": 1,
            "timestamp": datetime(2025, 6, 15, 8, 30, 0),
            "final_decision": "EXECUTED",
        })

        entries = logger.get_entries()
        assert entries[0]["timestamp"] == "2025-06-15T08:30:00"

    def test_serializes_tool_result(self, tmp_path):
        log_path = tmp_path / "audit.jsonl"
        logger = AuditLogger(log_path)

        logger.log({
            "step": 1,
            "final_decision": "EXECUTED",
            "tool_result": {
                "success": True,
                "data": "output",
                "error": None,
                "meta": {"exit_code": 0, "diff": "+x"},
            },
        })

        entries = logger.get_entries()
        tr = entries[0]["tool_result"]
        assert tr["success"] is True
        assert tr["data"] == "output"
        assert tr["error"] is None
        assert tr["meta"]["exit_code"] == "0"
        assert tr["meta"]["diff"] == "+x"

    def test_filters_api_key(self, tmp_path):
        log_path = tmp_path / "audit.jsonl"
        logger = AuditLogger(log_path)

        logger.log({
            "step": 1,
            "api_key": "sk-secret-123",
            "final_decision": "EXECUTED",
        })

        entries = logger.get_entries()
        assert entries[0]["api_key"] == "***REDACTED***"

    def test_filters_openai_api_key(self, tmp_path):
        log_path = tmp_path / "audit.jsonl"
        logger = AuditLogger(log_path)

        logger.log({
            "step": 1,
            "OPENAI_API_KEY": "sk-abc123",
            "final_decision": "EXECUTED",
        })

        entries = logger.get_entries()
        assert entries[0]["OPENAI_API_KEY"] == "***REDACTED***"

    def test_filters_token_and_secret(self, tmp_path):
        log_path = tmp_path / "audit.jsonl"
        logger = AuditLogger(log_path)

        logger.log({
            "step": 1,
            "token": "ghp_xxx",
            "secret": "mysecret",
            "password": "pass123",
            "final_decision": "EXECUTED",
        })

        entries = logger.get_entries()
        assert entries[0]["token"] == "***REDACTED***"
        assert entries[0]["secret"] == "***REDACTED***"
        assert entries[0]["password"] == "***REDACTED***"

    def test_does_not_filter_normal_fields(self, tmp_path):
        log_path = tmp_path / "audit.jsonl"
        logger = AuditLogger(log_path)

        logger.log({
            "step": 1,
            "action": "read_file",
            "path": "src/main.py",
            "final_decision": "EXECUTED",
        })

        entries = logger.get_entries()
        assert entries[0]["action"] == "read_file"
        assert entries[0]["path"] == "src/main.py"

    def test_creates_parent_directories(self, tmp_path):
        log_path = tmp_path / "deep" / "nested" / "audit.jsonl"
        logger = AuditLogger(log_path)

        logger.log({"step": 1, "final_decision": "EXECUTED"})

        assert log_path.exists()

    def test_entries_independent_of_file(self, tmp_path):
        log_path = tmp_path / "audit.jsonl"
        logger = AuditLogger(log_path)

        logger.log({"step": 1, "final_decision": "EXECUTED"})
        entries = logger.get_entries()
        entries[0]["step"] = 999

        assert logger.get_entries()[0]["step"] == 1