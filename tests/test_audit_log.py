"""审计日志单元测试。"""

import json
import os

import pytest

from src.audit_log import log
from src.models import Action, AuditLog
from datetime import datetime


class TestAuditLog:
    def test_log_writes_entry(self, tmp_path):
        log_dir = str(tmp_path / "logs")
        action = Action(type="read_file", params={"path": "x.py"})
        entry = AuditLog(
            step=1,
            timestamp=datetime.now(),
            action=action,
            risk_level="LOW",
            final_decision="EXECUTED",
        )
        log(entry, log_dir=log_dir)

        log_file = os.path.join(log_dir, "audit.jsonl")
        assert os.path.exists(log_file)

        with open(log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["step"] == 1
        assert data["action"]["type"] == "read_file"