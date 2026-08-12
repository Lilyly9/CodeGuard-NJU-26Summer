"""集成测试 — 验证拦截危险命令 + 反馈闭环自我修正，绝对不发起真实 HTTP 请求。"""

import json
import subprocess
from pathlib import Path
from unittest import mock

from src.agent import Agent


def test_block_rm_rf(tmp_path):
    mock_llm = mock.Mock()
    mock_llm.get_response.side_effect = [
        json.dumps({"action": "run_command", "command": "rm -rf /"}),
        json.dumps({"action": "finish", "summary": "blocked"}),
    ]

    with mock.patch("subprocess.run", wraps=subprocess.run) as mock_subprocess:
        agent = Agent(llm_client=mock_llm)
        result = agent.run(task="做点什么", workspace=str(tmp_path))

    blocked = any(
        entry.get("final_decision") == "BLOCKED"
        for entry in result["audit_log"]
    )
    assert blocked, f"Expected BLOCKED in audit log, got: {result['audit_log']}"

    rm_calls = [
        call for call in mock_subprocess.call_args_list
        if call.args and "rm" in str(call.args[0])
    ]
    assert len(rm_calls) == 0, f"subprocess.run was called with rm: {rm_calls}"

    assert result["steps"] == 2
    assert result["finish_reason"] == "finish_action"


def test_feedback_loop_self_correct(tmp_path):
    test_file = Path(tmp_path) / "test_calc.py"
    test_file.write_text(
        "def add(a, b):\n    return a + b\n\n\ndef test_add():\n    assert add(1, 2) == 4\n"
    )

    corrected_content = (
        "def add(a, b):\n    return a + b\n\n\ndef test_add():\n    assert add(1, 2) == 3\n"
    )

    mock_llm = mock.Mock()
    mock_llm.get_response.side_effect = [
        json.dumps({"action": "run_command", "command": "pytest test_calc.py -v"}),
        json.dumps({"action": "write_file", "path": "test_calc.py", "content": corrected_content}),
        json.dumps({"action": "run_command", "command": "pytest test_calc.py -v"}),
        json.dumps({"action": "finish", "summary": "tests pass"}),
    ]

    agent = Agent(llm_client=mock_llm)
    result = agent.run(task="修复 test_calc.py 的断言", workspace=str(tmp_path), max_steps=10)

    run_command_entries = [
        entry for entry in result["audit_log"]
        if entry.get("action", {}).get("action") == "run_command"
    ]
    assert len(run_command_entries) == 2, f"Expected 2 run_command executions, got {len(run_command_entries)}"

    first_exit = int(run_command_entries[0].get("tool_result", {}).get("meta", {}).get("exit_code", 0))
    assert first_exit != 0, f"Expected first pytest to fail (exit_code != 0), got {first_exit}"

    second_exit = int(run_command_entries[1].get("tool_result", {}).get("meta", {}).get("exit_code", 0))
    assert second_exit == 0, f"Expected second pytest to pass (exit_code == 0), got {second_exit}"

    assert result["finish_reason"] == "finish_action"
    assert result["steps"] < 10, f"Agent should finish before max_steps, got {result['steps']} steps"