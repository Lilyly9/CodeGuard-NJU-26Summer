"""加固回归测试 — 针对代码审查中发现的具体缺陷。

每个测试先锁定"当前错误行为"（红），修复实现后应转为通过（绿）。
覆盖：风险分级 / 命令白名单 / 停机原因映射 / 配置接线。
"""

import json
from unittest import mock

import pytest

from src.agent import Agent
from src.config import Config
from src.executor import execute_tool
from src.guardrail import assess_risk
from src.models import RiskLevel, ValidationResult
from src.tools import run_command


def _valid(action: dict) -> ValidationResult:
    return ValidationResult(valid=True, sanitized_params=action)


class TestRunPytestRiskLevel:
    """SPEC §4.3 / README 分级表：run_pytest 应为 MEDIUM，而非 LOW。"""

    def test_run_pytest_action_is_medium(self):
        decision = assess_risk(_valid({"action": "run_pytest"}), Config())
        assert decision.level == RiskLevel.MEDIUM
        assert decision.needs_approval is False


class TestRmRfGlobForbidden:
    """rm -rf /* 与 rm -rf /. 等价于删除根目录，应 FORBIDDEN，而非仅 HIGH。"""

    @pytest.mark.parametrize("cmd", ["rm -rf /*", "rm -rf /.", "rm -rf /"])
    def test_rm_rf_root_variants_forbidden(self, cmd):
        decision = assess_risk(_valid({"action": "run_command", "command": cmd}), Config())
        assert decision.level == RiskLevel.FORBIDDEN, f"'{cmd}' should be FORBIDDEN"

    def test_rm_rf_specific_dir_is_high(self):
        decision = assess_risk(_valid({"action": "run_command", "command": "rm -rf /tmp"}), Config())
        assert decision.level == RiskLevel.HIGH


class TestRunCommandWhitelist:
    """命令白名单必须整词匹配，前缀绕过（pytestx 等）应被明确拒绝。"""

    @pytest.mark.parametrize("cmd", ["pytestx", "python3script", "git diffx", "ruffle"])
    def test_prefix_bypass_rejected(self, tmp_path, cmd):
        result = run_command(cmd, str(tmp_path))
        assert result["success"] is False
        assert "not allowed" in result["error"].lower()

    def test_legit_command_still_allowed(self, tmp_path):
        result = run_command("python --version", str(tmp_path))
        assert result["success"] is True


class TestValidationFailureFinishReason:
    """连续 3 次验证失败应映射为 validation_failure，而非笼统的 error。"""

    def test_validation_failure_finish_reason(self, tmp_path):
        responses = [
            json.dumps({"action": "read_file", "path": f"x{i}.py"}) for i in range(5)
        ]
        mock_llm = mock.Mock()
        mock_llm.get_response.side_effect = responses

        agent = Agent(
            llm_client=mock_llm,
            validate_fn=lambda a, ws, cfg: ValidationResult(
                valid=False, reason="bad", errors=["bad"]
            ),
        )
        result = agent.run(task="fix", workspace=str(tmp_path))

        assert result["finish_reason"] == "validation_failure"
        assert "验证失败" in result.get("stop_reason", "")


class TestExecutorWiresConfigToWriteFile:
    """execute_tool 应将 config 传给 write_file，使 config.max_file_size 生效。"""

    def test_write_file_respects_config_max_size(self, tmp_path):
        cfg = Config()
        cfg.max_file_size = 10
        result = execute_tool(
            "write_file",
            {"path": "big.txt", "content": "x" * 20},
            str(tmp_path),
            cfg,
        )
        assert result["success"] is False
        assert "too large" in result["error"].lower()
