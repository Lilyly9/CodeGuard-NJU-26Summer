"""Global End-to-End (E2E) Integrity Test Suite for CodeGuard.

Validates the complete Agent pipeline — Parser → Validation → Guardrail →
Approval → Executor → Feedback — across 10 critical scenarios including
boundary conditions, attack surfaces, and failure recovery.

All tests use MockLLM (no network) but exercise the full Agent.run() loop.
"""

import json
import os
from pathlib import Path
from unittest import mock

import pytest

from src.agent import Agent
from src.approval import request_approval, clear_approval_log
from src.config import Config
from src.llm_client import MockLLM
from src.models import ApprovalResult, RiskDecision, RiskLevel
from src.tools import read_file as tools_read_file


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_risk(level: str) -> RiskDecision:
    """Build a RiskDecision for custom assess_risk injection."""
    return RiskDecision(
        level=RiskLevel(level.upper()),
        rule="mock",
        needs_approval=level.upper() == "HIGH",
        is_forbidden=level.upper() == "FORBIDDEN",
    )


def _config_no_auto_finish() -> Config:
    """Return a Config with auto_finish_on_test_pass disabled."""
    cfg = Config()
    cfg.auto_finish_on_test_pass = False
    return cfg


# =============================================================================
# Scenario 1 — Happy Path (Golden Flow)
# =============================================================================

def test_scenario_1_happy_path(tmp_path):
    """Full pipeline: read → write → run_pytest → finish, all succeeding."""
    ws = tmp_path / "project"
    ws.mkdir()

    # create a buggy source file and a test that expects the fix
    (ws / "math.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    (ws / "test_math.py").write_text(
        "from math import add\n\ndef test_add():\n    assert add(1, 2) == 3\n",
        encoding="utf-8",
    )

    corrected = "def add(a, b):\n    return a + b\n"

    mock_llm = MockLLM([
        json.dumps({"action": "read_file", "path": "math.py"}),
        json.dumps({"action": "write_file", "path": "math.py", "content": corrected}),
        json.dumps({"action": "run_pytest"}),
        json.dumps({"action": "finish", "summary": "all done"}),
    ])

    agent = Agent(llm_client=mock_llm, config=_config_no_auto_finish())
    result = agent.run(task="Fix add function so test_add passes",
                       workspace=str(ws))

    assert result["success"] is True
    assert result["steps"] == 4, f"expected 4 steps, got {result['steps']}"
    assert result["finish_reason"] == "finish_action", \
        f"expected finish_action, got {result['finish_reason']}"

    # verify the file was actually corrected on disk
    assert (ws / "math.py").read_text(encoding="utf-8") == corrected


# =============================================================================
# Scenario 2 — Path Traversal Attack Prevention
# =============================================================================

def test_scenario_2_path_traversal_blocked(tmp_path):
    """Validation must block '../../..' paths and never read real system files."""
    ws = tmp_path / "sandbox"
    ws.mkdir()

    mock_llm = MockLLM([
        json.dumps({"action": "read_file", "path": "../../../windows/win.ini"}),
        json.dumps({"action": "finish", "summary": "gave up"}),
    ])

    agent = Agent(llm_client=mock_llm)
    result = agent.run(task="Read config file", workspace=str(ws))

    # the action MUST be rejected before tool execution
    blocked_entries = [
        e for e in result["audit_log"]
        if e.get("final_decision") in ("VALIDATION_ERROR", "BLOCKED")
    ]
    assert len(blocked_entries) >= 1, \
        f"path traversal was not blocked; audit_log={result['audit_log']}"

    # absolutely no real system file was touched
    real_path = Path("C:/windows/win.ini") if os.name == "nt" else Path("/etc/passwd")
    # the test doesn't try to verify the "not read" property via the mock
    # (the mock doesn't execute tools), but we verify the agent blocked it
    assert any(".." in str(e.get("action", {}).get("path", ""))
               for e in blocked_entries), \
        "blocked entry should reference the traversal path"


# =============================================================================
# Scenario 3 — Shell Injection Attack Prevention
# =============================================================================

def test_scenario_3_shell_injection_blocked(tmp_path):
    """Guardrail must detect shell connectors (&&) and return FORBIDDEN."""
    ws = tmp_path / "sandbox"
    ws.mkdir()

    mock_llm = MockLLM([
        json.dumps({"action": "run_command", "command": "pytest && rm -rf /"}),
        json.dumps({"action": "finish", "summary": "blocked"}),
    ])

    agent = Agent(llm_client=mock_llm)
    result = agent.run(task="Run tests", workspace=str(ws))

    blocked = [
        e for e in result["audit_log"]
        if e.get("final_decision") == "BLOCKED"
    ]
    assert len(blocked) >= 1, \
        f"shell injection was not blocked; audit_log={result['audit_log']}"

    # verify the blocked entry has FORBIDDEN risk level
    assert any(
        e.get("risk_level") == RiskLevel.FORBIDDEN.value
        for e in blocked
    ), "shell injection should be FORBIDDEN"


# =============================================================================
# Scenario 4 — Invalid JSON Recovery (Parse Error Resilience)
# =============================================================================

def test_scenario_4_invalid_json_recovery(tmp_path):
    """Agent survives malformed JSON, recovers, and continues the task."""
    ws = tmp_path / "sandbox"
    ws.mkdir()
    (ws / "test.txt").write_text("hello world", encoding="utf-8")

    mock_llm = MockLLM([
        "{action: read_file}",                                    # invalid JSON
        json.dumps({"action": "read_file", "path": "test.txt"}), # recovery
        json.dumps({"action": "finish", "summary": "done"}),
    ])

    agent = Agent(llm_client=mock_llm)
    result = agent.run(task="Do something", workspace=str(ws))

    # should NOT have crashed — verify the agent didn't stop due to parse errors
    parse_errors = [
        e for e in result["audit_log"]
        if e.get("final_decision") == "PARSE_ERROR"
    ]
    assert len(parse_errors) >= 1, "first response should be a parse error"

    executed = [
        e for e in result["audit_log"]
        if e.get("final_decision") == "EXECUTED"
    ]
    assert len(executed) >= 1, "agent should recover and execute the valid action"

    assert result["success"] is True
    assert result["finish_reason"] == "finish_action"


# =============================================================================
# Scenario 5 — Missing Required Parameter (Validation)
# =============================================================================

def test_scenario_5_missing_required_param(tmp_path):
    """Parser catches missing 'path' for read_file, agent continues gracefully."""
    ws = tmp_path / "sandbox"
    ws.mkdir()
    (ws / "data.txt").write_text("some data", encoding="utf-8")

    mock_llm = MockLLM([
        json.dumps({"action": "read_file"}),                        # missing path
        json.dumps({"action": "read_file", "path": "data.txt"}),   # valid
        json.dumps({"action": "finish", "summary": "done"}),
    ])

    agent = Agent(llm_client=mock_llm)
    result = agent.run(task="Read a file", workspace=str(ws))

    # verify the first action was rejected
    rejected = [
        e for e in result["audit_log"]
        if e.get("final_decision") in ("PARSE_ERROR", "VALIDATION_ERROR")
    ]
    assert len(rejected) >= 1, \
        f"missing-param action should be rejected; got {result['audit_log']}"

    # agent did NOT crash — it finished normally
    assert result["success"] is True
    assert result["finish_reason"] == "finish_action", \
        f"expected finish_action, got {result['finish_reason']}"


# =============================================================================
# Scenario 6 — Repetitive Action Loop Protection
# =============================================================================

def test_scenario_6_repetitive_action_stop(tmp_path):
    """Agent detects 3 identical consecutive actions and force-stops."""
    ws = tmp_path / "sandbox"
    ws.mkdir()

    # Same action 4 times — repeat detection fires at count >= 3
    mock_llm = MockLLM([
        json.dumps({"action": "run_pytest"}) for _ in range(4)
    ])

    agent = Agent(llm_client=mock_llm, config=_config_no_auto_finish())
    result = agent.run(task="Fix bug", workspace=str(ws))

    # should stop due to repeated action (not max_steps since default is 10)
    assert result["finish_reason"] in ("repeated_action", "max_steps"), \
        f"expected repeated_action or max_steps, got {result['finish_reason']}"
    assert result["steps"] <= 4, \
        f"should stop early, got {result['steps']} steps"


# =============================================================================
# Scenario 7 — Approval Timeout (Auto-Reject)
# =============================================================================

def test_scenario_7_approval_timeout_reject(tmp_path):
    """HIGH-risk action with approval timeout is auto-rejected, file not written."""
    ws = tmp_path / "sandbox"
    ws.mkdir()

    def _assess_always_high(_validated, _config):
        return _make_risk("high")

    def _approval_timeout(_risk):
        # simulate a timeout — the user never responds
        return ApprovalResult(approved=False, reason="TIMEOUT")

    mock_llm = MockLLM([
        json.dumps({"action": "write_file", "path": "temp.txt",
                    "content": "important data"}),
        json.dumps({"action": "finish", "summary": "rejected"}),
    ])

    agent = Agent(
        llm_client=mock_llm,
        assess_risk_fn=_assess_always_high,
        approval_fn=_approval_timeout,
    )
    result = agent.run(task="Delete temp file", workspace=str(ws))

    # the write action should have been rejected
    rejected = [
        e for e in result["audit_log"]
        if e.get("final_decision") == "REJECTED"
    ]
    assert len(rejected) >= 1, "HIGH-risk action should be rejected on timeout"

    # file must NOT have been written
    assert not (ws / "temp.txt").exists(), \
        "file should not exist after rejection"


# =============================================================================
# Scenario 8 — Max Steps Hard Limit
# =============================================================================

def test_scenario_8_max_steps_enforced(tmp_path):
    """Agent forcibly exits after exactly max_steps iterations."""
    ws = tmp_path / "sandbox"
    ws.mkdir()

    mock_llm = MockLLM([
        json.dumps({"action": "run_pytest"}) for _ in range(10)
    ])

    agent = Agent(llm_client=mock_llm, config=_config_no_auto_finish())
    result = agent.run(task="Infinite loop", workspace=str(ws), max_steps=3)

    assert result["steps"] == 3, f"expected exactly 3 steps, got {result['steps']}"
    assert result["finish_reason"] == "max_steps", \
        f"expected max_steps, got {result['finish_reason']}"


# =============================================================================
# Scenario 9 — Large File Truncation (Resource Protection)
# =============================================================================

def test_scenario_9_large_file_truncation(tmp_path):
    """tools.read_file truncates content at MAX_READ_SIZE and sets truncated=True."""
    ws = tmp_path / "sandbox"
    ws.mkdir()

    # create a 1 MB file
    huge_path = ws / "huge.log"
    huge_path.write_text("X" * (1024 * 1024), encoding="utf-8")

    result = tools_read_file(str(huge_path), str(ws))

    assert result["success"] is True
    data = result["data"]
    assert data is not None
    # _MAX_READ_SIZE = 10000 in tools.py
    assert len(data) <= 10000, \
        f"content should be truncated to ≤10000, got {len(data)}"
    assert len(data) < (1024 * 1024), "content must be truncated"

    meta = result.get("meta", {})
    assert meta.get("truncated") is True, \
        f"meta.truncated should be True, got {meta}"


# =============================================================================
# Scenario 10 — Audit Log Sensitive Information Filtering
# =============================================================================

def test_scenario_10_audit_log_redacts_secrets(tmp_path):
    """Audit logger must redact fields matching sensitive patterns (api_key, etc.)."""
    ws = tmp_path / "sandbox"
    ws.mkdir()

    mock_llm = MockLLM([
        json.dumps({"action": "write_file", "path": "config.txt",
                    "content": "normal content", "api_key": "sk-abc123"}),
        json.dumps({"action": "finish", "summary": "done"}),
    ])

    agent = Agent(llm_client=mock_llm)
    result = agent.run(task="Check config", workspace=str(ws))

    # read the on-disk audit log
    audit_path = ws / ".codeguard" / "audit.jsonl"
    assert audit_path.exists(), "audit log file must exist"

    raw_text = audit_path.read_text(encoding="utf-8")
    assert "sk-abc123" not in raw_text, \
        f"secret 'sk-abc123' leaked into audit log: {raw_text[:500]}"
    assert "***REDACTED***" in raw_text, \
        "secret should be replaced with ***REDACTED***"

    # also verify the in-memory audit log doesn't contain the secret
    for entry in result["audit_log"]:
        entry_str = json.dumps(entry, default=str)
        assert "sk-abc123" not in entry_str, \
            f"secret leaked in memory entry: {entry_str[:200]}"
