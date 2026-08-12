"""边界与极端情况专项测试 — 所有模块的恶意/畸形/边界输入，纯本地 Mock，不联网。"""

import json
import time
from unittest import mock

import pytest

from src.agent import Agent
from src.approval import request_approval, clear_approval_log
from src.guardrail import evaluate
from src.models import ApprovalResult, RiskDecision, RiskLevel
from src.parser import parse_llm_output
from src.tools import run_command


# =============================================================================
# guardrail.py —— 风险分级护栏
# =============================================================================

class TestGuardrailBoundary:
    """大小写、路径穿越、Shell 注入、敏感文件、白名单命令的边界测试。"""

    @pytest.mark.parametrize("cmd", [
        "Rm -Rf /",
        "rm -RF /",
        "RM -rf /",
        "RM -RF /",
    ])
    def test_case_insensitive_rm_rf(self, cmd):
        result = evaluate({"action": "run_command", "command": cmd}, "/ws")
        assert result.level == RiskLevel.FORBIDDEN, f"'{cmd}' should be FORBIDDEN"
        assert result.is_forbidden is True

    @pytest.mark.parametrize("path", [
        "../etc/passwd",
        "....//....//config",
        "../../../windows/win.ini",
        "a/../../b/../c/../../etc/shadow",
    ])
    def test_path_traversal_variants(self, path):
        result = evaluate({"action": "read_file", "path": path}, "/ws")
        assert result.level == RiskLevel.FORBIDDEN, f"path '{path}' should be FORBIDDEN"

    @pytest.mark.parametrize("cmd", [
        "pytest; rm -rf /",
        "pytest && ls",
        "pytest | cat",
        "pytest $(whoami)",
        "echo `id`",
        "ls || echo hacked",
    ])
    def test_shell_injection_symbols(self, cmd):
        result = evaluate({"action": "run_command", "command": cmd}, "/ws")
        assert result.level == RiskLevel.FORBIDDEN, f"'{cmd}' should be FORBIDDEN"

    @pytest.mark.parametrize("path", [
        ".env",
        "key.pem",
        "secret.key",
        ".git/config",
        ".git/hooks/pre-commit",
    ])
    def test_sensitive_file_extensions(self, path):
        result = evaluate({"action": "read_file", "path": path}, "/ws")
        assert result.level == RiskLevel.FORBIDDEN, f"path '{path}' should be FORBIDDEN"

    @pytest.mark.parametrize("cmd", [
        "git diff --cached",
        "git status --porcelain",
    ])
    def test_allowed_git_variants(self, cmd):
        result = evaluate({"action": "run_command", "command": cmd}, "/ws")
        assert result.level != RiskLevel.FORBIDDEN, f"'{cmd}' should be allowed by guardrail"

    def test_git_push_rejected_by_tools(self, tmp_path):
        result = run_command("git push", str(tmp_path))
        assert result["success"] is False
        assert "not allowed" in result["error"].lower()

    def test_large_file_write_high_risk(self, tmp_path):
        result = evaluate({"action": "write_file", "path": "big.txt", "content": "x" * 20000}, "/ws")
        assert result.level == RiskLevel.HIGH
        assert result.needs_approval is True


# =============================================================================
# parser.py —— LLM 输出解析器
# =============================================================================

class TestParserBoundary:
    """非法 JSON、缺失字段、未知 action、类型错误、超大内容的边界测试。"""

    @pytest.mark.parametrize("raw", [
        "{action: read_file}",
        "{'action':'read'}",
        "action read_file",
        "null",
        "undefined",
        "",
    ])
    def test_invalid_json_strings(self, raw):
        result = parse_llm_output(raw)
        assert result.error is not None, f"'{raw}' should produce error"

    @pytest.mark.parametrize("data", [
        {"action": "read_file"},
        {"action": "write_file"},
        {"action": "write_file", "path": "x.py"},
        {"action": "run_command"},
    ])
    def test_missing_required_params(self, data):
        raw = json.dumps(data)
        result = parse_llm_output(raw)
        assert result.error is not None, f"{data} should produce error"
        assert "Missing required param" in result.error

    def test_unknown_action(self):
        raw = json.dumps({"action": "delete_everything"})
        result = parse_llm_output(raw)
        assert result.error is not None
        assert "Unknown action" in result.error

    def test_path_param_type_error(self):
        raw = json.dumps({"action": "read_file", "path": 123})
        result = parse_llm_output(raw)
        assert result.error is None

    def test_large_content_not_crash(self):
        raw = json.dumps({"action": "write_file", "path": "a.txt", "content": "x" * 100000})
        result = parse_llm_output(raw)
        assert result.error is None
        assert result.action.type == "write_file"
        assert len(result.action.params["content"]) == 100000


# =============================================================================
# approval.py —— 审批管理器
# =============================================================================

class TestApprovalBoundary:
    """超时、forbidden 覆盖、拒绝状态的边界测试。"""

    def test_timeout_auto_rejects(self):
        clear_approval_log()
        decision = RiskDecision(
            level=RiskLevel.HIGH,
            rule="test timeout",
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
        with mock.patch("builtins.input", return_value="y"):
            result = request_approval(decision, timeout=5)
        assert result.approved is False
        assert result.reason == "FORBIDDEN"

    def test_reject_returns_false(self):
        clear_approval_log()
        decision = RiskDecision(
            level=RiskLevel.HIGH,
            rule="test reject",
            needs_approval=True,
            action={"action": "write_file", "path": "x.py"},
        )
        result = request_approval(decision, get_input=lambda _: "n", timeout=5)
        assert result.approved is False
        assert result.reason == "REJECTED"


# =============================================================================
# agent.py —— 主循环
# =============================================================================

class TestAgentBoundary:
    """最大步数、连续无效动作、空任务、空工作目录的边界测试。"""

    def test_max_steps_limit(self, tmp_path):
        mock_llm = mock.Mock()
        mock_llm.get_response.side_effect = [
            json.dumps({"action": "run_command", "command": "pytest"})
            for _ in range(10)
        ]
        agent = Agent(llm_client=mock_llm)
        result = agent.run(task="keep running", workspace=str(tmp_path), max_steps=3)
        assert result["finish_reason"] == "max_steps"
        assert result["steps"] == 3

    def test_consecutive_invalid_json(self, tmp_path):
        mock_llm = mock.Mock()
        mock_llm.get_response.side_effect = [
            "not json",
            "also not json",
            "still not json",
            json.dumps({"action": "finish"}),
        ]
        agent = Agent(llm_client=mock_llm)
        result = agent.run(task="bad input", workspace=str(tmp_path), max_steps=10)
        assert result["finish_reason"] == "parse_failure"
        assert "解析失败" in result.get("stop_reason", "")

    def test_empty_task(self, tmp_path):
        mock_llm = mock.Mock()
        mock_llm.get_response.return_value = json.dumps({"action": "finish"})
        agent = Agent(llm_client=mock_llm)
        result = agent.run(task="", workspace=str(tmp_path))
        assert result["success"] is True
        assert result["finish_reason"] == "finish_action"

    def test_empty_workspace_list_files(self, tmp_path):
        from src.tools import list_files
        result = list_files(str(tmp_path), str(tmp_path))
        assert result["success"] is True
        assert result["data"] == []