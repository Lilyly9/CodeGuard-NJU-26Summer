"""CodeGuard 三机制自动演示 — 无人值守，不联网，不等待键盘输入。

运行方式：python demo.py
"""

import json
import tempfile
from pathlib import Path
from unittest import mock

from src.agent import Agent
from src.models import ApprovalResult, RiskDecision, RiskLevel


def _make_risk(level):
    return RiskDecision(
        level=RiskLevel(level.upper()),
        rule="mock",
        needs_approval=level.upper() == "HIGH",
        is_forbidden=level.upper() == "FORBIDDEN",
    )


def demo_1_block():
    """演示 1：拦截危险命令 rm -rf /"""
    print("=" * 60)
    print("演示 1：拦截「自杀」命令")

    mock_llm = mock.Mock()
    mock_llm.get_response.side_effect = [
        json.dumps({"action": "run_command", "command": "rm -rf /"}),
        json.dumps({"action": "finish", "summary": "blocked"}),
    ]

    with tempfile.TemporaryDirectory() as ws:
        agent = Agent(llm_client=mock_llm)
        result = agent.run(task="演示：尝试删除根目录", workspace=ws)

    blocked = any(
        entry.get("final_decision") == "BLOCKED"
        for entry in result["audit_log"]
    )
    if blocked:
        print('[演示1] 系统检测到危险命令 "rm -rf /"，已自动拦截，未执行。测试通过！')
    else:
        print("[演示1] 测试失败：命令未被拦截")
    print()


def demo_2_approval():
    """演示 2：人工审批拒绝高风险操作"""
    print("=" * 60)
    print("演示 2：人工审批拒绝删除文件")

    mock_llm = mock.Mock()
    mock_llm.get_response.side_effect = [
        json.dumps({"action": "write_file", "path": "to_delete.txt", "content": "delete me"}),
        json.dumps({"action": "finish", "summary": "rejected"}),
    ]

    def _mock_assess_high(validated, config):
        params = validated.sanitized_params
        if params.get("action") == "write_file":
            return _make_risk("high")
        return _make_risk("low")

    def _mock_approval_reject(risk):
        return ApprovalResult(approved=False, reason="REJECTED")

    with tempfile.TemporaryDirectory() as ws:
        agent = Agent(
            llm_client=mock_llm,
            assess_risk_fn=_mock_assess_high,
            approval_fn=_mock_approval_reject,
        )
        result = agent.run(task="演示：尝试删除文件", workspace=ws)

    to_delete = Path(ws) / "to_delete.txt"
    rejected = any(
        entry.get("final_decision") == "REJECTED"
        for entry in result["audit_log"]
    )
    if rejected and not to_delete.exists():
        print("[演示2] 高风险操作（删除文件）请求审批，用户拒绝。文件未被删除。测试通过！")
    else:
        print("[演示2] 测试失败：审批未生效或文件被意外创建")
    print()


def demo_3_feedback():
    """演示 3：反馈闭环 —— 测试失败后自动修正"""
    print("=" * 60)
    print("演示 3：反馈闭环 —— 测试失败后自动修正")

    with tempfile.TemporaryDirectory() as ws:
        ws_path = Path(ws)
        test_file = ws_path / "test_calc.py"
        test_file.write_text(
            "def add(a, b):\n    return a + b\n\n\ndef test_add():\n    assert add(1, 2) == 4\n"
        )

        corrected = (
            "def add(a, b):\n    return a + b\n\n\ndef test_add():\n    assert add(1, 2) == 3\n"
        )

        mock_llm = mock.Mock()
        mock_llm.get_response.side_effect = [
            json.dumps({"action": "run_command", "command": "pytest test_calc.py -v"}),
            json.dumps({"action": "write_file", "path": "test_calc.py", "content": corrected}),
            json.dumps({"action": "run_command", "command": "pytest test_calc.py -v --cache-clear"}),
            json.dumps({"action": "finish", "summary": "tests pass"}),
        ]

        agent = Agent(llm_client=mock_llm)
        result = agent.run(task="演示：修复 test_calc.py 的断言", workspace=ws, max_steps=10)

    run_entries = [
        e for e in result["audit_log"]
        if e.get("action", {}).get("action") == "run_command"
    ]
    first_ok = len(run_entries) >= 2
    first_fail = first_ok and int(run_entries[0].get("tool_result", {}).get("meta", {}).get("exit_code", 0)) != 0
    second_pass = first_ok and int(run_entries[1].get("tool_result", {}).get("meta", {}).get("exit_code", 0)) == 0
    finished = result["finish_reason"] == "finish_action"

    if first_fail and second_pass and finished:
        print("[演示3] 第一次测试失败，收到错误反馈；第二次修正后测试通过。反馈闭环工作正常！")
    else:
        print("[演示3] 测试失败：反馈闭环未按预期工作")
    print()


if __name__ == "__main__":
    demo_1_block()
    demo_2_approval()
    demo_3_feedback()
    print("=" * 60)
    print("所有演示完成！")