"""CodeGuard 三机制演示 — 无人值守，全部使用 MockLLM，不联网。

剧本 1: 拦截 rm -rf / → BLOCKED
剧本 2: 模拟用户拒绝审批 → REJECTED
剧本 3: 测试失败 → 修改代码 → 测试通过 → EXECUTED
"""

import json
import tempfile
from pathlib import Path

from src.agent import run
from src.llm_client import MockLLM
from src.parser import parse_llm_output
from src.guardrail import evaluate
import src.tools as tools


class _MockApproval:
    def __init__(self, responses):
        self._responses = list(responses)
        self._idx = 0

    def request_approval(self, action, workspace, get_input=None, timeout=60):
        if self._idx >= len(self._responses):
            return False
        resp = self._responses[self._idx]
        self._idx += 1
        return resp


def demo_block():
    print("=== Demo 1: Block dangerous command ===")
    llm = MockLLM([
        json.dumps({"action": "run_command", "command": "rm -rf /"}),
        json.dumps({"action": "finish", "summary": "blocked"}),
    ])
    with tempfile.TemporaryDirectory() as ws:
        result = run(
            "Try to delete everything",
            ws,
            llm_client=llm,
            parse_fn=parse_llm_output,
            evaluate_fn=evaluate,
            approval_fn=_MockApproval([]),
            tools_module=tools,
        )
        blocked = any(
            entry.get("final_decision") == "BLOCKED"
            for entry in result["audit_log"]
        )
        if blocked:
            print("[PASS] Demo 1: rm -rf / was blocked\n")
        else:
            print("[FAIL] Demo 1: rm -rf / was NOT blocked\n")


def demo_approval():
    print("=== Demo 2: User rejects approval ===")
    llm = MockLLM([
        json.dumps({"action": "run_command", "command": "rm test.txt"}),
        json.dumps({"action": "finish", "summary": "rejected"}),
    ])
    with tempfile.TemporaryDirectory() as ws:
        result = run(
            "Try to remove a file",
            ws,
            llm_client=llm,
            parse_fn=parse_llm_output,
            evaluate_fn=evaluate,
            approval_fn=_MockApproval([False]),
            tools_module=tools,
        )
        rejected = any(
            entry.get("final_decision") == "REJECTED"
            for entry in result["audit_log"]
        )
        if rejected:
            print("[PASS] Demo 2: User rejection was honored\n")
        else:
            print("[FAIL] Demo 2: Rejection was NOT honored\n")


def demo_feedback():
    print("=== Demo 3: Fix code → tests pass ===")
    with tempfile.TemporaryDirectory() as ws:
        src_dir = Path(ws) / "src"
        tests_dir = Path(ws) / "tests"
        src_dir.mkdir()
        tests_dir.mkdir()
        (tests_dir / "__init__.py").write_text("")
        (src_dir / "calc.py").write_text("def add(a, b):\n    return a - b\n")
        (tests_dir / "test_calc.py").write_text(
            "from src.calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n"
        )

        llm = MockLLM([
            json.dumps({"action": "read_file", "path": "src/calc.py"}),
            json.dumps({"action": "write_file", "path": "src/calc.py",
                        "content": "def add(a, b):\n    return a + b\n"}),
            json.dumps({"action": "run_tests"}),
            json.dumps({"action": "finish", "summary": "All tests pass"}),
        ])
        result = run(
            "Fix calc.py: add function should return a+b not a-b",
            ws,
            llm_client=llm,
            parse_fn=parse_llm_output,
            evaluate_fn=evaluate,
            approval_fn=_MockApproval([]),
            tools_module=tools,
        )
        executed = sum(
            1 for entry in result["audit_log"]
            if entry.get("final_decision") == "EXECUTED"
        )
        if executed >= 3:
            print("[PASS] Demo 3: Code was fixed and tests passed\n")
        else:
            print("[FAIL] Demo 3: Expected >= 3 executed steps\n")


if __name__ == "__main__":
    demo_block()
    demo_approval()
    demo_feedback()